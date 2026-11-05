# University Seed Curation

Agent collaboration for a traceable list of global present and historical
higher-education institutions. Research uses online Wikidata, revision-bound
Wikipedia and supporting websites. Each university has one JSON record, edited
through scripts and delivered in small GitHub PRs after independent review.

**Status:** verified online source helpers, a real private Terra Research/Review
pilot, and signed initial-import PR preparation with a base-trusted data validator.
First public data import requires explicit operator acceptance and the integration
workflow on main. Incremental v0.2 updates, production task dispatch and automatic
merge are not enabled.

- [Design and confirmed decisions](docs/design.md)
- [Research / Review contract](docs/agent-workflow.md)
- [Data and Schema contract](docs/data-contract.md)
- [Preferred candidate Schema v0.2](docs/schema-v0.2.md)
- [Complete synthetic university JSON](examples/university.complete.synthetic.json)
- [Online Wikidata / Wikipedia tools](docs/source-tools.md)
- [Batch and integration contract](docs/batch-workflows.md)
- [Implementation boundaries and rollout](docs/rollout.md)
- [Implemented offline commands](docs/commands.md)
- [Reviewed data PR export](docs/reviewed-pr-export.md)
- [Current handoff and next steps](docs/handoff.md)
- [Built-in skill](.agents/skills/university-curation/SKILL.md)

The initial source contains 39,489 university candidates, with 64,667 legacy-only
objects retained as a separate discovery queue. These are candidates, not an
accepted census. Existing and historical institutions are equally in scope.

Records use `data/universities/<sha256(QID)[:3]>/<QID>.json`; the hash is of the
canonical QID, not changing file contents. Missing business fields are omitted:
no `null`, empty strings or invented zeroes. Sources, uncertainty and attempted
coverage remain explicit.

Domain fields retain sourced candidates and a short preferred reference. A
Wikipedia-only student count with no year is usable; its statistical period is
omitted and disclosed as unknown. Conflicts and past observations remain visible.

One Research manager dispatches one-QID subagents; one Review role independently
checks changed facts. The shared private task queue defaults to never-refreshed
or six-calendar-month-old universities, with a fixed-snapshot cursor.
`update_datetime` advances only after a full Research + Review refresh;
ordinary field/batch changes update `modified_datetime` instead.

Code and schemas belong here. Raw dumps, article caches, unreviewed proposals,
private job logs, credentials and model prompts do not. Initial seed records
are staged privately until a human accepts their public candidate-list version.
