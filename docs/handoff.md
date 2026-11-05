# Current state and handoff

## Operator decision, 2026-11-05 (supersedes workflow below)

New university data batches use a single main Agent with native Research
subagents. The main Agent performs explicit structured Review on Research's
hash-verified, revision-bound **offline** snapshot. No duplicate web requests
from Review, independent Review session or data PR. Approved batches are
materialized and posted directly to main with a guarded expected-head update;
schema changes and official dataset release still need a human decision.
External deep research is constrained to 8 searches/12 pages/5 domains/2 hops/
15 minutes per QID, after fully inspecting Wikidata/Wikipedia. The existing
schema supports website facts; a bounded HTTPS capture adapter now provides
hash-bound website evidence and reuse across offline Review. Main-page
`profile.summary` is a sourced 180–260-word English overview (90–179 if sparse).
See docs/commands.md, docs/deep-research.md, docs/university-overview.md. The
rest of this handoff is historical background about the previous two-session
PR workflow, not current operating instruction.

The active implementation is the **GitHub-coordinated workflow**, executed in
the current workspace using the connected GitHub plugin and native subagents.
Research and Review use independent sessions and separate private jobs/caches;
they may share a checkout. No keys, shell tokens, gh or Codex CLI are required.
The former shared-host queue is a historical offline prototype, not production
authority. Original trials and source captures remain private and unchanged.

PR #9 (workflow) and PR #10 (seed/bucket bootstrap) are merged. At `2790342`,
main contains the signed candidate catalog and three approved school records
under the two-hex, 256-bucket layout. Their bytes were preserved during migration.
Q519556's coordinate correction remains a separate reviewed change; earlier
feature-branch merges did not apply that correction to main.

The candidate files are now versioned on main:
`data/seeds/primary.json` has 39,489 rows (34,672 included / 4,817 needs_review);
`discovery.json` has 64,667 legacy-only QIDs. A signed manifest records exact
source hashes and operator authorization for **candidate import only**.
This is not factual acceptance or an external dataset release.

The startup prompts reuse the current workspace checkout and preserve existing
work. If absent, clone into a child directory of that workspace. Scripts isolate
per-PR branches/trees. agent.py defaults to native mode: doctor checks local
contracts, prepare/compile handle model JSON, and coord-plan emits pending plugin
operations. The host executes and confirms those operations before taking work.
GitHub remains the shared task/Review channel even on one host.

Implemented: compact seed import, GitHub CAS task/model/
PR lease plans, bounded native Research and independent Review, persistent objections,
two-round revision entry, approved-only PR materialization, stale-base checks,
private incremental recency indexing, and deployable trusted-main event scripts.
All skill implementation remains inside the skill folder.

Not yet demonstrated: a complete live native-subagent Research/Review PR cycle.
Not configured: enabled event queue dispatch, a continuously
running Review worker, required statuses/branch protection, or automatic merge.
No webhook/service is deployed. Event dispatch defaults off. Human merging
remains explicit. Native account/session attribution is not cryptographic role
identity. Actual model/session metadata is caller-reported; missing host metadata
is not_reported. Historical signed CLI adapters remain available explicitly.

Read README → AGENTS → role startup prompt / SKILL. Consult the data contract,
commands, source tools and immutable review-policy-v2 only as needed.
Historical designs are available in Git history; do not duplicate old operating
instructions into current docs.
