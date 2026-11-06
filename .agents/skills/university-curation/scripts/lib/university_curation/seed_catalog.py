"""Compact, independently verifiable candidate catalog; no school facts are accepted here."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from . import integrity

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


def verify(files, base_files=None, trust=None):
    """Validate projected bytes; with base trust require a signed manifest envelope."""
    del base_files
    if any(name not in files for name in NAMES): raise ValueError("Missing seed catalog file")
    manifest = integrity.load_json(files[NAMES[2]])
    if trust is not None:
        manifest = integrity.verify_catalog_signature(manifest, trust)
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
        rows = integrity.load_json(data)
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
    trust = None if preview else integrity.load_json((repo / ".curation/review-trust.json").read_bytes())
    rows = verify(files, trust=trust)
    catalog = {row["qid"]: {**row, "queue_kind": "discovery"} for row in rows["discovery"]}
    catalog.update({row["qid"]: {**row, "queue_kind": "primary"} for row in rows["primary"]})
    return catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("verify", help="verify signed catalog using repository trust")
    v.add_argument("--repo", required=True)
    args = parser.parse_args()
    print(json.dumps({"count": len(load_catalog(args.repo))}))
