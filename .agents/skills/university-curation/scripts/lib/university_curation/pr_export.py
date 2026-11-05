"""Signed, base-bound data batches. Preparation is private; installation is gated."""
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

from .attestations import load_json, sha, sign, verify, private_path
from .records import encode, qid, record_path, instant, ROOT
from .preferred import validate, fields, recompute

TRUST_PATH = ".curation/review-trust.json"


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)


def commit(repo, ref):
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", ref) or ref.startswith("-"): raise ValueError("Invalid Git ref")
    return git(repo, "rev-parse", "--verify", ref + "^{commit}").decode().strip()


def check_sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value): raise ValueError("SHA-256 digest required")


def blob(repo, ref, path, optional=False, max_bytes=2 * 1024**2):
    entry = git(repo, "ls-tree", "-z", ref, "--", path)
    if not entry:
        if optional: return None
        raise ValueError("Missing Git blob: " + path)
    info, found = entry.rstrip(b"\0").split(b"\t", 1)
    if found.decode() != path or info.split()[:2] != [b"100644", b"blob"]:
        raise ValueError("Data must be a regular non-executable Git blob")
    size = int(git(repo, "cat-file", "-s", info.split()[2].decode()))
    if size > max_bytes: raise ValueError("Oversized data blob")
    return git(repo, "cat-file", "blob", info.split()[2].decode())


def record_relative(entity_id):
    return record_path(Path.cwd(), entity_id).relative_to(Path.cwd().resolve()).as_posix()


def no_legacy_duplicate(repo, base, entity_id):
    from .bucket_migration import paths
    if blob(repo, base, paths(entity_id)[0], optional=True) is not None:
        raise ValueError("Migrate existing three-hex records before importing/updating this QID")


def batch_slug(value):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", value): raise ValueError("Invalid batch ID")
    return value


def canonical_json(data):
    value = load_json(data)
    if encode(value) != data: raise ValueError("Public JSON must use canonical script encoding")
    return value


def scope(rows, receipts, trust):
    return sha(encode({"schemas": trust["schemas"], "review_policy": trust["review_policy"],
        "records": [{"qid": row["qid"], "record_sha256": row["record_sha256"],
            "inferences_sha256": sha(encode(receipts[row["qid"]]["review"]["inferences"]))} for row in rows]}))


def check_record(record, review, trust, baseline):
    validate(record)
    if record.get("example", {}).get("synthetic"): raise ValueError("Synthetic example cannot be exported")
    check_source_revisions(record)
    version = record["schema_version"]
    if version not in trust["schemas"]: raise ValueError("Schema version not trusted for public export")
    if recompute(record) != record: raise ValueError("Preferred projection was modified")
    for _, field, _ in fields(record):
        for candidate in field["candidates"]:
            if any(len(e.get("original_text", "")) > 1000 for e in candidate["evidence"]):
                raise ValueError("Public evidence must be a short excerpt, not bulk source text")
    if review["decision"] != "approve" or review["model"] != trust["model"] or review["reasoning_effort"] != trust["reasoning_effort"]:
        raise ValueError("Required independent review configuration missing")
    if review.get("task_kind") == "wikidata_coordinates":
        from .coordinates import check_update
        check_update(record, review, trust, baseline)
        return
    researchers = review["research_sessions"]
    if not researchers or len(set(researchers)) != len(researchers) or not review["review_session"] or review["review_session"] in researchers:
        raise ValueError("Independent Research/Review sessions required")
    if review["facts_checked"] != sum(len(f["candidates"]) for _, f, _ in fields(record)) or review["facts_checked"] < 1:
        raise ValueError("Review does not cover all canonical facts")
    contexts = 1 + len(record.get("locations", [])) + len(record.get("related_entities", {})) + len(record.get("history", {}).get("milestones", []))
    if review["contexts_checked"] != contexts or review["source_revisions_checked"] != len(record.get("sources", {})):
        raise ValueError("Review does not cover contexts/source revisions")
    instant(review["reviewed_at"])
    if not record.get("update_datetime") or set(record["curation"].get("reviewed_groups", [])) != {"identity", "geography", "history", "population", "finance", "profile"}:
        raise ValueError("Initial pilot export requires full reviewed refresh")
    if record["record_revision"] != (1 if baseline is None else baseline["record_revision"] + 1):
        raise ValueError("Record revision does not follow its Git baseline")
    if baseline is not None:
        # The first bridge is an initial-import adapter, not an arbitrary domain
        # mutation engine. Existing records need a new explicit diff task.
        raise ValueError("Pilot import cannot overwrite existing university records")
    if review.get("attestation_kind") != "local_coordinator_verified_private_traces": raise ValueError("Unknown review attestation kind")


def check_source_revisions(record):
    """Fail closed on misleading public links to immutable Wikimedia revisions.

    The private exporter additionally replays actual captures; this public check
    validates the signed record's *claim* about the revision, not the live page.
    """
    for reference, source in record.get("sources", {}).items():
        kind = source["kind"]
        if kind not in ("wikidata", "wikipedia"):
            continue
        revision = source["revision_id"]
        url = urlsplit(source["url"])
        host = "www.wikidata.org" if kind == "wikidata" else source["language"] + ".wikipedia.org"
        if (url.scheme != "https" or url.hostname != host or url.port is not None
                or url.username is not None or url.password is not None
                or url.path != "/w/index.php" or url.query != "oldid=" + str(revision)
                or url.fragment):
            raise ValueError("Source " + reference + " URL does not bind its pinned revision")
        if kind == "wikidata" and not re.fullmatch(r"Q[1-9][0-9]*", source["source_qid"]):
            raise ValueError("Source " + reference + " has invalid Wikidata subject")
    for _, field, _ in fields(record):
        for candidate in field["candidates"]:
            for evidence in candidate["evidence"]:
                if not evidence["locator"].strip():
                    raise ValueError("Empty evidence locator")


def prepare(repo, pilot, entity_ids, batch_id, base_ref, trust, key, output, acceptance=None):
    from .pilot_audit import audit_case
    output = private_path(output); batch_id = batch_slug(batch_id); base = commit(repo, base_ref)
    ids = sorted([qid(v) for v in entity_ids], key=lambda s: int(s[1:]))
    if not ids or len(ids) != len(set(ids)) or len(ids) > trust["max_schools_per_batch"]: raise ValueError("Invalid batch school count")
    if output.exists(): raise FileExistsError("Private export output must be new; preserve prior attempts")
    files = {}; rows = []; payloads = {}
    for entity_id in ids:
        no_legacy_duplicate(repo, base, entity_id)
        record, review = audit_case(pilot, entity_id, trust)
        path = record_relative(entity_id)
        old = blob(repo, base, path, optional=True)
        baseline = load_json(old) if old is not None else None
        check_record(record, review, trust, baseline)
        schema_path = ROOT / ("schemas/university.v" + record["schema_version"] + ".schema.json")
        if sha(encode(load_json(schema_path.read_bytes()))) != trust["schemas"][record["schema_version"]]: raise ValueError("Local schema differs from trust")
        record_bytes = encode(record)
        payload = {"type": "university-review-v1", "repository": trust["repository"], "qid": entity_id,
            "base_commit": base, "record_path": path, "record_sha256": sha(record_bytes), "baseline_sha256": sha(old) if old else "absent",
            "schema_version": record["schema_version"], "schema_sha256": trust["schemas"][record["schema_version"]],
            "review_policy": trust["review_policy"], "review": review}
        receipt_path = "data/reviews/" + batch_id + "/" + entity_id + ".json"
        if blob(repo, base, receipt_path, optional=True) is not None: raise ValueError("Batch ID already used")
        receipt_bytes = encode(sign(payload, key, trust)); payloads[entity_id] = payload
        files[path] = record_bytes; files[receipt_path] = receipt_bytes
        rows.append({"qid": entity_id, "record_path": path, "record_sha256": sha(record_bytes),
            "receipt_path": receipt_path, "receipt_sha256": sha(receipt_bytes)})
    content_scope = scope(rows, payloads, trust)
    approval = acceptance or {"status": "pending", "content_scope_sha256": content_scope}
    if acceptance:
        check_acceptance(acceptance, content_scope)
    manifest = {"type": "university-batch-v1", "repository": trust["repository"], "batch_id": batch_id,
        "base_commit": base, "created_at": datetime.now(timezone.utc).isoformat(),
        "content_scope_sha256": content_scope, "acceptance": approval, "records": rows}
    manifest_path = "data/batches/" + batch_id + ".json"
    if blob(repo, base, manifest_path, optional=True) is not None: raise ValueError("Batch manifest is immutable")
    files[manifest_path] = encode(sign(manifest, key, trust))
    verify_files(repo, base, files, trust, require_acceptance=bool(acceptance))
    for relative, data in files.items():
        target = output / relative; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
    preview = {"status": "ready" if acceptance else "awaiting_human_data_acceptance", "batch_id": batch_id,
        "base_commit": base, "content_scope_sha256": content_scope, "qids": ids,
        "files": {p: sha(v) for p, v in files.items()}, "publication_allowed": bool(acceptance)}
    (output / "preview.json").write_bytes(encode(preview))
    inspection = {"status": preview["status"], "content_scope_sha256": content_scope,
        "universities": [{"qid": row["qid"], "record": load_json(files[row["record_path"]]),
            "review": payloads[row["qid"]]["review"]} for row in rows]}
    (output / "inspection.json").write_bytes(encode(inspection))
    return preview


def check_acceptance(acceptance, expected):
    if acceptance.get("status") != "accepted" or acceptance.get("content_scope_sha256") != expected:
        raise ValueError("Human acceptance must bind this exact structured-data scope")
    if not isinstance(acceptance.get("human_approval_ref"), str) or not acceptance["human_approval_ref"].strip():
        raise ValueError("Human approval reference required; code PR merge is not dataset acceptance")
    if not isinstance(acceptance.get("human_actor"), str) or not acceptance["human_actor"].strip(): raise ValueError("Human actor required")


def verify_files(repo, base, files, trust, require_acceptance=True):
    manifests = [p for p in files if re.fullmatch(r"data/batches/[a-z0-9][a-z0-9-]{0,79}\.json", p)]
    if len(manifests) != 1: raise ValueError("Exactly one new signed batch manifest required")
    raw_manifest = canonical_json(files[manifests[0]])
    if raw_manifest.get("type") == "university-native-final-v1":
        from .native_protocol import verify_final
        return verify_final(repo, base, files, trust)
    if raw_manifest.get("payload", {}).get("type") == "university-final-batch-v1":
        from .distributed_protocol import verify_final
        return verify_final(repo, base, files, trust)
    if canonical_json(files[manifests[0]]).get("type") == "university-path-migration-v1":
        from .bucket_migration import verify_migration
        return verify_migration(repo, base, files, manifests[0])
    manifest_path = manifests[0]; manifest = verify(canonical_json(files[manifest_path]), trust)
    if manifest["type"] != "university-batch-v1" or manifest["repository"] != trust["repository"] or manifest["base_commit"] != base:
        raise ValueError("Batch repository or Git baseline mismatch")
    batch_id = batch_slug(manifest["batch_id"])
    if manifest_path != "data/batches/" + batch_id + ".json": raise ValueError("Batch path mismatch")
    if blob(repo, base, manifest_path, optional=True) is not None: raise ValueError("Existing batch manifest cannot be changed")
    instant(manifest["created_at"]); rows = manifest["records"]
    ids = [row["qid"] for row in rows]
    if not rows or len(rows) > trust["max_schools_per_batch"] or len(set(ids)) != len(ids): raise ValueError("Invalid/duplicate batch membership")
    if ids != sorted(ids, key=lambda v: int(qid(v)[1:])): raise ValueError("Noncanonical batch order")
    expected_paths = {manifest_path}; receipts = {}; all_sessions = []
    for row in rows:
        entity_id = qid(row["qid"]); path = record_relative(entity_id)
        no_legacy_duplicate(repo, base, entity_id)
        receipt_path = "data/reviews/" + batch_id + "/" + entity_id + ".json"
        if row["record_path"] != path or row["receipt_path"] != receipt_path: raise ValueError("Noncanonical data path")
        expected_paths.update((path, receipt_path))
        if path not in files or receipt_path not in files: raise ValueError("Manifest file missing")
        if sha(files[path]) != row["record_sha256"] or sha(files[receipt_path]) != row["receipt_sha256"]: raise ValueError("Batch file changed")
        if blob(repo, base, receipt_path, optional=True) is not None: raise ValueError("Existing review receipt cannot be overwritten")
        record = canonical_json(files[path]); receipt = verify(canonical_json(files[receipt_path]), trust)
        if receipt["type"] != "university-review-v1" or receipt["repository"] != trust["repository"] or receipt["qid"] != entity_id or record["qid"] != entity_id:
            raise ValueError("Receipt/record identity mismatch")
        if receipt["base_commit"] != base or receipt["record_path"] != path or receipt["record_sha256"] != row["record_sha256"]:
            raise ValueError("Stale or mismatched record receipt")
        old = blob(repo, base, path, optional=True)
        if receipt["baseline_sha256"] != (sha(old) if old else "absent"): raise ValueError("Record Git baseline changed")
        version = record["schema_version"]
        if receipt["schema_version"] != version or receipt["schema_sha256"] != trust["schemas"].get(version) or receipt["review_policy"] != trust["review_policy"]:
            raise ValueError("Review bound to another schema/policy version")
        check_record(record, receipt["review"], trust, load_json(old) if old else None)
        all_sessions += receipt["review"]["research_sessions"] + [receipt["review"]["review_session"]]
        receipts[entity_id] = receipt
    if len(all_sessions) != len(set(all_sessions)): raise ValueError("Model sessions reused between schools")
    if set(files) != expected_paths: raise ValueError("Data PR includes files outside the signed approved batch")
    content_scope = scope(rows, receipts, trust)
    if content_scope != manifest["content_scope_sha256"]: raise ValueError("Content acceptance scope mismatch")
    updates = [r["review"].get("task_kind") == "wikidata_coordinates" for r in receipts.values()]
    if any(updates):
        if not all(updates) or manifest.get("task_kind") != "wikidata_coordinates":
            raise ValueError("Field updates cannot be mixed with initial imports")
        authorization = manifest.get("authorization", {})
        if authorization != {"kind": "independently_reviewed_field_update", "request_refs": sorted(set(
                r["review"]["request_ref"] for r in receipts.values()))}:
            raise ValueError("Field-update authorization mismatch")
        if "acceptance" in manifest: raise ValueError("Field update must not invent initial-data human acceptance")
    elif manifest.get("task_kind"):
        raise ValueError("Unsupported batch task kind")
    elif require_acceptance: check_acceptance(manifest["acceptance"], content_scope)
    elif manifest["acceptance"].get("status") not in ("pending", "accepted"): raise ValueError("Unknown acceptance state")
    return {"status": "validated", "batch_id": batch_id, "qids": ids, "base_commit": base,
        "content_scope_sha256": content_scope, "human_accepted": manifest.get("acceptance", {}).get("status") == "accepted",
        **({"task_kind": "wikidata_coordinates"} if all(updates) else {})}


def validate_pr(repo, base_ref, head_ref, expected_head_sha=None):
    base = commit(repo, base_ref); head = commit(repo, head_ref)
    if expected_head_sha is not None:
        if not re.fullmatch(r"[0-9a-f]{40}", expected_head_sha) or head != expected_head_sha:
            raise ValueError("Checked-out PR HEAD differs from the immutable GitHub event SHA")
    changed = git(repo, "diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--name-only", "-z", base, head).decode().split("\0")
    changed = [p for p in changed if p]
    if any(".private" in p.split("/") for p in changed): raise ValueError("Private artifacts in proposed Git tree")
    if not any(p.startswith("data/") for p in changed): return {"status": "code_only", "base_commit": base, "head_commit": head}
    if subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", base, head],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
        raise ValueError("Data PR is not based on the exact current Git baseline")
    from .distributed_protocol import trust_at
    trust = trust_at(repo, base)
    if any(p.startswith("data/seeds/") for p in changed):
        from .seed_catalog import NAMES, verify as verify_catalog
        if not set(NAMES).issubset(changed): raise ValueError("Complete signed seed catalog required")
        if any(blob(repo, base, p, optional=True, max_bytes=20_000_000) is not None for p in NAMES): raise ValueError("Initial seed catalog is immutable")
        seed_files = {p: blob(repo, head, p, max_bytes=20_000_000) for p in NAMES}
        rows = verify_catalog(seed_files, trust=trust); extra = set(changed) - set(NAMES); moved = 0
        if extra:
            from .bucket_migration import verify_migration
            manifests = [p for p in extra if re.fullmatch(r"data/batches/[a-z0-9][a-z0-9-]{0,79}\.json", p)]
            if len(manifests) != 1: raise ValueError("Seed bootstrap may include only a proven byte-preserving path migration")
            moved = verify_migration(repo, base, {p: blob(repo, head, p, optional=True) for p in extra}, manifests[0])["records_moved"]
        return {"status": "validated", "task_kind": "seed_catalog", "base_commit": base, "head_commit": head,
                "primary_count": len(rows["primary"]), "discovery_count": len(rows["discovery"]), "overlap_count": rows["overlap_count"], "records_moved": moved}
    if any(p.startswith("data/proposals/") for p in changed):
        from .distributed_protocol import inspect_draft
        manifests = [p for p in changed if p.endswith('/manifest.json') and p.startswith('data/proposals/')]
        if len(manifests) == 1 and canonical_json(blob(repo, head, manifests[0])).get('type') == 'university-native-draft-v1':
            from .native_protocol import inspect_draft as inspect_native
            inspect_native(repo, base, head, trust)
        else: inspect_draft(repo, base, head, trust)
        raise ValueError("Draft proposals are valid but unreviewed; independent Review is required before main")
    for version, expected in trust["schemas"].items():
        raw = blob(repo, base, "schemas/university.v" + version + ".schema.json")
        if sha(encode(load_json(raw))) != expected: raise ValueError("Base schema trust mismatch")
    raw_policy = blob(repo, base, "docs/review-policy-v2.md").decode().replace("\r\n", "\n")
    if sha(raw_policy.encode()) != trust["review_policy"]["sha256"]: raise ValueError("Base review-policy trust mismatch")
    files = {}
    for path in changed:
        if not re.fullmatch(r"data/(?:universities/[0-9a-f]{2,3}/Q[1-9][0-9]*|reviews/[a-z0-9][a-z0-9-]{0,79}/Q[1-9][0-9]*|batches/[a-z0-9][a-z0-9-]{0,79})\.json", path):
            raise ValueError("Mixed code/data PR or forbidden data path: " + path)
        files[path] = blob(repo, head, path, optional=True)
    result = verify_files(repo, base, files, trust)
    return {**result, "head_commit": head}


def install(repo, bundle):
    bundle = private_path(bundle); preview = load_json((bundle / "preview.json").read_bytes())
    base = commit(repo, "HEAD")
    if base != preview["base_commit"]: raise ValueError("Workspace baseline changed; prepare again")
    trust = load_json(blob(repo, base, TRUST_PATH))
    files = {}
    for path in preview["files"]:
        unresolved = bundle / path; source = unresolved.resolve()
        if not source.is_relative_to(bundle) or unresolved.is_symlink(): raise ValueError("Private bundle path escapes its root")
        files[path] = source.read_bytes()
    for path, data in files.items():
        if sha(data) != preview["files"][path]: raise ValueError("Private export bundle changed")
    result = verify_files(repo, base, files, trust)
    # Validate the complete batch before any write; a partial retry is safe only
    # when every pre-existing target has exactly the approved bytes.
    check_workspace(repo, base, files)
    for path, data in files.items():
        target = Path(repo).resolve() / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
    return {**result, "status": "installed_for_data_pr", "files": sorted(files)}


def check_workspace(repo, base, files):
    """Protect both the index and working tree; allow only exact completed retries."""
    root = Path(repo).resolve()
    for path, data in files.items():
        target = root / path
        if target.resolve() != target or not target.resolve().is_relative_to(root) or target.is_symlink():
            raise ValueError("Export path escapes workspace or crosses a symlink/junction")
        old = blob(repo, base, path, optional=True)
        entries = [e for e in git(repo, "ls-files", "--stage", "-z", "--", path).split(b"\0") if e]
        indexed = None
        if entries:
            if len(entries) != 1: raise ValueError("Unmerged index entry")
            info, name = entries[0].split(b"\t", 1); mode, oid, stage = info.split()
            if mode != b"100644" or stage != b"0" or name.decode() != path: raise ValueError("Unsafe index entry")
            indexed = git(repo, "cat-file", "blob", oid.decode())
        if indexed not in (old, data): raise ValueError("Refuse to overwrite staged work")
        if target.exists():
            if target.read_bytes() not in (old, data): raise ValueError("Refuse to overwrite uncommitted work")
        elif old is not None and data is not None:
            raise ValueError("Refuse to resurrect a locally deleted university")
