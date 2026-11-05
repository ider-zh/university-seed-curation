# GitHub Research / Review pilot (current contract)

This is an operational boundary, not a declaration that two independent GitHub
App installations or a production review pipeline have been configured. The
initial design is preserved in history; see `reviewed-pr-export.md` for the
implemented initial-import and bounded coordinate adapter.

## Three distinct identities

| Layer | Research | Independent Review | Trusted coordinator/operator |
| --- | --- | --- | --- |
| Model execution | Fresh Research session and private proposal | Fresh, different Review session; re-fetches pinned sources | Independently audits complete traces and holds the signing key |
| GitHub | Data-author GitHub App/account (not configured) | Separate GitHub App/account with required review authority (not configured) | Human final merge/acceptance; must not impersonate the reviewer |
| Authority | Cannot approve its own work or merge | Cannot change candidate data while approving | May stage approved bytes; may not invent human acceptance |

Two different model session IDs **do not prove** two GitHub identities. A review
comment using the same `ider-zh` connection as the proposer is not independent
GitHub approval. The local Ed25519 receipt is a coordinator assertion, not a
provider-signed model identity or a GitHub review by the second account.

## Synthetic test (no school data, no external mutation)

```sh
python -m pip install -e .
python .agents/skills/university-curation/scripts/maintain_schema.py check
python -m unittest discover -s tests -v
```

`tests/test_pr_export.py` creates an ephemeral Git repository, a synthetic QID
and local signing key, separate Research/Review session identifiers, a signed
test-only acceptance, and a data branch. It validates the complete data diff
against the exact branch head. Failure cases include forged review signatures,
reused sessions, false source revisions, out-of-scope raw pages, stale Git
baselines, changed PR heads and malformed Schema. Synthetic acceptance is never
an operator approval and those test fixtures are never staged to the real
`data/universities/` tree. No source pages or private logs are uploaded.

## Real GitHub data PR gates

1. Configure separate Research-author and Review GitHub identities. Verify
   the reviewer cannot write the proposal as the author and the author cannot
   satisfy the required independent review. Keep coordinator signing material
   outside either agent's worktree and tools.
2. Complete a private, revision-bound Research task and a fresh independent
   Review, preserving source captures, provider traces and failures privately.
3. For an initial school import, obtain explicit *human data-content acceptance*
   for the exact export scope. A code PR merge does not count. Prepare using
   `pr-build`, then `pr-stage` only after acceptance. Other adapters have their
   own explicit bounded authorization, not an invented acceptance.
4. Open a **data-only** PR from the accepted bundle, targeting the current
   `main`. Require the `signed-data-validation` check on the immutable PR head.
   Review must examine the exact current head after the last push. Do not
   modify Schema, validator, trust keys, workflows or unrelated files in it.
5. Re-check base and PR head before the operator manually merges. If `main`
   advances, regenerate or rebind the batch as appropriate and rerun checks.
   Merge/public dataset release/automated publication remain separate actions.

Not yet configured/verified here: separate GitHub review identity and effective
branch protection/required checks. Without both, even a green signed-data check
is **not** a production-quality, independently approved GitHub merge gate. No
automatic merge or production release is enabled.
