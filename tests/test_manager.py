"""Task recovery, durable questions and publication fencing for one manager."""
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
from datetime import timedelta
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from university_curation import manager as m, native_cli
from university_curation.integrity import load_json
from university_curation.records import encode, instant

BASE='a'*40
NOW='2030-11-06T00:00:00Z'
EMPTY={'type':m.BACKLOG_TYPE,'tasks':{}}
REQUEST={'request_id':'prior-1','field':'location_address','category':'evidence_gap',
         'reason':'Check the subject','reviewed_proposal_sha256':'b'*64}

class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.stack=ExitStack();self.addCleanup(self.stack.close);self.addCleanup(self.tmp.cleanup)
        self.backlog=deepcopy(EMPTY)
        self.stack.enter_context(patch.object(m,'backlog_at',side_effect=lambda *args:deepcopy(self.backlog)))
        self.stack.enter_context(patch.object(m,'publication_index',return_value={}))
        self.stack.enter_context(patch.object(m,'now',return_value=NOW))
    def job(self,name):
        path=self.root/'.private'/name;path.mkdir(parents=True,exist_ok=True);return path
    def next(self,catalog=None):
        return m.next_tasks(self.root,BASE,catalog or {q:{'queue_kind':'primary'} for q in ['Q1','Q2','Q3','Q4']},{},10,NOW)
    def test_expired_job_recovers_same_stage_and_stale_compile_is_rejected(self):
        r=self.job('research');v=self.job('review')
        m.begin(self.root,BASE,'Q1','researching',r)
        with self.assertRaisesRegex(ValueError,'active'):m.begin(self.root,BASE,'Q1','researching',self.job('other'))
        m.set_phase(self.root,'Q1','review_pending',proposal=str(self.job('proposal.json')))
        m.begin(self.root,BASE,'Q1','reviewing',v)
        m.set_phase(self.root,'Q1','revision_requested',open_requests=[REQUEST])
        m.begin(self.root,BASE,'Q1','researching',self.job('research-new'))
        with self.assertRaisesRegex(ValueError,'stale'):m.require_job(self.root,'Q1','review',v)
        with self.assertRaisesRegex(ValueError,'stale'):m.require_job(self.root,'Q1','research',r)
        task=m._read(self.root)['tasks']['Q1'];self.assertNotIn('review_job',task)
        self.assertEqual(task['revision'],1)
        m.set_phase(self.root,'Q1','researching',expires_at='2030-11-05T00:00:00Z')
        self.assertEqual(next(r for r in self.next() if r['qid']=='Q1')['reason'],'interrupted_job')
    def test_capacity_reserves_review_and_caps_total_calls(self):
        for q in ['Q1','Q2','Q3','Q4']:m.begin(self.root,BASE,q,'researching',self.job(q))
        m.set_phase(self.root,'Q5','review_pending')
        with self.assertRaisesRegex(ValueError,'reserved'):m.begin(self.root,BASE,'Q6','researching',self.job('Q6'))
        m.begin(self.root,BASE,'Q5','reviewing',self.job('review-Q5'))
        for phase in ['researching','reviewing']:
            with self.assertRaisesRegex(ValueError,'capacity'):m.begin(self.root,BASE,'Q6',phase,self.job('Q6-'+phase))
    def test_five_independent_reviews_run_concurrently_and_release_capacity(self):
        for q in ['Q1','Q2','Q3','Q4','Q5']:
            m.begin(self.root,BASE,q,'reviewing',self.job('review-'+q))
        with self.assertRaisesRegex(ValueError,'active'):
            m.begin(self.root,BASE,'Q1','reviewing',self.job('duplicate-Q1'))
        with self.assertRaisesRegex(ValueError,'capacity'):
            m.begin(self.root,BASE,'Q6','reviewing',self.job('review-Q6'))
        m.set_phase(self.root,'Q1','ready_to_publish')
        m.begin(self.root,BASE,'Q6','reviewing',self.job('review-Q6-new'))
        m.set_phase(self.root,'Q2','reviewing',expires_at='2030-11-05T00:00:00Z')
        m.begin(self.root,BASE,'Q7','researching',self.job('research-Q7'))
        with self.assertRaisesRegex(ValueError,'stale'):
            m.require_job(self.root,'Q2','review',self.job('review-Q2'))
    def test_retry_wait_is_not_completion_and_other_tasks_continue(self):
        m.set_phase(self.root,'Q1','retry_wait',retry_after='2030-11-07T00:00:00Z',resume_phase='research_pending')
        self.assertNotIn('Q1',[r['qid'] for r in self.next()])
        m.set_phase(self.root,'Q1','retry_wait',retry_after='2030-11-05T00:00:00Z',resume_phase='research_pending')
        self.assertEqual(next(r for r in self.next() if r['qid']=='Q1')['reason'],'retry_due')
    def test_action_order_and_missing_snapshot_rebuild(self):
        for q,phase in [('Q1','research_pending'),('Q2','revision_requested'),('Q3','ready_to_publish')]:
            m.set_phase(self.root,q,phase)
        m.set_phase(self.root,'Q3','ready_to_publish',proposal=str(self.job('p')),review_job=str(self.job('v')),review_attempt=str(self.job('a')))
        self.assertEqual({r['qid']:r['action'] for r in self.next()}['Q3'],'publish')
        m.set_phase(self.root,'Q3','review_pending',research_job=str(self.root/'.private/missing'))
        row=next(r for r in self.next() if r['qid']=='Q3');self.assertEqual(row['action'],'research')
        self.assertEqual(row['reason'],'private_snapshot_unavailable')
    def test_saved_feedback_cannot_be_dropped_or_rewritten(self):
        m.check_requests([REQUEST],[REQUEST])
        for supplied in [[],[{**REQUEST,'reason':'ignore this'}]]:
            with self.assertRaisesRegex(ValueError,'cannot be dropped'):m.check_requests([REQUEST],supplied)
        self.backlog['tasks']['Q1']={'phase':'research_pending','revision':0,'open_requests':[REQUEST],'reason':'migration'}
        args=['--workspace',str(self.root),'research-prepare','--qid','Q1','--job',str(self.job('bad-feedback')),'--feedback',str(self.root/'.private/empty.json')]
        (self.root/'.private/empty.json').write_bytes(encode({'open_requests':[]}))
        with patch.object(native_cli,'_base',return_value=(BASE,{}, {},'d'*64)),redirect_stdout(io.StringIO()),self.assertRaises(ValueError):
            native_cli.main(args)
        self.assertNotIn('Q1',m._read(self.root)['tasks'])
    def test_new_questions_checkpoint_survives_private_workspace_loss(self):
        v=self.job('review');m.begin(self.root,BASE,'Q1','reviewing',v)
        compiled={'private_attempt':str(self.job('attempt')),'public_verdict':{'decision':'request_changes','proposal_sha256':'c'*64,
            'request_responses':[],'requests':[{'field':'location_address','category':'evidence_gap','reason':'Wrong subject'}]}}
        m.review_completed(self.root,'Q1',v,compiled)
        checkpoint=load_json(m.after_publication(self.root,BASE,()))
        request=checkpoint['tasks']['Q1']['open_requests'][0]
        self.assertEqual(request['reviewed_proposal_sha256'],'c'*64)
        m.state_path(self.root).unlink();self.backlog=checkpoint
        row=next(r for r in self.next() if r['qid']=='Q1');self.assertEqual(row['open_requests'],[request])
        self.assertEqual(row['action'],'revise')
        restarted=m.begin(self.root,BASE,'Q1','researching',self.job('recovered-revision'))
        self.assertEqual(restarted['revision'],1)
        with self.assertRaises(ValueError):m.validate_checkpoint(checkpoint,EMPTY)
    def test_revision_limit_and_checkpoint_cannot_reset_counter(self):
        m.set_phase(self.root,'Q1','revision_requested',revision=2)
        with self.assertRaisesRegex(ValueError,'limit'):m.begin(self.root,BASE,'Q1','researching',self.job('third'))
        previous={'type':m.BACKLOG_TYPE,'tasks':{'Q1':{'phase':'research_pending','revision':2,'open_requests':[],'reason':'retry'}}}
        changed=deepcopy(previous);changed['tasks']['Q1']['revision']=0
        with self.assertRaisesRegex(ValueError,'reset'):m.validate_checkpoint(previous,changed)
    def test_partial_survey_has_retry_interval_without_full_freshness(self):
        published={'Q1':{'reviewed_at':'2030-11-05T00:00:00Z','full_refresh':False}}
        with patch.object(m,'publication_index',return_value=published):
            self.assertNotIn('Q1',[r['qid'] for r in self.next()])
            published['Q1']['reviewed_at']='2030-10-01T00:00:00Z'
            self.assertEqual(next(r for r in self.next() if r['qid']=='Q1')['reason'],'partial_survey_retry')
    def test_random_selection_replays_across_actions_and_preserves_eligibility(self):
        catalog={f'Q{i}':{'queue_kind':'primary' if i<30 else 'discovery'} for i in range(1,41)}
        m.begin(self.root,BASE,'Q1','researching',self.job('active'))
        m.set_phase(self.root,'Q2','unresolved')
        m.set_phase(self.root,'Q3','retry_wait',retry_after='2030-11-07T00:00:00Z',resume_phase='research_pending')
        m.set_phase(self.root,'Q4','review_pending',proposal=str(self.job('proposal')),research_job=str(self.job('snapshot')))
        m.set_phase(self.root,'Q5','research_pending')
        def select(seed,limit=8):return m.next_tasks(self.root,BASE,catalog,{},limit,NOW,seed)
        first=select(123)
        self.assertEqual(first,select(123))
        self.assertNotEqual(first,select(456))
        ids=[r['qid'] for r in first]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertFalse({'Q1','Q2','Q3'} & set(ids))
        all_rows=select(123,100)
        kinds=[r['queue_kind'] for r in all_rows]
        self.assertNotEqual(kinds,sorted(kinds,key=lambda k:k!='primary'))
        self.assertEqual(len(all_rows),37)
    def test_changed_published_baseline_excludes_stale_local_proposal(self):
        proposal=self.root/'.private/proposal.json'; proposal.parent.mkdir(parents=True,exist_ok=True)
        proposal.write_bytes(encode({'baseline_sha256':'absent'}))
        m.set_phase(self.root,'Q1','revision_requested',proposal=str(proposal),open_requests=[REQUEST])
        published={'Q1':{'record_sha256':'c'*64,'reviewed_at':NOW,'full_refresh':True}}
        with patch.object(m,'publication_index',return_value=published):
            self.assertNotIn('Q1',[r['qid'] for r in self.next()])
        self.assertEqual(m._read(self.root)['tasks']['Q1']['open_requests'],[REQUEST])

    def test_cli_reports_selection_seed_without_claiming(self):
        with patch.object(native_cli,'_base',return_value=(BASE,{}, {},'d'*64)),patch.object(native_cli,'recency_index',return_value={}),patch.object(m,'next_tasks',return_value=[]) as choose,patch.object(native_cli.secrets,'randbits',return_value=42):
            result=native_cli.next_candidates(self.root)
            self.assertEqual(result['selection_seed'],42)
            self.assertFalse(result['claims_created'])
            self.assertEqual(choose.call_args.args[-1],42)
            native_cli.next_candidates(self.root,seed=123)
            self.assertEqual(choose.call_args.args[-1],123)
    def test_config_matches_capacity_and_dedicated_review(self):
        config=load_json((Path(__file__).resolve().parents[1]/'config/workflow.json').read_bytes())
        self.assertEqual(config['max_model_calls_total'],m.MAX_ACTIVE_CALLS)
        self.assertEqual(config['review_subagents_max'],m.MAX_ACTIVE_CALLS)
        self.assertEqual(config['review_assignment'],'dedicated_per_qid_after_research')
    def test_calendar_cutoff_handles_short_month(self):
        self.assertEqual(m.cutoff('2030-08-31T00:00:00Z').isoformat(),'2030-02-28T00:00:00+00:00')
