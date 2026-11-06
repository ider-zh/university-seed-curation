#!/usr/bin/env python3
"""Generate/check the current university schema; inspect historical schema files read-only."""
import argparse
import json

from _bootstrap import ROOT
from university_curation.records import CURRENT_SCHEMA_VERSION
from university_curation.schema_v02 import schema


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('generate','check'))
    args=parser.parse_args()
    import jsonschema
    path=ROOT/'schemas'/('university.v'+CURRENT_SCHEMA_VERSION+'.schema.json')
    value=schema(CURRENT_SCHEMA_VERSION)
    jsonschema.Draft202012Validator.check_schema(value)
    encoded=json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
    if args.command=='generate': path.write_text(encoded,encoding='utf-8')
    elif path.read_text(encoding='utf-8')!=encoded:
        raise ValueError('Generated current schema differs: '+str(path))
    # Historical contracts are data artifacts, not generators or writable modes.
    for historical in (ROOT/'schemas').glob('*.schema.json'):
        if historical==path:continue
        jsonschema.Draft202012Validator.check_schema(json.loads(historical.read_text(encoding='utf-8')))


if __name__=='__main__':main()
