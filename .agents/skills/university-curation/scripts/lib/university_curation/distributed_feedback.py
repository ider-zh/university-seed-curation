"""Role-signed, persistent Review objections carried by GitHub PR comments."""
from datetime import datetime, timezone
import re
import uuid

from .attestations import load_json, sha, sign, verify
from .distributed_jobs import _safe_reason
from .distributed_protocol import REVIEW_MARKER, signed_comment
from .records import encode, instant, qid as valid_qid

CATEGORIES = {'subject_mismatch','evidence_gap','value_error','scope_conflict','schema_error','other'}
FIELD = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{0,127}\Z')
SHA = re.compile(r'[0-9a-f]{40}\Z')
HASH = re.compile(r'[0-9a-f]{64}\Z')
COMMENT = re.compile(r'<!-- ' + re.escape(REVIEW_MARKER) + r'\n([\s\S]*?)-->')


def _id(value):
    if not isinstance(value,str): raise ValueError('Invalid request ID')
    try:
        if str(uuid.UUID(value)) != value: raise ValueError('Invalid request ID')
    except (ValueError,AttributeError): raise ValueError('Invalid request ID') from None
    return value


def _request(row, head, comment_id):
    if not isinstance(row,dict): raise ValueError('Invalid objection')
    ident=_id(row['request_id']); field=row['field']; category=row['category']; reason=_safe_reason(row['reason'])
    if not isinstance(field,str) or not FIELD.fullmatch(field) or category not in CATEGORIES: raise ValueError('Invalid objection field or category')
    return {'request_id':ident,'field':field,'category':category,'reason':reason,'reviewed_head_sha':head,'comment_id':comment_id}


def _pull(pull, repository, number=None):
    if not isinstance(pull,dict): raise ValueError('Invalid pull request')
    pr=pull.get('number'); head=pull.get('head',{}).get('sha')
    if type(pr) is not int or pr<1 or (number is not None and pr!=number): raise ValueError('Invalid PR number')
    if pull.get('state')!='open' or pull.get('base',{}).get('ref')!='main': raise ValueError('Open PR against main required')
    if (pull.get('head',{}).get('repo') or {}).get('full_name')!=repository or not isinstance(head,str) or not SHA.fullmatch(head):
        raise ValueError('PR head is outside the trusted repository')
    return pr,head


def submit_objection(client,pull,proposal_document,review_key,trust,field,category,reason):
    repository=trust['repository']; pr,head=_pull(pull,repository)
    if getattr(client,'repository',None)!=repository: raise ValueError('GitHub client repository mismatch')
    proposal=verify(proposal_document,trust,role='research'); entity=valid_qid(proposal['qid'])
    if proposal.get('type')!='university-proposal-v1' or proposal.get('transport',{}).get('repository')!=repository: raise ValueError('Proposal repository or type mismatch')
    row={'request_id':str(uuid.uuid4()),'field':field,'category':category,'reason':reason}
    _request(row,head,1)
    if _pull(client.pull(pr),repository,pr)[1]!=head: raise ValueError('Reviewed PR head is stale')
    payload={'type':'university-review-objection-v1','repository':repository,'pr_number':pr,'reviewed_head_sha':head,
        'qid':entity,'proposal_sha256':sha(encode(proposal)),'request_id':row['request_id'],'field':field,
        'category':category,'reason':_safe_reason(reason),'created_at':datetime.now(timezone.utc).isoformat()}
    document=sign(payload,review_key,trust,role='review')
    if document['key_id']==proposal_document['key_id']: raise ValueError('Research and Review keys must differ')
    if _pull(client.pull(pr),repository,pr)[1]!=head: raise ValueError('Reviewed PR head is stale')
    response=client.request('POST','/issues/'+str(pr)+'/comments',{'body':signed_comment(document)})
    if not pull.get('draft', False) and hasattr(client, 'set_draft'): client.set_draft(client.pull(pr), True)
    return {'request_id':row['request_id'],'head_sha':head,'qid':entity,'comment_id':response['id'],
            **({'comment_url':response['html_url']} if response.get('html_url') else {})}


def requests_from_comments(comments,trust,pr_number,qid,resolved_by=None):
    entity=valid_qid(qid)
    if type(pr_number) is not int or pr_number<1: raise ValueError('Invalid PR number')
    if not isinstance(comments,list): raise ValueError('Expected a list of GitHub comments')
    events=[]
    for comment in comments:
        try:
            cid=comment.get('id')
            if type(cid) is not int or cid<1: continue
            body=comment.get('body') or ''
            found=COMMENT.findall(body)
            if len(found)!=1: continue
            doc=load_json(found[0].strip().encode()); value=verify(doc,trust,role='review')
            if value.get('repository')!=trust['repository'] or value.get('pr_number')!=pr_number or value.get('qid')!=entity: continue
            head=value.get('reviewed_head_sha'); ph=value.get('proposal_sha256')
            if not isinstance(head,str) or not SHA.fullmatch(head) or not isinstance(ph,str) or not HASH.fullmatch(ph): continue
            kind=value.get('type')
            if kind=='university-review-objection-v1':
                at=instant(value['created_at']); events.append((cid,'request',(_request(value,head,cid),at)))
            elif kind=='university-review-decision-v1' and value.get('decision')=='request_changes':
                at=instant(value['reviewed_at'])
                for row in value.get('requests',[]): events.append((cid,'request',(_request(row,head,cid),at)))
            # The caller must first validate this exact decision against its
            # proposal/baseline. An unrelated signed approval cannot clear it.
            elif kind=='university-review-decision-v1' and value.get('decision')=='approve' and doc==resolved_by:
                at=instant(value['reviewed_at'])
                for row in value.get('request_responses',[]):
                    if isinstance(row,dict) and row.get('status')=='addressed': events.append((cid,'resolve',(_id(row.get('request_id')),at)))
        except (ValueError,KeyError,TypeError,AttributeError): continue
    # GitHub comment IDs order comments. An earlier approval cannot pre-resolve a later objection.
    requests={}; resolved=set()
    for cid,kind,value in sorted(events,key=lambda event:event[0]):
        if kind=='request':
            request, at=value; ident=request['request_id']
            if ident not in requests: requests[ident]=(request,at)
        else:
            ident, at=value
            if ident in requests and cid>requests[ident][0]['comment_id'] and at>=requests[ident][1]: resolved.add(ident)
    return [value[0] for ident,value in requests.items() if ident not in resolved]


def assert_no_objections(comments,trust,pr,qids,decisions=None):
    if not isinstance(qids,(list,tuple,set)) or not qids: raise ValueError('Expected nonempty QID set')
    blocked=[qid for qid in qids if requests_from_comments(comments,trust,pr,qid,resolved_by=(decisions or {}).get(qid))]
    if blocked: raise ValueError('Unresolved independently signed Review objections: '+', '.join(sorted(blocked)))
    return True
