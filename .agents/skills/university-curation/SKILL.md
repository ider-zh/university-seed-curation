---
name: university-curation
description: Obtain bounded university tasks, privately research or review sourced changes, and validate script-managed per-QID JSON records.
---

# University curation

Read `AGENTS.md` and `docs/agent-workflow.md`. Determine whether this session is
Research manager, Research subagent or Review. Do not interchange those roles.
The script manages state and data. This skill is not a provider, secret store,
publication approval or proof that integrations are already configured.

Use `python scripts/curate.py --help`. The default private queue is
`.private/state/queue.sqlite3`; separate worktrees must explicitly use the same
private state path. Do not create an independent copy of the queue per subagent.

## Research manager

1. Build one snapshot from a known Git base with `snapshot --base-ref SHA`.
   Default eligibility is never refreshed or last complete refresh at least six
   calendar months old. Browse using `tasks --run ID --limit 10 --cursor TOKEN`.
2. Cursor browsing is read-only. Actual assignment requires `claim --role research
   --actor ACTOR --session SESSION --run ID`; pass just that QID to one subagent.
3. Start at most the available three shared model slots. If Review is waiting,
   reserve a slot; do not start three Research jobs in addition to Review.
4. Let the single Review role consume `ready_for_review` tasks. Keep proposals,
   source caches and full verdicts private. Make one small PR from passed schools
   only after the trusted export integration has been configured.

## Research subagent

1. Work on the claimed QID and task field groups. Check identity first.
2. Use online Wikidata and cached/revision-bound Wikipedia, supporting sites as
   needed. Preserve subject, period, units, language and source locator.
3. Produce compact change operations, not a rewritten school file. Script-owned
   revision numbers, hashes and fact IDs are not model output.
4. Use `propose QID --changes FILE --output .private/proposals/ID.json` then
   `submit --task ID --lease TOKEN --proposal FILE`.
5. Renew with `heartbeat`. An expired worker must stop; its old token is fenced
   and cannot submit. Never work around a stale baseline by deleting a record.

## Review

1. Claim as `--role review` with a fresh session and different actor.
2. Obtain the private task packet. Verify every changed claim from the source,
   independently of the Research explanation. Check all high-risk identity,
   historical continuity and university/campus/faculty attributions.
3. Submit `review --task ID --lease TOKEN --session SESSION --verdict FILE`.
   Verdict: decision (`approve`, `request_changes`, `unresolved`), source_checks
   covering every changed claim, and reviewed_groups. Never approve by Schema
   validity alone. Record unavailable evidence as unresolved.
4. Two revisions maximum, then unresolved. Keep every actual model attempt in
   the private run archive; the offline queue is not a replacement for that log.
5. Apply passed results using `apply --task ID --workspace PATH --kind KIND`.
   Full `university_refresh` updates update_datetime only when the entire core
   profile has passed. `field_update` / `batch_import` must preserve it.

## Schema and initialization

For domain Schema v0.2 inspect `docs/schema-v0.2.md` and the full synthetic example.
Keep candidates; use preferred even for single-source/undated facts, disclose
missing period and unresolved conflicts. Do not invent years or require a second
source merely to allow a usable Wikipedia value. v0.2 domain mutation is pending
schema acceptance; do not send v0.1 claims operations to v0.2 records.

`scripts/maintain_schema.py check` checks the generated contract. `propose-field`
stages a definition for a separate schema PR; it never activates a new field.
Do not hand-edit generated schema or introduce arbitrary keys in school records.

`seed-init --input FILE --manifest FILE` is a dry-run by default. Write initial
candidate records only under `.private/bootstrap` until the candidate-list
version has a human acceptance record. Initial candidates have no update_datetime.
Never create/update a school file by hand or copy null placeholders into it.

## Current implementation boundary

Offline lease/data primitives and online Wikidata/Wikipedia helpers are implemented.
Actual host subagent dispatch, other source adapters, authenticated review-session provenance, signed public receipts,
PR construction and protected auto-merge require the rollout verification.
`pr-build` fails closed until trusted public export is configured. Do not claim
production Research/Review or bypass this boundary by publishing private files.

## Online sources: portable common commands

Read `docs/source-tools.md`. No upstream dump host is required in this project.

```text
python scripts/sources.py wikidata-get QID --properties P31 P17 P131 P571 P856 --resolve P17 P131 --linked-limit 8
python scripts/sources.py wikidata-search "UNIVERSITY NAME" --language en --limit 5
python scripts/sources.py wikipedia-get --language LANGUAGE --qid QID
python scripts/sources.py wikipedia-get --language LANGUAGE --title "TITLE" --view infobox
python scripts/sources.py wikipedia-get --language LANGUAGE --qid QID --view text --section SECTION_ID --max-chars 12000
```

Inspect sitelinks before choosing a language. Summary gives section IDs and the
original infobox rows; text supports offset windows. Use exact oldid when reviewing
a cited article revision. Preserve returned page/revision IDs, observation time,
URL and locator. Original statements/references and page HTML/wikitext stay in
immutable private captures. Never commit raw cache files, put raw pages in a PR,
or treat mechanical infobox parsing as independent fact verification.

## Shared linked-item lookup and flexible Review (private pilot)

Research agents may query necessary linked Wikidata items, including quantity-unit
QIDs, using the same source script. Never guess a currency from its QID or an
ambiguous symbol. Resolve the item and retain its revision; request P498 for the
ISO 4217 code where available:

```text
python scripts/sources.py --cache ABSOLUTE_PRIVATE_CACHE wikidata-get Q4917 --properties P498 --languages en zh
```

All workspaces must use the same explicit absolute `--cache` path, or set
`UNIVERSITY_SOURCE_CACHE` to that path. The path must contain a `.private` directory.
The 30-day cache uses per-request cross-process OS locks and atomic captures: three
workers requesting one missing item share one retrieval. Unrelated requests can
proceed independently. Do not cache credentials or publish original captures.

The sealed pilot transport also supports bounded `source_requests`; the manager
executes the lookup through the same cache and returns source evidence, without
letting a source request turn into arbitrary tool execution. Unit and linked-item
lookup is on demand; do not recursively crawl the entity graph. Review retrieves
cited entity revisions independently; a shared Research cache is not additional
independent factual corroboration.

Read `docs/review-policy-v2.md` for the operator-authorized private pilot policy.
Allow grounded concept adaptation and reasonable inference, including campus
opening as valid_from and leader inauguration year as term_start. Keep original
wording and record the inference basis. Wrong subjects, values/units, fabricated
facts and unsupported legal independence remain errors. Bounded coverage gaps
are reported rather than demanding an exhaustive article transcription.
