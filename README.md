# nostrhost-contributions

Intermediary repository for community-contributed [nostrhost-agent](https://github.com/imattau/nostrhost) planner interaction data. Each nostrhost host that opts into contribution opens a pull request appending exactly one redacted candidate as one JSON line to `contributions.jsonl`. Hugging Face's PR flow has no merge queue and no way to gate a merge on automated checks, so contributions land here first:

- **Validation** (`.github/workflows/validate.yml`, required check): every PR must touch only `contributions.jsonl`, must be a pure append (no existing line changed, reordered, or removed), must add between 1 and 20 well-formed candidate lines, must not reuse a `candidate_id` already in the file, and must not contain data matching the same redaction patterns the client is supposed to have already stripped (emails, IPs, hostnames, secrets/tokens, filesystem paths, UUIDs, long hex strings). See `scripts/validate_contribution.py`.
- **Merging** is fully automatic — there is no human review step. A PR merges once the validation check passes. (GitHub's merge queue would additionally serialize concurrent contributions so they can't race each other onto `main`; it isn't enabled on this repo yet — see below.)
- **Sync to Hugging Face** (`.github/workflows/sync-to-huggingface.yml`): on every push to `main`, the current `contributions.jsonl` is pushed to the configured Hugging Face dataset repo using a [Trusted Publisher](https://huggingface.co/docs/hub/trusted-publishers) (OIDC) — no long-lived `HF_TOKEN` secret is stored in this repo. This is the dataset's canonical public home; this repo is the validation/merge pipeline in front of it.

## Repository setup (one-time)

Done already, via branch protection + repo settings:
- Branch protection on `main`: require the `validate` status check (strict — PRs must be up to date with `main`), no required approving reviews, no force-pushes/deletions.
- `allow_auto_merge` and `allow_update_branch` enabled, so a PR merges itself once the check is green and stays up to date with `main` while waiting.

Still needed before the sync workflow will succeed:
- On the target Hugging Face dataset repo's `Settings > Trusted Publishers`, add a publisher with provider **GitHub Actions** and claims `repository=imattau/nostrhost-contributions`, `branch=main`, `workflow=sync-to-huggingface.yml`.
- Set the repository variable `HF_DATASET_RESOURCE` on this repo to `datasets/<owner>/<dataset>`.
- Attempted but not yet enabled: GitHub's **merge queue** on `main`, which would fully serialize concurrent contribution PRs instead of relying on strict status checks + branch auto-update. The API rejected the ruleset (`Invalid rule 'merge_queue'`) — likely needs enabling once from the repo's Settings > Rules UI first. Worth revisiting if contribution volume gets high enough for merge races to actually happen.

## Contributing

Contributions are opened by `nostrhost-agent`'s contribution submission path (`nostrhost-agent-contribute`, or the daemon's opt-in automatic submission), not typically by hand. See the `nostrhost-agent` repository for how a candidate is built and redacted before it ever reaches a PR here.
