# University Seed Curation

Agent collaboration for a traceable list of global present and historical
higher-education institutions. Research uses online Wikidata, revision-bound
Wikipedia and supporting websites. Each university has one JSON record, edited
through scripts and delivered in small GitHub PRs after independent review.

**Status:** three reviewed university records are versioned in GitHub. Online
source helpers, the private Terra Research/Review trial, signed initial export,
and base-trusted data checks are verified. This branch adds 256-bucket storage
and a bounded root-P625 update; arbitrary domain updates and automatic merge
remain unavailable.

Read only what the task requires:

- [Current state and handoff](docs/handoff.md)
- [Research / Review workflow](docs/agent-workflow.md)
- [Data, Schema and preferred contract](docs/data-contract.md)
- [Commands](docs/commands.md) and [online sources](docs/source-tools.md)
- [Review policy](docs/review-policy-v2.md) and [reviewed PR export](docs/reviewed-pr-export.md)
- [Built-in skill](.agents/skills/university-curation/SKILL.md)
- [Complete synthetic JSON](examples/university.complete.synthetic.json)

Current docs describe current behavior. Previous designs and trial reports are
available through Git history; immutable schemas and signed evidence remain in
the repository. The documentation consolidation starts from commit `8535ab0`.

The initial source contains 39,489 university candidates, with 64,667 legacy-only
objects retained as a separate discovery queue. These are candidates, not an
accepted census. Existing and historical institutions are equally in scope.

Records use `data/universities/<sha256(QID)[:2]>/<QID>.json`; the hash is of the
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

All skill commands and implementation modules live under
`.agents/skills/university-curation/scripts/` (`lib/` contains internal modules).
There is no second implementation under root `src/`. Schemas, data, docs and
offline tests are shared repository resources.
