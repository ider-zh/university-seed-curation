"""Current bundled entry points resolve the checkout, and old modes are unavailable."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'.agents/skills/university-curation/scripts'

class BundledScriptTests(unittest.TestCase):
    def test_current_commands_work_from_unrelated_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            def run(name,*args):
                return subprocess.run([sys.executable,str(SCRIPTS/name),*args],cwd=directory,capture_output=True,text=True,timeout=30)
            for name in ('agent.py','sources.py','seeds.py'):
                result=run(name,'--help');self.assertEqual(result.returncode,0,result.stderr)
            result=run('maintain_schema.py','check');self.assertEqual(result.returncode,0,result.stderr)
            help_text=run('agent.py','--help').stdout
            self.assertIn('publication-confirm',help_text)
            for command in ('draft','finalize','decision','coord-plan','register-key'):
                result=run('agent.py',command);self.assertNotEqual(result.returncode,0)
            self.assertNotEqual(run('agent.py','--runtime','cli','doctor').returncode,0)
            self.assertFalse((SCRIPTS/'curate.py').exists())
