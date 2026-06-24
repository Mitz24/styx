#!/usr/bin/env python3
"""
export_experiment_metrics.py

Export the Prometheus metrics used by the autoscaling-paper figures to CSV.

Given an experiment run directory that contains a ``metadata.json`` with the
run's ``start`` and ``end`` timestamps, this queries the local Prometheus over
the run's time window and writes one CSV per metric in a canonical
``timestamp,value`` format (Unix seconds, numeric value).

These CSVs are the direct inputs to the figure scripts under ``scripts/``
(``generate_eval_figures.py`` / ``generate_motivation_figures.py``). Re-running
an experiment and then running this exporter regenerates inputs in exactly the
same shape, so the figures can be reproduced from fresh data.

Unlike a generic dashboard dump, this exports only the short, explicit list of
metrics the paper actually plots (METRICS below). Add an entry to that dict to
export more.

Usage:
    python scripts/export_experiment_metrics.py --run-dir results/my_run
    python scripts/export_experiment_metrics.py        # latest dir under results/

Assumes Prometheus is reachable at http://localhost:9090 (override with
--prometheus) and that the run's metadata timestamps are on the same clock as
Prometheus (true when the experiment and Prometheus run on the same host).
"""

import argparse
import csv
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

METRICS = {
    "backlog.csv": "sum(queue_backlog)",
    "num_workers.csv": "live_worker_count",
    "epoch_latency.csv": "avg(worker_epoch_latency_ms)",
    "committed_tps.csv": "sum(rate(epoch_total_transactions_total[15s]))",
}


def find_latest_run_dir(results_dir: Path) -> Path | None:
    if not results_dir.is_dir():
        return None
    runs = [d for d in results_dir.iterdir() if d.is_dir() and (d / "metadata.json").exists()]
    if not runs:
        # metadata.json may live one level down (e.g. results/<run>/<inner>/metadata.json)
        runs = [p.parent for p in results_dir.glob("*/*/metadata.json")]
    if not runs:
        return None
    return max(runs, key=lambda d: d.stat().st_mtime)


def read_window(run_dir: Path) -> tuple[float, float]:
    meta = json.loads((run_dir / "metadata.json").read_text())
    start, end = meta.get("start"), meta.get("end")
    if not start or not end:
        raise ValueError(f"metadata.json in {run_dir} is missing 'start'/'end'")
    # ISO timestamps are interpreted in local time, matching how the run
    # client wrote them and how Prometheus stored the samples.
    return datetime.fromisoformat(start).timestamp(), datetime.fromisoformat(end).timestamp()


def query_range(prometheus: str, expr: str, start: float, end: float, step: str) -> list[list]:
    params = urllib.parse.urlencode({"query": expr, "start": start, "end": end, "step": step})
    url = f"{prometheus.rstrip('/')}/api/v1/query_range?{params}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        payload = json.loads(resp.read().decode())
    if payload.get("status") != "success":
        raise RuntimeError(f"query failed: {payload.get('error', 'unknown error')}")
    result = payload.get("data", {}).get("result", [])
    if not result:
        return []
    if len(result) > 1:
        print(f"  warning: {len(result)} series returned for '{expr}'; using the first", file=sys.stderr)
    return result[0].get("values", [])


def export(run_dir: Path, prometheus: str, step: str) -> None:
    start, end = read_window(run_dir)
    print(f"Run:    {run_dir}")
    print(f"Window: {datetime.fromtimestamp(start)} -> {datetime.fromtimestamp(end)}")
    for filename, expr in METRICS.items():
        try:
            values = query_range(prometheus, expr, start, end, step)
        except Exception as exc:  # noqa: BLE001 - report and continue with the other metrics
            print(f"  ERROR  {filename:20s} ({expr}): {exc}", file=sys.stderr)
            continue
        if not values:
            print(f"  empty  {filename:20s} ({expr}) - no samples in window")
            continue
        out_path = run_dir / filename
        with out_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "value"])
            for ts, val in values:
                writer.writerow([ts, val])
        print(f"  wrote  {filename:20s} {len(values):5d} samples")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", help="Run directory (contains metadata.json). Default: latest under results/")
    parser.add_argument("--results-dir", default="results", help="Where to look for the latest run (default: results)")
    parser.add_argument("--prometheus", default="http://localhost:9090", help="Prometheus base URL")
    parser.add_argument("--step", default="1s", help="Query resolution step (default: 1s)")
    args = parser.parse_args()

    if args.run_dir:
        run_dir = Path(args.run_dir)
    else:
        run_dir = find_latest_run_dir(Path(args.results_dir))
        if run_dir is None:
            sys.exit(f"No run directory with metadata.json found under {args.results_dir}/")

    if not (run_dir / "metadata.json").exists():
        sys.exit(f"{run_dir} has no metadata.json")

    export(run_dir, args.prometheus, args.step)


if __name__ == "__main__":
    main()
