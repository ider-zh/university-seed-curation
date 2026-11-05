"""Private source/review audit and signed export for the bounded P625 adapter."""
from datetime import datetime, timezone
from pathlib import Path

from .attestations import load_json, private_path, sha, sign
from .coordinates import KIND, root_source, projection, materialize, review_prompt, review_gate, REVIEW_SCHEMA
from .pilot_audit import provider
from .pr_export import blob, commit, record_relative, scope, batch_slug, verify_files
from .records import encode, instant
from .sources import Cache


def read(path): return load_json(Path(path).read_bytes())


def start(repo, entity_id, base_ref, cache, output, request_ref):
    output = private_path(output)
    if output.exists(): raise FileExistsError("Preserve previous coordinate attempts; choose a new private job")
    if not request_ref.strip(): raise ValueError("Change-request reference required")
    base = commit(repo, base_ref); raw = blob(repo, base, record_relative(entity_id), optional=True)
    if raw is None:
        from .bucket_migration import paths
        raw = blob(repo, base, paths(entity_id)[0])
    record = load_json(raw)
    _, source = root_source(record)
    entity, capture = Cache(cache, maxlag=30).entity_revision(entity_id, source["revision_id"])
    point = projection(record, entity)
    changed_at = datetime.now(timezone.utc).isoformat()
    candidate = materialize(record, point, changed_at)
    output.mkdir(parents=True)
    packet = {"base_commit": base, "baseline_sha256": sha(raw), "baseline": record, "coordinate_projection": point,
        "candidate": candidate, "request_ref": request_ref}
    (output / "production-capture.json").write_bytes(encode(read(capture["cache_path"])))
    (output / "job.json").write_bytes(encode(packet))
    return {"job": str(output), "qid": entity_id, "statements": len(point["statements"]), "status": "awaiting_independent_review"}


def independent_review(job, cache, repo):
    from .codex_provider import run
    job = private_path(job); packet = read(job / "job.json"); base = packet["baseline"]
    if (job / "review-call").exists(): raise FileExistsError("Preserve prior Review attempts; create a new private job")
    _, source = root_source(base)
    entity, capture = Cache(cache, maxlag=30).entity_revision(base["qid"], source["revision_id"], refresh=True)
    if projection(base, entity) != packet["coordinate_projection"]: raise ValueError("Independent source projection differs")
    expected = materialize(base, packet["coordinate_projection"], packet["candidate"]["modified_datetime"])
    if packet["candidate"] != expected: raise ValueError("Private candidate was modified outside coordinate task")
    value = {"baseline": base, "candidate": expected, "coordinate_projection": packet["coordinate_projection"],
        "source_entity": entity}
    # Full source stays private; only normalized point and statement IDs go public.
    (job / "review-capture.json").write_bytes(encode(read(capture["cache_path"])))
    (job / "review-input.json").write_bytes(encode(value))
    result, _ = run(review_prompt(value), REVIEW_SCHEMA, job / "review-call", repo)
    review_gate(result, packet["coordinate_projection"])
    return {"qid": base["qid"], "decision": result["decision"], "checks": len(result["checks"])}


def audit(job, trust, cache):
    job = private_path(job); packet = read(job / "job.json"); baseline = packet["baseline"]
    source_ref, src = root_source(baseline)
    # Replay only the exact captured independent response, with no network or TTL fallback.
    capture = read(job / "review-capture.json")
    def only_capture(url):
        if url != capture["request_url"]: raise ValueError("Unexpected independent source request")
        return capture["data"]
    entity, _ = Cache(cache, fetch=only_capture, maxlag=30).entity_revision(baseline["qid"], src["revision_id"], refresh=True)
    point = projection(baseline, entity)
    if point != packet["coordinate_projection"]: raise ValueError("Coordinate projection is not the captured source")
    candidate = materialize(baseline, point, packet["candidate"]["modified_datetime"])
    if candidate != packet["candidate"]: raise ValueError("Private delta changed")
    value = {"baseline": baseline, "candidate": candidate, "coordinate_projection": point, "source_entity": entity}
    if read(job / "review-input.json") != value: raise ValueError("Review input changed after run")
    result, meta = provider(job / "review-call", trust)
    if instant(capture["retrieved_at"]) > instant(meta["started_at"]): raise ValueError("Source capture postdates Review input")
    import json
    raw_hash = sha(json.dumps(capture["data"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
    if raw_hash != capture["body_sha256"]: raise ValueError("Independent capture body changed")
    if (job / "review-call/prompt.txt").read_text(encoding="utf-8") != review_prompt(value):
        raise ValueError("Review prompt was not the complete trusted coordinate review")
    if read(job / "review-call/output.schema.json") != REVIEW_SCHEMA: raise ValueError("Wrong coordinate review contract")
    review_gate(result, point)
    at = meta["ended_at"]; instant(at)
    if instant(at) < instant(candidate["modified_datetime"]): raise ValueError("Review predates proposal")
    record = materialize(baseline, point, at)
    review = {"task_kind": KIND, "producer": "deterministic-root-p625-v1", "research_sessions": [],
        "review_session": meta["session_ids"][0], "decision": result["decision"], "model": trust["model"],
        "reasoning_effort": trust["reasoning_effort"], "reviewed_at": at,
        "facts_checked": len(point["statements"]), "contexts_checked": 1, "source_revisions_checked": 1,
        "coordinate_projection": point, "request_ref": packet["request_ref"], "inferences": [],
        "runtime_model_reported": bool(meta.get("reported_models")),
        "private_evidence_sha256": sha(encode({"review_input": value, "capture": capture, "provider": meta})),
        "review_output_sha256": sha(encode(result)), "attestation_kind": "local_coordinator_verified_private_traces"}
    return packet, record, review


def build(repo, job, base_ref, batch_id, key, output, cache):
    output = private_path(output); batch_id = batch_slug(batch_id); base = commit(repo, base_ref)
    if output.exists(): raise FileExistsError("Preserve previous coordinate export attempts")
    trust = load_json(blob(repo, base, ".curation/review-trust.json"))
    packet, record, review = audit(job, trust, cache)
    path = record_relative(record["qid"]); old = blob(repo, base, path)
    if old != encode(packet["baseline"]) or sha(old) != packet["baseline_sha256"]:
        raise ValueError("University baseline changed; prepare and review a new task")
    # A code-only rebase is safe when facts and task contract remain identical.
    version = record["schema_version"]
    schema_hash = sha(encode(load_json(blob(repo, base, "schemas/university.v" + version + ".schema.json"))))
    if trust["schemas"].get(version) != schema_hash: raise ValueError("Coordinate schema not trusted by Git base")
    data = encode(record)
    payload = {"type": "university-review-v1", "repository": trust["repository"], "qid": record["qid"],
        "base_commit": base, "record_path": path, "record_sha256": sha(data), "baseline_sha256": sha(old),
        "schema_version": version, "schema_sha256": schema_hash, "review_policy": trust["review_policy"], "review": review}
    receipt_path = "data/reviews/" + batch_id + "/" + record["qid"] + ".json"
    receipt = encode(sign(payload, key, trust))
    rows = [{"qid": record["qid"], "record_path": path, "record_sha256": sha(data), "receipt_path": receipt_path, "receipt_sha256": sha(receipt)}]
    content = scope(rows, {record["qid"]: payload}, trust)
    manifest = {"type": "university-batch-v1", "task_kind": KIND, "repository": trust["repository"], "batch_id": batch_id,
        "base_commit": base, "created_at": datetime.now(timezone.utc).isoformat(), "content_scope_sha256": content,
        "authorization": {"kind": "independently_reviewed_field_update", "request_refs": [review["request_ref"]]}, "records": rows}
    files = {path: data, receipt_path: receipt, "data/batches/" + batch_id + ".json": encode(sign(manifest, key, trust))}
    result = verify_files(repo, base, files, trust)
    for relative, raw in files.items():
        dest = output / relative; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(raw)
    preview = {**result, "files": {p: sha(v) for p, v in files.items()}}
    (output / "preview.json").write_bytes(encode(preview))
    (output / "inspection.json").write_bytes(encode({"record": record, "review": review}))
    return preview
