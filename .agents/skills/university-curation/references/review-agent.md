# Review subagent contract

Review one exact proposal assigned by the Main Agent in a session distinct from
Research. Read only the prepared Review prompt, strict schema and frozen
hash-verified evidence packet. Do not fetch sources, browse, inspect Research
model traces, publish, or edit task/canonical state.

Check every fact, context, source locator, subject attribution, historical scope,
statistical period/unit, source conflict, root P625 interpretation, all six
coverage groups and the institutional overview. Address every prior request ID.
Apply immutable docs/review-policy-v2.md as included in the prepared prompt.

Return strict JSON with approve, request_changes or unresolved. Give specific
reasons for unsupported claims and required revisions. Missing optional fields
alone do not require rejection; fabricated values, wrong subjects/units and
unsupported identity conflation do. Approval requires complete supported checks
and addressed prior requests.

The manager compiles your actual result and publishes only approved exact bytes.
Session separation is workflow independence, not cryptographic identity. Do not
start a separate Review service or use PRs, role keys or coordination branches.
