"""Prepare and compile an offline native Review subagent result.

Review uses Research's hash-verified source snapshot without network access.
Native session/model declarations are not treated as provider-signed proof.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re
import uuid

import jsonschema

from .attestations import load_json, private_path, sha
from .research_contract import (_verify_proposal, _fact_scope, _safe_reason,
    REVIEW_RULES, REVIEW_SCHEMA, MODEL, EFFORT)
from .workflow_contract import seed_metadata, baseline_at
from .domain_refresh import materialize
from .native_research import _base, _origin, _write
from .research_schema import GROUPS
from .git_data import blob
from .records import encode, instant, qid as valid_qid
from .web_sources import verify_packet as verify_web_packet


def _verify_native(proposal, baseline, packet, root):
    """Apply the shared factual checks without claiming a caller-reported model is authenticated."""
    metadata=proposal.get('research',{})
    if not isinstance(metadata.get('model'),str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',metadata['model']):
        raise ValueError('Invalid reported Research model')
    if metadata.get('reasoning_effort') not in ('low','medium','high','xhigh','max','ultra','not_reported'):
        raise ValueError('Invalid reported Research effort')
    adjusted=deepcopy(proposal)
    adjusted['research']['model']=MODEL; adjusted['research']['reasoning_effort']=EFFORT
    return _verify_proposal(adjusted,baseline,packet,root)


def _prompt(value, policy):
    return (REVIEW_RULES+'\nREVIEW POLICY:\n'+policy+'\nReturn only one JSON object matching the supplied schema. '
        'The source packet is a revision-bound, hash-checked evidence snapshot. Review every fact, context, source locator, '
        'subject, period and unit against this snapshot. Do not fetch sources again. '
        'You are the Review subagent in a session distinct from the Research subagent. '
        'Independence means independently assessing the frozen evidence and exact proposal, '
        'not fetching any site again or claiming a cryptographically signed identity. '
        'Do not read Research model traces or outputs beyond this supplied review packet.\nINPUT:\n'
        +encode(value).decode())


def prepare(repo, proposal_file, job, base_ref='origin/main', research_job=None):
    repo=Path(repo).resolve(); proposal_file=private_path(proposal_file); job=private_path(job)
    if job.exists(): raise FileExistsError('Use a new private native Review attempt')
    if research_job is None: raise ValueError('Offline Review requires a Research job snapshot')
    proposal_raw=proposal_file.read_bytes(); proposal=load_json(proposal_raw); entity=valid_qid(proposal['qid'])
    base,trust,catalog,digest=_base(repo,base_ref); _origin(repo,trust['repository'])
    if entity not in catalog or proposal.get('seed')!=seed_metadata(catalog[entity],digest): raise ValueError('Proposal QID or seed is outside the signed catalog')
    baseline,baseline_hash=baseline_at(repo,base,entity)
    if baseline_hash!=proposal['baseline_sha256']: raise ValueError('Proposal baseline changed on main')
    policy=blob(repo,base,'docs/review-policy-v2.md').decode('utf-8').replace('\r\n','\n')
    if sha(policy.encode())!=trust['review_policy']['sha256']: raise ValueError('Review policy does not match repository trust')
    job.mkdir(parents=True); _write(job/'public-proposal.json',encode(proposal))
    if research_job is not None:
        research_job=private_path(research_job)
        research_meta=load_json((research_job/'job.json').read_bytes())
        packet_bytes=(research_job/'cases'/entity/'research-packet.json').read_bytes()
        root_bytes=(research_job/'root-entity.json').read_bytes()
        if (research_meta.get('qid')!=entity or
                research_meta.get('catalog_sha256')!=digest or
                research_meta.get('schema_sha256')!=trust['schemas']['0.2.2'] or
                research_meta.get('review_policy_sha256')!=trust['review_policy']['sha256'] or
                research_meta.get('baseline_sha256')!=baseline_hash or
                sha(packet_bytes)!=research_meta.get('packet_sha256') or sha(root_bytes)!=research_meta.get('root_entity_sha256')):
            raise ValueError('Research snapshot identity/hash/baseline/catalog/policy mismatch; prepare new Research')
        packet=load_json(packet_bytes); root=load_json(root_bytes)
        verify_web_packet(packet)
        if proposal['delta']['sources']!=packet['sources']:
            raise ValueError('Review source snapshots differ from published proposal')
        from .research_contract import _root
        _,source=_root(packet)
        if root.get('id')!=entity or root.get('lastrevid')!=source['revision_id']:
            raise ValueError('Research root snapshot revision mismatch')
    point=_verify_native(proposal,baseline,packet,root); facts,contexts=_fact_scope(proposal['delta'])
    value={'proposal':proposal,'baseline':baseline,'facts':facts,'contexts':contexts,
        'source_corpus':packet['source_corpus'],'root_entity':root,'coordinate_projection':point}
    prompt=_prompt(value,policy).encode('utf-8'); shape=encode(REVIEW_SCHEMA)
    for name,data in (('review-packet.json',encode(packet)),('root-entity.json',encode(root)),('review-input.json',encode(value)),
                      ('prompt.txt',prompt),('output.schema.json',shape)): _write(job/name,data)
    manifest={'type':'native-review-job-v1','qid':entity,'base_commit':base,'catalog_sha256':digest,
        'schema_sha256':trust['schemas']['0.2.2'],'review_policy_sha256':trust['review_policy']['sha256'],
        'baseline_sha256':baseline_hash,'proposal_sha256':sha(encode(proposal)),'prepared_at':datetime.now(timezone.utc).isoformat(),
        'packet_sha256':sha(encode(packet)),'root_entity_sha256':sha(encode(root)),'review_input_sha256':sha(encode(value)),
        'prompt_sha256':sha(prompt),'output_schema_sha256':sha(shape),'native_code_sha256':sha(Path(__file__).read_bytes()),
        'shared_source_cache':True,'offline_research_snapshot':True}
    _write(job/'job.json',encode(manifest))
    return {'status':'prepared','qid':entity,'job_dir':str(job),'base_commit':base,
        'prompt_path':str(job/'prompt.txt'),'schema_path':str(job/'output.schema.json'),
        'review_input_sha256':manifest['review_input_sha256']}


def compile(repo, job, result_file, session, model, effort='medium', completed_at=None):
    repo=Path(repo).resolve(); job=private_path(job); result_file=private_path(result_file)
    if not isinstance(session,str) or not session.strip() or len(session)>200 or any(ord(c)<32 for c in session): raise ValueError('Native session ID required')
    if not isinstance(model,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}',model): raise ValueError('Valid native model identifier required')
    if effort not in ('low','medium','high','xhigh','max','ultra','not_reported'): raise ValueError('Invalid reported reasoning effort')
    attempt=job/'compile-attempts'/uuid.uuid4().hex; attempt.mkdir(parents=True,exist_ok=False)
    raw=result_file.read_bytes(); _write(attempt/'native-result.json',raw)
    manifest=load_json((job/'job.json').read_bytes())
    if manifest.get('type')!='native-review-job-v1': raise ValueError('Invalid native Review job')
    entity=valid_qid(manifest['qid']); base,trust,catalog,digest=_base(repo,manifest['base_commit'])
    if base!=manifest['base_commit'] or digest!=manifest['catalog_sha256'] or entity not in catalog: raise ValueError('Review Git base or signed catalog changed')
    if manifest['schema_sha256']!=trust['schemas']['0.2.2'] or manifest['review_policy_sha256']!=trust['review_policy']['sha256']: raise ValueError('Review schema or policy changed')
    baseline,baseline_hash=baseline_at(repo,base,entity)
    if baseline_hash!=manifest['baseline_sha256']: raise ValueError('Review baseline changed')
    files={'public-proposal.json':'proposal_sha256','review-packet.json':'packet_sha256','root-entity.json':'root_entity_sha256',
        'review-input.json':'review_input_sha256','prompt.txt':'prompt_sha256','output.schema.json':'output_schema_sha256'}
    for filename,key in files.items():
        if sha((job/filename).read_bytes())!=manifest[key]: raise ValueError('Prepared Review input changed: '+filename)
    if sha(Path(__file__).read_bytes())!=manifest['native_code_sha256']: raise ValueError('Native Review compiler changed after preparation')
    if load_json((job/'output.schema.json').read_bytes())!=REVIEW_SCHEMA: raise ValueError('Native Review schema changed')
    proposal=load_json((job/'public-proposal.json').read_bytes()); packet=load_json((job/'review-packet.json').read_bytes())
    verify_web_packet(packet)
    root=load_json((job/'root-entity.json').read_bytes()); value=load_json((job/'review-input.json').read_bytes())
    if proposal.get('qid')!=entity or proposal.get('seed')!=seed_metadata(catalog[entity],digest): raise ValueError('Review proposal identity or seed changed')
    point=_verify_native(proposal,baseline,packet,root); facts,contexts=_fact_scope(proposal['delta'])
    reconstructed={'proposal':proposal,'baseline':baseline,'facts':facts,'contexts':contexts,
        'source_corpus':packet['source_corpus'],'root_entity':root,'coordinate_projection':point}
    if value!=reconstructed: raise ValueError('Prepared Review input differs from independently captured sources')
    policy=blob(repo,base,'docs/review-policy-v2.md').decode('utf-8').replace('\r\n','\n')
    if sha(policy.encode())!=manifest['review_policy_sha256'] or (job/'prompt.txt').read_bytes()!=_prompt(value,policy).encode('utf-8'):
        raise ValueError('Native Review prompt differs from prepared task')
    if session==proposal['research']['session']: raise ValueError('Research and Review sessions must be distinct')
    verdict=load_json(raw); jsonschema.Draft202012Validator(REVIEW_SCHEMA).validate(verdict)
    if verdict['qid']!=entity: raise ValueError('Review QID mismatch')
    expected={r['id'] for r in facts+contexts}; checks=verdict['checks']
    if len(checks)!=len(expected) or {r['id'] for r in checks}!=expected: raise ValueError('Review fact/context coverage incomplete')
    if len(verdict['coverage_checks'])!=len(GROUPS) or {r['group'] for r in verdict['coverage_checks']}!=set(GROUPS): raise ValueError('Review group coverage incomplete')
    request_ids={r['request_id'] for r in proposal.get('open_requests',[])}; responses=verdict['request_responses']
    if len(responses)!=len(request_ids) or {r['request_id'] for r in responses}!=request_ids: raise ValueError('Review request response coverage incomplete')
    for row in checks+verdict['coverage_checks']+responses+verdict['requests']: _safe_reason(row['reason'])
    for row in verdict['requests']:
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,127}',row['field']): raise ValueError('Invalid requested field')
    supported=all(row['supported'] and row['support_basis'] in ('direct','reasonable_inference') for row in checks)
    addressed=all(row['status']=='addressed' for row in responses)
    if verdict['decision']=='approve' and (not supported or not addressed or verdict['requests']): raise ValueError('Incomplete or contradictory approval')
    if verdict['decision']=='request_changes' and not verdict['requests']: raise ValueError('Changes requested without actionable requests')
    declared={r['group']:r['status'] for r in proposal['coverage']}; checked={r['group']:r['status'] for r in verdict['coverage_checks']}
    full=(verdict['decision']=='approve' and declared==checked and not proposal['retrieval_failures'] and
          proposal['delta']['curation']['identity_status'] in ('in_scope','related','excluded'))
    at=completed_at or datetime.now(timezone.utc).isoformat(); instant(at)
    if instant(at)<instant(manifest['prepared_at']) or instant(at)<instant(proposal['proposed_at']): raise ValueError('Native Review predates its inputs')
    record=materialize(baseline,proposal['delta'],proposal['seed'],at,full) if verdict['decision']=='approve' else None
    inferences=[{'id':r['id'],'reason':_safe_reason(r['reason'])} for r in checks if r['support_basis']=='reasonable_inference']
    public={'decision':verdict['decision'],'qid':entity,'reviewed_at':at,'proposal_sha256':sha(encode(proposal)),
        'facts_checked':len(facts),'contexts_checked':len(contexts),'source_revisions_checked':len(proposal['delta']['sources']),
        'requests':deepcopy(verdict['requests']),'request_responses':deepcopy(responses),'coverage_checks':deepcopy(verdict['coverage_checks']),
        'model':model,'reasoning_effort':effort,'review_session':session,'full_refresh':full,'inferences':inferences}
    if record is not None: public['record_sha256']=sha(encode(record))
    _write(attempt/'public-verdict.json',encode(public))
    if record is not None: _write(attempt/'final-record.json',encode(record))
    _write(attempt/'result-metadata.json',encode({'session':session,'model':model,'reasoning_effort':effort,
        'completed_at':at,'provider_trace_verified':False,'native_result_sha256':sha(raw)}))
    result={'status':'compiled','qid':entity,'job_dir':str(job),'decision':verdict['decision'],
        'public_verdict':public,'public_verdict_path':str(attempt/'public-verdict.json'),'private_attempt':str(attempt),
        'session_and_model':'caller_reported','provider_trace_verified':False}
    if record is not None: result['final_record_path']=str(attempt/'final-record.json')
    return result
