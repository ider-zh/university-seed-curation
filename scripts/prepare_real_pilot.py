"""Prepare ten online real-source cases without making any institution classifications."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))
from university_curation.pilot_sources import CASES, prepare_case, save

if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--root", required=True); args = p.parse_args()
    root = Path(args.root).resolve()
    if ".private" not in root.parts: raise ValueError("Pilot sources must remain private")
    save(root / "case-plan.json", {"cases": CASES, "selection_is_diagnostic_not_ground_truth": True})
    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(prepare_case, case, root): case for case in CASES}
        for future in as_completed(futures):
            case = futures[future]
            try: result = future.result()
            except Exception as error: result = {"qid": case["qid"], "failed": str(error)}
            results.append(result); save(root / "source-preparation-status.json", {"completed": len(results), "total": len(CASES), "results": results})
            print(result, flush=True)
