# Handoff — reviewed PR integration

PR #1 was merged by the operator (main ef49fdf). The 10-school private trial
remains under `.private/pilots/university-20261105-terra-v02`: 515 facts, 136
contexts and 36 interpretation notes, all independently approved by model Review.
Do not redo those model calls without a changed task/source requirement.

The current code branch adds the signed initial-import exporter, private preview,
operator acceptance record, gated staging and base-trusted Git-blob validation.
Read `docs/reviewed-pr-export.md` and the built-in skill. Source/model traces are
locally audited coordinator evidence, not provider-authenticated execution.

42 offline tests pass, including signed/unsigned and tampered payloads, same-
session rejection, acceptance scope, stale Git bases, mixed code/data, executable
blobs, atomic preflight/idempotence, complete prompt/context binding, current
capture binding and Windows line endings. A separate read-only Terra-medium code
review found the prompt/context and cached-evidence issues; both were fixed with
regressions. All 10 real pilot cases pass the new offline audit.

The first private GitHub batch uses Q13371 (Harvard/finance), Q1075625 (Nottingham
Ningbo/branch and multilingual), Q519556 (Southwestern Associated University/history).
Use the most recent `.private/pr-pilot/.../inspection.json` and `preview.json` for
operator inspection. The content scope binds exact records and inference summaries;
base commits are separately rebound after a code-only rebase. Private keys and raw
sources are never included in PRs or inspection exports.

Next steps:

1. Merge the integration code PR so the public trust policy and base workflow exist.
2. Obtain explicit operator acceptance of the three-school data scope. Merging a
   code PR alone does not record that data acceptance. Do not invent an approval.
3. Fetch current main, prepare the same reviewed batch against that base with its
   acceptance record, and use `pr-stage` in a clean data worktree.
4. Open a real data-only PR and let the trusted base check verify exact blobs.
   Record independent model Review as a safe PR comment/summary; do not claim a
   second GitHub account formally approved when credentials use the same account.
5. Keep merge visible to the operator. Required checks, strict-base protection,
   authenticated separate reviewer accounts and auto-merge remain unconfigured.

The exporter deliberately refuses replacing an existing university. The next
coding milestone after the initial data PR is a versioned v0.2 incremental diff
adapter, joined to the existing lease/CAS task primitives. Existing v0.1 commands
remain compatible. Broader adapters and official dataset releases remain separate.
