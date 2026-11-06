"""Canonical hashes, private paths and read-only verification of the signed seed catalog."""
import hashlib
import json
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .records import encode

DOMAIN = b"university-curation-attestation-v1\x00"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result
    def nonfinite(value): raise ValueError("Nonfinite JSON value: " + value)
    return json.loads(data, object_pairs_hook=unique, parse_constant=nonfinite)


def private_path(path):
    path = Path(path).resolve()
    if ".private" not in path.parts: raise ValueError("Private artifacts must stay under .private")
    return path


def verify_catalog_signature(document, trust):
    if set(document) != {"payload", "key_id", "signature_hex"}: raise ValueError("Invalid signed envelope")
    entry = trust["keys"].get(document["key_id"], {})
    if entry.get("status") != "active": raise ValueError("Unknown/revoked catalog key")
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(entry["public_key_hex"]))
        key.verify(bytes.fromhex(document["signature_hex"]), DOMAIN + encode(document["payload"]))
    except (InvalidSignature, KeyError, ValueError) as error:
        raise ValueError("Invalid catalog signature") from error
    return document["payload"]
