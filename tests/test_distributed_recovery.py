from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.agents/skills/university-curation/scripts/lib'))
from university_curation import distributed_recovery as recovery
from university_curation.records import encode

HEAD='a'*40; BASE='b'*40; TIME='2026-11-05T00:00:00+00:00'; OLD='2026-11-04T00:00:00+00:00'; FUTURE='2026-11-06T00:00:00+00:00'
TRUST={'repository':'owner/repo'}; BATCH='batch-test'; BRANCH='codex/university-'+BATCH

def pull(state='open'):
    return {'number':7,'state':state,'base':{'ref':'main'},'head':{'ref':BRANCH,'sha':HEAD,'repo':{'full_name':'owner/repo'}}}

def permit(expires=OLD): return {'owner':'research-owner','batch_id':BATCH,'token':'permit','expires_at':expires}
def task(): return {'qid':'Q1','owner':'research-owner','token':'task','expires_at':FUTURE,'phase':'draft','revision':0}
def snapshot():
    manifest={'batch_id':BATCH,'base_commit':BASE,'records':[{'qid':'Q1'}]}
    proposals={'Q1':{'key_id':'research-owner','payload':{'qid':'Q1'}}}
    return manifest,proposals

class Coord:
    def __init__(self,p): self.permit=p; self.bound=[]; self.released=[]; self.updated=[]
    def read(self,name): return ({'pr_permits':[self.permit]},None)
    def list_tasks(self): return {'Q1':task()}
    def heartbeat_task(self,lease,now): return lease
    def claim_task(self,*args,**kw): raise AssertionError('live task should be heartbeated')
    def set_task(self,lease,phase,now,**metadata): self.updated.append((lease['qid'],phase,metadata))
    def bind_pr_permit(self,lease,number,now): self.bound.append(number)
    def release_pr_permit(self,lease,now): self.released.append(lease)

class Client:
    repository='owner/repo'
    def __init__(self,pulls=None,state='open'): self.pulls=pulls or []; self.created=[]; self.state=state
    def find_branch(self,branch): return self.pulls
    def pull(self,n): return pull(self.state)
    def create(self,branch,title,body,draft=False): self.created.append((branch,draft)); return {'number':7}

class Agent:
    def __init__(self,client,p): self.client=client; self.coord=Coord(p); self.owner='research-owner'; self.repo=Path('.')
    def _require(self,role): assert role=='research'
    def _load(self): return {'version':1,'tasks':{'Q1':{'prepared':'.private/old.json'}}}
    def _save(self,state): self.saved=deepcopy(state)

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.time=patch.object(recovery,'now',return_value=TIME); self.time.start()
        self.fetch=patch.object(recovery,'fetch_pull',return_value=HEAD); self.fetch.start()
        self.verify=patch.object(recovery,'verify',side_effect=lambda doc,trust,role:doc['payload']); self.verify.start()
        manifest,_=snapshot(); self.blob=patch.object(recovery,'blob',return_value=encode({'key_id':'research-owner','payload':manifest})); self.blob.start()
    def tearDown(self): patch.stopall()
    def test_existing_open_or_closed_pr_is_validated_then_bound(self):
        manifest,proposals=snapshot()
        for state in ('open','closed'):
            a=Agent(Client([{'number':7}],state),permit())
            with patch.object(recovery,'proposal_snapshot',return_value=('draft',manifest,proposals,{})):
                result=recovery.recover_unbound_permits(a,TRUST)
            self.assertEqual(result[0]['status'],'bound_existing_pr'); self.assertEqual(a.coord.bound,[7]); self.assertEqual(a.client.created,[])
            self.assertEqual(a.coord.updated[0][1],'review_pending'); self.assertNotIn('prepared',a.saved['tasks']['Q1'])
    def test_bound_permit_repairs_only_missing_binding_and_preserves_revision(self):
        manifest,proposals=snapshot(); manifest['records'].append({'qid':'Q2'})
        proposals['Q2']={'key_id':'research-owner','payload':{'qid':'Q2'}}
        p={**permit(),'pr_number':7}; a=Agent(Client([{'number':7}]),p)
        a.coord.list_tasks=lambda: {'Q1':{**task(),'pr_number':7,'phase':'revision_requested','revision':1},
            'Q2':{**task(),'qid':'Q2','token':'task2','phase':'draft'}}
        a._load=lambda: {'version':1,'tasks':{'Q1':{'prepared':'.private/revision.json'},'Q2':{'prepared':'.private/initial.json'}}}
        with patch.object(recovery,'blob',return_value=encode({'key_id':'research-owner','payload':manifest})), \
             patch.object(recovery,'proposal_snapshot',return_value=('draft',manifest,proposals,{})):
            result=recovery.recover_unbound_permits(a,TRUST)
        self.assertEqual(result[0]['status'],'repaired_bound_pr')
        self.assertEqual(a.coord.updated,[('Q2','draft',{'pr_number':7})])
        self.assertEqual(a.saved['tasks']['Q1']['prepared'],'.private/revision.json')
        self.assertEqual(a.saved['tasks']['Q2']['prepared'],'.private/initial.json')
        self.assertEqual(a.coord.bound,[]); self.assertEqual(a.coord.released,[])

    def test_expired_unused_permit_released_only_after_double_check(self):
        a=Agent(Client(),permit())
        with patch.object(recovery,'_remote_head',return_value=None) as check:
            result=recovery.recover_unbound_permits(a,TRUST)
        self.assertEqual(result[0]['status'],'released_unused_permit'); self.assertEqual(len(a.coord.released),1)
        self.assertEqual(check.call_count,2); self.assertFalse(hasattr(a,'saved'))
    def test_unexpired_unused_permit_is_preserved(self):
        a=Agent(Client(),permit(FUTURE))
        with patch.object(recovery,'_remote_head',return_value=None): result=recovery.recover_unbound_permits(a,TRUST)
        self.assertEqual(result[0]['status'],'waiting_for_permit_expiry'); self.assertEqual(a.coord.released,[])
    def test_existing_public_branch_creates_one_validated_draft(self):
        manifest,proposals=snapshot(); a=Agent(Client(),permit())
        with patch.object(recovery,'_remote_head',return_value=HEAD), patch.object(recovery,'command'), \
             patch.object(recovery,'commit',return_value=HEAD), patch.object(recovery,'draft_snapshot',return_value=(manifest,proposals)), \
             patch.object(recovery,'proposal_snapshot',return_value=('draft',manifest,proposals,{})):
            result=recovery.recover_unbound_permits(a,TRUST)
        self.assertEqual(result[0]['status'],'created_draft_pr'); self.assertEqual(a.client.created,[(BRANCH,True)])
        self.assertEqual(a.coord.bound,[7]); self.assertEqual(a.coord.released,[])
    def test_invalid_or_ambiguous_public_work_is_never_released(self):
        a=Agent(Client([{'number':7},{'number':8}]),permit())
        self.assertEqual(recovery.recover_unbound_permits(a,TRUST)[0]['status'],'ambiguous_existing_pr')
        self.assertEqual(a.coord.released,[])
        manifest,proposals=snapshot(); proposals['Q1']['key_id']='other'
        a=Agent(Client([{'number':7}]),permit())
        with patch.object(recovery,'proposal_snapshot',return_value=('draft',manifest,proposals,{})):
            with self.assertRaisesRegex(ValueError,'another Research role'): recovery.recover_unbound_permits(a,TRUST)
        self.assertEqual(a.coord.bound,[]); self.assertEqual(a.coord.released,[])

if __name__=='__main__': unittest.main()
