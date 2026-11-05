from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.agents/skills/university-curation/scripts/lib'))
from university_curation import native_cli as c
from university_curation.records import encode
import test_native_protocol as native_fixture

class NativeCLITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.private=Path(self.temp.name)/'.private'; self.private.mkdir()
        self.base='a'*40; self.trust={'repository':'owner/repo'}
    def tearDown(self):self.temp.cleanup()
    def call(self,*args):
        with redirect_stdout(io.StringIO()): return c.main(['--workspace',self.temp.name,*args])
    def test_doctor_and_role_enforcement(self):
        with patch.object(c.native_research,'doctor',return_value={'status':'local_ready'}) as doctor:
            self.assertEqual(self.call('--role','research','doctor')['status'],'local_ready'); doctor.assert_called_once()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):self.call('--role','review','research-prepare','--qid','Q1','--job',str(self.private/'job'))
    def test_prepare_compile_route_without_provider(self):
        with patch.object(c.native_research,'prepare',return_value={'status':'prepared'}) as prepare:
            self.call('--role','research','research-prepare','--qid','Q1','--job',str(self.private/'job'))
            self.assertEqual(prepare.call_args.args[1],'Q1')
        with patch.object(c.native_review,'compile',return_value={'status':'compiled'}) as compile_review:
            self.call('--role','review','review-compile','--job',str(self.private/'job'),'--result',str(self.private/'result'),'--session','s2','--model','not_reported')
            self.assertEqual(compile_review.call_args.args[3:6],('s2','not_reported','medium'))
    def test_plugin_plan_private_and_not_finalized(self):
        snap=self.private/'snapshot.json'; args=self.private/'args.json'; out=self.private/'plan.json'
        snap.write_bytes(encode({'coord/runtime':{'sha':None,'state':{}}}))
        args.write_bytes(encode({'role':'review','owner':'r','job':'j','now':'2026-11-05T00:00:00Z'}))
        with patch.object(c,'_base',return_value=(self.base,self.trust,{},'d'*64)):
            result=self.call('--role','review','coord-plan','--snapshot',str(snap),'--action','acquire_model','--arguments',str(args),'--output',str(out))
        self.assertEqual(result['status'],'awaiting_plugin_commit'); obj=json.loads(out.read_text())
        self.assertEqual(obj['operations'][2]['arguments']['parent_sha'],self.base)
        self.assertEqual(obj['operations'][0]['arguments']['repository_full_name'],'owner/repo')
        with self.assertRaises(FileExistsError):c._save(out,{'x':1})
    def test_bundle_is_private_base_bound_and_force_with_lease(self):
        files={'data/batches/batch-1.json':b'{}\n'}; out=self.private/'bundle'
        with patch.object(c,'git',return_value=b'b'*40+b'\n'):
            result=c._bundle(self.temp.name,out,files,self.base,'owner/repo','codex/university-batch-1','c'*40,'final')
        self.assertEqual(result['status'],'bundle_prepared'); plan=json.loads((out/'operations.json').read_text())
        self.assertEqual(plan['operations'][-1]['arguments']['expected_sha'],'c'*40)
        self.assertTrue(plan['operations'][-1]['arguments']['force']); self.assertEqual(plan['operations'][-2]['arguments']['parent_sha'],self.base)
        self.assertEqual((out/'data/batches/batch-1.json').read_bytes(),b'{}\n')
        with self.assertRaises(ValueError):c._bundle(self.temp.name,Path(self.temp.name)/'public',files,self.base,'owner/repo','codex/university-batch-1')
    def test_draft_revision_uses_expected_head(self):
        proposal=self.private/'proposal.json'; proposal.write_bytes(encode({'transport':{'protocol':'native-subagent-v1'}}))
        with patch.object(c,'_base',return_value=(self.base,self.trust,{},'d'*64)), \
             patch.object(c.native_protocol,'draft_files',return_value={'data/proposals/batch-1/manifest.json':b'{}\n'}), \
             patch.object(c,'_bundle',return_value={'status':'bundle_prepared'}) as bundle:
            c.draft(self.temp.name,[proposal],'batch-1','origin/main',self.private/'draft','c'*40)
            self.assertEqual(bundle.call_args.args[-1],'c'*40)
    def test_next_is_advisory_and_excludes_fresh_and_snapshot_tasks(self):
        catalog={'Q2':{'queue_kind':'primary'},'Q3':{'queue_kind':'primary'},'Q4':{'queue_kind':'discovery'}}
        snapshot={c.GitCoordinator._task_ref('Q2'):{'sha':self.base,'state':{'tasks':{'Q2':{'phase':'draft'}}}}}
        record={'qid':'Q3','update_datetime':'2026-11-01T00:00:00Z'}
        with patch.object(c,'_base',return_value=(self.base,self.trust,catalog,'d'*64)),patch.object(c,'recency_index',return_value={'Q3':record['update_datetime']}):
            result=c.next_candidates(self.temp.name,limit=3,snapshot=snapshot,now='2026-11-05T00:00:00Z')
        self.assertEqual(result['candidates'],[{'qid':'Q4','queue_kind':'discovery'}]); self.assertFalse(result['claims_created'])
    def test_finalize_requires_latest_owner_review_and_exact_head(self):
        test=native_fixture.NativeTests('test_native_review_and_independence'); test.setUp()
        try:
            proposal=test.proposal; decision=test.decision; trust=test.fixture.trust; catalog=test.fixture.catalog; digest=test.fixture.catalog_hash
            head='f'*40; comments=self.private/'comments.json'; output=self.private/'final'
            def write_comment(login,body): comments.write_bytes(encode([{'id':1,'user':{'login':login},'body':body}]))
            body=c.native_protocol.review_comment(decision)
            manifest=encode({'base_commit':self.base,'batch_id':'batch-1'})
            def git(repo,*args):
                return b'data/proposals/batch-1/manifest.json\n' if args[0]=='ls-tree' else b'b'*40+b'\n'
            with patch.object(c,'_base',return_value=(self.base,trust,catalog,digest)),patch.object(c,'commit',return_value=head), \
                 patch.object(c,'git',side_effect=git),patch.object(c,'blob',return_value=manifest), \
                 patch.object(c,'baseline_at',return_value=(None,'absent')),patch.object(c.native_protocol,'inspect_draft',return_value=({}, {'Q101':proposal})):
                write_comment('outsider',body)
                with self.assertRaisesRegex(ValueError,'Missing owner'):c.finalize(self.temp.name,'head',8,comments,'origin/main',output)
                write_comment('owner',body)
                result=c.finalize(self.temp.name,'head',8,comments,'origin/main',output)
                self.assertEqual(result['status'],'bundle_prepared')
                stale=dict(decision); stale['reviewed_head_sha']='e'*40
                write_comment('owner',c.native_protocol.review_comment(stale))
                self.assertEqual(c.finalize(self.temp.name,'head',8,comments,'origin/main',self.private/'rebind')['status'],'bundle_prepared')
                ref=c.GitCoordinator._task_ref('Q101'); entry={'sha':'1'*40,'state':{'tasks':{'Q101':{'phase':'unresolved','pr_number':8,'proposal_sha256':c.sha(encode(proposal))}}}}
                outcome=c.finalize(self.temp.name,'head',8,comments,'origin/main',self.private/'all', ['Q101'], {ref:entry})
                self.assertEqual(outcome['status'],'all_unresolved'); self.assertFalse((self.private/'all').exists())
                entry['state']['tasks']['Q101']['pr_number']=9
                with self.assertRaisesRegex(ValueError,'matching unresolved'): c.finalize(self.temp.name,'head',8,comments,'origin/main',self.private/'bad',['Q101'],{ref:entry})
        finally:test.tearDown()
    def test_merged_and_expired_claimed_are_eligible_after_recency(self):
        catalog={q:{'queue_kind':'primary'} for q in ('Q2','Q3','Q4','Q5')}
        tasks={'Q2':{'phase':'merged'},'Q3':{'phase':'claimed','expires_at':'2026-11-04T00:00:00Z'},'Q4':{'phase':'unresolved'},'Q5':{'phase':'merged','retry_after':'2026-11-06T00:00:00Z'}}
        snapshot={c.GitCoordinator._task_ref(q):{'sha':self.base,'state':{'tasks':{q:task}}} for q,task in tasks.items()}
        with patch.object(c,'_base',return_value=(self.base,self.trust,catalog,'d'*64)),patch.object(c,'recency_index',return_value={}):
            result=c.next_candidates(self.temp.name,limit=10,snapshot=snapshot,now='2026-11-05T00:00:00Z')
        self.assertEqual([r['qid'] for r in result['candidates']],['Q2','Q3'])
    def test_final_rebind_reuses_exact_receipt_review(self):
        test=native_fixture.NativeTests('test_native_review_and_independence'); test.setUp()
        try:
            proposal=test.proposal; decision=test.decision; trust=test.fixture.trust; catalog=test.fixture.catalog; digest=test.fixture.catalog_hash
            head='e'*40; old='f'*40; comments=self.private/'rebind-comments.json'
            comments.write_bytes(encode([{'id':1,'user':{'login':'owner'},'body':c.native_protocol.review_comment(decision)}]))
            receipt=encode({'research':proposal,'review':decision}); receipt_path='data/reviews/batch-1/Q101.json'
            def git(repo,*args):
                if args[0]=='ls-tree':return b''
                if args[0]=='rev-list':return (head+' '+old+'\n').encode()
                if args[0]=='diff':return (receipt_path+'\0').encode()
                return b'b'*40+b'\n'
            verify={'review_pr':8,'batch_id':'batch-1','qids':['Q101']}
            with patch.object(c,'_base',return_value=(self.base,trust,catalog,digest)),patch.object(c,'commit',return_value=head),patch.object(c,'git',side_effect=git), \
                 patch.object(c,'blob',return_value=receipt),patch.object(c,'baseline_at',return_value=(None,'absent')), \
                 patch.object(c.native_protocol.legacy,'trust_at',return_value=trust),patch.object(c.native_protocol,'verify_final',return_value=verify), \
                 patch.object(c.native_protocol,'finalized_files',return_value={'data/batches/batch-1.json':b'{}\n'}):
                result=c.finalize(self.temp.name,'head',8,comments,'origin/main',self.private/'final-rebind')
                self.assertEqual(result['status'],'bundle_prepared')
                changed=dict(decision); changed['review_session']='different'
                comments.write_bytes(encode([{'id':2,'user':{'login':'owner'},'body':c.native_protocol.review_comment(changed)}]))
                with self.assertRaisesRegex(ValueError,'not latest'):c.finalize(self.temp.name,'head',8,comments,'origin/main',self.private/'stale-receipt')
        finally:test.tearDown()

if __name__=='__main__': unittest.main()
