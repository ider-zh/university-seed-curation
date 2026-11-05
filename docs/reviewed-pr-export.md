# Trusted PR data validation

Two current public stages exist. Draft PRs contain explicitly unreviewed signed
structured proposals under data/proposals/BATCH/. A ready data PR contains only
approved canonical school JSON, dual-sign review receipts and a signed batch.
Raw sources, model traces, private keys and logs never enter either stage.

## Trust and separation

Trusted main provides the implementation, Schema/policy hashes, legacy approval
keys and separate role descriptors under .curation/roles/research/ and review/.
Research and Review keys cannot impersonate each other or legacy human acceptance.
Registration is code-only and human-merged. The same GitHub login may post both
roles' comments; signatures identify keys, not separate users or provider-signed
model execution.

Every independent Review decision binds the exact proposal digest, repository,
actual PR number, reviewed head, schema, policy and fresh model session. Scripts
materialize the final record deterministically from its current main baseline.
They preserve existing observations, remap source references, recompute preferred
and check the resulting hash. Arbitrary withdrawal/overwrite is unsupported.

## Merge gates

signed-data-validation runs trusted base code against proposed blobs as data.
It rejects unreviewed Drafts, changed baselines, mixed code/data, untrusted keys,
forged records and incomplete receipts. A valid Draft failing this final-data
check is expected until independent Review has completed.

The separate university-review status also reads the actual PR and signed comment
history. It rejects replay from a different PR, older approvals superseded by
a later decision, and outstanding signed objections. Only the exact validated
final decision can resolve an objection. Unsigned or malformed comments have no
authority. PR events, signed comment changes and main updates trigger rechecks.

These checks are enforceable merge barriers only after repository protection
requires both signed-data-validation and university-review. Protection is not
configured by this change; do not describe automatic merge as operational.
Model Review dispatch is separate and defaults off. No service is deployed.
Status scans are serialized and recheck discussion/main immediately before a
successful status. GitHub comment delivery and human merge are asynchronous,
not an atomic transaction; inspect the current discussion and wait for fresh
checks before merging. No atomic automated merge guarantee is claimed.

## PR independence and archival

Each batch starts from main in its own worktree, never another batch branch.
After approval, Research rebuilds main + approved files; failed Draft commits do
not become main ancestors. Before replacing a head, scripts preserve it through
coordination ancestry. GitHub PR comments retain signed feedback. Missing local
Research files do not prevent Review from fetching sources independently.

Unrelated main changes permit a mechanical rebind using identical proposal and
Review bytes. Same-school baseline changes require another model review.
The actual final receipt must appear in main before task completion is recorded.

## Bootstrap and legacy compatibility

The signed seed catalog is a candidate-list projection authorized by the operator;
it does not accept individual university facts. Its three files are validated
against exact source hashes/counts and a human acceptance reference. The one-time
bootstrap may also move existing school paths byte-for-byte from three hex digits
to two. No school facts may change in that structural PR.

Legacy accepted initial imports and bounded P625 coordinate receipts remain
verifiable with their original adapters and immutable policy. They do not grant
new role keys permission to bypass the distributed workflow. Official dataset
release still requires separate human acceptance and a versioned manifest.
