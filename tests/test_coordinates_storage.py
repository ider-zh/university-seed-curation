from copy import deepcopy
from collections import Counter
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".agents/skills/university-curation/scripts/lib"))
from university_curation.coordinates import projection, materialize, root_source, review_gate, KIND
from university_curation.preferred import validate
from university_curation.records import ROOT, encode, record_path
from university_curation.attestations import sha, load_json, sign
from university_curation.pr_export import check_record, record_relative, scope, verify_files, validate_pr, install
from university_curation.bucket_migration import paths, prepare, stage
import test_pr_export as export_fixtures
NOW = export_fixtures.NOW


class CoordinateStorageTests(unittest.TestCase):
    def setUp(self):
        self.case = export_fixtures.ExportTests(methodName="runTest"); self.case.setUp()
        self.addCleanup(self.case.tearDown)
        self.record = deepcopy(self.case.record)
        self.record["sources"]["s2"] = {"kind": "wikidata", "source_qid": "Q101", "revision_id": 5,
            "url": "https://www.wikidata.org/w/index.php?oldid=5", "retrieved_at": NOW,
            "publisher_role": "knowledge_base", "family": "wikimedia"}
        self.entity = {"id": "Q101", "lastrevid": 5, "claims": {"P625": [self.claim()]}}

    def claim(self, sid="Q101$ABC-123", lat=0, lon=0, state="value", rank="normal"):
        snak = {"property": "P625", "snaktype": state}
        if state == "value": snak["datavalue"] = {"type": "globecoordinate", "value": {
            "latitude": lat, "longitude": lon, "precision": 0.0001, "globe": "http://www.wikidata.org/entity/Q2", "altitude": None}}
        return {"id": sid, "rank": rank, "mainsnak": snak}

    def configure_base(self, legacy=False):
        case = self.case
        case.trust["schemas"]["0.2.2"] = sha(encode(load_json((ROOT / "schemas/university.v0.2.2.schema.json").read_bytes())))
        case.trust["field_update_adapters"] = [KIND]
        case.put(".curation/review-trust.json", encode(case.trust))
        case.put("schemas/university.v0.2.2.schema.json", (ROOT / "schemas/university.v0.2.2.schema.json").read_bytes())
        case.put(paths("Q101")[0] if legacy else record_relative("Q101"), encode(self.record))
        case.commit("trusted schema and existing university"); case.base = case.git("rev-parse", "HEAD").decode().strip()

    def update(self):
        point = projection(self.record, self.entity)
        review = {**self.case.review, "task_kind": KIND, "producer": "deterministic-root-p625-v1", "research_sessions": [],
            "review_session": "independent-coordinate-review", "coordinate_projection": point, "request_ref": "test-only:missing-point",
            "facts_checked": len(point["statements"]), "contexts_checked": 1, "source_revisions_checked": 1}
        return materialize(self.record, point, NOW), review

    def update_bundle(self, record, review):
        case = self.case; path = record_relative("Q101"); receipt_path = "data/reviews/coordinate-fixture/Q101.json"
        data = encode(record)
        receipt = {"type": "university-review-v1", "repository": case.trust["repository"], "qid": "Q101",
            "base_commit": case.base, "record_path": path, "record_sha256": sha(data), "baseline_sha256": sha(encode(self.record)),
            "schema_version": "0.2.2", "schema_sha256": case.trust["schemas"]["0.2.2"], "review_policy": case.trust["review_policy"], "review": review}
        signed = encode(sign(receipt, case.key, case.trust))
        rows = [{"qid": "Q101", "record_path": path, "record_sha256": sha(data), "receipt_path": receipt_path, "receipt_sha256": sha(signed)}]
        content = scope(rows, {"Q101": receipt}, case.trust)
        manifest = {"type": "university-batch-v1", "task_kind": KIND, "repository": case.trust["repository"],
            "batch_id": "coordinate-fixture", "base_commit": case.base, "created_at": NOW, "content_scope_sha256": content,
            "authorization": {"kind": "independently_reviewed_field_update", "request_refs": [review["request_ref"]]}, "records": rows}
        return {path: data, receipt_path: signed, "data/batches/coordinate-fixture.json": encode(sign(manifest, case.key, case.trust))}

    def test_root_coordinate_is_preserved_despite_other_site_and_zero_is_valid(self):
        self.record["locations"][0]["coordinates"] = {"candidates": [{"id": "c1", "value": {
            "latitude": 25, "longitude": 102, "crs": "EPSG:4326"}, "verification": "supported",
            "evidence": [{"source_ref": "s1", "locator": "lead"}]}]}
        from university_curation.preferred import recompute
        self.record = recompute(self.record)
        point = projection(self.record, self.entity); result = materialize(self.record, point, NOW)
        self.assertEqual(result["locations"][:-1], self.record["locations"])
        value = result["locations"][-1]["coordinates"]["candidates"][0]["value"]
        self.assertEqual(value["latitude"], 0); self.assertEqual(value["source_precision_degrees"], 0.0001)
        self.assertNotIn("accuracy_metres", value)
        self.assertEqual(result["locations"][-1]["kind"], "institution")
        self.assertEqual(result["update_datetime"], self.record["update_datetime"])

    def test_lowercase_wikidata_statement_prefix_keeps_original_locator(self):
        self.entity["claims"]["P625"] = [self.claim("q101$abc-123", 52.16, 21.04)]
        point = projection(self.record, self.entity)
        self.assertEqual(point["statements"][0]["statement_id"], "q101$abc-123")
        result = materialize(self.record, point, NOW)
        evidence = result["locations"][-1]["coordinates"]["candidates"][0]["evidence"][0]
        self.assertEqual(evidence["locator"], "statement:q101$abc-123")
        for foreign in ("q102$abc-123", "q101abc-123", "Q101$", "Q101$abc_123"):
            self.entity["claims"]["P625"] = [self.claim(foreign)]
            with self.subTest(foreign=foreign), self.assertRaisesRegex(ValueError, "foreign Wikidata statement"):
                projection(self.record, self.entity)

    def test_linked_item_wrong_revision_non_earth_and_qualified_points_fail_closed(self):
        for mutation in (lambda e: e.update(id="Q174091"), lambda e: e.update(lastrevid=6),
            lambda e: e["claims"]["P625"][0]["mainsnak"]["datavalue"]["value"].update(globe="http://www.wikidata.org/entity/Q111"),
            lambda e: e["claims"]["P625"][0].update(qualifiers={"P585": [1]})):
            entity = deepcopy(self.entity); mutation(entity)
            with self.subTest(entity=entity), self.assertRaises(ValueError): projection(self.record, entity)

    def test_unknown_novalue_deprecated_and_multi_point_coverage(self):
        self.entity["claims"]["P625"] = [self.claim("Q101$C", state="somevalue"), self.claim("Q101$D", state="novalue"),
            self.claim("Q101$E", rank="deprecated"), self.claim("Q101$B", 10, 20), self.claim("Q101$A", 11, 21, rank="preferred")]
        point = projection(self.record, self.entity); result = materialize(self.record, point, NOW)
        field = result["locations"][-1]["coordinates"]
        self.assertEqual(len(field["candidates"]), 4)
        self.assertEqual(field["candidates"][0]["value"]["latitude"], 11)
        self.assertEqual(field["candidates"][2]["value_state"], "unknown")
        self.assertEqual(field["candidates"][3]["value_state"], "no_value")
        self.assertIn("conflicting_candidates", field["preferred"]["qualifications"])
        with self.assertRaises(ValueError): review_gate({"decision": "approve", "scope_supported": True, "checks": []}, point)
        for state in ("somevalue", "novalue"):
            self.entity["claims"]["P625"] = [self.claim("Q101$A", state=state, rank="preferred"), self.claim("Q101$B", 10, 20)]
            result = materialize(self.record, projection(self.record, self.entity), NOW)
            self.assertNotIn("preferred", result["locations"][-1]["coordinates"])
            self.assertEqual(result["locations"][-1]["coordinates"]["candidates"][0]["source_rank"], "preferred")

    def test_signed_update_checks_only_its_delta_and_preserves_existing_review(self):
        self.configure_base(); record, review = self.update(); files = self.update_bundle(record, review)
        checked = verify_files(self.case.repo, self.case.base, files, self.case.trust)
        self.assertEqual(checked["task_kind"], KIND); self.assertFalse(checked["human_accepted"])
        for path, raw in files.items(): self.case.put(path, raw)
        self.case.commit("coordinate update")
        self.assertEqual(validate_pr(self.case.repo, self.case.base, "HEAD")["task_kind"], KIND)
        for name, value in (("update_datetime", "2027-01-01T00:00:00Z"), ("record_revision", 9)):
            bad = deepcopy(record); bad[name] = value
            with self.assertRaises(ValueError): check_record(bad, review, self.case.trust, self.record)
        bad = deepcopy(record); bad["locations"][0]["kind"] = "office"
        with self.assertRaises(ValueError): check_record(bad, review, self.case.trust, self.record)
        with self.assertRaises(ValueError): materialize(record, review["coordinate_projection"], NOW)

    def test_update_install_preserves_dirty_baseline_and_allows_exact_tracked_baseline(self):
        self.configure_base(); record, review = self.update(); files = self.update_bundle(record, review)
        output = self.case.root / ".private/update-bundle"; output.mkdir(parents=True)
        for path, raw in files.items():
            target = output / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
        (output / "preview.json").write_bytes(encode({"base_commit": self.case.base, "files": {p: sha(v) for p, v in files.items()}}))
        target = self.case.repo / record_relative("Q101"); target.write_bytes(b"dirty")
        with self.assertRaises(ValueError): install(self.case.repo, output)
        self.case.git("add", record_relative("Q101"))
        target.write_bytes(encode(self.record))
        with self.assertRaises(ValueError): install(self.case.repo, output)
        self.case.git("restore", "--staged", "--", record_relative("Q101"))
        target.unlink()
        with self.assertRaises(ValueError): install(self.case.repo, output)
        target.write_bytes(encode(self.record))
        self.assertEqual(install(self.case.repo, output)["task_kind"], KIND)

    def test_256_bucket_migration_preserves_bytes_and_historical_receipts(self):
        self.configure_base(legacy=True)
        self.case.put(".gitattributes", (ROOT / ".gitattributes").read_bytes())
        self.case.git("config", "core.autocrlf", "true")
        self.case.put("data/reviews/old/Q101.json", b"historical immutable receipt")
        self.case.commit("old receipt"); base = self.case.git("rev-parse", "HEAD").decode().strip()
        self.case.git("checkout-index", "--force", "--", paths("Q101")[0])
        self.assertNotIn(b"\r\n", (self.case.repo / paths("Q101")[0]).read_bytes())
        with self.assertRaises(ValueError): verify_files(self.case.repo, base, self.case.bundle(record=self.record), self.case.trust)
        output = self.case.root / ".private/migration"
        preview = prepare(self.case.repo, base, "bucket-fixture", output)
        self.assertEqual(preview["records_moved"], 1)
        old, new = paths("Q101")
        (self.case.repo / old).write_bytes(b"staged old-path edit"); self.case.git("add", old)
        (self.case.repo / old).write_bytes(encode(self.record))
        with self.assertRaises(ValueError): stage(self.case.repo, output)
        self.case.git("restore", "--staged", "--", old)
        self.assertEqual(stage(self.case.repo, output)["bucket_count"], 256)
        self.assertFalse((self.case.repo / old).exists()); self.assertEqual((self.case.repo / new).read_bytes(), encode(self.record))
        self.assertEqual((self.case.repo / "data/reviews/old/Q101.json").read_bytes(), b"historical immutable receipt")
        self.case.commit("migrate")
        self.assertEqual(validate_pr(self.case.repo, base, "HEAD")["records_moved"], 1)
        changed = deepcopy(self.record); changed["record_revision"] += 1
        self.case.put(new, encode(changed)); self.case.commit("hidden fact change")
        with self.assertRaises(ValueError): validate_pr(self.case.repo, base, "HEAD")

    def test_50000_records_fit_256_buckets(self):
        counts = Counter(record_path(self.case.root, "Q" + str(i)).parent.name for i in range(1, 50001))
        self.assertEqual(len(counts), 256)
        self.assertTrue(all(100 < n < 300 for n in counts.values()))


if __name__ == "__main__": unittest.main()
