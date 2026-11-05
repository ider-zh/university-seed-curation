from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import subprocess
from urllib.parse import parse_qs, urlparse
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/university-curation/scripts/lib"))
from university_curation.sources import Cache


HTML = '<table class="infobox"><tr><th>President</th><td>Dr. Example</td></tr><tr><td><img src="//example.org/image.jpg"></td></tr></table><p>Lead text.</p><h2 id="History">History</h2><p>Established in 1906.</p>'


class SourceTests(unittest.TestCase):
    def test_three_processes_share_one_cache_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            private = Path(tmp) / ".private/cache"
            calls = Path(tmp) / "calls.txt"
            gate = Path(tmp) / "start"
            code = '''import sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from university_curation.sources import Cache
def fetch(url):
    with Path(sys.argv[3]).open("a") as stream: stream.write("fetch\\n")
    time.sleep(.15)
    return {"entities":{"Q101":{"id":"Q101","lastrevid":7,"claims":{}}}}
while not Path(sys.argv[4]).exists(): time.sleep(.01)
entity,meta=Cache(sys.argv[2],fetch).entity("Q101")
assert entity["lastrevid"]==7
'''
            args = [sys.executable, "-c", code, str(Path(__file__).resolve().parents[1] / ".agents/skills/university-curation/scripts/lib"), str(private), str(calls), str(gate)]
            workers = [subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(3)]
            gate.touch()
            for worker in workers:
                out, err = worker.communicate(timeout=20)
                self.assertEqual(worker.returncode, 0, err.decode(errors="replace"))
            self.assertEqual(calls.read_text().splitlines(), ["fetch"])

    def test_review_entity_revision_rejects_wrong_qid_or_revision(self):
        response = {"query": {"pages": [{"title": "Q101", "revisions": [{"revid": 7,
            "slots": {"main": {"content": json.dumps({"id": "Q101", "claims": {}})}}}]}]}}
        def fetch(url):
            args = parse_qs(urlparse(url).query)
            self.assertEqual(args["revids"], ["7"])
            self.assertEqual(args["rvprop"], ["ids|content"])
            return response
        with tempfile.TemporaryDirectory() as tmp:
            cache = Cache(Path(tmp) / ".private/review", fetch)
            entity, _ = cache.entity_revision("Q101", 7)
            self.assertEqual(entity["lastrevid"], 7)
            with self.assertRaises(ValueError): cache.entity_revision("Q102", 7)
            response["query"]["pages"][0]["revisions"][0]["revid"] = 8
            with self.assertRaises(ValueError): cache.entity_revision("Q101", 7, refresh=True)

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
