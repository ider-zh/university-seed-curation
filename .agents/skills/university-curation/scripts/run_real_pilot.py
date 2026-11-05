"""Private ten-university Terra-medium Research + independent Review pilot."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

from _bootstrap import ROOT, SCRIPTS
if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
from university_curation.codex_provider import run as call_codex
from university_curation.pilot_sources import CASES, replay_packet, save
from university_curation.pilot_protocol import (RULES, RESEARCH_INSTRUCTIONS, REVIEW_INSTRUCTIONS,
    RESEARCH_SCHEMA, REVIEW_SCHEMA, GROUPS, compile_record, review_gate, normalize, PILOT_SCHEMA_VERSION)
from university_curation.preferred import validate, fields, recompute

MODEL_SLOTS = threading.Semaphore(3)
REVIEW_SLOT = threading.Lock()
STATUS_LOCK = threading.Lock()


def read(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def compact(value): return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def model(prompt, schema, directory):
    with MODEL_SLOTS:
        return call_codex(prompt, schema, directory, ROOT)


def contexts(proposal, ids):
    byid = {"identity": {"identity_status": proposal["identity_status"]}}
    for key, prefix in [("locations", "location:"), ("milestones", "milestone:"), ("related_entities", "related:")]:
        byid.update({prefix + c["id"]: c for c in proposal[key]})
    return [{"context_id": key, **byid[key]} for key in ids]


def short_error(error):
    if hasattr(error, "absolute_path"):
        return {"type": type(error).__name__, "path": list(error.absolute_path), "message": error.message}
    return {"type": type(error).__name__, "message": str(error)}


def process(case, root):
    directory = root / "cases" / case["qid"]; packet = read(directory / "research-packet.json")
    task = directory / ("schema-" + PILOT_SCHEMA_VERSION)
    if (task / "outcome.json").exists():
        result = read(task / "outcome.json")
        if result["status"] == "approved": validate(read(root / result["record_path"]))
        return result
    if task.exists(): raise ValueError("Interrupted task retained; inspect before explicit recovery, never reset its revision budget")
    task.mkdir()
    previous = None; feedback = []; semantic_round = 0; recovered = None
    # Preserve the first pilot's semantic budget. Compiler failures did not reach
    # Review; Sichuan's unchanged third proposal can now be checked as-is.
    old = directory / "attempt-3"
    if (old / "proposal.json").exists():
        previous = read(old / "proposal.json")
        prior_verdicts = [read(p) for p in sorted(directory.glob("attempt-*/verdict.json"))]
        feedback = [{"stage": "previous_independent_review", "verdict": v} for v in prior_verdicts]
        if not prior_verdicts:
            recovered = old
        else:
            semantic_round = len(prior_verdicts)
    save(task / "task.json", {"schema_version": PILOT_SCHEMA_VERSION, "initial_semantic_round": semantic_round,
        "max_semantic_round": 2, "max_format_repairs_per_round": 2,
        "original_task_archived": old.exists(), "publication_allowed": False})
    attempt_number = 0; outcome = None; format_repairs = 0
    while semantic_round <= 2:
        attempt_number += 1; attempt = task / ("attempt-" + str(attempt_number)); attempt.mkdir()
        save(directory / "progress.json", {"stage": "research", "schema_version": PILOT_SCHEMA_VERSION,
            "attempt": attempt_number, "semantic_round": semantic_round, "format_repairs": format_repairs, "publication_allowed": False})
        try:
            if recovered is not None:
                proposal = previous; research_meta = read(recovered / "research/provider.json")
                save(attempt / "research-provider-reference.json", {"original_path": str(recovered / "research/provider.json"),
                    "reason": "Unmodified proposal recovered after compiler index/partial-date contract correction"})
                recovered = None
            else:
                prompt = RULES + "\n" + RESEARCH_INSTRUCTIONS + "\nONLINE SOURCES:\n" + compact(packet)
                if previous is not None:
                    prompt += "\nPRIOR PRIVATE PROPOSAL (preserve supported facts, correct actual issues; schema now supports headquarters/chair/provost/intake/campus events):\n" + compact(previous)
                    prompt += "\nVALIDATION/INDEPENDENT REVIEW FEEDBACK:\n" + compact(feedback)
                proposal, research_meta = model(prompt, RESEARCH_SCHEMA, attempt / "research")
            save(attempt / "proposal.json", proposal); previous = proposal
            record, mapping, context_ids = compile_record(proposal, packet)
            save(attempt / "candidate.json", record); save(attempt / "fact-map.json", mapping)
        except Exception as error:
            feedback = [{"stage": "research_or_schema", **short_error(error)}]
            save(attempt / "validation-failure.json", {"errors": feedback, "original_attempt_preserved": True})
            outcome = {"qid": case["qid"], "name": case["name"], "status": "unresolved", "attempt": attempt_number, "errors": feedback}
            format_repairs += 1
            if format_repairs > 2: break
            continue
        save(directory / "progress.json", {"stage": "waiting_for_independent_review", "attempt": attempt_number, "publication_allowed": False})
        try:
            with REVIEW_SLOT:
                replayed, source_checks = replay_packet(packet, root)
                save(attempt / "independent-source-replay.json", source_checks)
                source_text_changes = []
                replay_map = {s: {c["locator"]: c["text"] for c in rows} for s, rows in replayed["source_corpus"].items()}
                for i, fact in enumerate(proposal["facts"], 1):
                    for citation in fact["evidence"]:
                        text = replay_map.get(citation["source_ref"], {}).get(citation["locator"], "")
                        if citation["original_text"] and normalize(citation["original_text"]) not in normalize(text):
                            source_text_changes.append({"fact_id": "f" + str(i), "source_ref": citation["source_ref"], "locator": citation["locator"]})
                review_input = {"case": case, "sources": replayed["sources"], "source_corpus": replayed["source_corpus"],
                    "proposed_facts": [{"fact_id": "f" + str(i + 1), **fact} for i, fact in enumerate(proposal["facts"])],
                    "contexts": contexts(proposal, context_ids), "declared_coverage": proposal["coverage"],
                    "research_notes": proposal["notes"], "computed_preferred": [{"path": p, "preferred": f.get("preferred", {})} for p, f, _ in fields(record)],
                    "source_text_reproduction_warnings": source_text_changes}
                save(attempt / "review-input.json", review_input)
                save(directory / "progress.json", {"stage": "independent_review", "attempt": attempt_number, "semantic_round": semantic_round, "publication_allowed": False})
                verdict, review_meta = model(RULES + "\n" + REVIEW_INSTRUCTIONS + "\nINDEPENDENTLY RETRIEVED SOURCES AND PROPOSAL:\n" + compact(review_input), REVIEW_SCHEMA, attempt / "review")
                save(attempt / "verdict.json", verdict)
                if set(research_meta["session_ids"]) & set(review_meta["session_ids"]): raise ValueError("Research and Review session reused")
                approved = review_gate(verdict, proposal, context_ids)
                if approved:
                    now = datetime.now(timezone.utc).isoformat()
                    record["curation"]["reviewed_groups"] = GROUPS; record["curation"]["refresh_profile"] = "core-v1"
                    if record["curation"]["identity_status"] in ("in_scope", "related", "excluded"): record["update_datetime"] = now
                    record["modified_datetime"] = now; validate(record)
                    bucket = hashlib.sha256(case["qid"].encode()).hexdigest()[:3]
                    relative = Path("acceptance/records") / bucket / (case["qid"] + ".json")
                    save(root / relative, record)
                    outcome = {"qid": case["qid"], "name": case["name"], "status": "approved", "schema_version": PILOT_SCHEMA_VERSION,
                        "attempt": attempt_number, "semantic_round": semantic_round,
                        "record_path": str(relative).replace("\\", "/"), "record_sha256": sha(root / relative),
                        "approved_proposal_path": str((attempt / "proposal.json").relative_to(root)).replace("\\", "/"),
                        "facts_reviewed": len(mapping), "contexts_reviewed": len(context_ids), "source_replays": len(source_checks),
                        "source_text_reproduction_warnings": source_text_changes, "research_sessions": research_meta["session_ids"],
                        "review_sessions": review_meta["session_ids"], "human_acceptance": None, "publication_allowed": False}
                    save(task / "outcome.json", outcome); save(directory / "outcome.json", outcome)
                    print(compact(outcome), flush=True); return outcome
                feedback = [{"stage": "independent_review", "verdict": verdict}]
                outcome = {"qid": case["qid"], "name": case["name"], "status": "unresolved", "attempt": attempt_number,
                    "semantic_round": semantic_round, "review_decision": verdict["decision"],
                    "issues": [v for v in [*verdict["checks"], *verdict["context_checks"]] if v["verdict"] != "supported"]}
                semantic_round += 1; format_repairs = 0
        except Exception as error:
            feedback = [{"stage": "independent_review_or_replay", **short_error(error)}]
            save(attempt / "review-failure.json", {"errors": feedback, "original_attempt_preserved": True})
            outcome = {"qid": case["qid"], "name": case["name"], "status": "unresolved", "attempt": attempt_number, "errors": feedback}
            break  # Infrastructure failure never consumes semantic budget or starts blind new research.
    outcome["schema_version"] = PILOT_SCHEMA_VERSION
    save(task / "outcome.json", outcome); save(directory / "outcome.json", outcome)
    print(compact(outcome), flush=True); return outcome


def report(root):
    outcomes = [read(root / "cases" / c["qid"] / "outcome.json") for c in CASES if (root / "cases" / c["qid"] / "outcome.json").exists()]
    records = []; per_case = []
    for outcome in outcomes:
        detail = dict(outcome)
        if outcome["status"] == "approved":
            record = read(root / outcome["record_path"]); validate(record)
            if sha(root / outcome["record_path"]) != outcome["record_sha256"]: raise ValueError("Approved record changed")
            records.append(record)
            fs = list(fields(record)); unknown = []
            for path, field, _ in fs:
                if "preferred" not in field: continue
                chosen = next(c for c in field["candidates"] if c["id"] == field["preferred"]["candidate_id"])
                if chosen.get("period_status") == "not_stated": unknown.append(path)
            detail.update({"field_sets": len(fs), "candidates": sum(len(f["candidates"]) for _, f, _ in fs),
                "preferred_undated_fields": unknown, "milestones": len(record.get("history", {}).get("milestones", [])),
                "leadership_roles": list(record.get("leadership", {})), "population_metrics": list(record.get("population", {})),
                "finance_metrics": list(record.get("finance", {})), "locations": len(record.get("locations", [])),
                "languages": sorted({s["language"] for s in record["sources"].values() if s["kind"] == "wikipedia"})})
        per_case.append(detail)
    providers = [(path, read(path)) for path in (root / "cases").rglob("provider.json")]
    intervals = []
    for _, meta in providers:
        intervals += [(meta["started_at"], 1), (meta["ended_at"], -1)]
    active = peak = 0
    for _, change in sorted(intervals, key=lambda v: (v[0], v[1])):
        active += change; peak = max(peak, active)
    if peak > 3: raise ValueError("Global model concurrency limit exceeded")
    sessions = [s for _, m in providers for s in m["session_ids"]]
    if len(sessions) != len(set(sessions)): raise ValueError("Model sessions reused across cases/roles")
    usage = {key: sum(m.get("usage", {}).get(key, 0) for _, m in providers) for key in ("input_tokens", "cached_input_tokens", "output_tokens")}
    quality = {"schema_version": PILOT_SCHEMA_VERSION, "model": "gpt-6.1-terra", "reasoning_effort": "medium",
        "status": "completed_for_human_acceptance" if len(records) == len(CASES) else "partial_results",
        "case_count": len(CASES), "processed_outcomes": len(outcomes), "approved_records": len(records),
        "unresolved_records": len(outcomes) - len(records), "model_calls": len(providers), "peak_model_concurrency": peak,
        "review_concurrency_limit": 1, "distinct_model_sessions": len(sessions), "token_usage": usage,
        "per_case": per_case, "checks": {"all_delivered_records_schema_valid": True,
            "all_delivered_facts_and_contexts_independently_reviewed": True, "source_revisions_independently_retrieved": True,
            "missing_values_omitted": True, "preferred_generated_deterministically": True, "original_failed_attempts_retained": True,
            "no_per_entity_manual_fact_repairs": True, "raw_sources_private": True},
        "limitations": ["A purposive ten-case acceptance sample is not a global precision/recall estimate.",
            "Research and Review use the same model in distinct sessions; model-error correlation remains possible.",
            "Wikipedia and Wikidata are not independent fact-source families.",
            "Data is limited to the supplied bounded source packets; missing fields and schema representation gaps remain visible.",
            "Provider model is explicitly requested and accepted by CLI; reported runtime model telemetry may be absent."],
        "human_acceptance": None, "publication_allowed": False}
    acceptance = root / "acceptance"; acceptance.mkdir(exist_ok=True)
    save(acceptance / "universities.complete.json", records); save(acceptance / "quality_report.json", quality)
    save(root / "pilot-status.json", {k: quality[k] for k in ("status", "processed_outcomes", "approved_records", "unresolved_records", "model_calls", "peak_model_concurrency")})
    return quality


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--root", required=True); parser.add_argument("--qids", nargs="*"); parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args(); root = Path(args.root).resolve()
    if ".private" not in root.parts: raise ValueError("Real pilot output must remain private until human acceptance")
    if args.report_only:
        print(compact({k: v for k, v in report(root).items() if k != "per_case"})); raise SystemExit(0)
    selection = [c for c in CASES if not args.qids or c["qid"] in args.qids]
    code_files = [Path(__file__), SCRIPTS / "_bootstrap.py", *[ROOT / "src/university_curation" / name for name in ("pilot_protocol.py", "pilot_sources.py", "codex_provider.py", "preferred.py", "schema_v02.py", "sources.py")]]
    code = {str(p.relative_to(ROOT)).replace("\\", "/"): sha(p) for p in code_files}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    execution = root / "executions" / stamp; execution.mkdir(parents=True)
    save(execution / "versions.json", {"model": "gpt-6.1-terra", "effort": "medium", "max_model_calls": 3,
        "review_concurrency": 1, "code": code, "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "schema_sha256": sha(ROOT / ("schemas/university.v" + PILOT_SCHEMA_VERSION + ".schema.json")), "human_acceptance": None, "publication_allowed": False})
    for file in code_files:
        target = execution / file.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(file, target)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(process, case, root): case for case in selection}
        for future in as_completed(futures):
            case = futures[future]
            try: future.result()
            except Exception as error:
                save(root / "cases" / case["qid"] / "outcome.json", {"qid": case["qid"], "name": case["name"], "status": "unresolved", "error": str(error)})
            with STATUS_LOCK: report(root)
