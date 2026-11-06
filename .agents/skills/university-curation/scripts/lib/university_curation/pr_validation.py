"""Validate data PRs with trusted base code; never execute code from the PR."""
import sys
from .git_data import git, blob, canonical_json, record_relative, commit
from .native_research import _base
from .unified_publish import verify_files
from .workflow_contract import baseline_at, check_proposal
from .manager import BACKLOG, backlog_at, check_requests, required_requests
from .records import encode


def validate_pr(repo, base, head, merged=None):
    base=commit(repo,base); head=commit(repo,head)
    ancestor=git(repo,'merge-base',base,head).decode().strip()
    names=git(repo,'diff','--name-only',ancestor,head).decode().splitlines()
    if not names or any(not p.startswith('data/') for p in names):
        raise ValueError('Data PR must contain only generated data files')
    files={p:blob(repo,head,p) for p in names}
    # A generated backlog can be byte-identical to the base and absent from diff.
    # Validate its actual committed bytes alongside the changed bundle files.
    files.setdefault(BACKLOG,blob(repo,head,BACKLOG))
    _,trust,catalog,digest=_base(repo,base)
    manifests=[p for p in names if p.startswith('data/batches/')]
    published=[]
    if manifests:
        if len(manifests)!=1: raise ValueError('One batch per data PR')
        manifest=canonical_json(files[manifests[0]]); original=manifest['base_commit']
        git(repo,'merge-base','--is-ancestor',original,base)
        created=git(repo,'log','--diff-filter=A','--format=%H',head,'--',manifests[0]).decode().splitlines()[0]
        frozen={p:blob(repo,created,p) for p in files}
        verify_files(repo,original,frozen,trust)
        if any(files[p]!=frozen[p] for p in names if p!=BACKLOG):
            raise ValueError('PR altered approved bundle after creation')
        for row in manifest['records']:
            entity=row['qid']; proposal=canonical_json(files[row['receipt_path']])['research']
            baseline,_=baseline_at(repo,base,entity)
            check_proposal(proposal,baseline,catalog,digest,trust)
            check_requests(required_requests(repo,base,entity),proposal['open_requests'])
            if blob(repo,base,row['receipt_path'],optional=True) is not None:
                raise ValueError('Batch already published')
            published.append(entity)
    else:
        if names!=[BACKLOG]: raise ValueError('Checkpoint PR may only change the backlog')
        original=ancestor
    old=backlog_at(repo,ancestor)['tasks']; proposed=canonical_json(files[BACKLOG])['tasks']
    current=backlog_at(repo,base)['tasks']
    changed={q for q in old.keys()|proposed.keys() if old.get(q)!=proposed.get(q)}
    for q in changed:
        if current.get(q)!=old.get(q): raise ValueError('Concurrent task change: '+q)
    expected=dict(current)
    for q in changed:
        if q in proposed: expected[q]=proposed[q]
        else: expected.pop(q,None)
    from .manager import validate_checkpoint, BACKLOG_TYPE
    checkpoint={'type':BACKLOG_TYPE,'tasks':expected}
    validate_checkpoint(backlog_at(repo,base),checkpoint,published)
    if merged:
        if canonical_json(blob(repo,merged,BACKLOG))!=checkpoint:
            raise ValueError('Merged backlog lost concurrent task changes')
        for path,raw in files.items():
            if path!=BACKLOG and blob(repo,merged,path)!=raw:
                raise ValueError('Merged data differs from reviewed bundle')
    return {'status':'validated','qids':published}


if __name__=='__main__':
    import json
    args=sys.argv[1:]
    ancestor=git('.', 'merge-base', args[0], args[1]).decode().strip()
    names=git('.', 'diff','--name-only',ancestor,args[1]).decode().splitlines()
    if any(p.startswith('data/') for p in names):
        print(json.dumps(validate_pr('.',*args)))
    else:
        print(json.dumps({'status':'development_pr','data_changed':False}))
