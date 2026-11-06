# University homepage overview specification

The current trusted schema 0.2.2 already supports `profile.summary`: a
language-marked text candidate with source evidence. No schema change is
necessary for the overview format.

## Content

- Language: English, with original-language official names when relevant.
- Preferred length: 180–260 words, generally 2–3 paragraphs.
- Sparse-evidence fallback: 90–179 words with an explicit private coverage
  note. Omit the field entirely when fewer than 90 grounded words are possible.
- Paragraph 1: recognized school identity, institution type, geographic home,
  current/historical status.
- Paragraph 2: factual founding/charter/rename/merger chronology, carefully
  distinguishing predecessor institutions and historical territories.
- Paragraph 3: evidenced teaching/research fields, institutional structure,
  programmes and time-qualified scale only if known.

The text must be original synthesized prose, neutral, third-person and readable
without viewing a table. No invented strengths, promotional superlatives,
unverified accreditation, unsourced rankings, irrelevant trivia or invented
precise founding dates. Do not copy large paragraphs from source websites.

Every material proposition must map to the summary candidate's cited
`source_ref`/`locator` with short verbatim evidence excerpts, using multiple
citations as appropriate. Pinned Wikimedia and the new hash-bound `website`
capture adapter can both supply evidence. Research remains responsible for these requirements. Under core-review-v3 the
summary is supplementary and does not receive independent sentence-level Review.

## Example transport shape (illustrative, not a factual record)

```json
{
  "field": "profile.summary",
  "context": "institution",
  "value_state": "known",
  "value_json": "{\"text\":\"A sourced, multi-paragraph English overview ...\",\"language\":\"en\"}",
  "period_json": "",
  "current_basis": "not_applicable",
  "evidence": [{"source_ref":"s1","locator":"exact:source:locator","original_text":"short exact supporting quote"}]
}
```

The university detail page consumes `profile.summary.preferred`; numerical
rankings, tuition, student counts and live administrative roles remain separate
dynamic data and should not be embedded without a clear reference period.
