"""Compact, independently verifiable candidate catalog; no school facts are accepted here."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from . import attestations

ROOT = "data/seeds/"
NAMES = (ROOT + "primary.json", ROOT + "discovery.json", ROOT + "manifest.json")
AUTH = {"status": "accepted", "scope": "seed candidate-list import only; not factual acceptance", "actor": "ider-zh", "approval_ref": "operator:2026-11-05:import-seed-list-into-university-seed-curation"}
SOURCES = {
    "primary": {"sha256": "4d962f20e31faf4d721879ba9afc9d32d192b34d64118341fcf4ec1d9fd90e09", "manifest_sha256": "26eb9244df103cb9f536271f2264e6493e097d66747725c591deb7ba885e4d1e", "count": 39489},
    "discovery": {"sha256": "264005432afb805ddae0b6e9adf2b4994e0fe6b3ac6f8ca19cf5eb5fc2f2c5ba", "manifest_sha256": "e674289505ed3e58f009de1337134294d95887bb819b77be054b7fd41b73cb27", "count": 64667},
}
QID = re.compile(r"Q[1-9][0-9]*\Z")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def number(qid):
    if not isinstance(qid, str) or not QID.fullmatch(qid):
        raise ValueError("Invalid QID")
    return int(qid[1:])


def compact(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def encode_rows(rows):
    return b"[\n" + b",\n".join(compact(row) for row in rows) + b"\n]\n"


def _strings(values, qids=False):
    if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v for v in values):
        raise ValueError("Expected nonempty string array")
    if len(values) != len(set(values)):
        raise ValueError("Duplicate array value")
    if qids:
        for value in values: number(value)
    return values


def _check_rows(rows, kind):
    previous = 0
    for row in rows:
        if not isinstance(row, dict): raise ValueError("Invalid seed row")
        allowed = {"qid", "screening_status", "channels"} if kind == "primary" else {"qid", "legacy_types"}
        if set(row) != allowed: raise ValueError("Unexpected seed fields")
        n = number(row["qid"])
        if n <= previous: raise ValueError("Seed QIDs must be unique and numerically sorted")
        previous = n
        if kind == "primary":
            if row["screening_status"] not in {"included", "needs_review"}: raise ValueError("Invalid screening status")
            _strings(row["channels"])
        else: _strings(row["legacy_types"], qids=True)


def build(primary, discovery, source_manifest, legacy_manifest, output_dir):
    """Build an unsigned private preview from exactly the authorized input snapshots."""
    inputs = {"primary": (Path(primary), Path(source_manifest)), "discovery": (Path(discovery), Path(legacy_manifest))}
    for kind, (path, manifest) in inputs.items():
        if digest(path.read_bytes()) != SOURCES[kind]["sha256"] or digest(manifest.read_bytes()) != SOURCES[kind]["manifest_sha256"]:
            raise ValueError("Input snapshot or source manifest hash mismatch: " + kind)
    import pyarrow.parquet as pq
    p = pq.read_table(primary, columns=["qid", "classification", "discovery"]).to_pylist()
    d = pq.read_table(discovery, columns=["qid", "legacy_types"]).to_pylist()
    primary_rows = [{"qid": x["qid"], "screening_status": x["classification"]["screening_status"], "channels": sorted(x["discovery"]["channels"])} for x in p]
    discovery_rows = [{"qid": x["qid"], "legacy_types": sorted(x["legacy_types"], key=number)} for x in d]
    projected = {}
    for kind, rows, name in zip(("primary", "discovery"), (primary_rows, discovery_rows), NAMES):
        rows.sort(key=lambda x: number(x["qid"]))
        _check_rows(rows, kind)
        if len(rows) != SOURCES[kind]["count"]: raise ValueError("Input count mismatch: " + kind)
        projected[name] = encode_rows(rows)
    payload = {"version": 1, "format": "utf8-json-array-one-canonical-object-per-line-v1", "sources": SOURCES, "acceptance": AUTH,
               "lists": {kind: {"path": name, "sha256": digest(projected[name]), "count": len(rows)} for kind, name, rows in (("primary", NAMES[0], primary_rows), ("discovery", NAMES[1], discovery_rows))}}
    projected[NAMES[2]] = compact(payload) + b"\n"
    verify(projected)
    output = Path(output_dir).resolve()
    if ".private" not in output.parts: raise ValueError("Preview must be under .private")
    for name, data in projected.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != data: raise ValueError("Preview would overwrite different file: " + str(path))
        path.write_bytes(data)
    return payload


def verify(files, base_files=None, trust=None):
    """Validate projected bytes; with base trust require a signed manifest envelope."""
    del base_files
    if any(name not in files for name in NAMES): raise ValueError("Missing seed catalog file")
    manifest = attestations.load_json(files[NAMES[2]])
    if trust is not None:
        manifest = attestations.verify(manifest, trust)
    elif isinstance(manifest, dict) and "payload" in manifest:
        raise ValueError("Trust required to verify signed catalog")
    if not isinstance(manifest, dict) or set(manifest) != {"version", "format", "sources", "acceptance", "lists"}: raise ValueError("Invalid catalog manifest")
    if manifest["version"] != 1 or manifest["format"] != "utf8-json-array-one-canonical-object-per-line-v1" or manifest["sources"] != SOURCES or manifest["acceptance"] != AUTH:
        raise ValueError("Unrecognized source or acceptance")
    if set(manifest["lists"]) != {"primary", "discovery"}: raise ValueError("Invalid lists")
    result = {}
    ids = {}
    for kind, name in zip(("primary", "discovery"), NAMES):
        data = files[name]
        if len(data) > 20_000_000: raise ValueError("Catalog list too large")
        rows = attestations.load_json(data)
        if not isinstance(rows, list) or encode_rows(rows) != data: raise ValueError("Noncanonical catalog list")
        _check_rows(rows, kind)
        if manifest["lists"][kind] != {"path": name, "sha256": digest(data), "count": len(rows)} or len(rows) != SOURCES[kind]["count"]:
            raise ValueError("Catalog hash or count mismatch")
        ids[kind] = {row["qid"] for row in rows}
        result[kind] = rows
    result["overlap_count"] = len(ids["primary"] & ids["discovery"])
    return result


def load_catalog(repo, preview=False):
    repo = Path(repo)
    files = {name: (repo / name).read_bytes() for name in NAMES}
    trust = None if preview else attestations.load_json((repo / ".curation/review-trust.json").read_bytes())
    rows = verify(files, trust=trust)
    catalog = {row["qid"]: {**row, "queue_kind": "discovery"} for row in rows["discovery"]}
    catalog.update({row["qid"]: {**row, "queue_kind": "primary"} for row in rows["primary"]})
    return catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="build unsigned private preview")
    for arg in ("primary", "discovery", "source-manifest", "legacy-manifest", "output-dir"): b.add_argument("--" + arg, required=True)
    v = sub.add_parser("verify", help="verify signed catalog using repository trust")
    v.add_argument("--repo", required=True)
    args = parser.parse_args()
    if args.command == "build": print(json.dumps(build(args.primary, args.discovery, args.source_manifest, args.legacy_manifest, args.output_dir), indent=2))
    else: print(json.dumps({"count": len(load_catalog(args.repo))}))
