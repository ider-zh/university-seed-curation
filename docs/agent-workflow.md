# Distributed Research and Review

The repository is https://github.com/ider-zh/university-seed-curation.
One Research manager and its one-QID subagents run independently of one Review
role. They may authenticate as the same GitHub user. Each holds its own signing
key and local cache. No shared disk, SQLite database or local model lock is used
as cross-role authority.

## Bootstrap

Merge implementation code, then the signed seed import / byte-preserving bucket
bootstrap. Each role runs `agent.py --role ROLE register-key` from its own host.
Only the public key descriptor enters a code-only registration PR. Human merge
activates it. Role keys cannot sign legacy human seed acceptance or initial
imports. Run doctor after registration merges. Do not exchange private keys.

## Research loop

The manager calls sync before claiming more work. It handles signed revision
requests first, then claims up to three QIDs with next. Primary candidates precede
the separate discovery queue; current approved update_datetime governs the
six-calendar-month refresh threshold. A local derived index speeds selection,
but main and GitHub task refs remain authoritative.

Dispatch each assigned QID to one subagent running the research command.
The script acquires a global model lease and builds a bounded source packet,
then emits a strict compact delta. It automatically preserves root Wikidata P625,
without reinterpreting it as a campus, headquarters or city point.

Publish a small batch as a public Draft PR. Each batch gets a fresh branch and
worktree based directly on main. No PR depends on another data PR. Maximum five
schools per batch and three active PR permits prevent unlimited review backlog.
Waiting at capacity is not task completion.

## Independent Review and revisions

Review can poll with event_review.py --mode queue --scan and agent.py next-review.
A deployable Actions dispatcher can enqueue validated Draft heads on PR events;
it defaults off until an execution environment is selected. The Review worker,
not Actions, owns the model credentials and Review signing key.

Review independently retrieves pinned source revisions, validates every changed
fact/context, then posts a structured signed decision. A partial objection can
also be posted with review-request. Signatures bind repository, PR, QID, proposal,
reviewed head, policy, schema and session; same-account comments are not formal
second-account approvals.

Research sync reads these comments. Failed schools are revised on the same PR
using research --pr N, then publish --pr N. Questions survive branch/head changes.
Only the exact valid independent approval carrying addressed request IDs resolves
them. Two revisions maximum; further failures become unresolved. Research never
closes a Review objection itself. Historical failed heads stay reachable through
coordination refs before force-with-lease replacement.

When every remaining school is approved or explicitly unresolved, sync builds
main + approved canonical records + dual-sign receipts. It removes unresolved
schools from the mergeable batch while retaining their public Draft history.
The PR becomes ready for **human merge**. A fully unresolved Draft remains visible.

## Base changes, completion and recovery

If main changes only for another school, sync rebinds the final batch mechanically
without another model call. A changed same-QID baseline requires fresh Research
and Review; schema/policy/catalog incompatibility never overwrites current data.
Signed-data and live university-review checks must pass again.

Submission is not completion. Sync confirms immutable receipts actually reached
main before marking tasks merged and releasing PR permits. A closed unmerged PR
becomes unresolved; it is not blindly resubmitted. A partial survey has a seven-day
queue backoff and preserves update_datetime. A complete six-group survey may
retain disclosed missing/conflicting values; unknown identity or source retrieval
failures prevent complete freshness.

Coordination refs: coord/tasks-00..ff for tasks, coord/runtime for global model
slots, Review head queue and PR permits. Updates use compare-and-swap Git pushes.
Leases expire and are fenced; failed workers stop. Coordination metadata and
short diagnostic codes are public; never put sources, credentials or logs there.

Human setup must make signed-data-validation and university-review required
before treating CI as an enforced merge barrier. This implementation does not
configure protections or auto-merge. Review comments/statuses are asynchronous;
a human must not bypass a pending or newly failed check.
