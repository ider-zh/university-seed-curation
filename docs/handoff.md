# Current state and handoff

Operator decisions on 2026-11-06 enable multiple independent Agent groups and
replace direct-main publication with PRs targeting main plus auto-merge.
See AGENTS.md and docs/agent-workflow.md for the current contract.

Research/Review remains a separate session pair per QID, with five concurrent
calls per group. Core-review-v3 limits independent factual checks; schema stays
v0.2.2 and historical data/receipts and immutable v2 policy are preserved.
Wikimedia socket timeout is 90 seconds and maxlag=30 consistently. Timeouts and
maxlag/429/503 use bounded retries and private manager retry_wait state.

unified-publish/checkpoint generate unique data branches and PR/auto-merge plans.
Required main checks include reference-tests for Python 3.11/3.13 and trusted-base
data-publication validation with branches up to date. Overlapping QIDs/tasks or
Git conflicts require refreshed bundles; no distributed task claims are promised.
Confirm only actual merged bytes on fetched main. Private snapshots lost across
workspaces must be rebuilt. Source raw data and model traces stay private.

Local doctor verifies contracts, not plugin permissions, live subagent execution
or actual remote publication. Formal external dataset releases remain separate
operator decisions. Old signed receipts/branch-cleanup manifests remain audit
artifacts, not an execution workflow.
