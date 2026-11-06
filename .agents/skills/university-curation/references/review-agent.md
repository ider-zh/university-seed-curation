# Review subagent contract

Review one exact QID proposal assigned by the Task Agent in a dedicated session
distinct from all Research sessions and every other QID's Review session.
Other QIDs have their own independent Review subagents and may run in parallel.
Return one strict result for your QID. Read only the prepared Review prompt, strict schema and frozen
hash-verified evidence packet. Do not fetch sources, browse, inspect Research
model traces, publish, or edit task/canonical state.

Check every ID in the prepared facts and contexts arrays, including subject,
period, unit and evidence. Follow docs/review-scope-v3.md. Other fields are
supplementary and do not receive independent factual checks. Six group checks
assess completion of the Research survey only. Respond to prior requests except
those explicitly listed in waived_request_ids; do not reopen secondary facts.
Apply immutable docs/review-policy-v2.md as included in the prepared prompt.

Return strict JSON with approve, request_changes or unresolved. Give specific
reasons for unsupported claims and required revisions. Missing optional fields
alone do not require rejection; fabricated values, wrong subjects/units and
unsupported identity conflation do. Approval requires complete supported checks
and addressed prior requests.

The manager compiles your actual result and publishes only approved exact bytes.
Session separation is workflow independence, not cryptographic identity. Do not
start a separate Review service or use PRs, role keys or coordination branches.
