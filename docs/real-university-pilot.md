# Private real-university acceptance pilot

This is a bounded, operator-authorized extraction trial. It is separate from the
production queue and cannot publish records or bypass `pr-build`. It does not
change the upstream wikidata-research local-dump boundary.

## Run

Use Python 3.11+ with project dependencies and an authenticated Codex CLI.

```text
python .agents/skills/university-curation/scripts/prepare_real_pilot.py --root .private/pilots/RUN
python .agents/skills/university-curation/scripts/run_real_pilot.py --root .private/pilots/RUN
python .agents/skills/university-curation/scripts/review_pilot_policy_v2.py --root .private/pilots/RUN
python .agents/skills/university-curation/scripts/finalize_real_pilot.py --root .private/pilots/RUN
```

Inspect `prepare_real_pilot.py --help` for the exact source preparation options.
Source preparation is online, bounded to ten diagnostic QIDs, selected languages,
core statements and at most ten necessary linked items. It retains raw captures
privately. Missing language sitelinks are disclosed, never silently replaced with
a different institution. Article sections are bounded; this is not exhaustive
article extraction. Case focus labels are questions to investigate, not answers.

Each Codex subprocess explicitly requests `gpt-6.1-terra` and medium reasoning.
A shared semaphore limits Research plus Review to three calls. A separate lock
serializes the single logical Review role. Each invocation is a fresh ephemeral
session with read-only sandbox settings and a strict output schema. These roles
are sealed: evidence is supplied by the script and unexpected model tool calls
fail the provider gate. Session IDs and model/configuration arguments are kept in
private receipts. A missing runtime model-name telemetry field must be disclosed;
it is not proof of an independently attested backend model.

Review uses its own cache to retrieve the same Wikidata entity revisions and
Wikipedia oldids, checks every fact and context, then returns one verdict per
item. Source re-fetching and fresh model sessions do not make Wikipedia and
Wikidata independent source families, or eliminate same-model correlated errors.

## Schema trial changes

The pre-existing v0.2.0 schema and synthetic example remain reproducible.
Draft v0.2.1 adds partial month/day dates, student intake distinct from enrollment,
provost and unspecified chair roles, headquarters locations, and campus opening,
teaching start, cooperation agreement and construction completion events.
These are internal trial changes pending the operator's schema acceptance.

Research emits typed facts and short source pointers. The compiler assigns IDs,
validates exact source locators and quotations, constructs full JSON and computes
preferred pointers. Conflict indexes in the private transport are explicitly
zero-based; canonical conflicts use field-local candidate IDs. No per-entity
manual fact repair is allowed. A compiler repair can re-materialize an unchanged
archived proposal; it must not be described as a new Research call.

The pilot permits initial semantic review plus at most two Research revisions.
Transport/schema failures are retained and capped separately at two format
repairs per semantic round. A source/provider infrastructure failure does not
silently trigger fresh research. An interrupted task is retained and requires
explicit inspection before recovery. Resuming a finished task returns its
outcome; it does not reset the semantic budget.

## Acceptance output

Only schools with complete positive fact/context Review are written to
`acceptance/records/<sha256-qid-prefix>/<QID>.json`. The script checks every
approved file against its reviewed proposal, exact source revision replays and
recomputed preferred fields. A full refresh time requires all six core groups
and resolved institution identity. Source absence is a field coverage state,
not a reason to invent a value.

`universities.complete.json`, `quality_report.json`, `receipt-audit.json`,
`QUALITY_REPORT.md`, `schema.json`, the manifest and an acceptance ZIP are private
operator inspection artifacts. Failure counts and unresolved cases remain
visible. An agent approval is not human dataset acceptance. No raw pages,
provider prompts/logs or credentials enter this package or Git history.

The operator-authorized flexible policy re-review retains each original outcome,
allows reasonable source-grounded inference and records direct/inferred support
for every fact and context. Quantity-unit QIDs are resolved through the shared
cache; a bounded Research supplement adds missing numerical observations without
rewriting the existing facts. The supplement can request another necessary QID
and receive cached Wikidata evidence before its next model turn. Every resulting
fact is independently reviewed before applying the record. Inference annotations
are included in `interpretations.json` and the full inspection envelope.

See `docs/github-agent-pilot.md` for the next observable real-PR milestone. The
private pilot verifies model/source processing, not a configured production PR
exporter or protected merge service.
