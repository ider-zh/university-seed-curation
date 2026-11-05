# Next milestone: observable GitHub agent collaboration

Operator intent recorded during the ten-school private trial: after successful
acceptance, exercise Research/Review through real GitHub branches and PRs, then
keep upgrading the workflow. The private trial is not itself public acceptance.

## First real batch

Use a small batch drawn from the accepted sample, including a historical school,
a branch/system boundary and a multilingual institution. Freeze the accepted
schema, selection policy and input baseline first. Only reviewed structured
results are exported; raw pages, prompts, failed proposals, private job logs and
credentials stay outside Git. Public seed/data import retains the existing human
acceptance gate. No automatic merge is enabled by this design note.

## Concrete implementation needed before the first data PR

1. Finish the code/schema draft PR, preserving the old schema version and
   keeping code/workflow changes separate from school-data PRs.
2. Connect the trusted export adapter to actual Research and independent Review
   receipts. Bind QID, base revision, record content, schema/policy/code versions,
   reviewed fields and source checks. Do not treat a self-asserted JSON receipt
   from a data branch as trusted approval.
3. Create a real small-batch branch and PR containing only passed records and
   compact public review summaries. Preserve each QID's SHA-256 bucket path.
4. Run read-only CI using trusted validation code from the base revision. Check
   schema, provenance references, preferred/inference consistency, record baseline
   and the allowed export scope. Never execute proposed workflow code with a
   write token on an untrusted data PR.
5. Let the independent Review role inspect the exact PR diff, return precise
   per-school findings and verify revisions before the merge decision. A returned
   school is removed or corrected and re-reviewed; GitHub cannot partially merge
   files from a PR.
6. Record the final PR head and checks. Initial testing keeps the merge decision
   visible to the operator; protected automation is a later verified rollout.

## What the operator should see

- Actual PR link, branch/head commits, schema/policy baseline and a small school list.
- Added/changed facts with source revisions and reasonable-inference explanations.
- Distinct Research/Review model sessions, with only compact safe metadata public.
- Review comments, any requested revision, the resulting diff and CI status.
- A merge outcome bound to the reviewed PR head, not to an earlier proposal.

GitHub account identity and model-session identity are different. If the available
credentials identify one account, do not claim that it formally approved its own
PR as a second GitHub reviewer. Verify account/App capabilities before selecting
formal review events, safe comments plus checks, or a separately configured
reviewer identity. The export, authenticated public receipts and protected merge
integration remain unconfigured until that verification is actually performed.

Keep a synthetic negative-control CI case for invalid schema/stale baseline/
unverified receipt rejection. Do not publish failed real-school proposals just
to demonstrate a red check.

## Integration progress after PR #1 merge

The next code PR implements signed initial-import receipts, private batch
preparation, explicit data-acceptance gating, safe staging and a base-trusted data
validator/workflow. See `docs/reviewed-pr-export.md` for executable commands and
trust assumptions. The first private batch is Harvard (finance), Nottingham
Ningbo (branch/multilingual), and Southwestern Associated University (historical).
Actual data PR publication waits for the integration merge and explicit acceptance
of that content scope; model trials are reused rather than rerun without need.
