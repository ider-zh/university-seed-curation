"""Prepare, independently review, and export an additive Wikidata P625 update."""
import argparse
from _bootstrap import ROOT
from university_curation.records import encode
from university_curation.coordinate_job import start, independent_review, build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--qid", required=True); p.add_argument("--base-ref", required=True)
    p.add_argument("--output", required=True); p.add_argument("--request-ref", required=True)
    p = sub.add_parser("review"); p.add_argument("--job", required=True)
    p = sub.add_parser("build"); p.add_argument("--job", required=True)
    p.add_argument("--base-ref", required=True); p.add_argument("--batch-id", required=True)
    p.add_argument("--key", required=True); p.add_argument("--output", required=True)
    for p in sub.choices.values():
        p.add_argument("--workspace", default=str(ROOT))
        p.add_argument("--cache", default=str(ROOT / ".private/cache/coordinate-sources"))
    args = parser.parse_args()
    if args.command == "prepare": result = start(args.workspace, args.qid, args.base_ref, args.cache, args.output, args.request_ref)
    elif args.command == "review": result = independent_review(args.job, args.cache, args.workspace)
    else: result = build(args.workspace, args.job, args.base_ref, args.batch_id, args.key, args.output, args.cache)
    print(encode(result).decode(), end="")


if __name__ == "__main__": main()
