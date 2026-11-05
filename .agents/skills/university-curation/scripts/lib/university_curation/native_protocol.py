"""Native subagent Draft and Review contracts; comments are account-attributed, not signed."""
from copy import deepcopy
import re

from . import distributed_protocol as legacy
from .attestations import sha
from .records import encode, instant
from .pr_export import blob, git, record_relative, batch_slug, canonical_json, no_legacy_duplicate
from .domain_refresh import materialize
from .distributed_feedback import _request

MARKER = 'university-native-review-v1'
PATTERN = re.compile(r'<!-- ' + MARKER + r'\n([\s\S]*?)-->')


def check_proposal(proposal, baseline, catalog, catalog_hash, trust):
    if proposal.get('transport', {}).get('protocol') != 'native-subagent-v1': raise ValueError('Native proposal protocol required')
    metadata=proposal.get('research', {})
    if not isinstance(metadata.get('model'), str) or not metadata['model'].strip() or metadata.get('reasoning_effort') not in ('low','medium','high','xhigh','max','ultra','not_reported') or not isinstance(metadata.get('session'), str) or not metadata['session'].strip(): raise ValueError('Truthful native model, effort and session required')
    adjusted = deepcopy(proposal); adjusted['transport']['protocol'] = 'distributed-v1'
    adjusted['research']['model']=trust['model']; adjusted['research']['reasoning_effort']=trust['reasoning_effort']
    return legacy.check_proposal(adjusted, baseline, catalog, catalog_hash, trust)


def check_decision(value, research, baseline, trust, pr_number=None):
    if value.get('type') != 'university-native-review-v1': raise ValueError('Native review decision required')
    # This helper performs business validation but no signature claims.
    from .distributed_protocol import check_decision_payload
    return check_decision_payload(value, research, baseline, trust, pr_number)


def draft_files(repo, base, proposals, batch):
    trust = legacy.trust_at(repo, base); catalog, catalog_hash = legacy.catalog_at(repo, base, trust); batch = batch_slug(batch)
    if not isinstance(proposals, list) or not 1 <= len(proposals) <= trust['max_schools_per_batch']: raise ValueError('Invalid proposal count')
    files = {}; rows = []; seen = set()
    for proposal in sorted(proposals, key=lambda p: int(p['qid'][1:])):
        entity = proposal['qid']
        if entity in seen: raise ValueError('Duplicate QID')
        baseline, _ = legacy.baseline_at(repo, base, entity)
        check_proposal(proposal, baseline, catalog, catalog_hash, trust)
        path = 'data/proposals/' + batch + '/' + entity + '.json'; raw = encode(proposal)
        files[path] = raw; rows.append({'qid':entity, 'path':path, 'sha256':sha(raw)}); seen.add(entity)
    manifest = {'type':'university-native-draft-v1','repository':trust['repository'],'batch_id':batch,'base_commit':base,'seed_catalog_sha256':catalog_hash,'records':rows}
    files['data/proposals/' + batch + '/manifest.json'] = encode(manifest)
    return files


def inspect_draft(repo, base, head, trust):
    paths = [p for p in git(repo,'diff','--no-renames','--name-only','-z',base,head).decode().split('\0') if p]
    manifests = [p for p in paths if re.fullmatch(r'data/proposals/[a-z0-9][a-z0-9-]{0,79}/manifest\.json',p)]
    if len(manifests) != 1: raise ValueError('One native Draft manifest required')
    manifest = canonical_json(blob(repo,head,manifests[0]))
    if set(manifest) != {'type','repository','batch_id','base_commit','seed_catalog_sha256','records'} or manifest['type'] != 'university-native-draft-v1' or manifest['repository'] != trust['repository'] or manifest['base_commit'] != base: raise ValueError('Draft identity/base mismatch')
    batch = batch_slug(manifest['batch_id']); catalog, catalog_hash = legacy.catalog_at(repo,base,trust)
    if manifests[0] != 'data/proposals/'+batch+'/manifest.json' or manifest['seed_catalog_sha256'] != catalog_hash or not 1 <= len(manifest['records']) <= trust['max_schools_per_batch']: raise ValueError('Draft catalog/size mismatch')
    expected = {manifests[0]}; proposals = {}; ids = []
    for row in manifest['records']:
        entity=row['qid']; path='data/proposals/'+batch+'/'+entity+'.json'
        if row['path'] != path: raise ValueError('Draft path mismatch')
        raw=blob(repo,head,path); proposal=canonical_json(raw)
        if sha(raw) != row['sha256'] or proposal['qid'] != entity: raise ValueError('Draft bytes or identity mismatch')
        baseline,_=legacy.baseline_at(repo,base,entity); check_proposal(proposal,baseline,catalog,catalog_hash,trust)
        expected.add(path); proposals[entity]=proposal; ids.append(entity)
    if len(ids)!=len(set(ids)) or ids!=sorted(ids,key=lambda q:int(q[1:])) or set(paths)!=expected: raise ValueError('Draft membership mismatch')
    return manifest,proposals


def finalized_files(repo, base, batch, proposals, decisions):
    trust=legacy.trust_at(repo,base); catalog,catalog_hash=legacy.catalog_at(repo,base,trust); batch=batch_slug(batch)
    if not isinstance(proposals,dict) or not 1 <= len(proposals) <= trust['max_schools_per_batch'] or set(proposals)!=set(decisions): raise ValueError('Every proposal requires a Review')
    files={}; rows=[]; pr=None
    for entity,proposal in sorted(proposals.items(),key=lambda row:int(row[0][1:])):
        if proposal.get('qid') != entity: raise ValueError('Proposal subject mismatch')
        baseline,_=legacy.baseline_at(repo,base,entity); check_proposal(proposal,baseline,catalog,catalog_hash,trust)
        verdict,record=check_decision(decisions[entity],proposal,baseline,trust)
        if verdict['decision']!='approve' or record is None: raise ValueError('Proposal lacks independent approval')
        if pr is not None and pr != verdict['pr_number']: raise ValueError('Review PR mismatch')
        pr=verdict['pr_number']; p=record_relative(entity); receipt_path='data/reviews/'+batch+'/'+entity+'.json'
        receipt={'type':'university-native-receipt-v1','research':proposal,'review':decisions[entity]}
        files[p]=encode(record); files[receipt_path]=encode(receipt)
        rows.append({'qid':entity,'record_path':p,'record_sha256':sha(files[p]),'receipt_path':receipt_path,'receipt_sha256':sha(files[receipt_path])})
    manifest={'type':'university-native-final-v1','repository':trust['repository'],'batch_id':batch,'base_commit':base,'seed_catalog_sha256':catalog_hash,'records':rows}
    files['data/batches/'+batch+'.json']=encode(manifest)
    return files


def verify_final(repo, base, files, trust):
    manifests=[p for p in files if re.fullmatch(r'data/batches/[a-z0-9][a-z0-9-]{0,79}\.json',p)]
    if len(manifests)!=1: raise ValueError('One final manifest required')
    manifest=canonical_json(files[manifests[0]])
    if set(manifest)!={'type','repository','batch_id','base_commit','seed_catalog_sha256','records'} or manifest['type']!='university-native-final-v1' or manifest['repository']!=trust['repository'] or manifest['base_commit']!=base: raise ValueError('Final identity/base mismatch')
    batch=batch_slug(manifest['batch_id']); catalog,catalog_hash=legacy.catalog_at(repo,base,trust)
    if manifest['seed_catalog_sha256']!=catalog_hash or not 1<=len(manifest['records'])<=trust['max_schools_per_batch']: raise ValueError('Final catalog/size mismatch')
    if manifests[0]!='data/batches/'+batch+'.json' or blob(repo,base,manifests[0],optional=True) is not None: raise ValueError('Final batch is immutable')
    expected={manifests[0]}; ids=[]; review_pr=None
    for row in manifest['records']:
        entity=row['qid']; p=record_relative(entity); receipt_path='data/reviews/'+batch+'/'+entity+'.json'
        no_legacy_duplicate(repo,base,entity)
        if row['record_path']!=p or row['receipt_path']!=receipt_path: raise ValueError('Final path mismatch')
        if blob(repo,base,receipt_path,optional=True) is not None: raise ValueError('Receipt immutable')
        if sha(files[p])!=row['record_sha256'] or sha(files[receipt_path])!=row['receipt_sha256']: raise ValueError('Final bytes changed')
        receipt=canonical_json(files[receipt_path])
        if set(receipt)!={'type','research','review'} or receipt['type']!='university-native-receipt-v1': raise ValueError('Invalid native receipt')
        proposal=receipt['research']; baseline,_=legacy.baseline_at(repo,base,entity)
        if proposal['qid']!=entity: raise ValueError('Final subject mismatch')
        check_proposal(proposal,baseline,catalog,catalog_hash,trust)
        verdict,record=check_decision(receipt['review'],proposal,baseline,trust)
        if verdict['decision']!='approve' or record is None or record['qid']!=entity or encode(record)!=files[p]: raise ValueError('No Review for exact final bytes')
        if review_pr is not None and review_pr!=verdict['pr_number']: raise ValueError('Review receipts from different PRs')
        review_pr=verdict['pr_number']; expected.update((p,receipt_path)); ids.append(entity)
    if len(ids)!=len(set(ids)) or ids!=sorted(ids,key=lambda q:int(q[1:])) or set(files)!=expected: raise ValueError('Final membership mismatch')
    return {'status':'validated','task_kind':'native_research','batch_id':batch,'qids':ids,'base_commit':base,'review_pr':review_pr}


def review_comment(value):
    raw=encode(value).decode()
    if len(raw.encode())>60000: raise ValueError('Review comment exceeds limit')
    return 'Native independent Review; role/session are workflow attestations.\n\n<!-- '+MARKER+'\n'+raw+'-->'


def _comments(comments, trust, pr_number, qid):
    owner=trust['repository'].split('/')[0].lower()
    for comment in sorted(comments,key=lambda c:c.get('id',0)):
        if (comment.get('user') or {}).get('login','').lower()!=owner or type(comment.get('id')) is not int or comment['id']<1: continue
        matches=PATTERN.findall(comment.get('body') or '')
        if len(matches)!=1: continue
        try:
            value=canonical_json(matches[0].encode())
            if value.get('repository')!=trust['repository'] or value.get('pr_number')!=pr_number or value.get('qid')!=qid: continue
            yield value,comment
        except (ValueError,TypeError,AttributeError): continue


def read_reviews(comments, trust, pr_number, qid, proposal_hash):
    return [(v,c['id'],c.get('html_url')) for v,c in _comments(comments,trust,pr_number,qid)
            if v.get('type')=='university-native-review-v1' and v.get('proposal_sha256')==proposal_hash]


def read_requests(comments, trust, pr_number, qid, resolved_by_validated_decision=None):
    requests={}; resolved=set()
    for value,comment in _comments(comments,trust,pr_number,qid):
        try:
            head=value['reviewed_head_sha']
            if not re.fullmatch(r'[0-9a-f]{40}',head) or not re.fullmatch(r'[0-9a-f]{64}',value['proposal_sha256']): continue
            if value.get('type')=='university-native-objection-v1':
                events=[_request(value,head,comment['id'])]; at=instant(value['created_at'])
            elif value.get('type')=='university-native-review-v1' and value.get('decision')=='request_changes':
                events=[_request(row,head,comment['id']) for row in value['requests']]; at=instant(value['reviewed_at'])
            else:
                events=[]; at=None
            for item in events:
                if item['request_id'] not in requests: requests[item['request_id']]=(item,at)
            if value.get('type')=='university-native-review-v1' and value.get('decision')=='approve' and value==resolved_by_validated_decision:
                at=instant(value['reviewed_at'])
                for row in value.get('request_responses',[]):
                    ident=row.get('request_id')
                    if row.get('status')=='addressed' and ident in requests and comment['id']>requests[ident][0]['comment_id'] and at>=requests[ident][1]: resolved.add(ident)
        except (ValueError,KeyError,TypeError,AttributeError): continue
    return [row[0] for ident,row in requests.items() if ident not in resolved]
