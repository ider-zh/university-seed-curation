"""Local native-subagent commands and reviewable GitHub plugin plans."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid

from . import native_research, native_review, native_protocol
from .attestations import load_json, private_path, sha
from .distributed_protocol import attach_transport, baseline_at
from .plugin_coordination import plan
from .pr_export import blob, commit, git, batch_slug
from .records import ROOT, encode, instant
from .tasks import cutoff
from .distributed_agent import recency_index
from .github_coordination import GitCoordinator


def _json(path): return load_json(Path(path).read_bytes())
def _base(repo, ref): return native_research._base(repo, ref)
def _private_output(path):
    path=private_path(path)
    if path.exists(): raise FileExistsError('Use a new private output path')
    return path

def _save(path, value):
    path=_private_output(path); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(encode(value)); return path


def next_candidates(repo, base_ref='origin/main', limit=3, snapshot=None, now=None):
    if not 1<=limit<=100: raise ValueError('Limit must be 1 to 100')
    base,trust,catalog,digest=_base(repo,base_ref); now=now or datetime.now(timezone.utc).isoformat(); threshold=cutoff(now)
    blocked=set()
    if snapshot is not None:
        if not isinstance(snapshot,dict): raise ValueError('Invalid coordination snapshot')
        for ref,entry in snapshot.items():
            ref=ref.removeprefix('refs/heads/')
            if not isinstance(entry,dict) or set(entry)!={'sha','state'} or not isinstance(entry['state'],dict): raise ValueError('Invalid coordination snapshot')
            if entry['sha'] is None:
                if entry['state']: raise ValueError('Absent coordination ref has state')
            elif not isinstance(entry['sha'],str) or not re.fullmatch(r'[0-9a-f]{40}',entry['sha']): raise ValueError('Invalid coordination ref SHA')
            for entity,task in entry['state'].get('tasks',{}).items():
                if ref!=GitCoordinator._task_ref(entity): raise ValueError('QID in wrong task shard')
                phase=task.get('phase'); retry=task.get('retry_after')
                if retry and instant(retry)>instant(now): blocked.add(entity); continue
                if phase in ('released','merged'): continue
                if phase=='claimed' and task.get('expires_at') and instant(task['expires_at'])<=instant(now): continue
                blocked.add(entity)
    studied=recency_index(repo,base,Path(repo)/'.private'/'native-research'/'recency-index.json')
    rows=[]
    for entity,row in sorted(catalog.items(),key=lambda item:(item[1]['queue_kind']!='primary',int(item[0][1:]))):
        if entity in blocked: continue
        updated=studied.get(entity)
        if updated and instant(updated)>threshold: continue
        rows.append({'qid':entity,'queue_kind':row['queue_kind']})
        if len(rows)>=limit: break
    return {'status':'advisory','base_commit':base,'candidates':rows,'coordination_snapshot_supplied':snapshot is not None,'claims_created':False}


def _bundle(repo, output, files, base, repository, branch, expected_head=None, kind='draft'):
    target=_private_output(output); batch_slug(branch.removeprefix('codex/university-'))
    if not branch.startswith('codex/university-'): raise ValueError('Invalid data branch')
    if expected_head is not None and not re.fullmatch(r'[0-9a-f]{40}',expected_head): raise ValueError('Invalid expected head')
    tree=git(repo,'rev-parse',base+'^{tree}').decode().strip()
    ops=[]; entries=[]
    for index,(path,raw) in enumerate(sorted(files.items())):
        if not path.startswith('data/') or '..' in path.split('/'): raise ValueError('Invalid public data path')
        name='blob_'+str(index)
        ops.append({'tool':'mcp__codex_apps__github_create_blob','arguments':{'repository_full_name':repository,'content':raw.decode('utf-8'),'encoding':'utf-8'},'output':name})
        entries.append({'path':path,'mode':'100644','type':'blob','sha':'$'+name})
    ops.append({'tool':'mcp__codex_apps__github_create_tree','arguments':{'repository_full_name':repository,'base_tree_sha':tree,'tree_elements':entries},'output':'tree_sha'})
    ops.append({'tool':'mcp__codex_apps__github_create_commit','arguments':{'repository_full_name':repository,'message':('Propose' if kind=='draft' else 'Apply reviewed')+' university batch','tree_sha':'$tree_sha','parent_sha':base},'output':'commit_sha'})
    if expected_head:
        ops.append({'tool':'mcp__codex_apps__github_update_ref','arguments':{'repository_full_name':repository,'branch_name':branch,'sha':'$commit_sha','expected_sha':expected_head,'force':True}})
    else: ops.append({'tool':'mcp__codex_apps__github_create_branch','arguments':{'repository_full_name':repository,'branch_name':branch,'sha':'$commit_sha'}})
    target.mkdir(parents=True)
    for name,raw in files.items():
        path=target/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(raw)
    payload={'status':'awaiting_plugin_commit','kind':kind,'repository':repository,'base_commit':base,'branch':branch,'expected_head':expected_head,
             'files':{name:sha(raw) for name,raw in sorted(files.items())},'operations':ops,
             'after_commit':'create_draft_pr' if kind=='draft' and expected_head is None else ('verify_then_mark_ready' if kind=='final' else 'verify_updated_draft'),
             'host_prerequisites':(['confirm repository, PR number, branch and current head using the GitHub plugin','confirm complete owner-attributed PR comments and active Review state'] if kind=='final' else
                (['confirm repository, branch and current head using the GitHub plugin'] if expected_head else ['confirm repository and branch absence using the GitHub plugin'])) +
                (['preserve the old head in the coordination shard ancestry before updating the branch'] if expected_head else [])}
    (target/'operations.json').write_bytes(encode(payload))
    return {'status':'bundle_prepared','output':str(target),'operations_path':str(target/'operations.json'),'base_commit':base,'branch':branch}


def draft(repo, proposal_paths, batch, base_ref, output, expected_head=None):
    batch_slug(batch); base,trust,catalog,digest=_base(repo,base_ref); proposals=[]
    for path in proposal_paths:
        proposal=_json(path)
        if 'transport' not in proposal:
            proposal=attach_transport(proposal,trust['repository'],base,digest,trust); proposal['transport']['protocol']='native-subagent-v1'
        proposals.append(proposal)
    files=native_protocol.draft_files(repo,base,proposals,batch)
    return _bundle(repo,output,files,base,trust['repository'],'codex/university-'+batch,expected_head)


def decision(repo, proposal_path, verdict_path, pr, head, output, base_ref='origin/main'):
    if type(pr) is not int or pr<1 or not re.fullmatch(r'[0-9a-f]{40}',head): raise ValueError('Invalid PR/head')
    base,trust,catalog,digest=_base(repo,base_ref); proposal=_json(proposal_path); verdict=deepcopy(_json(verdict_path)); entity=proposal['qid']
    baseline,_=baseline_at(repo,base,entity); native_protocol.check_proposal(proposal,baseline,catalog,digest,trust)
    for i,row in enumerate(verdict.get('requests',[])):
        row['request_id']=str(uuid.uuid5(uuid.NAMESPACE_URL,sha(encode({'proposal':verdict['proposal_sha256'],'session':verdict['review_session'],'index':i,'request':row}))))
    verdict.update({'type':'university-native-review-v1','repository':trust['repository'],'pr_number':pr,'reviewed_head_sha':head,'policy':trust['review_policy'],'schema_sha256':trust['schemas']['0.2.2']})
    native_protocol.check_decision(verdict,proposal,baseline,trust,pr)
    path=_save(output,{'decision':verdict,'comment_body':native_protocol.review_comment(verdict),'pr_number':pr,'reviewed_head_sha':head})
    return {'status':'comment_prepared','output':str(path),'pr_number':pr,'reviewed_head_sha':head}


def finalize(repo, head_ref, pr, comments_path, base_ref, output, exclude_unresolved=(), snapshot=None):
    if type(pr) is not int or pr<1: raise ValueError('Invalid PR')
    head=commit(repo,head_ref); base,trust,catalog,digest=_base(repo,base_ref)
    names=git(repo,'ls-tree','-r','--name-only',head,'--','data/proposals').decode().splitlines()
    manifests=[p for p in names if re.fullmatch(r'data/proposals/[a-z0-9][a-z0-9-]{0,79}/manifest\.json',p)]
    existing_decisions={}
    if len(manifests)==1:
        manifest=_json_bytes(blob(repo,head,manifests[0])); original=manifest['base_commit']
        _,proposals=native_protocol.inspect_draft(repo,original,head,trust)
    elif not manifests:
        parents=git(repo,'rev-list','--parents','-n','1',head).decode().split()
        if len(parents)!=2 or parents[0]!=head or not re.fullmatch(r'[0-9a-f]{40}',parents[1]): raise ValueError('Final head must have one original base parent')
        original=parents[1]
        paths=[p for p in git(repo,'diff','--no-renames','--name-only','-z',original,head).decode().split('\0') if p]
        files={p:blob(repo,head,p) for p in paths}
        original_trust=native_protocol.legacy.trust_at(repo,original)
        old=native_protocol.verify_final(repo,original,files,original_trust)
        if old['review_pr']!=pr: raise ValueError('Review PR mismatch')
        manifest={'batch_id':old['batch_id']}; proposals={}
        for entity in old['qids']:
            receipt=_json_bytes(files['data/reviews/'+old['batch_id']+'/'+entity+'.json'])
            proposals[entity]=receipt['research']; existing_decisions[entity]=receipt['review']
    else: raise ValueError('Expected one Draft manifest')
    comments=_json(comments_path)
    if not isinstance(comments,list): raise ValueError('Expected complete PR comment array')
    exclusions=set(exclude_unresolved)
    if len(exclusions)!=len(exclude_unresolved) or not exclusions.issubset(proposals): raise ValueError('Invalid unresolved exclusions')
    if exclusions and not isinstance(snapshot,dict): raise ValueError('Unresolved exclusions require coordination snapshot')
    for entity in exclusions:
        ref=GitCoordinator._task_ref(entity)
        entry=snapshot.get(ref) or snapshot.get('refs/heads/'+ref)
        valid_entry=(isinstance(entry,dict) and set(entry)=={'sha','state'} and isinstance(entry['sha'],str) and re.fullmatch(r'[0-9a-f]{40}',entry['sha']) and isinstance(entry['state'],dict))
        task=entry['state'].get('tasks',{}).get(entity,{}) if valid_entry else {}
        if task.get('phase')!='unresolved' or task.get('pr_number')!=pr or task.get('proposal_sha256')!=sha(encode(proposals[entity])):
            raise ValueError('Exclusion lacks matching unresolved coordination state')
    decisions={}
    for entity,proposal in proposals.items():
        if entity in exclusions: continue
        baseline,_=baseline_at(repo,base,entity); native_protocol.check_proposal(proposal,baseline,catalog,digest,trust)
        reviews=native_protocol.read_reviews(comments,trust,pr,entity,sha(encode(proposal)))
        if not reviews: raise ValueError('Missing owner-attributed Review')
        value=reviews[-1][0]; verdict,record=native_protocol.check_decision(value,proposal,baseline,trust,pr)
        if entity in existing_decisions and value!=existing_decisions[entity]: raise ValueError('Existing receipt is not latest owner Review')
        if verdict['decision']!='approve' or record is None: raise ValueError('Latest Review does not approve')
        if native_protocol.read_requests(comments,trust,pr,entity,resolved_by_validated_decision=value): raise ValueError('Unresolved Review objections')
        decisions[entity]=value
    proposals={entity:value for entity,value in proposals.items() if entity not in exclusions}
    if not proposals: return {'status':'all_unresolved','pr_number':pr,'qids':sorted(exclusions),'head_sha':head,'action':'no_change'}
    files=native_protocol.finalized_files(repo,base,manifest['batch_id'],proposals,decisions)
    verified=native_protocol.verify_final(repo,base,files,trust)
    if verified['review_pr']!=pr: raise ValueError('Review PR mismatch')
    return _bundle(repo,output,files,base,trust['repository'],'codex/university-'+manifest['batch_id'],head,'final')


def _json_bytes(raw): return load_json(raw)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--workspace',default=str(ROOT)); parser.add_argument('--role',required=True,choices=('research','review'))
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor')
    n=sub.add_parser('next'); n.add_argument('--limit',type=int,default=3); n.add_argument('--snapshot'); n.add_argument('--base-ref',default='origin/main')
    r=sub.add_parser('research-prepare'); r.add_argument('--qid',required=True); r.add_argument('--job',required=True); r.add_argument('--base-ref',default='origin/main'); r.add_argument('--feedback')
    for name in ('research-compile','review-compile'):
        p=sub.add_parser(name); p.add_argument('--job',required=True); p.add_argument('--result',required=True); p.add_argument('--session',required=True); p.add_argument('--model',required=True); p.add_argument('--effort',default='medium'); p.add_argument('--completed-at')
    r=sub.add_parser('review-prepare'); r.add_argument('--proposal',required=True); r.add_argument('--job',required=True); r.add_argument('--base-ref',default='origin/main')
    p=sub.add_parser('coord-plan'); p.add_argument('--snapshot',required=True); p.add_argument('--action',required=True); p.add_argument('--arguments',required=True); p.add_argument('--output',required=True); p.add_argument('--bootstrap-parent-sha')
    p=sub.add_parser('draft'); p.add_argument('--proposal',action='append',required=True); p.add_argument('--batch-id',required=True); p.add_argument('--base-ref',default='origin/main'); p.add_argument('--expected-head'); p.add_argument('--output',required=True)
    p=sub.add_parser('decision'); p.add_argument('--proposal',required=True); p.add_argument('--verdict',required=True); p.add_argument('--pr',type=int,required=True); p.add_argument('--head-sha',required=True); p.add_argument('--base-ref',default='origin/main'); p.add_argument('--output',required=True)
    p=sub.add_parser('finalize'); p.add_argument('--head-ref',required=True); p.add_argument('--pr',type=int,required=True); p.add_argument('--comments',required=True); p.add_argument('--base-ref',default='origin/main'); p.add_argument('--output',required=True); p.add_argument('--exclude-unresolved',action='append',default=[]); p.add_argument('--snapshot')
    a=parser.parse_args(argv); repo=Path(a.workspace).resolve()
    research={'next','research-prepare','research-compile','draft','finalize'}; review={'review-prepare','review-compile','decision'}
    if (a.command in research and a.role!='research') or (a.command in review and a.role!='review'): parser.error('Command belongs to the other role')
    if a.command=='doctor': result=native_research.doctor(repo)
    elif a.command=='next': result=next_candidates(repo,a.base_ref,a.limit,_json(a.snapshot) if a.snapshot else None)
    elif a.command=='research-prepare': result=native_research.prepare(repo,a.qid,a.job,a.base_ref,_json(a.feedback) if a.feedback else None)
    elif a.command=='review-prepare': result=native_review.prepare(repo,a.proposal,a.job,a.base_ref)
    elif a.command in ('research-compile','review-compile'):
        module=native_research if a.command=='research-compile' else native_review
        result=module.compile(repo,a.job,a.result,a.session,a.model,a.effort,a.completed_at)
    elif a.command=='coord-plan':
        base,trust,_,_=_base(repo,'origin/main'); value=plan(_json(a.snapshot),a.action,_json(a.arguments),repository=trust['repository'],bootstrap_parent_sha=a.bootstrap_parent_sha or base)
        path=_save(a.output,value); result={'status':value['status'],'output':str(path)}
    elif a.command=='draft': result=draft(repo,a.proposal,a.batch_id,a.base_ref,a.output,a.expected_head)
    elif a.command=='decision': result=decision(repo,a.proposal,a.verdict,a.pr,a.head_sha,a.output,a.base_ref)
    else: result=finalize(repo,a.head_ref,a.pr,a.comments,a.base_ref,a.output,a.exclude_unresolved,_json(a.snapshot) if a.snapshot else None)
    print(json.dumps(result,ensure_ascii=True)); return result
