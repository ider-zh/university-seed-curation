from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/university-curation/scripts/lib"))
from university_curation.records import initial, create, record_path, validate, digest, proposal, finish_candidate, apply_reviewed, GROUPS
from university_curation.manager import cutoff

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
            self.assertEqual(record_path(tmp, record["qid"]).parent.name, "df")
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
