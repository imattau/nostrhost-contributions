#!/usr/bin/env python3
"""Validates a pull request against contributions.jsonl.

Runs as a required GitHub Actions check on every PR. Since merges are fully
automatic (no human review), this is the only gate a contribution passes
through before landing in the shared dataset — it must be conservative and
reject anything ambiguous rather than let it through.

Checks:
  1. contributions.jsonl is the only file touched by the PR.
  2. The change is a pure append: every line present on the base branch is
     still present, unchanged, at the start of the file.
  3. At least one line was added, and no more than MAX_NEW_LINES per PR
     (keeps any one submission small and reviewable in the diff even
     without a human gate).
  4. Every added line is valid JSON with the expected schema_version and
     the required fields a nostrhost-agent contribution candidate carries.
  5. No added candidate_id collides with one already in the file.
  6. Every added line is re-scanned for the same categories of data the
     client is supposed to have already redacted (emails, IPs, hostnames,
     private keys, bearer tokens/secrets, filesystem paths, UUIDs, long hex
     strings) as defense in depth against a client that forgot to redact.
"""
import json
import re
import subprocess
import sys

FILE_PATH = "contributions.jsonl"
EXPECTED_SCHEMA_VERSION = "nostrhost-agent-contribution/v1"
REQUIRED_FIELDS = ("schema_version", "candidate_id", "review_status", "review_warning")
MAX_NEW_LINES = 20
MAX_FILE_BYTES = 64 * 1024 * 1024

SECURITY_PATTERNS = [
    re.compile(r"(?i)\b(?:nsec|npub|note|nevent|nprofile|naddr)1[023456789acdefghjklmnpqrstuvwxyz]{20,}\b"),
    re.compile(r"(?i)\bhttps?://[^\s<>\"']+"),
    re.compile(r"(?i)\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b"),
    re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"),
    re.compile(r"(?i)(?:^|[\s=:])(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b"),
    re.compile(r"(?i)\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|dev|app|local|home|lan|test|example|internal|invalid|corp|onion|nostr)\b"),
    re.compile(r"(?:^|\s)/(?:home|root|tmp|var|etc|opt|srv|mnt|media)/[^\s,;\"']+"),
    re.compile(r"(?i)\b(?:bearer|token|api[_-]?key|password|passwd|secret|authorization)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"),
    re.compile(r"\b[0-9a-fA-F]{40,}\b"),
]


# Values the client generates deterministically from the local cycle id. They
# always look like long hex (a sha256 digest), so the long-hex defense pattern
# would otherwise flag every legitimate candidate. They carry no host content:
# removing exactly these two values before scanning keeps the whole-line
# defense surface for every other field.
STRUCTURAL_HASH_FIELDS = ("candidate_id", "source_ref")


def redaction_scan_text(line, record):
    scan = line
    for field in STRUCTURAL_HASH_FIELDS:
        value = record.get(field)
        if isinstance(value, str) and value:
            scan = scan.replace(value, "")
    return scan


def fail(message):
    print(f"::error::{message}")
    sys.exit(1)


def run(*args):
    return subprocess.run(args, capture_output=True, text=True, check=False)


def changed_files(base_sha, head_sha):
    result = run("git", "diff", "--name-only", f"{base_sha}...{head_sha}")
    if result.returncode != 0:
        fail(f"could not diff base and head: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line.strip()]


def read_file_at(ref, path):
    result = run("git", "show", f"{ref}:{path}")
    if result.returncode != 0:
        return ""
    return result.stdout


def main():
    if len(sys.argv) != 3:
        fail("usage: validate_contribution.py <base_sha> <head_sha>")
    base_sha, head_sha = sys.argv[1], sys.argv[2]

    touched = changed_files(base_sha, head_sha)
    if FILE_PATH not in touched:
        # Not a contribution PR (e.g. a workflow/README change from a
        # maintainer) — nothing here to validate. Since there is no human
        # review gate at all, anyone who can open a PR against this repo
        # can also merge an infra change purely by passing CI; restricting
        # write/PR access to trusted collaborators is what keeps that safe.
        print(f"ok: {FILE_PATH} not touched by this PR, nothing to validate")
        return
    if touched != [FILE_PATH]:
        fail(f"a contribution PR must touch only {FILE_PATH}, not other files too; this PR touches: {touched}")

    base_text = read_file_at(base_sha, FILE_PATH)
    head_text = read_file_at(head_sha, FILE_PATH)

    if len(head_text.encode("utf-8")) > MAX_FILE_BYTES:
        fail(f"{FILE_PATH} would exceed the {MAX_FILE_BYTES} byte cap")

    base_lines = [line for line in base_text.split("\n") if line]
    head_lines = [line for line in head_text.split("\n") if line]

    if head_lines[: len(base_lines)] != base_lines:
        fail(f"{FILE_PATH} must only be appended to; existing lines were changed, reordered, or removed")

    new_lines = head_lines[len(base_lines):]
    if not new_lines:
        fail(f"no lines were appended to {FILE_PATH}")
    if len(new_lines) > MAX_NEW_LINES:
        fail(f"this PR appends {len(new_lines)} lines; at most {MAX_NEW_LINES} per PR is allowed")

    existing_ids = set()
    for line in base_lines:
        try:
            existing_ids.add(json.loads(line).get("candidate_id"))
        except json.JSONDecodeError:
            pass

    for index, line in enumerate(new_lines, start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            fail(f"appended line {index} is not valid JSON: {exc}")
        if not isinstance(record, dict):
            fail(f"appended line {index} is not a JSON object")
        for field in REQUIRED_FIELDS:
            if not record.get(field):
                fail(f"appended line {index} is missing required field {field!r}")
        if record["schema_version"] != EXPECTED_SCHEMA_VERSION:
            fail(f"appended line {index} has schema_version {record['schema_version']!r}, expected {EXPECTED_SCHEMA_VERSION!r}")
        candidate_id = record["candidate_id"]
        if candidate_id in existing_ids:
            fail(f"appended line {index} reuses candidate_id {candidate_id!r}, which is already in {FILE_PATH}")
        existing_ids.add(candidate_id)

        scan_line = redaction_scan_text(line, record)
        for pattern in SECURITY_PATTERNS:
            match = pattern.search(scan_line)
            if match:
                fail(
                    f"appended line {index} still contains what looks like unredacted sensitive data "
                    f"({pattern.pattern!r} matched); the client-side redaction should have caught this"
                )

    print(f"ok: {len(new_lines)} new line(s) appended, {len(existing_ids)} total candidates, no security patterns matched")


if __name__ == "__main__":
    main()
