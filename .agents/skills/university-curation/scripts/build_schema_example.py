"""Generate a wholly fictional, complete university record for Schema review."""
import json

from _bootstrap import ROOT
from university_curation.preferred import recompute, validate

NOW = "2026-11-05T00:00:00Z"
Q = "Q999999999999999"


def evidence(source, locator, original=None):
    result = {"source_ref": source, "locator": locator}
    if original: result["original_text"] = original
    return result


def c(value, source, locator, original=None, year=None, undated=False, current=None, extra_evidence=()):
    result = {"value": value, "evidence": [evidence(source, locator, original), *extra_evidence], "verification": "supported"}
    if year is not None: result.update({"period_status": "stated", "period": {"kind": "calendar_year", "year": year}})
    if undated: result["period_status"] = "not_stated"
    if current: result["current_basis"] = current
    return result


def fs(*candidates, conflicts=None):
    result = {"candidates": [{"id": "c" + str(i + 1), **value} for i, value in enumerate(candidates)]}
    if conflicts: result["conflicts"] = conflicts
    return result


def count(amount, basis="headcount", precision="exact"):
    return {"amount": amount, "basis": basis, "precision": precision}


def money(amount, currency="USD"):
    return {"amount": str(amount), "currency": currency, "precision": "exact"}


def date(year): return {"year": year, "precision": "year"}


def site(path, role="institution_official", family="example-university"):
    return {"kind": "website", "url": "https://example.org/" + path, "publisher_role": role,
            "family": family, "language": "en", "retrieved_at": NOW}


def example():
    sources = {
        "s1": {"kind": "wikipedia", "url": "https://example.org/fictional-wikipedia/en/University?oldid=1", "publisher_role": "encyclopedia",
            "family": "wikimedia", "language": "en", "page_id": 101, "revision_id": 1, "retrieved_at": NOW},
        "s2": {"kind": "wikipedia", "url": "https://example.org/fictional-wikipedia/zh/University?oldid=2", "publisher_role": "encyclopedia",
            "family": "wikimedia", "language": "zh", "page_id": 102, "revision_id": 2, "retrieved_at": NOW},
        "s3": site("university/about"), "s4": site("university/reports/2024"),
        "s5": site("university/history"), "s6": site("university/leadership"),
        "s7": site("university/reports/2023"), "s8": site("university/campus-map"),
        "s9": {"kind": "dataset", "url": "https://example.org/government/city-data", "publisher_role": "government",
            "family": "example-government", "dataset_version": "fictional-2024-v1", "source_record_id": "CITY-DEMO-1", "retrieved_at": NOW},
        "s10": {"kind": "wikidata", "url": "https://example.org/fictional-wikidata/" + Q + "?oldid=17", "publisher_role": "knowledge_base",
            "family": "wikimedia", "source_qid": Q, "revision_id": 17, "retrieved_at": NOW}
    }
    milestones = []
    for ident, kind, year, text, subject in [
        ("origin", "vocational_origin", 1906, "A vocational school opened in 1906 as the institution's predecessor.", "related:predecessor"),
        ("established", "institution_establishment", 1952, "The present institution was established in 1952.", "institution"),
        ("higher-education", "higher_education_status", 1954, "It began providing recognized higher education in 1954.", "institution"),
        ("university-status", "university_status", 1986, "University status was granted in 1986.", "institution"),
        ("charter", "charter", 1988, "The institution received its charter in 1988.", "institution"),
        ("move", "relocation", 1998, "Teaching moved to the present main campus in 1998.", "institution"),
        ("rename", "rename", 2005, "The name Meridian Example University was adopted in 2005.", "institution")]:
        extra = [evidence("s10", Q + "/claims/P571/0")] if kind == "institution_establishment" else []
        milestones.append({"id": ident, "kind": kind, "subject_ref": subject,
            "date": fs(c(date(year), "s5", "History/" + ident, text, extra_evidence=extra)),
            "description": fs(c({"text": text, "language": "en"}, "s5", "History/" + ident, text))})
    record = {
        "schema_version": "0.2.2", "qid": Q, "record_revision": 3,
        "example": {"synthetic": True, "notice": "SCHEMA EXAMPLE ONLY. All institutions, people, figures, identifiers, URLs and source revisions are fictional. This is not a researched university record."},
        "update_datetime": NOW, "modified_datetime": NOW, "selection_policy": "preferred-v1",
        "curation": {"identity_status": "in_scope", "reviewed_groups": ["identity", "geography", "history", "population", "finance", "profile"], "refresh_profile": "core-v1"},
        "seed": {"import_id": "synthetic-example-only", "screening_status": "included", "channels": ["synthetic_fixture"]},
        "identity": {
            "names": {"en": fs(c("Meridian Example University", "s3", "Official name")), "zh": fs(c("示范大学", "s2", "Lead", "示范大学"))},
            "kind": fs(c("university", "s3", "Institution status")),
            "ownership": fs(c("public", "s3", "Governance")),
            "operating_status": fs(c("operating", "s3", "About"))
        },
        "population": {
            "students_total": fs(c(count(25000, precision="approximate"), "s1", "infobox.students", "Approximately 25,000 students", undated=True)),
            "undergraduate_students": fs(c(count(17500), "s4", "Student statistics/Table 1", year=2024)),
            "postgraduate_students": fs(c(count(6500), "s4", "Student statistics/Table 1", year=2024)),
            "masters_students": fs(c(count(5200), "s4", "Student statistics/Table 1", year=2024)),
            "doctoral_students": fs(c(count(1300), "s4", "Student statistics/Table 1", year=2024)),
            "international_students": fs(c(count(2500), "s4", "Student statistics/Table 2", year=2024)),
            "academic_staff": fs(c(count(1480), "s4", "Staff/Table 3", "1,480 academic staff (headcount), 2024", year=2024)),
            "teaching_staff": fs(c(count(980), "s4", "Staff/Table 4", "980 teaching staff (headcount), 2024", year=2024),
                c(count(1020), "s1", "infobox.teaching_staff", "1,020 teaching staff (2024)", year=2024),
                conflicts=[{"candidate_ids": ["c1", "c2"], "kind": "value_disagreement", "status": "unresolved",
                    "note": "Both report institution-wide teaching headcount for 2024. Prefer the original annual report while retaining the Wikipedia value and unresolved conflict."}]),
            "administrative_staff": fs(c(count(620), "s4", "Staff/Table 3", year=2024)),
            "employees_total": fs(c(count(2300), "s4", "Staff/Table 3", year=2024),
                c(count(2100, basis="fte"), "s4", "Staff/Table 3/FTE", "2,100 FTE employees in 2024", year=2024))
        },
        "finance": {
            "endowment": fs(c(money(850000000), "s4", "Financial statements/Endowment", "$850 million, 2024", year=2024),
                c(money(800000000), "s7", "Financial statements/Endowment", "$800 million, 2023", year=2023)),
            "budget": fs(c(money(450000000), "s1", "infobox.budget", "$450 million", undated=True)),
            "revenue": fs(c(money(470000000), "s4", "Financial statements/Revenue", year=2024)),
            "expenses": fs(c(money(455000000), "s4", "Financial statements/Expenses", year=2024)),
            "assets": fs(c(money(1700000000), "s4", "Balance sheet/Assets", year=2024)),
            "research_funding": fs(c({"minimum": "70000000", "maximum": "75000000", "currency": "USD", "precision": "range"},
                "s4", "Research funding", "$70–75 million in 2024", year=2024))
        },
        "history": {"milestones": milestones},
        "leadership": {
            "president": fs(c({"person": {"name": "Dr. Mira Chen"}, "title_original": {"text": "President", "language": "en"}, "term_start": date(2024)},
                "s1", "infobox.president", "President: Dr. Mira Chen", current="infobox_current"),
                c({"person": {"name": "Prof. Rowan Ellis"}, "title_original": {"text": "President", "language": "en"}, "term_start": date(2012), "term_end": date(2023)},
                "s5", "Former presidents", "Rowan Ellis served as president from 2012 to 2023.", current="historical")),
            "chancellor": fs(c({"person": {"name": "Dr. Avery Stone"}, "title_original": {"text": "Chancellor", "language": "en"}},
                "s6", "Current leadership", "Current chancellor: Dr. Avery Stone", current="explicit_current"))
        },
        "locations": [
            {"id": "main", "kind": "campus",
                "name": fs(c({"text": "Main campus", "language": "en"}, "s8", "Main campus")),
                "address": fs(c({"formatted": {"text": "100 University Avenue, Example City, Example Country", "language": "en"},
                    "street": "100 University Avenue", "city_name": "Example City", "country_name": "Example Country", "postal_code": "EX100"}, "s8", "Contact/Main campus"),
                    c({"formatted": {"text": "示例国示例市学府路100号", "language": "zh"}}, "s2", "infobox.address", "示例国示例市学府路100号")),
                "coordinates": fs(c({"latitude": 35.12345, "longitude": 120.12345, "crs": "EPSG:4326", "accuracy_metres": 15}, "s8", "Campus map/University entrance")),
                "population": {"students_total": fs(c(count(18000), "s4", "Campus breakdown/Main campus", year=2024))}},
            {"id": "city", "kind": "administrative_area",
                "name": fs(c({"text": "Example City", "language": "en"}, "s9", "City name")),
                "coordinates": fs(c({"latitude": 35.15, "longitude": 120.1, "crs": "EPSG:4326", "accuracy_metres": 1000}, "s9", "City centroid"))}
        ],
        "related_entities": {"predecessor": {"kind": "institution", "qid": "Q999999999999998",
            "name": fs(c({"text": "Meridian Vocational School", "language": "en"}, "s5", "Early history"))}},
        "relationships": {"predecessor": [fs(c({"target_ref": "related:predecessor"}, "s5", "Early history", "The vocational school is described as a predecessor; legal continuity is not stated."))]},
        "profile": {
            "website": fs(c("https://example.org/university", "s3", "Official website")),
            "summary": fs(c({"text": "A fictional public university used to demonstrate this data contract.", "language": "en"}, "s3", "About")),
            "main_image_url": fs(c("https://example.org/images/main-campus.jpg", "s1", "infobox.main_image")),
            "motto": fs(c({"text": "Learning through inquiry", "language": "en"}, "s3", "Motto")),
            "teaching_languages": fs(c(["en", "zh"], "s3", "Teaching languages")),
            "degree_levels": fs(c(["bachelor", "master", "doctorate"], "s3", "Degrees"))
        },
        "sources": sources,
        "coverage": {group: {"status": "checked", "checked_at": NOW} for group in ("identity", "geography", "history", "population", "finance", "profile")}
    }
    for data in record["finance"].values():
        for candidate in data["candidates"]:
            if "period" in candidate:
                year = candidate["period"]["year"]
                candidate["period"] = {"kind": "fiscal_year", "year": year, "label": "FY" + str(year),
                    "start_date": str(year - 1) + "-07-01", "end_date": str(year) + "-06-30"}
    record = recompute(record); validate(record)
    return record


if __name__ == "__main__":
    target = ROOT / "examples" / "university.complete.synthetic.json"; target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(example(), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(str(target))
