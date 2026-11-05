"""Prepare and compile one native Research subagent result in this workspace.

The host supplies the subagent session and structured result. This module does
not launch a model, authenticate to GitHub, sign data, or attest provider identity.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re

import jsonschema

from .attestations import load_json, private_path, sha
from .distributed_jobs import (RESEARCH_RULES, coordinate_aliases, coordinate_delta,
    guard_root_coordinates, source_languages, _clean_failures, _open_requests, _public_evidence, _root)
from .distributed_protocol import trust_at, catalog_at, seed_metadata, baseline_at
from .domain_refresh import compile_delta, materialize
from .pilot_protocol import RESEARCH_INSTRUCTIONS, RESEARCH_SCHEMA
from .pilot_sources import prepare_case
from .pr_export import blob, commit, git
from .records import encode, instant, qid as valid_qid
from .sources import Cache


def _base(repo, ref):
    base=commit(repo,ref); trust=trust_at(repo,base)
    raw=blob(repo,base,'schemas/university.v0.2.2.schema.json')
    if sha(encode(load_json(raw)))!=trust.get('schemas',{}).get('0.2.2'):
        raise ValueError('Approved university schema does not match repository trust')
    catalog,catalog_hash=catalog_at(repo,base,trust)
    return base,trust,catalog,catalog_hash


def _origin(repo, repository):
    value=git(repo,'remote','get-url','origin').decode().strip().removesuffix('.git')
    if value not in ('https://github.com/'+repository,'git@github.com:'+repository):
        raise ValueError('Local Git origin does not match the signed catalog repository')
    return value


def doctor(repo):
    repo=Path(repo).resolve(); base,trust,catalog,digest=_base(repo,'origin/main')
    _origin(repo,trust['repository'])
    return {'status':'local_ready','base_commit':base,'repository':trust['repository'],
        'catalog_count':len(catalog),'catalog_sha256':digest,'schema_version':'0.2.2',
        'github_plugin':'not_verified_locally','native_subagents':'not_verified_locally',
        'network_authentication':'not_checked','signing_key':'not_required'}


def _prompt(value, policy):
    return (RESEARCH_RULES+'\n'+RESEARCH_INSTRUCTIONS+'\nREVIEW POLICY (takes precedence over stricter pilot wording):\n'
        +policy+'\nReturn only one JSON object matching the supplied schema. '
        'The output is an unreviewed proposal; do not assert independent Review.\nINPUT:\n'+encode(value).decode())


def _write(path, data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)


def prepare(repo, qid, job, base_ref='origin/main', feedback=None):
    repo=Path(repo).resolve(); entity=valid_qid(qid); job=private_path(job)
    if job.exists(): raise FileExistsError('Use a new private native Research attempt')
    if feedback is not None and len(encode(feedback).decode('utf-8'))>8000: raise ValueError('Feedback exceeds 8000 characters')
    requests=_open_requests(feedback)
    base,trust,catalog,catalog_hash=_base(repo,base_ref); _origin(repo,trust['repository'])
    if entity not in catalog: raise ValueError('QID is outside the signed seed catalog')
    seed=seed_metadata(catalog[entity],catalog_hash); baseline,baseline_hash=baseline_at(repo,base,entity)
    if baseline is not None and baseline.get('qid')!=entity: raise ValueError('Baseline QID mismatch')
    policy=blob(repo,base,'docs/review-policy-v2.md').decode('utf-8').replace('\r\n','\n')
    if sha(policy.encode())!=trust['review_policy']['sha256']: raise ValueError('Review policy does not match repository trust')
    job.mkdir(parents=True)
    source_cache=private_path(repo/'.private'/'native'/'research'/'source-cache')
    cache=Cache(source_cache,maxlag=30); item,_=cache.entity(entity)
    if item.get('id')!=entity: raise ValueError('Root identity redirected')
    case={'qid':entity,'name':item.get('labels',{}).get('en',{}).get('value',entity),
          'languages':source_languages(item),'focus':['identity','general_profile']}
    prepare_case(case,job,source_cache=source_cache)
    packet_path=job/'cases'/entity/'research-packet.json'; packet=coordinate_aliases(load_json(packet_path.read_bytes()))
    _write(packet_path,encode(packet)); _,source=_root(packet)
    root,_=cache.entity_revision(entity,source['revision_id'])
    if root.get('id')!=entity or root.get('lastrevid')!=source['revision_id']: raise ValueError('Captured root identity or revision mismatch')
    if baseline and baseline.get('modified_datetime') and instant(baseline['modified_datetime'])>instant(packet['captured_at']):
        raise ValueError('Source capture predates baseline')
    value={'qid':entity,'seed':seed,'baseline':baseline,'packet':packet}
    if feedback is not None: value['previous_attempt_feedback']=deepcopy(feedback)
    prompt=_prompt(value,policy).encode('utf-8'); shape=encode(RESEARCH_SCHEMA); root_bytes=encode(root)
    _write(job/'prompt.txt',prompt); _write(job/'output.schema.json',shape); _write(job/'root-entity.json',root_bytes)
    _write(job/'research-input.json',encode(value))
    manifest={'type':'native-research-job-v1','qid':entity,'base_commit':base,'catalog_sha256':catalog_hash,
        'schema_sha256':trust['schemas']['0.2.2'],'review_policy_sha256':trust['review_policy']['sha256'],
        'baseline_sha256':baseline_hash,'seed':seed,'open_requests':requests,'prepared_at':datetime.now(timezone.utc).isoformat(),
        'prompt_sha256':sha(prompt),'output_schema_sha256':sha(shape),'packet_sha256':sha(encode(packet)),
        'root_entity_sha256':sha(root_bytes),'research_input_sha256':sha(encode(value)),'native_code_sha256':sha(Path(__file__).read_bytes())}
    _write(job/'job.json',encode(manifest))
    return {'status':'prepared','qid':entity,'job_dir':str(job),'base_commit':base,
        'prompt_path':str(job/'prompt.txt'),'schema_path':str(job/'output.schema.json'),
        'research_input_sha256':manifest['research_input_sha256']}


def compile(repo, job, result_file, session, model, effort='medium', completed_at=None):
    repo=Path(repo).resolve(); job=private_path(job); result_file=private_path(result_file)
    if not isinstance(session,str) or not session.strip() or len(session)>200 or any(ord(c)<32 for c in session): raise ValueError('Native session ID required')
    if not isinstance(model,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',model): raise ValueError('Valid native model identifier required')
    if effort not in ('low','medium','high','xhigh','max','ultra','not_reported'): raise ValueError('Invalid reported reasoning effort')
    import uuid
    attempt=job/'compile-attempts'/uuid.uuid4().hex; attempt.mkdir(parents=True,exist_ok=False)
    raw=result_file.read_bytes(); _write(attempt/'native-result.json',raw)
    manifest=load_json((job/'job.json').read_bytes())
    if manifest.get('type')!='native-research-job-v1': raise ValueError('Invalid native Research job')
    entity=valid_qid(manifest['qid']); base,trust,catalog,digest=_base(repo,manifest['base_commit'])
    if base!=manifest['base_commit'] or digest!=manifest['catalog_sha256'] or entity not in catalog: raise ValueError('Job Git base or signed catalog changed')
    if manifest['schema_sha256']!=trust['schemas']['0.2.2'] or manifest['review_policy_sha256']!=trust['review_policy']['sha256']: raise ValueError('Job schema or policy changed')
    baseline,baseline_hash=baseline_at(repo,base,entity); seed=seed_metadata(catalog[entity],digest)
    if baseline_hash!=manifest['baseline_sha256'] or seed!=manifest['seed']: raise ValueError('Job baseline or seed changed')
    files={'prompt.txt':'prompt_sha256','output.schema.json':'output_schema_sha256','root-entity.json':'root_entity_sha256',
        'research-input.json':'research_input_sha256', 'cases/'+entity+'/research-packet.json':'packet_sha256'}
    for filename,key in files.items():
        if sha((job/filename).read_bytes())!=manifest[key]: raise ValueError('Prepared Research input changed: '+filename)
    if sha(Path(__file__).read_bytes())!=manifest['native_code_sha256']: raise ValueError('Native Research compiler changed after preparation')
    if load_json((job/'output.schema.json').read_bytes())!=RESEARCH_SCHEMA: raise ValueError('Native Research schema changed')
    packet=load_json((job/'cases'/entity/'research-packet.json').read_bytes()); root=load_json((job/'root-entity.json').read_bytes())
    value=load_json((job/'research-input.json').read_bytes())
    if value.get('qid')!=entity or value.get('seed')!=seed or value.get('baseline')!=baseline or value.get('packet')!=packet:
        raise ValueError('Prepared Research packet does not match Git baseline')
    if manifest['open_requests']!=_open_requests(value.get('previous_attempt_feedback')):
        raise ValueError('Prepared Research feedback changed')
    policy=blob(repo,base,'docs/review-policy-v2.md').decode('utf-8').replace('\r\n','\n')
    if sha(policy.encode())!=manifest['review_policy_sha256'] or (job/'prompt.txt').read_bytes()!=_prompt(value,policy).encode('utf-8'):
        raise ValueError('Native Research prompt differs from prepared task')
    _,source=_root(packet)
    if root.get('id')!=entity or root.get('lastrevid')!=source['revision_id']: raise ValueError('Captured root revision mismatch')
    proposal=load_json(raw); jsonschema.Draft202012Validator(RESEARCH_SCHEMA).validate(proposal)
    guard_root_coordinates(proposal,packet)
    delta,_,_=compile_delta(proposal,packet); delta['seed']=deepcopy(seed)
    delta,_=coordinate_delta(delta,root,packet); _public_evidence(delta)
    at=completed_at or datetime.now(timezone.utc).isoformat(); instant(at)
    if instant(at)<instant(manifest['prepared_at']) or instant(at)<instant(packet['captured_at']): raise ValueError('Native result predates preparation')
    candidate=materialize(baseline,delta,seed,at,False)
    result={'type':'university-proposal-v1','review_status':'unreviewed','qid':entity,'seed':seed,
        'baseline_sha256':baseline_hash,'delta':delta,'candidate':candidate,'proposed_at':at,
        'coverage':[{'group':r['group'],'status':r['status']} for r in proposal['coverage']],
        'retrieval_failures':_clean_failures(packet['retrieval_failures']),'open_requests':manifest['open_requests'],
        'research':{'model':model,'reasoning_effort':effort,'session':session,
            'prompt_sha256':manifest['prompt_sha256'],'schema_sha256':manifest['output_schema_sha256']}}
    _write(attempt/'public-proposal.json',encode(result)); _write(attempt/'result-metadata.json',encode({'session':session,'model':model,
        'reasoning_effort':effort,'completed_at':at,'provider_trace_verified':False,'native_result_sha256':sha(raw)}))
    return {'status':'compiled','qid':entity,'job_dir':str(job),'public_proposal':result,
        'public_proposal_path':str(attempt/'public-proposal.json'),'private_attempt':str(attempt),
        'session_and_model':'caller_reported','provider_trace_verified':False}
