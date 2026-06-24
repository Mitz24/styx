import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import requests
import pandas as pd
from pathlib import Path

PROM = "http://localhost:9090"


@dataclass(frozen=True)
class MetadataParams:
    workload: str
    start: float
    end: float
    out_path: str
    n_partitions: int
    messages_per_second: int
    n_keys: int
    seconds: int
    epoch_size: int
    warmup_seconds: int
    migrations: list[dict] = None
    zipf_const: Optional[float] = None
    interval_seconds: Optional[int] = None
    delta_tps: Optional[int] = None
    n_threads: int = 1


def query_prometheus_range(
    metric: str,
    start_time: float,  # Unix timestamp (seconds)
    end_time: float,
    step: str = "1s",
    prometheus_url: str = "http://localhost:9090",
) -> pd.DataFrame:
    """Query Prometheus for a time series over a range."""
    resp = requests.get(
        f"{prometheus_url}/api/v1/query_range",
        params={
            "query": metric,
            "start": start_time,
            "end": end_time,
            "step": step,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    
    if data["status"] != "success":
        raise ValueError(f"Prometheus query failed: {data}")
    
    results = data["data"]["result"]
    if not results:
        return pd.DataFrame(columns=["timestamp", "value"])
    
    # Handle multiple series (e.g., per-instance metrics)
    rows = []
    for series in results:
        labels = series.get("metric", {})
        for timestamp, value in series["values"]:
            row = {"timestamp": float(timestamp), "value": float(value)}
            row.update(labels)  # Add labels as columns
            rows.append(row)
    
    return pd.DataFrame(rows)

def export_metrics(
    save_dir: Path,
    start_time: float,
    end_time: float,
    prometheus_url: str = "http://localhost:9090",
    step: str = "1s",
):
    """Export key metrics from Prometheus to CSV files."""
    metrics = {
        "backlog": "sum(queue_backlog)",
        "num_workers": "live_worker_count",
        "epoch_latency": "avg(worker_epoch_latency_ms)",
        "committed_tps": "sum(rate(epoch_total_transactions_total[15s]))",
    }
    
    save_dir = Path(save_dir)
    
    for name, query in metrics.items():
        try:
            df = query_prometheus_range(
                query, start_time, end_time, step, prometheus_url
            )
            if not df.empty:
                df.to_csv(save_dir / f"{name}.csv", index=False)
                print(f"Exported {name}: {len(df)} data points")
        except Exception as e:
            print(f"Failed to export {name}: {e}")


def plot_run(save_dir, warmup_seconds: Optional[int] = None) -> None:
    """Write a quick-look overview.png (worker count, backlog, epoch latency) into
    the run directory. Best-effort: skips silently if matplotlib or the metric
    CSVs are unavailable, so it never blocks an experiment from finishing.

    Time is relative to the run's own first sample (minus warmup), so it works
    for any run regardless of absolute timestamps.
    """
    save_dir = Path(save_dir)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:  # noqa: BLE001
        print(f"Skipping overview plot (matplotlib unavailable): {e}")
        return

    if warmup_seconds is None:
        try:
            meta = json.loads((save_dir / "metadata.json").read_text())
            warmup_seconds = int(meta.get("warmup_seconds", 0))
        except Exception:  # noqa: BLE001
            warmup_seconds = 0

    panels = [
        ("num_workers.csv", "Workers", "step", "C2"),
        ("backlog.csv", "Queue backlog", "line", "C3"),
        ("epoch_latency.csv", "Epoch latency (ms)", "line", "C0"),
    ]
    loaded, t0 = [], None
    for fname, ylabel, kind, color in panels:
        path = save_dir / fname
        if not path.is_file():
            continue
        df = pd.read_csv(path)
        if df.empty or "timestamp" not in df.columns or "value" not in df.columns:
            continue
        df = df.groupby("timestamp", as_index=False)["value"].mean().sort_values("timestamp")
        loaded.append((df, ylabel, kind, color))
        first = df["timestamp"].iloc[0]
        t0 = first if t0 is None else min(t0, first)

    if not loaded:
        print("Skipping overview plot (no metric CSVs found)")
        return

    fig, axes = plt.subplots(len(loaded), 1, sharex=True, figsize=(10, 2.4 * len(loaded)))
    if len(loaded) == 1:
        axes = [axes]
    for ax, (df, ylabel, kind, color) in zip(axes, loaded):
        t = df["timestamp"].to_numpy() - t0 - warmup_seconds
        v = df["value"].to_numpy()
        mask = t >= 0
        if kind == "step":
            ax.step(t[mask], v[mask], where="post", color=color, lw=1.8)
        else:
            ax.plot(t[mask], v[mask], color=color, lw=1.5)
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.3, lw=0.5)
    axes[-1].set_xlabel("Time since workload start (s)")
    fig.suptitle(f"Run overview — {save_dir.name}")
    fig.tight_layout()
    out = save_dir / "overview.png"
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved overview plot: {out}")


def save_data(data, save_dir, filename):
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    with open(os.path.join(save_dir, filename), "w") as f:
        json.dump(data, f, indent=2)


def save_metadata(params: MetadataParams):
    metadata = {
        "workload": params.workload,
        "messages_per_second": params.messages_per_second,
        "n_partitions": params.n_partitions,
        "n_keys": params.n_keys,
        "start": datetime.fromtimestamp(params.start).isoformat(),
        "end": datetime.fromtimestamp(params.end).isoformat(),
        "duration (s)": params.seconds, 
        "epoch_size": params.epoch_size,
        "warmup_seconds": params.warmup_seconds,
        "migrations": params.migrations if params.migrations is not None else None,
    }
    if params.zipf_const is not None:
        metadata["zipf_const"] = params.zipf_const
    if params.interval_seconds is not None:
        metadata["increase_interval"] = params.interval_seconds
    if params.delta_tps is not None:
        metadata["increase_amount"] = params.delta_tps

    metadata["n_threads"] = params.n_threads

    save_data(metadata, params.out_path, "metadata.json")

    # Quick-look plot for this run (metric CSVs were written by export_metrics()).
    plot_run(params.out_path, params.warmup_seconds)
