---
name: university-curation
description: Research or independently review university records through GitHub-coordinated tasks, public Draft proposals, signed comments and script-validated JSON.
---

# University curation

Read AGENTS.md and docs/handoff.md. Choose exactly one role: Research manager,
one-QID Research subagent, or independent Review. Repository:
https://github.com/ider-zh/university-seed-curation.

All helpers and implementation live in this skill's scripts/ and scripts/lib/.
Schemas, tests and data are repository resources. Run commands from the checkout
root, or pass --workspace to agent.py. The script returns JSON.

## Bootstrap

Use the matching startup prompt in references/research-agent.md or
references/review-agent.md. Install trusted checkout dependencies. Each role
registers its own local private key using agent.py --role ROLE register-key;
only its public descriptor goes into a human-merged code PR. Never share keys.
Run doctor after code, seed bootstrap and key registration reach main.
Do not pretend an unconfigured worker/event service is operating.

## Research manager

1. Run agent.py --role research sync; handle existing signed PR requests first.
2. Run next --limit 3. Never-refreshed or six-month-old main records are eligible;
   primary seeds precede discovery. Only the manager claims tasks.
3. Assign each returned QID to one subagent running research --qid QID.
   Do not pass private keys/caches/logs to another host or role.
4. Run publish --batch-size 3 for prepared proposals. This creates an isolated
   public Draft PR based on main. At most five schools/PR, three active PR permits.
5. Loop sync. For a signed objection or changed school baseline, research
   --qid QID --pr N, then publish --pr N. Use the same PR; two revisions maximum.
6. sync materializes approved records and makes the PR ready. Human merge remains
   required. Submission/waiting is not completion; confirm merged receipts.
   Unresolved schools stay explicit and failed public heads remain archived.

Use references/research-agent.md for a complete autonomous-loop instruction.
Do not create a second shared-local database queue.

## Research subagent

Use the single assigned QID and research command. Scripts gather bounded online
Wikidata, necessary linked items and revision-bound Wikipedia, then call Terra
medium with strict Schema. Emit compact new observations, not a rewritten record.
Existing facts, candidate IDs and source lineage are script-managed. Root P625
is owned by code; do not reinterpret its point as campus/headquarters/city.
Retain missing periods, units, historical events, source language and conflicts.
Reasonable inference is allowed under docs/review-policy-v2.md.
Wrong subjects/numbers/units and unsupported legal independence still fail.

## Independent Review

1. In the separate Review environment, enqueue current Drafts using
   event_review.py --repository ider-zh/university-seed-curation --mode queue --scan.
2. Run agent.py --role review next-review. It leases an exact PR head.
   It independently fetches pinned revisions; no Research-private files are used.
3. Verify every changed fact/context, earlier question and high-risk identity.
   Post a signed decision. review --pr N is the manual single-PR entry.
4. review-request can post a partial signed objection after prior approval.
   Only a valid Review decision addressing its request ID can clear it.
5. Loop with bounded waits. Never merge or act as the Research role.
   references/review-agent.md gives the full startup instruction.

GitHub CAS refs enforce three total model calls and at most one Review, across
hosts. Lease loss cancels/fences work. A local OS lock is not a global budget.

## Public and private boundaries

Structured unreviewed candidates are allowed only in Draft PRs, clearly marked.
Main contains approved canonical records and receipts. Short source evidence
excerpts are allowed; full article text/HTML/wikitext, dumps, prompt/model traces,
logs, caches and keys remain private. Role-local caches may be shared among that
host's subagents, never required for cross-role communication.

Only script-owned fields and registered Schema are allowed. Missing business
values are omitted, not null/blank. Keep explicit source unknown/no-value.
Sources use short record-local references; immutable revision and statement
locators remain. Preferred is a presentation choice, not conflict resolution.
Campus opening may count as valid_from; inauguration may inform term_start if
the inference is disclosed. Do not invent dates/units/independence.

School paths use SHA-256(QID)[:2] (256 buckets). Complete six-group accepted
surveys advance update_datetime; partial/batch changes preserve it. A complete
survey may retain missing/disputed observations. Unknown identity or failed
source retrieval prevents complete freshness.

## Sources and maintenance

Read docs/source-tools.md for sources.py wikidata-get/search and wikipedia-get.
Necessary linked items, including currency P498, may be queried with bounded
limits and retained revisions. Each host uses its own 30-day private cache.
Review fetches cited revisions independently.

Read docs/commands.md for executable commands, docs/data-contract.md for fields,
docs/reviewed-pr-export.md for trusted validation. Schema major changes and
official releases need human approval. No automatic merge or deployment is
implied. Historical SQLite commands and initial-import/coordinate adapters
remain compatible but do not schedule distributed agents.
