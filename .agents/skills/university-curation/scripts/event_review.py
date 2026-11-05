from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from university_curation.distributed_events import main

if __name__ == "__main__":
    main()
