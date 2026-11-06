# University Seed Curation

Reliable structured data about global present and historical higher-education
institutions. One Task Agent orchestrates native Research and Review subagents,
then publishes approved records directly to `main` through the GitHub plugin.

There is one workflow and one branch. Task progress lives in private local jobs;
a compact pending-task list on main preserves unfinished migration work. Review
uses the same hash-verified evidence offline. Sources, prompts and model traces
remain private; approved records and review receipts are public.

- [Task Agent startup prompt](.agents/skills/university-curation/references/task-agent.md)
- [Operating contract](AGENTS.md), [current handoff](docs/handoff.md)
- [Workflow](docs/agent-workflow.md), [commands](docs/commands.md)
- [Data contract](docs/data-contract.md), [review policy](docs/review-policy-v2.md)
- [Source tools](docs/source-tools.md), [bounded deep research](docs/deep-research.md)
- [University overview](docs/university-overview.md)

```bash
python -m pip install -e .
python .agents/skills/university-curation/scripts/agent.py doctor
python .agents/skills/university-curation/scripts/agent.py next --limit 5
```

The signed candidate import contains 39,489 primary and 64,667 discovery QIDs.
Candidate membership does not establish a university's identity. Source-backed
observations retain original subjects, languages, periods, units and conflicts.

Each QID has a dedicated Research subagent and a separate, dedicated offline
Review subagent. Reviews for different QIDs may run in parallel. At most five
concurrent data calls total across both roles; five schools per publication
batch; two Research revisions per school. A full six-group
survey alone advances freshness. Publication is complete only after remote
canonical bytes and receipts have been verified.

Previous workflows are available in Git history. Frozen historical proposals
and branch cleanup provenance are under data/history; they are not approvals.
