"""Propose one independently held role public key for human review."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .attestations import init_key, load_json, private_path, sha
from .records import encode
from .pr_export import blob, commit
from .distributed_protocol import trust_at


def _git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    return result.stdout


def _public(path):
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey): raise ValueError("Ed25519 key required")
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return "review-" + sha(raw)[:16], raw.hex()


def _validate_branch(repo, base, head, path, descriptor):
    ancestor = _git(repo, "merge-base", base, head).decode().strip()
    if _git(repo, "diff", "--name-only", ancestor, head, "--").decode().splitlines() != [path]: raise ValueError("Registration branch must change only its role descriptor")
    if blob(repo, ancestor, path, optional=True) is not None or blob(repo, head, path) != encode(descriptor): raise ValueError("Invalid role descriptor registration")
    # Reject use of a key already registered to any role or legacy coordinator.
    if descriptor["key_id"] in trust_at(repo, ancestor)["keys"]: raise ValueError("Signing key already registered for another role")


def register(repo, key_path, role, client, private_root):
    if role not in ("research", "review"): raise ValueError("Invalid role")
    repo, key_path, private_root = Path(repo).resolve(), private_path(key_path), private_path(private_root)
    if not key_path.exists(): init_key(key_path)
    key_id, public = _public(key_path)
    _git(repo, "fetch", "origin", "main")
    base = commit(repo, "origin/main"); trust = trust_at(repo, base)
    origin = _git(repo, "remote", "get-url", "origin").decode().strip().removesuffix(".git")
    repository = trust["repository"]
    if origin not in ("https://github.com/" + repository, "git@github.com:" + repository) or getattr(client, "repository", None) != repository: raise ValueError("Origin/client repository mismatch")
    descriptor = {"key_id": key_id, "algorithm": "Ed25519", "public_key_hex": public, "status": "active", "role": role}
    existing = trust["keys"].get(key_id)
    if existing is not None:
        if existing != {"algorithm": "Ed25519", "public_key_hex": public, "status": "active", "roles": [role]}: raise ValueError("Key revoked, mismatched, or already belongs to another role")
        return {"status": "already_trusted", "key_id": key_id}
    branch = "codex/register-" + role + "-" + key_id
    path = ".curation/roles/" + role + "/" + key_id + ".json"
    worktree = private_root / "role-registration-worktrees" / (role + "-" + key_id)
    if key_path == worktree or worktree in key_path.parents: raise ValueError("Private key cannot be inside the registration worktree")
    journal = private_root / "role-registration" / (role + "-" + key_id + ".json")
    journal.parent.mkdir(parents=True, exist_ok=True)
    metadata = {"key_id": key_id, "role": role, "branch": branch, "repository": repository}
    if journal.exists() and load_json(journal.read_bytes()) != metadata: raise ValueError("Registration journal mismatch")
    fd, temporary = tempfile.mkstemp(dir=journal.parent, prefix="role-registration-")
    try:
        with os.fdopen(fd, "wb") as stream: stream.write(encode(metadata))
        os.replace(temporary, journal)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
    pulls = [p for p in client.find_branch(branch) if p.get("state") == "open"]
    if len(pulls) > 1: raise ValueError("Multiple registration PRs")
    remote = _git(repo, "ls-remote", "--heads", "origin", "refs/heads/" + branch).decode().strip()
    if remote:
        _git(repo, "fetch", "origin", "refs/heads/" + branch + ":refs/remotes/origin/" + branch)
        head = commit(repo, "refs/remotes/origin/" + branch); _validate_branch(repo, base, head, path, descriptor)
        if pulls:
            pull = pulls[0]
            if pull["head"]["sha"] != head or pull["base"]["ref"] != "main": raise ValueError("Registration PR head/base mismatch")
            return {"status": "registration_pr_open", "key_id": key_id, "pr_url": pull["html_url"]}
        pull = client.create(branch, "Register " + role + " role key", "Registers a role public key; human approval is required. No university data is published.")
        return {"status": "registration_pr_open", "key_id": key_id, "pr_url": pull["html_url"]}
    if pulls: raise ValueError("Registration PR branch is unavailable")
    if worktree.exists():
        if _git(worktree, "branch", "--show-current").decode().strip() != branch: raise ValueError("Unexpected registration worktree")
        head = commit(worktree, "HEAD")
        dirty = _git(worktree, "status", "--porcelain", "--untracked-files=all").decode().splitlines()
        if head != base:
            if dirty: raise ValueError("Dirty registration worktree")
            _validate_branch(repo, base, head, path, descriptor)
        elif any(line[3:] != path for line in dirty): raise ValueError("Dirty registration worktree")
    else:
        worktree.parent.mkdir(parents=True, exist_ok=True)
        _git(repo, "worktree", "add", "-b", branch, str(worktree), base); head = base
    if head == base:
        target = worktree / path; target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != encode(descriptor): raise ValueError("Unexpected role descriptor")
        target.write_bytes(encode(descriptor)); _git(worktree, "add", "--", path)
        _git(worktree, "-c", "user.name=University Research Agent", "-c", "user.email=research-agent@users.noreply.github.com", "commit", "-m", "Register " + role + " role key")
        head = commit(worktree, "HEAD")
    _validate_branch(repo, base, head, path, descriptor)
    _git(worktree, "push", "-u", "origin", branch)
    pull = client.create(branch, "Register " + role + " role key", "Registers a role public key; human approval is required. No university data is published.")
    return {"status": "registration_pr_open", "key_id": key_id, "pr_url": pull["html_url"]}
