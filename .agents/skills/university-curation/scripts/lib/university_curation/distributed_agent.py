"""One-step, role-separated distributed Research and Review agents.

GitHub coordination refs and signed PRs are authoritative. Local state is only
this role/key's resumable private cache and never another role's input.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import subprocess
import tarfile
import threading
import uuid

from .attestations import load_json, private_path, sha, sign, verify
from .distributed_feedback import requests_from_comments, assert_no_objections
from .distributed_jobs import research, review
from .distributed_protocol import (trust_at, catalog_at, seed_metadata, baseline_at, check_proposal,
    read_reviews, check_decision, verify_final)
from .distributed_transport import (fetch_main, fetch_pull, draft_snapshot, ensure_origin, publish_draft,
    comments, submit_decision, proposal_snapshot)
from .github_coordination import GitCoordinator, GitModelBudget
from .pr_export import blob, git
from .records import encode, instant, qid as valid_qid
from .research_github import GitHub
from .tasks import cutoff


def now(): return datetime.now(timezone.utc).isoformat()


_RECORD_PATH = re.compile(r'data/universities/[0-9a-f]{2,3}/(Q[1-9][0-9]*)\.json\Z')


def recency_index(repo, base, path):
    """Derive approved main timestamps, streaming a cold snapshot and diffing later commits."""
    path=private_path(path); path.parent.mkdir(parents=True,exist_ok=True)
    cached=None
    if path.exists():
        try:
            cached=load_json(path.read_bytes())
            if (not isinstance(cached,dict) or cached.get('version')!=1 or
                not re.fullmatch(r'[0-9a-f]{40}',cached.get('base','')) or not isinstance(cached.get('updated'),dict)):
                cached=None
            else:
                for entity,stamp in cached['updated'].items(): valid_qid(entity); instant(stamp)
        except (ValueError,TypeError,KeyError): cached=None
    if cached and cached['base']==base: return cached['updated']
    if cached:
        try:
            names=git(repo,'diff','--no-renames','--name-only','-z',cached['base'],base,'--','data/universities').decode().split('\0')
        except Exception:
            cached=None
    if cached:
        updated=dict(cached['updated'])
        changed={m.group(1) for name in names if (m:=_RECORD_PATH.fullmatch(name))}
        for entity in changed:
            record,_=baseline_at(repo,base,entity)
            if record and record.get('update_datetime'):
                instant(record['update_datetime']); updated[entity]=record['update_datetime']
            else: updated.pop(entity,None)
    else:
        updated={}; seen=set()
        env={**os.environ,'GIT_TERMINAL_PROMPT':'0'}
        process=subprocess.Popen(['git','-C',str(repo),'archive',base,'data/universities'],stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,env=env,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            with tarfile.open(fileobj=process.stdout,mode='r|*') as archive:
                for item in archive:
                    match=_RECORD_PATH.fullmatch(item.name)
                    if not match: continue
                    if not item.isfile() or item.size>2*1024*1024: raise ValueError('Invalid university blob in main archive')
                    entity=match.group(1)
                    if entity in seen: raise ValueError('Duplicate university QID in main archive')
                    seen.add(entity); stream=archive.extractfile(item)
                    if stream is None: raise ValueError('Unreadable university blob')
                    record=load_json(stream.read())
                    if record.get('qid')!=entity: raise ValueError('University path/QID mismatch')
                    if record.get('update_datetime'):
                        instant(record['update_datetime']); updated[entity]=record['update_datetime']
            if process.wait()!=0: raise RuntimeError('Cannot stream university data from main')
        except BaseException:
            if process.poll() is None: process.kill()
            process.wait(); raise
        finally:
            if process.stdout: process.stdout.close()
    temporary=path.with_name(path.name+'-'+uuid.uuid4().hex+'.part')
    temporary.write_bytes(encode({'version':1,'base':base,'updated':updated})); temporary.replace(path)
    return updated


class RoleAgent:
    def __init__(self, repo, role, key, client=None):
        if role not in ('research','review'): raise ValueError('Role must be research or review')
        self.repo=Path(repo).resolve(); self.role=role; self.key=private_path(key)
        base=fetch_main(self.repo); trust=trust_at(self.repo,base)
        ensure_origin(self.repo,trust['repository'])
        self.client=client or GitHub(trust['repository'])
        if self.client.repository != trust['repository']: raise ValueError('GitHub repository mismatch')
        probe=sign({},self.key,trust,role=role); self.owner=probe['key_id']
        if trust['keys'][self.owner].get('roles') != [role]: raise ValueError('A role-specific signing key is required')
        self.root=private_path(self.repo/'.private'/'agents'/role/self.owner); self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'state.json'; self.coord=GitCoordinator(self.repo); self._checkpoint_local=threading.local()
        if not self.path.exists(): self._save({'version':1,'tasks':{}})

    def _snapshot_local(self):
        if not hasattr(self, '_checkpoint_local'): self._checkpoint_local=threading.local()
        return self._checkpoint_local

    def _load(self):
        value=load_json(self.path.read_bytes()) if self.path.exists() else {'version':1}
        if value.get('version')!=1 or not isinstance(value.get('tasks',{}),dict): raise ValueError('Invalid role checkpoint')
        # Legacy map is read-only input during migration; individual QID files override it.
        tasks=deepcopy(value.get('tasks',{})); directory=self.root/'tasks'
        if directory.exists():
            for path in directory.glob('Q*.json'):
                entity=valid_qid(path.stem); tasks[entity]=load_json(path.read_bytes())
        local=self._snapshot_local(); local.snapshot=deepcopy(tasks)
        return {'version':1,'tasks':tasks}

    def _save(self,value):
        if value.get('version')!=1 or not isinstance(value.get('tasks'),dict): raise ValueError('Invalid role checkpoint')
        local=self._snapshot_local(); previous=getattr(local,'snapshot',{})
        if set(previous)-set(value['tasks']): raise ValueError('Checkpoint task deletion is unsupported')
        directory=self.root/'tasks'; directory.mkdir(parents=True,exist_ok=True)
        for entity,item in value['tasks'].items():
            valid_qid(entity)
            if entity in previous and previous[entity]==item: continue
            target=directory/(entity+'.json'); temporary=directory/(entity+'-'+uuid.uuid4().hex+'.part')
            temporary.write_bytes(encode(item)); temporary.replace(target)
        if not self.path.exists():
            temporary=self.path.with_name('state-'+uuid.uuid4().hex+'.part')
            temporary.write_bytes(encode({'version':1})); temporary.replace(self.path)
        local.snapshot=deepcopy(value['tasks'])

    def _context(self):
        base=fetch_main(self.repo); trust=trust_at(self.repo,base); ensure_origin(self.repo,trust['repository'])
        catalog,digest=catalog_at(self.repo,base,trust)
        return base,trust,catalog,digest

    def _require(self,role):
        if self.role != role: raise ValueError('This operation requires the '+role+' role')

    def next_tasks(self,limit=1):
        self._require('research')
        if type(limit) is not int or not 1<=limit<=3: raise ValueError('Task limit must be 1 to 3')
        base,trust,catalog,digest=self._context(); remote=self.coord.list_tasks(); current=now(); threshold=cutoff(current)
        state=self._load(); active=[v for v in remote.values() if v.get('owner')==self.owner and v.get('phase') in ('claimed','draft') and v.get('token') and v.get('expires_at') and instant(v['expires_at'])>instant(current)]
        slots=max(0,3-len(active)); result=[]
        for entity,item in state['tasks'].items():
            task=remote.get(entity,{})
            if item.get('prepared') and task.get('owner')==self.owner and task.get('phase')=='draft' and not (task.get('expires_at') and instant(task['expires_at'])>instant(current)) and slots:
                lease=self.coord.claim_task(entity,self.owner,now(),allow_resume=True)
                self.coord.set_task(lease,'draft',now(),revision=item.get('revision',0))
                item['lease']=lease; self._save(state)
                return {'status':'prepared_waiting_publish','tasks':[{'qid':entity}]}

        if not slots: return {'status':'capacity','tasks':[]}
        runtime,_=self.coord.read('coord/runtime')
        if len(runtime.get('pr_permits',[]))>=3: return {'status':'waiting_for_pr_capacity','tasks':[]}
        updated=recency_index(self.repo,base,self.root/'recency-index.json')
        rows=sorted(catalog.items(),key=lambda row:(row[1].get('queue_kind')!='primary',int(row[0][1:])))
        for entity,row in rows:
            task=remote.get(entity,{})
            if task.get('phase')=='merged' and task.get('retry_after') and instant(task['retry_after'])>instant(current): continue
            if task.get('phase') in ('draft','review_pending','revision_requested','approved','published','unresolved'): continue
            if task.get('token') and task.get('expires_at') and instant(task['expires_at'])>instant(current): continue
            if entity in updated and instant(updated[entity])>threshold: continue
            try: lease=self.coord.claim_task(entity,self.owner,now(),allow_resume=task.get('phase')=='merged')
            except ValueError: continue
            self.coord.set_task(lease,'claimed',now(),revision=0)
            state['tasks'][entity]={'lease':lease,'revision':0,'base':base}; self._save(state)
            result.append({'qid':entity,'queue_kind':row.get('queue_kind','discovery'),'base':base})
            if len(result)>=min(limit,slots): break
        return {'status':'claimed' if result else 'no_eligible_task','tasks':result}

    def public_proposals(self,pr_number):
        if type(pr_number) is not int or pr_number<1: raise ValueError('Invalid PR number')
        pull=self.client.pull(pr_number); base,trust,_,_=self._context()
        if pull.get('state')!='open' or pull.get('base',{}).get('ref')!='main' or (pull.get('head',{}).get('repo') or {}).get('full_name')!=trust['repository']:
            raise ValueError('Open PR in this repository against main required')
        fetch_pull(self.repo,pr_number,pull['head']['sha'])
        stage,manifest,proposals,_=proposal_snapshot(self.repo,pull,trust)
        return pull,manifest['batch_id'],proposals,base

    def _lease(self,entity,pr_number=None):
        state=self._load(); item=state['tasks'].get(entity)
        remote=self.coord.list_tasks().get(entity,{})
        if item and item.get('lease') and remote.get('token')==item['lease'].get('token') and remote.get('owner')==self.owner and remote.get('expires_at') and instant(remote['expires_at'])>instant(now()):
            self.coord.heartbeat_task(item['lease'],now()); return state,item,remote
        if item and item.get('prepared') and remote.get('owner')==self.owner and remote.get('phase')=='draft':
            lease=self.coord.claim_task(entity,self.owner,now(),allow_resume=True)
            item['lease']=lease; self.coord.set_task(lease,'draft',now(),revision=item.get('revision',0)); self._save(state)
            return state,item,remote
        if pr_number is None or remote.get('pr_number')!=pr_number or remote.get('phase') not in ('review_pending','revision_requested','draft'):
            raise ValueError('Claim this QID first or provide its existing revision PR')
        lease=self.coord.claim_task(entity,self.owner,now(),allow_resume=True)
        item={'lease':lease,'revision':remote.get('revision',0),'pr_number':pr_number}; state['tasks'][entity]=item; self._save(state)
        return state,item,remote

    def research_one(self,qid,pr_number=None):
        self._require('research'); entity=valid_qid(qid)
        base,trust,catalog,digest=self._context()
        if entity not in catalog: raise ValueError('QID is outside accepted seed catalog')
        state,item,remote=self._lease(entity,pr_number); lease=item['lease']; feedback=None
        revision=remote.get('revision',item.get('revision',0))
        if pr_number is not None:
            pull,batch,proposals,_=self.public_proposals(pr_number)
            if entity not in proposals: raise ValueError('QID is not in the supplied PR')
            open_requests=requests_from_comments(comments(self.client,pr_number),trust,pr_number,entity)
            previous=verify(proposals[entity],trust,role='research')
            current_baseline,_=baseline_at(self.repo,base,entity)
            current_hash=sha(encode(current_baseline)) if current_baseline is not None else 'absent'
            rebaseline=previous.get('baseline_sha256')!=current_hash
            if not open_requests and not rebaseline: return {'status':'waiting_for_review_objection','qid':entity,'pr_number':pr_number}
            if revision>=2:
                self.coord.set_task(lease,'unresolved',now(),reason_code='revision_limit')
                return {'status':'unresolved','qid':entity,'reason':'revision_limit'}
            revision+=1; self.coord.set_task(lease,'claimed',now(),revision=revision,pr_number=pr_number,batch_id=batch)
            item['revision']=revision; item['pr_number']=pr_number; self._save(state)
            feedback={'open_requests':open_requests}
            if rebaseline: feedback['reason']='Approved main baseline changed; re-evaluate this school using the current baseline.'
        else:
            self.coord.set_task(lease,'claimed',now(),revision=revision)
        baseline,_=baseline_at(self.repo,base,entity); seed=seed_metadata(catalog[entity],digest)
        stop=threading.Event(); cancel=threading.Event(); lost=[]
        def heartbeat():
            while not stop.wait(60):
                try: self.coord.heartbeat_task(lease,now())
                except Exception as error: lost.append(type(error).__name__); cancel.set(); return
        thread=threading.Thread(target=heartbeat,daemon=True); thread.start()
        job=self.root/'jobs'/entity/uuid.uuid4().hex
        try:
            budget=GitModelBudget(self.coord,'research',self.owner,'research-'+uuid.uuid4().hex,cancel_event=cancel)
            proposal,private_job=research(entity,seed,baseline,job,self.root/'source-cache',self.repo,budget,feedback=feedback)
            if cancel.is_set() or lost: raise RuntimeError('Task lease lost; result cannot be published')
            self.coord.heartbeat_task(lease,now())
            savepath=self.root/'prepared'/(entity+'-'+uuid.uuid4().hex+'.json'); savepath.parent.mkdir(parents=True,exist_ok=True); savepath.write_bytes(encode(proposal))
            state=self._load(); state['tasks'][entity].update({'prepared':str(savepath),'base':base,'revision':revision})
            if pr_number is not None: state['tasks'][entity]['pr_number']=pr_number
            self._save(state); self.coord.set_task(lease,'draft',now(),revision=revision,base_sha=base)
            return {'status':'prepared','qid':entity,'revision':revision,'private_job':private_job}
        finally:
            stop.set(); thread.join(timeout=2)

    def publish_ready(self,batchsize=5,pr_number=None):
        self._require('research')
        if type(batchsize) is not int or not 1<=batchsize<=5: raise ValueError('Batch size must be 1 to 5')
        state=self._load(); selected=[]
        for entity,item in sorted(state['tasks'].items(),key=lambda row:int(row[0][1:])):
            if item.get('prepared') and item.get('pr_number')==pr_number:
                state,item,_=self._lease(entity,pr_number); selected.append((entity,item))
            if len(selected)>=batchsize: break
        if not selected: return {'status':'no_prepared_proposals'}
        pull=None; permit=None
        if pr_number is not None:
            pull,batch,existing,_=self.public_proposals(pr_number)
            selected_ids={q for q,_ in selected}
            if not selected_ids <= set(existing): raise ValueError('Revision cannot introduce other QIDs')
            proposals=[doc for q,doc in existing.items() if q not in selected_ids]
        else:
            batch='batch-'+uuid.uuid4().hex[:20]; proposals=[]
            permit=self.coord.acquire_pr_permit(self.owner,batch,now())
            if permit is None: return {'status':'waiting_for_pr_capacity'}
        for entity,item in selected:
            path=private_path(item['prepared'])
            if not path.is_relative_to(self.root): raise ValueError('Prepared proposal escapes role checkpoint')
            proposals.append(load_json(path.read_bytes()))
        result=publish_draft(self.repo,proposals,self.key,self.client,self.root/'worktrees',batch=batch,pull=pull)
        if permit is not None: self.coord.bind_pr_permit(permit,result['number'],now())
        current,batch,envelopes,base=self.public_proposals(result['number'])
        for entity,item in selected:
            payload=verify(envelopes[entity],trust_at(self.repo,base),role='research')
            self.coord.set_task(item['lease'],'review_pending',now(),pr_number=result['number'],head_sha=current['head']['sha'],
                base_sha=base,batch_id=batch,proposal_sha256=sha(encode(payload)),revision=item.get('revision',0))
            state['tasks'][entity].pop('prepared',None); state['tasks'][entity]['pr_number']=result['number']
        self._save(state)
        return {'status':'review_pending','pr_number':result['number'],'head_sha':current['head']['sha'],'qids':[q for q,_ in selected]}

    def review_pr(self,pr_number,cancel_event=None,expected_head=None,lease_guard=None):
        self._require('review')
        def require_review_lease():
            if cancel_event is not None and cancel_event.is_set(): raise RuntimeError('Review lease lost')
            if lease_guard is not None: lease_guard()
            if cancel_event is not None and cancel_event.is_set(): raise RuntimeError('Review lease lost')
        require_review_lease(); pull,batch,proposals,base=self.public_proposals(pr_number)
        if expected_head is not None and pull['head']['sha']!=expected_head: raise ValueError('Review queue head is stale')
        trust=trust_at(self.repo,base); notes=comments(self.client,pr_number)
        stage,manifest,_,decisions=proposal_snapshot(self.repo,pull,trust)
        if stage=='final':
            if manifest['base_commit']!=base:
                return {'status':'rebind_required','pr_number':pr_number,'qids':sorted(proposals)}
            assert_no_objections(notes,trust,pr_number,list(proposals),decisions=decisions)
            return {'status':'mechanical_valid','pr_number':pr_number,'qids':sorted(proposals)}
        catalog,digest=catalog_at(self.repo,base,trust); outcomes=[]
        for entity,document in proposals.items():
            require_review_lease()
            proposal=verify(document,trust,role='research'); baseline,_=baseline_at(self.repo,base,entity)
            check_proposal(proposal,baseline,catalog,digest,trust)
            if document['key_id']==self.owner: raise ValueError('Independent Review key required')
            outstanding=requests_from_comments(notes,trust,pr_number,entity)
            carried={r['request_id'] for r in proposal['open_requests']}
            if any(r['request_id'] not in carried for r in outstanding):
                outcomes.append({'qid':entity,'status':'revision_requested'}); continue
            previous=read_reviews(notes,trust,pr_number,entity,sha(encode(proposal)))
            if previous:
                verdict,_=check_decision(previous[-1][0],document,baseline,trust,pr_number)
                outcomes.append({'qid':entity,'status':'already_reviewed','decision':verdict['decision']}); continue
            job=self.root/'jobs'/entity/uuid.uuid4().hex
            budget=GitModelBudget(self.coord,'review',self.owner,'review-'+uuid.uuid4().hex,cancel_event=cancel_event)
            verdict,_=review(proposal,baseline,job,self.repo,budget)
            require_review_lease()
            fresh_base=fetch_main(self.repo); current=self.client.pull(pr_number)
            if fresh_base!=base or current.get('head',{}).get('sha')!=pull['head']['sha'] or current.get('base',{}).get('ref')!='main':
                outcomes.append({'qid':entity,'status':'stale_review'}); continue
            latest=requests_from_comments(comments(self.client,pr_number),trust,pr_number,entity)
            if any(r['request_id'] not in carried for r in latest):
                outcomes.append({'qid':entity,'status':'revision_requested'}); continue
            require_review_lease()
            posted=submit_decision(document,verdict,self.key,self.client,current,trust)
            outcomes.append({'qid':entity,'status':verdict['decision'],'comment_id':posted['comment_id']})
        return {'status':'review_processed','pr_number':pr_number,'results':outcomes}
