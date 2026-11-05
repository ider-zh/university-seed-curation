from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
import subprocess
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.agents/skills/university-curation/scripts/lib'))
from university_curation import distributed_agent as agent

T='2026-11-05T00:00:00+00:00'; FUTURE='2026-11-05T01:00:00+00:00'; BASE='a'*40

class Coord:
    def __init__(self,tasks=None): self.tasks=deepcopy(tasks or {}); self.claimed=[]; self.updates=[]
    def list_tasks(self): return deepcopy(self.tasks)
    def read(self,name): return ({},None)
    def claim_task(self,qid,owner,now,ttl=1800,allow_resume=False):
        self.claimed.append((qid,allow_resume)); lease={'qid':qid,'owner':owner,'token':'token-'+qid,'expires_at':FUTURE}
        self.tasks[qid]={**self.tasks.get(qid,{}),**lease,'phase':'claimed'}; return lease
    def heartbeat_task(self,lease,now): return lease
    def set_task(self,lease,phase,now,**metadata):
        self.updates.append((lease['qid'],phase,metadata)); self.tasks[lease['qid']]={**self.tasks.get(lease['qid'],{}),**metadata,'phase':phase}; return self.tasks[lease['qid']]

class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)/'.private'; self.root.mkdir()
        self.a=agent.RoleAgent.__new__(agent.RoleAgent); self.a.repo=self.root; self.a.role='research'; self.a.owner='review-abcdef'; self.a.root=self.root
        self.a.path=self.root/'state.json'; self.a.coord=Coord(); self.a._save({'version':1,'tasks':{}})
        self.catalog={'Q2':{'queue_kind':'discovery'},'Q3':{'queue_kind':'primary'},'Q1':{'queue_kind':'primary'}}
        self.context=patch.object(self.a,'_context',return_value=(BASE,{},self.catalog,'c'*64)); self.context.start()
        self.clock=patch.object(agent,'now',return_value=T); self.clock.start()
        self.index=patch.object(agent,'recency_index',return_value={}); self.index_mock=self.index.start()
    def tearDown(self): self.index.stop(); self.clock.stop(); self.context.stop(); self.tmp.cleanup()
    def test_claims_primary_first_and_excludes_fresh_or_pending(self):
        self.a.coord=Coord({'Q1':{'phase':'review_pending','owner':'other'}})
        self.index_mock.return_value={'Q3':'2026-10-01T00:00:00Z'}
        result=self.a.next_tasks(3)
        self.assertEqual([x['qid'] for x in result['tasks']],['Q2'])
        self.assertEqual(self.a._load()['tasks']['Q2']['lease']['owner'],self.a.owner)
    def test_three_active_claims_block_additional_claims(self):
        self.a.coord=Coord({f'Q{i}':{'phase':'claimed','owner':self.a.owner,'token':str(i),'expires_at':FUTURE} for i in range(1,4)})
        self.assertEqual(self.a.next_tasks()['status'],'capacity'); self.assertEqual(self.a.coord.claimed,[])
    def test_prepared_expired_task_is_recovered_without_research(self):
        old='2026-11-04T00:00:00Z'; lease={'qid':'Q1','owner':self.a.owner,'token':'old','expires_at':old}
        self.a.coord=Coord({'Q1':{**lease,'phase':'draft','revision':1}})
        self.a._save({'version':1,'tasks':{'Q1':{'lease':lease,'prepared':str(self.root/'prepared.json'),'revision':1}}})
        result=self.a.next_tasks()
        self.assertEqual(result['status'],'prepared_waiting_publish'); self.assertEqual(self.a.coord.claimed,[('Q1',True)])
        self.assertEqual(self.a.coord.updates[0][1],'draft')
    def test_feedback_required_before_revision(self):
        self.a.coord=Coord({'Q1':{'phase':'review_pending','owner':self.a.owner,'token':'valid','expires_at':FUTURE,'revision':0,'pr_number':7}})
        lease={'qid':'Q1','owner':self.a.owner,'token':'valid','expires_at':FUTURE}
        self.a._save({'version':1,'tasks':{'Q1':{'lease':lease,'revision':0,'pr_number':7}}})
        self.a.client=object()
        with patch.object(self.a,'public_proposals',return_value=({'number':7},'batch',{'Q1':{}},BASE)), \
             patch.object(agent,'comments',return_value=[]), patch.object(agent,'requests_from_comments',return_value=[]), \
             patch.object(agent,'verify',return_value={'baseline_sha256':'absent'}), patch.object(agent,'baseline_at',return_value=(None,'absent')):
            result=self.a.research_one('Q1',7)
        self.assertEqual(result['status'],'waiting_for_review_objection'); self.assertEqual(self.a.coord.updates,[])
    def test_revision_permits_changed_main_baseline_without_new_objection(self):
        self.a.coord=Coord({'Q1':{'phase':'review_pending','owner':self.a.owner,'token':'valid','expires_at':FUTURE,'revision':0,'pr_number':7}})
        lease={'qid':'Q1','owner':self.a.owner,'token':'valid','expires_at':FUTURE}
        self.a._save({'version':1,'tasks':{'Q1':{'lease':lease,'revision':0,'pr_number':7}}}); self.a.client=object()
        with patch.object(self.a,'public_proposals',return_value=({'number':7},'batch',{'Q1':{'document':True}},BASE)), \
             patch.object(agent,'comments',return_value=[]), patch.object(agent,'requests_from_comments',return_value=[]), \
             patch.object(agent,'verify',return_value={'baseline_sha256':'absent'}), \
             patch.object(agent,'baseline_at',return_value=({'qid':'Q1'},'digest')), \
             patch.object(agent,'GitModelBudget'), patch.object(agent,'research',return_value=({'qid':'Q1'},str(self.root/'job'))) as model:
            result=self.a.research_one('Q1',7)
        self.assertEqual(result['status'],'prepared'); self.assertEqual(result['revision'],1)
        self.assertIn('baseline changed',model.call_args.kwargs['feedback']['reason'])
        self.assertEqual(model.call_args.kwargs['feedback']['open_requests'],[])

    def test_review_blocks_omitted_objection_and_skips_duplicate_model_call(self):
        self.a.role='review'; self.a.client=object()
        pull={'number':7,'head':{'sha':'d'*40}}
        document={'key_id':'different','payload':{}}
        proposal={'qid':'Q1','open_requests':[]}
        with patch.object(self.a,'public_proposals',return_value=(pull,'batch',{'Q1':document},BASE)), \
             patch.object(agent,'trust_at',return_value={}), patch.object(agent,'comments',return_value=[]), \
             patch.object(agent,'proposal_snapshot',return_value=('draft',{'base_commit':BASE},{},{})), \
             patch.object(agent,'git',return_value=b'data/proposals/batch/Q1.json\0'), patch.object(agent,'catalog_at',return_value=({'Q1':{}},'c'*64)), \
             patch.object(agent,'verify',return_value=proposal), patch.object(agent,'baseline_at',return_value=(None,'absent')), \
             patch.object(agent,'check_proposal'), patch.object(agent,'requests_from_comments',return_value=[{'request_id':'unseen'}]), \
             patch.object(agent,'review') as model:
            result=self.a.review_pr(7)
        self.assertEqual(result['results'][0]['status'],'revision_requested'); model.assert_not_called()
        with patch.object(self.a,'public_proposals',return_value=(pull,'batch',{'Q1':document},BASE)), \
             patch.object(agent,'trust_at',return_value={}), patch.object(agent,'comments',return_value=[]), \
             patch.object(agent,'proposal_snapshot',return_value=('draft',{'base_commit':BASE},{},{})), \
             patch.object(agent,'git',return_value=b'data/proposals/batch/Q1.json\0'), patch.object(agent,'catalog_at',return_value=({'Q1':{}},'c'*64)), \
             patch.object(agent,'verify',return_value=proposal), patch.object(agent,'baseline_at',return_value=(None,'absent')), \
             patch.object(agent,'check_proposal'), patch.object(agent,'requests_from_comments',return_value=[]), \
             patch.object(agent,'read_reviews',return_value=[({'key_id':'review'},1,'url')]), \
             patch.object(agent,'check_decision',return_value=({'decision':'approve'},{})), patch.object(agent,'review') as model:
            result=self.a.review_pr(7)
        self.assertEqual(result['results'][0]['status'],'already_reviewed'); model.assert_not_called()

    def test_review_does_not_post_if_new_objection_arrives_during_model_call(self):
        self.a.role='review'; pull={'number':7,'head':{'sha':'d'*40},'base':{'ref':'main'}}
        class Client:
            def pull(self,n): return pull
        self.a.client=Client(); document={'key_id':'different','payload':{}}; proposal={'qid':'Q1','open_requests':[]}
        with patch.object(self.a,'public_proposals',return_value=(pull,'batch',{'Q1':document},BASE)), \
             patch.object(agent,'trust_at',return_value={}), patch.object(agent,'comments',return_value=[]), \
             patch.object(agent,'proposal_snapshot',return_value=('draft',{'base_commit':BASE},{},{})), \
             patch.object(agent,'git',return_value=b'data/proposals/batch/Q1.json\0'), patch.object(agent,'catalog_at',return_value=({'Q1':{}},'c'*64)), \
             patch.object(agent,'verify',return_value=proposal), patch.object(agent,'baseline_at',return_value=(None,'absent')), \
             patch.object(agent,'check_proposal'), patch.object(agent,'requests_from_comments',side_effect=[[],[{'request_id':'new'}]]), \
             patch.object(agent,'read_reviews',return_value=[]), patch.object(agent,'GitModelBudget'), \
             patch.object(agent,'review',return_value=({'decision':'approve'},{})), patch.object(agent,'fetch_main',return_value=BASE), \
             patch.object(agent,'submit_decision') as post:
            result=self.a.review_pr(7)
        self.assertEqual(result['results'][0]['status'],'revision_requested'); post.assert_not_called()

    def test_parallel_instances_write_only_changed_qid_files(self):
        other=agent.RoleAgent.__new__(agent.RoleAgent); other.root=self.root; other.path=self.a.path
        first=self.a._load(); second=other._load()
        first['tasks']['Q1']={'revision':1}; second['tasks']['Q2']={'revision':2}
        self.a._save(first); other._save(second)
        result=self.a._load()['tasks']
        self.assertEqual(result['Q1']['revision'],1); self.assertEqual(result['Q2']['revision'],2)

    def test_waiting_pr_leases_do_not_consume_research_slots(self):
        self.a.coord=Coord({f'Q{i}':{'phase':'review_pending','owner':self.a.owner,'token':str(i),'expires_at':FUTURE} for i in range(1,4)})
        self.catalog['Q4']={'queue_kind':'primary'}
        with patch.object(agent,'baseline_at',return_value=(None,'absent')): result=self.a.next_tasks()
        self.assertEqual([row['qid'] for row in result['tasks']],['Q4'])

    def test_recent_partial_backoff_and_full_recency_are_separate(self):
        self.a.coord=Coord({'Q1':{'phase':'merged','retry_after':FUTURE},'Q3':{'phase':'merged','published_at':'2026-10-01T00:00:00Z'}})
        self.index_mock.return_value={'Q2':'2026-10-01T00:00:00Z'}
        result=self.a.next_tasks()
        self.assertEqual([row['qid'] for row in result['tasks']],['Q3'])


    def test_full_pr_permits_stop_new_claims(self):
        self.a.coord.read=lambda name: ({'pr_permits':[{}, {}, {}]},None)
        result=self.a.next_tasks(); self.assertEqual(result['status'],'waiting_for_pr_capacity')
        self.assertEqual(self.a.coord.claimed,[])

    def test_public_snapshot_preserves_stale_final_for_rebind(self):
        pull={'number':7,'state':'open','base':{'ref':'main'},'head':{'sha':'d'*40,'repo':{'full_name':'owner/repo'}}}
        class Client:
            def pull(self,n): return pull
        self.a.client=Client(); self.a.role='review'
        self.context.stop(); self.context=patch.object(self.a,'_context',return_value=(BASE,{'repository':'owner/repo'},self.catalog,'c'*64)); self.context.start()
        manifest={'batch_id':'batch','base_commit':'e'*40}; proposals={'Q1':{'payload':{}}}
        with patch.object(agent,'fetch_pull',return_value='d'*40), \
             patch.object(agent,'proposal_snapshot',return_value=('final',manifest,proposals,{})), \
             patch.object(agent,'trust_at',return_value={'repository':'owner/repo'}), patch.object(agent,'comments',return_value=[]), \
             patch.object(agent,'review') as model:
            self.assertEqual(self.a.public_proposals(7),(pull,'batch',proposals,BASE))
            result=self.a.review_pr(7)
        self.assertEqual(result['status'],'rebind_required'); model.assert_not_called()

    def test_recency_index_streams_snapshot_and_incrementally_tracks_changes(self):
        self.index.stop()
        repo=Path(self.tmp.name)/'repo'; repo.mkdir()
        def run(*args): return subprocess.run(['git','-C',str(repo),*args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout.decode().strip()
        run('init'); run('config','user.name','Test'); run('config','user.email','test@example.invalid')
        folder=repo/'data/universities/aa'; folder.mkdir(parents=True)
        (folder/'Q1.json').write_text('{"qid":"Q1","update_datetime":"2026-01-01T00:00:00Z"}',encoding='utf-8')
        (folder/'Q2.json').write_text('{"qid":"Q2"}',encoding='utf-8')
        run('add','data'); run('commit','-m','first'); first=run('rev-parse','HEAD')
        path=self.root/'cache.json'
        self.assertEqual(agent.recency_index(repo,first,path),{'Q1':'2026-01-01T00:00:00Z'})
        (folder/'Q2.json').write_text('{"qid":"Q2","update_datetime":"2026-10-01T00:00:00Z"}',encoding='utf-8')
        run('add','data'); run('commit','-m','second'); second=run('rev-parse','HEAD')
        # Fixture paths intentionally bypass stable QID buckets; mock the incremental blob adapter.
        with patch.object(agent,'baseline_at',return_value=({'qid':'Q2','update_datetime':'2026-10-01T00:00:00Z'},'x')) as read:
            index=agent.recency_index(repo,second,path)
        self.assertEqual(index,{'Q1':'2026-01-01T00:00:00Z','Q2':'2026-10-01T00:00:00Z'})
        self.assertEqual(read.call_count,1)
        self.index.start()

    def test_wrong_role_is_rejected(self):
        self.a.role='review'
        with self.assertRaises(ValueError): self.a.next_tasks()

if __name__=='__main__': unittest.main()
