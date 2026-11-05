"""Prepare/stage the signed operator-authorized seed candidate import."""
import argparse
from _bootstrap import ROOT
from university_curation.seed_delivery import prepare, stage
from university_curation.records import encode

parser = argparse.ArgumentParser(description=__doc__)
sub = parser.add_subparsers(dest="command", required=True)
p = sub.add_parser("prepare")
for arg in ("preview", "base-ref", "key", "output"): p.add_argument("--" + arg, required=True)
p = sub.add_parser("stage"); p.add_argument("--bundle", required=True)
for p in sub.choices.values(): p.add_argument("--workspace", default=str(ROOT))
args = parser.parse_args()
if args.command == "prepare": result = prepare(args.workspace, args.preview, args.base_ref, args.key, args.output)
else: result = stage(args.workspace, args.bundle)
print(encode(result).decode(), end="")
