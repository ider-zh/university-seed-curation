# Agent operating contract

Use one Main Agent in one workspace to orchestrate distinct native Research and
Review subagents. Develop and publish directly on `main`. Do not create working,
data or coordination branches, worktrees, PRs, PR permits, role-signing keys,
separate Review services, or a legacy CLI runtime.

Read docs/handoff.md, docs/agent-workflow.md and the bundled
.agents/skills/university-curation/SKILL.md. The manager startup prompt is
.agents/skills/university-curation/references/main-agent.md.

- Reuse the checkout, verify origin, fetch public origin/main and preserve private
  caches. Clone into a child directory only when absent. Use trusted main code.
- The host owns the connected GitHub plugin and native subagent tools. Python
  prepares evidence, validates JSON and emits publication operations; it never
  launches models or inherits plugin credentials. No shell token, gh, SSH, Codex
  CLI, signing key or another host is required. All GitHub writes use the plugin.
- Main Agent selects tasks, prepares/compiles jobs, tracks retries, manages
  revisions and publishes. It must not perform the subagents' primary university
  research or fabricate Review approval. Each Research subagent handles one QID.
- A distinct Review subagent checks every fact, context, locator, period, unit,
  all six coverage groups, summary and prior request against the exact prepared,
  hash-verified offline Research snapshot. Never re-fetch Review sources or give
  Review Research-private model traces. Only the manager publishes.
- Local atomic checkpoints under .private/native track active jobs and source
  failures. data/workflow/tasks.json carries portable pending-task metadata on
  main; approved records, receipts and batch manifests establish publication.
  Never infer publication from an old PR merge, task status or a local bundle.
- Run next --limit 5; it returns actions and reasons from main plus local jobs.
  It does not claim tasks. Prepare reserves the QID locally. One manager only;
  independent managers in other workspaces are unsupported. Maximum three
  concurrent data calls total and one Review; reserve capacity for waiting Review.
  Prefer Terra medium when offered; report actual metadata or not_reported.
  Heartbeat active jobs; discard results superseded by a newer job for the QID.
- On request_changes, retain request IDs and exact proposal digests. Prepare a
  fresh Research attempt with the saved feedback, maximum two revisions per QID.
  After request_changes/unresolved, checkpoint the compact task metadata to main
  and confirm it before continuing. Unresolved schools are not published. Source failures enter retry_wait, never
  an empty accepted record or a successful refresh.
- Exhaust Wikidata and relevant multilingual Wikipedia first. External searches
  address specific gaps only: at most 8 queries, 12 pages, 5 domains, 2 hops and
  15 minutes per QID. Use the bounded capture adapter; stop after two searches
  without credible new evidence. Reuse the shared private 30-day cache.
- Distinguish institutions, systems, campuses, faculties, predecessors and
  buildings. Preserve original names, subject attribution, statistical periods,
  units, qualifiers and source conflicts. Never invent absent values or zeros.
  Root Wikidata P625 is script-owned and institution-scoped, never automatically
  assigned to a campus/headquarters. Follow immutable docs/review-policy-v2.md.
- Generate a neutral evidenced English profile.summary when support permits:
  normally 180–260 words, 90–179 for sparse historical evidence, 2–3 paragraphs.
- Use script-generated canonical records and append-only deltas. Keep existing
  observations; do not hand-edit records, receipts, record revisions or hashes.
  Only a complete six-group Research + Review survey advances update_datetime.
  Partial accepted records use a separate seven-day retry interval.
- unified-publish accepts only exact approved records and emits an expected-SHA,
  non-forced main update. On conflict fetch main and prepare fresh offline Review
  on the new baseline. Verify actual remote files and run publication-confirm
  before declaring completion. At most five schools per publication batch.
- Public output contains approved structured records, permitted short evidence,
  receipts, batch manifests and compact workflow metadata. Raw dumps/pages,
  captures, cache bodies, private prompts/results/traces and credentials stay
  private. Historical proposals under data/history are unreviewed audit material.
- Schema/policy changes and official external dataset releases require an
  operator decision. Candidate-list import is not school identity acceptance.
  Offline tests do not establish actual subagent execution or live publication.
