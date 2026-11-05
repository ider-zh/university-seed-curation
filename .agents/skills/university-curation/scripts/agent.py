#!/usr/bin/env python3
"""Use native host subagents and the connected GitHub plugin by default."""
from _bootstrap import ROOT
import sys


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    runtime = 'native'
    for index, value in enumerate(args):
        if value == '--runtime':
            if index + 1 >= len(args): raise SystemExit('--runtime requires native or cli')
            runtime = args[index + 1]; del args[index:index + 2]; break
        if value.startswith('--runtime='):
            runtime = value.split('=', 1)[1]; del args[index]; break
    if runtime == 'cli':
        from university_curation.distributed_cli import main as run
    elif runtime == 'native':
        from university_curation.native_cli import main as run
    else: raise SystemExit('--runtime must be native or cli')
    result = run(args)
    return result if isinstance(result, int) else 0

if __name__ == '__main__': raise SystemExit(main())
