# University Seed Curation

Script-managed records for global present and historical higher education:
online Wikidata/Wikipedia research, independent review, and small GitHub PRs.

Research and Review run in the current workspace using independent native
subagent sessions and the connected ChatGPT GitHub plugin. No signing keys,
shell tokens, gh or Codex CLI are needed. They share GitHub task refs, Draft PRs
and structured owner-attributed comments. Drafts contain candidates; main contains
approved records and receipts. Raw sources and model traces stay private.

Start here:

- [Current state](docs/handoff.md)
- [Research startup prompt](.agents/skills/university-curation/references/research-agent.md)
- [Review startup prompt](.agents/skills/university-curation/references/review-agent.md)
- [Built-in skill](.agents/skills/university-curation/SKILL.md)
- [Workflow](docs/agent-workflow.md) and [commands](docs/commands.md)
- [Data contract](docs/data-contract.md), [source tools](docs/source-tools.md)
- [Review policy](docs/review-policy-v2.md), [PR validation](docs/reviewed-pr-export.md)

The candidate import contains **39,489 primary** and **64,667 discovery** QIDs,
kept in compact `data/seeds/` lists. Research creates full school records lazily,
one file at `data/universities/<sha256(QID)[:2]>/<QID>.json` (256 buckets).
Importing seeds does not approve their university identities.

One Research manager dispatches one-QID subagents. GitHub leases enforce three
total model calls and one Review call; every batch starts from main in an isolated
worktree. A full refresh is due after six calendar months. Missing fields are
omitted; sourced observations, conflicts and preferred references remain explicit.

All executable skill code lives under `.agents/skills/university-curation/scripts/`.
Offline checks: `python -m unittest discover -s tests`.
Current docs describe one current workflow; previous designs remain in Git history.
Read handoff for bootstrap status and execution prerequisites.
