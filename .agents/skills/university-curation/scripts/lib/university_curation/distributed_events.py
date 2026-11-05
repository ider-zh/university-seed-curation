"""Trusted-main GitHub events for statuses and metadata-only Review dispatch."""
from datetime import datetime, timezone
import json
import re

from . import distributed_gate
from .attestations import load_json, verify
from .distributed_feedback import COMMENT
from .distributed_protocol import trust_at
from .distributed_transport import fetch_main
from .github_coordination import GitCoordinator

BRANCH = re.compile(r"codex/university-[a-z0-9][a-z0-9-]{0,79}\Z")


def _eligible(pull, repository):
    return (pull.get("state") == "open" and pull.get("base", {}).get("ref") == "main"
            and (pull.get("head", {}).get("repo") or {}).get("full_name") == repository
            and bool(BRANCH.fullmatch(pull.get("head", {}).get("ref", ""))))


def _signed_comment(repo, client, number, body):
    from .native_protocol import PATTERN
    native = PATTERN.findall(body or '')
    if len(native) == 1:
        try:
            value = load_json(native[0].encode())
            if value.get('repository') == client.repository and value.get('pr_number') == number and value.get('type') in ('university-native-review-v1','university-native-objection-v1'):
                return True
        except (ValueError, TypeError, AttributeError): pass
    matches = COMMENT.findall(body or "")
    if len(matches) != 1: return False
    try:
        base = fetch_main(repo); trust = trust_at(repo, base)
        value = verify(load_json(matches[0].strip().encode()), trust, role="review")
        return (value.get("repository") == client.repository and value.get("pr_number") == number
                and value.get("type") in ("university-review-decision-v1", "university-review-objection-v1"))
    except (ValueError, KeyError, TypeError, RuntimeError): return False


def process_pr(repo, client, number, mode="status", coordinator=None, now=None):
    if mode not in ("status", "queue"): raise ValueError("Invalid event mode")
    if type(number) is not int or number < 1: raise ValueError("Invalid PR number")
    pull = client.pull(number)
    if not _eligible(pull, client.repository): return {"status": "ignored"}
    if mode == "status": return distributed_gate.update_status(repo, client, number)
    result = distributed_gate.check(repo, client, number)
    if result.get("status") not in ("awaiting_independent_signed_review", "awaiting_independent_review"): return {"status": "not_a_valid_draft"}
    current = client.pull(number)
    if not _eligible(current, client.repository) or current["head"]["sha"] != result["head_sha"]: return {"status": "superseded"}
    base = fetch_main(repo); trust = trust_at(repo, base)
    if trust["repository"] != client.repository: raise ValueError("Configured repository mismatch")
    # Check the current main and PR head again after obtaining the policy snapshot.
    verified = distributed_gate.check(repo, client, number)
    if verified.get("status") not in ("awaiting_independent_signed_review", "awaiting_independent_review") or verified.get("head_sha") != result["head_sha"]: return {"status": "superseded"}
    if client.pull(number)["head"]["sha"] != result["head_sha"]: return {"status": "superseded"}
    if fetch_main(repo) != base: return {"status": "superseded"}
    coordinator = coordinator or GitCoordinator(repo)
    timestamp = now or datetime.now(timezone.utc).isoformat()
    item = coordinator.enqueue_review(number, result["head_sha"], base, trust["review_policy"]["sha256"], timestamp)
    return {"status": "queued", "pr_number": number, "head_sha": item["head_sha"]}


def handle_event(repo, client, event, event_name, mode="status", coordinator=None, now=None):
    if not isinstance(event, dict): raise ValueError("Invalid event")
    if event_name == "push":
        if event.get("ref") != "refs/heads/main" or event.get("deleted") or event.get("repository", {}).get("full_name") != client.repository:
            return {"status": "ignored"}
        return scan(repo, client, mode, coordinator, now)
    action = event.get("action")
    if event_name == "pull_request_target":
        if action not in ("opened", "synchronize", "reopened", "ready_for_review"): return {"status": "ignored"}
        number = event.get("number")
    elif event_name == "issue_comment":
        if action not in ("created", "edited", "deleted") or not event.get("issue", {}).get("pull_request"): return {"status": "ignored"}
        number = event.get("issue", {}).get("number")
        if type(number) is not int or number < 1: return {"status": "ignored"}
        comment = event.get("comment", {}); body = comment.get("body") or ""
        previous = event.get("changes", {}).get("body", {}).get("from") or ""
        from .native_protocol import PATTERN
        if (PATTERN.search(body) or PATTERN.search(previous)) and (comment.get('user') or {}).get('login','').lower() != client.repository.split('/')[0].lower():
            return {'status':'ignored'}
        if not (_signed_comment(repo, client, number, body) or _signed_comment(repo, client, number, previous)): return {"status": "ignored"}
    else: return {"status": "ignored"}
    if type(number) is not int or number < 1: return {"status": "ignored"}
    return process_pr(repo, client, number, mode, coordinator, now)


def scan(repo, client, mode="status", coordinator=None, now=None):
    """Polling fallback: enumerate open research PRs and re-evaluate each."""
    return [process_pr(repo, client, pull["number"], mode, coordinator, now) for pull in client.university_pulls()]


def main():
    import argparse
    import os
    from pathlib import Path
    from .research_github import GitHub
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--mode", required=True, choices=("status", "queue"))
    parser.add_argument("--scan", action="store_true")
    args = parser.parse_args()
    if not args.repository: parser.error("--repository or GITHUB_REPOSITORY is required")
    client = GitHub(args.repository)
    if args.scan: result = scan(args.repo, client, args.mode)
    else:
        path = os.environ.get("GITHUB_EVENT_PATH"); name = os.environ.get("GITHUB_EVENT_NAME")
        if not path or not name: parser.error("GitHub event environment is required")
        result = handle_event(args.repo, client, json.loads(Path(path).read_text(encoding="utf-8")), name, args.mode)
    print(json.dumps(result, ensure_ascii=True))
