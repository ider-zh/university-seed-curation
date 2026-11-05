from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.agents/skills/university-curation/scripts/lib'))
from university_curation import distributed_sync as syncer
from university_curation import distributed_agent as agent_module
from university_curation.attestations import sha

BASE='a'*40; OLD='c'*40; HEAD='b'*40; T='2026-11-05T00:00:00+00:00'; EXPIRES='2026-11-05T01:00:00+00:00'

class Coord:
    def __init__(self,tasks): self.tasks=deepcopy(tasks); self.changes=[]; self.released=[]
    def list_tasks(self): return deepcopy(self.tasks)
    def read(self,name): return ({'pr_permits':[{'owner':'owner','pr_number':7,'batch_id':'batch','token':'p'}]},None)
    def heartbeat_task(self,lease,now): return lease
    def claim_task(self,qid,owner,now,allow_resume=False): return {'qid':qid,'owner':owner,'token':'new','expires_at':EXPIRES}
    def set_task(self,lease,phase,now,**kw): self.changes.append((lease['qid'],phase,kw))
    def release_pr_permit(self,permit,now): self.released.append(permit['pr_number'])

class Agent:
    def __init__(self,tasks,pull):
        self.owner='owner'; self.repo=Path('.'); self.root=Path('.private'); self.key=Path('.private/key')
        self.coord=Coord(tasks); self.client=type('Client',(),{'pull':lambda self,number:pull})()
    def _require(self,role):
        if role!='research': raise ValueError('wrong role')

def task(qid,revision=0): return {'qid':qid,'owner':'owner','token':'token-'+qid,'expires_at':EXPIRES,'pr_number':7,'phase':'review_pending','revision':revision}
def proposal(qid): return {'payload':{'qid':qid,'baseline_sha256':'absent'}}
def verdict(decision='approve',full=True): return {'payload':{'decision':decision,'reviewed_at':T,'full_refresh':full}}
def pull(state='open',merged=False): return {'number':7,'state':state,'merged':merged,'base':{'ref':'main'},'head':{'sha':HEAD,'repo':{'full_name':'owner/repo'}}}

class SyncTests(unittest.TestCase):
    def setUp(self):
        self.recovery=patch.object(syncer,'recover_unbound_permits',return_value=[]); self.recovery.start()
        self.clock=patch.object(syncer,'now',return_value=T); self.clock.start()
        self.main=patch.object(syncer,'fetch_main',return_value=BASE); self.main.start()
        self.trust=patch.object(syncer,'trust_at',return_value={'repository':'owner/repo'}); self.trust.start()
        self.catalog=patch.object(syncer,'catalog_at',return_value=({},'d'*64)); self.catalog.start()
        self.fetch=patch.object(syncer,'fetch_pull',return_value=HEAD); self.fetch.start()
        self.comments=patch.object(syncer,'comments',return_value=[]); self.comments.start()
        self.verify=patch.object(syncer,'verify',side_effect=lambda doc,trust,role:doc['payload']); self.verify.start()
        self.baseline=patch.object(syncer,'baseline_at',return_value=(None,'absent')); self.baseline.start()
        self.check=patch.object(syncer,'check_proposal'); self.check.start()
        self.reviews=patch.object(syncer,'read_reviews',return_value=[]); self.reviews_mock=self.reviews.start()
        self.decision=patch.object(syncer,'check_decision',side_effect=lambda doc,*args:(doc['payload'],{})); self.decision.start()
        self.feedback=patch.object(syncer,'requests_from_comments',return_value=[]); self.feedback_mock=self.feedback.start()
        self.apply=patch.object(syncer,'apply_reviews',return_value={'status':'approved_records_prepared','head_sha':'e'*40}); self.apply_mock=self.apply.start()
    def tearDown(self): patch.stopall()
    def snapshot(self,stage,proposals,base=BASE,embedded=None):
        manifest={'batch_id':'batch','base_commit':base,'records':[{'qid':q,'receipt_path':'receipt/'+q,'receipt_sha256':sha(b'expected')} for q in proposals]}
        return patch.object(syncer,'proposal_snapshot',return_value=(stage,manifest,proposals,embedded or {}))
    def test_approved_draft_finalizes_without_merging(self):
        a=Agent({'Q1':task('Q1')},pull()); self.reviews_mock.return_value=[(verdict(),1,'url')]
        with self.snapshot('draft',{'Q1':proposal('Q1')}): result=syncer.sync(a)
        self.assertEqual(result['results'][0]['status'],'approved_records_prepared')
        self.assertEqual([x[1] for x in a.coord.changes],['approved','published'])
        self.assertEqual(self.apply_mock.call_args.kwargs['approved_qids'],{'Q1'})
        self.assertEqual(a.coord.released,[])
    def test_open_signed_objection_requests_revision_and_stays_draft(self):
        a=Agent({'Q1':task('Q1')},pull()); self.feedback_mock.return_value=[{'request_id':'x'}]
        with self.snapshot('draft',{'Q1':proposal('Q1')}): result=syncer.sync(a)
        self.assertEqual(result['results'][0]['actions'][0]['action'],'research')
        self.assertEqual(a.coord.changes[0][1],'revision_requested'); self.apply_mock.assert_not_called()
    def test_revision_limit_marks_unresolved_and_releases_permit(self):
        a=Agent({'Q1':task('Q1',2)},pull()); self.feedback_mock.return_value=[{'request_id':'x'}]
        with self.snapshot('draft',{'Q1':proposal('Q1')}): result=syncer.sync(a)
        self.assertEqual(result['results'][0]['status'],'unresolved')
        self.assertEqual(a.coord.changes[0][1],'unresolved'); self.assertEqual(a.coord.released,[7]); self.apply_mock.assert_not_called()
    def test_partial_batch_only_finalizes_approved_subset(self):
        a=Agent({'Q1':task('Q1'),'Q2':task('Q2',2)},pull())
        self.reviews_mock.side_effect=lambda notes,trust,number,qid,digest: [(verdict(),1,'url')] if qid=='Q1' else []
        self.feedback_mock.side_effect=lambda notes,trust,number,qid,**kwargs: [] if qid=='Q1' else [{'request_id':'x'}]
        with self.snapshot('draft',{'Q1':proposal('Q1'),'Q2':proposal('Q2')}): result=syncer.sync(a)
        self.assertEqual(result['results'][0]['unresolved'],['Q2']); self.assertEqual(self.apply_mock.call_args.kwargs['approved_qids'],{'Q1'})
        self.assertIn(('Q2','unresolved'),[(q,p) for q,p,_ in a.coord.changes])
    def test_merged_requires_matching_actual_main_receipt(self):
        a=Agent({'Q1':task('Q1')},pull('closed',True)); embedded={'Q1':verdict(full=False)}
        with self.snapshot('final',{'Q1':proposal('Q1')},embedded=embedded), patch.object(syncer,'blob',return_value=b'wrong'):
            with self.assertRaisesRegex(ValueError,'receipt'): syncer.sync(a)
        self.assertEqual(a.coord.changes,[]); self.assertEqual(a.coord.released,[])
        with self.snapshot('final',{'Q1':proposal('Q1')},embedded=embedded), patch.object(syncer,'blob',return_value=b'expected'):
            result=syncer.sync(a)
        self.assertEqual(result['results'][0]['status'],'merged'); self.assertEqual(a.coord.changes[0][1],'merged')
        self.assertIn('retry_after',a.coord.changes[0][2]); self.assertEqual(a.coord.released,[7])
    def test_lost_review_queue_lease_cancels_without_comment(self):
        with tempfile.TemporaryDirectory() as temp:
            a=agent_module.RoleAgent.__new__(agent_module.RoleAgent); a.role='review'; a.owner='review-owner'; a.repo=Path(temp); a.root=Path(temp)/'.private'; a.root.mkdir()
            a.coord=object(); p=pull(); a.client=type('Client',(),{'pull':lambda self,n:p})()
            cancel=threading.Event(); document={'key_id':'research','payload':{}}; value={'qid':'Q1','open_requests':[]}
            def lost(*args): cancel.set(); return {'decision':'approve'},{}
            with patch.object(a,'public_proposals',return_value=(p,'batch',{'Q1':document},BASE)), \
                 patch.object(agent_module,'trust_at',return_value={}), patch.object(agent_module,'comments',return_value=[]), \
                 patch.object(agent_module,'proposal_snapshot',return_value=('draft',{'base_commit':BASE},{},{})), \
                 patch.object(agent_module,'catalog_at',return_value=({'Q1':{}},'d'*64)), \
                 patch.object(agent_module,'verify',return_value=value), patch.object(agent_module,'baseline_at',return_value=(None,'absent')), \
                 patch.object(agent_module,'check_proposal'), patch.object(agent_module,'requests_from_comments',return_value=[]), \
                 patch.object(agent_module,'read_reviews',return_value=[]), patch.object(agent_module,'GitModelBudget'), \
                 patch.object(agent_module,'review',side_effect=lost), patch.object(agent_module,'submit_decision') as post:
                with self.assertRaisesRegex(RuntimeError,'lease lost'):
                    a.review_pr(7,cancel_event=cancel,expected_head=HEAD)
            post.assert_not_called()

    def test_stale_final_rebinds_without_model(self):
        a=Agent({'Q1':task('Q1')},pull()); self.reviews_mock.return_value=[(verdict(),1,'url')]
        with self.snapshot('final',{'Q1':proposal('Q1')},base=OLD,embedded={'Q1':verdict()}): result=syncer.sync(a)
        self.assertEqual(result['results'][0]['status'],'approved_records_prepared')
        self.assertEqual(self.apply_mock.call_args.kwargs['approved_qids'],{'Q1'})

if __name__=='__main__': unittest.main()
