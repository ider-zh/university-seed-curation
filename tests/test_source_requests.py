import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/university-curation/scripts/lib"))
from university_curation.sources import Cache
from university_curation.source_requests import augment_packet


class LinkedRequestsTests(unittest.TestCase):
    def test_unit_lookup_is_bounded_cached_and_keeps_revision_and_iso_code(self):
        calls = []
        def fetch(url):
            calls.append(url)
            return {"entities": {"Q4917": {"id": "Q4917", "lastrevid": 7,
                "labels": {"en": {"value": "US dollar"}}, "claims": {"P498": [{"id": "Q4917$code", "mainsnak": {"snaktype": "value", "datavalue": {"value": "USD"}}}]}}}}
        packet = {"case": {"qid": "Q101", "languages": ["en"]}, "sources": {"s1": {"kind": "wikidata", "source_qid": "Q101"}},
            "source_corpus": {"s1": [{"locator": "claim", "text": 'unit: http://www.wikidata.org/entity/Q4917'}]}, "property_labels": {}}
        with tempfile.TemporaryDirectory() as tmp:
            cache = Cache(Path(tmp) / ".private/shared", fetch)
            updated, first = augment_packet(packet, [{"qid": "Q4917", "purpose": "quantity_unit"}], cache)
            _, second = augment_packet(packet, [{"qid": "Q4917", "purpose": "quantity_unit"}], cache)
            self.assertEqual(len(calls), 1)
            self.assertFalse(first[0]["from_cache"]); self.assertTrue(second[0]["from_cache"])
            self.assertEqual(updated["sources"]["s2"]["revision_id"], 7)
            self.assertIn("USD", json.dumps(updated["source_corpus"]["s2"]))
            self.assertNotIn("s2", packet["sources"])
            with self.assertRaises(ValueError): augment_packet(packet, [{"qid": "Q2", "purpose": "quantity_unit"}], cache)
            with self.assertRaises(ValueError): augment_packet(packet, [{"qid": "Q4917", "purpose": "quantity_unit"}] * 9, cache)
            self.assertEqual(len(calls), 1)
