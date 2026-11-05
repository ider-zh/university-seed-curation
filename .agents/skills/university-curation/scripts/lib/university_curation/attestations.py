"""Operator-owned Ed25519 attestations; only public keys belong in Git."""
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

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


def init_key(path):
    path = private_path(path); path.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try: restrict_key(path)
    except Exception:
        os.close(fd); path.unlink(); raise
    with os.fdopen(fd, "wb") as stream: stream.write(raw)
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return {"key_id": "review-" + sha(public)[:16], "algorithm": "Ed25519", "public_key_hex": public.hex()}


def restrict_key(path):
    path = private_path(path)
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW
        response = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"], creationflags=flags)
        sid = next(csv.reader(response.decode(errors="replace").splitlines()))[1]
        if not sid.startswith("S-1-"): raise ValueError("Cannot resolve current Windows account SID")
        subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", "*" + sid + ":F"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=flags)
    else: path.chmod(0o600)


def sign(payload, key_path, trust):
    key = serialization.load_pem_private_key(private_path(key_path).read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey): raise ValueError("Ed25519 key required")
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    key_id = "review-" + sha(bytes.fromhex(public))[:16]
    entry = trust["keys"].get(key_id, {})
    if entry.get("status") != "active" or entry.get("public_key_hex") != public:
        raise ValueError("Signing key not trusted")
    return {"payload": payload, "key_id": key_id, "signature_hex": key.sign(DOMAIN + encode(payload)).hex()}


def verify(document, trust):
    if set(document) != {"payload", "key_id", "signature_hex"}: raise ValueError("Invalid signed envelope")
    entry = trust["keys"].get(document["key_id"], {})
    if entry.get("status") != "active": raise ValueError("Unknown/revoked reviewer key")
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(entry["public_key_hex"]))
        key.verify(bytes.fromhex(document["signature_hex"]), DOMAIN + encode(document["payload"]))
    except (InvalidSignature, KeyError, ValueError) as error:
        raise ValueError("Invalid review signature") from error
    return document["payload"]


def policy(root, public_key, repository):
    root = Path(root)
    return {"version": 1, "repository": repository, "max_schools_per_batch": 5,
        "schemas": {"0.2.1": sha(encode(load_json((root / "schemas/university.v0.2.1.schema.json").read_bytes())))},
        "review_policy": {"id": "source-grounded-flexible-v2", "sha256": sha((root / "docs/review-policy-v2.md").read_text(encoding="utf-8").encode())},
        "model": "gpt-6.1-terra", "reasoning_effort": "medium",
        "keys": {public_key["key_id"]: {"algorithm": "Ed25519", "public_key_hex": public_key["public_key_hex"], "status": "active"}}}
