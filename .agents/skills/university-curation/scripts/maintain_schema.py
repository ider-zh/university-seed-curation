"""Generate/check the initial record schema and propose controlled field additions."""
import argparse
import json
from pathlib import Path
import sys

from _bootstrap import ROOT, SCRIPTS


def obj(properties, required=()):
    return {"type": "object", "additionalProperties": False, "properties": properties, "required": list(required)}


TEXT = {"type": "string", "minLength": 1}
QID = {"type": "string", "pattern": "^Q[1-9][0-9]*$"}
STAMP = {"type": "string", "format": "date-time"}


def initial_fields():
    name = obj({"text": TEXT, "language": TEXT}, ("text", "language"))
    count = obj({"amount": {"type": "number", "minimum": 0}, "minimum": {"type": "number", "minimum": 0},
        "maximum": {"type": "number", "minimum": 0}, "basis": {"enum": ["headcount", "fte", "unspecified"]},
        "precision": {"enum": ["exact", "approximate", "range"]}}, ("basis", "precision"))
    count["allOf"] = [
        {"if": {"properties": {"precision": {"const": "range"}}}, "then": {"required": ["minimum", "maximum"], "not": {"required": ["amount"]}},
         "else": {"required": ["amount"], "not": {"anyOf": [{"required": ["minimum"]}, {"required": ["maximum"]}]}}}]
    money = obj({"amount": {"type": "string", "pattern": "^-?[0-9]+(?:\\.[0-9]+)?$"},
        "currency": {"type": "string", "pattern": "^[A-Z]{3}$"}, "approximate": {"type": "boolean"}}, ("amount", "currency"))
    event = obj({"kind": {"enum": ["origin", "higher_education_status", "university_status", "charter", "rename", "relocation", "merger", "split", "closure", "reopening", "jurisdiction_change"]},
        "date_text": TEXT, "precision": {"enum": ["day", "month", "year", "decade", "century", "interval", "uncertain"]}}, ("kind", "date_text", "precision"))
    relation = obj({"kind": {"enum": ["parent", "member_of", "campus", "faculty", "predecessor", "successor", "legal_successor", "possible_duplicate"]},
        "target_qid": QID, "independence": {"enum": ["explicit_legal", "explicit_administrative", "unresolved"]}}, ("kind", "target_qid"))
    fields = {}
    def add(key, group, value): fields[key] = {"group": group, "value_schema": value}
    add("identity.kind", "identity", {"enum": ["university", "higher_education_college", "specialist_institution", "tertiary_vocational_institution", "historical_academy", "university_system", "campus", "faculty", "building", "other"]})
    add("identity.operating_status", "identity", {"enum": ["operating", "closed", "merged", "historical"]})
    for key in ("official", "former", "short"): add("names." + key, "identity", name)
    add("geography.location", "geography", obj({"place_qid": QID, "role": {"enum": ["institution", "campus", "administrative_area"]}}, ("place_qid", "role")))
    add("geography.coordinates", "geography", obj({"latitude": {"type": "number", "minimum": -90, "maximum": 90},
        "longitude": {"type": "number", "minimum": -180, "maximum": 180}, "role": {"enum": ["institution", "campus"]}}, ("latitude", "longitude", "role")))
    add("history.event", "history", event); add("history.relation", "history", relation)
    for key in ("students_total", "undergraduate_students", "postgraduate_students", "masters_students", "doctoral_students", "international_students", "academic_staff", "administrative_staff", "employees_total"):
        add("population." + key, "population", count)
    for key in ("endowment", "budget", "revenue", "expenses", "assets", "research_funding"): add("finance." + key, "finance", money)
    for key in ("website", "main_image_url", "logo_url"): add("profile." + key, "profile", {"type": "string", "format": "uri", "pattern": "^https?://"})
    for key in ("summary", "motto", "teaching_language", "academic_focus"): add("profile." + key, "profile", name)
    return {"version": "0.1.0", "status": "draft", "fields": fields}


def record_schema():
    source = obj({"kind": {"enum": ["wikidata", "wikipedia", "website", "dataset"]},
        "url": {"type": "string", "format": "uri", "pattern": "^https?://"}, "locator": TEXT, "language": TEXT,
        "page_id": {"type": "integer", "minimum": 1}, "revision_id": {"type": "integer", "minimum": 1},
        "snapshot_id": TEXT, "source_qid": QID, "statement_id": TEXT, "retrieved_at": STAMP,
        "dataset_version": TEXT, "source_record_id": TEXT}, ("kind", "url", "locator"))
    source["allOf"] = [
        {"if": {"properties": {"kind": {"const": "wikipedia"}}}, "then": {"required": ["language", "page_id", "revision_id", "retrieved_at"]}},
        {"if": {"properties": {"kind": {"const": "wikidata"}}}, "then": {"required": ["source_qid", "revision_id"],
            "anyOf": [{"required": ["snapshot_id"]}, {"required": ["retrieved_at"]}]}},
        {"if": {"properties": {"kind": {"const": "website"}}}, "then": {"required": ["retrieved_at"]}},
        {"if": {"properties": {"kind": {"const": "dataset"}}}, "then": {"required": ["dataset_version", "source_record_id"]}}]
    claim = obj({"id": {"type": "string", "pattern": "^c[1-9][0-9]*$"}, "field": TEXT, "subject_qid": QID,
        "value_state": {"enum": ["known", "unknown", "no_value", "not_applicable"]}, "value": {},
        "source_refs": {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"type": "string", "pattern": "^s[1-9][0-9]*$"}},
        "period": TEXT, "original_text": TEXT, "status": {"enum": ["supported", "disputed", "withdrawn"]}},
        ("id", "field", "value_state", "source_refs", "status"))
    claim["allOf"] = [{"if": {"properties": {"value_state": {"const": "known"}}}, "then": {"required": ["value"]}, "else": {"not": {"required": ["value"]}}}]
    record = obj({"schema_version": {"const": "0.1.0"}, "qid": QID, "record_revision": {"type": "integer", "minimum": 1},
        "update_datetime": STAMP, "modified_datetime": STAMP,
        "curation": obj({"identity_status": {"enum": ["pending", "in_scope", "related", "excluded", "needs_review", "conflation_suspected"]},
            "reviewed_groups": {"type": "array", "uniqueItems": True, "items": {"enum": ["identity", "geography", "history", "population", "finance", "profile"]}},
            "refresh_profile": {"const": "core-v1"}}, ("identity_status",)),
        "seed": obj({"import_id": TEXT, "screening_status": {"enum": ["included", "needs_review"]},
            "channels": {"type": "array", "minItems": 1, "items": TEXT},
            "labels": {"type": "object", "additionalProperties": TEXT}, "source_revision": {"type": "integer", "minimum": 1}},
            ("import_id", "screening_status", "channels")),
        "claims": {"type": "array", "items": claim},
        "sources": {"type": "object", "patternProperties": {"^s[1-9][0-9]*$": source}, "additionalProperties": False},
        "coverage": {"type": "object", "patternProperties": {"^(identity|geography|history|population|finance|profile)$":
            obj({"status": {"enum": ["checked", "not_found", "not_applicable", "disputed"]}, "checked_at": STAMP}, ("status", "checked_at"))}, "additionalProperties": False}},
        ("schema_version", "qid", "record_revision", "curation", "seed"))
    record.update({"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "urn:university-curation:record:0.1.0", "title": "University record draft 0.1.0"})
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "check", "propose-field", "register-coordinate-adapter"))
    parser.add_argument("--definition"); parser.add_argument("--output")
    args = parser.parse_args()
    if args.command == "register-coordinate-adapter":
        from university_curation.attestations import load_json, sha
        from university_curation.records import encode
        path = ROOT / ".curation/review-trust.json"
        trust = load_json(path.read_bytes())
        generated = ROOT / "schemas/university.v0.2.2.schema.json"
        from university_curation.schema_v02 import schema
        if load_json(generated.read_bytes()) != schema("0.2.2"): raise ValueError("Generate/check coordinate schema first")
        trust["schemas"]["0.2.2"] = sha(encode(schema("0.2.2")))
        adapters = trust.setdefault("field_update_adapters", [])
        if "wikidata_coordinates" not in adapters: adapters.append("wikidata_coordinates")
        path.write_bytes(encode(trust))
        return
    fields_path = ROOT / "schemas" / "fields.v0.1.json"
    schema_path = ROOT / "schemas" / "university.v0.1.schema.json"
    if args.command == "propose-field":
        import jsonschema
        if not args.definition or not args.output: parser.error("--definition and --output are required")
        definition = json.loads(Path(args.definition).read_text(encoding="utf-8"))
        if set(definition) != {"field", "group", "value_schema", "meaning", "compatibility"}: raise ValueError("Incomplete field proposal")
        if definition["field"] in json.loads(fields_path.read_text())["fields"]: raise ValueError("Field already registered")
        jsonschema.Draft202012Validator.check_schema(definition["value_schema"])
        Path(args.output).write_text(json.dumps({"status": "proposed_not_active", "definition": definition}, indent=2) + "\n")
        return
    from university_curation.schema_v02 import schema as schema_v02
    payloads = {fields_path: initial_fields(), schema_path: record_schema(),
                ROOT / "schemas" / "university.v0.2.schema.json": schema_v02(),
                ROOT / "schemas" / "university.v0.2.1.schema.json": schema_v02("0.2.1"),
                ROOT / "schemas" / "university.v0.2.2.schema.json": schema_v02("0.2.2")}
    for path, value in payloads.items():
        if "$schema" in value:
            import jsonschema
            jsonschema.Draft202012Validator.check_schema(value)
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        if args.command == "check":
            if path.read_text(encoding="utf-8") != encoded: raise ValueError("Generated schema/registry differs: " + str(path))
        else:
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text(encoded, encoding="utf-8")


if __name__ == "__main__": main()
