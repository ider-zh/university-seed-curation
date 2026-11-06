---
name: university-curation
description: Orchestrate native university Research and offline core Review subagents, recover tasks and publish approved structured data through concurrent-group pull requests with auto-merge.
---

# University curation

Use one Task Agent per workspace. Multiple groups may work concurrently.
Read AGENTS.md, docs/agent-workflow.md, docs/commands.md, docs/source-tools.md,
docs/review-scope-v3.md and references/task-agent.md from the repository root.
Reuse the checkout, verify origin, fetch trusted main and preserve private caches.
Use the host GitHub plugin and native subagents, no shell credentials or model CLI.

1. Run doctor and next --limit 5. Inspect open data PR QIDs to reduce duplicate
   research. Follow recovery, Review, revision and source-retry priorities.
2. research-prepare one QID; send its exact prompt/schema to its own Research
   subagent. Record actual metadata and compile, then unified-proposal.
3. review-prepare --research-job into a fresh private job; dispatch that QID's
   dedicated independent Review session. Use only its frozen evidence, prompt
   and schema. Compile the actual result; apply core-review-v3 scope, keeping
   sourced secondary fields without independent factual checks.
4. Preserve request IDs, at most two revisions, private snapshots and retry state.
   Checkpoint rejected/unresolved work through a generated PR.
5. unified-publish up to five approved schools. Execute its plugin plan: unique
   data/ branch, blobs/tree/commit/ref, PR targeting main, enable-auto-merge.
   Required CI validates exact reviewed data and concurrent baselines. Update
   branches after main advances; rebuild and re-review affected-QID conflicts.
6. Wait for actual merge, fetch main and publication-confirm the merge/squash
   commit. A successful branch push or opened PR is not publication.

Five concurrent Research/Review calls combined per group; reserve Review capacity,
heartbeat jobs and replace lost Review sessions independently. Never drop another
group's records or tasks when resolving conflicts. Never push data directly to main.
Use shared private 30-day cache, 90-second HTTP timeout and maxlag=30 defaults.
Root P625 remains script-owned and institution-scoped; preserve subjects, periods,
units and conflicts. Research follows docs/deep-research.md and the sourced summary
requirements in docs/university-overview.md. Immutable review-policy-v2.md guides
facts in scope; docs/review-scope-v3.md defines the mandatory independent checks.
Only complete six-group successful surveys advance freshness. Keep raw sources,
model prompts/results/traces and credentials private. Publish only generated data,
receipts, manifests and pending-task metadata. Historical receipts remain unchanged.
