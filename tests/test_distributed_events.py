from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/university-curation/scripts/lib"))
from university_curation import distributed_events as e

HEAD = "a"*40; BASE = "b"*40; POLICY = "c"*64
class Client:
    repository = "owner/repo"
    def __init__(self):
        self.pr = {"number": 2, "state": "open", "base": {"ref": "main"}, "head": {"sha": HEAD, "ref": "codex/university-batch-1", "repo": {"full_name": self.repository}}}
    def pull(self, number): return self.pr
    def university_pulls(self): return [self.pr]
class Coordinator:
    def __init__(self): self.calls=[]
    def enqueue_review(self, *args): self.calls.append(args); return {"head_sha": args[1]}

class EventTests(unittest.TestCase):
    def setUp(self): self.client=Client(); self.coord=Coordinator()
    def test_eligible_status_uses_trusted_gate(self):
        with patch.object(e.distributed_gate, "update_status", return_value={"status": "pending"}) as status:
            self.assertEqual(e.process_pr("repo", self.client, 2)["status"], "pending")
            status.assert_called_once_with("repo", self.client, 2)
        for change in ("fork", "branch", "base", "closed"):
            old = self.client.pr.copy(); self.client.pr = {**old, "base": dict(old["base"]), "head": {**old["head"], "repo": dict(old["head"]["repo"])}}
            if change == "fork": self.client.pr["head"]["repo"]["full_name"] = "other/repo"
            if change == "branch": self.client.pr["head"]["ref"] = "other"
            if change == "base": self.client.pr["base"]["ref"] = "other"
            if change == "closed": self.client.pr["state"] = "closed"
            with self.subTest(change=change): self.assertEqual(e.process_pr("repo", self.client, 2)["status"], "ignored")
            self.client.pr = old
    def test_queue_requires_verified_draft_and_stable_head(self):
        trust = {"repository": self.client.repository, "review_policy": {"sha256": POLICY}}
        with patch.object(e.distributed_gate, "check", return_value={"status": "awaiting_independent_signed_review", "head_sha": HEAD}), patch.object(e, "fetch_main", return_value=BASE), patch.object(e, "trust_at", return_value=trust):
            result=e.process_pr("repo", self.client, 2, "queue", self.coord, "2026-11-05T00:00:00Z")
            self.assertEqual(result["status"], "queued")
            self.assertEqual(self.coord.calls[0][:4], (2, HEAD, BASE, POLICY))
        with patch.object(e.distributed_gate, "check", return_value={"status": "awaiting_independent_signed_review", "head_sha": "f"*40}):
            self.assertEqual(e.process_pr("repo", self.client, 2, "queue", self.coord)["status"], "superseded")
        with patch.object(e.distributed_gate, "check", return_value={"status": "review_blocked"}):
            self.assertEqual(e.process_pr("repo", self.client, 2, "queue", self.coord)["status"], "not_a_valid_draft")
    def test_unsigned_comment_and_wrong_events_ignored(self):
        event={"action": "created", "issue": {"number": 2, "pull_request": {}}, "comment": {"body": "plain"}}
        self.assertEqual(e.handle_event("repo", self.client, event, "issue_comment")["status"], "ignored")
        event["issue"]["pull_request"] = {"url": "example"}
        with patch.object(e, "_signed_comment", return_value=False): self.assertEqual(e.handle_event("repo", self.client, event, "issue_comment")["status"], "ignored")
        with patch.object(e, "_signed_comment", return_value=True), patch.object(e, "process_pr", return_value={"status":"checked"}):
            self.assertEqual(e.handle_event("repo", self.client, event, "issue_comment")["status"], "checked")
        self.assertEqual(e.handle_event("repo", self.client, {"action":"closed", "number":2}, "pull_request_target")["status"], "ignored")
    def test_comment_signature_and_pr_binding(self):
        doc="<!-- university-signed-review-v1\n{}-->"
        trust={"repository":"owner/repo"}
        payload={"repository":"owner/repo", "pr_number":2, "type":"university-review-objection-v1"}
        with patch.object(e, "fetch_main", return_value=BASE), patch.object(e, "trust_at", return_value=trust), patch.object(e, "verify", return_value=payload):
            self.assertTrue(e._signed_comment("repo", self.client, 2, doc))
            self.assertFalse(e._signed_comment("repo", self.client, 3, doc))
        with patch.object(e, "fetch_main", return_value=BASE), patch.object(e, "trust_at", return_value=trust), patch.object(e, "verify", side_effect=ValueError):
            self.assertFalse(e._signed_comment("repo", self.client, 2, doc))
    def test_poll_scan(self):
        with patch.object(e, "process_pr", return_value={"status":"ok"}) as run:
            self.assertEqual(e.scan("repo", self.client), [{"status":"ok"}]); run.assert_called_once()
    def test_main_push_rescans_and_other_pushes_are_ignored(self):
        event = {"ref": "refs/heads/main", "repository": {"full_name": "owner/repo"}, "deleted": False}
        with patch.object(e, "scan", return_value=[{"status": "ok"}]) as scan:
            self.assertEqual(e.handle_event("repo", self.client, event, "push", "queue", self.coord), [{"status": "ok"}])
            scan.assert_called_once_with("repo", self.client, "queue", self.coord, None)
        for change in ({"ref": "refs/heads/other"}, {"deleted": True}, {"repository": {"full_name": "other/repo"}}):
            with self.subTest(change=change):
                self.assertEqual(e.handle_event("repo", self.client, {**event, **change}, "push")["status"], "ignored")
    def test_edited_comment_removal_checks_previous_signature(self):
        event = {"action": "edited", "issue": {"number": 2, "pull_request": {"url": "x"}},
                 "comment": {"body": "removed"}, "changes": {"body": {"from": "previous"}}}
        with patch.object(e, "_signed_comment", side_effect=lambda repo, client, number, body: body == "previous"), patch.object(e, "process_pr", return_value={"status": "checked"}):
            self.assertEqual(e.handle_event("repo", self.client, event, "issue_comment")["status"], "checked")

if __name__ == "__main__": unittest.main()
