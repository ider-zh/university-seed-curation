from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from university_curation.records import initial, create, record_path, validate, digest, proposal, finish_candidate, apply_reviewed, GROUPS
from university_curation.tasks import Queue, cutoff

NOW = "2026-11-05T04:00:00+00:00"


def seed(qid):
    return initial({"qid": qid, "classification": {"screening_status": "included"},
                    "discovery": {"channels": ["reviewed_institution_type"]}}, "test-import")


def receipt(base, candidate):
    return {"qid": base["qid"], "decision": "approve", "base_digest": digest(base),
        "candidate_digest": digest(candidate), "research_actor": "research-1", "research_session": "session-r",
        "review_actor": "review-1", "review_session": "session-v"}


class RecordTests(unittest.TestCase):
    def test_omission_zero_unknown_and_subject_attribution(self):
        record = seed("Q101"); validate(record)
        self.assertNotIn("update_datetime", record)
        record["sources"] = {"s1": {"kind": "website", "url": "https://example.org", "locator": "test section", "retrieved_at": NOW}}
        record["claims"] = [{"id": "c1", "field": "population.students_total", "value_state": "known",
            "value": {"amount": 0, "basis": "headcount", "precision": "exact"}, "source_refs": ["s1"], "status": "supported"}]
        validate(record)
        bad = deepcopy(record); bad["claims"][0]["value"] = None
        with self.assertRaises(ValueError): validate(bad)
        bad = deepcopy(record); bad["claims"][0]["subject_qid"] = "Q102"
        with self.assertRaises(ValueError): validate(bad)
        unknown = deepcopy(record); unknown["claims"][0].pop("value"); unknown["claims"][0]["value_state"] = "unknown"
        validate(unknown)
        unknown["claims"][0]["value"] = 0
        with self.assertRaises(Exception): validate(unknown)

    def test_canonical_bucket_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = seed("Q10924764")
            self.assertEqual(record_path(tmp, record["qid"]).parent.name, "dfc")
            self.assertEqual(create(tmp, record), "created")
            self.assertEqual(create(tmp, record), "unchanged")
            changed = deepcopy(record); changed["curation"]["identity_status"] = "needs_review"
            with self.assertRaises(FileExistsError): create(tmp, changed)
            with self.assertRaises(ValueError): record_path(tmp, "../Q1")

    def test_full_refresh_and_batch_dates_differ(self):
        old = seed("Q101"); proposed = deepcopy(old); proposed["curation"]["identity_status"] = "in_scope"
        full = finish_candidate(old, proposed, NOW, "university_refresh", GROUPS)
        partial = finish_candidate(full, deepcopy(full), "2026-11-06T04:00:00Z", "batch_import", ())
        self.assertEqual(partial["update_datetime"], NOW)
        self.assertEqual(partial["modified_datetime"], "2026-11-06T04:00:00Z")
        with self.assertRaises(ValueError): finish_candidate(old, proposed, NOW, "university_refresh", ["identity"])
        with self.assertRaises(ValueError): finish_candidate(old, full, NOW, "field_update", ())

    def test_cas_stale_rejection_and_idempotent_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = seed("Q101"); create(tmp, old)
            next_record = finish_candidate(old, old, NOW, "field_update", ())
            proof = receipt(old, next_record)
            self.assertEqual(apply_reviewed(tmp, next_record, digest(old), proof), "applied")
            self.assertEqual(apply_reviewed(tmp, next_record, digest(old), proof), "unchanged")
            stale = deepcopy(next_record); stale["curation"]["identity_status"] = "needs_review"
            with self.assertRaises(ValueError): apply_reviewed(tmp, stale, digest(old), receipt(old, stale))
            fake = receipt(next_record, stale); fake["review_session"] = fake["research_session"]
            with self.assertRaises(ValueError): apply_reviewed(tmp, stale, digest(next_record), fake)

    def test_compact_diff_cannot_change_revision_or_unregistered_fields(self):
        old = seed("Q101")
        with self.assertRaises(ValueError): proposal(old, {"record_revision": 900})
        with self.assertRaises(ValueError): proposal(old, {"new_claims": [{"field": "invented.field"}]})
        with self.assertRaises(ValueError): proposal(old, {"identity_status": "in_scope"}, ["population"])


class QueueTests(unittest.TestCase):
    def fixture(self, tmp, count=5):
        for n in range(count): create(tmp, seed("Q" + str(101 + n)))
        q = Queue(Path(tmp) / ".private" / "queue.sqlite3")
        run = q.snapshot(tmp, NOW, "test-base-ref")["run_id"]
        return q, run

    def test_six_calendar_months_and_snapshot_cursor_do_not_skip_updates(self):
        self.assertEqual(cutoff("2026-08-31T12:00:00Z").date().isoformat(), "2026-02-28")
        with tempfile.TemporaryDirectory() as tmp:
            q, run = self.fixture(tmp, 3)
            first = q.page(run, 1)
            old = json.loads(record_path(tmp, "Q102").read_text())
            changed = deepcopy(old); changed["curation"]["identity_status"] = "in_scope"
            updated = finish_candidate(old, changed, NOW, "university_refresh", GROUPS)
            apply_reviewed(tmp, updated, digest(old), receipt(old, updated))
            rest = q.page(run, 10, first["next_cursor"])
            self.assertEqual([x["qid"] for x in rest["tasks"]], ["Q102", "Q103"])
            newer = q.snapshot(tmp, NOW, "new-base")["run_id"]
            self.assertEqual([x["qid"] for x in q.page(newer)["tasks"]], ["Q101", "Q103"])
            with self.assertRaises(ValueError): q.page(newer, cursor=first["next_cursor"])
            q.close()
    def test_private_proposal_to_reviewed_refresh_cli(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); state = root / ".private" / "queue.sqlite3"; create(root, seed("Q201"))
            def run(*args):
                result = subprocess.run([sys.executable, str(repo / "scripts" / "curate.py"), "--state", str(state), "--now", NOW, *args],
                                        text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)
            snapshot = run("snapshot", "--workspace", str(root), "--base-ref", "test-base")
            researcher = run("claim", "--run", snapshot["run_id"], "--role", "research", "--actor", "research", "--session", "r-session")
            changes = root / ".private" / "changes.json"
            changes.write_text(json.dumps({"identity_status": "in_scope", "new_sources": {"s1": {
                "kind": "website", "url": "https://example.org", "locator": "fixture", "retrieved_at": NOW}},
                "new_claims": [{"field": "identity.kind", "value_state": "known", "value": "university", "source_refs": ["s1"], "status": "supported"}]}))
            path = root / ".private" / "proposal.json"
            run("propose", "Q201", "--workspace", str(root), "--changes", str(changes), "--output", str(path))
            task = str(researcher["task_id"])
            run("submit", "--task", task, "--lease", researcher["lease_token"], "--proposal", str(path))
            reviewer = run("claim", "--run", snapshot["run_id"], "--role", "review", "--actor", "review", "--session", "v-session")
            verdict = root / ".private" / "verdict.json"
            verdict.write_text(json.dumps({"decision": "approve", "source_checks": [{"claim_id": "c1", "verdict": "supported"}], "reviewed_groups": list(GROUPS)}))
            run("review", "--task", task, "--lease", reviewer["lease_token"], "--session", "v-session", "--verdict", str(verdict))
            self.assertEqual(run("apply", "--task", task, "--workspace", str(root), "--kind", "university_refresh")["state"], "applied")
            self.assertEqual(run("apply", "--task", task, "--workspace", str(root), "--kind", "university_refresh")["state"], "unchanged")
            result = json.loads(record_path(root, "Q201").read_text())
            self.assertEqual(result["update_datetime"], "2026-11-05T04:00:00+00:00")
            self.assertEqual(result["record_revision"], 2)

    def test_concurrent_claim_budget_and_expired_worker_fencing(self):
        with tempfile.TemporaryDirectory() as tmp:
            q, run = self.fixture(tmp, 5); state = Path(tmp) / ".private" / "queue.sqlite3"
            def claim(n):
                worker = Queue(state)
                try: return worker.claim(run, "research", "worker-" + str(n), "session-" + str(n), NOW, 10)
                finally: worker.close()
            with ThreadPoolExecutor(max_workers=5) as pool: results = list(pool.map(claim, range(5)))
            active = [x for x in results if x["available"]]
            self.assertEqual(len(active), 3)
            self.assertEqual(len({x["qid"] for x in active}), 3)
            replacement = q.claim(run, "research", "new", "new-session", "2026-11-05T04:00:11Z")
            self.assertTrue(replacement["available"])
            with self.assertRaises(ValueError):
                q.submit(active[0]["task_id"], active[0]["lease_token"], "2026-11-05T04:00:11Z", {})
            q.close()

    def test_independent_review_source_checks_and_two_revisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            q, run = self.fixture(tmp, 1)
            for attempt in range(3):
                research = q.claim(run, "research", "research", "r" + str(attempt), NOW)
                q.submit(research["task_id"], research["lease_token"], NOW,
                         {"qid": research["qid"], "base_digest": research["base_digest"], "changed_claim_ids": ["c1"]})
                self.assertFalse(q.claim(run, "review", "research", "other", NOW)["available"])
                review = q.claim(run, "review", "review", "v" + str(attempt), NOW)
                self.assertFalse(q.claim(run, "review", "review-2", "new-v", NOW)["available"])
                with self.assertRaises(ValueError):
                    q.decide(review["task_id"], review["lease_token"], NOW, "approve", "v" + str(attempt))
                result = q.decide(review["task_id"], review["lease_token"], NOW, "request_changes", "v" + str(attempt))
                self.assertEqual(result["state"], "unresolved" if attempt == 2 else "changes_requested")
            second_run = q.snapshot(tmp, NOW, "second-base")["run_id"]
            self.assertFalse(q.claim(second_run, "research", "research", "r4", NOW)["available"])
            self.assertEqual(q.db.execute("SELECT count(*) FROM attempts").fetchone()[0], 6)
            q.close()


if __name__ == "__main__": unittest.main()
