"""Offline bridge from actual private pilot traces to an exportable approval."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path

from .attestations import load_json, private_path, sha
from .pilot_protocol import compile_record, review_gate, RULES, REVIEW_INSTRUCTIONS, REVIEW_SCHEMA
from .pilot_sources import wikidata_corpus, wikipedia_corpus
from .preferred import validate, recompute, fields
from .records import ROOT, encode, instant
from .sources import Cache


def read(path): return load_json(Path(path).read_bytes())


def inside(root, path):
    path = Path(path)
    if not path.is_absolute(): path = root / path
    path = path.resolve()
    if not path.is_relative_to(root): raise ValueError("Private artifact escapes pilot root")
    return path


def provider(path, trust):
    meta = read(path / "provider.json")
    if meta["returncode"] != 0 or not meta["fresh_session"] or meta["tool_events"]:
        raise ValueError("Unsuccessful or unsealed model session")
    if meta["requested_model"] != trust["model"] or meta["reasoning_effort"] != trust["reasoning_effort"]:
        raise ValueError("Unexpected model configuration")
    if len(meta["session_ids"]) != 1: raise ValueError("Ambiguous model session")
    if meta.get("reported_models") and meta["reported_models"] != [trust["model"]]: raise ValueError("Reported model mismatch")
    if sha((path / "prompt.txt").read_text(encoding="utf-8").encode()) != meta["prompt_sha256"]: raise ValueError("Prompt changed after run")
    if sha((path / "output.schema.json").read_bytes()) != meta["schema_sha256"]: raise ValueError("Output schema changed after run")
    import jsonschema
    result = read(path / "result.json")
    jsonschema.Draft202012Validator(read(path / "output.schema.json")).validate(result)
    events = [load_json(line) for line in (path / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if [e["thread_id"] for e in events if e.get("type") == "thread.started"] != meta["session_ids"]:
        raise ValueError("Provider trace session mismatch")
    if not any(e.get("type") == "turn.completed" for e in events): raise ValueError("Incomplete provider trace")
    if any(e.get("item", {}).get("type") in ("command_execution", "mcp_tool_call", "web_search", "file_change") for e in events):
        raise ValueError("Unsealed tools present in actual provider trace")
    messages = []
    for event in events:
        if event.get("item", {}).get("type") != "agent_message": continue
        try: messages.append(load_json(event["item"]["text"]))
        except (ValueError, KeyError): continue
    if result not in messages: raise ValueError("Result differs from provider event")
    return result, meta


def merge_supplement(proposal, response):
    def signature(f):
        return (f["field"], f["context"], f["value_state"],
            json.dumps(json.loads(f["value_json"]), ensure_ascii=False, separators=(",", ":")) if f["value_json"] else "",
            json.dumps(json.loads(f["period_json"]), ensure_ascii=False, separators=(",", ":")) if f["period_json"] else "")
    for fact in response["new_facts"]:
        if not fact["field"].startswith(("finance.", "population.")): raise ValueError("Supplement outside quantitative scope")
        existing = next((f for f in proposal["facts"] if signature(f) == signature(fact)), None)
        if existing is None: proposal["facts"].append(deepcopy(fact))
        else:
            for evidence in fact["evidence"]:
                if evidence not in existing["evidence"]: existing["evidence"].append(deepcopy(evidence))
    proposal["notes"] += response["notes"]


def review_input(proposal, packet, record, corpus, contexts):
    byid = {"identity": {"identity_status": proposal["identity_status"]}}
    for key, prefix in (("locations", "location:"), ("milestones", "milestone:"), ("related_entities", "related:")):
        byid.update({prefix + item["id"]: item for item in proposal[key]})
    return {"case": packet["case"], "sources": packet["sources"], "source_corpus": corpus,
        "proposed_facts": [{"fact_id": "f" + str(i + 1), **f} for i, f in enumerate(proposal["facts"])],
        "contexts": [{"context_id": key, **byid[key]} for key in contexts], "declared_coverage": proposal["coverage"],
        "research_notes": proposal["notes"], "computed_preferred": [{"path": p, "preferred": f.get("preferred", {})} for p, f, _ in fields(record)]}


def exact_review_prompt(value, policy_text):
    return (RULES + "\n" + REVIEW_INSTRUCTIONS + "\nLATEST OPERATOR REVIEW POLICY (takes precedence over exact-concept requirements):\n"
        + policy_text + "\nFor every fact and context return support_basis=direct or reasonable_inference (explain inference in reason_en); unsupported for failed checks.\nSOURCES AND UNTRUSTED PROPOSAL:\n"
        + json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def check_review_prompt(prompt, value, policy_text):
    # Historical model inputs did not sort JSON object keys. Their order may be
    # changed by a private artifact formatter, but the role/policy text must be
    # exact and the entire remainder must be one strictly parsed JSON value.
    prefix = exact_review_prompt({}, policy_text)[:-2]
    if not prompt.startswith(prefix): raise ValueError("Actual review prompt differs from trusted role/policy/input")
    try: supplied = load_json(prompt[len(prefix):])
    except ValueError as error: raise ValueError("Actual review prompt has extra or invalid instructions/input") from error
    if supplied != value: raise ValueError("Actual review prompt input differs from reviewed proposal")


def inference_annotations(verdict, proposal, mapping, reviewed_contexts):
    byid = {row["fact_id"]: row for row in mapping}; rows = []
    for check in verdict["checks"]:
        if check["support_basis"] != "reasonable_inference": continue
        fact = proposal["facts"][int(check["fact_id"][1:]) - 1]
        rows.append({**byid[check["fact_id"]], "basis": "reasonable_inference",
            "value": json.loads(fact["value_json"]) if fact["value_json"] else {"value_state": "unknown"}, "reason_en": check["reason_en"]})
    contexts = {row["context_id"]: row for row in reviewed_contexts}
    for check in verdict["context_checks"]:
        if check["support_basis"] == "reasonable_inference":
            rows.append({"context_id": check["context_id"], "basis": "reasonable_inference",
                "representation": contexts[check["context_id"]], "reason_en": check["reason_en"]})
    return rows


def public_inferences(rows):
    """Allowlisted derived summaries, never a verbatim private annotation object."""
    result = []
    for row in rows:
        reason = row["reason_en"]
        if not isinstance(reason, str) or not 1 <= len(reason) <= 2000: raise ValueError("Unbounded public inference explanation")
        if ".private/" in reason or ".private\\" in reason or "PRIVATE KEY" in reason: raise ValueError("Private material in public explanation")
        if "fact_id" in row:
            value = row["value"]
            if len(encode(value)) > 8192: raise ValueError("Unbounded public inference value")
            result.append({"kind": "fact", "field": row["field"], "context": row["context"],
                "candidate_id": row["candidate_id"], "value": value, "basis": "reasonable_inference", "reason_en": reason})
        else:
            result.append({"kind": "context", "context_id": row["context_id"], "basis": "reasonable_inference", "reason_en": reason})
    return result


def audit_case(root, entity_id, trust):
    root = private_path(root); outcome = read(root / "cases" / entity_id / "outcome.json")
    if outcome["qid"] != entity_id or outcome["status"] != "approved": raise ValueError("Approved QID outcome required")
    record_file = inside(root, outcome["record_path"]); record = read(record_file)
    if sha(record_file.read_bytes()) != outcome["record_sha256"]: raise ValueError("Approved record bytes changed")
    validate(record)
    proposal_file = inside(root, outcome["approved_proposal_path"]); task = proposal_file.parent
    proposal = read(proposal_file); packet = read(inside(root, outcome["source_packet_path"]))
    research_path = inside(root, read(task / "research-provider-reference.json")["original_path"]).parent
    base_proposal, research = provider(research_path, trust); assembled = deepcopy(base_proposal)
    sessions = list(research["session_ids"])
    for source in sorted(task.glob("unit-research-*")):
        response, meta = provider(source, trust); sessions += meta["session_ids"]
        merge_supplement(assembled, response)
    if assembled != proposal: raise ValueError("Proposal differs from actual Research output/deltas")
    verdict, review = provider(task / "review", trust)
    if verdict != read(task / "verdict.json"): raise ValueError("Review result changed")
    if set(sessions) & set(review["session_ids"]) or len(sessions) != len(set(sessions)):
        raise ValueError("Research/Review session reuse")
    if sessions != outcome["research_sessions"] or review["session_ids"] != outcome["review_sessions"]:
        raise ValueError("Outcome session mismatch")
    trusted_policy = (ROOT / "docs/review-policy-v2.md").read_text(encoding="utf-8")
    if read(task / "policy.json")["text"] != trusted_policy or sha(trusted_policy.encode()) != trust["review_policy"]["sha256"]:
        raise ValueError("Review policy is not the trusted version")
    expected, mapping, contexts = compile_record(proposal, packet)
    if not review_gate(verdict, proposal, contexts): raise ValueError("Incomplete/rejected independent review")
    for check in verdict["checks"] + verdict["context_checks"]:
        if check.get("support_basis") not in ("direct", "reasonable_inference"): raise ValueError("Missing support basis")
    review_base = deepcopy(expected)
    expected["curation"].update({"reviewed_groups": ["identity", "geography", "history", "population", "finance", "profile"], "refresh_profile": "core-v1"})
    if record.get("update_datetime") != record.get("modified_datetime"): raise ValueError("Initial full-refresh timestamps differ")
    completed = instant(review["ended_at"]); applied = instant(record["modified_datetime"])
    if not completed <= applied <= completed + timedelta(minutes=1): raise ValueError("Refresh date is not bound to actual Review completion")
    for field in ("update_datetime", "modified_datetime"):
        if field in record: expected[field] = record[field]
    if record != expected or recompute(record) != record: raise ValueError("Canonical record differs from reviewed proposal")
    replay_log = read(task / "independent-source-replay.json")
    if len(replay_log) != len(packet["sources"]) or {r["source_ref"] for r in replay_log} != set(packet["sources"]):
        raise ValueError("Incomplete independent source replay")
    captures = {}; capture_hashes = []
    for row in replay_log:
        capture_path = inside(root, row["cache_path"])
        if "independent-review-cache" not in capture_path.parts: raise ValueError("Research cache reused for independent review")
        capture = read(capture_path)
        if row["revision_id"] != packet["sources"][row["source_ref"]]["revision_id"]: raise ValueError("Replay receipt revision mismatch")
        body = json.dumps(capture["data"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        if sha(body) != capture["body_sha256"]: raise ValueError("Source capture body changed")
        if capture["request_url"] in captures and captures[capture["request_url"]] != capture["data"]: raise ValueError("Conflicting pinned captures for one request")
        captures[capture["request_url"]] = capture["data"]; capture_hashes.append(sha(capture_path.read_bytes()))
    def fetch(url):
        if url not in captures: raise ValueError("Missing pinned source capture; export never fetches the network")
        return captures[url]
    cache = Cache(root / "offline-export-audit-cache", fetch=fetch, maxlag=30)
    corpus = {}
    for ref, source in packet["sources"].items():
        if source["kind"] == "wikidata":
            entity, _ = cache.entity_revision(source["source_qid"], source["revision_id"], refresh=True)
            if source["url"] != "https://www.wikidata.org/w/index.php?oldid=" + str(source["revision_id"]): raise ValueError("Source URL mismatch")
            corpus[ref] = wikidata_corpus(entity, packet["property_labels"], packet["case"]["languages"], source["source_qid"] == entity_id)
        elif source["kind"] == "wikipedia":
            page = cache.wikipedia_get(source["language"], oldid=source["revision_id"], refresh=True)
            if page["page_id"] != source["page_id"] or page["source_url"] != source["url"]: raise ValueError("Source identity mismatch")
            corpus[ref] = wikipedia_corpus(page)
        else: raise ValueError("Unknown pilot source family")
    supplied = read(task / "review-input.json")
    reconstructed = review_input(proposal, packet, review_base, corpus, contexts)
    if supplied != reconstructed: raise ValueError("Complete review input differs from captured sources/compiled proposal")
    prompt = (task / "review/prompt.txt").read_text(encoding="utf-8")
    check_review_prompt(prompt, reconstructed, trusted_policy)
    expected_schema = deepcopy(REVIEW_SCHEMA)
    for field in ("checks", "context_checks"):
        shape = expected_schema["properties"][field]["items"]
        shape["properties"]["support_basis"] = {"enum": ["direct", "reasonable_inference", "unsupported"]}
        shape["required"].append("support_basis")
    if read(task / "review/output.schema.json") != expected_schema: raise ValueError("Reviewer output schema differs from trusted protocol")
    annotations = read(task / "interpretations.json")
    if annotations != outcome["inferred_facts"]: raise ValueError("Inference annotations changed")
    if annotations != inference_annotations(verdict, proposal, mapping, supplied["contexts"]): raise ValueError("Inference content differs from actual review result")
    return record, {"decision": "approve", "facts_checked": len(mapping), "contexts_checked": len(contexts),
        "source_revisions_checked": len(replay_log), "research_sessions": sessions, "review_session": review["session_ids"][0],
        "reviewed_at": review["ended_at"], "model": review["requested_model"], "reasoning_effort": review["reasoning_effort"],
        "runtime_model_reported": bool(review.get("reported_models")), "inferences": public_inferences(annotations),
        "private_evidence_sha256": sha(json.dumps(sorted(capture_hashes)).encode()),
        "prompt_sha256": review["prompt_sha256"], "output_schema_sha256": review["schema_sha256"],
        "review_output_sha256": sha((task / "review/result.json").read_bytes()),
        "attestation_kind": "local_coordinator_verified_private_traces"}
