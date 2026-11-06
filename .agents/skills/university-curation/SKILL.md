---
name: university-curation
description: Orchestrate native Research and offline Review subagents for university data, recover tasks and publish approved records directly to main through the connected GitHub plugin.
---

# University curation

Use one Task Agent in one workspace, native Research and Review subagents, and
only the main branch. Read AGENTS.md, docs/handoff.md, docs/agent-workflow.md and
docs/commands.md. Start with references/task-agent.md. Research and Review role
references describe subagent responsibilities, not standalone worker services.

Verify the checkout origin, fetch public origin/main and preserve private work.
Clone into a child directory only when absent. Use trusted main code. The host
owns GitHub plugin and native subagent tools; Python never launches a model or
requires a shell token, signing key, gh, Codex CLI, SSH or another host.

1. Run doctor and next --limit 5. Follow returned actions/reasons, prioritizing
   interrupted publication, approved work, Review and revisions. Do not read or
   create coordination branches, PRs, permits or distributed role registries.
2. Run research-prepare for one QID in a fresh private job. Dispatch its exact
   prompt/schema to a native Research subagent. Record actual metadata, compile
   its JSON, then use unified-proposal before Review.
3. Run review-prepare with --research-job into a fresh private Review directory.
   Create a dedicated Review subagent for each QID and pass only its prepared
   packet/prompt/schema. Review different QIDs in parallel. Compile each result
   with its actual Review session ID, distinct from every Research session and
   every other QID's Review session.
   It must check the frozen hash-verified snapshot offline, not re-fetch sources
   or read Research-private model traces. Run review-compile on its actual JSON.
4. On request_changes, retain request IDs/proposal hashes, start fresh Research
   with saved feedback and repeat Review. After rejection/unresolved, publish and
   confirm a compact checkpoint of questions/revision counters before continuing.
   Maximum two revisions. Never fabricate
   approval or publish unresolved cases. next returns pending actions and recovery
   reasons from local checkpoints and main's compact backlog.
5. Run unified-publish for up to five approved schools. Execute exactly its
   GitHub blob/tree/commit/ref plan with expected_sha and force:false on main.
   Refresh and re-review on conflict. Fetch the actual published main and run
   publication-confirm before reporting completion.

Keep at most five active data calls across Research and Review combined, with
one active subagent per QID. Prioritize waiting Reviews, reserve capacity for
them and heartbeat active jobs. If one reviewer is lost, replace only that QID's
Review in a fresh session while other approvals remain valid on the same main
baseline. Use the same workspace for private recovery.
After a cache/job loss, rebuild evidence; a public historical proposal is not a
substitute for captured sources. Historical receipts remain audit artifacts.

Exhaust Wikidata and relevant multilingual Wikipedia before targeted external
gap research. Limits per QID: 8 queries, 12 pages, 5 domains, 2 hops, 15 minutes;
stop after two searches without credible new information. Use the bounded
external capture adapter, hash-bound paragraph evidence and shared private
30-day cache. Read docs/deep-research.md and docs/source-tools.md.

Preserve institution/system/campus/predecessor boundaries, original language,
periods, units and conflicts. Omit absent business values; never invent zeros.
Root P625 is script-owned and institution-scoped. Use deterministic append-only
materialization, not hand-edited canonical JSON or receipt/hash repairs.
Follow immutable docs/review-policy-v2.md. Full six-group surveys alone advance
update_datetime; partial accepted work has a separate seven-day retry interval.

Generate a sourced neutral English profile.summary when possible, normally
180–260 words, 90–179 for sparse evidence, in 2–3 paragraphs; read
docs/university-overview.md. Keep raw pages/dumps, captures, prompts, model
outputs/traces and credentials private. Only approved records, permitted short
excerpts, manifests, receipts and compact task metadata are published.
