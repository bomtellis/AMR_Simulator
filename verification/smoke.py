"""Bounded-duration realistic run; a repeatability check, not a numerical oracle.

python -m verification.smoke --config ltn.json --minutes 60 --output verification/latest/ltn-smoke
The source project is never saved. Only end_datetime is shortened in the copy.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from verification.run import source_manifest, write_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--minutes", type=float, default=60)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not 0 < args.minutes <= 1440:
        parser.error("minutes must be greater than zero and no more than 1440")
    from simulator import Simulation
    raw = args.config.read_bytes()
    config = json.loads(raw)
    original_end = config["simulation"].get("end_datetime")
    start = datetime.fromisoformat(config["simulation"]["start_datetime"])
    end = start + timedelta(minutes=args.minutes)
    if original_end:
        end = min(end, datetime.fromisoformat(original_end))
    config["simulation"]["end_datetime"] = end.isoformat()
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "config.json", config)
    report = {"scope": "Shortened LTN repeatability smoke check, not independent numerical validation. Existing simulator may drain assigned work beyond the demand horizon.",
              "input_sha256": hashlib.sha256(raw).hexdigest(),
              "source": source_manifest(), "original_end_datetime": original_end,
              "run_end_datetime": config["simulation"]["end_datetime"], "runs": []}
    for repeat in range(2):
        started = time.perf_counter()
        with (args.output / f"run-{repeat + 1}.txt").open("w", encoding="utf-8") as stream:
            with contextlib.redirect_stdout(stream):
                sim = Simulation(copy.deepcopy(config))
                loaded = time.perf_counter()
                sim.run()
        outcome = {"completed": sim.completed_task_records, "failed": sim.failed_tasks,
                   "pending_ids": sorted(task.id for _priority, _release, _seq, task in sim.pending_tasks
                                         if task.id not in sim._removed_pending_task_ids)}
        outcome_json = json.dumps(outcome, sort_keys=True, default=str)
        write_json(args.output / f"outcome-{repeat + 1}.json", outcome)
        report["runs"].append({"initialisation_seconds": round(loaded - started, 6),
                               "total_seconds": round(time.perf_counter() - started, 6),
                               "completed": len(outcome["completed"]), "failed": len(outcome["failed"]),
                               "pending": len(outcome["pending_ids"]),
                               "final_sim_time_sec": sim.current_time,
                               "outcome_sha256": hashlib.sha256(outcome_json.encode()).hexdigest()})
        print(f'Run {repeat + 1}: {report["runs"][-1]}', flush=True)
    report["repeatable"] = report["runs"][0]["outcome_sha256"] == report["runs"][1]["outcome_sha256"]
    report["source_unchanged"] = report["source"] == source_manifest()
    report["input_unchanged"] = hashlib.sha256(args.config.read_bytes()).hexdigest() == report["input_sha256"]
    write_json(args.output / "smoke.json", report)
    return 0 if report["repeatable"] and report["source_unchanged"] and report["input_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
