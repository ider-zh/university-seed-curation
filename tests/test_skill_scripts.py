"""Bundled commands must work without relying on the caller's working directory."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".agents/skills/university-curation/scripts"


class BundledScriptTests(unittest.TestCase):
    def test_commands_resolve_checkout_from_an_unrelated_working_directory(self):
        with tempfile.TemporaryDirectory(prefix="external working directory ") as tmp:
            def run(name, *arguments):
                result = subprocess.run([sys.executable, str(SCRIPTS / name), *arguments],
                    cwd=tmp, capture_output=True, text=True, encoding="utf-8", timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout
            output = json.loads(run("curate.py", "path", "Q13371", "--workspace", tmp))
            self.assertEqual(Path(output["path"]), Path(tmp) / "data/universities/da/Q13371.json")
            self.assertIn("wikidata-get", run("sources.py", "--help"))
            self.assertIn("prepare", run("buckets.py", "--help"))
            self.assertIn("review", run("coordinates.py", "--help"))
            self.assertTrue((SCRIPTS / "lib/university_curation/records.py").is_file())
            self.assertFalse(any((ROOT / "src").rglob("*.py")))
            # Resolving the wrong root would look for schemas below the skill
            # folder or temporary cwd instead of the real checkout.
            run("maintain_schema.py", "check")
            for name in ("prepare_real_pilot.py", "run_real_pilot.py", "review_pilot_policy_v2.py", "finalize_real_pilot.py"):
                self.assertIn("--root", run(name, "--help"))
