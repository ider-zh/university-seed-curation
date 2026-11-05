# Agent operating contract

Read `docs/design.md`, your role in `docs/agent-workflow.md`, and the built-in
`.agents/skills/university-curation/SKILL.md` before taking work.

- Scope is global present and historical higher education. A seed is not an
  accepted university identity. Distinguish institutions, systems, branches,
  campuses, colleges, faculties and buildings; retain QIDs and original facts.
- Research starts with identity/scope, then a bounded field task. Use online
  Wikidata entity/search APIs and revision-bound Wikipedia first, other websites
  for supporting evidence. Agents may work in other environments: no access to
  the upstream dump host is required. This online policy is specific to this
  downstream project; it does not change wikidata-research's local dump contract.
- Use the source skill script for bounded entity lookup/search, necessary linked
  items and page retrieval. Preserve revisions and keep the raw cache private.
  Do not turn per-university research into an unbounded remote SPARQL sweep.
- No raw dump, bulk article content, unreviewed proposal, prompt, private job
  log or credential may enter Git history, a PR or public Actions artifacts.
- Each Research subagent works on one QID. Review is a fresh independent
  session, verifies every changed claim against sources and cannot review its
  own proposal. Terra medium is the initial model; three total model calls
  across Research and Review, not three per role/workspace.
- Use scripts to create or update school JSON. Do not hand-edit canonical
  files, lease state, schema versions, review receipts or record revisions.
- Missing values are omitted. Never write JSON null, empty-string placeholders,
  made-up zeros, or empty lists to mean unknown. Preserve explicit unknown/no-value
  source semantics and field-attempt coverage separately.
- A source fact must identify its subject, period/meaning and provenance. Do
  not attribute faculty/campus values to the whole institution or use retrieval
  time as a measurement year. Keep conflicting observations; do not silently
  replace them or collapse distinct historical events.
- For the operator-authorized private trial, apply `docs/review-policy-v2.md`:
  allow grounded concept adaptation and reasonable inference. Campus opening
  may be valid_from; leader inauguration year may be term_start. Retain source
  wording and explain inferred values. Bounded optional-field omissions are
  coverage limits, not automatic rejection of supported records. Wrong subjects,
  numbers, currencies, fabricated facts and unsupported legal independence still
  fail. Agents may request necessary linked Wikidata items through the shared
  source cache, including currency QIDs; never guess a missing unit.
- Only independently approved record changes reach a data PR. Failed schools
  are removed from the batch and returned for revision. GitHub cannot partially
  merge a PR. Validate current base revisions immediately before merge.
- Human review controls major Schema changes and official dataset releases.
  Release acceptance is separate from an Agent's claim approval. Initial public
  seed import also needs a human acceptance record for that candidate version.
- Provider, coordinator and GitHub integrations must remain marked unconfigured
  until configured and verified. Offline reference commands are not a claim of
  an operational multi-agent deployment.
