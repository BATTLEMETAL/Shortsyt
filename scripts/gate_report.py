"""Prints quality-score calibration and 48h Reality Gate summary from lol_agent/learning_directive.json."""
import json
from pathlib import Path

LD = Path(__file__).resolve().parent.parent / "lol_agent" / "learning_directive.json"


def main() -> None:
    d = json.loads(LD.read_text(encoding="utf-8"))
    gc = d.get("gate_calibration") or {}
    rg = d.get("post_48h_gate_summary") or {}
    print("=== 1) Quality score calibration (quality_score vs real YouTube outcome) ===")
    print(json.dumps(gc, indent=2))
    print("=== 2) 48h post-publish Reality Gate (YouTube Analytics API) ===")
    keys = ["total_verified_48h", "pending_under_48h", "avg_rwi_score", "median_rwi_score", "verdict_counts", "fit_confirmed_pct"]
    print(json.dumps({k: rg.get(k) for k in keys}, indent=2))


if __name__ == "__main__":
    main()
