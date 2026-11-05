from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from university_curation.pilot_protocol import compile_record, review_gate, GROUPS


def fixture():
    source = {"kind": "wikipedia", "url": "https://en.wikipedia.org/w/index.php?oldid=1", "publisher_role": "encyclopedia",
        "family": "wikimedia", "language": "en", "page_id": 1, "revision_id": 1, "retrieved_at": "2026-11-05T00:00:00Z"}
    packet = {"case": {"qid": "Q101"}, "sources": {"s1": source}, "captured_at": "2026-11-05T00:00:00Z",
        "source_corpus": {"s1": [{"locator": "lead", "text": "Example University is a university with approximately 100 students. Campus A has 40 students."}]}}
    def fact(field, value, quote, context="institution"):
        return {"field": field, "context": context, "value_state": "known", "value_json": json.dumps(value),
            "period_json": "", "current_basis": "not_applicable", "evidence": [{"source_ref": "s1", "locator": "lead", "original_text": quote}]}
    proposal = {"qid": "Q101", "identity_status": "in_scope", "locations": [{"id": "campus", "kind": "campus", "qid": ""}],
        "milestones": [], "related_entities": [], "conflicts": [], "coverage": [{"group": g, "status": "checked", "note": "Fixture"} for g in GROUPS],
        "notes": [], "facts": [fact("identity.name", {"text": "Example University", "language": "en"}, "Example University"),
            fact("identity.kind", "university", "is a university"),
            fact("population.students_total", {"amount": 100, "basis": "unspecified", "precision": "approximate"}, "approximately 100 students"),
            fact("location.name", {"text": "Campus A", "language": "en"}, "Campus A", "location:campus"),
            fact("population.students_total", {"amount": 40, "basis": "unspecified", "precision": "exact"}, "Campus A has 40 students", "location:campus")]}
    return proposal, packet


class PilotTests(unittest.TestCase):
    def test_strict_materialization_preserves_subject_unknown_period_and_evidence(self):
        proposal, packet = fixture(); record, facts, contexts = compile_record(proposal, packet)
        self.assertEqual(record["population"]["students_total"]["candidates"][0]["value"]["amount"], 100)
        self.assertEqual(record["locations"][0]["population"]["students_total"]["candidates"][0]["value"]["amount"], 40)
        self.assertNotIn("period", record["population"]["students_total"]["candidates"][0])
        self.assertIn("period_not_stated", record["population"]["students_total"]["preferred"]["qualifications"])
        self.assertEqual([f["fact_id"] for f in facts], ["f1", "f2", "f3", "f4", "f5"])
        self.assertEqual(contexts, ["identity", "location:campus"])

    def test_review_must_cover_every_fact_and_context(self):
        proposal, packet = fixture(); _, facts, contexts = compile_record(proposal, packet)
        verdict = {"qid": "Q101", "decision": "approve", "checks": [{"fact_id": f["fact_id"], "verdict": "supported"} for f in facts],
            "context_checks": [{"context_id": c, "verdict": "supported"} for c in contexts],
            "coverage_checks": [{"group": g, "status": "checked"} for g in GROUPS]}
        self.assertTrue(review_gate(verdict, proposal, contexts))
        wrong = deepcopy(verdict); wrong["checks"].pop()
        with self.assertRaises(ValueError): review_gate(wrong, proposal, contexts)
        wrong = deepcopy(verdict); wrong["checks"][0]["verdict"] = "wrong_subject"
        self.assertFalse(review_gate(wrong, proposal, contexts))

    def test_nonverbatim_missing_source_and_invalid_conflict_cannot_pass(self):
        proposal, packet = fixture(); proposal["facts"][0]["evidence"][0]["original_text"] = "Invented University"
        with self.assertRaises(ValueError): compile_record(proposal, packet)

    def test_zero_based_conflict_and_partial_observation_month(self):
        proposal, packet = fixture()
        proposal["facts"].append(deepcopy(proposal["facts"][2]))
        proposal["facts"][-1]["period_json"] = json.dumps({"kind": "date", "year": 2025, "month": 9})
        proposal["conflicts"] = [{"fact_indexes": [2, 5], "kind": "value_disagreement", "note": "Source conflict fixture"}]
        record, _, _ = compile_record(proposal, packet)
        metric = record["population"]["students_total"]
        self.assertEqual(metric["conflicts"][0]["candidate_ids"], ["c1", "c2"])
        self.assertEqual(metric["candidates"][1]["period"], {"kind": "date", "year": 2025, "month": 9})
        self.assertIn("conflicting_candidates", metric["preferred"]["qualifications"])

    def test_headquarters_is_not_office_and_chair_is_not_board_chair(self):
        proposal, packet = fixture()
        proposal["locations"][0]["kind"] = "headquarters"
        template = deepcopy(proposal["facts"][0])
        template.update({"field": "leadership.chair", "value_json": json.dumps({"person": {"name": "Example"},
            "title_original": {"text": "Chair", "language": "en"}}), "current_basis": "infobox_current"})
        proposal["facts"].append(template)
        record, _, _ = compile_record(proposal, packet)
        self.assertEqual(record["locations"][0]["kind"], "headquarters")
        self.assertIn("chair", record["leadership"])
        self.assertNotIn("board_chair", record["leadership"])
        proposal, packet = fixture(); proposal["conflicts"] = [{"fact_indexes": [0, 1], "kind": "value_disagreement", "note": "Invalid"}]
        with self.assertRaises(ValueError): compile_record(proposal, packet)


if __name__ == "__main__": unittest.main()
