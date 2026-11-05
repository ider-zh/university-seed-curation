"""Fresh, read-only Codex CLI calls with private traces and explicit model configuration."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time


def command():
    if os.name == "nt":
        shim = shutil.which("codex.cmd")
        if shim:
            js = Path(shim).parent / "node_modules/@openai/codex/bin/codex.js"
            if js.exists() and shutil.which("node"): return [shutil.which("node"), str(js)]
    path = shutil.which("codex")
    if not path: raise RuntimeError("Codex CLI is not installed")
    return [path]


def run(prompt, schema, directory, cwd, timeout=1200):
    directory = Path(directory).resolve(); directory.mkdir(parents=True, exist_ok=False)
    result = directory / "result.json"; shape = directory / "output.schema.json"
    shape.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    (directory / "prompt.txt").write_text(prompt, encoding="utf-8")
    rule_files = {}
    for relative in ("AGENTS.md", ".agents/skills/university-curation/SKILL.md", "docs/review-policy-v2.md"):
        path = Path(cwd) / relative
        if path.exists(): rule_files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    (directory / "repository-rule-hashes.json").write_text(json.dumps(rule_files, indent=2), encoding="utf-8")
    argv = command() + ["exec", "--json", "--ephemeral", "--sandbox", "read-only", "--color", "never",
        "--model", "gpt-6.1-terra", "-c", 'model_reasoning_effort="medium"', "--output-schema", str(shape),
        "--output-last-message", str(result), "--cd", str(Path(cwd).resolve()), "-"]
    started = datetime.now(timezone.utc).isoformat(); start = time.monotonic(); returncode = -1
    try:
        with (directory / "events.jsonl").open("wb") as out, (directory / "stderr.log").open("wb") as err:
            process = subprocess.run(argv, input=prompt.encode("utf-8"), stdout=out, stderr=err, timeout=timeout,
                cwd=cwd, check=False, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            returncode = process.returncode
    finally:
        meta = {"requested_model": "gpt-6.1-terra", "reasoning_effort": "medium", "fresh_session": True,
            "started_at": started, "ended_at": datetime.now(timezone.utc).isoformat(), "elapsed_seconds": time.monotonic() - start,
            "returncode": returncode, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "schema_sha256": hashlib.sha256(shape.read_bytes()).hexdigest(), "repository_rule_hashes": rule_files,
            "session_ids": [], "reported_models": [], "tool_events": []}
        models = set()
        for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines():
            try: event = json.loads(line)
            except ValueError: continue
            if isinstance(event.get("model"), str): models.add(event["model"])
            if event.get("type") == "thread.started": meta["session_ids"].append(event["thread_id"])
            if event.get("type") == "turn.completed": meta["usage"] = event.get("usage", {})
            kind = event.get("item", {}).get("type")
            if kind in ("command_execution", "mcp_tool_call", "web_search", "file_change"): meta["tool_events"].append(kind)
        stderr = (directory / "stderr.log").read_text(encoding="utf-8", errors="replace")
        header = re.search(r"^model:\s*(\S+)", stderr, re.M)
        if header: models.add(header[1])
        meta["reported_models"] = sorted(models)
        (directory / "provider.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    if returncode: raise RuntimeError("Codex call failed; original private trace retained: " + directory.name)
    if models and models != {"gpt-6.1-terra"}: raise RuntimeError("Codex reported a different model")
    if meta["tool_events"]: raise RuntimeError("Sealed evidence role attempted unexpected tool use; trace retained")
    if len(meta["session_ids"]) != 1: raise RuntimeError("Missing/ambiguous independent session")
    data = json.loads(result.read_text(encoding="utf-8"))
    import jsonschema
    jsonschema.Draft202012Validator(schema).validate(data)
    return data, meta
