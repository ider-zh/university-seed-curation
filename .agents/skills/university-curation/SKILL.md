---
name: university-curation
description: Research or independently review university records in the current workspace using native subagents, a connected GitHub plugin and deterministic local validation.
---

# University curation

Read AGENTS.md and docs/handoff.md. Choose Research manager, one-QID Research
subagent, or independent Review. Repository:
https://github.com/ider-zh/university-seed-curation.

Run in the current workspace, reusing its checkout. Clone into a child directory
only if absent. Preserve existing work and use trusted main code. Separate hosts
are optional. Both roles may share a checkout in independent sessions.

## Native execution (default)

GitHub operations use the host's **connected GitHub plugin**. Model work uses
the host's **built-in subagent tool**. No signing key, shell token, gh, Codex CLI
or SSH is required. Never infer plugin authentication from environment variables.
Local doctor checks repository, signed input catalog and contracts; the host
Agent separately verifies plugin/subagent capabilities. Historical catalog
signatures are checked with public keys, without generating a Research key.

All executable helpers and implementation live in scripts/ and scripts/lib/.
agent.py defaults to native mode. Run from the checkout root or pass --workspace.
Do not use register-key, the legacy research/publish loop, or --runtime cli as a
workaround for native execution. The old signed CLI runtime remains explicit
compatibility only; historical artifacts remain verifiable.

## Research manager

Read references/research-agent.md for the full startup instruction.

1. Use the GitHub plugin to read main, open PRs/comments and complete coordination
   state. next only proposes candidates, never claims them.
2. coord-plan builds an **uncommitted plan**. Execute its plugin blob/tree/commit/
   guarded ref operations, substitute returned SHAs, then confirm the ref.
   On conflict reread/replan. Preserve old public Draft heads before replacement.
3. Claim one QID per subagent. research-prepare writes a private prompt, strict
   schema and source packet. Acquire a global model slot before native dispatch,
   renew task/model leases, and cancel on loss. research-compile validates the
   returned JSON and generates a compact unreviewed proposal.
4. draft creates a bounded structured bundle and plugin publication plan.
   Use an independent main-based branch, at most five schools per PR and three
   active PR permits. Create Draft PRs with the plugin.
5. Native owner-authored Review comments feed revisions back into the same PR.
   Carry earlier question IDs, two revisions maximum, then unresolved.
6. finalize requires exact independent Review decisions and no open objections.
   Publish only its approved files and receipts, mark ready, and await human merge.
   Confirm immutable receipts on actual main before marking tasks merged.

## Independent Review

Read references/review-agent.md.

Use review-prepare to independently retrieve cited revisions and enumerate every
fact/context. Dispatch a fresh native subagent under the global Review lease,
then review-compile and decision. Post the generated structured comment through
the plugin after rechecking the head. Review cannot share the Research session.
Keep role-local caches and private jobs separate even in one workspace.

Native comments are attributed to the actual configured repository-owner login
and bound to PR, proposal digest, head, schema, policy and session. They are
**not cryptographic role signatures**. The same account can represent both roles;
independence is a workflow requirement and human merge remains explicit.

## Data and sources

Use sources.py for bounded online Wikidata, necessary linked items and
revision-bound Wikipedia. Currency QIDs may be queried and retained with their
revision. Each role uses its own private cache; raw sources never enter GitHub.
Root P625 is script-owned and is not automatically a campus/headquarters point.

Missing business fields are omitted; preserve explicit unknown/no-value,
original language, subject, periods, units, historical events and conflicts.
Preferred is a presentation choice, not proof a conflict is resolved.
Follow immutable docs/review-policy-v2.md for reasonable disclosed inference.
Wrong subjects/numbers/units and unsupported legal independence fail.

Full six-group Research + Review surveys alone advance update_datetime.
Partial/batch changes preserve it. School paths use SHA-256(QID)[:2], 256 buckets.
Schema major changes and official releases require human approval.

Read docs/commands.md for native commands, docs/data-contract.md for fields,
docs/source-tools.md for sources, and docs/reviewed-pr-export.md for merge checks.
