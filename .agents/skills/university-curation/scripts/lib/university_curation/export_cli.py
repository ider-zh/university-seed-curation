"""CLI wiring for private preparation, gated installation and read-only CI."""
from pathlib import Path

from .attestations import init_key, policy, load_json, private_path
from .records import ROOT, encode
from .pr_export import prepare, install, validate_pr, check_acceptance


def arguments(sub):
    p = sub.add_parser("pr-key-init", help="Initialize a private signing key and public trust policy")
    p.add_argument("--key", required=True); p.add_argument("--public-policy", default=".curation/review-trust.json")
    p.add_argument("--repository", default="ider-zh/university-seed-curation")
    p = sub.add_parser("pr-build", help="Prepare a reviewed private batch; never publishes")
    p.add_argument("--pilot-root", required=True); p.add_argument("--qids", nargs="+", required=True)
    p.add_argument("--batch-id", required=True); p.add_argument("--base-ref", required=True)
    p.add_argument("--workspace", default="."); p.add_argument("--trust", default=str(ROOT / ".curation/review-trust.json"))
    p.add_argument("--key", required=True); p.add_argument("--output", required=True); p.add_argument("--acceptance")
    p = sub.add_parser("pr-record-acceptance", help="Operator command: record explicit acceptance of reviewed data")
    p.add_argument("--bundle", required=True); p.add_argument("--human-actor", required=True)
    p.add_argument("--approval-ref", required=True); p.add_argument("--output", required=True)
    p = sub.add_parser("pr-stage", help="Install a human-accepted signed batch for a data-only PR")
    p.add_argument("--workspace", default="."); p.add_argument("--bundle", required=True)
    p = sub.add_parser("pr-validate", help="Validate proposed Git blobs using base-branch trust")
    p.add_argument("--workspace", default="."); p.add_argument("--base-ref", required=True); p.add_argument("--head-ref", default="HEAD")
    p.add_argument("--expected-head-sha", help="Require the checked-out HEAD to match the immutable PR event SHA")


def handle(args):
    if args.command == "pr-key-init":
        target = Path(args.public_policy)
        if target.exists(): raise FileExistsError("Trust policy already exists; rotation requires a reviewed code PR")
        public = init_key(args.key); value = policy(ROOT, public, args.repository)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream: stream.write(encode(value))
        return {"key_id": public["key_id"], "public_policy": str(target), "private_key_printed": False}
    if args.command == "pr-build":
        trust = load_json(Path(args.trust).read_bytes())
        approval = load_json(Path(args.acceptance).read_bytes()) if args.acceptance else None
        return prepare(args.workspace, args.pilot_root, args.qids, args.batch_id, args.base_ref, trust, args.key, args.output, approval)
    if args.command == "pr-stage": return install(args.workspace, args.bundle)
    if args.command == "pr-validate": return validate_pr(args.workspace, args.base_ref, args.head_ref, args.expected_head_sha)
    if args.command == "pr-record-acceptance":
        preview = load_json((private_path(args.bundle) / "preview.json").read_bytes())
        value = {"status": "accepted", "content_scope_sha256": preview["content_scope_sha256"],
            "human_actor": args.human_actor, "human_approval_ref": args.approval_ref}
        check_acceptance(value, preview["content_scope_sha256"])
        target = private_path(args.output); target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream: stream.write(encode(value))
        return {"path": str(target), "content_scope_sha256": value["content_scope_sha256"], "publication_performed": False}
    raise ValueError("Unknown export command")
