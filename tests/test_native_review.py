from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.agents/skills/university-curation/scripts/lib'))
from university_curation import native_review as native, research_contract as jobs
from university_curation.integrity import sha
from university_curation.records import ROOT, encode
from university_curation.research_schema import GROUPS
from test_research_schema import fixture

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
        delta,_,_=compile_delta(raw,packet)
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
        research=self.private/'research-snapshot'; (research/'cases/Q101').mkdir(parents=True)
        (research/'cases/Q101/research-packet.json').write_bytes(encode(packet))
        (research/'root-entity.json').write_bytes(encode(self.root))
        (research/'job.json').write_bytes(encode({'qid':'Q101','base_commit':BASE,
            'catalog_sha256':'c'*64,'schema_sha256':'b'*64,'review_policy_sha256':sha(POLICY.encode()),'baseline_sha256':'absent',
            'packet_sha256':sha(encode(packet)),'root_entity_sha256':sha(encode(self.root))}))
        self.research_job=research
        self.patches=patches
        for p in patches: p.start()
    def tearDown(self): patch.stopall(); self.temp.cleanup()
    def result_for(self,job):
        value=native.load_json((job/'review-input.json').read_bytes())
        return {'qid':'Q101','decision':'approve',
            'checks':[{'id':r['id'],'supported':True,'support_basis':'direct','reason':'Supported'} for r in value['facts']+value['contexts']],
            'coverage_checks':[{'group':g,'status':'checked','reason':'Checked'} for g in GROUPS],
            'request_responses':[],'requests':[]}
    def test_offline_review_compiles_without_network_or_research_traces(self):
        job=self.private/'review-job'; prepared=native.prepare(ROOT,self.proposal_file,job,research_job=self.research_job)
        self.assertTrue(Path(prepared['prompt_path']).exists())
        result=self.private/'result.json'; result.write_bytes(encode(self.result_for(job)))
        compiled=native.compile(ROOT,job,result,'review-session','not_reported',effort='not_reported')
        self.assertEqual(compiled['decision'],'approve'); self.assertFalse(compiled['provider_trace_verified'])
        self.assertEqual(compiled['public_verdict']['model'],'not_reported'); self.assertTrue(compiled['public_verdict']['full_refresh'])
        self.assertTrue(Path(compiled['final_record_path']).exists())
    def test_unaddressed_request_and_missing_fact_cannot_be_approved(self):
        self.proposal['open_requests']=[{'request_id':'req-1','field':'identity','category':'evidence_gap',
            'reason':'Check the institution identity','reviewed_proposal_sha256':'a'*64}]
        self.proposal_file.write_bytes(encode(self.proposal))
        job=self.private/'review-job'; native.prepare(ROOT,self.proposal_file,job,research_job=self.research_job)
        value=self.result_for(job); value['request_responses']=[{'request_id':'req-1','status':'not_addressed','reason':'Still unclear'}]
        result=self.private/'result.json'; result.write_bytes(encode(value))
        with self.assertRaisesRegex(ValueError,'contradictory approval'): native.compile(ROOT,job,result,'review-session','not_reported')
        value['request_responses'][0]['status']='addressed'; value['checks'].pop(); result.write_bytes(encode(value))
        with self.assertRaisesRegex(ValueError,'coverage incomplete'): native.compile(ROOT,job,result,'review-session','not_reported')

    def test_reused_session_and_changed_input_fail_closed(self):
        job=self.private/'review-job'; native.prepare(ROOT,self.proposal_file,job,research_job=self.research_job)
        result=self.private/'result.json'; result.write_bytes(encode(self.result_for(job)))
        with self.assertRaisesRegex(ValueError,'distinct'): native.compile(ROOT,job,result,'research-session','not_reported')
        (job/'review-input.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'input changed'): native.compile(ROOT,job,result,'review-session','not_reported')
        self.assertEqual(len(list((job/'compile-attempts').glob('*/native-result.json'))),2)

    def test_secondary_prior_request_is_preserved_as_waived(self):
        self.proposal['open_requests']=[{'request_id':'req-secondary','field':'leadership.chair.preferred',
            'category':'scope_conflict','reason':'Recheck historical appointment', 'reviewed_proposal_sha256':'a'*64}]
        self.proposal_file.write_bytes(encode(self.proposal))
        job=self.private/'review-secondary'; native.prepare(ROOT,self.proposal_file,job,research_job=self.research_job)
        value=native.load_json((job/'review-input.json').read_bytes())
        self.assertEqual(value['waived_request_ids'],['req-secondary'])
        result=self.private/'result-secondary.json'; result.write_bytes(encode(self.result_for(job)))
        compiled=native.compile(ROOT,job,result,'review-session','not_reported')
        self.assertEqual(compiled['public_verdict']['waived_requests'][0]['request_id'],'req-secondary')
        self.assertEqual(compiled['public_verdict']['review_scope']['version'],'core-review-v3')

    def test_secondary_fact_needs_no_model_check(self):
        from copy import deepcopy
        from university_curation.preferred import recompute
        self.proposal['delta']['profile']={'motto':deepcopy(self.proposal['delta']['identity']['names']['en'])}
        for c in self.proposal['delta']['profile']['motto']['candidates']:
            c['value']={'text':c['value'],'language':'en'}
        self.proposal['delta']=recompute(self.proposal['delta'])
        self.proposal['candidate']=materialize(None,self.proposal['delta'],self.proposal['seed'],self.proposal['proposed_at'])
        self.proposal_file.write_bytes(encode(self.proposal))
        job=self.private/'review-motto'; native.prepare(ROOT,self.proposal_file,job,research_job=self.research_job)
        value=native.load_json((job/'review-input.json').read_bytes())
        self.assertFalse(any(r['field']=='$.profile.motto' for r in value['facts']))
        result=self.private/'result-motto.json'; result.write_bytes(encode(self.result_for(job)))
        compiled=native.compile(ROOT,job,result,'review-session','not_reported')
        self.assertIn('$.profile.motto:c1',compiled['public_verdict']['review_scope']['not_independently_reviewed_ids'])

from university_curation.domain_refresh import materialize, compile_delta
if __name__=='__main__': unittest.main()
