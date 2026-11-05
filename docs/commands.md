# Native Agent commands

## Current unified mode (new data batches)

One main Agent dispatches a Research subagent for each QID, then reviews the
same snapshot offline. No secondary Review subagent, repeated source HTTP
requests or data PR. Up to five schools per batch; keep all source packets and
prompts private. See [deep research](deep-research.md) for search budgets and
the current external-source limitation.

```text
python .agents/skills/university-curation/scripts/agent.py --role research research-prepare --qid Q13371 --job .private/native/research/Q13371/run-1 --external-leads .private/native/Q13371-external-leads.json
python .agents/skills/university-curation/scripts/agent.py --role research research-compile --job .private/native/research/Q13371/run-1 --result .private/native/research/Q13371/result.json --session RESEARCH_SUBAGENT_SESSION --model ACTUAL_MODEL
python .agents/skills/university-curation/scripts/agent.py --role research unified-proposal --proposal .private/native/research/Q13371/run-1/compile-attempts/ACTUAL_ATTEMPT/public-proposal.json --output .private/native/Q13371-transport.json
python .agents/skills/university-curation/scripts/agent.py --role review review-prepare --proposal .private/native/Q13371-transport.json --job .private/native/review/Q13371/run-1 --research-job .private/native/research/Q13371/run-1 --shared-cache
python .agents/skills/university-curation/scripts/agent.py --role review review-compile --job .private/native/review/Q13371/run-1 --result .private/native/review/Q13371/structured-main-review.json --session MAIN_AGENT_SESSION --model ACTUAL_MODEL
python .agents/skills/university-curation/scripts/agent.py --role research unified-publish --proposal .private/native/Q13371-transport.json --review-job .private/native/review/Q13371/run-1 --review-attempt .private/native/review/Q13371/run-1/compile-attempts/ACTUAL_ATTEMPT --batch-id unified-001 --output .private/native/unified-delivery-001
```

Main Agent writes the strict Review JSON after reading the offline Review
prompt; approval is never automatic. Pass multiple aligned
`--proposal`, `--review-job` and `--review-attempt` arguments for up to five
schools. The output `operations.json` specifies plugin blob/tree/commit and
**non-forced expected-head main update**; execute only after checking actual
GitHub main head and local validation. Verify published files on actual main.

Omit `--external-leads` when there are no confirmed gaps or host search is
unavailable. To use external sources, first inspect Wikimedia, then create
a private JSON search-budget manifest such as:

```json
{"search_queries":["example university history official"],"elapsed_seconds":30,
 "pages":[{"url":"https://www.example.edu/history","publisher_role":"institution_official",
           "query_index":0,"depth":0}]}
```

The host must count actual discovery queries, pages, domains, depth and elapsed
time, including failed attempts. Only explicit URL pages are fetched; no
automatic link traversal. The schema allows `institution_official`,
`government`, `academic_publisher` and `other`. Each snapshot is hash-bound
and Review reads its private packet without network requests.

The older PR commands below remain available solely for historical batches.

Run in the current workspace checkout with Python 3.11+ and Git. GitHub writes
use the connected ChatGPT GitHub plugin; models use the host's native subagent
tool. These local commands require no private signing key, token, gh or Codex CLI.

```text
python -m pip install -e .
python .agents/skills/university-curation/scripts/agent.py --help
python .agents/skills/university-curation/scripts/agent.py --role research doctor
python .agents/skills/university-curation/scripts/agent.py --role review doctor
```

local_ready confirms local contracts/catalog, not host capabilities. The Agent
must discover and verify its GitHub plugin and subagent tool in the current
session. It must not report missing shell credentials as missing plugin access.

## Research

```text
python .agents/skills/university-curation/scripts/agent.py --role research next --limit 3 --snapshot .private/native/github-snapshot.json
python .agents/skills/university-curation/scripts/agent.py --role research research-prepare --qid Q13371 --job .private/native/research/Q13371/attempt-001
python .agents/skills/university-curation/scripts/agent.py --role research research-compile --job .private/native/research/Q13371/attempt-001 --result .private/native/research/Q13371/result.json --session ACTUAL_SESSION --model ACTUAL_MODEL --effort medium
python .agents/skills/university-curation/scripts/agent.py --role research draft --proposal .private/native/proposal.json --batch-id native-001 --output .private/native/delivery-001
```

Preparation writes private prompt/schema paths. The host supplies these to its
subagent and saves its JSON privately. Record actual session/model/effort.
Prefer Terra medium when selectable; use not_reported when host metadata is
unavailable, never invent it. Compile never launches or authenticates a model.

## Review

```text
python .agents/skills/university-curation/scripts/agent.py --role review review-prepare --proposal .private/native/proposal.json --job .private/native/review/Q13371/attempt-001
python .agents/skills/university-curation/scripts/agent.py --role review review-compile --job .private/native/review/Q13371/attempt-001 --result .private/native/review/Q13371/result.json --session NEW_REVIEW_SESSION --model ACTUAL_MODEL --effort medium
python .agents/skills/university-curation/scripts/agent.py --role review decision --proposal .private/native/proposal.json --verdict .private/native/verdict.json --pr 12 --head-sha REVIEWED_HEAD_SHA --output .private/native/decision-001
```

The host posts the generated comment through the GitHub plugin; it is not a
signature. It binds actual PR/head/proposal and independent session. Review
preparation fetches exact sources independently, without Research-private logs.
The proposal file must be downloaded from the public Draft, including its
transport metadata; do not substitute a pre-publication Research artifact.

## Coordination and publication

```text
python .agents/skills/university-curation/scripts/agent.py --role research coord-plan --snapshot .private/native/coord-snapshot.json --action claim_task --arguments .private/native/claim-arguments.json --output .private/native/claim-plan.json
python .agents/skills/university-curation/scripts/agent.py --role research finalize --head-ref PR_HEAD_SHA --pr 12 --comments .private/native/pr12-comments.json --output .private/native/final-001
```

Use the plugin to read all relevant refs/state and complete PR comments, including
author login/ID/body. coord-plan requires explicit known-present or known-absent
ref snapshots. Arguments match GitCoordinator's task/model/PR lease operations;
its output lists the exact plugin tools and expected-head guards.
tentative_result is not a committed lease. Execute and confirm the plan first.
Global limits remain three model calls, one Review, three active PR permits.

Snapshot files are maps keyed by coordination branch name. Read each existing
branch's SHA and state.json through the plugin. A ref is known absent only
after a complete GitHub ref listing confirms absence, represented as:

```json
{"coord/runtime":{"sha":null,"state":{}}}
```

For a present ref use its actual 40-character commit SHA and parsed state object.
Task shards are coord/tasks- plus SHA-256(QID)[:2]. For example acquire_model
arguments use role, owner (native manager/session ID), job, and now (UTC ISO time).
Renew/release arguments use the confirmed lease plus now. Match the chosen
GitCoordinator method's argument names; do not copy a tentative lease into work.

Publication bundles list only approved structured files and blob/tree/commit/ref
operations. Use expected_sha and reread/replan on conflicts. Finalization rejects
unapproved/stale proposals and unresolved questions; human merging stays explicit.
For an existing Draft, pass draft --expected-head ACTUAL_PR_HEAD_SHA. Finalize
also supports an existing native Final after an unrelated main update. To remove
an exhausted school, use --exclude-unresolved QID --snapshot FILE; it requires a
matching unresolved task, PR and exact proposal digest in that GitHub snapshot.
When every school is unresolved it produces no publication change.

## Validation and compatibility

```text
python .agents/skills/university-curation/scripts/maintain_schema.py check
python .agents/skills/university-curation/scripts/seeds.py verify --repo .
python -m unittest discover -s tests
```

agent.py --runtime cli selects the historical signed CLI mode explicitly. Its
key/token/Codex requirements do not apply to native mode. Historical receipts,
catalog signatures, SQLite trials and source captures are retained.
