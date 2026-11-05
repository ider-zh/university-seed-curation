# Current state and handoff

The active implementation is the **distributed GitHub-only workflow**.
The former shared-host queue is a historical offline prototype, not production
authority. Original trials and source captures remain private and unchanged.

Main at implementation start: `e219d7b` (PR #5). It contains three approved
school records. PRs #6/#7 were merged into feature branches, not main; those
merges do not prove main has the bucket migration or Q519556 coordinate fix.

Candidate import plus byte-preserving path bootstrap is on `codex/data/seed-bootstrap`
(the earlier catalog-only branch is preserved):
`data/seeds/primary.json` has 39,489 rows (34,672 included / 4,817 needs_review);
`discovery.json` has 64,667 legacy-only QIDs. A signed manifest records exact
source hashes and operator authorization for **candidate import only**.
This is not factual acceptance or an external dataset release.

Merge order: distributed implementation code first, then the independent
candidate import against main. The bootstrap data PR may include a byte-identical
three-hex to two-hex path migration; it must not include school fact changes.
Q519556 coordinates remain a separate reviewed change.

Implemented: role key registration, compact seed import, GitHub CAS task/model/
PR leases, bounded Research and independent Review, signed persistent objections,
two-round revision entry, approved-only PR materialization, stale-base checks,
private incremental recency indexing, and deployable trusted-main event scripts.
All skill implementation remains inside the skill folder.

Not yet configured or demonstrated: independent role keys on their eventual
hosts, a real distributed model run, enabled event queue dispatch, a continuously
running Review worker, required statuses/branch protection, or automatic merge.
No webhook/service is deployed. Event dispatch defaults off. Human merging
remains explicit. Signatures attest role-held keys, not provider-signed model
identity or two distinct GitHub users.

Read README → AGENTS → role startup prompt / SKILL. Consult the data contract,
commands, source tools and immutable review-policy-v2 only as needed.
Historical designs are available in Git history; do not duplicate old operating
instructions into current docs.
