"""Recover a Research owner's unbound PR permits without replacing public work."""
import re
from pathlib import Path

from .attestations import load_json, sha, verify
from .distributed_transport import command, fetch_pull, draft_snapshot, proposal_snapshot
from .pr_export import blob, commit, batch_slug
from .records import encode, instant
from .distributed_transport import now


def _remote_head(repo, branch):
    ref='refs/heads/'+branch
    raw=command(repo,'ls-remote','--heads','origin',ref).decode().strip()
    if not raw: return None
    rows=raw.splitlines()
    if len(rows)!=1: raise ValueError('Ambiguous public branch')
    parts=rows[0].split()
    if len(parts)!=2 or parts[1]!=ref or not re.fullmatch(r'[0-9a-f]{40}',parts[0]): raise ValueError('Invalid public branch response')
    return parts[0]


def _signed_owner(repo, head, batch, stage, manifest, proposals, owner, trust):
    path=('data/proposals/'+batch+'/manifest.json' if stage=='draft' else 'data/batches/'+batch+'.json')
    document=load_json(blob(repo,head,path)); value=verify(document,trust,role='research')
    if document['key_id']!=owner or value!=manifest or manifest.get('batch_id')!=batch: raise ValueError('Recovered manifest is not owned by this Research role')
    for entity,proposal in proposals.items():
        payload=verify(proposal,trust,role='research')
        if proposal['key_id']!=owner or payload.get('qid')!=entity: raise ValueError('Recovered proposal belongs to another Research role')


def _checked_pull(agent, pull, batch, trust):
    branch='codex/university-'+batch
    if (pull.get('state') not in ('open','closed') or pull.get('base',{}).get('ref')!='main' or pull.get('head',{}).get('ref')!=branch or
        (pull.get('head',{}).get('repo') or {}).get('full_name')!=trust['repository']):
        raise ValueError('Recovered PR repository, base or branch mismatch')
    head=pull['head']['sha']; fetch_pull(agent.repo,pull['number'],head)
    stage,manifest,proposals,_=proposal_snapshot(agent.repo,pull,trust)
    _signed_owner(agent.repo,head,batch,stage,manifest,proposals,agent.owner,trust)
    return head,manifest,proposals


def _bind_tasks(agent, permit, pull, head, manifest, proposals, trust, only_missing=False):
    tasks=agent.coord.list_tasks()
    for entity in proposals:
        task=tasks.get(entity,{})
        if task.get('owner')!=agent.owner or (task.get('pr_number') is not None and task['pr_number']!=pull['number']):
            raise ValueError('Recovered proposal has no matching owned task')
    repaired=0
    for entity,document in proposals.items():
        task=tasks[entity]
        if only_missing and task.get('pr_number')==pull['number']: continue
        if not only_missing and task.get('phase') in ('merged','unresolved'): continue
        if task.get('token') and task.get('expires_at') and instant(task['expires_at'])>instant(now()):
            lease={key:task[key] for key in ('qid','owner','token','expires_at')}; agent.coord.heartbeat_task(lease,now())
        else: lease=agent.coord.claim_task(entity,agent.owner,now(),allow_resume=True)
        payload=verify(document,trust,role='research')
        if only_missing:
            agent.coord.set_task(lease,task['phase'],now(),pr_number=pull['number'])
        else:
            agent.coord.set_task(lease,'review_pending',now(),pr_number=pull['number'],head_sha=head,
                base_sha=manifest['base_commit'],batch_id=permit['batch_id'],proposal_sha256=sha(encode(payload)),revision=task.get('revision',0))
        state=agent._load(); item=state['tasks'].setdefault(entity,{})
        item.update({'lease':lease,'pr_number':pull['number'],'revision':task.get('revision',0)})
        if not only_missing: item.pop('prepared',None)
        agent._save(state); repaired+=1
    if not only_missing: agent.coord.bind_pr_permit(permit,pull['number'],now())
    return repaired


def recover_unbound_permits(agent, trust):
    """Recover this role's permit metadata; never delete a public branch or PR."""
    agent._require('research')
    if getattr(agent.client,'repository',None)!=trust['repository']: raise ValueError('GitHub client repository mismatch')
    runtime,_=agent.coord.read('coord/runtime'); statuses=[]
    for permit in runtime.get('pr_permits',[]):
        if permit.get('owner')!=agent.owner: continue
        batch=batch_slug(permit['batch_id']); branch='codex/university-'+batch
        if permit.get('pr_number'):
            pull=agent.client.pull(permit['pr_number'])
            head,manifest,proposals=_checked_pull(agent,pull,batch,trust)
            fresh=agent.client.pull(pull['number'])
            if fresh['head']['sha']!=head: raise ValueError('Bound PR head changed before recovery')
            repaired=_bind_tasks(agent,permit,fresh,head,manifest,proposals,trust,only_missing=True)
            if repaired: statuses.append({'batch_id':batch,'status':'repaired_bound_pr','pr_number':pull['number'],'tasks':repaired})
            continue
        pulls=agent.client.find_branch(branch)
        if len(pulls)>1: statuses.append({'batch_id':batch,'status':'ambiguous_existing_pr'}); continue
        if pulls:
            pull=agent.client.pull(pulls[0]['number'])
            head,manifest,proposals=_checked_pull(agent,pull,batch,trust)
            fresh=agent.client.pull(pull['number'])
            if fresh['head']['sha']!=head: raise ValueError('Recovered PR head changed before binding')
            _bind_tasks(agent,permit,fresh,head,manifest,proposals,trust)
            statuses.append({'batch_id':batch,'status':'bound_existing_pr','pr_number':pull['number']}); continue
        head=_remote_head(agent.repo,branch)
        if head is not None:
            command(agent.repo,'fetch','--no-tags','origin','refs/heads/'+branch)
            if commit(agent.repo,'FETCH_HEAD')!=head: raise ValueError('Public branch changed during retrieval')
            manifest,proposals=draft_snapshot(agent.repo,head,trust)
            _signed_owner(agent.repo,head,batch,'draft',manifest,proposals,agent.owner,trust)
            if agent.client.find_branch(branch) or _remote_head(agent.repo,branch)!=head:
                statuses.append({'batch_id':batch,'status':'retry_discovery'}); continue
            body=('Unreviewed structured university proposals. Source caches, model logs and private keys remain local.\n\n'
                'Independent role-signed Review is required before main can receive canonical school records.\n\n'
                '<!-- university-batch '+batch+' -->')
            pull=agent.client.create(branch,'Research '+', '.join(proposals),body,draft=True)
            pull=agent.client.pull(pull['number'])
            checked,manifest,proposals=_checked_pull(agent,pull,batch,trust)
            if checked!=head: raise ValueError('Created PR does not reference the validated public branch')
            _bind_tasks(agent,permit,pull,head,manifest,proposals,trust)
            statuses.append({'batch_id':batch,'status':'created_draft_pr','pr_number':pull['number']}); continue
        if instant(permit['expires_at'])<=instant(now()):
            # Recheck both transports immediately before releasing; a public
            # branch or closed PR always wins over an expired lease.
            if agent.client.find_branch(branch) or _remote_head(agent.repo,branch) is not None:
                statuses.append({'batch_id':batch,'status':'retry_discovery'}); continue
            agent.coord.release_pr_permit(permit,now())
            statuses.append({'batch_id':batch,'status':'released_unused_permit'})
        else: statuses.append({'batch_id':batch,'status':'waiting_for_permit_expiry'})
    return statuses
