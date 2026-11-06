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
from university_curation.integrity import load_json, sha
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
            native_research._write(Path(job)/'cases'/case['qid']/'research-packet.json',encode(parent.packet))
        self.stack.enter_context(patch.object(native_research,'Cache',Cache))
        self.stack.enter_context(patch.object(native_research,'prepare_case',side_effect=prepare))
        self.http=self.stack.enter_context(patch('university_curation.sources.urlopen',side_effect=AssertionError('Unexpected HTTP')))
    def git(self,*args):return subprocess.check_output(['git','-C',str(self.root),*args],stderr=subprocess.PIPE).decode().strip()
    def commit(self,message):
        self.git('add','docs','data');self.git('commit','-m',message);self.git('update-ref','refs/remotes/origin/main','HEAD')
    def run_cli(self,*args):
        with redirect_stdout(io.StringIO()):return cli.main(['--workspace',str(self.root),*map(str,args)])
    def research(self,entity='Q101'):
        self.raw['qid']=entity;self.packet['case']['qid']=entity;self.entity['id']=entity
        self.packet['sources']['s2']['source_qid']=entity
        job=self.private/('research-'+entity);result=self.private/('research-result-'+entity+'.json');result.write_bytes(encode(self.raw))
        self.run_cli('research-prepare','--qid',entity,'--job',job)
        compiled=self.run_cli('research-compile','--job',job,'--result',result,'--session','research-'+entity,'--model','test-model')
        proposal=self.private/('proposal-'+entity+'.json')
        self.run_cli('unified-proposal','--proposal',compiled['public_proposal_path'],'--output',proposal)
        return job,proposal
    def review(self,job,proposal,name,decision="approve",session=None):
        review=self.private/name
        self.run_cli('review-prepare','--proposal',proposal,'--research-job',job,'--job',review)
        return self.compile_review(review,name,decision,session)
    def compile_review(self,review,name,decision="approve",session=None):
        value=load_json((review/'review-input.json').read_bytes())
        output={'qid':value['proposal']['qid'],'decision':decision,'checks':[{'id':r['id'],'supported':True,'support_basis':'direct','reason':'Fixture supported'} for r in value['facts']+value['contexts']],
            'coverage_checks':[{'group':g,'status':'checked','reason':'Fixture checked'} for g in ['identity','geography','history','population','finance','profile']],
            'request_responses':[{'request_id':r['request_id'],'status':'addressed','reason':'Fixture resolved'} for r in value['proposal']['open_requests']], 'requests':[]}
        if decision=='request_changes': output['requests']=[{'field':'location_address','category':'evidence_gap','reason':'Fixture needs subject evidence'}]
        result=self.private/(name+'-result.json');result.write_bytes(encode(output))
        compiled=self.run_cli('review-compile','--job',review,'--result',result,'--session',session or 'review-'+name,'--model','test-model')
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

    def test_publication_batch_requires_independent_reviewers_per_qid(self):
        first_research,first_proposal=self.research('Q101')
        second_research,second_proposal=self.research('Q102')
        first_review,first_result=self.review(first_research,first_proposal,'first-review',session='batch-reviewer')
        second_review,second_result=self.review(second_research,second_proposal,'second-review',session='batch-reviewer')
        def arguments(review,result,output):
            return ['unified-publish','--proposal',first_proposal,'--proposal',second_proposal,
                '--review-job',first_review,'--review-job',review,'--review-attempt',first_result['private_attempt'],
                '--review-attempt',result['private_attempt'],'--batch-id','two-schools','--output',output]
        with self.assertRaisesRegex(ValueError,'own Review subagent'):
            self.run_cli(*arguments(second_review,second_result,self.private/'shared-reviewer'))
        second_review,second_result=self.review(second_research,second_proposal,'rechecked',session='another-reviewer')
        bundle=self.private/'independent-reviewers'
        self.run_cli(*arguments(second_review,second_result,bundle))
        manifest=load_json((bundle/'data/batches/two-schools.json').read_bytes())
        self.assertEqual([row['qid'] for row in manifest['records']],['Q101','Q102'])
        plan=load_json((bundle/'operations.json').read_bytes())
        # The remote-file verifier must reject shared reviewers as well as the
        # local publication builder, even if receipt/manifest hashes are updated.
        files={path:(bundle/path).read_bytes() for path in plan['files']}
        receipt_path='data/reviews/two-schools/Q102.json'
        receipt=load_json(files[receipt_path]);receipt['review']['review_session']='batch-reviewer'
        files[receipt_path]=encode(receipt)
        manifest['records'][1]['receipt_sha256']=sha(files[receipt_path])
        files['data/batches/two-schools.json']=encode(manifest)
        with self.assertRaisesRegex(ValueError,'own Review subagent'):
            unified_publish.verify_files(self.root,plan['base_commit'],files,self.trust)
        for path in plan['files']:
            target=self.root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((bundle/path).read_bytes())
        self.commit('independent Review publication')
        verified=self.run_cli('publication-confirm','--bundle',bundle,'--published-ref',self.git('rev-parse','HEAD'))
        self.assertEqual(verified['qids'],['Q101','Q102'])
        self.http.assert_not_called()

    def test_parallel_review_jobs_compile_out_of_order(self):
        first_research,first_proposal=self.research('Q101')
        second_research,second_proposal=self.research('Q102')
        first=self.private/'parallel-first';second=self.private/'parallel-second'
        for research,proposal,job in [(first_research,first_proposal,first),(second_research,second_proposal,second)]:
            self.run_cli('review-prepare','--proposal',proposal,'--research-job',research,'--job',job)
        self.assertEqual([manager._read(self.root)['tasks'][q]['phase'] for q in ['Q101','Q102']],['reviewing','reviewing'])
        with self.assertRaisesRegex(ValueError,'active'):
            self.run_cli('review-prepare','--proposal',first_proposal,'--research-job',first_research,'--job',self.private/'duplicate')
        self.compile_review(second,'parallel-second')
        self.assertEqual(manager._read(self.root)['tasks']['Q101']['phase'],'reviewing')
        self.compile_review(first,'parallel-first')
        self.assertEqual([manager._read(self.root)['tasks'][q]['phase'] for q in ['Q101','Q102']],['ready_to_publish','ready_to_publish'])
        self.http.assert_not_called()

    def test_batch_sessions_reject_reused_research_and_cross_role_sessions(self):
        def pair(research,review):return ({'research':{'session':research}},{'review_session':review})
        with self.assertRaisesRegex(ValueError,'own Research'):
            unified_publish.check_batch_sessions([pair('r1','v1'),pair('r1','v2')])
        with self.assertRaisesRegex(ValueError,'also be a Research'):
            unified_publish.check_batch_sessions([pair('r1','r2'),pair('r2','v2')])
        with self.assertRaisesRegex(ValueError,'at least one'):
            unified_publish.check_batch_sessions([])

    def test_new_publication_rejects_old_receipt_attribution(self):
        research,proposal=self.research()
        review,result=self.review(research,proposal,'current')
        base=commit(self.root,'origin/main')
        files=unified_publish.files(self.root,base,'attribution',[(proposal,review,result['private_attempt'])])
        path='data/reviews/attribution/Q101.json'
        receipt=load_json(files[path]);receipt['attribution']='main_agent_review_of_native_research_subagent;not_independent_signature'
        files[path]=encode(receipt)
        manifest=load_json(files['data/batches/attribution.json']);manifest['records'][0]['receipt_sha256']=sha(files[path])
        files['data/batches/attribution.json']=encode(manifest)
        with self.assertRaisesRegex(ValueError,'Invalid unified receipt'):
            unified_publish.verify_files(self.root,base,files,self.trust)
