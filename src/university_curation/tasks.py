"""Private fixed-snapshot refresh queues with leases, fencing and a shared model budget."""
import base64
import calendar
from contextlib import contextmanager
from datetime import timedelta
import json
from pathlib import Path
import secrets
import sqlite3

from .records import instant, read, digest, validate, record_path


def cutoff(as_of):
    stamp = instant(as_of); month_index = stamp.year * 12 + stamp.month - 1 - 6
    year, month0 = divmod(month_index, 12); month = month0 + 1
    return stamp.replace(year=year, month=month, day=min(stamp.day, calendar.monthrange(year, month)[1]))


class Queue:
    def __init__(self, path):
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,as_of TEXT NOT NULL,cutoff TEXT NOT NULL,base_ref TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS tasks(
            id INTEGER PRIMARY KEY,run_id TEXT NOT NULL,qid TEXT NOT NULL,base_digest TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending',revisions INTEGER NOT NULL DEFAULT 0,
            research_actor TEXT,research_session TEXT,review_actor TEXT,review_session TEXT,token TEXT,lease_until TEXT,
            generation INTEGER NOT NULL DEFAULT 0,proposal TEXT,proposal_digest TEXT,receipt TEXT,next_attempt_after TEXT,
            UNIQUE(run_id,qid));
          CREATE TABLE IF NOT EXISTS attempts(
            id INTEGER PRIMARY KEY,task_id INTEGER NOT NULL,kind TEXT NOT NULL,
            actor TEXT NOT NULL,session TEXT NOT NULL,created_at TEXT NOT NULL,
            payload TEXT NOT NULL,payload_digest TEXT NOT NULL);
        """)

    def close(self): self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK"); raise

    def snapshot(self, workspace, as_of, base_ref):
        threshold = cutoff(as_of); selected = []; seen = set()
        for path in (Path(workspace) / "data" / "universities").glob("*/*.json"):
            record = read(path); validate(record)
            if path.resolve() != record_path(workspace, record["qid"]): raise ValueError("Record path does not match QID bucket")
            if record["qid"] in seen: raise ValueError("Duplicate QID in record tree")
            seen.add(record["qid"])
            if record["curation"]["identity_status"] == "excluded": continue
            updated = record.get("update_datetime")
            if not updated or instant(updated) <= threshold:
                selected.append((instant(updated).isoformat() if updated else "", int(record["qid"][1:]), record))
        selected.sort(key=lambda row: (row[0], row[1])); run = secrets.token_hex(8)
        with self.transaction():
            self.db.execute("INSERT INTO runs VALUES(?,?,?,?)", (run, instant(as_of).isoformat(), threshold.isoformat(), base_ref))
            self.db.executemany("INSERT INTO tasks(run_id,qid,base_digest) VALUES(?,?,?)", [(run, r["qid"], digest(r)) for _, _, r in selected])
        return {"run_id": run, "records": len(selected), "as_of": instant(as_of).isoformat(), "cutoff": threshold.isoformat()}

    def page(self, run, limit=10, cursor=None):
        if not 1 <= limit <= 100: raise ValueError("Limit must be between 1 and 100")
        after = 0
        if cursor:
            value = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            if value["run"] != run: raise ValueError("Cursor belongs to another snapshot")
            after = int(value["after"])
        if not self.db.execute("SELECT 1 FROM runs WHERE id=?", (run,)).fetchone(): raise ValueError("Unknown snapshot")
        rows = [dict(r) for r in self.db.execute("SELECT id,qid,state,base_digest FROM tasks WHERE run_id=? AND id>? ORDER BY id LIMIT ?", (run, after, limit + 1))]
        more = len(rows) > limit; rows = rows[:limit]
        result = {"run_id": run, "tasks": rows}
        if more:
            result["next_cursor"] = base64.urlsafe_b64encode(json.dumps({"run": run, "after": rows[-1]["id"]}).encode()).decode()
        return result

    def _expire(self, now):
        self.db.execute("""UPDATE tasks SET state=CASE WHEN state='researching' THEN 'pending' ELSE 'ready_for_review' END,
            token=NULL,lease_until=NULL,generation=generation+1 WHERE state IN('researching','reviewing') AND lease_until<=?""", (now,))

    def claim(self, run, role, actor, session, now, lease_seconds=1800):
        if role not in ("research", "review"): raise ValueError("Unknown agent role")
        if not actor or not session: raise ValueError("Actor and fresh session identifiers required")
        if lease_seconds < 1: raise ValueError("Positive lease duration required")
        now = instant(now).isoformat(); until = (instant(now) + timedelta(seconds=lease_seconds)).isoformat()
        with self.transaction():
            self._expire(now)
            if self.db.execute("SELECT count(*) FROM tasks WHERE state IN('researching','reviewing')").fetchone()[0] >= 3:
                return {"available": False, "reason": "shared_model_budget_full"}
            if role == "review" and self.db.execute("SELECT 1 FROM tasks WHERE state='reviewing'").fetchone():
                return {"available": False, "reason": "single_review_agent_busy"}
            if role == "research" and self.db.execute("SELECT 1 FROM tasks WHERE state='ready_for_review'").fetchone():
                active = self.db.execute("SELECT count(*) FROM tasks WHERE state IN('researching','reviewing')").fetchone()[0]
                if active >= 2 and not self.db.execute("SELECT 1 FROM tasks WHERE state='reviewing'").fetchone():
                    return {"available": False, "reason": "reserve_slot_for_review"}
            if role == "research":
                row = self.db.execute("""SELECT t.* FROM tasks t WHERE t.run_id=? AND t.state IN('pending','changes_requested')
                    AND NOT EXISTS(SELECT 1 FROM tasks a WHERE a.qid=t.qid AND a.id<>t.id
                      AND a.state IN('researching','ready_for_review','reviewing','changes_requested','approved','applied'))
                    AND NOT EXISTS(SELECT 1 FROM tasks a WHERE a.qid=t.qid AND a.state='unresolved' AND a.next_attempt_after>?)
                    ORDER BY t.id LIMIT 1""", (run, now)).fetchone()
            else:
                row = self.db.execute("""SELECT * FROM tasks WHERE run_id=? AND state='ready_for_review'
                    AND research_actor<>? AND research_session<>? ORDER BY id LIMIT 1""", (run, actor, session)).fetchone()
            if row is None: return {"available": False, "reason": "no_eligible_task"}
            token = secrets.token_hex(24); state = "researching" if role == "research" else "reviewing"
            self.db.execute("UPDATE tasks SET state=?,token=?,lease_until=?,generation=generation+1 WHERE id=?", (state, token, until, row["id"]))
            if role == "research":
                self.db.execute("UPDATE tasks SET research_actor=?,research_session=? WHERE id=?", (actor, session, row["id"]))
            else: self.db.execute("UPDATE tasks SET review_actor=?,review_session=? WHERE id=?", (actor, session, row["id"]))
            return {"available": True, "task_id": row["id"], "qid": row["qid"], "base_digest": row["base_digest"],
                    "lease_token": token, "lease_until": until, "role": role}

    def _owned(self, task, token, now, state):
        row = self.db.execute("SELECT * FROM tasks WHERE id=?", (task,)).fetchone()
        if row is None or row["state"] != state or row["token"] != token or instant(row["lease_until"]) <= instant(now):
            raise ValueError("Expired/stale lease or incorrect role")
        return row

    def heartbeat(self, task, token, now, lease_seconds=1800):
        with self.transaction():
            row = self.db.execute("SELECT state FROM tasks WHERE id=?", (task,)).fetchone()
            if row is None or row["state"] not in ("researching", "reviewing"): raise ValueError("No live lease")
            self._owned(task, token, now, row["state"])
            until = (instant(now) + timedelta(seconds=lease_seconds)).isoformat()
            self.db.execute("UPDATE tasks SET lease_until=? WHERE id=?", (until, task))
        return {"lease_until": until}

    def submit(self, task, token, now, proposal):
        with self.transaction():
            row = self._owned(task, token, now, "researching")
            if proposal.get("qid") != row["qid"] or proposal.get("base_digest") != row["base_digest"]:
                raise ValueError("Proposal binds another QID/baseline")
            self.db.execute("UPDATE tasks SET state='ready_for_review',proposal=?,proposal_digest=?,token=NULL,lease_until=NULL WHERE id=?",
                            (json.dumps(proposal, ensure_ascii=False), digest(proposal), task))
            self.db.execute("INSERT INTO attempts(task_id,kind,actor,session,created_at,payload,payload_digest) VALUES(?,?,?,?,?,?,?)",
                (task, "research", row["research_actor"], row["research_session"], instant(now).isoformat(), json.dumps(proposal, ensure_ascii=False), digest(proposal)))
        return {"state": "ready_for_review"}

    def decide(self, task, token, now, decision, review_session, source_checks=(), reviewed_groups=()):
        if decision not in ("approve", "request_changes", "unresolved"): raise ValueError("Unknown decision")
        with self.transaction():
            row = self._owned(task, token, now, "reviewing")
            if not review_session or review_session != row["review_session"] or review_session == row["research_session"]:
                raise ValueError("Independent allocated review session required")
            proposal = json.loads(row["proposal"])
            if decision == "approve":
                expected = set(proposal.get("changed_claim_ids", []))
                if {c.get("claim_id") for c in source_checks} != expected or any(c.get("verdict") != "supported" for c in source_checks):
                    raise ValueError("Every changed fact requires an affirmative source check")
            if decision == "approve": state = "approved"
            elif decision == "unresolved" or row["revisions"] >= 2: state = "unresolved"
            else: state = "changes_requested"
            receipt = {"qid": row["qid"], "task_id": task, "decision": decision, "base_digest": row["base_digest"],
                "proposal_digest": row["proposal_digest"], "research_actor": row["research_actor"],
                "research_session": row["research_session"], "review_actor": row["review_actor"],
                "review_session": review_session, "reviewed_at": instant(now).isoformat()}
            receipt["reviewed_groups"] = list(reviewed_groups)
            review_payload = {"receipt": receipt, "source_checks": list(source_checks)}
            self.db.execute("INSERT INTO attempts(task_id,kind,actor,session,created_at,payload,payload_digest) VALUES(?,?,?,?,?,?,?)",
                (task, "review", row["review_actor"], review_session, instant(now).isoformat(), json.dumps(review_payload, ensure_ascii=False), digest(review_payload)))
            retry = (instant(now) + timedelta(days=7)).isoformat() if state == "unresolved" else None
            self.db.execute("UPDATE tasks SET state=?,revisions=revisions+?,receipt=?,token=NULL,lease_until=NULL,next_attempt_after=? WHERE id=?",
                            (state, int(state == "changes_requested"), json.dumps(receipt), retry, task))
        return {"state": state, "receipt": receipt}

    def private_packet(self, task):
        row = self.db.execute("SELECT * FROM tasks WHERE id=?", (task,)).fetchone()
        if row is None: raise ValueError("Unknown task")
        value = {"task_id": task, "qid": row["qid"], "state": row["state"]}
        if row["proposal"]: value["proposal"] = json.loads(row["proposal"])
        if row["receipt"]: value["receipt"] = json.loads(row["receipt"])
        return value

    def mark_applied(self, task):
        with self.transaction():
            row = self.db.execute("SELECT state FROM tasks WHERE id=?", (task,)).fetchone()
            if row is None or row["state"] not in ("approved", "applied"): raise ValueError("Approved task required")
            self.db.execute("UPDATE tasks SET state='applied' WHERE id=?", (task,))
