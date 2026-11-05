"""Sign an explicitly authorized candidate catalog, then stage only that catalog."""
from pathlib import Path
from .attestations import load_json, private_path, sign, sha
from .records import encode
from .seed_catalog import NAMES, compact, verify
from .pr_export import blob, commit, check_workspace


def prepare(repo, preview, base_ref, key, output):
    preview = private_path(preview); output = private_path(output); base = commit(repo, base_ref)
    if output.exists(): raise FileExistsError("Preserve previous seed exports; use a new output")
    trust = load_json(blob(repo, base, ".curation/review-trust.json"))
    files = {name: (preview / name).read_bytes() for name in NAMES}
    verify(files)
    files[NAMES[2]] = compact(sign(load_json(files[NAMES[2]]), key, trust)) + b"\n"
    rows = verify(files, trust=trust)
    if any(blob(repo, base, p, optional=True, max_bytes=20_000_000) is not None for p in NAMES):
        raise ValueError("Seed catalog already exists; do not overwrite it")
    output.mkdir(parents=True)
    for name, data in files.items():
        target = output / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
    meta = {"base_commit": base, "files": {p: sha(v) for p, v in files.items()},
            "primary_count": len(rows["primary"]), "discovery_count": len(rows["discovery"])}
    (output / "preview.json").write_bytes(encode(meta))
    return meta


def stage(repo, bundle):
    bundle = private_path(bundle); meta = load_json((bundle / "preview.json").read_bytes()); base = commit(repo, "HEAD")
    if meta["base_commit"] != base: raise ValueError("Seed delivery baseline changed")
    if set(meta["files"]) != set(NAMES): raise ValueError("Unexpected seed export paths")
    files = {}
    for name in NAMES:
        target = bundle / name
        if target.resolve() != target or not target.resolve().is_relative_to(bundle): raise ValueError("Unsafe seed source path")
        files[name] = target.read_bytes()
        if sha(files[name]) != meta["files"][name]: raise ValueError("Seed export changed after signing")
        if blob(repo, base, name, optional=True, max_bytes=20_000_000) is not None: raise ValueError("Cannot replace an existing seed catalog")
    trust = load_json(blob(repo, base, ".curation/review-trust.json")); rows = verify(files, trust=trust)
    check_workspace(repo, base, files)
    for name, raw in files.items():
        target = Path(repo).resolve() / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
    return {"status": "staged", "primary_count": len(rows["primary"]), "discovery_count": len(rows["discovery"]), "base_commit": base}
