"""Portable online Wikidata/Wikipedia retrieval with private revision-bound caches."""
from datetime import datetime, timedelta, timezone
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import time
import random
import math
from email.utils import parsedate_to_datetime
import tempfile
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from .records import qid, instant
from .cache_lock import request_lock

USER_AGENT = "UniversitySeedCuration/0.2 (https://github.com/ider-zh/university-seed-curation)"


class RetryableSourceError(RuntimeError):
    def __init__(self, code, retry_after):
        self.code=code; self.retry_after=max(1,math.ceil(retry_after))
        super().__init__('Temporary Wikimedia source failure: '+code)


def _retry_seconds(value):
    try:
        seconds=float(value)
        return max(0,seconds) if math.isfinite(seconds) else 0
    except (TypeError,ValueError):
        try: return max(0,(parsedate_to_datetime(value)-datetime.now(timezone.utc)).total_seconds())
        except (TypeError,ValueError,OverflowError): return 0


def download(url):
    # Never shorten server Retry-After. If it exceeds the local wait budget,
    # return control to the manager so other QIDs can proceed.
    waited=0
    for attempt in range(3):
        try:
            request=Request(url,headers={'User-Agent':USER_AGENT,'Accept':'application/json'})
            with urlopen(request,timeout=45) as response:
                data=json.load(response); retry=_retry_seconds(response.headers.get('Retry-After'))
            code=data.get('error',{}).get('code')
            if code!='maxlag': return data
        except HTTPError as error:
            if error.code not in (429,503): raise
            code='http_'+str(error.code); retry=_retry_seconds(error.headers.get('Retry-After'))
        delay=max(retry,5*(2**attempt)+random.uniform(0,1))
        if attempt==2 or waited+delay>30:
            raise RetryableSourceError(code,max(60,delay))
        time.sleep(delay); waited+=delay


def language(value):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,19}", value): raise ValueError("Invalid language edition")
    return value


class Cache:
    def __init__(self, directory=None, fetch=download, now=lambda: datetime.now(timezone.utc), ttl_days=30, maxlag=5):
        self.directory = Path(directory or os.environ.get("UNIVERSITY_SOURCE_CACHE", ".private/cache/sources")).resolve()
        if ".private" not in self.directory.parts: raise ValueError("Raw source caches must be stored in a .private directory")
        if ttl_days <= 0: raise ValueError("Positive cache TTL required")
        if not 1 <= maxlag <= 60: raise ValueError("maxlag must be between 1 and 60 seconds")
        self.fetch = fetch; self.now = now; self.ttl = timedelta(days=ttl_days); self.maxlag = maxlag

    def _capture_path(self, payload):
        key = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return self.directory / "objects" / key[:3] / (key + ".json")

    @staticmethod
    def _write(path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".part")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if Path(temporary).exists(): Path(temporary).unlink()

    def request(self, endpoint, parameters, refresh=False):
        params = {**parameters, "format": "json", "formatversion": 2, "maxlag": self.maxlag}
        url = endpoint + "?" + urlencode(params)
        key = hashlib.sha256(url.encode()).hexdigest(); path = self.directory / key[:3] / (key + ".json")
        with request_lock(self.directory / "locks" / key[:3] / (key + ".lock")):
            if path.exists() and not refresh:
                try:
                    cached = json.loads(path.read_text(encoding="utf-8")); age = self.now() - instant(cached["retrieved_at"])
                    encoded = json.dumps(cached["data"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
                    if cached["request_url"] == url and timedelta(0) <= age < self.ttl and hashlib.sha256(encoded).hexdigest() == cached["body_sha256"]:
                        capture = self._capture_path(cached)
                        if capture.exists() and json.loads(capture.read_text(encoding="utf-8")) == cached:
                            return cached["data"], {"retrieved_at": cached["retrieved_at"], "from_cache": True, "cache_path": str(capture)}
                except (ValueError, KeyError, TypeError): pass
            data = self.fetch(url)
            if "error" in data: raise ValueError("MediaWiki API error: " + data["error"].get("code", "unknown") + ": " + data["error"].get("info", ""))
            if not isinstance(data, dict): raise ValueError("API did not return an object")
            payload = {"request_url": url, "retrieved_at": self.now().isoformat(), "data": data,
                "body_sha256": hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
            capture = self._capture_path(payload)
            self._write(capture, payload); self._write(path, payload)
            return data, {"retrieved_at": payload["retrieved_at"], "from_cache": False, "cache_path": str(capture)}

    def entity(self, entity_id, refresh=False):
        entity_id = qid(entity_id)
        data, meta = self.request("https://www.wikidata.org/w/api.php", {
            "action": "wbgetentities", "ids": entity_id, "props": "info|labels|descriptions|aliases|claims|sitelinks", "redirects": "yes"}, refresh)
        items = data.get("entities", {}); entity = items.get(entity_id)
        if entity is None and len(items) == 1: entity = next(iter(items.values()))
        if not entity or "missing" in entity: raise ValueError("Wikidata entity not found")
        if type(entity.get("lastrevid")) is not int or entity["lastrevid"] <= 0: raise ValueError("Entity revision missing")
        return entity, meta

    def entity_revision(self, entity_id, revision_id, refresh=False):
        """Independently re-fetch the exact entity JSON used by a cited revision."""
        entity_id = qid(entity_id)
        if type(revision_id) is not int or revision_id <= 0: raise ValueError("Positive entity revision required")
        data, meta = self.request("https://www.wikidata.org/w/api.php", {
            "action": "query", "prop": "revisions", "revids": revision_id, "rvprop": "ids|content", "rvslots": "main"}, refresh)
        pages = data.get("query", {}).get("pages", [])
        if isinstance(pages, dict): pages = list(pages.values())
        if len(pages) != 1 or pages[0].get("title") != entity_id: raise ValueError("Entity revision belongs to another item")
        revisions = pages[0].get("revisions", [])
        if len(revisions) != 1 or revisions[0].get("revid") != revision_id: raise ValueError("Entity revision mismatch")
        slot = revisions[0].get("slots", {}).get("main", {})
        entity = json.loads(slot.get("content", slot.get("*", "")))
        if entity.get("id") != entity_id: raise ValueError("Entity JSON identity mismatch")
        entity["lastrevid"] = revision_id
        return entity, meta

    def wikidata_get(self, entity_id, properties=(), languages=("en", "zh"), resolve=(), limit=12, refresh=False):
        if not 0 <= limit <= 50: raise ValueError("Linked-item limit must be 0..50")
        if any(not re.fullmatch(r"P[1-9][0-9]*", p) for p in (*properties, *resolve)): raise ValueError("Invalid property ID")
        entity, meta = self.entity(entity_id, refresh)
        wanted = list(properties) or ["P31", "P17", "P131", "P159", "P625", "P571", "P576", "P856", "P18", "P488", "P2196", "P1128"]
        claims = {}; links = set()
        for prop in wanted:
            if prop not in entity.get("claims", {}): continue
            claims[prop] = []
            for index, statement in enumerate(entity["claims"][prop]):
                snak = statement["mainsnak"]; row = {"statement_id": statement.get("id", entity["id"] + "/" + prop + "/" + str(index)),
                    "rank": statement.get("rank", "normal"), "snaktype": snak["snaktype"], "locator": entity["id"] + "/claims/" + prop + "/" + str(index)}
                if "datavalue" in snak: row["value"] = snak["datavalue"]["value"]
                if statement.get("qualifiers"):
                    row["qualifiers"] = {p: [{"snaktype": s["snaktype"], **({"value": s["datavalue"]["value"]} if "datavalue" in s else {})}
                        for s in snaks] for p, snaks in statement["qualifiers"].items()}
                if statement.get("references"): row["reference_count"] = len(statement["references"])
                claims[prop].append(row)
        for prop in resolve:
            for s in entity.get("claims", {}).get(prop, []):
                value = s.get("mainsnak", {}).get("datavalue", {}).get("value")
                if isinstance(value, dict) and isinstance(value.get("id"), str) and re.fullmatch(r"Q[1-9][0-9]*", value["id"]): links.add(value["id"])
        def labels(value, key):
            return {lang: v["value"] for lang, v in value.get(key, {}).items() if lang in languages}
        result = {"requested_qid": entity_id, "qid": entity["id"], "revision_id": entity["lastrevid"],
            "source_url": "https://www.wikidata.org/w/index.php?oldid=" + str(entity["lastrevid"]),
            "labels": labels(entity, "labels"), "descriptions": labels(entity, "descriptions"),
            "sitelinks": {site: v["title"] for site, v in entity.get("sitelinks", {}).items() if site.endswith("wiki") and site not in ("commonswiki", "specieswiki", "wikidatawiki")},
            "claims": claims, **meta}
        selected = sorted(links, key=lambda v: int(v[1:]))[:limit]
        if selected:
            result["linked_items"] = []
            for linked in selected:
                value, provenance = self.entity(linked, refresh)
                result["linked_items"].append({"qid": value["id"], "labels": labels(value, "labels"),
                    "descriptions": labels(value, "descriptions"), "revision_id": value["lastrevid"], **provenance})
        result["linked_items_truncated"] = len(links) > limit
        return result

    def wikidata_search(self, text, lang="en", limit=10):
        language(lang)
        if not text.strip() or not 1 <= limit <= 50: raise ValueError("Search text and limit 1..50 required")
        data, meta = self.request("https://www.wikidata.org/w/api.php", {"action": "wbsearchentities", "search": text,
            "language": lang, "uselang": lang, "type": "item", "limit": limit})
        result = {"results": data.get("search", []), **meta}
        if "search-continue" in data: result["next_continue"] = data["search-continue"]
        return result

    def wikipedia_get(self, lang, title=None, entity_id=None, oldid=None, refresh=False):
        language(lang)
        if sum(v is not None for v in (title, entity_id, oldid)) != 1: raise ValueError("Choose title, QID or oldid")
        if entity_id:
            entity, _ = self.entity(entity_id, refresh)
            link = entity.get("sitelinks", {}).get(lang.replace("-", "_") + "wiki")
            if not link: raise ValueError("No Wikipedia sitelink in requested language; choose another edition")
            title = link["title"]
        params = {"action": "parse", "prop": "text|wikitext|sections|revid", "redirects": 1}
        if oldid is not None:
            if oldid <= 0: raise ValueError("Positive revision required")
            params["oldid"] = oldid
        else:
            if not isinstance(title, str) or not title.strip(): raise ValueError("Page title required")
            params["page"] = title
        data, meta = self.request("https://" + lang + ".wikipedia.org/w/api.php", params, refresh)
        page = data.get("parse", {})
        if not isinstance(page.get("text"), str) or not isinstance(page.get("wikitext"), str): raise ValueError("Missing revision-consistent content")
        if any(type(page.get(k)) is not int or page[k] <= 0 for k in ("pageid", "revid")): raise ValueError("Missing page/revision identifiers")
        if oldid is not None and page["revid"] != oldid: raise ValueError("Returned another revision")
        parser = Article(); parser.feed(page["text"]); parser.close()
        return {"language": lang, "title": page["title"], "page_id": page["pageid"], "revision_id": page["revid"],
            "source_url": "https://" + lang + ".wikipedia.org/w/index.php?oldid=" + str(page["revid"]),
            "section_index": page.get("sections", []), "text_sections": parser.sections(), "infobox": parser.rows,
            "image_urls": [urljoin("https://" + lang + ".wikipedia.org", src) for src in parser.images], **meta}


class Article(HTMLParser):
    """Mechanical text/infobox projection; no semantic field extraction."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = [{"id": "lead", "title": "Lead", "parts": []}]; self.rows = []; self.images = []
        self.table_depth = 0; self.infobox_depth = 0; self.row = None; self.cell = None
        self.heading = None; self.hidden = 0

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag in ("script", "style"): self.hidden += 1
        if self.hidden: return
        if tag == "table":
            self.table_depth += 1
            if not self.infobox_depth and "infobox" in attrs.get("class", "").split(): self.infobox_depth = self.table_depth
        if self.infobox_depth:
            if tag == "tr" and self.table_depth == self.infobox_depth: self.row = {"label_parts": [], "text_parts": []}
            if tag in ("th", "td") and self.row is not None: self.cell = "label_parts" if tag == "th" else "text_parts"
            if tag == "img" and attrs.get("src") and attrs["src"] not in self.images: self.images.append(attrs["src"])
            return
        if tag in ("h2", "h3", "h4", "h5"):
            self.heading = {"tag": tag, "id": attrs.get("id", ""), "parts": []}
        elif self.heading is not None and attrs.get("id"): self.heading["id"] = attrs["id"]
        if tag in ("p", "div", "li", "br"): self.blocks[-1]["parts"].append("\n")

    def handle_data(self, value):
        if self.hidden: return
        if self.infobox_depth:
            if self.row is not None and self.cell: self.row[self.cell].append(value)
        elif self.heading is not None: self.heading["parts"].append(value)
        else: self.blocks[-1]["parts"].append(value)

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1); return
        if self.hidden: return
        if self.infobox_depth:
            if tag in ("th", "td"): self.cell = None
            if tag == "tr" and self.row is not None and self.table_depth == self.infobox_depth:
                label = " ".join("".join(self.row["label_parts"]).split()); value = " ".join("".join(self.row["text_parts"]).split())
                if label or value: self.rows.append({"label": label, "text": value})
                self.row = None
        if tag == "table":
            if self.table_depth == self.infobox_depth: self.infobox_depth = 0
            self.table_depth = max(0, self.table_depth - 1)
        if self.heading is not None and tag == self.heading["tag"]:
            title = " ".join("".join(self.heading["parts"]).split())
            self.blocks.append({"id": self.heading["id"] or title.replace(" ", "_"), "title": title, "parts": []}); self.heading = None

    def sections(self):
        return [{"id": b["id"], "title": b["title"], "text": "\n".join(" ".join(line.split()) for line in "".join(b["parts"]).splitlines() if line.strip())} for b in self.blocks]
