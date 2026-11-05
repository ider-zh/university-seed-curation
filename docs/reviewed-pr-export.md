# PR validation and Review

Default runtime uses native subagents and the connected ChatGPT GitHub plugin.
No Research/Review private key, shell token, gh or Codex CLI is required.

## Public stages

Draft PRs contain explicitly unreviewed structured native proposals under
data/proposals/BATCH/ plus a native manifest. A ready data PR contains approved
canonical school JSON, native Review receipts and a final manifest. Raw source
pages, source corpora, caches, prompts, model traces and credentials stay private.

Historical signed catalog, initial-import and coordinate receipts remain intact
and verifiable. Explicit --runtime cli can still use the older signed protocol;
those runtime requirements do not apply to native agents.

## Native attribution and independent Review

The GitHub plugin supplies actual PR metadata, complete comments and their
author login/ID/body. Native Review comments carry the university-native-review-v1
marker. CI trusts only the configured repository owner's actual account
attribution, exact PR/QID/proposal digest, reviewed head, schema/policy and distinct
Research/Review sessions. Same-account roles are a workflow convention, not
cryptographic independent identities. Model/session metadata is caller-reported;
do not imply provider-signed model provenance.

Review prepares independent source captures and enumerates every changed fact,
context and previous request. Strict compile checks reject missing source/fact
coverage, unsupported facts, reused Research sessions or unaddressed questions.
Only the exact valid later Review can resolve its request IDs. Questions survive
head replacement; a Research response cannot clear them.

## Deterministic files and gates

Local draft/finalize commands emit bounded bundles and pending plugin operations.
They validate catalog membership, canonical paths, source revisions, current
school baseline, schema, preferred projection, every approval and exact record
hash. Finalization never executes a GitHub write or merges.

The host creates blobs/trees/commits and updates refs with expected-head guards.
A planned lease is not active until the ref update succeeds and is confirmed.
Archive prior public Draft heads through coordination ancestry before replacing
them. Every batch begins directly from main; same-school baseline changes require
fresh Research/Review, while unrelated main changes permit mechanical rebind.

signed-data-validation is the historical check name; it validates both native
and signed formats and rejects unreviewed Drafts, mixed code/data, stale bases
and changed receipt bytes. university-review also checks the actual PR number,
complete live comment authors/history, latest matching approval and unresolved
objections. A receipt alone cannot establish native Review provenance.

Status scans are serialized and recheck discussion/main before success.
Comment delivery and human merge are asynchronous, not atomic. Require the
appropriate checks in branch protection and await fresh results before merging.
This change does not configure protections or automatic merge.

## Accepted bootstrap

PR #10 imported 39,489 primary plus 64,667 discovery candidates and moved the
three existing records byte-for-byte to 256 buckets. Its historical Ed25519
manifest records candidate-list authorization only; agents verify it using
public trust and do not need a private key. Candidate import does not accept each
university identity. Official dataset releases still need human acceptance and
a versioned manifest.
