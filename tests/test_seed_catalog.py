import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/university-curation/scripts/lib"))
from university_curation import seed_catalog as s, attestations


class SeedCatalogTests(unittest.TestCase):
    def setUp(self):
        self.sources = {"primary": {"sha256": "a", "manifest_sha256": "b", "count": 2}, "discovery": {"sha256": "c", "manifest_sha256": "d", "count": 2}}
        self.primary = [{"qid": "Q2", "screening_status": "included", "channels": ["type"]}, {"qid": "Q10", "screening_status": "needs_review", "channels": ["ranking"]}]
        self.discovery = [{"qid": "Q2", "legacy_types": ["Q1"]}, {"qid": "Q11", "legacy_types": ["Q3"]}]
        self.files = {s.NAMES[0]: s.encode_rows(self.primary), s.NAMES[1]: s.encode_rows(self.discovery)}
        payload = {"version": 1, "format": "utf8-json-array-one-canonical-object-per-line-v1", "sources": self.sources, "acceptance": s.AUTH,
            "lists": {kind: {"path": name, "sha256": s.digest(self.files[name]), "count": 2} for kind, name in zip(("primary", "discovery"), s.NAMES)}}
        self.payload = payload
        self.files[s.NAMES[2]] = s.compact(payload) + b"\n"

    def test_preview_checks_overlap_and_tampering(self):
        with patch.object(s, "SOURCES", self.sources):
            result = s.verify(self.files)
            self.assertEqual(result["overlap_count"], 1)
            self.files[s.NAMES[0]] += b" "
            with self.assertRaises(ValueError): s.verify(self.files)

    def test_signature_required_and_rejects_changed_payload(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(s, "SOURCES", self.sources):
            key = Path(tmp) / ".private" / "key.pem"
            public = attestations.init_key(key)
            trust = {"keys": {public["key_id"]: {**public, "status": "active"}}}
            with self.assertRaises(ValueError): s.verify(self.files, trust=trust)
            signed = attestations.sign(self.payload, key, trust)
            self.files[s.NAMES[2]] = s.compact(signed) + b"\n"
            self.assertEqual(s.verify(self.files, trust=trust)["overlap_count"], 1)
            signed["payload"]["acceptance"]["actor"] = "other"
            self.files[s.NAMES[2]] = s.compact(signed) + b"\n"
            with self.assertRaises(ValueError): s.verify(self.files, trust=trust)

    def test_invalid_qids_duplicates_and_extra_fields(self):
        for rows in ([self.primary[1], self.primary[0]], [self.primary[0], self.primary[0]], [{**self.primary[0], "extra": "x"}], [{**self.primary[0], "qid": "Q01"}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError): s._check_rows(rows, "primary")

    def test_primary_wins_overlapping_discovery(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(s, "SOURCES", self.sources):
            for name, data in self.files.items():
                path = Path(tmp) / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            catalog = s.load_catalog(tmp, preview=True)
            self.assertEqual(catalog["Q2"]["queue_kind"], "primary")
            self.assertEqual(catalog["Q11"]["queue_kind"], "discovery")
            with self.assertRaises(FileNotFoundError): s.load_catalog(tmp)


if __name__ == "__main__": unittest.main()
