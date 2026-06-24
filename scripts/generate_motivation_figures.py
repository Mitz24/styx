#!/usr/bin/env python3
"""
Generate the motivation-section figures from the committed static-sweep data.

Reads the CSVs under
results/paper_experiments/motivation_static/{4..9}workers/ and writes:

  results/figures/motivation_comparison.pdf  3-panel under(4w)/over(9w)/optimal
  results/figures/motivation_gradient.pdf    backlog gradient across 4-9 workers

The static sweep was collected on the upstream Styx version (15 s resolution);
the "optimal" schedule is spliced from the sweep by picking, at each sample, the
smallest worker count whose own run kept the backlog at zero.

Run from anywhere:
  python scripts/generate_motivation_figures.py
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "results" / "paper_experiments" / "motivation_static"
FIGDIR = REPO / "results" / "figures"
WORKER_COUNTS = [4, 5, 6, 7, 8, 9]

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 9,
    "axes.labelsize": 9,
    "legend.fontsize": 7,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "axes.titlesize": 9,
    "axes.titleweight": "bold",
})


def load_series(workers: int, metric: str) -> pd.DataFrame:
    """Canonical timestamp,value CSV -> elapsed-seconds series from its first sample."""
    df = pd.read_csv(DATA / f"{workers}workers" / f"{metric}.csv")
    df = df.groupby("timestamp", as_index=False)["value"].mean().sort_values("timestamp")
    df["elapsed_s"] = df["timestamp"] - df["timestamp"].iloc[0]
    return df[["elapsed_s", "value"]]


def resample(series: pd.DataFrame, grid_s: np.ndarray) -> pd.Series:
    r = pd.merge_asof(
        pd.DataFrame({"elapsed_s": grid_s}),
        series.sort_values("elapsed_s"),
        on="elapsed_s",
        direction="backward",
    )["value"]
    r.index = grid_s
    return r


def build_oracle(backlog_grid: pd.DataFrame, latency_grid: pd.DataFrame):
    sufficient = backlog_grid == 0
    oracle_workers = sufficient.apply(
        lambda row: next((w for w in WORKER_COUNTS if row[w]), WORKER_COUNTS[-1]), axis=1
    )
    oracle_backlog = pd.Series(
        [backlog_grid.loc[t, oracle_workers[t]] for t in backlog_grid.index],
        index=backlog_grid.index,
    )
    oracle_latency = pd.Series(
        [latency_grid.loc[t, oracle_workers[t]] for t in latency_grid.index],
        index=latency_grid.index,
    )
    return oracle_workers, oracle_backlog, oracle_latency


def main() -> None:
    FIGDIR.mkdir(parents=True, exist_ok=True)

    backlog = {w: load_series(w, "backlog") for w in WORKER_COUNTS}
    latency = {w: load_series(w, "epoch_latency") for w in WORKER_COUNTS}

    grid_s = np.arange(0, 301, 15, dtype=float)
    backlog_grid = pd.DataFrame({w: resample(backlog[w], grid_s) for w in WORKER_COUNTS})
    latency_grid = pd.DataFrame({w: resample(latency[w], grid_s) for w in WORKER_COUNTS})
    oracle_workers, oracle_backlog, oracle_latency = build_oracle(backlog_grid, latency_grid)

    under_w, over_w = 4, 9
    c_under, c_over, c_oracle = "#d62728", "#2ca02c", "#1f1f1f"

    # --- Figure 1: 3-panel comparison ---
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.65))
    leg_kw = dict(loc="upper left", fontsize=6.5, framealpha=0.92,
                  handlelength=2.2, borderaxespad=0.3, labelspacing=0.25)

    ax = axes[0]
    ax.axhline(under_w, color=c_under, linestyle="-", linewidth=1.3, label=f"Under ({under_w}w)")
    ax.axhline(over_w, color=c_over, linestyle="--", linewidth=1.3, label=f"Over ({over_w}w)")
    ax.step(grid_s, oracle_workers, where="post", color=c_oracle, linestyle="-.", linewidth=1.3, label="Optimal")
    ax.set_title("Worker Count"); ax.set_ylabel("Workers"); ax.set_xlabel("Elapsed time (s)")
    ax.set_xlim(0, 300); ax.set_ylim(3, 13); ax.legend(**leg_kw); ax.grid(alpha=0.3, linewidth=0.5)

    ax = axes[1]
    b_max = max(backlog[under_w]["value"].max(), 1) / 1000
    ax.plot(backlog[under_w]["elapsed_s"], backlog[under_w]["value"] / 1000,
            color=c_under, linestyle="-", linewidth=1.3, label=f"Under ({under_w}w)")
    ax.plot(backlog[over_w]["elapsed_s"], backlog[over_w]["value"] / 1000,
            color=c_over, linestyle="--", linewidth=2.2, label=f"Over ({over_w}w)")
    ax.step(grid_s, oracle_backlog / 1000, where="post", color=c_oracle, linestyle="-.", linewidth=1.3, label="Optimal")
    ax.set_title("Queue Backlog"); ax.set_ylabel(r"Backlog ($\times 10^3$)"); ax.set_xlabel("Elapsed time (s)")
    ax.set_xlim(0, 300); ax.set_ylim(-b_max * 0.05, b_max * 1.45); ax.legend(**leg_kw); ax.grid(alpha=0.3, linewidth=0.5)

    ax = axes[2]
    ax.plot(latency[under_w]["elapsed_s"], latency[under_w]["value"],
            color=c_under, linestyle="-", linewidth=1.3, label=f"Under ({under_w}w)")
    ax.plot(latency[over_w]["elapsed_s"], latency[over_w]["value"],
            color=c_over, linestyle="--", linewidth=2.2, label=f"Over ({over_w}w)")
    ax.step(grid_s, oracle_latency, where="post", color=c_oracle, linestyle="-.", linewidth=1.3, label="Optimal")
    ax.set_title("Transaction Latency"); ax.set_ylabel("Latency (ms)"); ax.set_xlabel("Elapsed time (s)")
    ax.set_yscale("symlog"); ax.set_xlim(0, 300); ax.set_ylim(top=10000); ax.legend(**leg_kw); ax.grid(alpha=0.3, linewidth=0.5)

    fig.tight_layout()
    fig.savefig(FIGDIR / "motivation_comparison.pdf")
    plt.close(fig)
    print(f"  wrote motivation_comparison.pdf")

    # --- Figure 2: backlog gradient across 4-9 workers ---
    cmap = plt.cm.viridis
    colors = {w: cmap(i / (len(WORKER_COUNTS) - 1)) for i, w in enumerate(WORKER_COUNTS)}
    fig2, ax2 = plt.subplots(figsize=(3.3, 2.6))
    for w in WORKER_COUNTS:
        d = backlog[w]
        ax2.plot(d["elapsed_s"], d["value"] / 1000, label=f"{w}", color=colors[w], linewidth=1.3)
    ax2.set_xlabel("Elapsed time (s)"); ax2.set_ylabel(r"Backlog ($\times 10^3$)")
    ax2.set_xlim(0, 300); ax2.grid(alpha=0.3, linewidth=0.5)
    ax2.legend(title="Workers", ncol=6, fontsize=6.3, title_fontsize=6.3,
               loc="upper center", bbox_to_anchor=(0.5, 1.22),
               handlelength=1.2, columnspacing=0.8, handletextpad=0.4, frameon=False)
    fig2.subplots_adjust(top=0.86, bottom=0.18, left=0.20, right=0.96)
    fig2.savefig(FIGDIR / "motivation_gradient.pdf")
    plt.close(fig2)
    print(f"  wrote motivation_gradient.pdf")

    print(f"\nOptimal schedule worker-seconds = {float((oracle_workers.to_numpy()[:-1] * np.diff(grid_s)).sum()):.0f}")
    print(f"Figures written to {FIGDIR}")


if __name__ == "__main__":
    main()
