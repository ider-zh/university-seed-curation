"""Resolve this checkout from the bundled script location, independent of cwd."""
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parent
ROOT = next((parent for parent in SCRIPTS.parents
             if (parent / "pyproject.toml").is_file()
             and (parent / "src/university_curation/__init__.py").is_file()), None)
if ROOT is None:
    raise RuntimeError("Run this skill from a university-seed-curation checkout")
sys.path.insert(0, str(ROOT / "src"))
