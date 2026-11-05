import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.agents/skills/university-curation/scripts/lib'))
from university_curation.plugin_coordination import PluginCoordinator, plan

T0='2026-11-05T00:00:00Z'; T1='2026-11-05T00:00:02Z'
A='a'*40; B='b'*40; POLICY='c'*64

class PluginPlanTests(unittest.TestCase):
    def setUp(self): self.snapshot={'coord/runtime':{'sha':None,'state':{}}}; self.count=0
    def apply(self,p):
        self.assertEqual(p['status'],'awaiting_plugin_commit')
        name=p['ref'].removeprefix('refs/heads/')
        self.assertEqual(self.snapshot[name]['sha'],p['expected_sha'])
        self.count+=1; self.snapshot[name]={'sha':format(self.count,'040x'),'state':p['new_state']}
        return p['tentative_result']
    def action(self,action,**args): return plan(self.snapshot,action,args)
    def test_known_absent_and_expected_parent_operations(self):
        qid='Q2'; ref='coord/tasks-'+hashlib.sha256(qid.encode()).hexdigest()[:2]
        with self.assertRaisesRegex(ValueError,'explicit'): self.action('claim_task',qid=qid,owner='owner',now=T0)
        self.snapshot[ref]={'sha':None,'state':{}}
        p=self.action('claim_task',qid=qid,owner='owner',now=T0)
        self.assertIsNone(p['expected_sha']); self.assertEqual(p['operations'][-1]['tool'],'mcp__codex_apps__github_create_branch')
        self.assertEqual(p['operations'][2]['arguments']['parent_sha'],'$bootstrap_parent_sha')
        lease=self.apply(p); self.assertEqual(lease['qid'],qid)
        next_plan=self.action('heartbeat_task',lease=lease,now=T1)
        self.assertEqual(next_plan['expected_sha'],self.snapshot[ref]['sha'])
        self.assertEqual(next_plan['operations'][2]['arguments']['parent_sha'],self.snapshot[ref]['sha'])
        self.assertFalse(next_plan['operations'][-1]['arguments']['force'])
        self.assertEqual(next_plan['operations'][-1]['arguments']['expected_sha'],self.snapshot[ref]['sha'])
        self.assertEqual(next_plan['on_conflict'],'read_ref_and_replan')
        self.assertEqual(self.snapshot[ref]['state']['tasks'][qid]['expires_at'],lease['expires_at'])
    def test_reservation_capacity_and_fencing(self):
        one=self.apply(self.action('acquire_model',role='research',owner='a',job='j1',now=T0,ttl=1))
        self.apply(self.action('acquire_model',role='research',owner='b',job='j2',now=T0,ttl=1))
        self.apply(self.action('enqueue_review',pr_number=4,head_sha=A,base_sha=B,policy_hash=POLICY,now=T0))
        blocked=self.action('acquire_model',role='research',owner='c',job='j3',now=T0)
        self.assertIsNone(blocked['tentative_result'])
        self.apply(self.action('acquire_model',role='review',owner='d',job='j4',now=T0,ttl=1))
        self.assertIsNone(self.action('acquire_model',role='review',owner='e',job='j5',now=T0)['tentative_result'])
        with self.assertRaisesRegex(ValueError,'Expired'): self.action('renew_model',lease=one,now=T1)
        self.assertIsNotNone(self.action('acquire_model',role='review',owner='e',job='j5',now=T1)['tentative_result'])
    def test_cas_rejection_requires_new_snapshot(self):
        ref='coord/tasks-'+hashlib.sha256(b'Q5').hexdigest()[:2]; self.snapshot[ref]={'sha':A,'state':{}}
        stale=self.action('claim_task',qid='Q5',owner='a',now=T0)
        self.snapshot[ref]={'sha':B,'state':{'tasks':{'Q5':{'qid':'Q5','phase':'claimed','owner':'b','token':'other','expires_at':'2026-11-05T00:20:00+00:00'}}}}
        self.assertNotEqual(stale['expected_sha'],self.snapshot[ref]['sha'])
        with self.assertRaisesRegex(ValueError,'already leased'): self.action('claim_task',qid='Q5',owner='a',now=T0)
    def test_preserve_draft_parent_and_validation(self):
        ref='coord/tasks-'+hashlib.sha256(b'Q5').hexdigest()[:2]; self.snapshot[ref]={'sha':A,'state':{}}
        lease=self.apply(self.action('claim_task',qid='Q5',owner='owner',now=T0))
        p=self.action('set_task',lease=lease,phase='draft',now=T0,head_sha=B,revision=2)
        self.assertEqual(p['operations'][2]['arguments']['parent_sha'],self.snapshot[ref]['sha'])
        self.assertEqual(p['operations'][2]['arguments']['additional_parent_shas'],[B])
        with self.assertRaises(ValueError): self.action('set_task',lease=lease,phase='draft',now=T0,revision=3)
        with self.assertRaises(ValueError): PluginCoordinator({'coord/runtime':{'sha':None,'state':{'slots':[]}}})
        with self.assertRaises(ValueError): self.action('unknown',x=1)

if __name__ == '__main__': unittest.main()
