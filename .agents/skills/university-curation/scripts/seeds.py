from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from university_curation.seed_catalog import main

if __name__ == "__main__":
    main()
