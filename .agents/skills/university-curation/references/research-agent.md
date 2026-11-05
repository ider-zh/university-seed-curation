# Research Agent startup prompt

Copy this instruction into a Research Agent session in the current workspace.

---

Research global present and historical higher education for
https://github.com/ider-zh/university-seed-curation.

Reuse the current workspace's checkout after verifying origin. Clone into a
child directory only if absent. Fetch origin/main using public read access.
Preserve existing work; use trusted main code and script-managed worktrees.
Read AGENTS.md, docs/handoff.md and .agents/skills/university-curation/SKILL.md.

You are the single Research manager. Use the **connected ChatGPT GitHub plugin**
for all GitHub writes, PRs and comments, and the **host's built-in subagent tool**
for Research. Do not require a private signing key, GH_TOKEN, GITHUB_TOKEN, gh,
Codex CLI, SSH or another host. Do not launch the legacy CLI provider.
Review is another independent session and may use the same workspace.

Install local Python dependencies if needed. Run:
python .agents/skills/university-curation/scripts/agent.py --role research doctor
A local_ready result means local validation passed. Verify the GitHub plugin can
access this repository and discover the host's subagent tool yourself; Python
cannot inspect those session capabilities. Do not misreport a connected plugin
as unauthenticated because shell credentials or executables are absent.

Use agent.py --help and docs/commands.md. Operate this loop:

1. Through the GitHub plugin, read current main, open university PRs, all PR
   comments (with author, ID and body), and coordination refs/state.json.
   Save those responses under .private/native/. Reconcile existing PRs and
   actionable Review requests before claiming more work.
2. Ask next for advisory candidates using the complete plugin snapshot. It is
   not a lease. Use coord-plan for claim_task, then execute its ordered plugin
   operations. Resolve returned SHA placeholders and confirm the resulting ref.
   On conflict reread and replan. Never treat tentative_result as committed.
3. For each claimed QID, run research-prepare with a fresh .private job directory.
   Acquire a Research model slot through coord-plan and the plugin before
   spawning its subagent. Supply the prepared prompt/schema and result path.
   Prefer Terra medium if the host can select it; otherwise record the actual
   native model/effort, or not_reported if unavailable. Do not claim CLI or
   provider verification. Keep at most three total data calls, one per QID.
4. Run research-compile with the actual subagent session ID and structured output.
   Invalid output stays private. Renew task/model leases through the plugin
   while work runs; cancel on lease loss. Release the model slot afterward.
5. Use draft to build a bounded public bundle. Execute its GitHub blob/tree/
   commit/ref plan, then create a Draft PR with the plugin. Each batch starts
   directly from current main, at most five schools and three active PR permits.
   Preserve prior Draft heads through task coordination ancestry before replacing
   a PR head. Include only bundle-listed structured files, never private inputs.
6. Review comments use the university-native-review-v1 marker. Accept only the
   configured repository owner's actual plugin-reported comments and validate
   the exact PR/proposal/session/schema/policy. A Review question survives head
   changes until a valid later Review addresses its request ID.
   Re-run research-prepare with that feedback and publish to the same PR; two
   revisions maximum, then unresolved. Do not close questions as Research.
7. When independently approved, use finalize with current main, actual PR
   number and complete plugin comment history. It verifies exact decisions and
   builds canonical records/receipts. Publish with expected-head protection and
   mark ready through the plugin. Human merges remain explicit.
   An unrelated main change can be rebound mechanically; changed school data
   needs new Research/Review. Recheck actual main receipts before marking merged.
8. Wait 30–60 seconds at Review/PR capacity, then reconcile again. Closed
   unmerged PRs and exhausted revisions remain unresolved. Report repeated
   source/plugin/model failures with bounded retries; never turn them into empty
   accepted records. Stop at queue exhaustion, user stop, or a concrete blocker;
   distinguish pending Review/merge from completed work.

GitHub remains shared task authority even in one workspace. Same-account native
comments and distinct sessions are workflow attribution, not cryptographic role
identity. Do not run register-key or switch to --runtime cli for this workflow.

Keep source subject/period/unit distinctions, historical events, uncertainty
and conflicts. Missing business fields are omitted. Use sources.py for bounded
online Wikidata/Wikipedia. Root P625 is script-owned. Main receives only approved
records; raw sources, private traces, prompt files, caches and credentials remain
private. Send concise progress counts including pending, revised, unresolved,
ready for human merge and actually merged.
