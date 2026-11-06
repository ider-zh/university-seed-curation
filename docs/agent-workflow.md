# Single-manager Research and Review

One Main Agent works from main, with one native Research subagent per QID and a
separate native Review subagent. Python does not launch models. The host owns
native subagent tools and the GitHub plugin. No remote coordination branches,
PRs, separate Review service or shell GitHub credentials are used.

## Select and recover

Fetch origin/main, run doctor, then next --limit 5. next combines the main backlog,
exact main publication receipts, refresh timestamps and private local jobs.
It returns qid, action, reason, revision and open_requests. The priority order is
verify interrupted publication, publish approved work, Review, Research revision,
then new/recovered Research, primary before discovery. next remains advisory.

Prepare records an active local job under an OS-locked atomic checkpoint. It
rejects duplicate active QIDs and exhausted capacity. There are at most three
active data calls including at most one Review; waiting Review reserves capacity.
Run job-heartbeat while a subagent is active. Job expiry permits recovery but
keeps completed Research/Review progress. Compilation checks the current job
identity so an obsolete job cannot replace newer work.

Temporary source failures enter retry_wait with retry_after and a resume phase.
Validation errors keep outputs private. A completed partial survey has a separate
seven-day retry interval; only full-refresh update_datetime has six-month freshness.

## Research and offline Review

research-prepare generates a fresh private job containing sources, root entity,
prompt and strict schema. The manager supplies exactly these to Research, records
its actual session/model metadata and runs research-compile. unified-proposal
binds the compiled proposal to repository/catalog/schema/policy and main baseline.

review-prepare requires --research-job. It verifies the Research packet/root
hashes, copies the evidence into a separate Review job, and prepares every fact,
context and prior request for Review. No HTTP retrieval fallback exists. Review
reads only its packet/prompt/schema and returns strict JSON in a distinct session.
review-compile validates complete coverage and cannot turn an incomplete or
contradictory assessment into approval.

request_changes creates proposal-bound request IDs in the local checkpoint.
The next Research attempt automatically receives the saved open_requests unless
explicit feedback is supplied. At most two revisions per QID; unresolved or
exhausted cases remain unpublished. Responses do not themselves constitute a
Review approval. After request_changes/unresolved, use checkpoint, execute its
main update and confirm it before continuing. This preserves question IDs and
revision counters across loss of the private workspace. Publication bundles also
checkpoint all other pending tasks using portable metadata.

## Direct publication

unified-publish revalidates exact proposals, offline Review jobs/attempts,
source counts, six coverage groups, canonical hashes and current main baseline.
It produces only canonical records, receipts, a batch manifest and the updated
main task backlog. Other pending backlog rows are preserved exactly.

Execute its blob/tree/commit/ref operations through the GitHub plugin. The main
update has expected_sha and force:false. On conflict, fetch main and repeat
Review against the new baseline before rebuilding the bundle.

Fetch the published main and run publication-confirm against the actual commit.
It checks the planned parent, main ancestry and every file hash before recording
completed. If the process stopped after the ref update, confirm that same bundle
and commit; do not create a replacement batch. Main manifests and receipts are
authoritative across sessions. A local state or successful operations plan alone
is not publication.

## Storage and history

Keep source captures, model results/prompts and job paths private. Main contains
compact portable backlog metadata, not raw packets or active-worker secrets.
Private jobs can optimize recovery in the same workspace; after their loss,
rebuild evidence from the retained QID and open questions.

Frozen historical proposals are under data/history/proposals; current commands
never read them as an approved proposal or re-enable their old PR protocol.
Canonical observations and signed historical receipt bytes are not rewritten
by this workflow migration. Dataset schema/policy and official release decisions
remain operator controlled.
