# nostrhost-contributions

Intermediary repository for community-contributed [nostrhost-agent](https://github.com/imattau/nostrhost) planner interaction data. Each nostrhost host that opts into contribution opens a pull request appending exactly one redacted candidate as one JSON line to `contributions.jsonl`. Hugging Face's PR flow has no merge queue and no way to gate a merge on automated checks, so contributions land here first:

- **Validation** (`.github/workflows/validate.yml`, required check): every PR must touch only `contributions.jsonl`, must be a pure append (no existing line changed, reordered, or removed), must add between 1 and 20 well-formed candidate lines, must not reuse a `candidate_id` already in the file, and must not contain data matching the same redaction patterns the client is supposed to have already stripped (emails, IPs, hostnames, secrets/tokens, filesystem paths, UUIDs, long hex strings). See `scripts/validate_contribution.py`.
- **Merging** is fully automatic — there is no human review step. A PR merges once the validation check passes, serialized through GitHub's merge queue so concurrent contributions can't race each other onto `main`.
- **Sync to Hugging Face** (`.github/workflows/sync-to-huggingface.yml`): on every push to `main`, the current `contributions.jsonl` is pushed to the configured Hugging Face dataset repo. This is the dataset's canonical public home; this repo is the validation/merge pipeline in front of it.

## Repository setup (one-time, done via branch protection + repo settings)

- Branch protection on `main`: require the `validate` status check, require the merge queue, no required approving reviews.
- Repository secret `HF_TOKEN`: a Hugging Face token with write access to the target dataset repo.
- Repository variable `HF_DATASET_REPO`: the target dataset, e.g. `owner/dataset`.

## Contributing

Contributions are opened by `nostrhost-agent`'s contribution submission path (`nostrhost-agent-contribute`, or the daemon's opt-in automatic submission), not typically by hand. See the `nostrhost-agent` repository for how a candidate is built and redacted before it ever reaches a PR here.
