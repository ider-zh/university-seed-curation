# Agent operating contract

Read `docs/handoff.md`, your role in `docs/agent-workflow.md`, and
`.agents/skills/university-curation/SKILL.md`.

- Scope: global present and historical higher education. A candidate seed is
  not an accepted institution. Distinguish institutions, systems, branches,
  campuses, faculties, predecessors and buildings. Preserve original facts.
- This downstream project uses bounded online Wikidata and revision-bound
  Wikipedia, plus supporting websites. Use the source skill. The upstream
  wikidata-research local-dump contract remains unchanged.
- Research and Review run in separate environments. **GitHub refs, PRs and
  signed PR comments are their only shared state and communication.** Their
  caches, local checkpoints, source captures, model logs and keys remain local.
- Operator override, 2026-11-05: public **Draft PRs may hold explicitly
  unreviewed structured proposals**. No raw pages/dumps, bulk source text,
  private model outputs, traces, prompts, logs or credentials enter GitHub.
  Main receives approved canonical records and their signed receipts only.
- Both roles may use the same GitHub account. Use independent Ed25519 role
  keys, registered by separate code-only PRs. Never share private keys or
  present signed comments as a second account's formal GitHub APPROVE.
- One Research manager assigns one QID to each subagent. Terra medium is
  fixed for data calls. GitHub CAS leases enforce three total Research/Review
  calls, at most one Review, with capacity reserved when Review waits.
- Each batch has its own branch/worktree from main; no stacked data PRs.
  At most three active PR permits, at most five schools per PR. Lease loss
  cancels work. Never bypass the coordinator by directly starting model calls.
- Use skill scripts for tasks, records, signatures and Schema. Never hand-edit
  canonical JSON, revisions, receipts or coordination state.
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
  and context. A signed objection survives head changes. Only a valid independent
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
