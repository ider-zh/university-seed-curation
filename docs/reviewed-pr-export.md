# Reviewed data PR export, v1

This adapter closes the initial-import path from the real private Terra pilot to
a small signed data PR. It does not enable arbitrary v0.2 record updates, production
model dispatch, automatic publication, formal GitHub reviewer identity, protected
merge or an official dataset release.

## Commands

Run from the repository with its dependencies installed. Keep the signing key on
the trusted coordinator, outside all public worktrees and model evidence packets.
The public key and accepted schemas/policy are reviewed in `.curation/review-trust.json`.

```text
python .agents/skills/university-curation/scripts/curate.py pr-key-init --key .private/keys/review-export.pem
python .agents/skills/university-curation/scripts/curate.py pr-build --pilot-root .private/pilots/RUN --qids Q13371 Q1075625 Q519556 --batch-id github-pilot-001 --base-ref origin/main --key .private/keys/review-export.pem --output .private/pr-pilot/PREVIEW
```

`pr-build` only prepares a private bundle. It audits actual Research output and
quantitative supplements, the complete Review input/policy/prompt and output
schema, every fact/context check, independently captured source revisions,
script-generated preferred values, inference annotations and record timestamps.
Its offline source replay has no network fallback. All original attempts remain
private. It refuses existing university records: incremental domain updates need
a separate bounded diff task, not an overwrite through the pilot importer.

Without explicit data acceptance, the preview is marked
`awaiting_human_data_acceptance` and cannot pass public PR validation or staging.
A code PR merge does not accept the school data. After the operator explicitly
accepts the exact private content scope, record that instruction through the script:

```text
python .agents/skills/university-curation/scripts/curate.py pr-record-acceptance --bundle .private/pr-pilot/PREVIEW --human-actor ider-zh --approval-ref OPERATOR_CONFIRMATION_REFERENCE --output .private/acceptances/github-pilot-001.json
python .agents/skills/university-curation/scripts/curate.py pr-build --pilot-root .private/pilots/RUN --qids Q13371 Q1075625 Q519556 --batch-id github-pilot-001 --base-ref origin/main --key .private/keys/review-export.pem --acceptance .private/acceptances/github-pilot-001.json --output .private/pr-pilot/ACCEPTED
```

Agents must not invent that instruction/reference or interpret a code merge as
data acceptance. The reference is an operator assertion recorded by the trusted
coordinator; it is not an independently authenticated GitHub approval event.
Acceptance binds the exact record bytes, inference summaries and contract hashes.
It survives a code-only rebase only while those approved contents remain unchanged.
The batch itself separately binds the exact current base commit.

Once the exporter/trust workflow is merged, create a clean data branch from the
current `origin/main`, then stage the accepted bundle:

```text
python .agents/skills/university-curation/scripts/curate.py pr-stage --workspace PATH_TO_DATA_WORKTREE --bundle ABSOLUTE_PRIVATE_ACCEPTED_BUNDLE
python .agents/skills/university-curation/scripts/curate.py pr-validate --workspace PATH_TO_DATA_WORKTREE --base-ref BASE_SHA --head-ref HEAD_SHA
```

Staging checks the public trust policy from the base Git commit, the entire batch,
human acceptance and every target before writing any file. Existing uncommitted
work is never overwritten. Repeated identical staging is safe. The command does
not create a commit, open a PR, send a message or merge; the manager performs those
observable GitHub operations after this gate.

## Public files

- `data/universities/<sha256(QID)[:3]>/<QID>.json`: complete reviewed record.
- `data/reviews/<batch>/<QID>.json`: signed concise per-school approval and
  allowlisted inference explanations, source-check counts, model configuration,
  independent sessions and private-evidence digests. No raw pages or model logs.
- `data/batches/<batch>.json`: signed membership, record/receipt hashes, base
  commit, content acceptance and human reference.

All JSON is script-encoded as UTF-8/LF with sorted keys. Signing uses a domain-
separated Ed25519 envelope. Schemas are hashed as canonical parsed JSON; policy
text and prompt text normalize line endings. This avoids Windows CRLF vs Linux LF
mismatches while preserving the actual model input and source values. Private
annotation objects never pass through wholesale, and public evidence excerpts
are limited to 1,000 characters. Free-form explanations still require the
operator's privacy inspection; bounds are not an automatic redaction guarantee.

## Trusted validation and rollout

`pr-validate` reads proposed **Git blobs**, not Python/code from the proposed tree.
Trust keys, schema hashes, review policy and validator come from the base branch.
A data PR cannot also change code, workflows, trust configuration or previous batch
receipts. Wrong buckets, executable/symlink blobs, deletions, unsigned/tampered
payloads, missing members, stale baselines, session reuse and unaccepted imports
fail. Code-only PRs remain valid; `.private` files are forbidden in all PRs.

`.github/workflows/reviewed-data.yml` uses `pull_request_target`, read-only token
permissions, pinned actions and separate base/proposed checkouts. It installs and
runs only base code; proposed files are treated as data. No model credential,
signing key, publication or merge operation is used in CI. This workflow activates
only after this integration PR is merged. The existing PR CI tests the integration
code before that merge.

Required checks, strict up-to-date-base enforcement and protected merge are not
configured by adding this workflow. Until those repository settings are verified,
the operator retains the visible merge decision and should rerun validation
against the current base immediately before merge. Do not claim an old green
check proves the PR is current after `main` advances.

## Explicit trust assumptions

The signature authenticates the local coordinator's assertions and detects
changes by a PR author without its key. It does **not** cryptographically prove
that OpenAI executed a particular model: private provider logs are locally owned
and mutable. The exporter checks their internal consistency, complete trusted
prompt, actual event/result agreement and source capture chain. Backend model
telemetry can be absent and is reported as such. Human approval references are
also coordinator-recorded assertions. A compromised coordinator/key can forge
these assertions; no stronger remote attestation is claimed.

Research/Review workers must not receive the signing key. On POSIX it is created
with mode 0600. On Windows the initializer sets a current-user-only DACL before
writing private bytes; Windows permissions cannot be inferred from `0o600`.
Machine administrators and the coordinator account remain trusted. Key rotation
or revocation is a reviewed trust-policy code PR, separate from data changes.

References: [Ed25519 API](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/),
[GitHub workflow event semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request_target).
