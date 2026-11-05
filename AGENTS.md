# Agent operating contract

## Unified workflow override (2026-11-05)

The operator has replaced the separate Research/Review PR workflow for **new**
data batches. A single main Agent manages native Research subagents (one QID per
subagent), audits their results itself using the exact private captured source
snapshot, then uses `unified-publish` and the connected GitHub plugin to commit
only approved canonical data and receipts directly to `main`, guarded by its
expected SHA. No data PR, independent Review session, duplicated source fetch,
or human merge is required for these routine approved records. This is a
main-Agent review, **not independent cryptographic attestation**. Human approval
still governs schema/policy changes and official dataset releases. Existing PRs
and their Review objections remain historical unresolved work; never silently
consider them merged. Previous role/PR rules below are legacy compatibility,
not instructions for new unified batches.

Research exhausts Wikidata/Wikipedia first, then conducts bounded external
gap searches (maximum 8 queries, 12 pages, 5 domains, 2 hops, 15 minutes per
QID). Keep external leads private until a validated external-source adapter
exists; current schema only accepts revision-bound Wikimedia facts. Review must
read Research's hash-verified immutable snapshot **offline** and never re-fetch
source pages. See `docs/commands.md` and `docs/deep-research.md`.

Read `docs/handoff.md`, your role in `docs/agent-workflow.md`, and
`.agents/skills/university-curation/SKILL.md`.

- Scope: global present and historical higher education. A candidate seed is
  not an accepted institution. Distinguish institutions, systems, branches,
  campuses, faculties, predecessors and buildings. Preserve original facts.
- This downstream project uses bounded online Wikidata and revision-bound
  Wikipedia, plus supporting websites. Use the source skill. The upstream
  wikidata-research local-dump contract remains unchanged.
- Run in the current workspace, reusing its checkout; clone into a child directory
  only if absent. Research and Review may use the same workspace in independent
  sessions with separate private jobs, caches and checkpoints. **GitHub refs, PRs
  and signed PR comments remain their shared task state and communication.**
  Source captures and model logs remain private. Preserve existing work and
  use script-managed worktrees for isolated PR branches.
- Operator override, 2026-11-05: public **Draft PRs may hold explicitly
  unreviewed structured proposals**. No raw pages/dumps, bulk source text,
  private model outputs, traces, prompts, logs or credentials enter GitHub.
  Main receives approved canonical records and their signed receipts only.
- Default runtime uses the connected ChatGPT GitHub plugin and the host's native
  subagents. Research and Review need no private keys, shell tokens, gh, Codex CLI,
  SSH or separate hosts. Local doctor cannot authenticate a host plugin; the
  Agent checks plugin/subagent availability in its own session.
- Both roles may use the same GitHub account. Native structured PR comments must
  come from the configured repository-owner account and bind actual PR/proposal/
  schema/policy/session. Independent sessions are a workflow requirement, not
  cryptographic role identity or a second account's formal GitHub APPROVE.
  Preserve historical signatures; --runtime cli is explicit compatibility only.
- One Research manager assigns one QID to each subagent. Terra medium is
  fixed for data calls. GitHub CAS leases enforce three total Research/Review
  calls, at most one Review, with capacity reserved when Review waits. Generate
  coord-plan operations locally, execute them through the plugin, and confirm
  the guarded ref update before treating a tentative result as a lease.
- Each batch has its own branch/worktree from main; no stacked data PRs.
  At most three active PR permits, at most five schools per PR. Lease loss
  cancels work. Never bypass the coordinator by directly starting model calls.
- Use skill scripts for tasks, records, signatures and Schema. Never hand-edit
  canonical JSON, revisions, receipts or coordination state. Native subagents
  return strict JSON to local prepare/compile scripts; scripts do not launch models.
- Missing business values are omitted: no null/blank placeholders or invented
  zeros. Explicit source unknown/no-value and attempted coverage remain visible.
- Every claim identifies its subject, meaning, period/unit and provenance.
  Preserve conflicts, source languages and statement/revision locators.
  Do not substitute city points for institution coordinates or retrieval dates
  for measurement years. Root P625 is script-owned.
- Follow immutable `docs/review-policy-v2.md`: allow grounded concept adaptation
  and disclosed reasonable inference. Wrong subjects, values, units, fabrication
  and unsupported legal independence fail. Missing optional fields alone do not.
- Review independently retrieves cited revisions and verifies every changed fact
  and context. An owner-attributed Review objection survives head changes. Only a valid independent
  Review decision addressing it can resolve it. Research revises the same PR.
  Maximum two revisions per school; then unresolved. Preserve failed public
  Draft heads through coordination ancestry before branch replacement.
- Scripts materialize approved append-only deltas; existing observations are
  retained. Withdrawals/arbitrary rewrites and unsupported source adapters need
  separate reviewed implementation. Approved siblings can proceed after failed
  schools become explicitly unresolved.
- update_datetime advances only after a complete six-group Research + Review
  survey. Ordinary/partial/batch changes preserve it. Missing/disputed values
  can remain explicit after a completed survey; unresolved identity or retrieval
  failures prevent complete status. A partial retry backoff is not freshness.
- Do not auto-merge. Human approval controls role trust, major Schema changes and
  official releases. Candidate-list import authorization is separate from school
  identity acceptance. No implicit Hugging Face or other publication.
- Deployment, event dispatch, required-check/branch-protection configuration and
  provider-signed model identity are not assumed. Report their actual status.
  Offline tests do not establish a live distributed deployment.
