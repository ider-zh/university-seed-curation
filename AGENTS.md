# Agent operating contract

Multiple Agent groups may work concurrently, each with one Task Agent and its
own checkout/private state. Reuse the checkout, verify origin and fetch main.
Develop and publish through unique branches and pull requests targeting main.
Never push data or checkpoints directly to main. Use the connected GitHub plugin;
no shell token, signing key, gh, SSH or separate model runtime is required.

Read docs/handoff.md, docs/agent-workflow.md, docs/commands.md and the bundled
.agents/skills/university-curation/SKILL.md. Start from its references/task-agent.md.

- Each QID has its own Research subagent and independent Review subagent session.
  The Task Agent orchestrates and publishes, never fabricates factual Review.
  Maximum five concurrent Research/Review calls per group, at most five QIDs per
  batch; reserve capacity for waiting Reviews. Heartbeat active jobs.
- Select with next --limit 5. Random selection is advisory, not a distributed
  claim. Groups can overlap; PR checks reject stale affected-school baselines.
  Inspect open data PR QIDs before dispatch to reduce duplicate research.
- Use trusted main code. Source captures, prompts, model traces, raw pages/dumps
  and credentials remain private. Shared local source cache TTL is 30 days.
  Wikimedia HTTP socket timeout defaults to 90 seconds, maxlag to 30; retryable
  failures enter retry_wait and are never accepted as empty successful data.
- Optional external-page acquisition failures do not block Research/Review.
  Freeze each failure and survey limitation alongside successful sources; never
  claim full-refresh freshness from a failed survey. Unsupported core facts or
  unresolved eligibility still block publication. Contract/integrity errors fail closed.
- Review uses only the frozen hash-verified Research packet, no new retrieval or
  private Research traces. Apply docs/review-scope-v3.md and immutable factual
  guidance docs/review-policy-v2.md. Only mandatory core IDs need factual checks;
  supplementary data remains sourced and structurally validated. Receipts
  disclose reviewed/unreviewed scope and explicitly waived historical objections.
- Preserve institution/system/campus/predecessor boundaries, source meanings,
  periods, units, currencies and conflicts. Root P625 is script-owned and
  institution-scoped. Do not invent absent values or zeros. Research generates
  a sourced neutral English summary under docs/university-overview.md.
- Research-compile, unified-proposal, review-prepare and review-compile produce
  exact append-only structured data. No hand-editing canonical records, hashes,
  receipts or revisions. Only full successful six-group surveys advance freshness.
- Retain proposal-bound request IDs; maximum two Research revision rounds.
  Rejected/unresolved work stays unpublished. Checkpoint pending metadata via PR.
- unified-publish emits a unique data branch, blob/tree/commit/ref operations,
  PR creation and enable-auto-merge. Execute the generated plan through GitHub.
  Auto-merge requires protected-main status checks. Keep the source branch
  current; if validation reports a changed QID or task baseline, fetch main,
  rebind unchanged Research only if valid, prepare fresh Review, rebuild the
  bundle and replace/close the obsolete PR. Never resolve conflicts by dropping
  another group's records, receipts or pending tasks.
- Wait until the PR actually merges, fetch origin/main, and publication-confirm
  the actual merge/squash commit and exact file hashes. A branch push, PR opened,
  successful CI or auto-merge request is not completed publication.
- Schema/policy changes and formal external releases require an operator
  decision. Historical receipts are immutable audit artifacts. Ordinary code
  and data changes both use PRs; only generated data belongs in data/ branches.
