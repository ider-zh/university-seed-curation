"""GitHub ref based, fenced coordination; no shared local state is authoritative."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import threading
import time

from .records import instant, qid as check_qid

REF = re.compile(r"(?:coord/tasks-[0-9a-f]{2}|coord/runtime)\Z")
HEX = re.compile(r"[0-9a-f]{40}\Z")
TASK_PHASES = {"claimed", "draft", "review_pending", "revision_requested", "approved", "published", "merged", "unresolved", "released"}
META = {"pr_number", "head_sha", "base_sha", "policy_hash", "reason_code", "batch_id", "revision", "proposal_sha256", "record_sha256", "review_comment_id", "published_at", "retry_after"}


def _now(): return datetime.now(timezone.utc).isoformat()
def _stamp(value): return instant(value).isoformat()
def _until(value, ttl):
    if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl < 1: raise ValueError("Positive TTL required")
    return (instant(value) + timedelta(seconds=ttl)).isoformat()
def _owner(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:@-]{1,128}", value): raise ValueError("Invalid owner/job identifier")
    return value

def _sha(value):
    if not isinstance(value, str) or not HEX.fullmatch(value): raise ValueError("Invalid SHA")
    return value

def _validate_metadata(metadata):
    if set(metadata) - META: raise ValueError("Unsupported coordination metadata")
    for key, value in metadata.items():
        if key in ("pr_number", "review_comment_id"):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1: raise ValueError("Invalid PR number")
        elif key in ("head_sha", "base_sha", "policy_hash", "proposal_sha256", "record_sha256"):
            if key in ("policy_hash", "proposal_sha256", "record_sha256"):
                if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value): raise ValueError("Invalid policy hash")
            else: _sha(value)
        elif key == "revision":
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 2: raise ValueError("Invalid revision")
        elif key == "batch_id":
            if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", value): raise ValueError("Invalid batch ID")
        elif key in ("published_at", "retry_after"): _stamp(value)
        elif not isinstance(value, str) or not re.fullmatch(r"[a-z_]{1,64}", value): raise ValueError("Invalid reason code")


class GitCoordinator:
    def __init__(self, repo): self.repo = Path(repo).resolve()
    def _git(self, *args, data=None, check=True):
        p = subprocess.run(["git", "-C", str(self.repo), *args], input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        if check and p.returncode: raise RuntimeError("Git coordination command failed: " + args[0])
        return p
    def _ref(self, name):
        if not isinstance(name, str) or not REF.fullmatch(name): raise ValueError("Invalid coordination ref")
        return "refs/heads/" + name
    def read(self, name):
        ref = self._ref(name)
        for _ in range(8):
            remote = self._git("ls-remote", "--refs", "origin", ref).stdout.decode().strip()
            if not remote: return {}, None
            fields = remote.split()
            if len(fields) != 2 or fields[1] != ref: raise RuntimeError("Invalid remote ref response")
            expected = _sha(fields[0])
            local = "refs/codex-coordination/" + secrets.token_hex(16)
            try:
                fetched = self._git("fetch", "--no-tags", "origin", "+" + ref + ":" + local, check=False)
                if fetched.returncode: continue
                actual = self._git("rev-parse", local).stdout.decode().strip()
                if actual != expected: continue
                raw = self._git("show", expected + ":state.json").stdout
                if len(raw) > 5_000_000: raise ValueError("Coordination state too large")
                state = json.loads(raw)
                if not isinstance(state, dict): raise ValueError("Invalid coordination state")
                return state, expected
            finally:
                self._git("update-ref", "-d", local, check=False)
        raise RuntimeError("Coordination ref changed repeatedly during read")
    def update(self, name, mutator, preserve_commit=None):
        ref = self._ref(name)
        if preserve_commit is not None: _sha(preserve_commit)
        for _ in range(8):
            state, old = self.read(name)
            new, result = mutator(state)
            if not isinstance(new, dict): raise ValueError("Mutator must return a state object")
            if new == state and preserve_commit is None: return result
            raw = (json.dumps(new, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode()
            if len(raw) > 5_000_000: raise ValueError("Coordination state too large")
            blob = self._git("hash-object", "-w", "--stdin", data=raw).stdout.decode().strip()
            tree = self._git("mktree", data=("100644 blob " + blob + "\tstate.json\n").encode()).stdout.decode().strip()
            parents = (["-p", old] if old else []) + (["-p", preserve_commit] if preserve_commit and preserve_commit != old else [])
            commit = self._git("-c", "user.name=University Research Agent", "-c", "user.email=research-agent@users.noreply.github.com", "commit-tree", tree, *parents,
                               data=b"Update coordination state\n").stdout.decode().strip()
            push = self._git("push", "--force-with-lease=" + ref + ":" + (old or ""), "origin", commit + ":" + ref, check=False)
            if push.returncode == 0: return result
            # Retry only if the observed ref actually changed, not on authentication/transport errors.
            _, current = self.read(name)
            if current == old: raise RuntimeError("Coordination push failed")
        raise RuntimeError("Coordination contention exceeded retry limit")
    @staticmethod
    def _task_ref(qid):
        check_qid(qid)
        return "coord/tasks-" + hashlib.sha256(qid.encode()).hexdigest()[:2]
    def claim_task(self, qid, owner, now, ttl=1800, allow_resume=False):
        ref = self._task_ref(qid); _owner(owner); now = _stamp(now); expires = _until(now, ttl)
        def mutate(state):
            new = dict(state); tasks = dict(new.get("tasks", {})); current = tasks.get(qid)
            if current and current.get("phase") not in ("claimed", "released") and not allow_resume: raise ValueError("Existing task requires explicit resume")
            if current and current.get("token") and instant(current["expires_at"]) > instant(now): raise ValueError("Task already leased")
            lease = {"qid": qid, "owner": owner, "token": secrets.token_hex(24), "expires_at": expires}
            tasks[qid] = {**(current or {}), **lease, "phase": "claimed"}; new["tasks"] = tasks
            return new, lease
        return self.update(ref, mutate)
    def heartbeat_task(self, lease, now, ttl=1800):
        ref = self._task_ref(lease["qid"]); expires = _until(now, ttl)
        def mutate(state):
            task = self._owned_task(state, lease, now)
            new = dict(state); tasks = dict(new["tasks"]); tasks[lease["qid"]] = {**task, "expires_at": expires}; new["tasks"] = tasks
            return new, {**lease, "expires_at": expires}
        return self.update(ref, mutate)
    @staticmethod
    def _owned_task(state, lease, now):
        task = state.get("tasks", {}).get(lease["qid"], {})
        if not lease.get("token") or task.get("token") != lease["token"] or task.get("owner") != lease.get("owner") or not task.get("expires_at") or instant(task["expires_at"]) <= instant(now): raise ValueError("Expired or stale task lease")
        return task
    def set_task(self, lease, phase, now, **metadata):
        if phase not in TASK_PHASES: raise ValueError("Invalid task phase")
        _validate_metadata(metadata); ref = self._task_ref(lease["qid"])
        def mutate(state):
            task = self._owned_task(state, lease, now); new = dict(state); tasks = dict(new["tasks"])
            updated = {**task, **metadata, "phase": phase}
            if phase in ("merged", "unresolved", "released"): updated.pop("token", None); updated.pop("expires_at", None)
            tasks[lease["qid"]] = updated; new["tasks"] = tasks
            return new, dict(updated)
        return self.update(ref, mutate, preserve_commit=metadata.get("head_sha"))
    def list_tasks(self):
        tasks = {}
        remote = self._git("ls-remote", "--refs", "origin", "refs/heads/coord/tasks-*").stdout.decode()
        names = []
        for line in remote.splitlines():
            parts = line.split()
            if len(parts) != 2 or not parts[1].startswith("refs/heads/"): raise ValueError("Invalid task ref listing")
            name = parts[1].removeprefix("refs/heads/")
            if not re.fullmatch(r"coord/tasks-[0-9a-f]{2}", name): raise ValueError("Invalid task shard ref")
            names.append(name)
        for name in sorted(names):
            state, _ = self.read(name)
            tasks.update(state.get("tasks", {}))
        return tasks
    def acquire_model(self, role, owner, job, now, ttl=180):
        if role not in ("research", "review"): raise ValueError("Invalid role")
        _owner(owner); _owner(job); stamp = _stamp(now); expiry = _until(now, ttl)
        def mutate(state):
            new = dict(state); slots = [x for x in state.get("slots", []) if instant(x["expires_at"]) > instant(stamp)]
            waiting = any(x.get("status") == "pending" or (x.get("status") == "claimed" and instant(x["expires_at"]) <= instant(stamp)) for x in state.get("reviews", {}).values())
            if len(slots) >= 3 or (role == "review" and any(x["role"] == "review" for x in slots)) or (role == "research" and waiting and len(slots) >= 2 and not any(x["role"] == "review" for x in slots)):
                new["slots"] = slots
                return new, None
            lease = {"role": role, "owner": owner, "job": job, "token": secrets.token_hex(24), "expires_at": expiry}
            new["slots"] = slots + [lease]; return new, lease
        return self.update("coord/runtime", mutate)
    def _model_change(self, lease, now, ttl=None):
        def mutate(state):
            new = dict(state); slots = list(state.get("slots", [])); match = next((x for x in slots if x.get("token") == lease.get("token") and x.get("owner") == lease.get("owner") and x.get("job") == lease.get("job") and x.get("role") == lease.get("role")), None)
            if not lease.get("token") or not match or instant(match["expires_at"]) <= instant(now): raise ValueError("Expired or stale model lease")
            slots.remove(match)
            result = None
            if ttl is not None:
                result = {**match, "expires_at": _until(now, ttl)}; slots.append(result)
            new["slots"] = slots; return new, result
        return self.update("coord/runtime", mutate)
    def renew_model(self, lease, now, ttl=180): return self._model_change(lease, now, ttl)
    def release_model(self, lease, now): return self._model_change(lease, now)
    def acquire_pr_permit(self, owner, batch_id, now, ttl=1800, reclaim_expired=False):
        _owner(owner); _validate_metadata({"batch_id": batch_id}); expiry = _until(now, ttl)
        def mutate(state):
            new = dict(state); permits = list(state.get("pr_permits", []))
            if reclaim_expired:
                permits = [p for p in permits if p.get("pr_number") or instant(p["expires_at"]) > instant(now)]
            if any(p["batch_id"] == batch_id for p in permits) or len(permits) >= 3:
                new["pr_permits"] = permits; return new, None
            lease = {"owner": owner, "batch_id": batch_id, "token": secrets.token_hex(24), "expires_at": expiry}
            new["pr_permits"] = permits + [lease]; return new, dict(lease)
        return self.update("coord/runtime", mutate)
    def _pr_permit_change(self, lease, now, action, value=None):
        def mutate(state):
            new = dict(state); permits = list(state.get("pr_permits", []))
            match = next((p for p in permits if p.get("token") == lease.get("token") and p.get("owner") == lease.get("owner") and p.get("batch_id") == lease.get("batch_id")), None)
            if not lease.get("token") or not match: raise ValueError("Stale PR permit")
            if action == "renew" and not match.get("pr_number") and instant(match["expires_at"]) <= instant(now): raise ValueError("Expired PR permit; verify branch before recovery")
            permits.remove(match); result = None
            if action == "bind":
                _validate_metadata({"pr_number": value})
                if match.get("pr_number") not in (None, value): raise ValueError("PR permit already bound")
                result = {**match, "pr_number": value}; permits.append(result)
            elif action == "renew":
                result = {**match, "expires_at": _until(now, value)}; permits.append(result)
            new["pr_permits"] = permits; return new, result
        return self.update("coord/runtime", mutate)
    def bind_pr_permit(self, lease, pr_number, now): return self._pr_permit_change(lease, now, "bind", pr_number)
    def renew_pr_permit(self, lease, now, ttl=1800): return self._pr_permit_change(lease, now, "renew", ttl)
    def release_pr_permit(self, lease, now): return self._pr_permit_change(lease, now, "release")
    def enqueue_review(self, pr_number, head_sha, base_sha, policy_hash, now):
        _validate_metadata({"pr_number": pr_number, "head_sha": head_sha, "base_sha": base_sha, "policy_hash": policy_hash}); stamp = _stamp(now)
        def mutate(state):
            new = dict(state); reviews = dict(state.get("reviews", {})); key = str(pr_number); current = reviews.get(key)
            if current and current["head_sha"] == head_sha and current["base_sha"] == base_sha and current["policy_hash"] == policy_hash: return state, dict(current)
            if len(reviews) >= 1000 and key not in reviews:
                done = sorted((v["updated_at"], k) for k, v in reviews.items() if v["status"] == "complete")
                if not done: raise ValueError("Review queue full")
                reviews.pop(done[0][1])
            item = {"pr_number": pr_number, "head_sha": head_sha, "base_sha": base_sha, "policy_hash": policy_hash, "status": "pending", "updated_at": stamp}
            reviews[key] = item; new["reviews"] = reviews; return new, item
        return self.update("coord/runtime", mutate)
    def claim_review(self, owner, now, ttl=1800):
        _owner(owner); stamp = _stamp(now); expiry = _until(now, ttl)
        def mutate(state):
            new = dict(state); reviews = dict(state.get("reviews", {}))
            available = [x for x in reviews.values() if x["status"] == "pending" or (x["status"] == "claimed" and instant(x["expires_at"]) <= instant(stamp))]
            if not available: return state, None
            item = min(available, key=lambda x: (x["updated_at"], x["pr_number"]))
            lease = {**item, "status": "claimed", "owner": owner, "token": secrets.token_hex(24), "expires_at": expiry, "updated_at": stamp}
            reviews[str(item["pr_number"])] = lease; new["reviews"] = reviews; return new, dict(lease)
        return self.update("coord/runtime", mutate)
    def finish_review(self, lease, outcome, now):
        if outcome not in ("approved", "changes_requested", "unresolved"): raise ValueError("Invalid review outcome")
        def mutate(state):
            new = dict(state); reviews = dict(state.get("reviews", {})); item = reviews.get(str(lease["pr_number"]), {})
            if not lease.get("token") or item.get("token") != lease["token"] or item.get("owner") != lease.get("owner") or item.get("head_sha") != lease.get("head_sha") or item.get("status") != "claimed" or instant(item["expires_at"]) <= instant(now): raise ValueError("Expired, stale or superseded review lease")
            item = {k: v for k, v in item.items() if k not in ("token", "owner", "expires_at")}; item.update(status="complete", outcome=outcome, updated_at=_stamp(now))
            reviews[str(lease["pr_number"])] = item; new["reviews"] = reviews; return new, dict(item)
        return self.update("coord/runtime", mutate)
    def renew_review(self, lease, now, ttl=1800):
        def mutate(state):
            new = dict(state); reviews = dict(state.get("reviews", {})); item = reviews.get(str(lease["pr_number"]), {})
            if not lease.get("token") or item.get("token") != lease["token"] or item.get("owner") != lease.get("owner") or item.get("head_sha") != lease.get("head_sha") or item.get("status") != "claimed" or instant(item["expires_at"]) <= instant(now): raise ValueError("Expired, stale or superseded review lease")
            item = {**item, "expires_at": _until(now, ttl)}; reviews[str(lease["pr_number"])] = item; new["reviews"] = reviews
            return new, dict(item)
        return self.update("coord/runtime", mutate)


class CapacityBusy(RuntimeError):
    """Model capacity remained unavailable until the bounded wait expired."""


class GitModelBudget:
    def __init__(self, coord, role, owner, job, cancel_event=None, ttl=180, clock=_now, wait_timeout=600, poll_interval=2):
        self.coord, self.role, self.owner, self.job, self.ttl, self.clock = coord, role, owner, job, ttl, clock
        self.cancel_event = cancel_event or threading.Event(); self.stop = threading.Event(); self.lease = None
        self.wait_timeout, self.poll_interval = wait_timeout, poll_interval
    def __enter__(self):
        deadline = time.monotonic() + self.wait_timeout
        while not self.cancel_event.is_set():
            self.lease = self.coord.acquire_model(self.role, self.owner, self.job, self.clock(), self.ttl)
            if self.lease is not None: break
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise CapacityBusy("Global model capacity unavailable")
            self.cancel_event.wait(min(self.poll_interval, remaining))
        if self.lease is None: raise CapacityBusy("Model capacity wait cancelled")
        def heartbeat():
            while not self.stop.wait(self.ttl / 3):
                try: self.lease = self.coord.renew_model(self.lease, self.clock(), self.ttl)
                except Exception: self.cancel_event.set(); return
        self.thread = threading.Thread(target=heartbeat, daemon=True); self.thread.start(); return self
    def __exit__(self, exc_type, exc, tb):
        self.stop.set(); self.thread.join(timeout=2)
        if self.thread.is_alive():
            self.cancel_event.set()
            return False
        try: self.coord.release_model(self.lease, self.clock())
        except Exception: self.cancel_event.set()
        return False
