"""Strict compact transport, deterministic domain materialization and review coverage gates."""
from copy import deepcopy
import json

from .preferred import recompute, validate

from .records import CURRENT_SCHEMA_VERSION
GROUPS = ["identity", "geography", "history", "population", "finance", "profile"]
METRICS = ["students_total", "undergraduate_students", "postgraduate_students", "masters_students", "doctoral_students", "international_students", "teaching_staff", "research_staff", "academic_staff", "administrative_staff", "employees_total", "students_intake"]
FINANCE = ["endowment", "budget", "revenue", "expenses", "assets", "research_funding"]
FIELD_NAMES = ["identity.name", "identity.alias", "identity.kind", "identity.operating_status", "identity.ownership", "identity.identifier",
    "location.name", "location.address", "location.coordinates", "location.valid_from", "location.valid_to",
    "milestone.date", "milestone.description", "related.name"] + ["population." + m for m in METRICS] + ["finance." + m for m in FINANCE] + ["leadership." + m for m in ["president", "rector", "vice_chancellor", "chancellor", "board_chair", "provost", "chair"]] + ["profile." + m for m in ["website", "main_image_url", "logo_url", "summary", "motto", "teaching_languages", "degree_levels", "academic_focus"]] + ["relationships." + m for m in ["parent", "member_of", "predecessor", "successor", "legal_successor", "campus", "faculty", "possible_duplicate"]]
MILESTONES = ["predecessor_establishment", "vocational_origin", "institution_establishment", "higher_education_status", "university_status", "charter", "rename", "relocation", "merger", "split", "closure", "reopening", "jurisdiction_change", "campus_opening", "teaching_start", "cooperation_agreement", "construction_completion"]


def obj(**properties): return {"type": "object", "additionalProperties": False, "properties": properties, "required": list(properties)}
def arr(item): return {"type": "array", "items": item}
def enum(values): return {"type": "string", "enum": values}
TEXT = {"type": "string"}
EVIDENCE = obj(source_ref=TEXT, locator=TEXT, original_text=TEXT)
RESEARCH_SCHEMA = obj(qid=TEXT, identity_status=enum(["in_scope", "related", "excluded", "needs_review", "conflation_suspected"]),
    locations=arr(obj(id=TEXT, kind=enum(["campus", "administrative_area", "office", "headquarters"]), qid=TEXT)),
    milestones=arr(obj(id=TEXT, kind=enum(MILESTONES), subject_ref=TEXT)),
    related_entities=arr(obj(id=TEXT, kind=enum(["institution", "university_system", "faculty", "campus", "building"]), qid=TEXT)),
    facts=arr(obj(field=enum(FIELD_NAMES), context=TEXT, value_state=enum(["known", "unknown", "no_value", "not_applicable"]),
        value_json=TEXT, period_json=TEXT, current_basis=enum(["not_applicable", "explicit_current", "infobox_current", "term_present", "undated_last_known", "historical"]), evidence=arr(EVIDENCE))),
    conflicts=arr(obj(fact_indexes=arr({"type": "integer", "minimum": 0}), kind=enum(["value_disagreement", "scope_disagreement", "time_disagreement"]), note=TEXT)),
    coverage=arr(obj(group=enum(GROUPS), status=enum(["checked", "not_found", "not_applicable", "disputed"]), note=TEXT)),
    notes=arr(TEXT))


RESEARCH_INSTRUCTIONS = """ROLE: Research. Extract a compact proposal, one university only.
MAIN-PAGE OVERVIEW: Produce one English profile.summary as a well-sourced institutional overview suitable for a university ranking detail page, when evidence permits. Aim for 180-260 English words in 2-3 coherent paragraphs; 90-179 words are acceptable only for sparse historical or poorly sourced institutions, with an explicit coverage note. Omit the summary if even 90 grounded words are unavailable. Open with identity, institutional type and location; then establishment/predecessor distinctions and major milestones; close with evidenced academic focus, structure and time-qualified scale. Preserve local-language institutional names. Use neutral third-person factual prose, not promotional language, rankings, invented claims or undated fluctuating numbers. No source-list or research-process chatter inside the summary. Each material claim must be backed by the summary fact's supplied source evidence; use multiple evidence refs if drawing on multiple sections. Summarizing is permitted, copying long source passages is not. Do not stretch text by repetition.
facts contains field, context, value_state, value_json, period_json, current_basis, evidence. value_json is a JSON-encoded TYPED value, NOT prose.
Canonical data never contains null/empty placeholders. Empty strings in this private transport only mean an OPTIONAL value is absent; code omits it.
context is 'institution', 'location:ID', 'milestone:ID', or 'related:ID'. Define every non-root context in locations/milestones/related_entities first.
Locations: ONLY source-established campus/admin-area/office/headquarters; no assumed main-campus names. Use campus context for campus counts; city centres remain administrative_area.
Milestone metadata: id, enum kind, subject_ref (institution or related:ID). Current establishment and predecessor origin are separate.
Related metadata has an optional QID encoded as '' if unavailable. A real item need not exist for a campus; use a stable local id.
FIELD VALUE SHAPES:
identity.name/alias, location.name, milestone.description, related.name, profile.summary/motto -> {"text":"...","language":"en|zh|..."}.
identity.kind -> university|higher_education_college|specialist_institution|tertiary_vocational_institution|historical_academy|university_system|campus|faculty|building|other.
identity.operating_status -> operating|closed|merged|historical. Do not infer operating just from absent dissolution.
identity.ownership -> public|private_nonprofit|private_for_profit|mixed.
identity.identifier -> {"scheme":"P5586 or another actual ID scheme","value":"actual ID"}.
population.* -> {"amount":NUMBER,"basis":"headcount|fte|unspecified","precision":"exact|approximate"}; ranges use minimum/maximum instead of amount and precision=range.
finance.* -> {"amount":"DECIMAL STRING IN BASE CURRENCY UNITS","currency":"ISO CODE","precision":"exact|approximate"}; ranges use decimal-string minimum/maximum and precision=range.
For quantities period_json is '' if unstated, otherwise JSON {"kind":"calendar_year|academic_year|fiscal_year|date|interval", "year":2024} or {"kind":"academic_year","start_year":2023,"end_year":2024,"label":"2023/24"} etc. No fabricated exact boundaries.
location.coordinates -> {"latitude":NUMBER,"longitude":NUMBER,"crs":"EPSG:4326"}; accuracy_metres optional if supported.
location.address -> {"formatted":{"text":"original address","language":"xx"}, optional street/postal_code/city_name/region_name/country_name/city_qid/region_qid/country_qid}.
milestone.date/location.valid_from/valid_to -> {"year":INTEGER,"precision":"year", optional approximate:true}; month/day components are allowed when sourced (e.g. {year:2025,month:9,precision:"month"}); other precision day/month/decade/century/interval/uncertain, original_date is allowed for an unparsed expression.
leadership.* -> {"person":{"name":"...", optional qid},"title_original":{"text":"...","language":"xx"}, optional term_start:{year,precision},term_end:{year,precision},acting:boolean}.
leadership current_basis uses explicit_current, infobox_current, term_present, undated_last_known or historical; no end date is needed for an infobox incumbent. For other fields current_basis=not_applicable.
profile.website/main_image_url/logo_url -> URL STRING, do not download binaries.
profile.teaching_languages/degree_levels -> ARRAY OF STRINGS; profile.academic_focus -> ARRAY OF {text,language}.
relationships.* -> {"target_ref":"related:ID or location:ID", optional independence:"explicit_legal|explicit_administrative|unresolved",valid_from:{year,precision},valid_to:{year,precision}}.
Only claim explicit_legal independence when the source actually states independent legal entity/status, and specify the related institution.
Do not guess a Wikidata property ID from an infobox field. If the scheme/property mapping is not present, use the source's literal scheme label.
conflicts.fact_indexes are ZERO-BASED indexes into the FINAL facts array (first fact=0). Check every index against its final field/context.
Different/unknown statistical periods are not automatically a contradiction; retain observations and note comparability limits. Use conflicts only when warranted.
Use leadership.chair when only Chair is stated; do not infer board_chair. Use location kind headquarters for P159 without assuming an office.
The current schema includes students_intake, leadership.provost and event kinds campus_opening/teaching_start/cooperation_agreement/construction_completion. Use campus-opening with location subject, not institution_establishment.
Keep each fact's source original meaning. Avoid redundant identical facts; use multiple evidence entries for corroborating identical assertions.
Include all six coverage groups (identity,geography,history,population,finance,profile), allowing not_found/not_applicable.
Focus on reliable coverage rather than output volume. Usually 25-70 facts suffice; more identifiable numerical periods may be retained.
"""


def normalize(text): return " ".join(str(text).split()).casefold()


def compile_record(proposal, packet):
    qid = packet["case"]["qid"]
    if proposal["qid"] != qid: raise ValueError("Research QID mismatch")
    coverage = {c["group"]: c for c in proposal["coverage"]}
    if len(proposal["coverage"]) != len(GROUPS) or set(coverage) != set(GROUPS): raise ValueError("Coverage groups missing/duplicated")
    record = {"schema_version": CURRENT_SCHEMA_VERSION, "qid": qid, "record_revision": 1,
        "selection_policy": "preferred-v1", "curation": {"identity_status": proposal["identity_status"]},
        "seed": {"import_id": "private-research-transport", "screening_status": "needs_review", "channels": ["research_transport"]},
        "sources": deepcopy(packet["sources"]), "coverage": {g: {"status": coverage[g]["status"], "checked_at": packet["captured_at"]} for g in GROUPS}}
    locations = {}; milestones = {}; related = {}; contexts = ["identity"]
    for value in proposal["locations"]:
        if value["id"] in locations: raise ValueError("Duplicate location context")
        item = {"id": value["id"], "kind": value["kind"]}
        if value["qid"]: item["qid"] = value["qid"]
        locations[value["id"]] = item; contexts.append("location:" + value["id"])
    for value in proposal["milestones"]:
        if value["id"] in milestones: raise ValueError("Duplicate milestone context")
        milestones[value["id"]] = deepcopy(value); contexts.append("milestone:" + value["id"])
    for value in proposal["related_entities"]:
        if value["id"] in related: raise ValueError("Duplicate related context")
        item = {"kind": value["kind"]}
        if value["qid"]: item["qid"] = value["qid"]
        related[value["id"]] = item; contexts.append("related:" + value["id"])
    if locations: record["locations"] = list(locations.values())
    if milestones: record["history"] = {"milestones": list(milestones.values())}
    if related: record["related_entities"] = related
    original_corpus = {ref: {v["locator"]: v["text"] for v in corpus} for ref, corpus in packet["source_corpus"].items()}
    mappings = []; alias_fields = {}; relation_fields = {}
    for i, fact in enumerate(proposal["facts"], 1):
        context = fact["context"]; field = fact["field"]
        if context == "institution": target = record
        elif context.startswith("location:"): target = locations[context.split(":", 1)[1]]
        elif context.startswith("milestone:"): target = milestones[context.split(":", 1)[1]]
        elif context.startswith("related:"): target = related[context.split(":", 1)[1]]
        else: raise ValueError("Undefined fact context")
        candidate = {"verification": "supported", "evidence": []}
        for e in fact["evidence"]:
            source = original_corpus.get(e["source_ref"], {})
            if e["locator"] not in source: raise ValueError("Unknown source/locator for f" + str(i) + ": " + str(e))
            if e["original_text"] and normalize(e["original_text"]) not in normalize(source[e["locator"]]):
                raise ValueError("Non-verbatim evidence for f" + str(i) + ": " + e["original_text"])
            citation = {"source_ref": e["source_ref"], "locator": e["locator"]}
            if e["original_text"]: citation["original_text"] = e["original_text"]
            candidate["evidence"].append(citation)
        if not candidate["evidence"]: raise ValueError("Unsourced fact f" + str(i))
        if fact["value_state"] == "known": value = json.loads(fact["value_json"])
        else:
            if fact["value_json"]: raise ValueError("Explicit no-value fact carries fabricated value")
            value = None; candidate["value_state"] = fact["value_state"]
        if field == "identity.name":
            if context != "institution" or value is None: raise ValueError("Name context/state mismatch")
            if set(value) != {"text", "language"}: raise ValueError("Name value must contain only text/language")
            leaf = target.setdefault("identity", {}).setdefault("names", {}).setdefault(value["language"], {"candidates": []})
            value = value["text"]
        elif field == "identity.alias":
            if context != "institution": raise ValueError("Alias crosses institution boundary")
            key = json.dumps(value, sort_keys=True, ensure_ascii=False)
            if key not in alias_fields:
                alias_fields[key] = {"candidates": []}; record.setdefault("identity", {}).setdefault("aliases", []).append(alias_fields[key])
            leaf = alias_fields[key]
        elif field == "identity.identifier":
            if context != "institution" or value is None or set(value) != {"scheme", "value"}: raise ValueError("Identifier context/value mismatch")
            leaf = target.setdefault("identity", {}).setdefault("identifiers", {}).setdefault(value["scheme"], {"candidates": []}); value = value["value"]
        elif field.startswith("location."):
            if not context.startswith("location:"): raise ValueError("Location fact applied to another subject")
            leaf = target.setdefault(field.split(".")[1], {"candidates": []})
        elif field.startswith("milestone."):
            if not context.startswith("milestone:"): raise ValueError("Milestone fact applied to another subject")
            leaf = target.setdefault(field.split(".")[1], {"candidates": []})
        elif field == "related.name":
            if not context.startswith("related:"): raise ValueError("Related name on wrong subject")
            leaf = target.setdefault("name", {"candidates": []})
        elif field.startswith("relationships."):
            if context != "institution" or value is None: raise ValueError("Relation context mismatch")
            key = (field, value["target_ref"])
            if key not in relation_fields:
                relation_fields[key] = {"candidates": []}; target.setdefault("relationships", {}).setdefault(field.split(".")[1], []).append(relation_fields[key])
            leaf = relation_fields[key]
        else:
            group, key = field.split(".")
            if context != "institution" and not (context.startswith("location:") and group == "population"):
                raise ValueError("Business fact crosses subject boundary")
            leaf = target.setdefault(group, {}).setdefault(key, {"candidates": []})
        if fact["value_state"] == "known": candidate["value"] = value
        if field.startswith(("population.", "finance.")):
            candidate["period_status"] = "stated" if fact["period_json"] else "not_stated"
            if fact["period_json"]: candidate["period"] = json.loads(fact["period_json"])
        elif fact["period_json"]: candidate["period"] = json.loads(fact["period_json"])
        if fact["current_basis"] != "not_applicable": candidate["current_basis"] = fact["current_basis"]
        candidate["id"] = "c" + str(len(leaf["candidates"]) + 1); leaf["candidates"].append(candidate)
        mappings.append({"fact_id": "f" + str(i), "field": field, "context": context, "candidate_id": candidate["id"], "leaf": leaf})
    for conflict in proposal["conflicts"]:
        if any(type(n) is not int or not 0 <= n < len(mappings) for n in conflict["fact_indexes"]): raise ValueError("Invalid conflict fact index")
        members = [mappings[n] for n in conflict["fact_indexes"]]
        if not members or any(m["leaf"] is not members[0]["leaf"] for m in members):
            raise ValueError("Conflict crosses fields/subjects. ZERO-BASED references resolved to " + str([
                {"index": n, "field": mappings[n]["field"], "context": mappings[n]["context"]} for n in conflict["fact_indexes"]]))
        members[0]["leaf"].setdefault("conflicts", []).append({"candidate_ids": [m["candidate_id"] for m in members],
            "kind": conflict["kind"], "status": "unresolved", "note": conflict["note"]})
    record = recompute(record); validate(record)
    for m in mappings: m.pop("leaf")
    return record, mappings, contexts
