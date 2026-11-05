import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.agents/skills/university-curation/scripts/lib'))
from university_curation import codex_provider


class CancellationTests(unittest.TestCase):
    def test_cancel_stops_owned_child_tree_and_keeps_failure_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); started = root/'started'; orphan = root/'orphan'
            child_code = "import time,pathlib;time.sleep(1.5);pathlib.Path(" + repr(str(orphan)) + ").write_text('orphan')"
            script = root/'fake_codex.py'
            script.write_text("import pathlib,subprocess,sys,time\n"
                "subprocess.Popen([sys.executable,'-c'," + repr(child_code) + "])\n"
                "pathlib.Path(" + repr(str(started)) + ").write_text('ready')\n"
                "sys.stdin.read()\ntime.sleep(30)\n", encoding='utf-8')
            event = threading.Event()
            def cancel():
                for _ in range(100):
                    if started.exists(): event.set(); return
                    time.sleep(0.03)
                event.set()
            thread = threading.Thread(target=cancel); thread.start()
            with patch.object(codex_provider, 'command', return_value=[sys.executable, str(script)]):
                with self.assertRaisesRegex(RuntimeError, 'cancelled'):
                    codex_provider.run('private prompt', {'type':'object'}, root/'trace', root, timeout=10, cancel_event=event)
            thread.join(); self.assertTrue(started.exists())
            meta = json.loads((root/'trace/provider.json').read_text(encoding='utf-8'))
            self.assertNotEqual(meta['returncode'], 0)
            self.assertTrue((root/'trace/events.jsonl').exists())
            time.sleep(1.7)
            self.assertFalse(orphan.exists())

    def test_timeout_retains_failure_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); script=root/'fake_codex.py'
            script.write_text('import sys,time\nsys.stdin.read()\ntime.sleep(30)\n', encoding='utf-8')
            with patch.object(codex_provider, 'command', return_value=[sys.executable, str(script)]):
                with self.assertRaisesRegex(RuntimeError, 'timed out'):
                    codex_provider.run('private prompt', {'type':'object'}, root/'trace', root, timeout=0.2)
            meta=json.loads((root/'trace/provider.json').read_text(encoding='utf-8'))
            self.assertNotEqual(meta['returncode'], 0)

if __name__ == '__main__': unittest.main()
