"""Storage v2: 256 buckets, with byte-preserving Git-bound path migration."""
from pathlib import Path
import hashlib
import re

from .attestations import load_json, private_path, sha
from .records import encode, qid


def paths(entity_id):
    entity_id = qid(entity_id); digest = hashlib.sha256(entity_id.encode()).hexdigest()
    prefix = "data/universities/"
    return prefix + digest[:3] + "/" + entity_id + ".json", prefix + digest[:2] + "/" + entity_id + ".json"


def migration_rows(repo, base):
    from .pr_export import git, blob, canonical_json
    names = git(repo, "ls-tree", "-r", "--name-only", base, "--", "data/universities").decode().splitlines()
    rows = []
    for name in names:
        match = re.fullmatch(r"data/universities/[0-9a-f]{2,3}/(Q[1-9][0-9]*)\.json", name)
        if not match: raise ValueError("Unexpected existing university path")
        entity_id = match[1]; old, new = paths(entity_id)
        if name == new: continue
        if name != old: raise ValueError("Wrong legacy QID bucket")
        raw = blob(repo, base, old); record = canonical_json(raw)
        if record["qid"] != entity_id: raise ValueError("Legacy record/path identity mismatch")
        if blob(repo, base, new, optional=True) is not None: raise ValueError("Duplicate old/new university records")
        rows.append({"qid": entity_id, "from": old, "to": new, "sha256": sha(raw)})
    return sorted(rows, key=lambda r: int(r["qid"][1:]))


def verify_migration(repo, base, files, manifest_path):
    from .pr_export import blob, canonical_json
    manifest = canonical_json(files[manifest_path])
    if set(manifest) != {"type", "base_commit", "from_hex_digits", "to_hex_digits", "records"}:
        raise ValueError("Unexpected path-migration fields")
    if manifest["type"] != "university-path-migration-v1" or manifest["base_commit"] != base or manifest["from_hex_digits"] != 3 or manifest["to_hex_digits"] != 2:
        raise ValueError("Unsupported/stale bucket migration")
    if blob(repo, base, manifest_path, optional=True) is not None: raise ValueError("Migration manifest is immutable")
    expected = migration_rows(repo, base)
    if not expected or manifest["records"] != expected: raise ValueError("Migration must cover every legacy record exactly")
    names = {manifest_path}
    for row in expected:
        names.update((row["from"], row["to"]))
        if files.get(row["from"], "missing") is not None: raise ValueError("Legacy file must be removed")
        if files.get(row["to"]) != blob(repo, base, row["from"]): raise ValueError("Path migration changed university bytes")
    if set(files) != names: raise ValueError("Path migration cannot change facts, receipts, code or unrelated data")
    return {"status": "validated", "task_kind": "bucket_migration", "base_commit": base,
            "qids": [r["qid"] for r in expected], "records_moved": len(expected), "bucket_count": 256}


def prepare(repo, base_ref, batch_id, output):
    from .pr_export import commit, blob, batch_slug
    output = private_path(output); batch_slug(batch_id); base = commit(repo, base_ref)
    if output.exists(): raise FileExistsError("Use a new private migration bundle")
    rows = migration_rows(repo, base)
    if not rows: raise ValueError("No legacy records to migrate")
    manifest_path = "data/batches/" + batch_id + ".json"
    manifest = {"type": "university-path-migration-v1", "base_commit": base, "from_hex_digits": 3, "to_hex_digits": 2, "records": rows}
    files = {manifest_path: encode(manifest)}
    for row in rows:
        files[row["from"]] = None; files[row["to"]] = blob(repo, base, row["from"])
    result = verify_migration(repo, base, files, manifest_path)
    output.mkdir(parents=True)
    for name, data in files.items():
        if data is None: continue
        dest = output / name; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(data)
    preview = {**result, "manifest_path": manifest_path,
        "files": {name: sha(data) for name, data in files.items() if data is not None}, "deletions": [r["from"] for r in rows]}
    (output / "preview.json").write_bytes(encode(preview))
    return preview


def stage(repo, bundle):
    from .pr_export import commit, check_workspace
    root = Path(repo).resolve(); bundle = private_path(bundle); preview = load_json((bundle / "preview.json").read_bytes())
    base = commit(repo, "HEAD")
    if base != preview["base_commit"]: raise ValueError("Stale bucket migration baseline")
    files = {name: None for name in preview["deletions"]}
    for name, expected in preview["files"].items():
        source = bundle / name
        if not source.resolve().is_relative_to(bundle) or source.is_symlink(): raise ValueError("Unsafe private bundle path")
        data = source.read_bytes()
        if sha(data) != expected: raise ValueError("Migration bundle was modified")
        files[name] = data
    result = verify_migration(repo, base, files, preview["manifest_path"])
    check_workspace(repo, base, files)
    for name, data in files.items():
        target = root / name
        if data is None:
            if target.exists(): target.unlink()
            if target.parent.exists() and not any(target.parent.iterdir()): target.parent.rmdir()
        else:
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
    return {**result, "status": "staged_for_data_pr"}
