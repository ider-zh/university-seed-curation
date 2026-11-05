"""Independent main-based Draft/final PR trees and signed Review comments."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import subprocess
import uuid

from .attestations import load_json, sha, sign, verify, private_path
from .records import encode
from .pr_export import git, blob, commit, batch_slug, record_relative, check_workspace
from .distributed_protocol import (trust_at, catalog_at, check_proposal, attach_transport, inspect_draft,
                                   signed_comment, read_reviews, check_decision, verify_final, baseline_at)


def now(): return datetime.now(timezone.utc).isoformat()


def command(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}).stdout


def fetch_main(repo): command(repo, "fetch", "origin", "main"); return commit(repo, "origin/main")


def fetch_pull(repo, number, expected=None):
    command(repo, "fetch", "origin", "refs/pull/" + str(int(number)) + "/head")
    head = commit(repo, "FETCH_HEAD")
    if expected is not None and head != expected: raise ValueError("PR head changed during retrieval")
    return head


def draft_snapshot(repo, head, trust):
    paths = command(repo, "ls-tree", "-r", "--name-only", head, "--", "data/proposals").decode().splitlines()
    manifests = [p for p in paths if p.endswith("/manifest.json")]
    if len(manifests) != 1: raise ValueError("One Draft manifest required")
    payload = verify(load_json(blob(repo, head, manifests[0])), trust, role="research")
    return inspect_draft(repo, payload["base_commit"], head, trust)


def final_snapshot(repo, head, trust, batch):
    batch_slug(batch); name = "data/batches/" + batch + ".json"
    manifest = verify(load_json(blob(repo, head, name)), trust, role="research")
    if manifest.get("type") != "university-final-batch-v1" or manifest.get("batch_id") != batch: raise ValueError("Final batch identity mismatch")
    names = {name}
    for row in manifest["records"]: names.update((row["record_path"], row["receipt_path"]))
    changed = {p for p in git(repo, "diff", "--no-renames", "--name-only", "-z", manifest["base_commit"], head).decode().split("\0") if p}
    if changed != names: raise ValueError("Final branch has unrelated code/data changes")
    files = {p: blob(repo, head, p) for p in names}; verify_final(repo, manifest["base_commit"], files, trust)
    proposals = {}; decisions = {}
    for row in manifest["records"]:
        receipt = load_json(files[row["receipt_path"]]); proposals[row["qid"]] = receipt["research"]; decisions[row["qid"]] = receipt["review"]
    return manifest, proposals, decisions


def proposal_snapshot(repo, pull, trust):
    head = pull["head"]["sha"]; branch = pull["head"]["ref"]
    if not branch.startswith("codex/university-"): raise ValueError("Not a university data branch")
    batch = batch_slug(branch.removeprefix("codex/university-"))
    if blob(repo, head, "data/proposals/" + batch + "/manifest.json", optional=True) is not None:
        manifest, proposals = draft_snapshot(repo, head, trust); return "draft", manifest, proposals, {}
    manifest, proposals, decisions = final_snapshot(repo, head, trust, batch)
    return "final", manifest, proposals, decisions


def ensure_origin(repo, repository):
    origin = command(repo, "remote", "get-url", "origin").decode().strip().removesuffix(".git")
    if origin not in ("https://github.com/" + repository, "git@github.com:" + repository): raise ValueError("Origin must match configured GitHub repository")


def worktree(repo, base, private_root, local_branch):
    path = private_path(Path(private_root) / (local_branch.replace("/", "-") + "-" + uuid.uuid4().hex[:8]))
    path.parent.mkdir(parents=True, exist_ok=True)
    command(repo, "worktree", "add", "-b", local_branch, str(path), base)
    return path


def commit_files(repo, base, files, private_root, message):
    branch = "codex/build-" + uuid.uuid4().hex[:20]; tree = worktree(repo, base, private_root, branch)
    check_workspace(tree, base, files)
    for path, raw in files.items():
        target = tree / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
    command(tree, "add", "--", "data")
    command(tree, "-c", "user.name=University Research Agent", "-c", "user.email=research-agent@users.noreply.github.com", "commit", "-m", message)
    return tree, commit(tree, "HEAD")


def draft_files(repo, base, proposals, batch, key):
    batch_slug(batch); trust = trust_at(repo, base); catalog, catalog_hash = catalog_at(repo, base, trust)
    if not 1 <= len(proposals) <= trust["max_schools_per_batch"]: raise ValueError("At most five schools per Draft PR")
    files = {}; rows = []; seen = set()
    for item in sorted(proposals, key=lambda p: int(p.get("payload", p)["qid"][1:])):
        existing = "payload" in item
        proposal = verify(item, trust, role="research") if existing else item
        qid = proposal["qid"]
        if qid in seen: raise ValueError("Duplicate school")
        seen.add(qid); baseline, _ = baseline_at(repo, base, qid)
        if not existing: proposal = attach_transport(proposal, trust["repository"], base, catalog_hash, trust)
        check_proposal(proposal, baseline, catalog, catalog_hash, trust)
        path = "data/proposals/" + batch + "/" + qid + ".json"
        raw = encode(item if existing else sign(proposal, key, trust, role="research")); files[path] = raw
        rows.append({"qid": qid, "path": path, "sha256": sha(raw)})
    manifest = {"type": "university-draft-batch-v1", "repository": trust["repository"], "batch_id": batch,
                "base_commit": base, "seed_catalog_sha256": catalog_hash, "records": rows}
    files["data/proposals/" + batch + "/manifest.json"] = encode(sign(manifest, key, trust, role="research"))
    return files


def publish_draft(repo, proposals, key, client, private_root, batch=None, pull=None):
    base = fetch_main(repo); trust = trust_at(repo, base); ensure_origin(repo, trust["repository"])
    if client.repository != trust["repository"]: raise ValueError("Wrong GitHub client repository")
    batch = batch or "batch-" + uuid.uuid4().hex[:20]; files = draft_files(repo, base, proposals, batch, key)
    tree, head = commit_files(repo, base, files, private_root, "Propose university batch " + batch)
    inspect_draft(repo, base, head, trust)
    branch = pull["head"]["ref"] if pull else "codex/university-" + batch
    if pull:
        if pull["base"]["ref"] != "main" or pull["head"]["repo"]["full_name"] != client.repository: raise ValueError("PR must target main in this repository")
        command(tree, "push", "--force-with-lease=refs/heads/" + branch + ":" + pull["head"]["sha"], "origin", head + ":refs/heads/" + branch)
        if not pull.get("draft", False): client.set_draft(client.pull(pull["number"]), True)
        return client.pull(pull["number"])
    command(tree, "push", "origin", head + ":refs/heads/" + branch)
    body = ("Unreviewed structured university proposals. Source caches, model logs and private keys remain local.\n\n"
            "Independent role-signed Review is required before main can receive canonical school records.\n\n"
            "<!-- university-batch " + batch + " -->")
    return client.create(branch, "Research " + ", ".join(p.get("payload", p)["qid"] for p in proposals), body, draft=True)


def comments(client, number):
    result = []
    for page in range(1, 11):
        rows = client.request("GET", "/issues/" + str(int(number)) + "/comments?per_page=100&page=" + str(page))
        result += rows
        if len(rows) < 100: return result
    raise RuntimeError("Review discussion too large to safely enumerate")


def submit_decision(proposal_document, verdict, key, client, pull, trust):
    proposal = verify(proposal_document, trust, role="research")
    value = dict(verdict)
    for index, request in enumerate(value.get("requests", [])):
        request["request_id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, sha(encode({"proposal": value["proposal_sha256"], "session": value["review_session"], "index": index, "request": request}))))
    value.update({"type": "university-review-decision-v1", "repository": trust["repository"], "pr_number": pull["number"],
                  "reviewed_head_sha": pull["head"]["sha"], "policy": trust["review_policy"], "schema_sha256": trust["schemas"]["0.2.2"]})
    doc = sign(value, key, trust, role="review")
    if doc["key_id"] == proposal_document["key_id"]: raise ValueError("Independent role keys required")
    if client.pull(pull["number"])["head"]["sha"] != pull["head"]["sha"]: raise ValueError("Review head became stale; no comment posted")
    result = client.request("POST", "/issues/" + str(pull["number"]) + "/comments", {"body": signed_comment(doc)})
    if verdict["decision"] != "approve" and not pull.get("draft", False): client.set_draft(client.pull(pull["number"]), True)
    return {"document": doc, "comment_id": result["id"], "comment_url": result.get("html_url", "")}


def finalized_files(repo, base, batch, proposals, decisions, key, trust):
    catalog, catalog_hash = catalog_at(repo, base, trust); files = {}; rows = []
    for qid, proposal_doc in sorted(proposals.items(), key=lambda x: int(x[0][1:])):
        proposal = verify(proposal_doc, trust, role="research"); baseline, _ = baseline_at(repo, base, qid)
        check_proposal(proposal, baseline, catalog, catalog_hash, trust)
        if qid not in decisions: raise ValueError("Review is still pending for " + qid)
        verdict, record = check_decision(decisions[qid], proposal_doc, baseline, trust)
        if verdict["decision"] != "approve" or record is None: raise ValueError("School still has unresolved Review objections")
        path = record_relative(qid); receipt_path = "data/reviews/" + batch + "/" + qid + ".json"
        files[path] = encode(record)
        files[receipt_path] = encode({"type": "university-distributed-receipt-v1", "research": proposal_doc, "review": decisions[qid]})
        rows.append({"qid": qid, "record_path": path, "record_sha256": sha(files[path]), "receipt_path": receipt_path, "receipt_sha256": sha(files[receipt_path])})
    manifest = {"type": "university-final-batch-v1", "repository": trust["repository"], "batch_id": batch,
                "base_commit": base, "seed_catalog_sha256": catalog_hash, "records": rows}
    files["data/batches/" + batch + ".json"] = encode(sign(manifest, key, trust, role="research"))
    verify_final(repo, base, files, trust)
    return files


def apply_reviews(repo, client, number, key, private_root, approved_qids=None):
    pull = client.pull(number); base = fetch_main(repo); trust = trust_at(repo, base)
    if pull["base"]["ref"] != "main" or pull["head"]["repo"]["full_name"] != client.repository: raise ValueError("PR must target this repository's main")
    head = fetch_pull(repo, number, pull["head"]["sha"])
    _, manifest, proposals, _ = proposal_snapshot(repo, pull, trust)
    if approved_qids is not None:
        if not approved_qids or not set(approved_qids) <= set(proposals): raise ValueError("Invalid approved subset")
        proposals = {q: p for q, p in proposals.items() if q in approved_qids}
    notes = comments(client, number); decisions = {}
    for qid, proposal_doc in proposals.items():
        proposal = verify(proposal_doc, trust, role="research")
        candidates = read_reviews(notes, trust, number, qid, sha(encode(proposal)))
        if candidates: decisions[qid] = candidates[-1][0]
    from .distributed_feedback import assert_no_objections
    files = finalized_files(repo, base, manifest["batch_id"], proposals, decisions, key, trust)
    assert_no_objections(notes, trust, number, list(proposals), decisions=decisions)
    # Build from fresh main. Draft/failed proposal commits do not enter main
    # ancestry; old public drafts remain reachable through PR history and refs.
    tree, final_head = commit_files(repo, base, files, private_root, "Apply independent signed Review for " + manifest["batch_id"])
    verify_final(repo, base, files, trust)
    command(tree, "push", "--force-with-lease=refs/heads/" + pull["head"]["ref"] + ":" + head, "origin", final_head + ":refs/heads/" + pull["head"]["ref"])
    if pull.get("draft", False): client.set_draft(client.pull(number), False)
    return {"pr_number": number, "head_sha": final_head, "qids": sorted(proposals), "status": "approved_records_prepared"}
