# Concurrent Agent groups and PR publication

Each group has one Task Agent, private checkpoints and its own checkout. Each
QID has a distinct Research/Review session pair. Each group retains the combined
five-call limit and five-school batch limit. Main is the shared published state.

Fetch main, run doctor and next --limit 5. Inspect open data PRs to avoid duplicate
QIDs where possible. Selection is randomized advisory work, not a global lock.
Research prepares revision-bound source snapshots; Review checks the required
core IDs offline under review-scope-v3.md. Compile outputs, bind the proposal and
publish only exact approved records. Rejections retain proposal-bound requests,
two revision rounds, portable checkpoint PRs and private retry state.

unified-publish and checkpoint produce a unique data/curation-<id> branch plus
GitHub operations creating a PR and enabling auto-merge. They never update main
directly. Execute operations in order and substitute returned blob/tree/commit
SHAs and PR number. Use a new branch for each bundle. GitHub checks the generated
PR; main requires passing checks and an up-to-date branch before merging.

The data-publication check runs trusted base code and reads PR blobs without
executing PR code. It validates exact manifest/receipt/record hashes and scope,
current affected-QID baselines, pending requests, and the merged backlog. One
batch per PR; checkpoint PRs contain only backlog metadata. Independent QIDs
can proceed concurrently. Same-QID updates or overlapping pending-task changes
must be regenerated against main; unrelated merged task rows must be preserved.

If another PR merges first, update the PR branch against main and let checks run
again. If content conflicts or a QID baseline changed, rebuild from fetched main:
rebind retained Research only if its baseline is still valid, run fresh offline
Review, create a replacement bundle/PR and close the obsolete PR. Shared backlog
JSON may still produce Git conflicts; automatic merging does not resolve them.

Wait for the actual PR merge, fetch main and run publication-confirm using its
merge/squash commit. Confirmation checks ancestry and exact bundle bytes. It
supports prior direct-main plans for interrupted historical work. No source
cache, model trace or private active-job state is committed. Historical records,
receipts and v2 policy remain unchanged; new receipts identify core-review-v3.
