from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.agents/skills/university-curation/scripts/lib'))
from university_curation.attestations import sha, sign
from university_curation.distributed_protocol import signed_comment
from university_curation.distributed_feedback import submit_objection,requests_from_comments,assert_no_objections

REPO='owner/repo'; HEAD='1'*40; NEXT='2'*40; HASH='a'*64; QID='Q101'; PR=8

class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.private=Path(self.temp.name)/'.private'; self.private.mkdir()
        self.trust={'repository':REPO,'keys':{}}
        self.rkey=self.make_key('research'); self.vkey=self.make_key('review')
        self.proposal=sign({'type':'university-proposal-v1','qid':QID,'transport':{'repository':REPO}},self.rkey,self.trust,role='research')
        self.ident=str(uuid.uuid4())
    def tearDown(self): self.temp.cleanup()
    def make_key(self,role):
        key=Ed25519PrivateKey.generate(); path=self.private/(role+'.pem')
        path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.trust['keys']['review-'+sha(public)[:16]]={'algorithm':'Ed25519','public_key_hex':public.hex(),'status':'active','roles':[role]}
        return path
    def envelope(self,payload,role='review'):
        return sign(payload,self.vkey if role=='review' else self.rkey,self.trust,role=role)
    def comment(self,ident,payload,role='review'):
        return {'id':ident,'body':signed_comment(self.envelope(payload,role)),'html_url':'https://github.com/example'}
    def objection(self,head=HEAD):
        return {'type':'university-review-objection-v1','repository':REPO,'pr_number':PR,'qid':QID,
            'reviewed_head_sha':head,'proposal_sha256':HASH,'request_id':self.ident,'field':'geography',
            'category':'scope_conflict','reason':'Item point may have another scope','created_at':'2026-11-05T00:00:00Z'}
    def decision(self,decision='approve'):
        return {'type':'university-review-decision-v1','repository':REPO,'pr_number':PR,'qid':QID,
            'reviewed_head_sha':NEXT,'proposal_sha256':'b'*64,'decision':decision,'reviewed_at':'2026-11-05T01:00:00Z',
            'request_responses':[{'request_id':self.ident,'status':'addressed','reason':'Checked'}]}
    def test_head_changes_do_not_clear_and_only_signed_later_review_resolves(self):
        comments=[self.comment(1,self.objection()),self.comment(2,self.decision(),'research')]
        rows=requests_from_comments(comments,self.trust,PR,QID)
        self.assertEqual(len(rows),1); self.assertEqual(rows[0]['reviewed_head_sha'],HEAD)
        with self.assertRaises(ValueError): assert_no_objections(comments,self.trust,PR,[QID])
        comments.append(self.comment(3,self.decision()))
        # A signature alone is insufficient: only the caller-validated exact
        # decision for the final proposal can resolve an objection.
        self.assertEqual(len(requests_from_comments(comments,self.trust,PR,QID)),1)
        decision=self.envelope(self.decision())
        self.assertEqual(requests_from_comments(comments,self.trust,PR,QID,resolved_by=decision),[])
        self.assertTrue(assert_no_objections(comments,self.trust,PR,[QID],decisions={QID:decision}))
    def test_request_changes_duplicates_and_earlier_approval_are_safe(self):
        decision={'type':'university-review-decision-v1','repository':REPO,'pr_number':PR,'qid':QID,
            'reviewed_head_sha':NEXT,'proposal_sha256':HASH,'decision':'request_changes','reviewed_at':'2026-11-05T00:30:00Z','requests':[
                {'request_id':self.ident,'field':'identity','category':'evidence_gap','reason':'Check name'}]}
        comments=[self.comment(1,self.decision()),self.comment(2,decision),self.comment(3,decision),{'id':4,'body':'garbled'}]
        rows=requests_from_comments(comments,self.trust,PR,QID)
        self.assertEqual(len(rows),1); self.assertEqual(rows[0]['comment_id'],2)
        self.assertEqual(rows[0]['reviewed_head_sha'],NEXT)
    def test_signed_objection_refuses_stale_head_and_cross_role_key(self):
        def pull(head): return {'number':PR,'state':'open','base':{'ref':'main'},'head':{'sha':head,'repo':{'full_name':REPO}}}
        class Client:
            repository=REPO
            def __init__(self,current): self.current=current; self.posted=[]
            def pull(self,n): return pull(self.current)
            def request(self,method,path,body): self.posted.append(body); return {'id':21,'html_url':'https://example.com/comment'}
        stale=Client(NEXT)
        with self.assertRaisesRegex(ValueError,'stale'): submit_objection(stale,pull(HEAD),self.proposal,self.vkey,self.trust,'identity','evidence_gap','Check source')
        self.assertEqual(stale.posted,[])
        good=Client(HEAD)
        with self.assertRaises(ValueError): submit_objection(good,pull(HEAD),self.proposal,self.rkey,self.trust,'identity','evidence_gap','Check source')
        self.assertEqual(good.posted,[])
        result=submit_objection(good,pull(HEAD),self.proposal,self.vkey,self.trust,'identity','evidence_gap','Check source')
        self.assertEqual(result['comment_id'],21); self.assertEqual(len(good.posted),1)
        rows=requests_from_comments([{'id':21,'body':good.posted[0]['body']}],self.trust,PR,QID)
        self.assertEqual(rows[0]['request_id'],result['request_id'])

if __name__=='__main__': unittest.main()
