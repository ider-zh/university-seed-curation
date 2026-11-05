from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.agents/skills/university-curation/scripts/lib'))
from university_curation import distributed_protocol as protocol
from university_curation.attestations import sha, sign, verify
from university_curation.domain_refresh import compile_delta, materialize
from university_curation.preferred import fields
from university_curation.records import encode
from university_curation.pr_export import record_relative
from test_pilot_protocol import fixture


class DistributedProtocolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); private = Path(self.tmp.name) / '.private'; private.mkdir()
        self.keys = {}; self.trust = {'repository':'owner/repo', 'model':'gpt-6.1-terra', 'reasoning_effort':'medium',
            'schemas':{'0.2.2':'a'*64}, 'review_policy':{'id':'policy', 'sha256':'b'*64}, 'max_schools_per_batch':5, 'keys':{}}
        for role in ('research','review','legacy_coordinator'):
            key = Ed25519PrivateKey.generate(); raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
            key_id = 'review-' + sha(raw)[:16]; path = private / (role + '.pem')
            path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
            self.keys[role] = path
            self.trust['keys'][key_id] = {'algorithm':'Ed25519','public_key_hex':raw.hex(),'status':'active','roles':[role]}
        source, packet = fixture(); delta, _, _ = compile_delta(source, packet)
        self.catalog_hash = 'c'*64; self.catalog = {'Q101':{'qid':'Q101','queue_kind':'primary','screening_status':'included','channels':['type']}}
        seed = protocol.seed_metadata(self.catalog['Q101'], self.catalog_hash); delta['seed'] = seed
        at='2026-11-05T00:01:00Z'; self.reviewed_at='2026-11-05T00:02:00Z'
        self.proposal = {'type':'university-proposal-v1','review_status':'unreviewed','qid':'Q101','seed':seed,'baseline_sha256':'absent',
            'delta':delta, 'candidate':materialize(None,delta,seed,at,False), 'proposed_at':at,
            'coverage':[{'group':r['group'],'status':r['status']} for r in source['coverage']], 'retrieval_failures':[], 'open_requests':[],
            'research':{'model':self.trust['model'],'reasoning_effort':'medium','session':'research-session','prompt_sha256':'d'*64,'schema_sha256':'e'*64}}
        self.proposal = protocol.attach_transport(self.proposal, self.trust['repository'], 'f'*40, self.catalog_hash, self.trust)
        self.research = self.signed(self.proposal, 'research')
        record = materialize(None,delta,seed,self.reviewed_at,True)
        self.decision = {'type':'university-review-decision-v1','repository':'owner/repo','pr_number':8,'reviewed_head_sha':'f'*40,
            'policy':self.trust['review_policy'],'schema_sha256':self.trust['schemas']['0.2.2'],'decision':'approve','qid':'Q101',
            'reviewed_at':self.reviewed_at,'proposal_sha256':sha(encode(self.proposal)),
            'facts_checked':sum(len(f['candidates']) for _,f,_ in fields(delta)),
            'contexts_checked':1+len(delta.get('locations',[]))+len(delta.get('history',{}).get('milestones',[]))+len(delta.get('related_entities',{})),
            'source_revisions_checked':len(delta['sources']),'requests':[],'request_responses':[],
            'coverage_checks':deepcopy(self.proposal['coverage']),'model':self.trust['model'],'reasoning_effort':'medium',
            'review_session':'review-session','full_refresh':True,'inferences':[],'record_sha256':sha(encode(record))}
        self.record = record
    def tearDown(self): self.tmp.cleanup()
    def signed(self, payload, role): return sign(payload, self.keys[role], self.trust, role=role)
    def test_role_separation(self):
        research = self.signed({'example':'x'}, 'research')
        for role in ('review','legacy_coordinator'):
            with self.assertRaises(ValueError): sign({'x':1}, self.keys['research'], self.trust, role=role)
            with self.assertRaises(ValueError): verify(research, self.trust, role=role)
        self.assertEqual(verify(research,self.trust,role='research'), {'example':'x'})
    def test_exact_proposal_independent_review_and_cross_pr(self):
        protocol.check_proposal(self.proposal,None,self.catalog,self.catalog_hash,self.trust)
        review=self.signed(self.decision,'review')
        value, record=protocol.check_decision(review,self.research,None,self.trust,pr_number=8)
        self.assertEqual(value['decision'],'approve'); self.assertEqual(encode(record),encode(self.record))
        with self.assertRaisesRegex(ValueError,'another PR'): protocol.check_decision(review,self.research,None,self.trust,pr_number=9)
        changed=deepcopy(self.proposal); changed['research']['prompt_sha256']='9'*64
        with self.assertRaisesRegex(ValueError,'exact proposal'): protocol.check_decision(review,self.signed(changed,'research'),None,self.trust)
        same=deepcopy(self.decision); same['review_session']='research-session'
        with self.assertRaisesRegex(ValueError,'Independent'): protocol.check_decision(self.signed(same,'review'),self.research,None,self.trust)
        wrong_record=deepcopy(self.decision); wrong_record['record_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'record hash'): protocol.check_decision(self.signed(wrong_record,'review'),self.research,None,self.trust)
        # Even a misconfigured dual-role key cannot self-review.
        self.trust['keys'][self.research['key_id']]['roles']=['research','review']
        self_review=sign(self.decision,self.keys['research'],self.trust,role='review')
        with self.assertRaisesRegex(ValueError,'signing identities'): protocol.check_decision(self_review,self.research,None,self.trust)
        with self.assertRaisesRegex(ValueError,'baseline'): protocol.check_proposal(self.proposal,{'qid':'Q101'},self.catalog,self.catalog_hash,self.trust)
    def test_latest_review_order_and_binding(self):
        first=self.signed(self.decision,'review'); newer=deepcopy(self.decision); newer['decision']='unresolved'; newer.pop('record_sha256')
        second=self.signed(newer,'review')
        comments=[{'id':12,'body':protocol.signed_comment(second),'html_url':'new'}, {'id':5,'body':protocol.signed_comment(first),'html_url':'old'}, {'id':15,'body':'noise'}]
        rows=protocol.read_reviews(comments,self.trust,8,'Q101',sha(encode(self.proposal)))
        self.assertEqual([row[1] for row in rows],[5,12]); self.assertEqual(rows[-1][0],second)
        self.assertEqual(protocol.read_reviews(comments,self.trust,9,'Q101',sha(encode(self.proposal))),[])
    def test_final_receipt_path_and_bytes(self):
        batch='batch-1'; base='f'*40; p=record_relative('Q101'); receipt_path='data/reviews/'+batch+'/Q101.json'; name='data/batches/'+batch+'.json'
        receipt={'type':'university-distributed-receipt-v1','research':self.research,'review':self.signed(self.decision,'review')}
        files={p:encode(self.record),receipt_path:encode(receipt)}
        row={'qid':'Q101','record_path':p,'receipt_path':receipt_path,'record_sha256':sha(files[p]),'receipt_sha256':sha(files[receipt_path])}
        manifest={'type':'university-final-batch-v1','repository':'owner/repo','batch_id':batch,'base_commit':base,'seed_catalog_sha256':self.catalog_hash,'records':[row]}
        files[name]=encode(self.signed(manifest,'research'))
        with patch.object(protocol,'catalog_at',return_value=(self.catalog,self.catalog_hash)), patch.object(protocol,'baseline_at',return_value=(None,'absent')), \
             patch.object(protocol,'blob',return_value=None), patch('university_curation.pr_export.no_legacy_duplicate'):
            result=protocol.verify_final('repo',base,files,self.trust); self.assertEqual(result['review_pr'],8)
            tampered=dict(files); tampered[p]=files[p]+b' '
            with self.assertRaisesRegex(ValueError,'bytes changed'): protocol.verify_final('repo',base,tampered,self.trust)
            wrong=deepcopy(manifest); wrong['records'][0]['receipt_path']='data/reviews/wrong/Q101.json'
            tampered=dict(files); tampered[name]=encode(self.signed(wrong,'research'))
            with self.assertRaisesRegex(ValueError,'path mismatch'): protocol.verify_final('repo',base,tampered,self.trust)

if __name__ == '__main__': unittest.main()
