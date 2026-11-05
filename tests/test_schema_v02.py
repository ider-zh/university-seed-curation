from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / ".agents/skills/university-curation/scripts/lib"))
SCRIPTS = ROOT / ".agents/skills/university-curation/scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("schema_example", SCRIPTS / "build_schema_example.py")
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
from university_curation.preferred import validate, recompute
from university_curation.records import create


class PreferredTests(unittest.TestCase):
    def setUp(self): self.record = module.example()

    def test_complete_example_unknown_period_and_history_are_usable(self):
        validate(self.record)
        students = self.record["population"]["students_total"]
        self.assertEqual(students["preferred"]["candidate_id"], "c1")
        self.assertIn("period_not_stated", students["preferred"]["qualifications"])
        self.assertNotIn("period", students["candidates"][0])
        self.assertEqual(len(self.record["history"]["milestones"]), 7)
        self.assertEqual(self.record["history"]["milestones"][0]["subject_ref"], "related:predecessor")
        self.assertNotIn("qid", self.record["locations"][0])

    def test_conflict_retained_and_fte_not_collapsed(self):
        teaching = self.record["population"]["teaching_staff"]
        self.assertEqual(teaching["preferred"]["candidate_id"], "c1")
        self.assertEqual([c["value"]["amount"] for c in teaching["candidates"]], [980, 1020])
        self.assertIn("conflicting_candidates", teaching["preferred"]["qualifications"])
        employees = self.record["population"]["employees_total"]
        self.assertEqual(len(employees["candidates"]), 2)
        self.assertIn("different_basis_available", employees["preferred"]["qualifications"])

    def test_infobox_current_without_term_end_and_explicit_current_priority(self):
        president = self.record["leadership"]["president"]
        self.assertNotIn("term_end", president["candidates"][0]["value"])
        self.assertEqual(president["preferred"]["reason_code"], "infobox_current")
        newer = deepcopy(president["candidates"][0]); newer["id"] = "c3"; newer["current_basis"] = "explicit_current"
        president["candidates"].append(newer)
        self.assertEqual(recompute(self.record)["leadership"]["president"]["preferred"]["candidate_id"], "c3")

    def test_dangling_sources_preferred_and_subjects_rejected(self):
        bad = deepcopy(self.record); bad["population"]["students_total"]["preferred"]["candidate_id"] = "c99"
        with self.assertRaises(ValueError): validate(bad)
        bad = deepcopy(self.record); bad["population"]["students_total"]["candidates"][0]["evidence"][0]["source_ref"] = "s999"
        with self.assertRaises(ValueError): validate(bad)
        bad = deepcopy(self.record); bad["locations"][0]["population"]["students_total"]["subject_ref"] = "institution"
        with self.assertRaises(ValueError): validate(bad)

    def test_null_and_hidden_conflict_rejected_and_demo_not_publishable(self):
        bad = deepcopy(self.record); bad["population"]["students_total"]["candidates"][0]["period"] = None
        with self.assertRaises(ValueError): validate(bad)
        bad = deepcopy(self.record); bad["population"]["teaching_staff"]["preferred"].pop("qualifications")
        with self.assertRaises(ValueError): validate(bad)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError): create(tmp, self.record)


if __name__ == "__main__": unittest.main()
