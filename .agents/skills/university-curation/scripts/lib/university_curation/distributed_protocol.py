"""Public Draft proposals and independent role-signed Review decisions.

GitHub is the transport. Private caches, model logs and keys never cross roles.
"""
from pathlib import Path
import re

from .attestations import load_json, sha, sign, verify
from .records import encode, instant
from .preferred import validate, recompute, fields
from .domain_refresh import materialize
from .pr_export import blob, record_relative, batch_slug, canonical_json
from .seed_catalog import NAMES, verify as verify_catalog

PROPOSAL_KEYS = {"type", "review_status", "qid", "seed", "baseline_sha256", "delta", "candidate", "proposed_at",
                 "coverage", "retrieval_failures", "open_requests", "research", "transport"}
REVIEW_MARKER = "university-signed-review-v1"


def trust_at(repo, ref):
    from .pr_export import git
    trust = load_json(blob(repo, ref, ".curation/review-trust.json"))
    names = git(repo, "ls-tree", "-r", "--name-only", ref, "--", ".curation/roles").decode().splitlines()
    for name in names:
        match = re.fullmatch(r"\.curation/roles/(research|review)/(review-[0-9a-f]{16})\.json", name)
        if not match: raise ValueError("Invalid role-key registry path")
        value = canonical_json(blob(repo, ref, name))
        if set(value) != {"key_id", "algorithm", "public_key_hex", "status", "role"} or value["algorithm"] != "Ed25519" or value["role"] != match[1] or value["key_id"] != match[2] or value["status"] not in ("active", "revoked"):
            raise ValueError("Invalid role-key descriptor")
        public = bytes.fromhex(value["public_key_hex"])
        if len(public) != 32 or "review-" + sha(public)[:16] != value["key_id"] or value["key_id"] in trust["keys"]: raise ValueError("Role keys must be unique, with independent signing identities")
        trust["keys"][value["key_id"]] = {"algorithm": "Ed25519", "public_key_hex": value["public_key_hex"], "status": value["status"], "roles": [value["role"]]}
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
    if raw is None:
        from .bucket_migration import paths
        raw = blob(repo, base, paths(qid)[0], optional=True)
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
        "schema_sha256": trust["schemas"]["0.2.2"], "review_policy": trust["review_policy"], "protocol": "distributed-v1"}
    return result


def check_proposal(proposal, baseline, catalog, catalog_hash, trust):
    if set(proposal) != PROPOSAL_KEYS or proposal["type"] != "university-proposal-v1" or proposal["review_status"] != "unreviewed":
        raise ValueError("Unexpected Draft proposal contract")
    qid = proposal["qid"]; delta = proposal["delta"]; transport = proposal["transport"]
    if qid not in catalog or proposal["seed"] != seed_metadata(catalog[qid], catalog_hash): raise ValueError("QID/seed is outside accepted catalog")
    if delta["qid"] != qid or delta["seed"] != proposal["seed"]: raise ValueError("Proposal subject mismatch")
    if set(transport) != {"repository", "base_commit", "seed_catalog_sha256", "schema_sha256", "review_policy", "protocol"}:
        raise ValueError("Unexpected transport metadata")
    if (transport["repository"] != trust["repository"] or transport["seed_catalog_sha256"] != catalog_hash
            or transport["schema_sha256"] != trust["schemas"].get("0.2.2") or transport["review_policy"] != trust["review_policy"] or transport["protocol"] != "distributed-v1"):
        raise ValueError("Proposal bound to another repository/schema/policy/catalog")
    if not re.fullmatch("[0-9a-f]{40}", transport["base_commit"]): raise ValueError("Invalid original Git base")
    if proposal["baseline_sha256"] != (sha(encode(baseline)) if baseline else "absent"): raise ValueError("University baseline changed")
    validate(delta); validate(proposal["candidate"]); instant(proposal["proposed_at"])
    if proposal["candidate"] != materialize(baseline, delta, proposal["seed"], proposal["proposed_at"], False): raise ValueError("Research rewrote fields outside deterministic append delta")
    if proposal["candidate"] != recompute(proposal["candidate"]): raise ValueError("Noncanonical preferred projection")
    metadata = proposal["research"]
    if set(metadata) != {"model", "reasoning_effort", "session", "prompt_sha256", "schema_sha256"}: raise ValueError("Unexpected Research metadata")
    if metadata["model"] != trust["model"] or metadata["reasoning_effort"] != trust["reasoning_effort"] or not metadata["session"]: raise ValueError("Wrong Research model configuration")
    for key in ("prompt_sha256", "schema_sha256"):
        if not re.fullmatch("[0-9a-f]{64}", metadata[key]): raise ValueError("Research provenance hash missing")
    from .pilot_protocol import GROUPS
    coverage = {r["group"]: r["status"] for r in proposal["coverage"]}
    if len(proposal["coverage"]) != len(GROUPS) or set(coverage) != set(GROUPS) or any(delta["coverage"][g]["status"] != coverage[g] for g in GROUPS): raise ValueError("Coverage declaration mismatch")
    from .distributed_jobs import _open_requests
    _open_requests({"open_requests": proposal["open_requests"]})
    public_bounds(proposal)


def signed_comment(document):
    raw = encode(document).decode()
    if len(raw.encode()) > 60_000: raise ValueError("Review summary exceeds GitHub comment budget")
    return "Independent signed university Review.\n\n<!-- " + REVIEW_MARKER + "\n" + raw + "-->"


def read_reviews(comments, trust, pr_number, qid, proposal_hash):
    results = []
    for comment in sorted(comments, key=lambda row: row.get("id", 0)):
        body = comment.get("body") or ""
        found = re.search(r"<!-- " + REVIEW_MARKER + r"\n([\s\S]*?)-->", body)
        if not found: continue
        try:
            doc = load_json(found[1].strip().encode()); value = verify(doc, trust, role="review")
        except (ValueError, KeyError, TypeError): continue
        if value.get("type") != "university-review-decision-v1" or value.get("repository") != trust["repository"]: continue
        if value.get("pr_number") == pr_number and value.get("qid") == qid and value.get("proposal_sha256") == proposal_hash:
            results.append((doc, comment.get("id"), comment.get("html_url")))
    return results


def check_decision(document, proposal_document, baseline, trust, pr_number=None):
    research = verify(proposal_document, trust, role="research"); value = verify(document, trust, role="review")
    if document["key_id"] == proposal_document["key_id"]: raise ValueError("Research and Review signing identities must differ")
    required = {"type", "repository", "pr_number", "reviewed_head_sha", "policy", "schema_sha256", "decision", "qid", "reviewed_at", "proposal_sha256", "facts_checked", "contexts_checked", "source_revisions_checked", "requests", "request_responses", "coverage_checks", "model", "reasoning_effort", "review_session", "full_refresh", "inferences"}
    expected = required | ({"record_sha256"} if value.get("decision") == "approve" else set())
    if set(value) != expected: raise ValueError("Unexpected Review decision keys")
    if value["type"] != "university-review-decision-v1" or value["repository"] != trust["repository"] or value["qid"] != research["qid"]: raise ValueError("Review identity mismatch")
    if value["decision"] not in ("approve", "request_changes", "unresolved"): raise ValueError("Unknown Review decision")
    if pr_number is not None and value["pr_number"] != pr_number: raise ValueError("Review belongs to another PR")
    if type(value["pr_number"]) is not int or value["pr_number"] < 1 or not re.fullmatch("[0-9a-f]{40}", value["reviewed_head_sha"]): raise ValueError("Invalid Review PR/head")
    if value["policy"] != trust["review_policy"] or value["schema_sha256"] != trust["schemas"]["0.2.2"]: raise ValueError("Review policy/schema changed")
    if value["proposal_sha256"] != sha(encode(research)): raise ValueError("Review did not cover this exact proposal")
    if value["model"] != trust["model"] or value["reasoning_effort"] != trust["reasoning_effort"] or not value["review_session"] or value["review_session"] == research["research"]["session"]:
        raise ValueError("Independent configured Review session required")
    instant(value["reviewed_at"])
    if instant(value["reviewed_at"]) < instant(research["proposed_at"]): raise ValueError("Review predates Research")
    delta = research["delta"]
    count = sum(len(f["candidates"]) for _, f, _ in fields(delta))
    contexts = 1 + len(delta.get("locations", [])) + len(delta.get("history", {}).get("milestones", [])) + len(delta.get("related_entities", {}))
    if value["facts_checked"] != count or value["contexts_checked"] != contexts or value["source_revisions_checked"] != len(delta["sources"]): raise ValueError("Review coverage incomplete")
    requested = {r["request_id"] for r in research["open_requests"]}; responses = value["request_responses"]
    if len(responses) != len(requested) or {r["request_id"] for r in responses} != requested: raise ValueError("Missing response to prior objections")
    public_bounds(value)
    if value["decision"] != "approve": return value, None
    if value["requests"] or any(r["status"] != "addressed" for r in responses): raise ValueError("Unresolved objections cannot be approved")
    from .pilot_protocol import GROUPS
    declared = {r["group"]: r["status"] for r in research["coverage"]}; checked = {r["group"]: r["status"] for r in value["coverage_checks"]}
    full = (declared == checked and len(value["coverage_checks"]) == len(GROUPS)
            and not research["retrieval_failures"] and delta["curation"]["identity_status"] in ("in_scope", "related", "excluded"))
    if type(value["full_refresh"]) is not bool or value["full_refresh"] != full: raise ValueError("Invalid full-refresh claim")
    record = materialize(baseline, delta, research["seed"], value["reviewed_at"], full)
    if value["record_sha256"] != sha(encode(record)): raise ValueError("Review record hash differs from deterministic finalization")
    return value, record


def inspect_draft(repo, base, head, trust):
    from .pr_export import git
    paths = [p for p in git(repo, "diff", "--no-renames", "--name-only", "-z", base, head).decode().split("\0") if p]
    manifests = [p for p in paths if re.fullmatch(r"data/proposals/[a-z0-9][a-z0-9-]{0,79}/manifest\.json", p)]
    if len(manifests) != 1: raise ValueError("One Draft batch manifest required")
    doc = canonical_json(blob(repo, head, manifests[0])); manifest = verify(doc, trust, role="research")
    if set(manifest) != {"type", "repository", "batch_id", "base_commit", "seed_catalog_sha256", "records"} or manifest["type"] != "university-draft-batch-v1" or manifest["repository"] != trust["repository"] or manifest["base_commit"] != base:
        raise ValueError("Draft batch identity/base mismatch")
    batch = batch_slug(manifest["batch_id"]); catalog, catalog_hash = catalog_at(repo, base, trust)
    if manifest["seed_catalog_sha256"] != catalog_hash or not 1 <= len(manifest["records"]) <= trust["max_schools_per_batch"]: raise ValueError("Draft catalog/size mismatch")
    expected = {"data/proposals/" + batch + "/manifest.json"}; proposals = {}; ids = []
    for row in manifest["records"]:
        qid = row["qid"]; path = "data/proposals/" + batch + "/" + qid + ".json"
        if row["path"] != path: raise ValueError("Noncanonical Draft path")
        raw = blob(repo, head, path); envelope = canonical_json(raw)
        if sha(raw) != row["sha256"]: raise ValueError("Draft file changed")
        proposal = verify(envelope, trust, role="research"); baseline, _ = baseline_at(repo, base, qid)
        if proposal["qid"] != qid: raise ValueError("Draft row/item mismatch")
        check_proposal(proposal, baseline, catalog, catalog_hash, trust)
        proposals[qid] = envelope; ids.append(qid); expected.add(path)
    if len(ids) != len(set(ids)) or ids != sorted(ids, key=lambda q: int(q[1:])) or set(paths) != expected: raise ValueError("Draft membership or file set mismatch")
    return manifest, proposals


def verify_final(repo, base, files, trust):
    manifests = [p for p in files if re.fullmatch(r"data/batches/[a-z0-9][a-z0-9-]{0,79}\.json", p)]
    if len(manifests) != 1: raise ValueError("One final batch manifest required")
    document = canonical_json(files[manifests[0]]); manifest = verify(document, trust, role="research")
    if set(manifest) != {"type", "repository", "batch_id", "base_commit", "seed_catalog_sha256", "records"} or manifest["type"] != "university-final-batch-v1" or manifest["repository"] != trust["repository"] or manifest["base_commit"] != base:
        raise ValueError("Final batch base/repository mismatch")
    batch = batch_slug(manifest["batch_id"]); catalog, catalog_hash = catalog_at(repo, base, trust)
    if manifest["seed_catalog_sha256"] != catalog_hash or not 1 <= len(manifest["records"]) <= trust["max_schools_per_batch"]: raise ValueError("Final catalog/size mismatch")
    if manifests[0] != "data/batches/" + batch + ".json" or blob(repo, base, manifests[0], optional=True) is not None: raise ValueError("Final batch is immutable")
    expected = {manifests[0]}; ids = []; review_pr = None
    for row in manifest["records"]:
        qid = row["qid"]; p = record_relative(qid); receipt_path = "data/reviews/" + batch + "/" + qid + ".json"
        from .pr_export import no_legacy_duplicate
        no_legacy_duplicate(repo, base, qid)
        if row["record_path"] != p or row["receipt_path"] != receipt_path: raise ValueError("Final path mismatch")
        if blob(repo, base, receipt_path, optional=True) is not None: raise ValueError("Review receipt is immutable")
        if sha(files[p]) != row["record_sha256"] or sha(files[receipt_path]) != row["receipt_sha256"]: raise ValueError("Final bytes changed")
        receipt = canonical_json(files[receipt_path])
        if set(receipt) != {"type", "research", "review"} or receipt["type"] != "university-distributed-receipt-v1": raise ValueError("Unexpected distributed receipt")
        proposal = verify(receipt["research"], trust, role="research"); baseline, _ = baseline_at(repo, base, qid)
        if proposal["qid"] != qid: raise ValueError("Final row/item mismatch")
        check_proposal(proposal, baseline, catalog, catalog_hash, trust)
        verdict, record = check_decision(receipt["review"], receipt["research"], baseline, trust)
        if verdict["decision"] != "approve" or record is None or record["qid"] != qid or encode(record) != files[p]: raise ValueError("No independent approval for these exact final bytes")
        if review_pr is not None and review_pr != verdict["pr_number"]: raise ValueError("Review receipts from different PRs")
        review_pr = verdict["pr_number"]; expected.update((p, receipt_path)); ids.append(qid)
    if len(ids) != len(set(ids)) or ids != sorted(ids, key=lambda q: int(q[1:])) or set(files) != expected: raise ValueError("Final batch membership mismatch")
    return {"status": "validated", "task_kind": "distributed_research", "batch_id": batch, "qids": ids, "base_commit": base, "review_pr": review_pr}
