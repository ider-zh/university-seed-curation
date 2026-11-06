# Core independent factual Review v3

Operator-approved 2026-11-06. `core-review-v3` supersedes exhaustive factual
coverage. Immutable review-policy-v2.md remains guidance for facts in scope.
Schema v0.2.2 and historical records/receipts are unchanged.

| Mandatory factual checks | Supplementary, no independent factual checks |
| --- | --- |
| Identity names, kind, operating status, ownership and identifiers; eligibility | Leadership, officeholders and all tenure dates |
| Institution relationships and related-entity identity contexts | Profile summary, motto/slogan, website, images, language and academic focus |
| Population counts and finance observations, including subjects, periods, units and currencies | Campus counts, street addresses and location names/validity dates |
| Coordinates and their location contexts; normalized country attribution in addresses | Rename, relocation, campus-opening, teaching-start, cooperation and construction events |
| Establishment/predecessor/vocational origins, higher-education/university status, charter, merger/split, closure/reopening and jurisdiction dates and event contexts | Descriptions and other supplementary fields |

`review_scope.py` selects paths deterministically. Country-only contexts retain
source evidence without requiring street-address review. All fields still pass
schema, subject structure, source-reference/locator and excerpt validation.
Research must continue sourcing supplementary facts. Six coverage checks attest
to survey completion, not exhaustive factual verification; a full refresh must
still satisfy six-group coverage and retrieval-success requirements.

Prepared packets and new public verdicts carry the version, reviewed IDs and
not_independently_reviewed_ids. An address may be unreviewed while its country
has a separate reviewed context. No unreviewed value is represented as having
received an independent factual check by the receipt.

Historical objections explicitly under leadership/profile are waived only for
non-subject/non-schema categories, preserved verbatim in waived_requests with
an explicit policy reason. Ambiguous legacy fields and identity/subject/schema
errors remain blocking. Other objections require responses. New objections
about supplementary content must not demand exhaustive factual review.

Existing published receipts are not rewritten. Unpublished approvals require a
fresh prepared/compiled Review under v3 before a new publication. Compilation
and publication both check exact scope coverage; missing core IDs or altered
scope receipts cannot pass. The manager still retains original request IDs.
