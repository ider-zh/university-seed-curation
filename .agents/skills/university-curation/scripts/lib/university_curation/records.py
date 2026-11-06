"""QID paths, canonical JSON and timestamps shared by the native workflow."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = next(parent for parent in Path(__file__).resolve().parents
            if (parent / "pyproject.toml").is_file() and (parent / "schemas").is_dir())
CURRENT_SCHEMA_VERSION = "0.2.2"
GROUPS = ("identity", "geography", "history", "population", "finance", "profile")


def qid(value):
    if not isinstance(value, str) or not re.fullmatch(r"Q[1-9][0-9]*", value):
        raise ValueError("Expected a canonical QID")
    return value


def record_path(workspace, entity_id):
    entity_id = qid(entity_id)
    bucket = hashlib.sha256(entity_id.encode("utf-8")).hexdigest()[:2]
    return Path(workspace).resolve() / "data" / "universities" / bucket / (entity_id + ".json")


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def instant(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Datetime must have a timezone")
    return stamp.astimezone(timezone.utc)
