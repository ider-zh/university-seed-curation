"""Repository-local entry point; no editable installation required."""
from pathlib import Path
import sys

from _bootstrap import ROOT, SCRIPTS
from university_curation.cli import main

if __name__ == "__main__": main()
