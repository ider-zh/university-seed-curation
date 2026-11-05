"""Audit private pilot receipts and prepare a source-text-free acceptance package."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
from run_real_pilot import report, read, sha
from university_curation.pilot_protocol import compile_record, review_gate, GROUPS, PILOT_SCHEMA_VERSION
from university_curation.pilot_sources import CASES, save
from university_curation.preferred import fields, validate, recompute


def finalize(root):
    quality = report(root); accepted = root / "acceptance"; audit = []; failures = []; source_gaps = []
    for case in CASES:
        directory = root / "cases" / case["qid"]
        packet = read(directory / "research-packet.json")
        source_gaps += [{"qid": case["qid"], **f} for f in packet["retrieval_failures"]]
        outcome_path = directory / "outcome.json"
        if not outcome_path.exists(): continue
        outcome = read(outcome_path)
        for verdict_path in sorted(directory.rglob("verdict.json")):
            verdict = read(verdict_path)
            errors = [c for c in verdict["checks"] + verdict["context_checks"] if c["verdict"] != "supported"]
            if errors:
                failures.append({"qid": case["qid"], "stage": "independent_review", "attempt": str(verdict_path.parent.relative_to(directory)).replace("\\", "/"),
                    "decision": verdict["decision"], "issues": errors, "revision_instructions": verdict["revision_instructions"]})
        for error_path in sorted(directory.rglob("validation-failure.json")):
            failures.append({"qid": case["qid"], "stage": "schema_or_transport", "attempt": str(error_path.parent.relative_to(directory)).replace("\\", "/"),
                "issues": read(error_path)["errors"]})
        if outcome["status"] != "approved": continue
        if outcome.get("source_packet_path"): packet = read(root / outcome["source_packet_path"])
        proposal_path = root / outcome["approved_proposal_path"]; attempt = proposal_path.parent
        proposal = read(proposal_path); record = read(root / outcome["record_path"])
        validate(record)
        rebuilt, mapping, context_ids = compile_record(proposal, packet)
        actual = dict(record); actual.pop("update_datetime", None); actual.pop("modified_datetime", None)
        actual["curation"] = {"identity_status": actual["curation"]["identity_status"]}
        if rebuilt != actual: raise ValueError("Canonical record differs from script-compiled reviewed proposal: " + case["qid"])
        if recompute(record) != record: raise ValueError("Non-deterministic preferred")
        verdict = read(attempt / "verdict.json")
        if not review_gate(verdict, proposal, context_ids): raise ValueError("Invalid independent approval")
        replays = read(attempt / "independent-source-replay.json")
        if {r["source_ref"] for r in replays} != set(packet["sources"]): raise ValueError("Incomplete source replay")
        for replay in replays:
            if replay["revision_id"] != packet["sources"][replay["source_ref"]]["revision_id"]: raise ValueError("Source revision mismatch")
            if "independent-review-cache" not in Path(replay["cache_path"]).parts: raise ValueError("Review reused Research raw cache")
        if not set(outcome["research_sessions"]).isdisjoint(outcome["review_sessions"]): raise ValueError("Self-review")
        audit.append({"qid": case["qid"], "schema_valid": True, "canonical_matches_reviewed_proposal": True,
            "facts_checked": len(mapping), "contexts_checked": len(context_ids), "source_revisions_replayed": len(replays),
            "coverage": proposal["coverage"], "review_quality_notes": verdict["quality_notes"],
            "source_text_reproduction_warnings": outcome["source_text_reproduction_warnings"], "review_policy": outcome.get("review_policy", "original-strict"), "inferred_facts": outcome.get("inferred_facts", [])})
    quality["review_policy"] = {"version": "source-grounded-flexible-v2", "source": "docs/review-policy-v2.md",
        "inauguration_year_as_term_start_allowed": True, "campus_opening_as_valid_from_allowed": True,
        "original_strict_verdicts_preserved": True, "changes_follow_operator_steering": True}
    interpretations = [{"qid": item["qid"], **fact} for item in quality["per_case"] for fact in item.get("inferred_facts", [])]
    quality["reasonable_inference_annotations"] = interpretations
    quality["limitations"].append("Reasonable concept adaptation is allowed; source wording and inference annotations distinguish it from direct assertions. Some statistical scope qualifiers remain in evidence text rather than normalized fields.")
    save(accepted / "interpretations.json", interpretations)
    quality["deterministic_receipt_audit"] = audit
    quality["source_availability_gaps"] = source_gaps
    quality["failed_attempts"] = failures
    quality["schema_trial_adjustments"] = [
        {"version": "0.2.1", "changes": ["Partial month/day dates without invented day boundaries", "Campus opening/teaching start/cooperation agreement/construction completion events", "Student intake distinct from enrollment", "Provost and unspecific chair distinct from president/board chair", "Headquarters distinct from office"]},
        {"component": "transport_compiler", "correction": "Conflict fact indexes explicitly zero-based; unchanged proposals are recompiled, never hand-repaired."}]
    quality["aggregate_totals"] = {"facts_reviewed": sum(o["facts_checked"] for o in audit),
        "contexts_reviewed": sum(o["contexts_checked"] for o in audit), "source_revision_replays": sum(o["source_revisions_replayed"] for o in audit),
        "review_rejections": sum(f["stage"] == "independent_review" for f in failures),
        "schema_transport_failures": sum(f["stage"] == "schema_or_transport" for f in failures)}
    quality["provider_verification"] = {"requested_model": "gpt-6.1-terra", "requested_reasoning_effort": "medium",
        "cli_arguments_accepted_and_calls_completed": True, "runtime_model_name_reported": False,
        "preflight_calls_outside_case_counts": 1, "review_role_sessions_are_fresh": True}
    tests = root / "verification-tests.json"
    if tests.exists(): quality["offline_tests"] = read(tests)
    inspection = []
    for case in CASES:
        directory = root / "cases" / case["qid"]
        if not (directory / "outcome.json").exists(): continue
        outcome = read(directory / "outcome.json")
        if outcome["status"] == "approved":
            inspection.append({"status": "approved", "record": read(root / outcome["record_path"]), "inferred_facts": outcome.get("inferred_facts", [])})
        else:
            candidate_path = directory / "policy-v2/candidate.json"
            if not candidate_path.exists():
                choices = sorted((directory / ("schema-" + PILOT_SCHEMA_VERSION)).glob("attempt-*/candidate.json"), key=lambda p: int(p.parent.name.split("-")[-1]))
                candidate_path = choices[-1] if choices else None
            if candidate_path:
                draft = read(candidate_path)
                draft["curation"] = {"identity_status": "needs_review"}; draft.pop("update_datetime", None)
                for _, field, _ in fields(draft):
                    for candidate in field["candidates"]: candidate["verification"] = "insufficient_evidence"
                draft = recompute(draft); validate(draft)
                inspection.append({"status": "unresolved_not_approved", "record": draft, "review_issues": outcome.get("issues", []),
                    "warning": "Private inspection draft; source-derived values are proposals, not accepted facts. Not part of approved records."})
    save(accepted / "universities.inspection.json", inspection)
    quality["inspection_records"] = len(inspection)
    save(accepted / "quality_report.json", quality)
    save(accepted / "receipt-audit.json", audit)
    lines = ["# University acceptance pilot", "", f"Approved: {quality['approved_records']}/10. Schema: {PILOT_SCHEMA_VERSION}. Human acceptance pending; publication disabled.", "",
        "Terra medium; maximum three model calls shared across roles. One serial Review role, fresh sessions, separate revision-bound source cache.", "",
        "| QID | Institution | Status | Facts | Milestones | Population metrics | Finance metrics | Languages |", "| --- | --- | --- | ---: | ---: | --- | --- | --- |"]
    for item in quality["per_case"]:
        lines.append("| " + " | ".join(str(v) for v in [item["qid"], item["name"], item["status"], item.get("facts_reviewed", ""), item.get("milestones", ""),
            ", ".join(item.get("population_metrics", [])), ", ".join(item.get("finance_metrics", [])), ", ".join(item.get("languages", []))]) + " |")
    lines += ["", "## Audit", "", f"{quality['aggregate_totals']['facts_reviewed']} facts and {quality['aggregate_totals']['contexts_reviewed']} contexts independently checked. Peak model concurrency: {quality['peak_model_concurrency']}.", "",
        "The full JSON retains all approved candidates, preferred pointers, original names, quantities/currency/periods, source revisions and short evidence. Missing business fields are omitted.", "",
        "## Limits", "", *["- " + text for text in quality["limitations"]], "",
        "- This is a bounded-source extraction pilot, not an exhaustive extraction of every article fact or a verified global accuracy estimate.",
        "- CLI accepted the requested Terra/medium configuration; runtime model-name telemetry was absent.",
        "- Failed proposals and original sources remain private and are not bundled. Detailed failure reasons and source availability gaps are in quality_report.json."]
    (accepted / "QUALITY_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    shutil.copy2(ROOT / "docs/review-policy-v2.md", accepted / "review-policy-v2.md")
    schema_target = accepted / "schema.json"; shutil.copy2(ROOT / ("schemas/university.v" + PILOT_SCHEMA_VERSION + ".schema.json"), schema_target)
    files = [p for p in accepted.rglob("*") if p.is_file() and p.name not in ("manifest.json", "acceptance.zip")]
    manifest = {"dataset": "university-real-ten-private-pilot", "schema_version": PILOT_SCHEMA_VERSION,
        "human_acceptance": None, "publication_allowed": False,
        "files": [{"path": p.relative_to(accepted).as_posix(), "sha256": sha(p), "bytes": p.stat().st_size} for p in sorted(files)]}
    save(accepted / "manifest.json", manifest)
    archive = accepted.parent / "university-10-acceptance.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        for path in files + [accepted / "manifest.json"]: output.write(path, path.relative_to(accepted).as_posix())
    return {"approved": len(audit), "facts": quality["aggregate_totals"]["facts_reviewed"], "zip": str(archive)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--root", required=True); args = parser.parse_args()
    root = Path(args.root).resolve()
    if ".private" not in root.parts: raise ValueError("Acceptance artifacts must remain private")
    print(json.dumps(finalize(root)))
