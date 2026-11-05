"""One explicit policy-change re-review of unresolved private pilot cases."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
from run_real_pilot import read, compact, model, contexts, sha, report
from university_curation.pilot_protocol import RULES, REVIEW_INSTRUCTIONS, REVIEW_SCHEMA, compile_record, review_gate, GROUPS, PILOT_SCHEMA_VERSION, RESEARCH_SCHEMA
from university_curation.pilot_sources import CASES, replay_packet, save
from university_curation.sources import Cache
from university_curation.source_requests import augment_packet
from university_curation.preferred import fields, validate


def recover_unit_facts(proposal, packet, task, root):
    requests = []
    for row in packet["source_corpus"]["s1"]:
        if not row["locator"].startswith("claim:"): continue
        value = json.loads(row["text"]).get("value", {})
        unit = value.get("unit", "") if isinstance(value, dict) else ""
        if "/entity/Q" in unit:
            request = {"qid": unit.rsplit("/", 1)[-1], "purpose": "quantity_unit"}
            if request not in requests: requests.append(request)
    cache = Cache(root / "source-cache", maxlag=30)
    packet, log = augment_packet(packet, requests, cache)
    save(task / "shared-unit-query-log.json", log)
    if not any(not item.get("already_in_packet") for item in log): return proposal, packet, [], 0
    shape = {"type": "object", "additionalProperties": False, "required": ["new_facts", "source_requests", "notes"],
        "properties": {"new_facts": RESEARCH_SCHEMA["properties"]["facts"], "notes": {"type": "array", "items": {"type": "string"}},
            "source_requests": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                "required": ["qid", "purpose"], "properties": {"qid": {"type": "string"}, "purpose": {"enum": ["quantity_unit", "linked_identity", "geography"]}}}}}}
    sessions = []; added = 0
    from university_curation.pilot_protocol import RESEARCH_INSTRUCTIONS
    for turn in range(3):
        instructions = "ROLE: Research supplement, one university. The manager resolved quantity-unit QIDs via the shared online cache. Recover numerical observations previously omitted solely because units were unknown. Only add finance/population facts using already-defined contexts; do not rewrite or remove any existing fact. Retain original periods/currencies. Cite both original value and unit evidence where needed. Return source_requests for a still-missing necessary linked QID; the script will query Wikidata using the common cache and return it. Requests are bounded to existing evidence, at most eight; no arbitrary browsing. Do not repeat existing observations. Empty new_facts is valid if nothing is supported. Reasonable source-grounded interpretation is allowed and independently reviewed."
        response, meta = model(RULES + "\n" + RESEARCH_INSTRUCTIONS + "\n" + instructions + "\nEXISTING PROPOSAL:\n" + compact(proposal) + "\nUPDATED ONLINE SOURCES:\n" + compact(packet), shape, task / ("unit-research-" + str(turn)))
        sessions += meta["session_ids"]
        save(task / ("unit-response-" + str(turn) + ".json"), response)
        for fact in response["new_facts"]:
            if not fact["field"].startswith(("population.", "finance.")): raise ValueError("Supplement exceeded quantitative field scope")
            def signature(f): return (f["field"], f["context"], f["value_state"], compact(json.loads(f["value_json"])) if f["value_json"] else "", compact(json.loads(f["period_json"])) if f["period_json"] else "")
            existing = next((f for f in proposal["facts"] if signature(f) == signature(fact)), None)
            if existing is None: proposal["facts"].append(fact); added += 1
            else:
                for citation in fact["evidence"]:
                    if citation not in existing["evidence"]: existing["evidence"].append(citation)
        proposal["notes"] += response["notes"]
        if not response["source_requests"]: break
        if turn == 2: raise ValueError("Linked lookup model-turn budget exhausted")
        packet, more = augment_packet(packet, response["source_requests"], cache)
        log += more; save(task / "shared-unit-query-log.json", log)
    return proposal, packet, sessions, added


def process(case, root):
    directory = root / "cases" / case["qid"]; old = read(directory / "outcome.json")
    task = directory / "policy-v2"
    if (task / "outcome.json").exists(): return read(task / "outcome.json")
    if task.exists(): raise ValueError("Interrupted policy review retained; explicit recovery required")
    task.mkdir()
    save(task / "previous-outcome.json", old)
    packet = read(directory / "research-packet.json")
    if old["status"] == "approved": save(task / "previous-record.json", read(root / old["record_path"]))
    candidates = sorted((directory / ("schema-" + PILOT_SCHEMA_VERSION)).glob("attempt-*/candidate.json"), key=lambda p: int(p.parent.name.split("-")[-1]), reverse=True)
    if not candidates: raise ValueError("No structurally valid proposal available for policy-only review")
    source_attempt = (root / old["approved_proposal_path"]).parent if old["status"] == "approved" else candidates[0].parent
    proposal = read(source_attempt / "proposal.json")
    proposal, packet, supplement_sessions, new_unit_facts = recover_unit_facts(proposal, packet, task, root)
    save(task / "research-packet.json", packet)
    record, mapping, context_ids = compile_record(proposal, packet)
    save(task / "proposal.json", proposal); save(task / "candidate.json", record); save(task / "fact-map.json", mapping)
    research_provider = source_attempt / "research/provider.json"
    if not research_provider.exists(): research_provider = Path(read(source_attempt / "research-provider-reference.json")["original_path"])
    research_meta = read(research_provider)
    research_meta["session_ids"] += supplement_sessions
    save(task / "research-provider-reference.json", {"original_path": str(research_provider), "reason": "Same Research proposal, new operator-authorized review policy"})
    replayed, source_checks = replay_packet(packet, root); save(task / "independent-source-replay.json", source_checks)
    review_input = {"case": case, "sources": replayed["sources"], "source_corpus": replayed["source_corpus"],
        "proposed_facts": [{"fact_id": "f" + str(i + 1), **f} for i, f in enumerate(proposal["facts"])],
        "contexts": contexts(proposal, context_ids), "declared_coverage": proposal["coverage"], "research_notes": proposal["notes"],
        "computed_preferred": [{"path": p, "preferred": f.get("preferred", {})} for p, f, _ in fields(record)]}
    save(task / "review-input.json", review_input)
    policy = (ROOT / "docs/review-policy-v2.md").read_text(encoding="utf-8")
    save(task / "policy.json", {"version": "source-grounded-flexible-v2", "sha256": sha(ROOT / "docs/review-policy-v2.md"), "text": policy,
        "reason": "Operator explicitly relaxed concept adaptation during this pilot; retain original strict decisions", "semantic_revisions_reset": False})
    save(directory / "progress.json", {"stage": "policy_v2_independent_review", "publication_allowed": False})
    review_schema = deepcopy(REVIEW_SCHEMA)
    checks = review_schema["properties"]["checks"]["items"]
    checks["properties"]["support_basis"] = {"enum": ["direct", "reasonable_inference", "unsupported"]}
    checks["required"].append("support_basis")
    verdict, review_meta = model(RULES + "\n" + REVIEW_INSTRUCTIONS + "\nLATEST OPERATOR REVIEW POLICY (takes precedence over exact-concept requirements):\n" + policy + "\nFor every fact return support_basis=direct or reasonable_inference (explain inference in reason_en); unsupported for failed checks.\nSOURCES AND UNTRUSTED PROPOSAL:\n" + compact(review_input), review_schema, task / "review")
    save(task / "verdict.json", verdict)
    if not set(research_meta["session_ids"]).isdisjoint(review_meta["session_ids"]): raise ValueError("Self-review")
    approved = review_gate(verdict, proposal, context_ids)
    inference_rows = []
    byid = {m["fact_id"]: m for m in mapping}
    for check in verdict["checks"]:
        if check["verdict"] == "supported" and check["support_basis"] == "unsupported": raise ValueError("Contradictory support basis")
        if check["support_basis"] == "reasonable_inference":
            inference_rows.append({**byid[check["fact_id"]], "basis": "reasonable_inference", "value": json.loads(proposal["facts"][int(check["fact_id"][1:]) - 1]["value_json"]) if proposal["facts"][int(check["fact_id"][1:]) - 1]["value_json"] else {"value_state": "unknown"}, "reason_en": check["reason_en"]})
    save(task / "interpretations.json", inference_rows)
    outcome = {"qid": case["qid"], "name": case["name"], "status": "unresolved", "schema_version": PILOT_SCHEMA_VERSION,
        "review_policy": "source-grounded-flexible-v2", "prior_strict_status": old["status"], "policy_only_rereview": True,
        "source_packet_path": (task / "research-packet.json").relative_to(root).as_posix(), "unit_supplement_facts": new_unit_facts, "inferred_facts": inference_rows, "review_decision": verdict["decision"], "issues": [c for c in verdict["checks"] + verdict["context_checks"] if c["verdict"] != "supported"],
        "human_acceptance": None, "publication_allowed": False}
    if approved:
        now = datetime.now(timezone.utc).isoformat()
        record["curation"].update({"reviewed_groups": GROUPS, "refresh_profile": "core-v1"})
        if record["curation"]["identity_status"] in ("in_scope", "related", "excluded"): record["update_datetime"] = now
        record["modified_datetime"] = now; validate(record)
        bucket = hashlib.sha256(case["qid"].encode()).hexdigest()[:3]
        relative = Path("acceptance/records") / bucket / (case["qid"] + ".json"); save(root / relative, record)
        outcome.update({"status": "approved", "record_path": relative.as_posix(), "record_sha256": sha(root / relative),
            "approved_proposal_path": (task / "proposal.json").relative_to(root).as_posix(),
            "facts_reviewed": len(mapping), "contexts_reviewed": len(context_ids), "source_replays": len(source_checks),
            "source_text_reproduction_warnings": [], "research_sessions": research_meta["session_ids"], "review_sessions": review_meta["session_ids"]})
    if not approved and old["status"] == "approved":
        stale = root / old["record_path"]
        if stale.exists(): stale.unlink()  # Exact pilot artifact; preserved above, never a recursive delete.
    save(task / "outcome.json", outcome); save(directory / "outcome.json", outcome)
    print(compact(outcome), flush=True); return outcome


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--root", required=True); args = parser.parse_args()
    root = Path(args.root).resolve()
    if ".private" not in root.parts: raise ValueError("Private outputs only")
    for case in CASES:
        try: process(case, root)
        except Exception as error: print(compact({"qid": case["qid"], "policy_review_error": str(error)}), flush=True)
        report(root)
