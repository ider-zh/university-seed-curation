"""Small, scriptable entry point for independent GitHub-coordinated agents."""
import argparse
from pathlib import Path
import subprocess
import threading

from .attestations import private_path
from . import codex_provider
from .distributed_agent import RoleAgent, now
from .distributed_feedback import submit_objection, CATEGORIES
from .distributed_protocol import trust_at, catalog_at
from .distributed_transport import fetch_main, ensure_origin
from .records import ROOT
from .research_github import GitHub
from .role_registration import register


def parser():
    p=argparse.ArgumentParser(description='Run one step of a distributed university Research or Review role')
    p.add_argument('--workspace',default=str(ROOT)); p.add_argument('--role',required=True,choices=('research','review'))
    p.add_argument('--key',help='Role-specific private key under .private (default: .private/keys/ROLE.pem)')
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('doctor','register-key','roles-check','next-review','sync'): sub.add_parser(name)
    next_task=sub.add_parser('next'); next_task.add_argument('--limit',type=int,default=1,choices=(1,2,3))
    research=sub.add_parser('research'); research.add_argument('--qid',required=True); research.add_argument('--pr',type=int)
    publish=sub.add_parser('publish'); publish.add_argument('--batch-size',type=int,default=5,choices=(1,2,3,4,5)); publish.add_argument('--pr',type=int)
    review=sub.add_parser('review'); review.add_argument('--pr',type=int,required=True)
    objection=sub.add_parser('review-request'); objection.add_argument('--pr',type=int,required=True); objection.add_argument('--qid',required=True)
    objection.add_argument('--field',required=True); objection.add_argument('--category',required=True,choices=sorted(CATEGORIES)); objection.add_argument('--reason',required=True)
    return p


def _configured(workspace):
    base=fetch_main(workspace); trust=trust_at(workspace,base); ensure_origin(workspace,trust['repository'])
    return base,trust


def _roles(trust):
    result={role:[] for role in ('research','review')}
    for key,entry in trust.get('keys',{}).items():
        roles=entry.get('roles',[])
        if entry.get('status')=='active' and roles in (['research'],['review']): result[roles[0]].append(key)
    return {role:sorted(keys) for role,keys in result.items()}


def _doctor(workspace,role,key):
    base,trust=_configured(workspace); catalog,_=catalog_at(workspace,base,trust)
    if not key.exists(): raise ValueError('Role private key is not configured; run register-key')
    from .attestations import sign
    probe=sign({},key,trust,role=role); entry=trust['keys'][probe['key_id']]
    if entry.get('roles')!=[role]: raise ValueError('Role key must be independent and trusted')
    cli=codex_provider.command()
    result=subprocess.run(cli+['login','status'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if __import__('os').name=='nt' else 0)
    if result.returncode: raise RuntimeError('Codex authentication unavailable')
    GitHub(trust['repository']).request('GET','')
    return {'status':'ready','role':role,'key_id':probe['key_id'],'base':base,'catalog_count':len(catalog),
        'model':trust['model'],'reasoning_effort':trust['reasoning_effort'],'github_authenticated':True,'codex_authenticated':True}


def next_review(agent):
    agent._require('review'); lease=agent.coord.claim_review(agent.owner,now())
    if lease is None: return {'status':'no_review_task'}
    cancel=threading.Event(); stop=threading.Event(); lost=[]
    def heartbeat():
        while not stop.wait(60):
            try: agent.coord.renew_review(lease,now())
            except Exception as error: lost.append(type(error).__name__); cancel.set(); return
    def fence():
        if cancel.is_set(): raise RuntimeError('Review lease lost')
        try: agent.coord.renew_review(lease,now())
        except Exception:
            cancel.set(); raise
    thread=threading.Thread(target=heartbeat,daemon=True); thread.start()
    try:
        result=agent.review_pr(lease['pr_number'],cancel_event=cancel,expected_head=lease['head_sha'],lease_guard=fence)
        fence()
        if result['status']=='mechanical_valid': outcome='approved'
        elif result['status']=='review_processed':
            statuses=[r.get('decision') if r.get('status')=='already_reviewed' else r.get('status') for r in result['results']]
            if statuses and all(v=='approve' for v in statuses): outcome='approved'
            elif any(v in ('request_changes','revision_requested') for v in statuses): outcome='changes_requested'
            else: outcome='unresolved'
        else: outcome='unresolved'
        agent.coord.finish_review(lease,outcome,now())
        return {**result,'queue_outcome':outcome}
    finally:
        stop.set(); thread.join(timeout=2)


def execute(args):
    workspace=Path(args.workspace).resolve(); key=private_path(args.key or workspace/'.private'/'keys'/(args.role+'.pem'))
    if args.command=='roles-check':
        base,trust=_configured(workspace); return {'status':'checked','base':base,'roles':_roles(trust)}
    if args.command=='doctor': return _doctor(workspace,args.role,key)
    if args.command=='register-key':
        _,trust=_configured(workspace); client=GitHub(trust['repository'])
        return register(workspace,key,args.role,client,workspace/'.private'/'registration')
    role_agent=RoleAgent(workspace,args.role,key)
    if args.command=='next': return role_agent.next_tasks(args.limit)
    if args.command=='research': return role_agent.research_one(args.qid,args.pr)
    if args.command=='publish': return role_agent.publish_ready(args.batch_size,args.pr)
    if args.command=='review': return role_agent.review_pr(args.pr)
    if args.command=='next-review': return next_review(role_agent)
    if args.command=='sync':
        from .distributed_sync import sync
        return sync(role_agent)
    if args.command=='review-request':
        role_agent._require('review'); pull,_,proposals,base=role_agent.public_proposals(args.pr)
        if args.qid not in proposals: raise ValueError('QID is not in the selected PR')
        trust=trust_at(workspace,base)
        return submit_objection(role_agent.client,pull,proposals[args.qid],key,trust,args.field,args.category,args.reason)
    raise ValueError('Unknown command')


def main(argv=None):
    from .records import encode
    args=parser().parse_args(argv)
    try: result=execute(args)
    except (ValueError,RuntimeError,OSError) as error:
        # Avoid logging provider stderr, source text, private traces or credentials.
        print(encode({'status':'error','error_type':type(error).__name__,'message':str(error)[:500]}).decode(),end='')
        return 1
    print(encode(result).decode(),end=''); return 0
