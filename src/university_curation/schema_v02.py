"""Draft domain-oriented record schema; candidates remain the source of preferred values."""
from copy import deepcopy
from collections import Counter
import json

VERSION = "0.2.0"
TEXT = {"type": "string", "minLength": 1}
QID = {"type": "string", "pattern": "^Q[1-9][0-9]*$"}
STAMP = {"type": "string", "format": "date-time"}
LOCAL = {"type": "string", "pattern": "^[a-z][a-z0-9_-]*$"}


def obj(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


def array(items, minimum=1):
    return {"type": "array", "items": items, "minItems": minimum}


def factor_schema(root):
    """Share repeated schema fragments instead of emitting thousands of duplicate lines."""
    counts = Counter(); nodes = {}
    def key(node): return json.dumps(node, sort_keys=True, separators=(",", ":"))
    def count(node):
        if isinstance(node, dict):
            signature = key(node)
            # Only actual typed schemas are referenceable here. A `properties`
            # name->schema map is not itself a schema and cannot become a $ref.
            if isinstance(node.get("type"), (str, list)) and len(signature) >= 300:
                counts[signature] += 1; nodes[signature] = node
            for value in node.values(): count(value)
        elif isinstance(node, list):
            for value in node: count(value)
    count(root)
    names = {signature: "shared" + str(i + 1) for i, signature in enumerate(sorted(s for s, n in counts.items() if n > 1))}
    def rewrite(node, own=False):
        if isinstance(node, dict):
            signature = key(node)
            if not own and signature in names: return {"$ref": "#/$defs/" + names[signature]}
            return {k: rewrite(v) for k, v in node.items()}
        if isinstance(node, list): return [rewrite(v) for v in node]
        return node
    result = rewrite(root)
    result["$defs"] = {name: rewrite(nodes[signature], True) for signature, name in names.items()}
    return result


def field(value, quantitative=False):
    evidence = obj({"source_ref": {"type": "string", "pattern": "^s[1-9][0-9]*$"},
                    "locator": TEXT, "original_text": TEXT}, ("source_ref", "locator"))
    period = obj({"kind": {"enum": ["calendar_year", "academic_year", "fiscal_year", "date", "interval"]},
        "year": {"type": "integer"}, "start_year": {"type": "integer"}, "end_year": {"type": "integer"},
        "label": TEXT, "date": {"type": "string", "format": "date"},
        "start_date": {"type": "string", "format": "date"}, "end_date": {"type": "string", "format": "date"}}, ("kind",))
    period["anyOf"] = [{"required": ["year"]}, {"required": ["start_year", "end_year"]}, {"required": ["date"]},
                       {"required": ["start_date", "end_date"]}, {"required": ["label"]}]
    candidate = obj({"id": {"type": "string", "pattern": "^c[1-9][0-9]*$"}, "value": value,
        "value_state": {"enum": ["known", "unknown", "no_value", "not_applicable"]},
        "period": period, "period_status": {"enum": ["stated", "not_stated"]},
        "evidence": array(evidence), "verification": {"enum": ["supported", "disputed", "insufficient_evidence", "withdrawn"]},
        "current_basis": {"enum": ["explicit_current", "infobox_current", "term_present", "undated_last_known", "historical"]}},
        ("id", "evidence", "verification"))
    candidate["allOf"] = [{"if": {"required": ["value_state"], "properties": {"value_state": {"enum": ["unknown", "no_value", "not_applicable"]}}},
        "then": {"not": {"required": ["value"]}}, "else": {"required": ["value"]}}]
    if quantitative:
        candidate["required"].append("period_status")
        candidate["allOf"].append({"if": {"properties": {"period_status": {"const": "stated"}}},
            "then": {"required": ["period"]}, "else": {"not": {"required": ["period"]}}})
    preferred = obj({"candidate_id": {"type": "string", "pattern": "^c[1-9][0-9]*$"},
        "reason_code": {"enum": ["only_available", "explicit_current", "infobox_current", "term_present", "last_known", "best_available"]},
        "reason": TEXT, "qualifications": {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"enum": [
            "period_not_stated", "single_source_family", "approximate_value", "range_value", "conflicting_candidates",
            "reported_current", "last_known_only", "historical_only", "disputed_claim", "limited_support", "different_basis_available", "different_currency_available"]}}},
        ("candidate_id", "reason_code"))
    conflict = obj({"candidate_ids": {"type": "array", "minItems": 2, "uniqueItems": True, "items": TEXT},
        "kind": {"enum": ["value_disagreement", "scope_disagreement", "time_disagreement"]},
        "status": {"enum": ["unresolved", "resolved_by_evidence"]}, "note": TEXT}, ("candidate_ids", "kind", "status", "note"))
    return obj({"subject_ref": TEXT, "candidates": array(candidate), "preferred": preferred, "conflicts": array(conflict)}, ("candidates",))


def schema():
    local_text = obj({"text": TEXT, "language": TEXT}, ("text", "language"))
    count = obj({"amount": {"type": "number", "minimum": 0}, "minimum": {"type": "number", "minimum": 0},
        "maximum": {"type": "number", "minimum": 0}, "basis": {"enum": ["headcount", "fte", "unspecified"]},
        "precision": {"enum": ["exact", "approximate", "range"]}}, ("basis", "precision"))
    count["allOf"] = [{"if": {"properties": {"precision": {"const": "range"}}},
        "then": {"required": ["minimum", "maximum"], "not": {"required": ["amount"]}},
        "else": {"required": ["amount"], "not": {"anyOf": [{"required": ["minimum"]}, {"required": ["maximum"]}]}}}]
    money = deepcopy(count)
    money["properties"].pop("basis"); money["required"] = ["currency", "precision"]
    money["properties"]["currency"] = {"type": "string", "pattern": "^[A-Z]{3}$"}
    for key in ("amount", "minimum", "maximum"):
        money["properties"][key] = {"type": "string", "pattern": "^-?[0-9]+(?:\\.[0-9]+)?$"}
    date = obj({"year": {"type": "integer"}, "date": {"type": "string", "format": "date"},
        "minimum_year": {"type": "integer"}, "maximum_year": {"type": "integer"},
        "precision": {"enum": ["day", "month", "year", "decade", "century", "interval", "uncertain"]},
        "approximate": {"type": "boolean"}, "calendar": TEXT, "original_date": TEXT}, ("precision",))
    date["anyOf"] = [{"required": ["year"]}, {"required": ["date"]}, {"required": ["minimum_year", "maximum_year"]}, {"required": ["original_date"]}]
    source = obj({"kind": {"enum": ["wikidata", "wikipedia", "website", "dataset"]},
        "url": {"type": "string", "format": "uri", "pattern": "^https?://"},
        "publisher_role": {"enum": ["institution_official", "government", "academic_publisher", "encyclopedia", "knowledge_base", "other"]},
        "family": TEXT, "language": TEXT, "retrieved_at": STAMP,
        "page_id": {"type": "integer", "minimum": 1}, "revision_id": {"type": "integer", "minimum": 1},
        "snapshot_id": TEXT, "source_qid": QID, "dataset_version": TEXT, "source_record_id": TEXT},
        ("kind", "url", "publisher_role", "family"))
    source["allOf"] = [
        {"if": {"properties": {"kind": {"const": "wikipedia"}}}, "then": {"required": ["language", "page_id", "revision_id", "retrieved_at"]}},
        {"if": {"properties": {"kind": {"const": "wikidata"}}}, "then": {"required": ["source_qid", "revision_id"],
            "anyOf": [{"required": ["snapshot_id"]}, {"required": ["retrieved_at"]}]}},
        {"if": {"properties": {"kind": {"const": "website"}}}, "then": {"required": ["retrieved_at"]}},
        {"if": {"properties": {"kind": {"const": "dataset"}}}, "then": {"required": ["dataset_version", "source_record_id"]}}]
    population = obj({name: field(count, True) for name in ("students_total", "undergraduate_students", "postgraduate_students", "masters_students", "doctoral_students",
        "international_students", "teaching_staff", "research_staff", "academic_staff", "administrative_staff", "employees_total")})
    finance = obj({name: field(money, True) for name in ("endowment", "budget", "revenue", "expenses", "assets", "research_funding")})
    names = {"type": "object", "patternProperties": {"^[a-z]{2,3}(?:-[a-z0-9]+)*$": field(TEXT)}, "additionalProperties": False}
    identity = obj({"names": names, "aliases": array(field(local_text)),
        "kind": field({"enum": ["university", "higher_education_college", "specialist_institution", "tertiary_vocational_institution", "historical_academy", "university_system", "campus", "faculty", "building", "other"]}),
        "operating_status": field({"enum": ["operating", "closed", "merged", "historical"]}),
        "ownership": field({"enum": ["public", "private_nonprofit", "private_for_profit", "mixed"]}),
        "identifiers": {"type": "object", "additionalProperties": field(TEXT)}})
    address = obj({"formatted": local_text, "street": TEXT, "postal_code": TEXT, "city_name": TEXT,
        "region_name": TEXT, "country_name": TEXT, "city_qid": QID, "region_qid": QID, "country_qid": QID}, ("formatted",))
    coordinates = obj({"latitude": {"type": "number", "minimum": -90, "maximum": 90},
        "longitude": {"type": "number", "minimum": -180, "maximum": 180}, "crs": {"const": "EPSG:4326"},
        "accuracy_metres": {"type": "number", "exclusiveMinimum": 0}}, ("latitude", "longitude", "crs"))
    location = obj({"id": LOCAL, "kind": {"enum": ["campus", "administrative_area", "office"]}, "qid": QID,
        "name": field(local_text), "address": field(address), "coordinates": field(coordinates),
        "valid_from": field(date), "valid_to": field(date), "population": population}, ("id", "kind"))
    milestone = obj({"id": LOCAL, "kind": {"enum": ["predecessor_establishment", "vocational_origin", "institution_establishment", "higher_education_status", "university_status",
        "charter", "rename", "relocation", "merger", "split", "closure", "reopening", "jurisdiction_change"]},
        "subject_ref": TEXT, "date": field(date), "description": field(local_text)}, ("id", "kind", "subject_ref", "date"))
    appointment = obj({"person": obj({"name": TEXT, "qid": QID}, ("name",)), "title_original": local_text,
        "term_start": date, "term_end": date, "acting": {"type": "boolean"}}, ("person", "title_original"))
    leadership = obj({role: field(appointment) for role in ("president", "rector", "vice_chancellor", "chancellor", "board_chair")})
    url = {"type": "string", "format": "uri", "pattern": "^https?://"}
    profile = obj({"website": field(url), "main_image_url": field(url), "logo_url": field(url),
        "summary": field(local_text), "motto": field(local_text), "teaching_languages": field(array(TEXT)), "degree_levels": field(array(TEXT)), "academic_focus": field(array(local_text))})
    related = obj({"kind": {"enum": ["institution", "university_system", "faculty", "campus", "building"]}, "qid": QID,
        "name": field(local_text)}, ("kind", "name"))
    relationships = obj({kind: array(field(obj({"target_ref": TEXT, "valid_from": date, "valid_to": date,
        "independence": {"enum": ["explicit_legal", "explicit_administrative", "unresolved"]}}, ("target_ref",))))
        for kind in ("parent", "member_of", "predecessor", "successor", "legal_successor", "campus", "faculty", "possible_duplicate")})
    result = obj({"schema_version": {"const": VERSION}, "qid": QID, "record_revision": {"type": "integer", "minimum": 1},
        "update_datetime": STAMP, "modified_datetime": STAMP, "selection_policy": {"const": "preferred-v1"},
        "example": obj({"synthetic": {"const": True}, "notice": TEXT}, ("synthetic", "notice")),
        "curation": obj({"identity_status": {"enum": ["pending", "in_scope", "related", "excluded", "needs_review", "conflation_suspected"]},
            "reviewed_groups": array({"enum": ["identity", "geography", "history", "population", "finance", "profile"]}), "refresh_profile": TEXT}, ("identity_status",)),
        "seed": obj({"import_id": TEXT, "screening_status": {"enum": ["included", "needs_review", "related_only"]}, "channels": array(TEXT)}, ("import_id", "screening_status", "channels")),
        "identity": identity, "locations": array(location), "history": obj({"milestones": array(milestone)}),
        "leadership": leadership, "population": population, "finance": finance, "profile": profile,
        "related_entities": {"type": "object", "additionalProperties": related, "propertyNames": LOCAL},
        "relationships": relationships,
        "sources": {"type": "object", "patternProperties": {"^s[1-9][0-9]*$": source}, "additionalProperties": False},
        "coverage": {"type": "object", "additionalProperties": obj({"status": {"enum": ["checked", "not_found", "not_applicable", "disputed"]},
            "checked_at": STAMP}, ("status", "checked_at"))}},
        ("schema_version", "qid", "record_revision", "curation", "seed", "selection_policy"))
    result.update({"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "urn:university-curation:record:0.2.0",
                   "title": "University domain record with preferred candidates, draft 0.2.0"})
    return factor_schema(result)
