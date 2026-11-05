from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.agents/skills/university-curation/scripts/lib'))
from university_curation import native_review as native, distributed_jobs as jobs
from university_curation.attestations import sha
from university_curation.records import ROOT, encode
from university_curation.pilot_protocol import GROUPS
from test_pilot_protocol import fixture

BASE='a'*40; POLICY='test native policy\n'

class NativeReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.private=Path(self.temp.name)/'.private'; self.private.mkdir()
        raw,packet=fixture(); packet['case'].update({'languages':['en']})
        captured=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat(); packet['captured_at']=captured
        packet['sources']['s2']={'kind':'wikidata','url':'https://www.wikidata.org/w/index.php?oldid=3',
            'publisher_role':'knowledge_base','family':'wikimedia','source_qid':'Q101','revision_id':3,'retrieved_at':captured}
        self.root={'id':'Q101','lastrevid':3,'claims':{}}
        packet['source_corpus']['s2']=jobs.wikidata_corpus(self.root,{},['en'],True); packet['retrieval_failures']=[]
        delta,_,_=jobs.compile_delta(raw,packet)
        seed={'import_id':'seed-'+'c'*16,'screening_status':'needs_review','channels':['type']}; delta['seed']=seed
        at=(datetime.now(timezone.utc)-timedelta(seconds=30)).isoformat()
        self.proposal={'type':'university-proposal-v1','review_status':'unreviewed','qid':'Q101','seed':seed,'baseline_sha256':'absent',
            'delta':delta,'candidate':materialize(None,delta,seed,at),'proposed_at':at,
            'coverage':[{'group':r['group'],'status':r['status']} for r in raw['coverage']],'retrieval_failures':[],'open_requests':[],
            'research':{'model':'not_reported','reasoning_effort':'not_reported','session':'research-session',
                        'prompt_sha256':'d'*64,'schema_sha256':'e'*64}}
        self.packet=packet; self.proposal_file=self.private/'proposal.json'; self.proposal_file.write_bytes(encode(self.proposal))
        self.trust={'repository':'owner/repo','schemas':{'0.2.2':'b'*64},'review_policy':{'sha256':sha(POLICY.encode())}}
        catalog={'Q101':{'queue_kind':'primary','screening_status':'needs_review','channels':['type']}}
        patches=[patch.object(native,'_base',return_value=(BASE,self.trust,catalog,'c'*64)),patch.object(native,'_origin'),
                 patch.object(native,'baseline_at',return_value=(None,'absent')),patch.object(native,'blob',return_value=POLICY.encode())]
        parent=self
        class Cache:
            def __init__(self,path,**kwargs): self.path=Path(path)
            def entity_revision(self,qid,revision,refresh=False): return parent.root,{}
            def wikipedia_get(self,lang,oldid,refresh=False): return {'page_id':1,'source_url':packet['sources']['s1']['url']}
        patches += [patch.object(jobs,'Cache',Cache),patch.object(jobs,'property_labels',return_value={}),
                    patch.object(jobs,'wikipedia_corpus',return_value=packet['source_corpus']['s1'])]
        self.patches=patches
        for p in patches: p.start()
    def tearDown(self): patch.stopall(); self.temp.cleanup()
    def result_for(self,job):
        value=native.load_json((job/'review-input.json').read_bytes())
        return {'qid':'Q101','decision':'approve',
            'checks':[{'id':r['id'],'supported':True,'support_basis':'direct','reason':'Supported'} for r in value['facts']+value['contexts']],
            'coverage_checks':[{'group':g,'status':'checked','reason':'Checked'} for g in GROUPS],
            'request_responses':[],'requests':[]}
    def test_native_review_replays_sources_and_compiles_without_research_private_data(self):
        job=self.private/'review-job'; prepared=native.prepare(ROOT,self.proposal_file,job)
        self.assertTrue(Path(prepared['prompt_path']).exists())
        result=self.private/'result.json'; result.write_bytes(encode(self.result_for(job)))
        compiled=native.compile(ROOT,job,result,'review-session','not_reported',effort='not_reported')
        self.assertEqual(compiled['decision'],'approve'); self.assertFalse(compiled['provider_trace_verified'])
        self.assertEqual(compiled['public_verdict']['model'],'not_reported'); self.assertTrue(compiled['public_verdict']['full_refresh'])
        self.assertTrue(Path(compiled['final_record_path']).exists())
    def test_unaddressed_request_and_missing_fact_cannot_be_approved(self):
        self.proposal['open_requests']=[{'request_id':'req-1','field':'identity','category':'evidence_gap',
            'reason':'Check the institution identity','reviewed_head_sha':'a'*40}]
        self.proposal_file.write_bytes(encode(self.proposal))
        job=self.private/'review-job'; native.prepare(ROOT,self.proposal_file,job)
        value=self.result_for(job); value['request_responses']=[{'request_id':'req-1','status':'not_addressed','reason':'Still unclear'}]
        result=self.private/'result.json'; result.write_bytes(encode(value))
        with self.assertRaisesRegex(ValueError,'contradictory approval'): native.compile(ROOT,job,result,'review-session','not_reported')
        value['request_responses'][0]['status']='addressed'; value['checks'].pop(); result.write_bytes(encode(value))
        with self.assertRaisesRegex(ValueError,'coverage incomplete'): native.compile(ROOT,job,result,'review-session','not_reported')

    def test_reused_session_and_changed_input_fail_closed(self):
        job=self.private/'review-job'; native.prepare(ROOT,self.proposal_file,job)
        result=self.private/'result.json'; result.write_bytes(encode(self.result_for(job)))
        with self.assertRaisesRegex(ValueError,'distinct'): native.compile(ROOT,job,result,'research-session','not_reported')
        (job/'review-input.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'input changed'): native.compile(ROOT,job,result,'review-session','not_reported')
        self.assertEqual(len(list((job/'compile-attempts').glob('*/native-result.json'))),2)

from university_curation.domain_refresh import materialize
if __name__=='__main__': unittest.main()
