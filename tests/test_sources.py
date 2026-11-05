from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
from urllib.parse import parse_qs, urlparse
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from university_curation.sources import Cache


HTML = '<table class="infobox"><tr><th>President</th><td>Dr. Example</td></tr><tr><td><img src="//example.org/image.jpg"></td></tr></table><p>Lead text.</p><h2 id="History">History</h2><p>Established in 1906.</p>'


class SourceTests(unittest.TestCase):
    def test_single_response_revision_cache_ttl_and_immutable_captures(self):
        now = [datetime(2026, 11, 5, tzinfo=timezone.utc)]; calls = []
        def fetch(url):
            calls.append(url)
            return {"parse": {"title": "Example", "pageid": 10, "revid": len(calls), "text": HTML, "wikitext": "{{Infobox}}", "sections": [{"index": "1", "line": "History", "anchor": "History"}]}}
        with tempfile.TemporaryDirectory() as tmp:
            cache = Cache(Path(tmp) / ".private/cache", fetch, lambda: now[0])
            first = cache.wikipedia_get("en", title="Example")
            self.assertEqual(first["revision_id"], 1)
            self.assertEqual(first["infobox"][0], {"label": "President", "text": "Dr. Example"})
            self.assertIn("Established in 1906.", first["text_sections"][1]["text"])
            self.assertEqual(first["image_urls"], ["https://example.org/image.jpg"])
            self.assertTrue(cache.wikipedia_get("en", title="Example")["from_cache"])
            self.assertEqual(len(calls), 1)
            now[0] += timedelta(days=31)
            second = cache.wikipedia_get("en", title="Example")
            self.assertEqual(second["revision_id"], 2)
            self.assertNotEqual(first["cache_path"], second["cache_path"])
            self.assertEqual(json.loads(Path(first["cache_path"]).read_text())["data"]["parse"]["revid"], 1)

    def test_online_entity_link_resolution_bound_and_full_references_private(self):
        calls = []
        def fetch(url):
            calls.append(url); args = parse_qs(urlparse(url).query); qid = args["ids"][0]
            self.assertEqual(args["redirects"], ["yes"])
            entity = {"id": qid, "lastrevid": 7, "labels": {"en": {"value": "Example"}}, "claims": {}, "sitelinks": {"enwiki": {"title": "Example"}}}
            if qid == "Q101":
                entity["claims"] = {"P17": [{"id": "Q101$one", "rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "Q102"}}}, "references": [{"hash": "private-original", "snaks": {}}]},
                                           {"id": "Q101$two", "rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "Q103"}}}}]}
            return {"entities": {qid: entity}}
        with tempfile.TemporaryDirectory() as tmp:
            cache = Cache(Path(tmp) / ".private/cache", fetch)
            result = cache.wikidata_get("Q101", ["P17"], resolve=["P17"], limit=1)
            self.assertEqual(result["linked_items"][0]["qid"], "Q102")
            self.assertTrue(result["linked_items_truncated"])
            self.assertEqual(result["claims"]["P17"][0]["reference_count"], 1)
            self.assertIn("private-original", Path(result["cache_path"]).read_text())
            self.assertEqual(len(calls), 2)

    def test_redirect_identity_preserved_and_bad_inputs_do_not_fetch(self):
        def fetch(url):return {"entities": {"Q102": {"id": "Q102", "lastrevid": 1, "claims": {}}}}
        with tempfile.TemporaryDirectory() as tmp:
            cache = Cache(Path(tmp) / ".private/cache", fetch)
            result = cache.wikidata_get("Q101")
            self.assertEqual((result["requested_qid"], result["qid"]), ("Q101", "Q102"))
            with self.assertRaises(ValueError): cache.wikipedia_get("en.evil.example", title="Example")
            with self.assertRaises(ValueError): cache.wikidata_get("../Q1")


if __name__ == "__main__": unittest.main()
