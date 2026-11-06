from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.agents/skills/university-curation/scripts/lib'))
from university_curation import native_research as native
from university_curation.integrity import sha
from university_curation.records import ROOT, encode
from test_research_schema import fixture

BASE='a'*40; POLICY='test native policy\n'

class NativeResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.private=Path(self.tmp.name)/'.private'; self.private.mkdir()
        self.transport,self.packet=fixture()
        self.packet['captured_at']=(datetime.now(timezone.utc)-timedelta(seconds=10)).isoformat()
        self.packet['case'].update({'languages':['en'],'name':'Example','focus':['identity']})
        self.root={'id':'Q101','lastrevid':3,'claims':{},'sitelinks':{'enwiki':{}}}
        self.packet['sources']['s2']={'kind':'wikidata','url':'https://www.wikidata.org/w/index.php?oldid=3',
            'publisher_role':'knowledge_base','family':'wikimedia','source_qid':'Q101','revision_id':3,'retrieved_at':self.packet['captured_at']}
        self.packet['source_corpus']['s2']=[]; self.packet['retrieval_failures']=[]; self.packet['property_labels']={}
        self.trust={'repository':'owner/repo','schemas':{'0.2.2':'b'*64},'review_policy':{'sha256':sha(POLICY.encode())}}
        self.catalog={'Q101':{'queue_kind':'primary','screening_status':'needs_review','channels':['type']}}
        self.patches=[patch.object(native,'_base',return_value=(BASE,self.trust,self.catalog,'c'*64)),patch.object(native,'_origin'),
            patch.object(native,'baseline_at',return_value=(None,'absent')),patch.object(native,'blob',return_value=POLICY.encode())]
        for p in self.patches: p.start()
        parent=self
        class Cache:
            def __init__(self,path,**kw): self.path=Path(path)
            def entity(self,qid): return parent.root,{}
            def entity_revision(self,qid,revision): return parent.root,{}
        self.cache=patch.object(native,'Cache',Cache); self.cache.start()
        def prepare(case,job,source_cache=None): native._write(Path(job)/'cases/Q101/research-packet.json',encode(parent.packet))
        self.source=patch.object(native,'prepare_case',side_effect=prepare); self.source.start()
    def tearDown(self): patch.stopall(); self.tmp.cleanup()
    def test_doctor_needs_no_key_or_host_provider(self):
        result=native.doctor(ROOT)
        self.assertEqual(result['status'],'local_ready'); self.assertEqual(result['native_subagents'],'not_verified_locally')
        self.assertEqual(result['signing_key'],'not_required')
    def test_native_prepare_and_compile_without_provider_or_key(self):
        job=self.private/'native-job'; result_path=self.private/'native-result.json'; result_path.write_bytes(encode(self.transport))
        prepared=native.prepare(ROOT,'Q101',job)
        self.assertTrue(Path(prepared['prompt_path']).is_file()); self.assertTrue(Path(prepared['schema_path']).is_file())
        compiled=native.compile(ROOT,job,result_path,'native-session-1','gpt-6.1-terra')
        self.assertEqual(compiled['status'],'compiled'); self.assertFalse(compiled['provider_trace_verified'])
        self.assertEqual(compiled['session_and_model'],'caller_reported')
        self.assertEqual(compiled['public_proposal']['qid'],'Q101'); self.assertEqual(compiled['public_proposal']['review_status'],'unreviewed')
        self.assertTrue(Path(compiled['public_proposal_path']).is_file())
        unknown=native.compile(ROOT,job,result_path,'native-session-2','not_reported',effort='not_reported')
        self.assertEqual(unknown['public_proposal']['research']['model'],'not_reported')
        self.assertEqual(unknown['public_proposal']['research']['reasoning_effort'],'not_reported')
    def test_changed_prepared_input_or_invalid_native_json_fails_and_preserves_attempt(self):
        job=self.private/'native-job'; result_path=self.private/'native-result.json'; result_path.write_bytes(encode(self.transport))
        native.prepare(ROOT,'Q101',job)
        (job/'prompt.txt').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'input changed'): native.compile(ROOT,job,result_path,'session','gpt-6.1-terra')
        self.assertEqual(len(list((job/'compile-attempts').glob('*/native-result.json'))),1)

if __name__=='__main__': unittest.main()
