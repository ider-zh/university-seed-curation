"""Prepare/stage a byte-preserving migration to 256 university buckets."""
import argparse
from _bootstrap import ROOT
from university_curation.bucket_migration import prepare, stage
from university_curation.records import encode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--base-ref", required=True); p.add_argument("--batch-id", required=True); p.add_argument("--output", required=True)
    p = sub.add_parser("stage"); p.add_argument("--bundle", required=True)
    for p in sub.choices.values(): p.add_argument("--workspace", default=str(ROOT))
    args = parser.parse_args()
    if args.command == "prepare": result = prepare(args.workspace, args.base_ref, args.batch_id, args.output)
    else: result = stage(args.workspace, args.bundle)
    print(encode(result).decode(), end="")


if __name__ == "__main__": main()
