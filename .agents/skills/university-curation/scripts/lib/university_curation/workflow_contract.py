"""Single-manager native proposal and repository contracts; no PR transport."""
from pathlib import Path
import re
from .attestations import load_json, sha
from .records import encode, instant
from .preferred import validate, recompute, fields
from .domain_refresh import materialize
from .git_data import blob, record_relative, batch_slug, canonical_json
from .seed_catalog import NAMES, verify as verify_catalog

PROPOSAL_KEYS = {"type", "review_status", "qid", "seed", "baseline_sha256", "delta", "candidate", "proposed_at",
                 "coverage", "retrieval_failures", "open_requests", "research", "transport"}


def trust_at(repo, ref):
    from .git_data import git
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
    validate(delta); validate(proposal["candidate"]); instant(proposal["proposed_at"])
    from .git_data import check_source_revisions
    check_source_revisions(delta)
    if proposal["candidate"] != materialize(baseline, delta, proposal["seed"], proposal["proposed_at"], False): raise ValueError("Research rewrote fields outside deterministic append delta")
    if proposal["candidate"] != recompute(proposal["candidate"]): raise ValueError("Noncanonical preferred projection")
    metadata = proposal["research"]
    if set(metadata) != {"model", "reasoning_effort", "session", "prompt_sha256", "schema_sha256"}: raise ValueError("Unexpected Research metadata")
    if (not isinstance(metadata['model'],str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',metadata['model'])
            or metadata['reasoning_effort'] not in ('low','medium','high','xhigh','max','ultra','not_reported')
            or not isinstance(metadata['session'],str) or not metadata['session'].strip()):
        raise ValueError('Truthful native model, effort and session required')
    for key in ("prompt_sha256", "schema_sha256"):
        if not re.fullmatch("[0-9a-f]{64}", metadata[key]): raise ValueError("Research provenance hash missing")
    from .research_schema import GROUPS
    coverage = {r["group"]: r["status"] for r in proposal["coverage"]}
    if len(proposal["coverage"]) != len(GROUPS) or set(coverage) != set(GROUPS) or any(delta["coverage"][g]["status"] != coverage[g] for g in GROUPS): raise ValueError("Coverage declaration mismatch")
    from .research_contract import _open_requests
    _open_requests({"open_requests": proposal["open_requests"]})
    public_bounds(proposal)
