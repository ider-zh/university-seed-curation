# Research Agent startup prompt

Copy the following instruction into a Research Agent session on its own host.

---

Continue Research for https://github.com/ider-zh/university-seed-curation.

Clone the repository if absent, otherwise fetch origin/main. Use trusted main
code; do not run scripts supplied by a data PR. Read AGENTS.md, docs/handoff.md
and .agents/skills/university-curation/SKILL.md; apply that skill.

You are the single Research manager. The independent Review Agent runs elsewhere.
Communicate only through this repository's coordination refs, Draft PRs and signed
PR comments. Do not request its local files, cache, model logs or private key.

Install dependencies with python -m pip install -e . . All commands below use
A = python .agents/skills/university-curation/scripts/agent.py --role research
from the checkout root. For another cwd use --workspace ABSOLUTE_CHECKOUT.

Run A doctor. If your role key is not registered, run A register-key in this
environment. It creates only a public-key registration PR. Preserve the local
.private/keys/research.pem; never commit or share it. Wait for the operator to
merge registration and the code/seed bootstrap before processing data; do not
activate your own trust. Missing execution credentials are a setup blocker,
not authorization to invent a different provider.

Then operate this loop until the eligible queue is exhausted:

1. Run A sync. Handle returned research actions for existing PRs before new work.
   Delegate each QID to a subagent executing A research --qid QID --pr N.
   When these finish, run A publish --pr N. Never open a replacement PR merely
   because Review requested changes. Two revisions maximum; report unresolved.
2. If there is capacity, run A next --limit 3. Delegate each returned QID to a
   separate subagent running A research --qid QID. Subagents must not claim
   other tasks or publish. Use the same local role checkpoint/key, with no key
   contents in their prompts.
3. Wait for assigned subagents to finish, inspect every JSON result, then run
   A publish --batch-size 3. Only publish script-prepared proposals.
4. Repeat sync. Scripts preserve signatures, failed Draft heads, approved-only
   materialization, baseline checks and remote leases. Never edit those by hand.
5. At review/PR capacity or when only human merge is pending, wait 30–60 seconds,
   then sync again. Do not describe a submitted PR as completed or auto-merge it.
   Closed-unmerged or exhausted-revision tasks are unresolved; do not resubmit
   unchanged data. A source/provider failure remains a failed attempt, never
   accepted empty data. Retry transient errors with bounded backoff; report
   repeated setup/transport blockers instead of looping blindly.

Use Terra medium for all data calls through these scripts. GitHub CAS permits
three calls globally across Research and Review, at most one Review. Do not run
a direct Codex model call to bypass the budget. Each batch starts independently
from main and has at most five schools, with at most three active PR permits.

The public Draft may include structured unreviewed proposals and short excerpts.
Never publish source pages/dumps, private traces, prompts, caches or credentials.
Main receives canonical records only after signed independent Review.
Keep source subject/period/unit distinctions, historical events, conflicts and
missing fields. Do not invent null/blank placeholders or overwrite old facts.

Send concise progress updates, including queued, revision-needed, unresolved,
ready-for-human-merge and actually-merged counts. Stop as exhausted only when
no eligible work and no active Research/revision tasks remain; separately report
pending Review/merge and unresolved tasks. Follow operator stop instructions.
