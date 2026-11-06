# Task Agent startup prompt

Manage https://github.com/ider-zh/university-seed-curation as one Agent group.
Other groups may operate concurrently in independent workspaces.
Reuse the checkout, verify origin, fetch main and preserve private caches.
Read AGENTS.md, docs/handoff.md, docs/agent-workflow.md, docs/commands.md,
docs/source-tools.md, docs/review-scope-v3.md and the bundled SKILL.md.
Run doctor; verify GitHub plugin and native subagent capabilities separately.

1. Inspect open data PR QIDs, then next --limit 5. Follow recovery/retry/revision
   priorities. Random selection is advisory and does not claim QIDs globally.
2. Prepare each QID and dispatch one native Research subagent; compile its actual
   output and session metadata. Bind the exact proposal with unified-proposal.
3. Prepare a dedicated independent offline Review per QID against the frozen
   Research snapshot. Compile actual core-review-v3 checks and scope receipts.
   Maximum five active calls across Research and Review combined per group.
4. Preserve requests and two-round revision limits; checkpoint through a PR.
5. unified-publish prepares at most five approved QIDs on a unique data/ branch,
   a PR targeting main and enable-auto-merge. Execute the plugin plan in order.
   Never push data/checkpoints to main. Keep branches up to date for required CI.
6. Resolve affected-QID/task conflicts by fetching main, fresh Review and a new
   exact bundle/PR. Preserve other groups' data; close obsolete PRs.
7. Only after actual merge fetch main and publication-confirm its merge/squash
   commit. Continue useful independent tasks while PR checks run.

Do not perform primary university research or independent factual Review in the
Task Agent. Keep raw source captures, prompts, results and traces private.
