"""One manager, local atomic checkpoints, and main-derived recovery. No branch leases."""
import calendar
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import uuid

from .attestations import load_json, private_path, sha
from .cache_lock import request_lock
from .git_data import blob, canonical_json, commit, git, record_relative
from .records import encode, instant, qid as valid_qid
from .research_contract import _open_requests, _safe_reason
from .workflow_contract import public_bounds

BACKLOG = 'data/workflow/tasks.json'
BACKLOG_TYPE = 'university-manager-backlog-v1'
PHASES = {'research_pending','researching','review_pending','reviewing','revision_requested',
          'ready_to_publish','publishing','completed','retry_wait','unresolved'}
ACTIVE = {'researching','reviewing'}


def now():
    return datetime.now(timezone.utc).isoformat()


def cutoff(at):
    stamp=instant(at); year,month=divmod(stamp.year*12+stamp.month-7,12); month+=1
    return stamp.replace(year=year,month=month,day=min(stamp.day,calendar.monthrange(year,month)[1]))


def validate_backlog(value):
    if not isinstance(value,dict) or set(value)!={'type','tasks'} or value['type']!=BACKLOG_TYPE or not isinstance(value['tasks'],dict):
        raise ValueError('Invalid single-manager backlog')
    for entity,row in value['tasks'].items():
        valid_qid(entity)
        if (not isinstance(row,dict) or not {'phase','revision','open_requests','reason'}<=set(row)
                or set(row)-{'phase','revision','open_requests','reason','history'}):
            raise ValueError('Invalid public task fields')
        if row.get('phase') not in ('research_pending','revision_requested','unresolved') or type(row.get('revision')) is not int or not 0<=row['revision']<=2:
            raise ValueError('Public tasks must be resumable without private evidence')
        _open_requests(row)
        _safe_reason(row.get('reason',''))
        history=row.get('history',{})
        if not isinstance(history,dict) or set(history)-{'proposal_path','proposal_sha256','commit','issue_url'}:
            raise ValueError('Invalid historical task provenance')
        for key in ('proposal_sha256','commit'):
            if key in history and not re.fullmatch('[0-9a-f]{'+('64' if key=='proposal_sha256' else '40')+'}',history[key]):
                raise ValueError('Invalid historical digest')
        if 'proposal_path' in history and not re.fullmatch(r'data/history/proposals/[a-z0-9-]+/Q[1-9][0-9]*\.json',history['proposal_path']):
            raise ValueError('Invalid historical proposal path')
        if 'issue_url' in history and not re.fullmatch(r'https://github.com/ider-zh/university-seed-curation/pull/[1-9][0-9]*',history['issue_url']):
            raise ValueError('Invalid historical discussion URL')
    public_bounds(value)
    return value


def backlog_at(repo,base):
    raw=blob(repo,base,BACKLOG,optional=True)
    return validate_backlog(canonical_json(raw)) if raw else {'type':BACKLOG_TYPE,'tasks':{}}


def after_publication(repo,base,entities):
    value=deepcopy(backlog_at(repo,base))
    for entity,task in _read(repo)['tasks'].items():
        if task.get('phase')=='completed': continue
        previous=value['tasks'].get(entity,{})
        row={'phase':task['phase'] if task['phase'] in ('unresolved','revision_requested') else 'research_pending',
             'revision':task.get('revision',0),'open_requests':task.get('open_requests',[]),
             'reason':task.get('reason','resume_after_private_workspace_loss')}
        if previous.get('history'): row['history']=previous['history']
        value['tasks'][entity]=row
    for entity in entities: value['tasks'].pop(entity,None)
    validate_checkpoint(backlog_at(repo,base),value,entities)
    return encode(value)


def validate_checkpoint(previous,current,completed=()):
    validate_backlog(current)
    for entity,row in previous['tasks'].items():
        if entity in completed:
            if entity in current['tasks']: raise ValueError('Approved task must leave the pending backlog')
            continue
        replacement=current['tasks'].get(entity)
        if replacement is None: raise ValueError('Pending task cannot disappear from checkpoint')
        check_requests(row['open_requests'],replacement['open_requests'])
        if replacement['revision']<row['revision'] or replacement.get('history')!=row.get('history'):
            raise ValueError('Checkpoint cannot reset revision or historical provenance')
    return current


def state_path(repo):
    return private_path(Path(repo)/'.private/native/manager-state.json')


def _read(repo):
    path=state_path(repo)
    if not path.exists(): return {'type':'university-manager-state-v1','tasks':{}}
    value=load_json(path.read_bytes())
    if value.get('type')!='university-manager-state-v1' or not isinstance(value.get('tasks'),dict):
        raise ValueError('Invalid private manager checkpoint')
    return value


def update(repo,mutator):
    path=state_path(repo); path.parent.mkdir(parents=True,exist_ok=True)
    with request_lock(path.with_suffix('.lock')):
        state=_read(repo); result=mutator(state)
        temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.part')
        try:
            temporary.write_bytes(encode(state)); temporary.replace(path)
        finally:
            if temporary.exists(): temporary.unlink()
        return result


def begin(repo,base,entity,phase,job,at=None):
    valid_qid(entity); job=private_path(job); stamp=at or now()
    inherited=backlog_at(repo,base)['tasks'].get(entity,{})
    if phase not in ACTIVE: raise ValueError('Only Research/Review can start a model job')
    def mutate(state):
        task=state['tasks'].get(entity,deepcopy(inherited))
        # An OS-backed local mutex protects the single manager across its short CLI calls.
        live=[r for r in state['tasks'].values() if r.get('phase') in ACTIVE and instant(r['expires_at'])>instant(stamp)]
        if task.get('phase') in ACTIVE and instant(task['expires_at'])>instant(stamp):
            raise ValueError('QID already has an active subagent')
        if len(live)>=3 or (phase=='reviewing' and any(r['phase']=='reviewing' for r in live)):
            raise ValueError('Native subagent capacity exhausted')
        if phase=='researching' and len(live)>=2 and any(r.get('phase')=='review_pending' for r in state['tasks'].values()):
            raise ValueError('Capacity is reserved for waiting Review')
        revision=0 if task.get('phase')=='completed' else task.get('revision',0)
        if phase=='researching' and task.get('phase')=='revision_requested':
            if revision>=2: raise ValueError('Research revision limit reached')
            revision+=1
        if phase=='researching':
            for key in ('review_job','review_attempt','proposal','bundle','published_commit','completed_at'):
                task.pop(key,None)
        task.update(phase=phase,revision=revision,expires_at=(instant(stamp)+timedelta(minutes=30)).isoformat())
        task[('research_job' if phase=='researching' else 'review_job')]=str(job)
        task.pop('retry_after',None); task.pop('error',None)
        state['tasks'][entity]=task
        return deepcopy(task)
    return update(repo,mutate)


def set_phase(repo,entity,phase,**metadata):
    if phase not in PHASES: raise ValueError('Invalid manager phase')
    def mutate(state):
        task=state['tasks'].setdefault(entity,{'revision':0})
        task.update(phase=phase,**metadata)
        if phase not in ACTIVE: task.pop('expires_at',None)
        return deepcopy(task)
    return update(repo,mutate)


def require_job(repo,entity,kind,job):
    task=_read(repo)['tasks'].get(entity,{})
    expected='researching' if kind=='research' else 'reviewing'
    if (task.get(kind+'_job')!=str(private_path(job)) or task.get('phase')!=expected
            or instant(task['expires_at'])<=instant(now())):
        raise ValueError('Job is stale or is not owned by this manager checkpoint')
    return task


def required_requests(repo,base,entity):
    rows={r['request_id']:r for r in backlog_at(repo,base)['tasks'].get(entity,{}).get('open_requests',[])}
    for row in _read(repo)['tasks'].get(entity,{}).get('open_requests',[]):
        if row['request_id'] in rows and rows[row['request_id']]!=row:
            raise ValueError('Saved Review request conflicts with main provenance')
        rows[row['request_id']]=row
    return list(rows.values())


def check_requests(required,provided):
    _open_requests({'open_requests':provided})
    rows={r['request_id']:r for r in provided}
    if any(rows.get(row['request_id'])!=row for row in required):
        raise ValueError('Saved Review requests cannot be dropped or rewritten')


def publication_ready(repo,entity,proposal,review_job,review_attempt):
    task=_read(repo)['tasks'].get(entity,{})
    if (task.get('phase')!='ready_to_publish' or task.get('proposal')!=str(private_path(proposal))
            or task.get('review_job')!=str(private_path(review_job))
            or task.get('review_attempt')!=str(private_path(review_attempt))):
        raise ValueError('Publication must use the current approved manager proposal and Review attempt')


def failure(repo,entity,phase,error):
    if isinstance(error,(ValueError,FileExistsError)):
        set_phase(repo,entity,'research_pending' if phase=='researching' else 'review_pending')
        return
    delay=getattr(error,'retry_after',300)
    set_phase(repo,entity,'retry_wait',resume_phase='research_pending' if phase=='researching' else 'review_pending',
              retry_after=(instant(now())+timedelta(seconds=max(1,delay))).isoformat(),error=type(error).__name__)


def review_completed(repo,entity,job,compiled):
    task=require_job(repo,entity,'review',job); verdict=compiled['public_verdict']
    if verdict['decision']=='approve':
        return set_phase(repo,entity,'ready_to_publish',review_attempt=compiled['private_attempt'])
    requests={r['request_id']:r for r in task.get('open_requests',[])}
    for row in verdict['requests']:
        identifier=str(uuid.uuid5(uuid.NAMESPACE_URL,verdict['proposal_sha256']+encode(row).decode()))
        requests[identifier]={**row,'request_id':identifier,'reviewed_proposal_sha256':verdict['proposal_sha256']}
    phase='unresolved' if verdict['decision']=='unresolved' or task.get('revision',0)>=2 else 'revision_requested'
    return set_phase(repo,entity,phase,open_requests=list(requests.values()),review_attempt=compiled['private_attempt'])


def publication_index(repo,base):
    """Only exact current canonical bytes plus a main-resident receipt count as publication."""
    result={}
    names=git(repo,'ls-tree','-r','--name-only',base,'--','data/batches').decode().splitlines()
    for name in names:
        manifest=load_json(blob(repo,base,name))
        if manifest.get('type')!='university-unified-batch-v1': continue
        for row in manifest['records']:
            entity=row['qid']; raw=blob(repo,base,record_relative(entity),optional=True)
            receipt_raw=blob(repo,base,row['receipt_path'],optional=True)
            if raw is None or receipt_raw is None or sha(raw)!=row['record_sha256'] or sha(receipt_raw)!=row['receipt_sha256']: continue
            receipt=load_json(receipt_raw); verdict=receipt.get('review',{})
            if (receipt.get('type')!='university-unified-receipt-v1' or verdict.get('decision')!='approve'
                    or verdict.get('qid')!=entity or verdict.get('record_sha256')!=sha(raw)
                    or verdict.get('requests') or receipt.get('research',{}).get('research',{}).get('session')==verdict.get('review_session')):
                raise ValueError('Invalid main publication receipt')
            result[entity]={'reviewed_at':verdict['reviewed_at'],'full_refresh':verdict['full_refresh'],
                            'batch_path':name,'record_sha256':sha(raw)}
    return result


def next_tasks(repo,base,catalog,studied,limit=5,at=None):
    if not 1<=limit<=100: raise ValueError('Limit must be 1 to 100')
    stamp=at or now(); tasks=deepcopy(backlog_at(repo,base)['tasks']); tasks.update(_read(repo)['tasks'])
    published=publication_index(repo,base); rows=[]; threshold=cutoff(stamp)
    for entity,seed in catalog.items():
        task=tasks.get(entity,{}); phase=task.get('phase','research_pending'); reason='never_researched'
        if phase=='unresolved': continue
        if phase=='retry_wait':
            if instant(task['retry_after'])>instant(stamp): continue
            phase=task.get('resume_phase','research_pending'); reason='retry_due'
        if phase in ACTIVE:
            if instant(task['expires_at'])>instant(stamp): continue
            phase='review_pending' if phase=='reviewing' else 'research_pending'; reason='interrupted_job'
        if phase in ('completed','research_pending') and entity in published:
            item=published[entity]
            if item['full_refresh'] and studied.get(entity) and instant(studied[entity])>threshold: continue
            # Partial accepted records have a separate retry interval; they are not full-refresh fresh.
            if not item['full_refresh'] and instant(item['reviewed_at'])+timedelta(days=7)>instant(stamp): continue
            reason='refresh_due' if item['full_refresh'] else 'partial_survey_retry'
        elif phase=='completed':
            phase='research_pending'; reason='published_bytes_not_on_main'
        elif not task and studied.get(entity) and instant(studied[entity])>threshold:
            continue
        elif task and reason=='never_researched': reason=task.get('reason','resume_saved_task')
        action={'publishing':'verify_publication','ready_to_publish':'publish','review_pending':'review',
                'revision_requested':'revise'}.get(phase,'research')
        if action in ('review','publish','verify_publication'):
            required={'review':['proposal','research_job'],'publish':['proposal','review_job','review_attempt'],
                      'verify_publication':['bundle']}[action]
            if any(not task.get(key) or not Path(task[key]).exists() for key in required):
                action='research'; reason='private_snapshot_unavailable'
        priority={'verify_publication':0,'publish':1,'review':2,'revise':3,'research':4}[action]
        rows.append((priority,not bool(task),seed['queue_kind']!='primary',int(entity[1:]),
                     {'qid':entity,'action':action,'reason':reason,'queue_kind':seed['queue_kind'],
                      'revision':task.get('revision',0),'open_requests':task.get('open_requests',[])}))
    return [row[-1] for row in sorted(rows,key=lambda r:r[:4])[:limit]]


def confirm_publication(repo,bundle,published_ref):
    bundle=private_path(bundle); plan=load_json((bundle/'operations.json').read_bytes())
    actual=commit(repo,published_ref); main=commit(repo,'origin/main')
    git(repo,'merge-base','--is-ancestor',actual,main)
    parents=git(repo,'rev-list','--parents','-n','1',actual).decode().split()
    if parents!=[actual,plan['base_commit']]: raise ValueError('Published commit is not the planned main successor')
    for path,digest in plan['files'].items():
        raw=blob(repo,actual,path)
        if sha(raw)!=digest: raise ValueError('Remote publication bytes differ from bundle')
    for entity in plan.get('qids',[]):
        set_phase(repo,entity,'completed',published_commit=actual,completed_at=now(),bundle=str(bundle),open_requests=[])
    return {'status':'publication_verified','commit':actual,'qids':plan.get('qids',[])}
