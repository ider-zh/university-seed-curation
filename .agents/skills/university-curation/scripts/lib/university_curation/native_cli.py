"""Single-manager native Research/Review and guarded direct-main publication."""
import argparse
import json
import secrets
from pathlib import Path

from . import manager, native_research, native_review, unified_publish
from .integrity import load_json, private_path, sha
from .git_data import git
from .records import ROOT, encode
from .recency import recency_index


def _json(path): return load_json(Path(path).read_bytes())
def _base(repo,ref): return native_research._base(repo,ref)


def _private_output(path):
    path=private_path(path)
    if path.exists(): raise FileExistsError('Use a new private output path')
    return path


def _save(path,value):
    path=_private_output(path); path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(encode(value)); return path


def next_candidates(repo,base_ref='origin/main',limit=5,now=None,seed=None):
    base,trust,catalog,digest=_base(repo,base_ref)
    studied=recency_index(repo,base,Path(repo)/'.private/native/recency-index.json')
    seed=secrets.randbits(64) if seed is None else seed
    rows=manager.next_tasks(repo,base,catalog,studied,limit,now,seed)
    return {'status':'advisory','base_commit':base,'tasks':rows,'claims_created':False,'selection_seed':seed,
            'coordination':'single_manager_local_checkpoint_and_main_backlog'}


def direct_main(repo,output,files,base,repository,qids=()):
    target=_private_output(output); tree=git(repo,'rev-parse',base+'^{tree}').decode().strip()
    operations=[]; elements=[]
    for index,(path,raw) in enumerate(sorted(files.items())):
        if not path.startswith('data/') or '..' in path.split('/'):
            raise ValueError('Direct publication accepts only structured data files')
        label='blob_'+str(index)
        operations.append({'tool':'mcp__codex_apps__github_create_blob','arguments':{
            'repository_full_name':repository,'content':raw.decode('utf-8'),'encoding':'utf-8'},'output':label})
        elements.append({'path':path,'mode':'100644','type':'blob','sha':'$'+label})
    operations.extend([
        {'tool':'mcp__codex_apps__github_create_tree','arguments':{'repository_full_name':repository,'base_tree_sha':tree,'tree_elements':elements},'output':'tree_sha'},
        {'tool':'mcp__codex_apps__github_create_commit','arguments':{'repository_full_name':repository,'message':'Apply reviewed university batch','tree_sha':'$tree_sha','parent_sha':base},'output':'commit_sha'},
        {'tool':'mcp__codex_apps__github_update_ref','arguments':{'repository_full_name':repository,'branch_name':'main','sha':'$commit_sha','expected_sha':base,'force':False}}
    ])
    target.mkdir(parents=True)
    for name,raw in files.items():
        path=target/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(raw)
    payload={'status':'awaiting_plugin_commit','kind':'direct_main','repository':repository,'base_commit':base,
        'qids':list(qids),'files':{path:sha(raw) for path,raw in sorted(files.items())},'operations':operations,
        'preflight':['Confirm actual GitHub main head equals base_commit','Validate exact approved files',
                     'On expected-head conflict refresh main and repeat offline Review'],
        'after_commit':'Fetch main, then run publication-confirm against the actual remote commit'}
    (target/'operations.json').write_bytes(encode(payload))
    for entity in qids: manager.set_phase(repo,entity,'publishing',bundle=str(target))
    return {'status':'direct_main_bundle_prepared','output':str(target),'operations_path':str(target/'operations.json'),'base_commit':base}


def _prepare(repo,args):
    base,_,_,_=_base(repo,args.base_ref)
    if args.command=='research-prepare':
        entity=args.qid; phase='researching'
        required=manager.required_requests(repo,base,entity)
        feedback=_json(args.feedback) if args.feedback else {'open_requests':required}
        manager.check_requests(required,feedback.get('open_requests',[]))
        manager.begin(repo,base,entity,phase,args.job)
        manager.set_phase(repo,entity,phase,open_requests=feedback['open_requests'])
        try:
            result=native_research.prepare(repo,entity,args.job,args.base_ref,feedback,
                _json(args.external_leads) if args.external_leads else None)
        except BaseException as error:
            manager.failure(repo,entity,phase,error); raise
        return result
    proposal=_json(args.proposal); entity=proposal['qid']; phase='reviewing'
    manager.check_requests(manager.required_requests(repo,base,entity),proposal.get('open_requests',[]))
    task=manager._read(repo)['tasks'].get(entity,{})
    if (task.get('proposal')!=str(private_path(args.proposal)) or
            task.get('research_job')!=str(private_path(args.research_job))):
        raise ValueError('Review must inspect the current manager Research proposal and snapshot')
    manager.begin(repo,base,entity,phase,args.job)
    try: return native_review.prepare(repo,args.proposal,args.job,args.base_ref,args.research_job)
    except BaseException as error:
        manager.failure(repo,entity,phase,error); raise



def rebind_proposal(repo, proposal_file, output, base_ref='origin/main'):
    """Invalidate stale approvals and bind unchanged Research to fetched main."""
    from .workflow_contract import baseline_at, check_proposal, attach_transport
    from .git_data import blob
    source=private_path(proposal_file); proposal=_json(source); entity=proposal['qid']
    base,trust,catalog,digest=_base(repo,base_ref)
    baseline,_=baseline_at(repo,base,entity)
    check_proposal(proposal,baseline,catalog,digest,trust)
    manager.check_requests(manager.required_requests(repo,base,entity),proposal.get('open_requests',[]))
    if proposal['transport']['base_commit']==base:
        raise ValueError('Proposal is already bound to current main; prepare fresh Review')
    rebound=attach_transport(proposal,trust['repository'],base,digest,trust)
    def mutate(state):
        task=state['tasks'].get(entity,{})
        if task.get('phase') not in ('review_pending','ready_to_publish','publishing') or task.get('proposal')!=str(source):
            raise ValueError('Rebind only the current inactive manager proposal')
        # Match the immutable compiled Research body, never accept a new delta.
        raw=dict(proposal); raw.pop('transport')
        job=private_path(task['research_job'])
        if not any(_json(p)==raw for p in (job/'compile-attempts').glob('*/public-proposal.json')):
            raise ValueError('Proposal differs from compiled Research')
        if task.get('bundle'):
            plan=_json(Path(task['bundle'])/'operations.json')
            for path,expected in plan['files'].items():
                if path.startswith('data/batches/'):
                    existing=blob(repo,base,path,optional=True)
                    if existing is not None:
                        raise ValueError('Batch already exists on main; confirm publication before rebinding')
        path=_save(output,rebound)
        for key in ('review_job','review_attempt','bundle','expires_at'):
            task.pop(key,None)
        task.update(phase='review_pending',proposal=str(path))
        return {'status':'transport_rebound','qid':entity,'base_commit':base,
                'proposal_path':str(path),'fresh_review_required':True}
    return manager.update(repo,mutate)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',default=str(ROOT))
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor')
    p=sub.add_parser('next'); p.add_argument('--seed',type=int,help='Replay randomized Research selection on the same eligible tasks'); p.add_argument('--limit',type=int,default=5); p.add_argument('--base-ref',default='origin/main')
    p=sub.add_parser('research-prepare'); p.add_argument('--qid',required=True); p.add_argument('--job',required=True); p.add_argument('--base-ref',default='origin/main'); p.add_argument('--feedback'); p.add_argument('--external-leads')
    p=sub.add_parser('review-prepare'); p.add_argument('--proposal',required=True); p.add_argument('--job',required=True); p.add_argument('--base-ref',default='origin/main'); p.add_argument('--research-job',required=True)
    for name in ('research-compile','review-compile'):
        p=sub.add_parser(name); p.add_argument('--job',required=True); p.add_argument('--result',required=True); p.add_argument('--session',required=True); p.add_argument('--model',required=True); p.add_argument('--effort',default='medium'); p.add_argument('--completed-at')
    p=sub.add_parser('unified-proposal'); p.add_argument('--rebind',action='store_true',help='Rebind the current inactive proposal after a main conflict; invalidate old approval'); p.add_argument('--proposal',required=True); p.add_argument('--output',required=True); p.add_argument('--base-ref',default='origin/main')
    p=sub.add_parser('unified-publish'); p.add_argument('--proposal',action='append',required=True); p.add_argument('--review-job',action='append',required=True); p.add_argument('--review-attempt',action='append',required=True); p.add_argument('--batch-id',required=True); p.add_argument('--base-ref',default='origin/main'); p.add_argument('--output',required=True)
    p=sub.add_parser('publication-confirm'); p.add_argument('--bundle',required=True); p.add_argument('--published-ref',required=True)
    p=sub.add_parser('checkpoint'); p.add_argument('--output',required=True); p.add_argument('--base-ref',default='origin/main')
    p=sub.add_parser('job-heartbeat'); p.add_argument('--qid',required=True)
    a=parser.parse_args(argv); repo=Path(a.workspace).resolve()
    if a.command=='doctor': result=native_research.doctor(repo)
    elif a.command=='next': result=next_candidates(repo,a.base_ref,a.limit,seed=a.seed)
    elif a.command.endswith('-prepare'): result=_prepare(repo,a)
    elif a.command in ('research-compile','review-compile'):
        meta=_json(Path(a.job)/'job.json'); entity=meta['qid']
        kind='research' if a.command=='research-compile' else 'review'
        manager.require_job(repo,entity,kind,a.job)
        module=native_research if kind=='research' else native_review
        result=module.compile(repo,a.job,a.result,a.session,a.model,a.effort,a.completed_at)
        if kind=='research': manager.set_phase(repo,entity,'review_pending',proposal=result['public_proposal_path'])
        else:
            manager.review_completed(repo,entity,a.job,result)
            result['checkpoint_required']=result['decision']!='approve'
    elif a.command=='unified-proposal' and a.rebind:
        result=rebind_proposal(repo,a.proposal,a.output,a.base_ref)
    elif a.command=='unified-proposal':
        entity=_json(a.proposal)['qid']; task=manager._read(repo)['tasks'].get(entity,{})
        if task.get('phase')!='review_pending' or task.get('proposal')!=str(private_path(a.proposal)):
            raise ValueError('Bind only the current compiled Research proposal')
        proposal=unified_publish.transport_proposal(repo,a.base_ref,a.proposal)
        path=_save(a.output,proposal)
        manager.set_phase(repo,proposal['qid'],'review_pending',proposal=str(path))
        result={'status':'transport_prepared','proposal_path':str(path)}
    elif a.command=='unified-publish':
        if len(a.proposal)!=len(a.review_job) or len(a.proposal)!=len(a.review_attempt): raise ValueError('Proposal/Review job/attempt count mismatch')
        base,trust,_,_=_base(repo,a.base_ref)
        files=unified_publish.files(repo,base,a.batch_id,list(zip(a.proposal,a.review_job,a.review_attempt)))
        entities=[_json(p)['qid'] for p in a.proposal]
        result=direct_main(repo,a.output,files,base,trust['repository'],entities)
    elif a.command=='publication-confirm': result=manager.confirm_publication(repo,a.bundle,a.published_ref)
    elif a.command=='checkpoint':
        base,trust,catalog,_=_base(repo,a.base_ref)
        raw=manager.after_publication(repo,base,())
        if any(entity not in catalog for entity in load_json(raw)['tasks']): raise ValueError('Checkpoint QID outside catalog')
        result=direct_main(repo,a.output,{manager.BACKLOG:raw},base,trust['repository'])
    else:
        from datetime import timedelta
        from .records import instant
        def renew(state):
            task=state['tasks'][a.qid]
            if task.get('phase') not in manager.ACTIVE or instant(task['expires_at'])<=instant(manager.now()):
                raise ValueError('No unexpired active native job')
            task['expires_at']=(instant(manager.now())+timedelta(minutes=30)).isoformat()
            return {'status':'renewed','qid':a.qid,'expires_at':task['expires_at']}
        result=manager.update(repo,renew)
    print(json.dumps(result,ensure_ascii=True)); return result
