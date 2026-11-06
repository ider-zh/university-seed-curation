"""Bounded Agent-requested linked-item lookup using a shared private cache."""
from copy import deepcopy
import json
import re

from .source_packet import wikidata_corpus
from .records import qid


def augment_packet(packet, requests, cache, limit=8):
    if len(requests) > limit: raise ValueError("Linked-item request budget exceeded")
    result = deepcopy(packet); result["property_labels"]["P498"] = "ISO 4217 currency code"; log = []; known = {s.get("source_qid") for s in result["sources"].values()}
    for request in requests:
        entity_id = qid(request["qid"])
        if request["purpose"] not in ("quantity_unit", "linked_identity", "geography"): raise ValueError("Unsupported lookup purpose")
        if entity_id in known:
            log.append({"requested_qid": entity_id, "already_in_packet": True}); continue
        corpus = json.dumps(result["source_corpus"], ensure_ascii=False)
        if not re.search(r"(?<![A-Za-z0-9])" + entity_id + r"(?![0-9])", corpus): raise ValueError("Requested item is not linked in bounded source evidence")
        entity, meta = cache.entity(entity_id)
        ref = "s" + str(max([int(k[1:]) for k in result["sources"]], default=0) + 1)
        result["sources"][ref] = {"kind": "wikidata", "url": "https://www.wikidata.org/w/index.php?oldid=" + str(entity["lastrevid"]),
            "publisher_role": "knowledge_base", "family": "wikimedia", "source_qid": entity["id"],
            "revision_id": entity["lastrevid"], "retrieved_at": meta["retrieved_at"]}
        result["source_corpus"][ref] = wikidata_corpus(entity, {**result["property_labels"], "P498": "ISO 4217 currency code"}, packet["case"]["languages"], False)
        known.add(entity_id); known.add(entity["id"])
        log.append({"source_ref": ref, "requested_qid": entity_id, "resolved_qid": entity["id"], "revision_id": entity["lastrevid"],
            "from_cache": meta["from_cache"], "cache_path": meta["cache_path"], "purpose": request["purpose"]})
    return result, log
