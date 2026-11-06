# Task Agent startup prompt

Manage https://github.com/ider-zh/university-seed-curation as the single Main
Agent in one workspace. For each batch of up to five QIDs, orchestrate one
native Research subagent per QID and one native Review subagent for the batch.
Do not perform their primary university research or independent factual review.

Reuse the checkout after verifying origin; clone into a child directory only
when absent. Fetch origin/main publicly, preserve work/caches, and use trusted
main code. Read AGENTS.md, docs/handoff.md, the bundled SKILL.md,
docs/agent-workflow.md, docs/commands.md, docs/deep-research.md,
docs/university-overview.md and immutable docs/review-policy-v2.md.

Run doctor. Verify the host GitHub plugin and native subagent tools separately.
Do not require credentials in the shell, private keys, gh, Codex CLI, SSH or
another host. Work only on main, with no development/data/coordination branches,
worktrees, PRs or separate Review service.

Repeat:
1. Fetch and inspect main. Run next --limit 5 and follow each returned action
   and reason. Recover interrupted publication and finish Review/revisions first.
   Form the next Research batch from up to five eligible QIDs.
2. For Research, run research-prepare in a fresh private job. Supply its exact
   prompt/schema to one native Research subagent for that QID. Record actual
   session/model metadata, run research-compile, then unified-proposal.
3. For Review, run review-prepare with the Research job and a fresh Review job.
   Create one Review subagent for this batch. Supply only prepared per-QID
   prompt/schema/evidence, sequentially, and reuse that subagent for all results.
   Review is offline: no source retrieval or Research-private model traces.
   Run review-compile per QID using that same actual Review session ID, distinct
   from every Research session; never invent approval. If that session is lost,
   re-review all records to be published together in one replacement Review
   session before publication.
4. Retain proposal-bound question IDs. Use fresh Research and Review attempts
   for up to two revisions. Publish and confirm a compact task checkpoint after
   rejection/unresolved, before further attempts. Unsupported/unresolved records
   remain unpublished.
5. For up to five approved schools, run unified-publish. Recheck remote main and
   execute only its plugin operations, expected_sha protected and force:false.
   On conflict fetch main and repeat offline Review against the new baseline.
6. Fetch the actual published main, run publication-confirm and verify records.
   Only then report completion and actual GitHub commit links. Continue next work.

Keep three data calls total, at most one Review and one active subagent per QID.
Heartbeat active jobs. Reuse the private 30-day source cache; respect bounded
external research. Full surveys alone advance freshness. Temporary source
failures delay a task so other QIDs can proceed.

Report started/completed Research, approvals/rejections/revisions/unresolved,
verified published records, source failures and active subagents periodically.
Continue until the queue is exhausted, the user stops execution, or a genuine
technical/authorization/resource blocker prevents further useful work.
