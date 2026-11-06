"""Bounded Wikidata/Wikipedia capture for native Research; Review reuses the snapshot."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from .sources import Cache

PROP_RE = re.compile(r"student|employee|staff|budget|endowment|revenue|income|expend|expense|asset|funding|inception|dissol|coordinate|country|administrative|headquarters|official name|native label|short name|official website|logo|image|rector|president|head of|chair|parent|subsidiary|part of|replaces|replaced by|instance of|subclass|motto|language of", re.I)
CORE_PROPERTIES = {"P31", "P17", "P131", "P159", "P625", "P571", "P576", "P856", "P18", "P154", "P488", "P169", "P749", "P361", "P355", "P1365", "P1366", "P1128", "P2196", "P1448", "P1705", "P1813", "P5584", "P5586", "P5242"}

def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def property_labels(cache, properties):
    labels = {}; ids = sorted(properties)
    for start in range(0, len(ids), 50):
        data, _ = cache.request("https://www.wikidata.org/w/api.php", {"action": "wbgetentities", "ids": "|".join(ids[start:start+50]), "props": "labels", "languages": "en"})
        labels.update({key: e.get("labels", {}).get("en", {}).get("value", key) for key, e in data.get("entities", {}).items()})
    return labels


def wikidata_corpus(entity, labels, languages, root=True):
    metadata = {"id": entity["id"], "labels": {k: v["value"] for k, v in entity.get("labels", {}).items() if k in {*languages, "en"}},
        "descriptions": {k: v["value"] for k, v in entity.get("descriptions", {}).items() if k in {*languages, "en"}}}
    corpus = [{"locator": "metadata", "text": json.dumps(metadata, ensure_ascii=False)}]
    for prop, statements in entity.get("claims", {}).items():
        label = labels.get(prop, prop)
        if root:
            if prop not in CORE_PROPERTIES and not PROP_RE.search(label): continue
        elif prop not in {"P31", "P279", "P17", "P131", "P625", "P1448", "P1705", "P498"}: continue
        for i, s in enumerate(statements):
            snak = s["mainsnak"]
            row = {"property": prop, "property_label": label, "statement_id": s.get("id"), "rank": s.get("rank", "normal"), "snaktype": snak["snaktype"]}
            if "datavalue" in snak: row["value"] = snak["datavalue"]["value"]
            if s.get("qualifiers"):
                row["qualifiers"] = {p: [{"snaktype": q["snaktype"], **({"value": q["datavalue"]["value"]} if "datavalue" in q else {})} for q in vals] for p, vals in s["qualifiers"].items()}
            if s.get("references"): row["reference_count"] = len(s["references"])
            corpus.append({"locator": "claim:" + prop + ":" + str(i), "text": json.dumps(row, ensure_ascii=False)})
    return corpus


def wikipedia_corpus(page):
    corpus = [{"locator": "page_metadata", "text": json.dumps({"title": page["title"], "language": page["language"]}, ensure_ascii=False)}]
    for i, row in enumerate(page["infobox"]):
        corpus.append({"locator": "infobox:" + str(i), "text": row["label"] + ": " + row["text"]})
    if page["image_urls"]: corpus.append({"locator": "infobox_image_urls", "text": json.dumps(page["image_urls"], ensure_ascii=False)})
    budget = 52000
    ranked = sorted(enumerate(page["text_sections"]), key=lambda pair: (0 if RELEVANT.search(pair[1]["title"]) else 1, pair[0]))
    for _, section in ranked:
        if not section["text"] or budget <= 0: continue
        text = section["text"][:min(18000, budget)]
        corpus.append({"locator": "section:" + section["id"], "text": text}); budget -= len(text)
    return corpus


def prepare_case(case, root, source_cache=None):
    root = Path(root); cache = Cache(source_cache or root / "source-cache", maxlag=30)
    directory = root / "cases" / case["qid"]; directory.mkdir(parents=True, exist_ok=True)
    entity, meta = cache.entity(case["qid"])
    if entity["id"] != case["qid"]: raise ValueError("Case redirects to a different identity")
    labels = property_labels(cache, set(entity.get("claims", {})))
    source_map = {}; corpus = {}; inventory = []
    def wd(e, m, is_root):
        ref = "s" + str(len(source_map) + 1)
        source_map[ref] = {"kind": "wikidata", "url": "https://www.wikidata.org/w/index.php?oldid=" + str(e["lastrevid"]),
            "publisher_role": "knowledge_base", "family": "wikimedia", "source_qid": e["id"],
            "revision_id": e["lastrevid"], "retrieved_at": m["retrieved_at"]}
        corpus[ref] = wikidata_corpus(e, labels, case["languages"], is_root)
        inventory.append({"source_ref": ref, "cache_path": m["cache_path"], "root_entity": is_root})
    wd(entity, meta, True)
    failures = []
    for lang in case["languages"]:
        try:
            page = cache.wikipedia_get(lang, entity_id=case["qid"])
            ref = "s" + str(len(source_map) + 1)
            source_map[ref] = {"kind": "wikipedia", "url": page["source_url"], "publisher_role": "encyclopedia", "family": "wikimedia",
                "language": lang, "page_id": page["page_id"], "revision_id": page["revision_id"], "retrieved_at": page["retrieved_at"]}
            corpus[ref] = wikipedia_corpus(page)
            inventory.append({"source_ref": ref, "cache_path": page["cache_path"], "title": page["title"]})
        except Exception as error: failures.append({"language": lang, "error": type(error).__name__ + ": " + str(error)})
    # Quantity units are necessary evidence, not optional enrichment. Resolve
    # currency/person units before consuming the bounded linked-item budget.
    linked = []
    for statements in entity.get("claims", {}).values():
        for statement in statements:
            value = statement.get("mainsnak", {}).get("datavalue", {}).get("value")
            unit = value.get("unit", "") if isinstance(value, dict) else ""
            target = unit.rsplit("/", 1)[-1]
            if re.fullmatch(r"Q[1-9][0-9]*", target) and target not in linked: linked.append(target)
    for prop in ("P31", "P17", "P131", "P159", "P749", "P361", "P1365", "P1366", "P488", "P169"):
        for statement in entity.get("claims", {}).get(prop, []):
            v = statement.get("mainsnak", {}).get("datavalue", {}).get("value")
            if statement.get("rank") != "deprecated" and isinstance(v, dict) and re.fullmatch(r"Q[1-9][0-9]*", str(v.get("id", ""))):
                if v["id"] not in linked and v["id"] != case["qid"]: linked.append(v["id"])
    for target in linked[:10]:
        try:
            e, m = cache.entity(target); wd(e, m, False)
        except Exception as error: failures.append({"linked_qid": target, "error": type(error).__name__ + ": " + str(error)})
    packet = {"case": case, "sources": source_map, "source_corpus": corpus,
        "retrieval_failures": failures, "property_labels": labels, "captured_at": datetime.now(timezone.utc).isoformat()}
    save(directory / "research-packet.json", packet); save(directory / "source-inventory.json", inventory)
    return {"qid": case["qid"], "sources": len(source_map), "wikipedia_languages": [s["language"] for s in source_map.values() if s["kind"] == "wikipedia"], "retrieval_failures": failures}
