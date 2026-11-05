"""Stable QID paths, omission semantics, field contracts and guarded record writes."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import re
import tempfile

ROOT = next(parent for parent in Path(__file__).resolve().parents
            if (parent / "pyproject.toml").is_file() and (parent / "schemas").is_dir())
SCHEMA_VERSION = "0.1.0"
GROUPS = ("identity", "geography", "history", "population", "finance", "profile")


def qid(value):
    if not isinstance(value, str) or not re.fullmatch(r"Q[1-9][0-9]*", value):
        raise ValueError("Expected a canonical QID")
    return value


def record_path(workspace, entity_id):
    entity_id = qid(entity_id)
    bucket = hashlib.sha256(entity_id.encode("utf-8")).hexdigest()[:2]
    return Path(workspace).resolve() / "data" / "universities" / bucket / (entity_id + ".json")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def instant(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Datetime must have a timezone")
    return stamp.astimezone(timezone.utc)


@lru_cache(maxsize=1)
def contracts():
    import jsonschema
    schema = read(ROOT / "schemas" / "university.v0.1.schema.json")
    fields = read(ROOT / "schemas" / "fields.v0.1.json")["fields"]
    checker = jsonschema.FormatChecker()
    return (jsonschema.Draft202012Validator(schema, format_checker=checker), fields,
            {key: jsonschema.Draft202012Validator(value["value_schema"], format_checker=checker) for key, value in fields.items()})


def validate(record):
    if record.get("schema_version") in ("0.2.0", "0.2.1", "0.2.2"):
        from .preferred import validate as validate_v02
        return validate_v02(record)
    validator, fields, value_validators = contracts()
    def no_missing_placeholders(value, path="$"):
        if value is None:
            raise ValueError("Missing fields must be omitted, not null: " + path)
        if isinstance(value, str) and not value.strip():
            raise ValueError("Empty strings are not missing-value markers: " + path)
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Nonfinite values are not JSON data: " + path)
        if isinstance(value, dict):
            for key, child in value.items(): no_missing_placeholders(child, path + "." + key)
        elif isinstance(value, list):
            for i, child in enumerate(value): no_missing_placeholders(child, path + "[" + str(i) + "]")
    no_missing_placeholders(record)
    validator.validate(record)
    qid(record["qid"])
    sources = record.get("sources", {})
    ids = set()
    for claim in record.get("claims", []):
        if claim["id"] in ids: raise ValueError("Duplicate fact ID")
        ids.add(claim["id"])
        field = fields.get(claim["field"])
        if field is None: raise ValueError("Unregistered field: " + claim["field"])
        if not set(claim["source_refs"]) <= sources.keys(): raise ValueError("Missing source reference")
        if claim.get("subject_qid", record["qid"]) != record["qid"]:
            raise ValueError("Initial contract stores facts on their actual QID; use a relation for linked subjects")
        if claim["value_state"] == "known":
            value_validators[claim["field"]].validate(claim["value"])
            if isinstance(claim["value"], dict) and claim["value"].get("precision") == "range":
                if claim["value"]["minimum"] > claim["value"]["maximum"]: raise ValueError("Reversed observation range")
        elif "value" in claim: raise ValueError("Non-value source state cannot carry a fabricated value")
    for name in ("update_datetime", "modified_datetime"):
        if name in record: instant(record[name])
    if "update_datetime" in record:
        if record["curation"]["identity_status"] not in ("in_scope", "related", "excluded"):
            raise ValueError("Unresolved identity cannot complete a university refresh")
        if set(record["curation"].get("reviewed_groups", [])) != set(GROUPS):
            raise ValueError("University refresh timestamp requires all configured profile groups reviewed")
        if record["curation"].get("refresh_profile") != "core-v1":
            raise ValueError("Refresh timestamp must identify the reviewed profile")


@contextmanager
def exclusive(path):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(path.suffix + ".lock")
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, str(os.getpid()).encode()); os.close(fd); yield
    finally:
        lock.unlink()


def _replace(path, value):
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".part", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encode(value)); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if Path(name).exists(): Path(name).unlink()


def create(workspace, record):
    """Create once; import policy/publication gate is owned by the calling script."""
    validate(record)
    if record.get("example", {}).get("synthetic"): raise ValueError("Synthetic examples cannot enter the university record tree")
    path = record_path(workspace, record["qid"])
    with exclusive(path):
        if path.exists():
            if read(path) == record: return "unchanged"
            raise FileExistsError("Initialization must not overwrite an existing institution")
        _replace(path, record)
    return "created"


def apply_reviewed(workspace, candidate, expected_digest, receipt):
    """Local CAS primitive; public PR construction still requires trusted attestation."""
    validate(candidate)
    if candidate.get("example", {}).get("synthetic"): raise ValueError("Synthetic examples cannot update university records")
    if receipt.get("decision") != "approve" or receipt.get("candidate_digest") != digest(candidate):
        raise ValueError("Approval is missing or binds another candidate")
    if receipt.get("base_digest") != expected_digest or receipt.get("qid") != candidate["qid"]:
        raise ValueError("Approval binds another baseline/QID")
    if receipt.get("research_session") == receipt.get("review_session") or not receipt.get("review_session"):
        raise ValueError("Independent review session required")
    if receipt.get("research_actor") == receipt.get("review_actor") or not receipt.get("review_actor"):
        raise ValueError("Independent reviewer required")
    path = record_path(workspace, candidate["qid"])
    with exclusive(path):
        current = read(path)
        if digest(current) == digest(candidate): return "unchanged"
        if digest(current) != expected_digest: raise ValueError("Stale record baseline; rebase and review affected facts")
        if candidate["record_revision"] != current["record_revision"] + 1: raise ValueError("Incorrect record revision")
        _replace(path, candidate)
    return "applied"


def initial(seed, import_id):
    record = {"schema_version": SCHEMA_VERSION, "qid": qid(seed["qid"]), "record_revision": 1,
        "curation": {"identity_status": "pending"},
        "seed": {"import_id": import_id, "screening_status": seed["classification"]["screening_status"],
                 "channels": seed["discovery"]["channels"]}}
    if seed.get("labels"):
        record["seed"]["labels"] = {v["language"]: v["value"] for v in seed["labels"] if v["value"].strip()}
    if seed.get("source", {}).get("revision_id"):
        record["seed"]["source_revision"] = seed["source"]["revision_id"]
    return record


def proposal(current, changes, allowed_groups=GROUPS):
    """Apply a compact research diff privately; never overwrite the current record."""
    if current.get("schema_version") != "0.1.0":
        raise ValueError("Domain v0.2 incremental updates are not implemented; the initial-import export adapter cannot overwrite records")
    allowed = {"identity_status", "new_sources", "new_claims", "withdraw_claim_ids", "coverage"}
    if not isinstance(changes, dict) or not set(changes) <= allowed: raise ValueError("Unknown proposal operation")
    result = deepcopy(current); fields = contracts()[1]
    existing_sources = result.setdefault("sources", {})
    for key, value in changes.get("new_sources", {}).items():
        if key in existing_sources and existing_sources[key] != value: raise ValueError("Existing source cannot be overwritten")
        existing_sources[key] = value
    claims = result.setdefault("claims", []); next_id = max((int(c["id"][1:]) for c in claims), default=0) + 1
    for value in changes.get("new_claims", []):
        if "id" in value: raise ValueError("Fact IDs are allocated by scripts")
        if value.get("field") not in fields or fields[value["field"]]["group"] not in allowed_groups:
            raise ValueError("Field outside task contract")
        claims.append({**deepcopy(value), "id": "c" + str(next_id)}); next_id += 1
    withdraw = set(changes.get("withdraw_claim_ids", []))
    if not withdraw <= {c["id"] for c in current.get("claims", [])}: raise ValueError("Unknown fact withdrawal")
    for claim in claims:
        if claim["id"] in withdraw:
            if fields[claim["field"]]["group"] not in allowed_groups: raise ValueError("Withdrawal outside task contract")
            claim["status"] = "withdrawn"
    if "identity_status" in changes:
        if "identity" not in allowed_groups: raise ValueError("Identity outside task contract")
        result["curation"]["identity_status"] = changes["identity_status"]
    if not set(changes.get("coverage", {})) <= set(allowed_groups): raise ValueError("Coverage outside task contract")
    if changes.get("coverage"): result.setdefault("coverage", {}).update(deepcopy(changes["coverage"]))
    if not existing_sources: result.pop("sources", None)
    if not claims: result.pop("claims", None)
    validate(result)
    return {"qid": current["qid"], "base_digest": digest(current), "candidate": result,
            "changed_claim_ids": [c["id"] for c in claims if c["id"] in withdraw or int(c["id"][1:]) >= max((int(x["id"][1:]) for x in current.get("claims", [])), default=0) + 1],
            "allowed_groups": list(allowed_groups)}


def finish_candidate(current, proposed, timestamp, task_kind, reviewed_groups):
    """Dates/revisions are script-owned; a partial task cannot postpone full refresh."""
    instant(timestamp); candidate = deepcopy(proposed)
    if candidate["qid"] != current["qid"]: raise ValueError("QID cannot change")
    candidate["record_revision"] = current["record_revision"] + 1
    candidate["modified_datetime"] = timestamp
    if task_kind == "university_refresh":
        if set(reviewed_groups) != set(GROUPS): raise ValueError("Full refresh coverage incomplete")
        candidate["update_datetime"] = timestamp
        candidate["curation"]["reviewed_groups"] = list(GROUPS)
        candidate["curation"]["refresh_profile"] = "core-v1"
    elif candidate.get("update_datetime") != current.get("update_datetime"):
        raise ValueError("Partial/batch update cannot reset university refresh time")
    validate(candidate); return candidate
