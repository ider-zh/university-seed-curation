# Current publication contract

All publication and checkpoint commands now emit **PR bundles**: unique data/
branch, PR targeting main, then enable-auto-merge. Execute generated plugin
operations sequentially. No command emits a main ref update. Wait for merge,
fetch main and confirm its merge/squash SHA. See agent-workflow.md for concurrent
baseline handling and review-scope-v3.md for factual Review coverage.

# Manager commands

Run from the existing checkout, or pass --workspace. Use Python 3.11+ and Git.
The host must verify its connected GitHub plugin and native subagent tools.

```bash
python -m pip install -e .
python .agents/skills/university-curation/scripts/agent.py doctor
python .agents/skills/university-curation/scripts/agent.py next --limit 5
```

doctor checks the local origin, signed candidate import, schema and policy. It
does not authenticate the host plugin. next returns tasks with action and reason;
there is no coordination snapshot input or branch lease step.

Research candidates are randomized within each existing priority tier: saved tasks
before new tasks, and primary before discovery. Recovery/publication/Review/revision
actions retain their priority. Each call returns a fresh `selection_seed`; use
`next --limit 5 --seed 123` to replay selection with the same main/local state.
The limit is the number returned (up to the eligible count), not a random batch
size. Selection is without replacement within a call. Randomization reduces
repeated picks across workspaces but is not a distributed claim or a guarantee
of disjoint batches; one manager per workspace remains the supported model.
Local prepare locking and expected-SHA publication protection remain required.


## Research

```bash
python .agents/skills/university-curation/scripts/agent.py research-prepare --qid Q4032 --job .private/native/research/Q4032/run-1
python .agents/skills/university-curation/scripts/agent.py research-compile --job .private/native/research/Q4032/run-1 --result .private/native/research/Q4032/result.json --session ACTUAL_RESEARCH_SESSION --model ACTUAL_MODEL
python .agents/skills/university-curation/scripts/agent.py unified-proposal --proposal .private/native/research/Q4032/run-1/compile-attempts/ACTUAL_ATTEMPT/public-proposal.json --output .private/native/Q4032-proposal.json
```

Give the returned prompt/schema paths to a one-QID native Research subagent.
Use the actual compile-attempt path, session, model and effort, or not_reported
for unavailable metadata. The Task Agent does not author Research JSON itself. Each QID uses a distinct
Research subagent session and a distinct dedicated Review subagent session.
Send prepared per-QID packets to separate Review subagents in parallel and compile
each result with its actual Review session ID. Publication rejects shared Review
sessions, reused Research sessions and any cross-role session reuse.
Keep at most five active calls across both roles, one active subagent per QID;
prioritize waiting Reviews before new Research.

For external gap research, first inspect Wikimedia evidence, then pass
--external-leads with a private budget manifest:

```json
{"search_queries":["example university history official"],"elapsed_seconds":30,"pages":[{"url":"https://www.example.edu/history","publisher_role":"institution_official","query_index":0,"depth":0}]}
```

Count actual attempts, including failures, against the 8-query/12-page/5-domain/
2-hop/15-minute limits. Uncaptured snippets do not support public facts.

## Review and revisions

```bash
python .agents/skills/university-curation/scripts/agent.py review-prepare --proposal .private/native/Q4032-proposal.json --research-job .private/native/research/Q4032/run-1 --job .private/native/review/Q4032/run-1
python .agents/skills/university-curation/scripts/agent.py review-compile --job .private/native/review/Q4032/run-1 --result .private/native/review/Q4032/result.json --session DISTINCT_REVIEW_SESSION --model ACTUAL_MODEL
python .agents/skills/university-curation/scripts/agent.py job-heartbeat --qid Q4032
```

Review receives only its prepared packet/prompt/schema and never fetches sources.
A Research job is mandatory; there is no source replay mode.
The manager records the actual result through review-compile. On request_changes,
next returns revise; research-prepare automatically includes saved open requests.
Use a new Research directory for each revision. Optional --feedback must retain
all saved requests unchanged. Two revisions maximum; exhausted tasks become unresolved.
After request_changes or unresolved, persist the compact questions/revision checkpoint
before the next attempt or leaving the workspace:

```bash
python .agents/skills/university-curation/scripts/agent.py checkpoint --output .private/native/checkpoint-001
```

Execute that bundle through the GitHub plugin, fetch main and use publication-confirm
with the same bundle and actual commit. It contains only task metadata, not
proposals, source snapshots, model results or private job paths.

## Publish and confirm

```bash
python .agents/skills/university-curation/scripts/agent.py unified-publish --proposal .private/native/Q4032-proposal.json --review-job .private/native/review/Q4032/run-1 --review-attempt .private/native/review/Q4032/run-1/compile-attempts/ACTUAL_ATTEMPT --batch-id unified-001 --output .private/native/delivery-001
```

Pass aligned repeated --proposal/--review-job/--review-attempt arguments for up
to five schools. Create the PR against main, then execute the exact operations.json
through the GitHub plugin. On a SHA conflict fetch main and repeat offline Review.
Never force. If an affected QID/task changes or conflict prevents merging, rebind the
current manager proposal into a new private path (do not use a Review copy):

```bash
python .agents/skills/university-curation/scripts/agent.py unified-proposal --rebind --proposal .private/native/Q4032-proposal.json --output .private/native/Q4032-rebound.json
```

This preserves compiled Research and questions, removes the old active approval
and bundle pointers, and returns to review_pending. Run review-prepare with the
new proposal and retained Research job, dispatch a fresh dedicated Review session,
then compile and build a new publication bundle. Other QIDs are unchanged. If the
school baseline, catalog, schema or policy changed, rebuild Research instead.
If the batch already exists on main, confirm its original publication first.
After successful publication, fetch public main and confirm:

```bash
git fetch origin main
python .agents/skills/university-curation/scripts/agent.py publication-confirm --bundle .private/native/delivery-001 --published-ref ACTUAL_REMOTE_COMMIT_SHA
```

The confirmation checks ancestry, exact planned parent and every canonical,
receipt, manifest and backlog hash. Run the same confirmation to recover an
interruption after publication. Keep the private bundle until confirmation.

## Checks

```bash
python .agents/skills/university-curation/scripts/maintain_schema.py check
python .agents/skills/university-curation/scripts/seeds.py verify --repo .
python -m unittest discover -s tests -v
```

agent.py has one native execution mode. draft, finalize, decision, coord-plan,
register-key, --role and --runtime cli have been removed. All commands belong
to the single Task Agent. Research and Review subagents receive prepared tasks.
