from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.agents/skills/university-curation/scripts/lib'))
from university_curation import native_protocol as native
from university_curation.attestations import sha
from university_curation.records import encode
import test_distributed_protocol as protocol_fixture

class NativeTests(unittest.TestCase):
    def setUp(self):
        self.fixture=protocol_fixture.DistributedProtocolTests('test_role_separation'); self.fixture.setUp(); f=self.fixture
        self.proposal=deepcopy(f.proposal); self.proposal['transport']['protocol']='native-subagent-v1'
        self.proposal['research']['model']='not_reported'; self.proposal['research']['reasoning_effort']='not_reported'
        self.decision=deepcopy(f.decision); self.decision['type']='university-native-review-v1'; self.decision['proposal_sha256']=sha(encode(self.proposal))
        self.decision['model']='not_reported'; self.decision['reasoning_effort']='not_reported'
        self.repo='repo'; self.base='f'*40; self.batch='batch-1'
        self.patches=[patch.object(native.legacy,'trust_at',return_value=f.trust),patch.object(native.legacy,'catalog_at',return_value=(f.catalog,f.catalog_hash)),
                      patch.object(native.legacy,'baseline_at',return_value=(None,'absent')),patch.object(native,'blob',return_value=None),patch.object(native,'no_legacy_duplicate')]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.fixture.tearDown()
    def test_native_review_and_independence(self):
        f=self.fixture
        native.check_proposal(self.proposal,None,f.catalog,f.catalog_hash,f.trust)
        value,record=native.check_decision(self.decision,self.proposal,None,f.trust,8)
        self.assertEqual(value['type'],'university-native-review-v1'); self.assertEqual(encode(record),encode(f.record))
        bad=deepcopy(self.decision); bad['review_session']=self.proposal['research']['session']
        with self.assertRaisesRegex(ValueError,'Independent'): native.check_decision(bad,self.proposal,None,f.trust,8)
        with self.assertRaisesRegex(ValueError,'another PR'): native.check_decision(self.decision,self.proposal,None,f.trust,9)
        bad=deepcopy(self.decision); bad['record_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'record hash'): native.check_decision(bad,self.proposal,None,f.trust)
    def test_files_require_review_and_preserve_exact_bytes(self):
        with self.assertRaises(ValueError): native.finalized_files(self.repo,self.base,self.batch,{'Q101':self.proposal},{})
        files=native.finalized_files(self.repo,self.base,self.batch,{'Q101':self.proposal},{'Q101':self.decision})
        result=native.verify_final(self.repo,self.base,files,self.fixture.trust)
        self.assertEqual(result['review_pr'],8)
        tampered=dict(files); path=next(x for x in files if x.startswith('data/universities/')); tampered[path]+=b' '
        with self.assertRaisesRegex(ValueError,'bytes changed'):native.verify_final(self.repo,self.base,tampered,self.fixture.trust)
        mixed=dict(files); mixed['data/extra.json']=b'{}'
        with self.assertRaisesRegex(ValueError,'membership'):native.verify_final(self.repo,self.base,mixed,self.fixture.trust)
    def test_owner_comments_only_and_latest(self):
        first=deepcopy(self.decision); second=deepcopy(first); second['decision']='unresolved'; second.pop('record_sha256')
        def comment(cid,user,value):return {'id':cid,'user':{'login':user},'body':native.review_comment(value)}
        comments=[comment(2,'owner',first),comment(3,'attacker',second),comment(4,'owner',second)]
        rows=native.read_reviews(comments,self.fixture.trust,8,'Q101',sha(encode(self.proposal)))
        self.assertEqual([row[1] for row in rows],[2,4]); self.assertEqual(rows[-1][0]['decision'],'unresolved')
        self.assertEqual(native.read_reviews(comments,self.fixture.trust,9,'Q101',sha(encode(self.proposal))),[])
    def test_draft_file_set_and_protocol_validation(self):
        files=native.draft_files(self.repo,self.base,[self.proposal],self.batch)
        with patch.object(native,'git',return_value=('\0'.join(files)+'\0').encode()), patch.object(native,'blob',side_effect=lambda repo,head,path,**kw:files[path]):
            manifest,rows=native.inspect_draft(self.repo,self.base,'e'*40,self.fixture.trust)
            self.assertEqual(rows['Q101'],self.proposal)
        bad=deepcopy(self.proposal); bad['research']['model']=''
        with self.assertRaises(ValueError):native.check_proposal(bad,None,self.fixture.catalog,self.fixture.catalog_hash,self.fixture.trust)
    def test_objections_require_explicit_validated_later_resolution(self):
        ident='a0062215-9668-4ec4-b233-18bf1016380e'
        objection={'type':'university-native-objection-v1','repository':'owner/repo','pr_number':8,'qid':'Q101',
                   'reviewed_head_sha':'f'*40,'proposal_sha256':sha(encode(self.proposal)), 'request_id':ident,
                   'field':'identity','category':'evidence_gap','reason':'Check source', 'created_at':'2026-11-05T00:01:00Z'}
        decision=deepcopy(self.decision); decision['request_responses']=[{'request_id':ident,'status':'addressed'}]
        comments=[{'id':1,'user':{'login':'owner'},'body':native.review_comment(objection)},
                  {'id':2,'user':{'login':'owner'},'body':native.review_comment(decision)}]
        self.assertEqual(len(native.read_requests(comments,self.fixture.trust,8,'Q101')),1)
        self.assertEqual(native.read_requests(comments,self.fixture.trust,8,'Q101',decision),[])
        comments[1]['user']['login']='outsider'
        self.assertEqual(len(native.read_requests(comments,self.fixture.trust,8,'Q101',decision)),1)

if __name__=='__main__': unittest.main()
