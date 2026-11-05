from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.agents/skills/university-curation/scripts/lib'))
from university_curation import distributed_gate as gate, native_protocol as native, distributed_transport as transport
from university_curation.attestations import sha
from university_curation.records import encode
from university_curation.preferred import fields
from university_curation.domain_refresh import compile_delta, materialize
from test_pilot_protocol import fixture

REPO='owner/repo'; QID='Q101'; PR=8; HEAD='1'*40; BASE='2'*40

class Client:
    repository=REPO
    def pull(self,number): return {'number':number,'base':{'ref':'main'},'head':{'sha':HEAD,'repo':{'full_name':REPO}},'html_url':'https://example.test/pr'}

class NativeGateTests(unittest.TestCase):
    def setUp(self):
        self.trust={'repository':REPO,'review_policy':{'id':'policy','sha256':'a'*64},'schemas':{'0.2.2':'b'*64},'model':'gpt-6.1-terra','reasoning_effort':'medium'}
        self.proposal={'qid':QID}; self.ident=str(uuid.uuid4())
        self.approval=self.decision(); self.receipt={'research':self.proposal,'review':self.approval}
        self.notes=[self.comment(1,self.approval)]; self.validation={'task_kind':'native_research','review_pr':PR,'qids':[QID],'batch_id':'batch'}
        self.client=Client(); self.patchers=[patch.object(gate,'fetch_main',return_value=BASE),patch.object(gate,'fetch_pull',return_value=HEAD),
            patch.object(gate,'trust_at',return_value=self.trust),patch.object(gate,'git',return_value=b'data/universities/aa/Q101.json\0'),
            patch.object(gate,'validate_pr',side_effect=lambda *args:self.validation),patch.object(gate,'blob',side_effect=lambda *args:encode(self.receipt)),
            patch.object(gate,'comments',side_effect=lambda *args:self.notes)]
        for p in self.patchers: p.start(); self.addCleanup(p.stop)
    def decision(self,responses=None,decision='approve'):
        return {'type':'university-native-review-v1','repository':REPO,'pr_number':PR,'qid':QID,
            'reviewed_head_sha':HEAD,'proposal_sha256':sha(encode(self.proposal)),'decision':decision,
            'reviewed_at':'2026-11-05T01:00:00Z','request_responses':responses or [],'requests':[]}
    def objection(self):
        return {'type':'university-native-objection-v1','repository':REPO,'pr_number':PR,'qid':QID,
            'reviewed_head_sha':HEAD,'proposal_sha256':sha(encode(self.proposal)),'request_id':self.ident,
            'field':'identity','category':'evidence_gap','reason':'Check source','created_at':'2026-11-05T00:00:00Z'}
    @staticmethod
    def comment(number,value,actor='owner'):
        return {'id':number,'user':{'login':actor},'body':native.review_comment(value)}
    def test_valid_native_final_has_owner_comment(self):
        result=gate.check('.',self.client,PR)
        self.assertEqual(result['state'],'success'); self.assertEqual(result['status'],'native_independently_reviewed')
    def test_wrong_pr_review_is_rejected(self):
        self.validation['review_pr']=PR+1
        with self.assertRaisesRegex(ValueError,'another PR'): gate.check('.',self.client,PR)
    def test_absent_or_outsider_comment_is_rejected(self):
        for notes in ([],[self.comment(1,self.approval,'outsider')]):
            self.notes=notes
            with self.assertRaisesRegex(ValueError,'owner-authored'): gate.check('.',self.client,PR)
    def test_latest_request_changes_cannot_match_approved_receipt(self):
        changed=self.decision(decision='request_changes'); self.notes.append(self.comment(2,changed))
        with self.assertRaisesRegex(ValueError,'latest owner-authored'): gate.check('.',self.client,PR)
    def test_later_native_objection_blocks_old_approval(self):
        self.notes.append(self.comment(2,self.objection()))
        with self.assertRaisesRegex(ValueError,'Unresolved'): gate.check('.',self.client,PR)
    def test_only_exact_validated_approval_resolves_request(self):
        other=self.decision([{'request_id':self.ident,'status':'addressed'}]); self.notes=[self.comment(1,self.objection()),self.comment(2,other),self.comment(3,self.approval)]
        with self.assertRaisesRegex(ValueError,'Unresolved'): gate.check('.',self.client,PR)
        self.receipt['review']=other; self.notes=[self.comment(1,self.objection()),self.comment(2,other)]
        self.assertEqual(gate.check('.',self.client,PR)['state'],'success')
    def test_non_native_draft_remains_pending(self):
        with patch.object(gate,'git',return_value=b'data/proposals/batch/manifest.json\0'), \
             patch.object(gate,'draft_snapshot',return_value=({'type':'university-draft-batch-v1'},{QID:{}})):
            result=gate.check('.',self.client,PR)
        self.assertEqual(result['state'],'pending'); self.assertEqual(result['status'],'awaiting_independent_signed_review')
    def test_unsigned_native_draft_routes_through_real_native_inspector(self):
        self.trust['max_schools_per_batch']=5
        path='data/proposals/batch/Q101.json'; manifest_path='data/proposals/batch/manifest.json'
        proposal=encode({'qid':QID}); manifest={'type':'university-native-draft-v1','repository':REPO,'batch_id':'batch',
            'base_commit':BASE,'seed_catalog_sha256':'c'*64,'records':[{'qid':QID,'path':path,'sha256':sha(proposal)}]}
        raw=encode(manifest); changed=(manifest_path+'\0'+path+'\0').encode()
        def read_blob(repo,ref,name): return raw if name==manifest_path else proposal
        with patch.object(gate,'git',return_value=changed), \
             patch.object(transport,'command',return_value=(manifest_path+'\n').encode()), patch.object(transport,'blob',return_value=raw), \
             patch.object(native,'git',return_value=changed), patch.object(native,'blob',side_effect=read_blob), \
             patch.object(native.legacy,'catalog_at',return_value=({QID:{}},'c'*64)), \
             patch.object(native.legacy,'baseline_at',return_value=(None,'absent')), patch.object(native,'check_proposal'):
            result=gate.check('.',self.client,PR)
        self.assertEqual(result['state'],'pending'); self.assertEqual(result['status'],'awaiting_independent_review')

    def test_native_review_business_gates_accept_unknown_model_and_reject_counts(self):
        transport,packet=fixture(); delta,_,_=compile_delta(transport,packet); seed=delta['seed']; at='2026-11-05T01:00:00Z'
        research={'qid':QID,'delta':delta,'seed':seed,'proposed_at':'2026-11-05T00:00:00Z','research':{'session':'research-session'},
            'coverage':[{'group':v['group'],'status':v['status']} for v in transport['coverage']], 'open_requests':[],'retrieval_failures':[]}
        value={'type':'university-native-review-v1','repository':REPO,'pr_number':PR,'reviewed_head_sha':HEAD,
            'policy':self.trust['review_policy'],'schema_sha256':self.trust['schemas']['0.2.2'],'decision':'approve','qid':QID,'reviewed_at':at,
            'proposal_sha256':sha(encode(research)),'facts_checked':sum(len(f['candidates']) for _,f,_ in fields(delta)),
            'contexts_checked':1+len(delta.get('locations',[])),'source_revisions_checked':len(delta['sources']),
            'requests':[],'request_responses':[],'coverage_checks':[{'group':x['group'],'status':x['status'],'reason':'Checked'} for x in transport['coverage']],
            'model':'not_reported','reasoning_effort':'not_reported','review_session':'independent-session','full_refresh':True,'inferences':[],
            'record_sha256':sha(encode(materialize(None,delta,seed,at,True)))}
        self.assertIsNotNone(native.check_decision(value,research,None,self.trust,PR)[1])
        bad=deepcopy(value); bad['facts_checked']-=1
        with self.assertRaisesRegex(ValueError,'coverage incomplete'): native.check_decision(bad,research,None,self.trust,PR)

if __name__=='__main__': unittest.main()
