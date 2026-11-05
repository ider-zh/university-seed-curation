from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.agents/skills/university-curation/scripts/lib'))
from university_curation import distributed_jobs as jobs
from university_curation.records import ROOT
from university_curation.pilot_protocol import GROUPS
from test_pilot_protocol import fixture


class Budget:
    def __init__(self): self.cancel_event=threading.Event()
    def __enter__(self): return self
    def __exit__(self,*args): pass

class DistributedTests(unittest.TestCase):
    def test_separate_roles_exchange_public_proposal_and_review_exact_sources(self):
        proposal,packet=fixture(); packet['case'].update({'languages':['en'],'name':'Example','focus':['identity']})
        packet['sources']['s2']={'kind':'wikidata','url':'https://www.wikidata.org/w/index.php?oldid=3',
            'publisher_role':'knowledge_base','family':'wikimedia','source_qid':'Q101','revision_id':3,'retrieved_at':'2026-11-05T00:00:00Z'}
        entity={'id':'Q101','lastrevid':3,'claims':{},'sitelinks':{'enwiki':{}}}
        packet['source_corpus']['s2']=jobs.wikidata_corpus(entity,{},['en'],True)
        packet['property_labels']={}; packet['retrieval_failures']=[]
        class Cache:
            def __init__(self,path,**kwargs): self.path=Path(path)
            def entity(self,qid): return entity,{}
            def entity_revision(self,qid,revision,**kw): return entity,{}
            def wikipedia_get(self,lang,oldid,**kw): return {'page_id':1,'source_url':packet['sources']['s1']['url']}
        def prepare(case,root,source_cache=None): jobs.save(Path(root)/'cases/Q101/research-packet.json',packet)
        calls={}; response_status=['addressed']
        def run(prompt,schema,directory,repo,**kwargs):
            directory=Path(directory); directory.mkdir()
            (directory/'prompt.txt').write_text(prompt,encoding='utf-8'); jobs.save(directory/'output.schema.json',schema)
            if directory.name=='research-call': result=deepcopy(proposal); session='research'; at='2026-11-05T00:01:00Z'
            else:
                value=jobs.read(directory.parent/'review-input.json'); session='review'; at='2026-11-05T00:02:00Z'
                result={'qid':'Q101','decision':'approve',
                    'checks':[{'id':x['id'],'supported':True,'support_basis':'direct','reason':'Supported'} for x in value['facts']+value['contexts']],
                    'coverage_checks':[{'group':r['group'],'status':r['status'],'reason':'Checked'} for r in value['proposal']['coverage']],
                    'request_responses':[{'request_id':r['request_id'],'status':response_status[0],'reason':'Resolved'} for r in value['proposal']['open_requests']],
                    'requests':[]}
            meta={'session_ids':[session],'ended_at':at,'prompt_sha256':jobs.sha(prompt.encode()),'schema_sha256':jobs.sha((directory/'output.schema.json').read_bytes())}
            calls[str(directory)]=(result,meta); return result,meta
        def audit(directory,trust): return calls[str(directory)]
        feedback={'open_requests':[{'request_id':'abc','field':'identity','category':'evidence_gap','reason':'Check source','reviewed_head_sha':'a'*40}]}
        seed={'import_id':'catalog','screening_status':'needs_review','channels':['primary']}
        with tempfile.TemporaryDirectory() as tmp:
            private=Path(tmp)/'.private'; private.mkdir()
            with patch.object(jobs,'Cache',Cache), patch.object(jobs,'prepare_case',prepare), patch.object(jobs,'property_labels',return_value={}), \
                 patch.object(jobs,'wikipedia_corpus',return_value=packet['source_corpus']['s1']), patch.object(jobs.codex_provider,'run',side_effect=run), \
                 patch.object(jobs,'provider',side_effect=audit):
                public,research_path=jobs.research('Q101',seed,None,private/'research',private/'source-cache',ROOT,Budget(),feedback)
                self.assertEqual(public['review_status'],'unreviewed')
                self.assertNotIn('source_corpus',str(public)); self.assertNotIn(str(private),str(public))
                self.assertEqual(public['open_requests'][0]['request_id'],'abc')
                # Remove access to Research artifacts: Review consumes only the public proposal.
                import shutil
                shutil.rmtree(research_path)
                verdict,record=jobs.review(public,None,private/'review',ROOT,Budget())
                self.assertEqual(verdict['decision'],'approve'); self.assertTrue(verdict['full_refresh'])
                self.assertEqual(verdict['request_responses'][0]['status'],'addressed')
                self.assertEqual(record['update_datetime'],'2026-11-05T00:02:00Z')
                self.assertEqual(record,jobs.finalize_record(public,None,verdict['reviewed_at'],True))
                disputed=deepcopy(public)
                next(r for r in disputed['coverage'] if r['group']=='geography')['status']='disputed'
                disputed['delta']['coverage']['geography']['status']='disputed'
                disputed['candidate']=jobs.materialize(None,disputed['delta'],seed,disputed['proposed_at'],False)
                dispute_verdict,dispute_record=jobs.review(disputed,None,private/'disputed',ROOT,Budget())
                self.assertTrue(dispute_verdict['full_refresh'])
                self.assertEqual(dispute_record['coverage']['geography']['status'],'disputed')
                self.assertIn('update_datetime',dispute_record)
                response_status[0]='not_addressed'
                with self.assertRaisesRegex(ValueError,'contradictory approval'):
                    jobs.review(disputed,None,private/'unresolved',ROOT,Budget())
                response_status[0]='addressed'
                changed=deepcopy(public); changed['candidate']['qid']='Q1'
                with self.assertRaisesRegex(ValueError,'candidate differs'):
                    jobs.review(changed,None,private/'rejected',ROOT,Budget())

    def test_review_reconstructs_root_p625_from_independent_entity(self):
        transport,packet=fixture()
        packet['sources']['s2']={'kind':'wikidata','url':'https://www.wikidata.org/w/index.php?oldid=3',
            'publisher_role':'knowledge_base','family':'wikimedia','source_qid':'Q101','revision_id':3,'retrieved_at':'2026-11-05T00:00:00Z'}
        root={'id':'Q101','lastrevid':3,'claims':{'P625':[{'id':'Q101$abc','rank':'normal',
            'mainsnak':{'property':'P625','datatype':'globe-coordinate','snaktype':'value',
                'datavalue':{'type':'globecoordinate','value':{'latitude':0,'longitude':10,'precision':0.01,'globe':'http://www.wikidata.org/entity/Q2'}}}}]}}
        packet['source_corpus']['s2']=jobs.wikidata_corpus(root,{},['en'],True)
        packet=jobs.coordinate_aliases(packet)
        delta,_,_=jobs.compile_delta(transport,packet)
        seed={'import_id':'catalog','screening_status':'needs_review','channels':['primary']}; delta['seed']=seed
        delta,point=jobs.coordinate_delta(delta,root,packet)
        at='2026-11-05T00:01:00Z'
        proposal={'type':'university-proposal-v1','review_status':'unreviewed','qid':'Q101','seed':seed,'baseline_sha256':'absent',
            'delta':delta,'candidate':jobs.materialize(None,delta,seed,at,False),'proposed_at':at,
            'coverage':[{'group':x['group'],'status':x['status']} for x in transport['coverage']], 'retrieval_failures':[], 'open_requests':[],
            'research':{'model':jobs.MODEL,'reasoning_effort':jobs.EFFORT,'session':'research','prompt_sha256':'a'*64,'schema_sha256':'b'*64}}
        self.assertEqual(jobs._verify_proposal(proposal,None,packet,root),point)
        changed=deepcopy(root); changed['claims']['P625'][0]['mainsnak']['datavalue']['value']['latitude']=1
        with self.assertRaises(ValueError): jobs._verify_proposal(proposal,None,packet,changed)

    def test_no_wikipedia_sitelink_does_not_invent_language(self):
        self.assertEqual(jobs.source_languages({'sitelinks':{},'claims':{}}),[])

    def test_public_reasons_allow_sources_and_locale_but_not_secrets(self):
        self.assertEqual(jobs._safe_reason('See https://www.wikidata.org/wiki/Q101 and sk-SK locale.'),
                         'See https://www.wikidata.org/wiki/Q101 and sk-SK locale.')
        for text in ('See .private/source.json', 'Token sk-abcdefghijklmnop1234', 'C:\\private\\record.json',
                     'Token ghp_abcdefghijklmnop1234', 'Token github_pat_abcdefghijklmnop1234'):
            with self.assertRaises(ValueError): jobs._safe_reason(text)

    def test_request_feedback_is_bounded_and_root_coordinates_reserved(self):
        with self.assertRaises(ValueError): jobs._open_requests({'open_requests':[{'request_id':'x'}]})
        proposal,packet=fixture(); packet['sources']['s2']={'kind':'wikidata','source_qid':'Q101'}
        packet['source_corpus']['s2']=[{'locator':'claim:P625:0','text':'{"statement_id":"Q101$abc"}'}]
        fact=deepcopy(proposal['facts'][0]); fact['field']='location.coordinates'; fact['evidence']=[{'source_ref':'s2','locator':'statement:Q101$abc','original_text':'x'}]
        proposal['facts'].append(fact)
        with self.assertRaisesRegex(ValueError,'script-owned'): jobs.guard_root_coordinates(proposal,packet)

if __name__=='__main__': unittest.main()
