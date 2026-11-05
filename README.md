# University Seed Curation

Agent collaboration for a traceable list of global present and historical
higher-education institutions. Research uses local Wikidata, revision-bound
Wikipedia and supporting websites. Each university has one JSON record, edited
through scripts and delivered in small GitHub PRs after independent review.

**Status:** initialization design and offline reference implementation. The
GitHub repository started empty. No university research, external collection,
public seed import, production coordinator or automatic merge is enabled yet.

- [Design and confirmed decisions](docs/design.md)
- [Research / Review contract](docs/agent-workflow.md)
- [Data and Schema contract](docs/data-contract.md)
- [Batch and integration contract](docs/batch-workflows.md)
- [Implementation boundaries and rollout](docs/rollout.md)
- [Implemented offline commands](docs/commands.md)
- [Built-in skill](.agents/skills/university-curation/SKILL.md)

The initial source contains 39,489 university candidates, with 64,667 legacy-only
objects retained as a separate discovery queue. These are candidates, not an
accepted census. Existing and historical institutions are equally in scope.

Records use `data/universities/<sha256(QID)[:3]>/<QID>.json`; the hash is of the
canonical QID, not changing file contents. Missing business fields are omitted:
no `null`, empty strings or invented zeroes. Sources, uncertainty and attempted
coverage remain explicit.

One Research manager dispatches one-QID subagents; one Review role independently
checks changed facts. The shared private task queue defaults to never-refreshed
or six-calendar-month-old universities, with a fixed-snapshot cursor.
`update_datetime` advances only after a full Research + Review refresh;
ordinary field/batch changes update `modified_datetime` instead.

Code and schemas belong here. Raw dumps, article caches, unreviewed proposals,
private job logs, credentials and model prompts do not. Initial seed records
are staged privately until a human accepts their public candidate-list version.
