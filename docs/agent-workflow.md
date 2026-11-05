# Native Research and Review workflow

Repository: https://github.com/ider-zh/university-seed-curation.
Run in the current workspace. Reuse the checkout and preserve existing work;
clone into a child directory only if absent. Research and Review use independent
sessions, optionally in the same checkout, with separate private jobs/caches.

## Execution boundary

The host Agent owns the connected GitHub plugin and native subagent tool.
Local Python prepares sources/tasks, validates strict JSON, generates records
and emits GitHub operation plans. It does not inherit plugin credentials or
launch Codex. No role signing keys, GH_TOKEN, gh or separate machine are required.

doctor returns local_ready after checking the repository, input catalog and
contracts. The host verifies plugin/subagent availability in its session.
Missing shell credentials are not evidence that the plugin is disconnected.

## Tasks and model budget

One Research manager selects primary candidates before discovery candidates,
using never-refreshed/six-calendar-month-old approved records. next is advisory.
The manager reads current coordination refs through the plugin and generates a
coord-plan for claims. It executes the returned blob/tree/commit/ref operations
with expected-head protection and confirms the resulting ref before assignment.

The same process grants/renews/releases global model slots: at most three calls
across both roles, at most one Review, reserving capacity for waiting Review.
A native subagent starts only after its model lease is confirmed. Renew leases
while it runs and cancel on loss. Coordination remains on GitHub, not local files.

## Research and Draft PRs

research-prepare creates a private revision-bound source packet, prompt and
strict output Schema. The manager dispatches one native subagent per QID, then
research-compile validates its returned JSON, root P625 and deterministic delta.
Actual model/session metadata is caller-reported, not provider-authenticated.
Prefer Terra medium when offered by the host; do not fabricate unavailable
metadata or introduce a CLI requirement.

draft builds raw structured native proposals under data/proposals/BATCH/, with
an explicit native manifest. No Research signature is required. Execute the
bundle's plugin operations and create a Draft PR. Each batch starts from main
in an isolated worktree/tree, at most five schools and three active PR permits.
Raw pages, caches, source corpora and model logs remain private.

## Independent Review and revisions

Review reads the public structured proposal through the plugin. review-prepare
independently retrieves pinned revisions and enumerates every fact/context and
earlier request. A fresh native subagent supplies strict checks; review-compile
rejects missing checks, same Research session, unsupported facts and unaddressed
requests. decision creates a PR/head/proposal-bound structured comment.

Comments use the university-native-review-v1 marker and actual repository-owner
GitHub attribution. Same-account sessions are a workflow separation, not
cryptographic independent identities. Only a later valid Review addressing a
request can resolve it; a head change or Research response cannot.

Research revises the same PR, maximum two rounds per school. Beyond that mark
unresolved and preserve the failed public Draft head through coordination
ancestry. Approved siblings can proceed independently after unresolved schools
are explicitly removed from the final batch.

## Finalization and completion

finalize uses current main, actual PR number and complete plugin comment history.
It requires the latest owner-authored independent approval, no open questions,
unchanged school baseline and exact deterministic record hash. It generates
canonical records, native receipts and a final manifest. Publish via guarded
plugin ref updates, mark ready, and await human merge.

Unrelated main changes permit mechanical rebind; changed same-school data needs
fresh Research/Review. Confirm immutable receipts actually reached main before
marking tasks merged. Closed unmerged PRs are unresolved, not blindly resubmitted.

Only a complete six-group survey advances update_datetime. Missing/disputed
values may remain disclosed; uncertain identity/source failures prevent complete
freshness. Partial changes preserve that timestamp.

Trusted CI checks use actual GitHub comment authors/history and exact blobs.
Required-check/branch-protection setup and event deployment remain separate.
No automatic merge is enabled. Native Review can poll via the plugin; queue-only
Actions entry remains optional and disabled until configured.
