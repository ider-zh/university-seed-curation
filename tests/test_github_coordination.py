from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/university-curation/scripts/lib"))
from university_curation.github_coordination import GitCoordinator, GitModelBudget, CapacityBusy

T0 = "2026-11-05T00:00:00Z"
T1 = "2026-11-05T00:00:02Z"
H1, H2, BASE, POLICY = "a"*40, "b"*40, "c"*40, "d"*64

class GitCoordinationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        self.remote = root / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(self.remote)], check=True)
        self.coords = []
        for n in range(2):
            repo = root / ("client" + str(n))
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(self.remote)], check=True)
            self.coords.append(GitCoordinator(repo))
    def tearDown(self): self.temp.cleanup()
    def test_concurrent_same_qid_claim_and_fence(self):
        def claim(index):
            try: return self.coords[index].claim_task("Q2", "worker"+str(index), T0, ttl=1)
            except ValueError: return None
        with ThreadPoolExecutor(max_workers=2) as pool: result = list(pool.map(claim, range(2)))
        winners = [x for x in result if x]; self.assertEqual(len(winners), 1)
        next_lease = self.coords[1].claim_task("Q2", "new", T1)
        with self.assertRaises(ValueError): self.coords[0].set_task(winners[0], "draft", T1)
        self.coords[0].set_task(next_lease, "draft", T1, pr_number=12)
    def test_concurrent_distinct_qids_same_shard(self):
        a = self.coords[0]; byshard = {}; pair = None
        for n in range(1, 1000):
            qid = "Q"+str(n); ref = a._task_ref(qid)
            if ref in byshard: pair = (byshard[ref], qid); break
            byshard[ref] = qid
        with ThreadPoolExecutor(max_workers=2) as pool:
            leases = list(pool.map(lambda i: self.coords[i].claim_task(pair[i], "w"+str(i), T0), range(2)))
        state, _ = a.read(a._task_ref(pair[0])); self.assertEqual(set(state["tasks"]), set(pair)); self.assertEqual(len(leases), 2)
    def test_models_review_reservation_and_expiry(self):
        c = self.coords[0]; r1 = c.acquire_model("research", "a", "job1", T0, 1); r2 = c.acquire_model("research", "b", "job2", T0, 1)
        c.enqueue_review(1, H1, BASE, POLICY, T0)
        self.assertIsNone(c.acquire_model("research", "c", "job3", T0))
        review = c.acquire_model("review", "d", "job4", T0, 1)
        self.assertIsNotNone(review)
        self.assertIsNone(c.acquire_model("review", "e", "job5", T0))
        with self.assertRaises(ValueError): c.renew_model(r1, T1)
        self.assertIsNotNone(c.acquire_model("review", "e", "job5", T1))
        with self.assertRaises(CapacityBusy):
            with GitModelBudget(c, "review", "f", "job6", clock=lambda:T1, wait_timeout=0): pass
    def test_review_superseding_fences_old_lease(self):
        c = self.coords[0]; c.enqueue_review(9, H1, BASE, POLICY, T0)
        old = c.claim_review("rev", T0)
        c.enqueue_review(9, H2, BASE, POLICY, T1)
        with self.assertRaises(ValueError): c.finish_review(old, "approved", T1)
        new = c.claim_review("rev2", T1)
        self.assertEqual(new["head_sha"], H2)
        self.assertEqual(c.finish_review(new, "approved", T1)["status"], "complete")

    def test_commit_history_and_preserved_draft(self):
        c = self.coords[0]
        c.update("coord/runtime", lambda state: ({"v": 1}, None))
        _, old = c.read("coord/runtime")
        tree = c._git("mktree", data=b"").stdout.decode().strip()
        draft = c._git("-c", "user.name=Test", "-c", "user.email=test@example.test", "commit-tree", tree, data=b"draft\n").stdout.decode().strip()
        c.update("coord/runtime", lambda state: ({"v": 2}, None), preserve_commit=draft)
        _, head = c.read("coord/runtime")
        parents = c._git("show", "-s", "--format=%P", head).stdout.decode().split()
        self.assertEqual(parents, [old, draft])

class PermitUnitTests(unittest.TestCase):
    def test_bound_permits_survive_expiry_and_capacity(self):
        c = GitCoordinator("."); saved = {}
        def update(name, mutator, preserve_commit=None):
            old = saved.get(name, {})
            new, result = mutator(old)
            saved[name] = new
            return result
        c.update = update
        a = c.acquire_pr_permit("w", "batch-a", T0, ttl=1)
        bound = c.bind_pr_permit(a, 1, T0)
        c.acquire_pr_permit("w", "batch-b", T0, ttl=1)
        c.acquire_pr_permit("w", "batch-c", T0, ttl=1)
        self.assertIsNone(c.acquire_pr_permit("w", "batch-d", T1))
        d = c.acquire_pr_permit("w", "batch-d", T1, reclaim_expired=True)
        self.assertIsNotNone(d)
        self.assertIn(bound, saved["coord/runtime"]["pr_permits"])
        c.release_pr_permit(bound, T1)
        self.assertNotIn(bound, saved["coord/runtime"]["pr_permits"])
    def test_metadata_range_and_review_renewal(self):
        from university_curation.github_coordination import _validate_metadata
        _validate_metadata({"revision": 2, "batch_id": "batch-1", "proposal_sha256": "a"*64})
        for bad in (-1, 3, True):
            with self.assertRaises(ValueError): _validate_metadata({"revision": bad})
        c = GitCoordinator("."); saved = {}
        def update(name, mutator, preserve_commit=None):
            new, result = mutator(saved.get(name, {})); saved[name] = new; return result
        c.update = update
        c.enqueue_review(1, H1, BASE, POLICY, T0)
        lease = c.claim_review("reviewer", T0, ttl=3)
        renewed = c.renew_review(lease, T1, ttl=30)
        self.assertGreater(renewed["expires_at"], lease["expires_at"])
        c.enqueue_review(1, H2, BASE, POLICY, T1)
        with self.assertRaises(ValueError): c.renew_review(lease, T1)

if __name__ == "__main__": unittest.main()
