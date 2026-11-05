"""Field-specific, non-destructive preferred projections and v0.2 semantic validation."""
from copy import deepcopy
from decimal import Decimal
from functools import lru_cache
import math
from pathlib import Path

from .schema_v02 import schema

AUTHORITY = {"institution_official": 5, "government": 5, "academic_publisher": 4,
             "encyclopedia": 3, "knowledge_base": 2, "other": 1}
CURRENT = {"explicit_current": 5, "infobox_current": 4, "term_present": 3,
           "undated_last_known": 2, "historical": 1}


def fields(record):
    def walk(node, path, subject):
        if isinstance(node, dict):
            if "candidates" in node:
                yield path, node, subject
                return
            if "id" in node and node.get("kind") in ("campus", "administrative_area", "office", "headquarters", "institution"):
                subject = "location:" + node["id"]
            if "date" in node and "subject_ref" in node and "kind" in node:
                subject = node["subject_ref"]
            for key, value in node.items():
                if key == "related_entities":
                    for local_id, related in value.items():
                        yield from walk(related, path + "." + key + "." + local_id, "related:" + local_id)
                else: yield from walk(value, path + "." + key, subject)
        elif isinstance(node, list):
            for i, value in enumerate(node): yield from walk(value, path + "[" + str(i) + "]", subject)
    yield from walk(record, "$", "institution")


def period_year(candidate):
    period = candidate.get("period", {})
    return period.get("end_year", period.get("year"))


def choose(field, sources, leadership=False):
    active = [c for c in field["candidates"] if c["verification"] != "withdrawn"]
    # A preferred-rank unknown/no-value cannot be replaced by a normal-rank point.
    if any(c.get("source_rank") == "preferred" for c in active):
        active = [c for c in active if c.get("source_rank") == "preferred"]
    candidates = [c for c in active if "value" in c]
    if not candidates: return None
    pool = candidates
    if leadership:
        rank = max(CURRENT.get(c.get("current_basis"), 2) for c in pool)
        pool = [c for c in pool if CURRENT.get(c.get("current_basis"), 2) == rank]
    # Keep undated observations eligible. Only eliminate older dated observations
    # from this selection round when there is a newer comparable dated one.
    if any("period_status" in c for c in pool):
        def comparable(c):
            value = c["value"]
            return (value.get("basis"), value.get("currency")) if isinstance(value, dict) else ()
        newest = {}
        for c in pool:
            year = period_year(c)
            if year is not None: newest[comparable(c)] = max(year, newest.get(comparable(c), year))
        pool = [c for c in pool if period_year(c) is None or period_year(c) == newest[comparable(c)]]
    def key(c):
        evidence_sources = [sources[e["source_ref"]] for e in c["evidence"]]
        authority = max(AUTHORITY[s["publisher_role"]] for s in evidence_sources)
        observed = max((s.get("retrieved_at", "") for s in evidence_sources), default="")
        support = {"supported": 3, "disputed": 2, "insufficient_evidence": 1}[c["verification"]]
        return (support, authority, observed, -int(c["id"][1:]))
    selected = max(pool, key=key)
    reason = "only_available" if len(candidates) == 1 else "best_available"
    if leadership:
        reason = {"explicit_current": "explicit_current", "infobox_current": "infobox_current", "term_present": "term_present",
                  "historical": "last_known", "undated_last_known": "last_known"}.get(selected.get("current_basis"), "last_known")
    notes = {
        "only_available": "Use the available sourced value; missing period or corroboration does not prevent selection.",
        "best_available": "Apply preferred-v1: compare stated periods within matching basis/currency, keep undated values eligible, then consider support, source role and observation recency.",
        "explicit_current": "The source explicitly identifies the current officeholder.",
        "infobox_current": "The page reports this person in its current officeholder field; a term-end date is not required.",
        "term_present": "The source gives a term continuing to the present.",
        "last_known": "Use the best available last-known appointment without claiming an explicitly confirmed current term."
    }
    qualifications = []
    if selected.get("period_status") == "not_stated": qualifications.append("period_not_stated")
    family = {sources[e["source_ref"]]["family"] for e in selected["evidence"]}
    if len(family) == 1 and ("period_status" in selected or leadership): qualifications.append("single_source_family")
    value = selected["value"]
    if isinstance(value, dict):
        if value.get("precision") == "approximate": qualifications.append("approximate_value")
        if value.get("precision") == "range": qualifications.append("range_value")
        bases = {c["value"].get("basis") for c in candidates if isinstance(c["value"], dict) and "basis" in c["value"]}
        currencies = {c["value"].get("currency") for c in candidates if isinstance(c["value"], dict) and "currency" in c["value"]}
        if len(bases) > 1: qualifications.append("different_basis_available")
        if len(currencies) > 1: qualifications.append("different_currency_available")
    if any(c["status"] == "unresolved" for c in field.get("conflicts", [])): qualifications.append("conflicting_candidates")
    if selected["verification"] == "disputed": qualifications.append("disputed_claim")
    if selected["verification"] == "insufficient_evidence": qualifications.append("limited_support")
    if leadership:
        if reason == "infobox_current": qualifications.append("reported_current")
        if reason == "last_known": qualifications.append("last_known_only")
        if selected.get("current_basis") == "historical": qualifications.append("historical_only")
    result = {"candidate_id": selected["id"], "reason_code": reason}
    if len(candidates) > 1 or leadership or selected.get("period_status") == "not_stated": result["reason"] = notes[reason]
    if qualifications: result["qualifications"] = qualifications
    return result


def recompute(record):
    result = deepcopy(record)
    for path, field, _ in fields(result):
        selected = choose(field, result.get("sources", {}), path.startswith("$.leadership."))
        if selected: field["preferred"] = selected
        else: field.pop("preferred", None)
    return result


@lru_cache(maxsize=3)
def validator(version="0.2.0"):
    import jsonschema
    return jsonschema.Draft202012Validator(schema(version), format_checker=jsonschema.FormatChecker())


def validate(record):
    def clean(node):
        if node is None: raise ValueError("Omit missing fields; JSON null is not a value")
        if isinstance(node, str) and not node.strip(): raise ValueError("Empty-string placeholder")
        if isinstance(node, float) and not math.isfinite(node): raise ValueError("Nonfinite JSON number")
        if isinstance(node, dict):
            for value in node.values(): clean(value)
        elif isinstance(node, list):
            for value in node: clean(value)
    clean(record); validator(record.get("schema_version", "0.2.0")).validate(record)
    sources = record.get("sources", {}); subjects = {"institution"}
    location_ids = [loc["id"] for loc in record.get("locations", [])]
    for loc in record.get("locations", []):
        if loc["kind"] == "institution" and loc.get("qid") != record["qid"]:
            raise ValueError("Institution location must identify the root Wikidata item")
    if len(location_ids) != len(set(location_ids)): raise ValueError("Duplicate location ID")
    subjects.update("location:" + s for s in location_ids)
    subjects.update("related:" + s for s in record.get("related_entities", {}))
    milestone_ids = [m["id"] for m in record.get("history", {}).get("milestones", [])]
    if len(milestone_ids) != len(set(milestone_ids)): raise ValueError("Duplicate milestone ID")
    for path, field, expected_subject in fields(record):
        subject = field.get("subject_ref", expected_subject)
        if subject not in subjects: raise ValueError("Unresolved subject at " + path)
        if subject != expected_subject:
            raise ValueError("Field subject differs from its containing institution/location/event")
        candidates = {c["id"]: c for c in field["candidates"]}
        if len(candidates) != len(field["candidates"]): raise ValueError("Duplicate field-local candidate ID")
        for c in candidates.values():
            if not all(e["source_ref"] in sources for e in c["evidence"]): raise ValueError("Dangling source reference")
            period = c.get("period", {})
            if "start_year" in period and "end_year" in period and period["start_year"] > period["end_year"]: raise ValueError("Reversed period")
            if "start_date" in period and "end_date" in period and period["start_date"] > period["end_date"]: raise ValueError("Reversed period dates")
            value = c.get("value")
            if isinstance(value, dict):
                if value.get("precision") == "range" and Decimal(str(value["minimum"])) > Decimal(str(value["maximum"])): raise ValueError("Reversed numeric range")
                if "minimum_year" in value and value["minimum_year"] > value["maximum_year"]: raise ValueError("Reversed date range")
                if "year" in value and "date" in value and int(value["date"][:4]) != value["year"]: raise ValueError("Date/year mismatch")
                if "target_ref" in value and value["target_ref"] not in subjects: raise ValueError("Unresolved relation target")
        for conflict in field.get("conflicts", []):
            if not set(conflict["candidate_ids"]) <= candidates.keys(): raise ValueError("Dangling conflict candidate")
        if "preferred" in field:
            preferred = field["preferred"]; selected = candidates.get(preferred["candidate_id"])
            if not selected or "value" not in selected or selected["verification"] == "withdrawn": raise ValueError("Invalid preferred candidate")
            flags = set(preferred.get("qualifications", []))
            if selected.get("period_status") == "not_stated" and "period_not_stated" not in flags: raise ValueError("Undated preferred value must disclose missing period")
            if any(c["status"] == "unresolved" for c in field.get("conflicts", [])) and "conflicting_candidates" not in flags: raise ValueError("Preferred selection cannot hide unresolved conflict")
    if "update_datetime" in record:
        from .records import GROUPS, instant
        instant(record["update_datetime"])
        if set(record["curation"].get("reviewed_groups", [])) != set(GROUPS): raise ValueError("Incomplete full refresh")
        if record["curation"]["identity_status"] not in ("in_scope", "related", "excluded"): raise ValueError("Identity unresolved at full refresh")
        if record["curation"].get("refresh_profile") != "core-v1": raise ValueError("Unknown refresh profile")
