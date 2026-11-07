"""Single-manager native proposal and repository contracts; no PR transport."""
import re
import subprocess
from .integrity import load_json, sha
from .records import CURRENT_SCHEMA_VERSION, encode, instant
from .preferred import validate, recompute
from .domain_refresh import materialize
from .git_data import blob, record_relative, commit, git
from .seed_catalog import NAMES, verify as verify_catalog

PROPOSAL_KEYS = {"type", "review_status", "qid", "seed", "baseline_sha256", "delta", "candidate", "proposed_at",
                 "coverage", "retrieval_failures", "open_requests", "research", "transport"}

# These inputs determine the meaning of a frozen Research/Review approval.
# Publication plumbing and unrelated records may advance independently.
REVIEW_CONTRACT_PATHS = (
    '.curation/review-trust.json', 'schemas', *NAMES,
    'docs/review-policy-v2.md', 'docs/review-scope-v3.md',
    'docs/deep-research.md', 'docs/university-overview.md', 'config/workflow.json',
) + tuple('.agents/skills/university-curation/scripts/lib/university_curation/'+name+'.py'
          for name in ('native_research', 'native_review', 'research_contract',
                       'research_schema', 'review_scope', 'domain_refresh',
                       'records', 'preferred', 'coordinates', 'schema_v02',
                       'seed_catalog', 'integrity', 'source_packet',
                       'sources', 'source_requests', 'web_sources'))

# An explicitly audited compiler transition: the only change tightens
# full_refresh for a disputed six-group survey. Old approvals are compatible
# only when their frozen verdict still computes the same full_refresh under
# the current rule (checked again by verify_files).
_NATIVE_REVIEW_PATH = '.agents/skills/university-curation/scripts/lib/university_curation/native_review.py'
_COMPATIBLE_REVIEW_BLOBS = {
    ('1ccce38fd841a4656bb925f907386dbfb655adde',
     'f8f4111d5e3892a6b2b3bb7a4c9d93c8c057e58f'),
}


def _compatible_review_change(repo, original, current, changed):
    """Allow only an exact, previously audited review-compiler transition."""
    if changed != [_NATIVE_REVIEW_PATH]:
        return False
    try:
        previous = git(repo, 'rev-parse', original + ':' + _NATIVE_REVIEW_PATH).decode().strip()
        latest = git(repo, 'rev-parse', current + ':' + _NATIVE_REVIEW_PATH).decode().strip()
    except subprocess.CalledProcessError:
        return False
    return (previous, latest) in _COMPATIBLE_REVIEW_BLOBS


def check_review_refresh(proposal, verdict):
    """Recompute full-refresh eligibility, including for frozen approvals."""
    from .research_schema import GROUPS
    declared = {r['group']: r['status'] for r in proposal['coverage']}
    reviewed = verdict['coverage_checks']
    checked = {r['group']: r['status'] for r in reviewed}
    full = (verdict['decision'] == 'approve' and declared == checked and
            len(declared) == len(GROUPS) and set(declared) == set(GROUPS) and
            len(reviewed) == len(GROUPS) and
            all(s in ('checked', 'not_found', 'not_applicable') for s in declared.values()) and
            not proposal['retrieval_failures'] and
            proposal['delta']['curation']['identity_status'] in ('in_scope', 'related', 'excluded'))
    if type(verdict.get('full_refresh')) is not bool or verdict['full_refresh'] != full:
        raise ValueError('Review full_refresh differs from current survey rules')


def check_publication_base(repo, original, current, entities=()):
    """Permit main advancement only outside the reviewed contract/QID scope."""
    original=commit(repo,original); current=commit(repo,current)
    git(repo,'merge-base','--is-ancestor',original,current)
    changed=git(repo,'diff','--name-only',original,current,'--',*REVIEW_CONTRACT_PATHS).decode().splitlines()
    if changed and not _compatible_review_change(repo,original,current,changed):
        raise ValueError('Review contract changed: '+', '.join(changed))
    if entities:
        from .manager import backlog_at
        previous=backlog_at(repo,original)['tasks']; latest=backlog_at(repo,current)['tasks']
        for entity in entities:
            if baseline_at(repo,original,entity)[1]!=baseline_at(repo,current,entity)[1]:
                raise ValueError('University baseline changed: '+entity)
            if previous.get(entity)!=latest.get(entity):
                raise ValueError('Concurrent task change: '+entity)


def trust_at(repo, ref):
    trust = load_json(blob(repo, ref, ".curation/review-trust.json"))
    return trust


def catalog_at(repo, base, trust):
    raw = {p: blob(repo, base, p, max_bytes=20_000_000) for p in NAMES}; rows = verify_catalog(raw, trust=trust)
    catalog = {r["qid"]: {**r, "queue_kind": "discovery"} for r in rows["discovery"]}
    catalog.update({r["qid"]: {**r, "queue_kind": "primary"} for r in rows["primary"]})
    return catalog, sha(raw[NAMES[2]])


def seed_metadata(row, catalog_hash):
    return {"import_id": "seed-" + catalog_hash[:16], "screening_status": row.get("screening_status", "needs_review"),
            "channels": row.get("channels", ["legacy_discovery"])}


def baseline_at(repo, base, qid):
    p = record_relative(qid); raw = blob(repo, base, p, optional=True)
    return (load_json(raw) if raw else None), (sha(raw) if raw else "absent")


def public_bounds(value):
    if len(encode(value)) > 1_900_000: raise ValueError("Structured proposal too large")
    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "original_text" and (not isinstance(v, str) or len(v) > 1000): raise ValueError("Public evidence must be a short excerpt")
                walk(v)
        elif isinstance(node, list):
            for v in node: walk(v)
        elif isinstance(node, str) and (".private/" in node or ".private\\" in node or "-----BEGIN PRIVATE KEY" in node):
            raise ValueError("Private material in public structured output")
    walk(value)


def attach_transport(proposal, repository, base, catalog_hash, trust):
    result = dict(proposal)
    result["transport"] = {"repository": repository, "base_commit": base, "seed_catalog_sha256": catalog_hash,
        "schema_sha256": trust["schemas"]["0.2.2"], "review_policy": trust["review_policy"], "protocol": "native-subagent-v1"}
    return result


def check_proposal(proposal, baseline, catalog, catalog_hash, trust):
    if set(proposal) != PROPOSAL_KEYS or proposal["type"] != "university-proposal-v1" or proposal["review_status"] != "unreviewed":
        raise ValueError("Unexpected native proposal contract")
    qid = proposal["qid"]; delta = proposal["delta"]; transport = proposal["transport"]
    if qid not in catalog or proposal["seed"] != seed_metadata(catalog[qid], catalog_hash): raise ValueError("QID/seed is outside accepted catalog")
    if delta["qid"] != qid or delta["seed"] != proposal["seed"]: raise ValueError("Proposal subject mismatch")
    if set(transport) != {"repository", "base_commit", "seed_catalog_sha256", "schema_sha256", "review_policy", "protocol"}:
        raise ValueError("Unexpected transport metadata")
    if (transport["repository"] != trust["repository"] or transport["seed_catalog_sha256"] != catalog_hash
            or transport["schema_sha256"] != trust["schemas"].get("0.2.2") or transport["review_policy"] != trust["review_policy"] or transport["protocol"] != "native-subagent-v1"):
        raise ValueError("Proposal bound to another repository/schema/policy/catalog")
    if not re.fullmatch("[0-9a-f]{40}", transport["base_commit"]): raise ValueError("Invalid original Git base")
    if proposal["baseline_sha256"] != (sha(encode(baseline)) if baseline else "absent"): raise ValueError("University baseline changed")
    check_publishable(delta); check_publishable(proposal["candidate"]); instant(proposal["proposed_at"])
    from .git_data import check_source_revisions
    check_source_revisions(delta)
    if proposal["candidate"] != materialize(baseline, delta, proposal["seed"], proposal["proposed_at"], False): raise ValueError("Research rewrote fields outside deterministic append delta")
    if proposal["candidate"] != recompute(proposal["candidate"]): raise ValueError("Noncanonical preferred projection")
    from .research_contract import check_research_metadata
    check_research_metadata(proposal['research'])
    from .research_schema import GROUPS
    coverage = {r["group"]: r["status"] for r in proposal["coverage"]}
    if len(proposal["coverage"]) != len(GROUPS) or set(coverage) != set(GROUPS) or any(delta["coverage"][g]["status"] != coverage[g] for g in GROUPS): raise ValueError("Coverage declaration mismatch")
    from .research_contract import _open_requests
    _open_requests({"open_requests": proposal["open_requests"]})
    public_bounds(proposal)


def check_publishable(record):
    if record.get('schema_version')!=CURRENT_SCHEMA_VERSION:
        raise ValueError('New publications require the current university schema')
    if record.get('example',{}).get('synthetic'):
        raise ValueError('Synthetic examples cannot be published as university records')
    validate(record)
