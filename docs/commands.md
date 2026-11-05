# Current skill commands

Run from the checkout root with Python 3.11+, Git, authenticated GitHub access,
and a configured Codex CLI for model work.

```text
python -m pip install -e .
python .agents/skills/university-curation/scripts/agent.py --help
python .agents/skills/university-curation/scripts/agent.py --role research register-key
python .agents/skills/university-curation/scripts/agent.py --role review register-key
python .agents/skills/university-curation/scripts/agent.py --role research doctor
python .agents/skills/university-curation/scripts/agent.py --role review doctor
```

Register each role in its own environment; human-merge the public-key registration
PR before doctor or model work. Default private keys are .private/keys/ROLE.pem.
Use global --workspace ABSOLUTE_CHECKOUT and --key ABSOLUTE_PRIVATE_KEY when needed.
Never pass key contents or GitHub tokens in arguments.

## Research manager and one-QID subagents

```text
python .agents/skills/university-curation/scripts/agent.py --role research sync
python .agents/skills/university-curation/scripts/agent.py --role research next --limit 3
python .agents/skills/university-curation/scripts/agent.py --role research research --qid Q13371
python .agents/skills/university-curation/scripts/agent.py --role research publish --batch-size 3
python .agents/skills/university-curation/scripts/agent.py --role research research --qid Q13371 --pr 12
python .agents/skills/university-curation/scripts/agent.py --role research publish --pr 12
```

Only the manager calls next/publish/sync. Assigned subagents call research for
their QID; global CAS model leases apply across both roles. JSON results state
whether to revise, wait for Review, rebind or wait for human merge.

## Independent Review

```text
python .agents/skills/university-curation/scripts/event_review.py --repository ider-zh/university-seed-curation --mode queue --scan
python .agents/skills/university-curation/scripts/agent.py --role review next-review
python .agents/skills/university-curation/scripts/agent.py --role review review --pr 12
python .agents/skills/university-curation/scripts/agent.py --role review review-request --pr 12 --qid Q13371 --field geography --category scope_conflict --reason "Check whether the point belongs to the institution"
python .agents/skills/university-curation/scripts/event_review.py --repository ider-zh/university-seed-curation --mode status --scan
```

next-review consumes the GitHub head queue with a renewed lease. Direct review
is a bounded manual entry and still obeys the global one-Review model slot.
The queue-only Actions dispatcher is disabled unless repository variable
UNIVERSITY_EVENT_REVIEW_ENABLED is true. It never runs models or holds role keys.

## Validation and maintenance

```text
python -m unittest discover -s tests
python .agents/skills/university-curation/scripts/maintain_schema.py check
python .agents/skills/university-curation/scripts/curate.py validate examples/university.complete.synthetic.json
python .agents/skills/university-curation/scripts/curate.py pr-validate --workspace . --base-ref BASE_SHA --head-ref HEAD_SHA
python .agents/skills/university-curation/scripts/seeds.py --help
python .agents/skills/university-curation/scripts/seed_delivery.py --help
python .agents/skills/university-curation/scripts/buckets.py --help
```

See source-tools for online queries. Historical curate.py SQLite task commands,
initial-import and coordinates adapters remain for compatibility; they are not
the distributed scheduler. Seed/bucket bootstrap scripts run against exact main
and preserve old receipts. Data PRs cannot mix executable code or Schema edits.
