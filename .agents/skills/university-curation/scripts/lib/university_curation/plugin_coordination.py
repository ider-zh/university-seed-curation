"""Pure GitHub-plugin coordination plans; the host performs and confirms every write."""
import copy
import hashlib
import json
import re

from .github_coordination import GitCoordinator, REF, _sha


class PluginCoordinator(GitCoordinator):
    """Plan one CAS transaction from explicitly supplied remote ref snapshots.

    A missing ref is known absent only when supplied as {sha: null, state: {}}.
    Plans are speculative until the host creates objects and successfully updates
    the ref without force. On rejection, fetch a fresh snapshot and replan.
    """
    def __init__(self, snapshot, repository=None, bootstrap_parent_sha=None):
        if not isinstance(snapshot, dict): raise ValueError("Snapshot must be an object")
        if repository is not None and (not isinstance(repository, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)): raise ValueError("Invalid repository")
        if bootstrap_parent_sha is not None: _sha(bootstrap_parent_sha)
        self.repository = repository or '$repository_full_name'
        self.bootstrap_parent_sha = bootstrap_parent_sha or '$bootstrap_parent_sha'
        self.snapshot = {}
        for name, entry in snapshot.items():
            if isinstance(name, str) and name.startswith('refs/heads/'): name = name[len('refs/heads/'):]
            if not isinstance(name, str) or not REF.fullmatch(name) or name in self.snapshot: raise ValueError("Invalid or duplicate coordination ref")
            if not isinstance(entry, dict) or set(entry) != {'sha','state'} or not isinstance(entry['state'],dict): raise ValueError("Invalid ref snapshot")
            if entry['sha'] is None:
                if entry['state'] != {}: raise ValueError("Absent ref cannot have state")
            else: _sha(entry['sha'])
            self.snapshot[name] = copy.deepcopy(entry)

    def read(self, name):
        self._ref(name)
        if name not in self.snapshot: raise ValueError("Unknown ref; obtain an explicit GitHub snapshot")
        entry = self.snapshot[name]
        return copy.deepcopy(entry['state']), entry['sha']

    def update(self, name, mutator, preserve_commit=None):
        ref = self._ref(name)
        if preserve_commit is not None: _sha(preserve_commit)
        state, old = self.read(name)
        new, result = mutator(copy.deepcopy(state))
        if not isinstance(new, dict): raise ValueError("Mutator must return a state object")
        raw = (json.dumps(new, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False) + '\n').encode('utf-8')
        if len(raw) > 5_000_000: raise ValueError("Coordination state too large")
        parent = old or self.bootstrap_parent_sha
        additional = [preserve_commit] if preserve_commit and preserve_commit != parent else []
        # The host must use the GitHub plugin's expected_sha guarded update_ref.
        return {'status':'awaiting_plugin_commit', 'ref':ref, 'expected_sha':old,
                'new_state':new, 'state_sha256':hashlib.sha256(raw).hexdigest(),
                'tentative_result':result,
                'operations':[
                    {'tool':'mcp__codex_apps__github_create_blob', 'arguments':{'repository_full_name':self.repository,'content':raw.decode('utf-8'),'encoding':'utf-8'}, 'output':'blob_sha'},
                    {'tool':'mcp__codex_apps__github_create_tree', 'arguments':{'repository_full_name':self.repository,'tree_elements':[{'path':'state.json','mode':'100644','type':'blob','sha':'$blob_sha'}]}, 'output':'tree_sha'},
                    {'tool':'mcp__codex_apps__github_create_commit', 'arguments':{'repository_full_name':self.repository,'message':'Update coordination state','tree_sha':'$tree_sha','parent_sha':parent,'additional_parent_shas':additional}, 'output':'commit_sha'},
                    ({'tool':'mcp__codex_apps__github_update_ref','arguments':{'repository_full_name':self.repository,'branch_name':name,'sha':'$commit_sha','expected_sha':old,'force':False}} if old else
                     {'tool':'mcp__codex_apps__github_create_branch','arguments':{'repository_full_name':self.repository,'branch_name':name,'sha':'$commit_sha'}})
                ],
                'on_conflict':'read_ref_and_replan', 'finalization':'confirm_ref_matches_created_commit'}

    def list_tasks(self):
        raise ValueError("Enumeration requires an authoritative GitHub ref listing; read each listed shard explicitly")


ALLOWED_ACTIONS = frozenset({'claim_task','heartbeat_task','set_task','acquire_model','renew_model','release_model',
    'acquire_pr_permit','bind_pr_permit','renew_pr_permit','release_pr_permit','enqueue_review','claim_review','renew_review','finish_review'})


def plan(snapshot, action, arguments, repository=None, bootstrap_parent_sha=None):
    if action not in ALLOWED_ACTIONS: raise ValueError("Unsupported coordination action")
    if not isinstance(arguments, dict): raise ValueError("Action arguments must be an object")
    return getattr(PluginCoordinator(snapshot, repository, bootstrap_parent_sha), action)(**arguments)
