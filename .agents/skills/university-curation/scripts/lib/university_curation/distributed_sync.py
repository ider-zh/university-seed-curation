"""Research-side reconciliation using GitHub refs, PRs and signed comments only."""
from datetime import datetime, timedelta, timezone

from .attestations import sha, verify
from .records import encode, instant
from .pr_export import blob
from .distributed_protocol import (trust_at, catalog_at, check_proposal,
    baseline_at, read_reviews, check_decision)
from .distributed_feedback import requests_from_comments
from .distributed_transport import (fetch_main, fetch_pull, proposal_snapshot,
    comments, apply_reviews)
from .distributed_recovery import recover_unbound_permits


def now(): return datetime.now(timezone.utc).isoformat()


def _lease(agent, entity, remote):
    if remote.get('owner') != agent.owner: raise ValueError('Task belongs to another Research identity')
    if remote.get('token') and remote.get('expires_at') and instant(remote['expires_at']) > instant(now()):
        lease = {k: remote[k] for k in ('qid','owner','token','expires_at')}
        agent.coord.heartbeat_task(lease, now()); return lease
    return agent.coord.claim_task(entity, agent.owner, now(), allow_resume=True)


def sync(agent):
    """Return next actions; finalize only approved schools, never merge a PR."""
    agent._require('research')
    base = fetch_main(agent.repo); trust = trust_at(agent.repo, base)
    catalog, digest = catalog_at(agent.repo, base, trust)
    recovery = recover_unbound_permits(agent, trust)
    tasks = agent.coord.list_tasks(); runtime, _ = agent.coord.read('coord/runtime')
    permits = [p for p in runtime.get('pr_permits',[]) if p.get('owner') == agent.owner]
    numbers = {v['pr_number'] for v in tasks.values() if v.get('owner') == agent.owner and v.get('pr_number') and v.get('phase') not in ('merged','unresolved')}
    numbers.update(p['pr_number'] for p in permits if p.get('pr_number'))
    results = []
    for number in sorted(numbers):
        pull = agent.client.pull(number)
        if pull.get('base',{}).get('ref') != 'main' or (pull.get('head',{}).get('repo') or {}).get('full_name') != trust['repository']:
            raise ValueError('Tracked PR no longer targets this repository main')
        head = fetch_pull(agent.repo, number, pull['head']['sha'])
        stage, manifest, proposals, embedded = proposal_snapshot(agent.repo, pull, trust)
        owned = {q:v for q,v in tasks.items() if q in proposals and v.get('owner') == agent.owner and v.get('pr_number') == number}
        if set(owned) != set(proposals): raise ValueError('PR has tasks not assigned to this Research identity')
        if pull.get('state') != 'open':
            merged = bool(pull.get('merged') or pull.get('merged_at'))
            for entity, remote in owned.items():
                if remote.get('phase') in ('merged','unresolved'): continue
                lease = _lease(agent, entity, remote)
                if merged:
                    if stage != 'final': raise ValueError('A Draft proposal was merged without approved records')
                    row = next(r for r in manifest['records'] if r['qid'] == entity)
                    # Immutable receipt in actual main confirms integration even
                    # if a later accepted PR has already updated the school.
                    if sha(blob(agent.repo, base, row['receipt_path'])) != row['receipt_sha256']:
                        raise ValueError('Merged receipt is not present in main')
                    verdict = verify(embedded[entity], trust, role='review')
                    metadata = {'head_sha':head,'published_at':verdict['reviewed_at']}
                    if not verdict['full_refresh']:
                        metadata['retry_after'] = (instant(verdict['reviewed_at']) + timedelta(days=7)).isoformat()
                    agent.coord.set_task(lease,'merged',now(),**metadata)
                else:
                    agent.coord.set_task(lease,'unresolved',now(),head_sha=head,reason_code='pr_closed_unmerged')
            for permit in permits:
                if permit.get('pr_number') == number: agent.coord.release_pr_permit(permit,now())
            results.append({'pr_number':number,'status':'merged' if merged else 'closed_unmerged'}); continue

        notes = comments(agent.client, number); approvals = {}; actions = []; terminal = []
        for entity, document in proposals.items():
            remote = owned[entity]
            if remote.get('phase') == 'unresolved': terminal.append(entity); continue
            proposal = verify(document,trust,role='research'); baseline,_ = baseline_at(agent.repo,base,entity)
            try: check_proposal(proposal,baseline,catalog,digest,trust)
            except ValueError:
                # No overwrite on same-QID/schema/catalog change. Research must
                # produce a fresh proposal; unrelated main changes need no model.
                if remote.get('revision',0) >= 2:
                    agent.coord.set_task(_lease(agent,entity,remote),'unresolved',now(),head_sha=head,reason_code='revision_limit')
                    terminal.append(entity)
                else: actions.append({'qid':entity,'action':'research','pr_number':number,'reason':'baseline_or_contract_changed'})
                continue
            history = read_reviews(notes,trust,number,entity,sha(encode(proposal)))
            decision = None; verdict = None
            if history:
                decision = history[-1][0]; verdict,_ = check_decision(decision,document,baseline,trust,number)
            outstanding = requests_from_comments(notes,trust,number,entity,resolved_by=decision if verdict and verdict['decision']=='approve' else None)
            if verdict and verdict['decision']=='approve' and not outstanding:
                approvals[entity] = decision
            elif (verdict and verdict['decision']=='unresolved') or (outstanding and remote.get('revision',0)>=2):
                agent.coord.set_task(_lease(agent,entity,remote),'unresolved',now(),head_sha=head,reason_code='review_unresolved')
                terminal.append(entity)
            elif outstanding:
                lease = _lease(agent,entity,remote)
                agent.coord.set_task(lease,'revision_requested',now(),head_sha=head)
                actions.append({'qid':entity,'action':'research','pr_number':number,'reason':'signed_review_requests'})
            else: actions.append({'qid':entity,'action':'wait_review','pr_number':number})
        if actions:
            results.append({'pr_number':number,'status':'actions_required','actions':actions,'unresolved':terminal}); continue
        if not approvals:
            # Keep the Draft and its failed signed proposals visible. Do not
            # automatically close or resubmit it under another PR.
            for permit in permits:
                if permit.get('pr_number')==number: agent.coord.release_pr_permit(permit,now())
            results.append({'pr_number':number,'status':'unresolved','qids':terminal}); continue
        if stage=='final' and manifest['base_commit']==base and not terminal:
            results.append({'pr_number':number,'status':'awaiting_human_merge','qids':sorted(approvals)}); continue
        # Archive the exact old public head through coordination ancestry before
        # replacing the branch with main + approved-only canonical data.
        leases = {}
        for entity in approvals:
            lease = _lease(agent,entity,owned[entity]); leases[entity] = lease
            agent.coord.set_task(lease,'approved',now(),head_sha=head)
        result = apply_reviews(agent.repo,agent.client,number,agent.key,agent.root/'worktrees',approved_qids=set(approvals))
        for entity,lease in leases.items():
            agent.coord.set_task(lease,'published',now(),head_sha=result['head_sha'],base_sha=base)
        result['unresolved'] = terminal; results.append(result)
    return {'status':'synchronized','recovery':recovery,'results':results}
