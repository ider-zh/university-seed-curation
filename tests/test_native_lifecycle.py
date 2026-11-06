"""Synthetic end-to-end native pipeline with real Git, exact hashes and zero HTTP."""
from contextlib import ExitStack, redirect_stdout
from datetime import datetime, timedelta, timezone
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from university_curation import native_cli as cli, native_research, native_review, unified_publish, manager
from university_curation.attestations import load_json, sha
from university_curation.git_data import blob, commit
from university_curation.records import ROOT, encode
from test_research_schema import fixture
from test_manager import REQUEST

class NativeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.private=self.root/'.private';self.private.mkdir()
        self.addCleanup(self.tmp.cleanup);self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.git('init','-b','main');self.git('config','user.name','Test');self.git('config','user.email','test@example.invalid')
        self.git('remote','add','origin','https://github.com/owner/repo.git')
        policy=(ROOT/'docs/review-policy-v2.md').read_bytes()
        (self.root/'docs').mkdir();(self.root/'docs/review-policy-v2.md').write_bytes(policy)
        self.public={'type':manager.BACKLOG_TYPE,'tasks':{
            'Q101':{'phase':'research_pending','revision':0,'open_requests':[REQUEST],'reason':'test_recovery'},
            'Q102':{'phase':'research_pending','revision':1,'open_requests':[],'reason':'other_pending_task'}}}
        (self.root/'data/workflow').mkdir(parents=True);(self.root/manager.BACKLOG).write_bytes(encode(self.public))
        self.commit('baseline')
        self.trust={'repository':'owner/repo','schemas':{'0.2.2':sha(encode(load_json((ROOT/'schemas/university.v0.2.2.schema.json').read_bytes())))},
            'review_policy':{'id':'source-grounded-flexible-v2','sha256':sha(policy)},'max_schools_per_batch':5}
        self.catalog={q:{'queue_kind':'primary','screening_status':'needs_review','channels':['type']} for q in ['Q101','Q102']}
        def base(repo,ref):return commit(repo,ref),self.trust,self.catalog,'c'*64
        self.stack.enter_context(patch.object(native_research,'_base',side_effect=base))
        self.stack.enter_context(patch.object(unified_publish,'_base',side_effect=base))
        self.stack.enter_context(patch.object(native_review,'_base',side_effect=base))
        self.raw,self.packet=fixture();self.packet['case'].update(languages=['en'],name='Example',focus=['identity'])
        self.packet['captured_at']=(datetime.now(timezone.utc)-timedelta(seconds=2)).isoformat()
        self.packet['retrieval_failures']=[];self.packet['property_labels']={}
        self.entity={'id':'Q101','lastrevid':3,'claims':{},'sitelinks':{'enwiki':{}}}
        self.packet['sources']['s2']={'kind':'wikidata','url':'https://www.wikidata.org/w/index.php?oldid=3',
            'publisher_role':'knowledge_base','family':'wikimedia','source_qid':'Q101','revision_id':3,'retrieved_at':self.packet['captured_at']}
        self.packet['source_corpus']['s2']=[]
        parent=self
        class Cache:
            def __init__(self,*args,**kwargs):pass
            def entity(self,*args,**kwargs):return parent.entity,{}
            def entity_revision(self,*args,**kwargs):return parent.entity,{}
        def prepare(case,job,source_cache=None):
            native_research._write(Path(job)/'cases/Q101/research-packet.json',encode(parent.packet))
        self.stack.enter_context(patch.object(native_research,'Cache',Cache))
        self.stack.enter_context(patch.object(native_research,'prepare_case',side_effect=prepare))
        self.http=self.stack.enter_context(patch('university_curation.sources.urlopen',side_effect=AssertionError('Unexpected HTTP')))
    def git(self,*args):return subprocess.check_output(['git','-C',str(self.root),*args],stderr=subprocess.PIPE).decode().strip()
    def commit(self,message):
        self.git('add','docs','data');self.git('commit','-m',message);self.git('update-ref','refs/remotes/origin/main','HEAD')
    def run_cli(self,*args):
        with redirect_stdout(io.StringIO()):return cli.main(['--workspace',str(self.root),*map(str,args)])
    def research(self):
        job=self.private/'research';result=self.private/'research-result.json';result.write_bytes(encode(self.raw))
        self.run_cli('research-prepare','--qid','Q101','--job',job)
        compiled=self.run_cli('research-compile','--job',job,'--result',result,'--session','research-test','--model','test-model')
        proposal=self.private/'proposal.json'
        self.run_cli('unified-proposal','--proposal',compiled['public_proposal_path'],'--output',proposal)
        return job,proposal
    def review(self,job,proposal,name,decision="approve"):
        review=self.private/name
        self.run_cli('review-prepare','--proposal',proposal,'--research-job',job,'--job',review)
        value=load_json((review/'review-input.json').read_bytes())
        output={'qid':'Q101','decision':decision,'checks':[{'id':r['id'],'supported':True,'support_basis':'direct','reason':'Fixture supported'} for r in value['facts']+value['contexts']],
            'coverage_checks':[{'group':g,'status':'checked','reason':'Fixture checked'} for g in ['identity','geography','history','population','finance','profile']],
            'request_responses':[{'request_id':r['request_id'],'status':'addressed','reason':'Fixture resolved'} for r in value['proposal']['open_requests']], 'requests':[]}
        if decision=='request_changes': output['requests']=[{'field':'location_address','category':'evidence_gap','reason':'Fixture needs subject evidence'}]
        result=self.private/(name+'-result.json');result.write_bytes(encode(output))
        compiled=self.run_cli('review-compile','--job',review,'--result',result,'--session','review-'+name,'--model','test-model')
        return review,compiled
    def test_offline_rebinding_and_interrupted_publication_confirmation(self):
        research,proposal=self.research()
        # Main may advance while native subagents are working on another school.
        (self.root/'docs/unrelated.txt').write_text('unrelated main update');self.commit('unrelated update')
        review,compiled=self.review(research,proposal,'review-one')
        (self.root/'docs/unrelated.txt').write_text('another main update');self.commit('another unrelated update')
        bundle=self.private/'delivery'
        arguments=['unified-publish','--proposal',proposal,'--review-job',review,'--review-attempt',compiled['private_attempt'],'--batch-id','fixture-batch','--output',bundle]
        with self.assertRaisesRegex(ValueError,'stale'):self.run_cli(*arguments)
        review,compiled=self.review(research,proposal,'review-two')
        arguments[4]=review;arguments[6]=compiled['private_attempt']
        self.run_cli(*arguments)
        plan=load_json((bundle/'operations.json').read_bytes())
        self.assertEqual(plan['operations'][-1]['arguments']['branch_name'],'main')
        self.assertFalse(plan['operations'][-1]['arguments']['force'])
        self.assertNotIn('Q101',load_json((bundle/manager.BACKLOG).read_bytes())['tasks'])
        self.assertEqual(load_json((bundle/manager.BACKLOG).read_bytes())['tasks']['Q102'],self.public['tasks']['Q102'])
        # Materialize exactly the plugin bundle in the isolated test repository.
        for path in plan['files']:
            target=self.root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((bundle/path).read_bytes())
        self.git('add','data');self.git('commit','-m','fixture publication');actual=self.git('rev-parse','HEAD')
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_cli('publication-confirm','--bundle',bundle,'--published-ref',actual)
        self.git('update-ref','refs/remotes/origin/main',actual)
        verified=self.run_cli('publication-confirm','--bundle',bundle,'--published-ref',actual)
        self.assertEqual(verified['qids'],['Q101'])
        self.assertEqual(self.run_cli('publication-confirm','--bundle',bundle,'--published-ref',actual)['status'],'publication_verified')
        self.assertEqual(manager._read(self.root)['tasks']['Q101']['phase'],'completed')
        self.assertEqual(manager._read(self.root)['tasks']['Q101']['open_requests'],[])
        self.assertNotIn('Q101',[r['qid'] for r in self.run_cli('next','--limit','5')['tasks']])
        self.http.assert_not_called()
    def test_review_is_mandatory_and_rejects_tampered_snapshot(self):
        research,proposal=self.research()
        with self.assertRaisesRegex(ValueError,'count mismatch'):
            self.run_cli('unified-publish','--proposal',proposal,'--review-job',self.private/'none','--review-attempt',self.private/'none','--review-attempt',self.private/'other','--batch-id','bad','--output',self.private/'bad')
        (research/'root-entity.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'snapshot'):
            self.run_cli('review-prepare','--proposal',proposal,'--research-job',research,'--job',self.private/'tampered-review')
        self.http.assert_not_called()

    def test_rejection_checkpoint_is_portable_and_cannot_publish_canonical_data(self):
        research,proposal=self.research()
        review,compiled=self.review(research,proposal,'rejected','request_changes')
        self.assertTrue(compiled['checkpoint_required'])
        with self.assertRaisesRegex(ValueError,'current approved'):
            self.run_cli('unified-publish','--proposal',proposal,'--review-job',review,'--review-attempt',compiled['private_attempt'],'--batch-id','rejected','--output',self.private/'rejected-bundle')
        checkpoint=self.private/'checkpoint'
        self.run_cli('checkpoint','--output',checkpoint)
        plan=load_json((checkpoint/'operations.json').read_bytes())
        self.assertEqual(set(plan['files']),{manager.BACKLOG})
        value=load_json((checkpoint/manager.BACKLOG).read_bytes())
        self.assertEqual(value['tasks']['Q101']['phase'],'revision_requested')
        self.assertEqual(len(value['tasks']['Q101']['open_requests']),2)
        self.assertEqual(value['tasks']['Q101']['open_requests'][0],REQUEST)
        (self.root/manager.BACKLOG).write_bytes((checkpoint/manager.BACKLOG).read_bytes());self.commit('checkpoint questions')
        manager.state_path(self.root).unlink()
        rows=self.run_cli('next','--limit','5')['tasks']
        self.assertEqual(rows[0]['action'],'revise');self.assertEqual(len(rows[0]['open_requests']),2)

    def test_an_older_approval_cannot_override_a_later_unresolved_review(self):
        research,proposal=self.research()
        first,approved=self.review(research,proposal,'approved')
        self.review(research,proposal,'later-unresolved','unresolved')
        self.assertEqual(manager._read(self.root)['tasks']['Q101']['phase'],'unresolved')
        with self.assertRaisesRegex(ValueError,'current approved'):
            self.run_cli('unified-publish','--proposal',proposal,'--review-job',first,'--review-attempt',approved['private_attempt'],'--batch-id','stale','--output',self.private/'stale')

    def test_review_result_cannot_change_after_compilation(self):
        research,proposal=self.research()
        review,compiled=self.review(research,proposal,'hash-checked')
        (Path(compiled['private_attempt'])/'native-result.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'changed after'):
            self.run_cli('unified-publish','--proposal',proposal,'--review-job',review,'--review-attempt',compiled['private_attempt'],'--batch-id','changed-result','--output',self.private/'changed-result')
