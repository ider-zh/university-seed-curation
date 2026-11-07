"""One-workspace Research subagent -> Review subagent -> guarded direct-main publication.

Review remains an explicit, coverage-checked decision; no PR or role signature is
claimed. Published receipts make the provenance and reduced independence clear.
"""
from pathlib import Path
import re

from .integrity import load_json, private_path, sha
from .workflow_contract import attach_transport, baseline_at
from .domain_refresh import materialize
from .workflow_contract import check_proposal, check_publication_base, check_review_refresh
from .native_research import _base
from .git_data import batch_slug, blob, canonical_json, no_legacy_duplicate, record_relative
from .preferred import validate, recompute
from .review_scope import scope, validate_receipt
from .records import encode, instant


def check_batch_sessions(proposals_and_verdicts):
    """Require a dedicated Research/Review pair for every QID in a new batch."""
    research=[proposal['research']['session'] for proposal,_ in proposals_and_verdicts]
    reviews=[verdict['review_session'] for _,verdict in proposals_and_verdicts]
    if not research:
        raise ValueError('Publication requires at least one Research/Review pair')
    if len(reviews)!=len(set(reviews)):
        raise ValueError('Each QID requires its own Review subagent session')
    if len(research)!=len(set(research)):
        raise ValueError('Each QID requires its own Research subagent session')
    if set(reviews).intersection(research):
        raise ValueError('Review session cannot also be a Research session in this batch')
    return tuple(reviews)


def _verified(repo, base, proposal, review_job, attempt, trust, catalog, catalog_hash):
    job=private_path(review_job); attempt=private_path(attempt)
    if attempt.parent != job/'compile-attempts' or not attempt.is_dir():
        raise ValueError('Review attempt must be generated inside the supplied Review job')
    meta=load_json((job/'job.json').read_bytes())
    if meta.get('type')!='native-review-job-v1' or not meta.get('offline_research_snapshot'):
        raise ValueError('An offline Research-snapshot Review job is required')
    if meta['catalog_sha256'] != catalog_hash:
        raise ValueError('Review is stale relative to catalog')
    check_publication_base(repo,meta['base_commit'],base,[proposal['qid']])
    check_publication_base(repo,proposal['transport']['base_commit'],meta['base_commit'])
    if sha(encode(proposal)) != meta['proposal_sha256'] or (job/'public-proposal.json').read_bytes()!=encode(proposal):
        raise ValueError('Review did not inspect the exact Research proposal')
    if meta['schema_sha256']!=trust['schemas']['0.2.2'] or meta['review_policy_sha256']!=trust['review_policy']['sha256']:
        raise ValueError('Review schema/policy mismatch')
    entity=proposal['qid']; baseline,baseline_hash=baseline_at(repo,base,entity)
    from .manager import check_requests, required_requests
    check_requests(required_requests(repo,base,entity),proposal.get('open_requests',[]))
    if baseline_hash!=meta['baseline_sha256']: raise ValueError('Record baseline changed')
    check_proposal(proposal,baseline,catalog,catalog_hash,trust)
    verdict=canonical_json((attempt/'public-verdict.json').read_bytes())
    metadata=canonical_json((attempt/'result-metadata.json').read_bytes())
    if metadata.get('native_result_sha256')!=sha((attempt/'native-result.json').read_bytes()):
        raise ValueError('Review result changed after deterministic compilation')
    if verdict.get('decision')!='approve' or verdict.get('qid')!=entity or verdict.get('proposal_sha256')!=sha(encode(proposal)):
        raise ValueError('Exact proposal lacks Review approval')
    if verdict.get('requests') or any(r['status']!='addressed' for r in verdict['request_responses']):
        raise ValueError('Unresolved Review questions')
    check_review_refresh(proposal,verdict)
    if metadata.get('session')!=verdict['review_session'] or metadata.get('model')!=verdict['model'] or metadata.get('reasoning_effort')!=verdict['reasoning_effort']:
        raise ValueError('Review provenance mismatch')
    if verdict['review_session']==proposal['research']['session']:
        raise ValueError('Research and Review subagent sessions must differ')
    if instant(verdict['reviewed_at'])<instant(meta['prepared_at']): raise ValueError('Review predates source replay')
    if not verdict.get('source_revisions_checked') == len(proposal['delta']['sources']): raise ValueError('Incomplete source coverage')
    from .research_contract import _fact_scope
    from .research_schema import GROUPS
    facts,contexts,_=scope(proposal['delta'])
    validate_receipt(proposal['delta'],verdict)
    if verdict['facts_checked']!=len(facts) or verdict['contexts_checked']!=len(contexts) or {r['group'] for r in verdict['coverage_checks']}!=set(GROUPS):
        raise ValueError('Incomplete Review coverage')
    record=materialize(baseline,proposal['delta'],proposal['seed'],verdict['reviewed_at'],verdict['full_refresh'])
    validate(record)
    if recompute(record)!=record: raise ValueError('Preferred projection changed')
    if (attempt/'final-record.json').read_bytes()!=encode(record) or verdict.get('record_sha256')!=sha(encode(record)):
        raise ValueError('Canonical record differs from approved bytes')
    return record, verdict


def transport_proposal(repo, base_ref, raw_path):
    base,trust,_,digest=_base(repo,base_ref)
    proposal=load_json(private_path(raw_path).read_bytes())
    if 'transport' in proposal: raise ValueError('Research proposal already has transport')
    proposal=attach_transport(proposal,trust['repository'],base,digest,trust)
    proposal['transport']['protocol']='native-subagent-v1'
    return proposal


def files(repo, base, batch, proposals_and_reviews):
    repo=Path(repo).resolve(); batch=batch_slug(batch)
    base_commit,trust,catalog,catalog_hash=_base(repo,base)
    if not 1<=len(proposals_and_reviews)<=trust['max_schools_per_batch']:
        raise ValueError('Invalid direct-main batch size')
    output={}; rows=[]; seen=set(); reviewed=[]
    for proposal_path,job_path,attempt_path in proposals_and_reviews:
        proposal=load_json(private_path(proposal_path).read_bytes())
        if 'transport' not in proposal:
            raise ValueError('Use unified-proposal before Review; reviewed bytes must match publication')
        entity=proposal['qid']
        from .manager import publication_ready
        publication_ready(repo,entity,proposal_path,job_path,attempt_path)
        if entity in seen: raise ValueError('Duplicate Research QID')
        seen.add(entity)
        record,verdict=_verified(repo,base_commit,proposal,job_path,attempt_path,trust,catalog,catalog_hash)
        reviewed.append((proposal,verdict))
        record_path=record_relative(entity); receipt_path='data/reviews/'+batch+'/'+entity+'.json'
        no_legacy_duplicate(repo,base_commit,entity)
        if blob(repo,base_commit,receipt_path,optional=True) is not None: raise ValueError('Immutable receipt exists')
        receipt={'type':'university-unified-receipt-v1','research':proposal,'review':verdict,
                 'attribution':'distinct_native_research_and_review_subagents;not_cryptographic_identity',
                 'review_result_sha256':sha(private_path(attempt_path).joinpath('native-result.json').read_bytes())}
        output[record_path]=encode(record); output[receipt_path]=encode(receipt)
        rows.append({'qid':entity,'record_path':record_path,'record_sha256':sha(output[record_path]),
                     'receipt_path':receipt_path,'receipt_sha256':sha(output[receipt_path])})
    check_batch_sessions(reviewed)
    rows.sort(key=lambda r:int(r['qid'][1:]))
    manifest={'type':'university-unified-batch-v1','repository':trust['repository'],'batch_id':batch,
              'base_commit':base_commit,'seed_catalog_sha256':catalog_hash,'records':rows}
    path='data/batches/'+batch+'.json'
    if blob(repo,base_commit,path,optional=True) is not None: raise ValueError('Immutable batch exists')
    output[path]=encode(manifest)
    from .manager import BACKLOG, after_publication
    output[BACKLOG]=after_publication(repo,base_commit,seen)
    verify_files(repo,base_commit,output,trust)
    return output


def verify_files(repo, base, files, trust):
    manifests=[p for p in files if re.fullmatch(r'data/batches/[a-z0-9][a-z0-9-]{0,79}\.json',p)]
    if len(manifests)!=1: raise ValueError('Exactly one unified manifest required')
    manifest=canonical_json(files[manifests[0]])
    if set(manifest)!={'type','repository','batch_id','base_commit','seed_catalog_sha256','records'} or manifest['type']!='university-unified-batch-v1' or manifest['repository']!=trust['repository'] or manifest['base_commit']!=base:
        raise ValueError('Invalid unified manifest')
    batch=batch_slug(manifest['batch_id']); _,_,catalog,digest=_base(repo,base)
    if manifests[0]!='data/batches/'+batch+'.json' or manifest['seed_catalog_sha256']!=digest or blob(repo,base,manifests[0],optional=True) is not None:
        raise ValueError('Unified manifest baseline mismatch')
    rows=manifest['records']; ids=[r['qid'] for r in rows]
    if not 1<=len(rows)<=trust['max_schools_per_batch'] or ids!=sorted(set(ids),key=lambda q:int(q[1:])):
        raise ValueError('Invalid unified batch membership')
    expected={manifests[0]}
    from .manager import BACKLOG, backlog_at, validate_checkpoint
    if BACKLOG not in files: raise ValueError('Publication must include the pending backlog')
    checkpoint=canonical_json(files[BACKLOG])
    validate_checkpoint(backlog_at(repo,base),checkpoint,ids)
    if any(entity not in catalog for entity in checkpoint['tasks']): raise ValueError('Checkpoint QID outside catalog')
    expected.add(BACKLOG)
    reviewed=[]
    for row in rows:
        entity=row['qid']; path=record_relative(entity); receipt_path='data/reviews/'+batch+'/'+entity+'.json'
        if set(row)!={'qid','record_path','record_sha256','receipt_path','receipt_sha256'} or row['record_path']!=path or row['receipt_path']!=receipt_path:
            raise ValueError('Invalid unified record path')
        expected.update((path,receipt_path))
        if sha(files[path])!=row['record_sha256'] or sha(files[receipt_path])!=row['receipt_sha256']: raise ValueError('Unified data digest mismatch')
        if blob(repo,base,receipt_path,optional=True) is not None: raise ValueError('Immutable receipt exists')
        no_legacy_duplicate(repo,base,entity)
        receipt=canonical_json(files[receipt_path]); record=canonical_json(files[path])
        attribution=receipt.get('attribution','')
        if (set(receipt)!={'type','research','review','attribution','review_result_sha256'} or
                receipt['type']!='university-unified-receipt-v1' or
                attribution!='distinct_native_research_and_review_subagents;not_cryptographic_identity'):
            raise ValueError('Invalid unified receipt')
        proposal=receipt['research']; verdict=receipt['review']; baseline,_=baseline_at(repo,base,entity)
        check_publication_base(repo,proposal['transport']['base_commit'],base)
        validate_receipt(proposal['delta'],verdict)
        reviewed.append((proposal,verdict))
        check_proposal(proposal,baseline,catalog,digest,trust)
        check_review_refresh(proposal,verdict)
        if verdict['decision']!='approve' or verdict['qid']!=entity or verdict['proposal_sha256']!=sha(encode(proposal)) or verdict['record_sha256']!=sha(files[path]) or verdict['requests']:
            raise ValueError('No approval for exact record')
        if verdict['review_session']==proposal['research']['session'] or verdict['source_revisions_checked']!=len(proposal['delta']['sources']):
            raise ValueError('Incomplete unified provenance')
        if encode(materialize(baseline,proposal['delta'],proposal['seed'],verdict['reviewed_at'],verdict['full_refresh']))!=files[path]:
            raise ValueError('Unified materialization mismatch')
        validate(record)
        if recompute(record)!=record: raise ValueError('Invalid preferred projection')
    check_batch_sessions(reviewed)
    if set(files)!=expected: raise ValueError('Unexpected public files in unified batch')
    return {'status':'validated','task_kind':'unified','batch_id':batch,'qids':ids,'base_commit':base}
