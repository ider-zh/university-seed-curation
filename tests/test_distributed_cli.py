from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.agents/skills/university-curation/scripts/lib'))
from university_curation import distributed_cli as cli

HEAD='a'*40

class FakeCoord:
    def __init__(self): self.finished=[]; self.renewed=0; self.lease={'pr_number':7,'head_sha':HEAD,'token':'secret'}
    def claim_review(self,owner,now): return self.lease
    def renew_review(self,lease,now): self.renewed+=1; return lease
    def finish_review(self,lease,outcome,now): self.finished.append(outcome)

class FakeAgent:
    def __init__(self): self.owner='review-123'; self.coord=FakeCoord(); self.called=[]
    def _require(self,role): self.called.append(role)
    def next_tasks(self,limit): return {'status':'claimed','limit':limit}
    def research_one(self,qid,pr): return {'status':'prepared','qid':qid,'pr':pr}
    def publish_ready(self,size,pr): return {'status':'review_pending','size':size,'pr':pr}
    def review_pr(self,pr,**kwargs):
        self.called.append((pr,kwargs))
        if 'lease_guard' in kwargs: kwargs['lease_guard']()
        return {'status':'review_processed','results':[{'status':'approve'}]}

class CLITests(unittest.TestCase):
    def setUp(self): self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def args(self,*parts): return cli.parser().parse_args(['--workspace',str(self.root),'--role','research',*parts])
    def test_thin_dispatch_preserves_qid_and_limits(self):
        fake=FakeAgent()
        with patch.object(cli,'RoleAgent',return_value=fake):
            self.assertEqual(cli.execute(self.args('next','--limit','3'))['limit'],3)
            self.assertEqual(cli.execute(self.args('research','--qid','Q1','--pr','8'))['pr'],8)
            self.assertEqual(cli.execute(self.args('publish','--batch-size','5'))['size'],5)
    def test_next_review_renews_fenced_lease_and_acknowledges(self):
        fake=FakeAgent(); result=cli.next_review(fake)
        self.assertEqual(result['queue_outcome'],'approved'); self.assertEqual(fake.coord.finished,['approved'])
        self.assertGreaterEqual(fake.coord.renewed,2)
        pr,kw=fake.called[-1]; self.assertEqual(pr,7); self.assertEqual(kw['expected_head'],HEAD)
        self.assertIsInstance(kw['cancel_event'],threading.Event)
    def test_lost_review_lease_sets_cancel_and_does_not_acknowledge(self):
        fake=FakeAgent()
        def reject(*args): raise ValueError('fenced')
        fake.coord.renew_review=reject
        with self.assertRaises(ValueError): cli.next_review(fake)
        self.assertEqual(fake.coord.finished,[])
        self.assertTrue(fake.called[-1][1]['cancel_event'].is_set())
    def test_no_review_task_is_actionable_idle(self):
        fake=FakeAgent(); fake.coord.claim_review=lambda *args: None
        self.assertEqual(cli.next_review(fake),{'status':'no_review_task'})
    def test_active_roles_only_are_listed(self):
        trust={'keys':{'r':{'status':'active','roles':['research']},'v':{'status':'active','roles':['review']},
            'revoked':{'status':'revoked','roles':['review']},'shared':{'status':'active','roles':['research','review']}}}
        self.assertEqual(cli._roles(trust),{'research':['r'],'review':['v']})

if __name__=='__main__': unittest.main()
