"""Online Wikidata query and Wikipedia page-get entry point for the built-in skill."""
import argparse
import json
import os
import sys

import _bootstrap  # Initialize the checkout-local package path.
from university_curation.sources import Cache


def main():
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--cache", default=os.environ.get("UNIVERSITY_SOURCE_CACHE", ".private/cache/sources"))
    p.add_argument("--maxlag", type=int, default=30, help="API replication-lag tolerance in seconds, 1..60; default 30")
    p.add_argument("--timeout", type=float, default=90, help="HTTP socket timeout in seconds, 1..600; default 90")
    commands = p.add_subparsers(dest="command", required=True)
    get = commands.add_parser("wikidata-get"); get.add_argument("qid"); get.add_argument("--properties", nargs="*", default=[])
    get.add_argument("--languages", nargs="+", default=["en", "zh"]); get.add_argument("--resolve", nargs="*", default=[]); get.add_argument("--linked-limit", type=int, default=12); get.add_argument("--refresh", action="store_true")
    query = commands.add_parser("wikidata-search"); query.add_argument("query"); query.add_argument("--language", default="en"); query.add_argument("--limit", type=int, default=10)
    page = commands.add_parser("wikipedia-get"); page.add_argument("--language", required=True)
    target = page.add_mutually_exclusive_group(required=True); target.add_argument("--qid"); target.add_argument("--title"); target.add_argument("--oldid", type=int)
    page.add_argument("--refresh", action="store_true"); page.add_argument("--view", choices=["summary", "infobox", "text"], default="summary")
    page.add_argument("--section"); page.add_argument("--offset", type=int, default=0); page.add_argument("--max-chars", type=int, default=12000)
    args = p.parse_args(); cache = Cache(args.cache, maxlag=args.maxlag, timeout=args.timeout)
    if args.command == "wikidata-get": result = cache.wikidata_get(args.qid, args.properties, args.languages, args.resolve, args.linked_limit, args.refresh)
    elif args.command == "wikidata-search": result = cache.wikidata_search(args.query, args.language, args.limit)
    else:
        if args.offset < 0 or not 1 <= args.max_chars <= 100000: p.error("Invalid text window")
        result = cache.wikipedia_get(args.language, args.title, args.qid, args.oldid, args.refresh)
        sections = result.pop("text_sections")
        if args.view == "summary":
            result["sections"] = [{"id": s["id"], "title": s["title"], "characters": len(s["text"])} for s in sections]
        elif args.view == "text":
            chosen = [s for s in sections if args.section is None or args.section in (s["id"], s["title"])]
            if not chosen: raise ValueError("Section not found; use the summary section IDs")
            text = "\n\n".join(s["title"] + "\n" + s["text"] for s in chosen)
            result["text"] = text[args.offset:args.offset + args.max_chars]; result["offset"] = args.offset
            if args.offset + args.max_chars < len(text): result["next_offset"] = args.offset + args.max_chars
            result.pop("infobox", None)
        else: result.pop("section_index", None)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__": main()
