from copy import deepcopy
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from university_curation.attestations import init_key, policy, sign, verify, sha, load_json
from university_curation.pr_export import record_relative, scope, verify_files, validate_pr, install
from university_curation.records import encode, ROOT
from university_curation.pilot_protocol import compile_record, GROUPS
from university_curation.pilot_audit import provider
from test_pilot_protocol import fixture

NOW = "2026-11-05T04:00:00Z"


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.repo = self.root / "repo"; self.repo.mkdir()
        self.key = self.root / ".private/key.pem"
        self.public = init_key(self.key); self.trust = policy(ROOT, self.public, "example/universities")
        self.git("init", "-q"); self.git("config", "user.name", "Offline fixture"); self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "core.autocrlf", "false")
        for name in ("schemas/university.v0.2.1.schema.json", "docs/review-policy-v2.md"):
            dest = self.repo / name; dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((ROOT / name).read_bytes())
        self.put(".curation/review-trust.json", encode(self.trust)); self.commit("base")
        self.base = self.git("rev-parse", "HEAD").decode().strip()
        proposal, packet = fixture(); self.record, mapping, contexts = compile_record(proposal, packet)
        self.record["curation"].update({"reviewed_groups": GROUPS, "refresh_profile": "core-v1"})
        self.record["modified_datetime"] = NOW; self.record["update_datetime"] = NOW
        self.review = {"decision": "approve", "facts_checked": len(mapping), "contexts_checked": len(contexts),
            "source_revisions_checked": len(self.record["sources"]), "research_sessions": ["fixture-research"],
            "review_session": "fixture-review", "reviewed_at": NOW, "model": "gpt-6.1-terra", "reasoning_effort": "medium",
            "runtime_model_reported": False, "inferences": [], "private_evidence_sha256": "a" * 64,
            "review_output_sha256": "b" * 64, "attestation_kind": "local_coordinator_verified_private_traces"}

    def tearDown(self): self.temp.cleanup()
    def git(self, *args): return subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.PIPE)
    def put(self, name, data):
        path = self.repo / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    def commit(self, message): self.git("add", "-A"); self.git("commit", "-qm", message)

    def bundle(self, record=None, review=None, accepted=True):
        record = record or self.record; review = review or self.review
        name = record_relative(record["qid"]); data = encode(record)
        receipt_name = "data/reviews/offline-fixture/" + record["qid"] + ".json"
        receipt = {"type": "university-review-v1", "repository": self.trust["repository"], "qid": record["qid"],
            "base_commit": self.base, "record_path": name, "record_sha256": sha(data), "baseline_sha256": "absent",
            "schema_version": "0.2.1", "schema_sha256": self.trust["schemas"]["0.2.1"],
            "review_policy": self.trust["review_policy"], "review": review}
        receipt_bytes = encode(sign(receipt, self.key, self.trust))
        rows = [{"qid": record["qid"], "record_path": name, "record_sha256": sha(data),
            "receipt_path": receipt_name, "receipt_sha256": sha(receipt_bytes)}]
        content = scope(rows, {record["qid"]: receipt}, self.trust)
        approval = {"status": "accepted" if accepted else "pending", "content_scope_sha256": content}
        if accepted: approval.update({"human_actor": "offline-fixture-operator", "human_approval_ref": "test-only:not-a-real-approval"})
        manifest = {"type": "university-batch-v1", "repository": self.trust["repository"], "batch_id": "offline-fixture",
            "base_commit": self.base, "created_at": NOW, "content_scope_sha256": content, "acceptance": approval, "records": rows}
        return {name: data, receipt_name: receipt_bytes, "data/batches/offline-fixture.json": encode(sign(manifest, self.key, self.trust))}

    def test_signed_accepted_initial_import_and_exact_git_head(self):
        files = self.bundle()
        result = verify_files(self.repo, self.base, files, self.trust)
        self.assertTrue(result["human_accepted"])
        for path, data in files.items(): self.put(path, data)
        self.commit("data")
        checked = validate_pr(self.repo, self.base, "HEAD")
        self.assertEqual(checked["qids"], ["Q101"])
        self.assertEqual(checked["head_commit"], self.git("rev-parse", "HEAD").decode().strip())

    def test_tampered_record_signature_and_unknown_or_revoked_key_rejected(self):
        files = self.bundle(); record_name = record_relative("Q101")
        changed = dict(files); changed[record_name] += b" "
        with self.assertRaises(ValueError): verify_files(self.repo, self.base, changed, self.trust)
        signed = sign({"test": 1}, self.key, self.trust); signed["payload"]["test"] = 2
        with self.assertRaises(ValueError): verify(signed, self.trust)
        signed = sign({"test": 1}, self.key, self.trust); signed["key_id"] = "unknown"
        with self.assertRaises(ValueError): verify(signed, self.trust)
        revoked = deepcopy(self.trust); revoked["keys"][self.public["key_id"]]["status"] = "revoked"
        with self.assertRaises(ValueError): verify_files(self.repo, self.base, files, revoked)

    def test_pending_or_wrong_human_acceptance_cannot_publish(self):
        files = self.bundle(accepted=False)
        self.assertFalse(verify_files(self.repo, self.base, files, self.trust, require_acceptance=False)["human_accepted"])
        with self.assertRaises(ValueError): verify_files(self.repo, self.base, files, self.trust)
        path = "data/batches/offline-fixture.json"; manifest = verify(load_json(self.bundle()[path]), self.trust)
        manifest["acceptance"]["content_scope_sha256"] = "0" * 64
        files = self.bundle(); files[path] = encode(sign(manifest, self.key, self.trust))
        with self.assertRaises(ValueError): verify_files(self.repo, self.base, files, self.trust)

    def test_same_session_wrong_counts_or_rejected_review_cannot_be_signed_into_acceptance(self):
        for patch in ({"review_session": "fixture-research"}, {"facts_checked": 1}, {"contexts_checked": 99},
                      {"source_revisions_checked": 0}, {"decision": "request_changes"}, {"model": "another-model"}):
            review = {**self.review, **patch}
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                verify_files(self.repo, self.base, self.bundle(review=review), self.trust)

    def test_stale_base_and_missing_manifest_member_fail_closed(self):
        files = self.bundle(); self.put("README.md", b"new base"); self.commit("advance")
        newer = self.git("rev-parse", "HEAD").decode().strip()
        with self.assertRaises(ValueError): verify_files(self.repo, newer, files, self.trust)
        files.pop(record_relative("Q101"))
        with self.assertRaises(ValueError): verify_files(self.repo, self.base, files, self.trust)

    def test_code_and_trust_cannot_change_in_a_data_pr(self):
        for path, data in self.bundle().items(): self.put(path, data)
        attacker = deepcopy(self.trust); attacker["keys"] = {}
        self.put(".curation/review-trust.json", encode(attacker)); self.commit("mixed data and trust")
        with self.assertRaises(ValueError): validate_pr(self.repo, self.base, "HEAD")

    def test_wrong_bucket_executable_blob_and_raw_files_fail(self):
        files = self.bundle(); original = record_relative("Q101")
        wrong = dict(files); wrong["data/universities/000/Q101.json"] = wrong.pop(original)
        with self.assertRaises(ValueError): verify_files(self.repo, self.base, wrong, self.trust)
        for path, data in files.items(): self.put(path, data)
        self.commit("data"); self.git("update-index", "--chmod=+x", original)
        self.git("commit", "-qm", "bad mode")
        with self.assertRaises(ValueError): validate_pr(self.repo, self.base, "HEAD")
        files["data/raw/page.html"] = b"unreviewed source"
        with self.assertRaises(ValueError): verify_files(self.repo, self.base, files, self.trust)

    def test_install_is_gated_preflighted_and_idempotent(self):
        output = self.root / ".private/bundle"; output.mkdir(parents=True)
        files = self.bundle(accepted=False)
        def write(files):
            for p, data in files.items():
                dest = output / p; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(data)
            (output / "preview.json").write_bytes(encode({"base_commit": self.base, "files": {p: sha(d) for p, d in files.items()}}))
        write(files)
        with self.assertRaises(ValueError): install(self.repo, output)
        self.assertFalse((self.repo / "data").exists())
        files = self.bundle(); write(files)
        target = self.repo / record_relative("Q101"); target.parent.mkdir(parents=True); target.write_text("uncommitted work")
        with self.assertRaises(ValueError): install(self.repo, output)
        self.assertFalse((self.repo / "data/batches").exists())
        target.unlink()
        self.assertEqual(install(self.repo, output)["status"], "installed_for_data_pr")
        self.assertEqual(install(self.repo, output)["status"], "installed_for_data_pr")

    def test_code_only_pr_and_private_file_detection(self):
        self.put("README.md", b"code documentation"); self.commit("code")
        self.assertEqual(validate_pr(self.repo, self.base, "HEAD")["status"], "code_only")
        self.put(".private/secret.txt", b"fixture"); self.commit("bad private file")
        with self.assertRaises(ValueError): validate_pr(self.repo, self.base, "HEAD")

    def test_strict_json_and_platform_independent_schema_hash(self):
        for data in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}'):
            with self.assertRaises(ValueError): load_json(data)
        schema = ROOT / "schemas/university.v0.2.1.schema.json"
        self.assertEqual(sha(encode(load_json(schema.read_bytes().replace(b"\r\n", b"\n")))) , self.trust["schemas"]["0.2.1"])

    def test_provider_prompt_crlf_and_real_event_result_binding(self):
        path = self.root / ".private/provider"; path.mkdir(parents=True)
        result = {"value": 1}; prompt = "line one\nline two\n"
        (path / "prompt.txt").write_bytes(prompt.replace("\n", "\r\n").encode())
        (path / "output.schema.json").write_bytes(encode({"type": "object"}))
        (path / "result.json").write_bytes(encode(result))
        events = [{"type": "thread.started", "thread_id": "fixture-session"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(result)}}, {"type": "turn.completed"}]
        (path / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
        meta = {"returncode": 0, "fresh_session": True, "tool_events": [], "requested_model": "gpt-6.1-terra", "reasoning_effort": "medium",
            "session_ids": ["fixture-session"], "reported_models": [], "prompt_sha256": sha(prompt.encode()),
            "schema_sha256": sha((path / "output.schema.json").read_bytes())}
        (path / "provider.json").write_bytes(encode(meta))
        self.assertEqual(provider(path, self.trust)[0], result)
        (path / "result.json").write_bytes(encode({"value": 2}))
        with self.assertRaises(ValueError): provider(path, self.trust)
