from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/university-curation/scripts/lib"))
from university_curation import role_registration as r

KEY = "review-0123456789abcdef"
PUBLIC = "ab" * 32
class Client:
    repository = "owner/project"
    def __init__(self): self.created = []
    def find_branch(self, branch): return []
    def create(self, branch, title, body):
        self.created.append(branch); return {"html_url": "https://example.test/pr"}

class RoleRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name); self.repo = self.root / "repo"; self.repo.mkdir()
        self.private = self.root / ".private"; self.private.mkdir(); self.key = self.private / "fake.pem"; self.key.write_text("test-only")
        self.client = Client(); self.trust = {"repository": "owner/project", "keys": {}}
        def git(repo, *args):
            if args == ("remote", "get-url", "origin"): return b"https://github.com/owner/project.git\n"
            if args[0] == "ls-remote": return b""
            return b""
        self.patches = [patch.object(r, "_public", return_value=(KEY, PUBLIC)), patch.object(r, "_git", side_effect=git),
                        patch.object(r, "trust_at", side_effect=lambda repo, base: self.trust), patch.object(r, "commit", return_value="a"*40), patch.object(r, "_validate_branch")]
        for p in self.patches: p.start()
    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()
    def test_descriptor_only_and_resume_existing_key(self):
        result = r.register(self.repo, self.key, "research", self.client, self.private)
        self.assertEqual(result["status"], "registration_pr_open")
        self.assertEqual(self.client.created, ["codex/register-research-" + KEY])
        path = self.private / "role-registration-worktrees" / ("research-" + KEY) / ".curation/roles/research" / (KEY + ".json")
        self.assertEqual(r.load_json(path.read_bytes()), {"key_id": KEY, "algorithm": "Ed25519", "public_key_hex": PUBLIC, "status": "active", "role": "research"})
        self.trust["keys"][KEY] = {"algorithm": "Ed25519", "public_key_hex": PUBLIC, "status": "active", "roles": ["research"]}
        self.assertEqual(r.register(self.repo, self.key, "research", self.client, self.private)["status"], "already_trusted")
    def test_rejects_revoked_cross_role_and_origin_mismatch(self):
        for entry in ({"algorithm": "Ed25519", "public_key_hex": PUBLIC, "status": "revoked", "roles": ["review"]}, {"algorithm": "Ed25519", "public_key_hex": PUBLIC, "status": "active", "roles": ["research"]}):
            self.trust["keys"][KEY] = entry
            with self.assertRaises(ValueError): r.register(self.repo, self.key, "review", self.client, self.private)
        self.trust["keys"].clear(); self.client.repository = "other/repo"
        with self.assertRaises(ValueError): r.register(self.repo, self.key, "review", self.client, self.private)
        self.assertEqual(self.client.created, [])

if __name__ == "__main__": unittest.main()
