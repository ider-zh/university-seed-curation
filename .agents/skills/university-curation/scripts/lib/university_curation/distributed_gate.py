"""Trusted-base PR gate, including newly signed objections after earlier approval."""
from .attestations import load_json, sha, verify
from .records import encode
from .pr_export import blob, git, validate_pr
from .distributed_protocol import trust_at, read_reviews
from .distributed_transport import fetch_main, fetch_pull, draft_snapshot, comments
from .distributed_feedback import assert_no_objections


def check(repo, client, number):
    pull = client.pull(number)
    if pull["base"]["ref"] != "main" or (pull["head"].get("repo") or {}).get("full_name") != client.repository:
        return {"state": "pending", "status": "unsupported_pr", "head_sha": pull["head"]["sha"]}
    base = fetch_main(repo); head = fetch_pull(repo, number, pull["head"]["sha"]); trust = trust_at(repo, base)
    paths = [p for p in git(repo, "diff", "--no-renames", "--name-only", "-z", base, head).decode().split("\0") if p]
    if any(p.startswith("data/proposals/") for p in paths):
        manifest, proposals = draft_snapshot(repo, head, trust)
        return {"state": "pending", "status": "awaiting_independent_signed_review", "head_sha": head, "qids": sorted(proposals)}
    result = validate_pr(repo, base, head)
    if result.get("task_kind") != "distributed_research":
        return {"state": "success", "status": result["status"], "head_sha": head}
    if result["review_pr"] != number: raise ValueError("Signed Review belongs to another PR")
    notes = comments(client, number)
    decisions = {}
    for qid in result["qids"]:
        receipt = load_json(blob(repo, head, "data/reviews/" + result["batch_id"] + "/" + qid + ".json"))
        proposal = verify(receipt["research"], trust, role="research")
        history = read_reviews(notes, trust, number, qid, sha(encode(proposal)))
        if not history or history[-1][0] != receipt["review"]:
            raise ValueError("Final records must use the latest independently signed Review decision")
        decisions[qid] = receipt["review"]
    assert_no_objections(notes, trust, number, result["qids"], decisions=decisions)
    return {"state": "success", "status": "independently_reviewed", "head_sha": head,
            "base_sha": base, "discussion_sha256": sha(encode(notes)), "qids": result["qids"]}


def update_status(repo, client, number):
    pull = client.pull(number); head = pull["head"]["sha"]
    try: result = check(repo, client, number)
    except (ValueError, RuntimeError) as error:
        result = {"state": "failure", "status": "review_blocked", "reason": str(error)[:100], "head_sha": head}
    if result.get("state") == "success" and result.get("discussion_sha256"):
        if sha(encode(comments(client, number))) != result["discussion_sha256"] or fetch_main(repo) != result["base_sha"]:
            result = {"state": "pending", "status": "discussion_or_main_changed", "head_sha": result["head_sha"]}
    if client.pull(number)["head"]["sha"] != result["head_sha"]:
        return {"status": "superseded", "head_sha": result["head_sha"]}
    client.request("POST", "/statuses/" + result["head_sha"], {"state": result["state"], "context": "university-review",
        "description": result.get("reason", result["status"])[:140], "target_url": pull["html_url"]})
    return result
