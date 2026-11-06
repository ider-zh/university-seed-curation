# Unified deep research: scope and cost limits

For new records the manager Agent dispatches separate Research and Review
subagents, validates their outputs and publishes directly to main. Research
captures evidence; Review critically assesses it offline. Subagents never
publish. Historical proposals are archived under data/history; they cannot be
assumed approved merely because this new pipeline exists.

## Search priority

1. Capture the Wikidata item and necessary linked entities. Analyze the full
   configured multilingual Wikipedia article/sections, with pinned revisions.
2. Build a six-group field-gap inventory: identity, geography, history,
   population, finance and profile. Distinguish unavailable fields from
   disputed, historically scoped, not applicable, and simply unchecked.
3. Search only specific gaps. Prefer the institution's official website and
   original-language pages, then government/education registers, and finally
   credible archives. Search earlier names for historical institutions.
4. Preserve claims separately by subject, time, units and evidence. Reject
   unsourced estimates. No brute-force crawling.

## Hard per-QID external budget

| Resource | Maximum |
| --- | ---: |
| Search queries | 8 |
| Opened external pages | 12 |
| Distinct external domains | 5 |
| Navigation depth per search result | 2 |
| External investigation wall time | 15 minutes |
| Retry on one failed endpoint | 1 |

Stop early after two consecutive targeted searches without credible new
evidence. De-duplicate URLs, reuse 30-day private captures, and log the budget
used with each Research job. Do not automatically escalate budgets. If a hard
cap is reached, mark remaining gaps as unsearched/unresolved, not absent.

## Evidence contract and offline Review

The Research snapshot is the single network acquisition per source. It records
the source identity, exact revision or capture timestamp, quote/locator,
content digest and subject. The Review job reads the Research packet and root
entity from the same workspace after checking the Research job's hashes and
Git baseline. The distinct Review subagent compares **all** facts, contexts
and coverage against the frozen packet without reading Research model traces.
It never makes another HTTP request; a missing or corrupt packet
returns to Research as a blocking failure.

The trusted v0.2.2 schema already supports `website` sources. After Wikimedia
coverage is examined, the host submits only targeted HTTPS URLs with explicit
query/depth accounting to `research-prepare --external-leads`. The bounded
adapter retrieves each HTML/plain-text page once (up to 1 MiB), extracts
short paragraph-located excerpts, and saves the raw capture privately under
the shared 30-day cache. The Research packet gets the `website` source role,
origin URL, retrieved_at, and `snapshot_id=sha256:<digest>`, with the source
corpus carrying identical immutable locator/text rows. The offline Review
checks snapshot integrity and every citation against this same packet.

The host performs *discovery*, not the subagent itself. The adapter never
automatically follows links or broad-crawls. It refuses non-public hosts,
non-HTTPS URLs, redirects, oversized/binary documents, unaccounted queries,
and budget overruns. Unsupported PDFs and dynamic pages remain unresolved.
Do not launder external snippets into Wikimedia evidence. The public record
contains only bounded sourced facts, not raw page dumps or private captures.

## Publication

The Review subagent verifies the core-review-v3 facts and contexts and all six survey-coverage groups.
Manager Agent validates the strict `review-compile` gate and generates an immutable unified receipt
describing workflow attribution honestly. `unified-publish` emits a bounded
blob/tree/commit/ref operations plan for the connected GitHub plugin. Confirm
the actual remote `main` SHA, then execute `update_ref` with `expected_sha` and
`force:false`; conflicts require fresh validation, never blind retry.

No PRs are created for new unified data. Official dataset release remains a
separate human approval decision.

Independent factual Review now uses [core-review-v3](review-scope-v3.md). Supplementary fields remain structurally validated; new receipts disclose unreviewed IDs.
