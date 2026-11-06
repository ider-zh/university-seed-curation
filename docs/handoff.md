# Current state and handoff

The 2026-11-06 operator decision replaces all branch/PR coordination with one
Task Agent orchestrating Research and Review subagents in one workspace.
Only main remains. Development and approved-data publication go directly to main
through the connected GitHub plugin with expected-SHA protection.

The CLI no longer exposes Draft, finalize, PR decision, coord-plan, key
registration or an alternate CLI/provider runtime. Obsolete PR Actions and
signed model-runner scripts have been removed. Pure source/evidence/materialization
checks are now shared by the native workflow instead of invoking old runners.

Five existing canonical records and all existing batch/review receipt bytes are
preserved. Historical Q681/Q1060 proposals were moved, without changing bytes,
to data/history/proposals. They are unreviewed historical evidence. Their
pending work, Q1377's interrupted task and Q519556's coordinate follow-up are
tracked by data/workflow/tasks.json. Q681's prior objection ID remains open.
A merge of the old PRs is not a Review approval or canonical publication.

The branch-cleanup manifest records the 18 removed branch names and head SHAs.
No coordination tokens or private caches were exported. Existing historical
signatures and schema files are retained for audit, not as execution modes.

Private .private/native/manager-state.json stores job progress, expiry and retries.
An OS lock serializes checkpoint writes. The manager enforces five concurrent
data calls across Research and Review combined, one active subagent per QID.
Each Research result receives its own independent Review subagent; multiple
Reviews may run concurrently. This is deliberately a single-manager
workflow, not a distributed worker service. Use the same checkout to retain
captures; without private captures, rebuild Research evidence before Review.

Run doctor, inspect next actions, then follow docs/commands.md. Source/API errors
are not successful research. Review requires a hash-verified Research snapshot
and has no network replay fallback. Publication includes task-backlog removal
in the same data commit, then publication-confirm verifies the actual commit
on fetched origin/main. Interrupted publication can be confirmed without
submitting the same batch twice.

The source adapters retain bounded online Wikidata/Wikipedia retrieval, shared
30-day captures, root P625 checks, bounded external website capture and sourced
English institutional summaries. maxlag/429/503 honor Retry-After within a
bounded local wait; longer failures return a retryable task to the manager.

Formal external dataset releases remain separate operator decisions. Local
checks, plugin permissions and actual subagent execution must be reported
separately; no runtime may fabricate a model identity or Review approval.

The final cleanup removes the v0.1 record writer, key-generation/signing tools,
standalone coordinate Review and duplicate Review formats. integrity.py verifies
the existing signed seed catalog read-only. Current Research output and the
example generator use schema v0.2.2; historical schema/data/receipt files remain
unchanged audit artifacts. The only startup prompt is references/task-agent.md.
A new publication batch requires a distinct Research session and a distinct
Review session per QID, with no shared Review or cross-role sessions. Existing
published receipts remain unchanged, including historical shared-reviewer batches.
Any unpublished shared-reviewer approvals must be re-reviewed per QID before a
new multi-QID publication. Loss of one Review session requires replacing only
that QID's Review, provided the main baseline has not changed.
