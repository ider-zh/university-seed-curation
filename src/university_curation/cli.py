"""Offline command facade for the built-in curation skill."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

from .records import read, encode, validate, record_path, initial, create, digest, proposal, finish_candidate, apply_reviewed
from .tasks import Queue


def emit(value): print(json.dumps(value, ensure_ascii=False, allow_nan=False))


def save_private(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    if ".private" not in path.resolve().parts: raise ValueError("Unreviewed work must be saved under a .private directory")
    with path.open("xb") as stream: stream.write(encode(value))


def seed_rows(path):
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq
        for batch in pq.ParquetFile(path).iter_batches(batch_size=256):
            yield from batch.to_pylist()
    else:
        value = read(path)
        if not isinstance(value, list): raise ValueError("Seed JSON must be a record array")
        yield from value


def main():
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", default=".private/state/queue.sqlite3")
    parser.add_argument("--now", default=datetime.now(timezone.utc).isoformat())
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("path"); p.add_argument("qid"); p.add_argument("--workspace", default=".")
    p = sub.add_parser("validate"); p.add_argument("path")
    p = sub.add_parser("seed-init")
    p.add_argument("--input", required=True); p.add_argument("--manifest", required=True)
    p.add_argument("--output", default=".private/bootstrap"); p.add_argument("--write", action="store_true")
    p.add_argument("--limit", type=int); p.add_argument("--acceptance")
    p = sub.add_parser("snapshot"); p.add_argument("--workspace", default="."); p.add_argument("--base-ref", required=True)
    p = sub.add_parser("tasks"); p.add_argument("--run", required=True); p.add_argument("--cursor"); p.add_argument("--limit", type=int, default=10)
    p = sub.add_parser("claim"); p.add_argument("--run", required=True); p.add_argument("--role", choices=("research", "review"), required=True)
    p.add_argument("--actor", required=True); p.add_argument("--session", required=True)
    p = sub.add_parser("heartbeat"); p.add_argument("--task", type=int, required=True); p.add_argument("--lease", required=True)
    p = sub.add_parser("propose"); p.add_argument("qid"); p.add_argument("--workspace", default=".")
    p.add_argument("--changes", required=True); p.add_argument("--output", required=True); p.add_argument("--groups", nargs="+")
    p = sub.add_parser("submit"); p.add_argument("--task", type=int, required=True); p.add_argument("--lease", required=True); p.add_argument("--proposal", required=True)
    p = sub.add_parser("packet"); p.add_argument("--task", type=int, required=True)
    p = sub.add_parser("review"); p.add_argument("--task", type=int, required=True); p.add_argument("--lease", required=True)
    p.add_argument("--session", required=True); p.add_argument("--verdict", required=True)
    p = sub.add_parser("apply"); p.add_argument("--task", type=int, required=True); p.add_argument("--workspace", default=".")
    p.add_argument("--kind", choices=("university_refresh", "field_update", "batch_import"), required=True)
    sub.add_parser("pr-build")
    args = parser.parse_args()
    if args.command == "path": emit({"path": str(record_path(args.workspace, args.qid))}); return
    if args.command == "validate": validate(read(args.path)); emit({"valid": True}); return
    if args.command == "pr-build":
        raise RuntimeError("GitHub export is disabled until trusted review attestations and branch checks are configured; never publish private proposals")
    if args.command == "seed-init":
        path = Path(args.input); manifest = read(args.manifest)
        expected = manifest.get("files", {}).get(path.name)
        h = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(8 * 1024**2), b""): h.update(chunk)
        if not expected or h.hexdigest() != expected: raise ValueError("Seed input not bound to supplied manifest")
        mh = hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest()
        if args.write and ".private" not in Path(args.output).resolve().parts:
            acceptance = read(args.acceptance) if args.acceptance else {}
            if acceptance.get("status") != "accepted" or acceptance.get("manifest_sha256") != mh or not acceptance.get("human_approval_ref"):
                raise ValueError("Public seed creation requires acceptance for this exact candidate-list manifest")
        count = 0; seen = set(); result = {"created": 0, "unchanged": 0}
        for row in seed_rows(path):
            if args.limit is not None and count >= args.limit: break
            if row.get("seed_role", "institution_candidate") != "institution_candidate": raise ValueError("Initial import is the primary candidate view only")
            record = initial(row, "seed-" + mh[:12]); validate(record)
            if record["qid"] in seen: raise ValueError("Duplicate seed QID")
            seen.add(record["qid"]); count += 1
            if args.write: result[create(args.output, record)] += 1
        emit({"mode": "write" if args.write else "dry_run", "records": count, **result, "manifest_sha256": mh}); return
    if args.command == "propose":
        current = read(record_path(args.workspace, args.qid))
        kwargs = {"allowed_groups": args.groups} if args.groups else {}
        value = proposal(current, read(args.changes), **kwargs); save_private(args.output, value)
        emit({"proposal_path": args.output, "qid": args.qid, "changed_claims": len(value["changed_claim_ids"])}); return
    queue = Queue(args.state)
    try:
        if args.command == "snapshot": value = queue.snapshot(args.workspace, args.now, args.base_ref)
        elif args.command == "tasks": value = queue.page(args.run, args.limit, args.cursor)
        elif args.command == "claim": value = queue.claim(args.run, args.role, args.actor, args.session, args.now)
        elif args.command == "heartbeat": value = queue.heartbeat(args.task, args.lease, args.now)
        elif args.command == "submit": value = queue.submit(args.task, args.lease, args.now, read(args.proposal))
        elif args.command == "packet": value = queue.private_packet(args.task)
        elif args.command == "review":
            verdict = read(args.verdict)
            value = queue.decide(args.task, args.lease, args.now, verdict["decision"], args.session,
                                 verdict.get("source_checks", []), verdict.get("reviewed_groups", []))
        elif args.command == "apply":
            packet = queue.private_packet(args.task)
            if packet["state"] not in ("approved", "applied"): raise ValueError("Approved private task required")
            proposed = packet["proposal"]; receipt = packet["receipt"]; proposed_record = proposed["candidate"]
            # Finalize against the original proposal baseline, even on retry.
            candidate = finish_candidate(proposed_record, proposed_record, receipt["reviewed_at"], args.kind, receipt["reviewed_groups"])
            receipt = {**receipt, "candidate_digest": digest(candidate)}
            state = apply_reviewed(args.workspace, candidate, proposed["base_digest"], receipt)
            queue.mark_applied(args.task); value = {"state": state, "qid": candidate["qid"]}
        else: raise AssertionError(args.command)
        emit(value)
    finally: queue.close()


if __name__ == "__main__": main()
