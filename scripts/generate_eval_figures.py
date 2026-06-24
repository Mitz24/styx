#!/usr/bin/env python3
"""
Generate the evaluation-section figures from the committed experiment data.

Reads the CSVs under results/paper_experiments (produced by demo/export_metadata.py on every run) and writes:

  results/figures/eval_reactive_policy.pdf   3-panel reactive policy (workers/backlog/latency)
  results/figures/eval_styx_workers.pdf      built-in Styx autoscaler, worker count
  results/figures/eval_styx_backlog.pdf      built-in Styx autoscaler, queue backlog
  results/figures/eval_styx_latency.pdf      built-in Styx autoscaler, epoch latency

Run from anywhere:
  python scripts/generate_eval_figures.py
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "results" / "paper_experiments"
FIGDIR = REPO / "results" / "figures"

C_REACTIVE = "#1f77b4"  # blue
C_STYX = "#ff7f0e"      # orange
C_THRESH = "#888888"    # grey
LATENCY_THRESHOLD_MS = 250.0

plt.rcParams.update({
    "font.size": 9,
    "axes.titlesize": 9,
    "axes.labelsize": 8,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 7.5,
    "figure.dpi": 150,  
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def load_run(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    meta = json.loads((run_dir / "metadata.json").read_text())
    warmup = float(meta.get("warmup_seconds", 30))

    def read(metric: str) -> pd.DataFrame:
        df = pd.read_csv(run_dir / f"{metric}.csv")
        # collapse any duplicate timestamps (raw gauges can repeat) to one point
        return df.groupby("timestamp", as_index=False)["value"].mean().sort_values("timestamp")

    backlog_df = read("backlog")
    t0 = backlog_df["timestamp"].iloc[0]

    def relative(df: pd.DataFrame) -> pd.Series:
        t = df["timestamp"].to_numpy() - t0 - warmup
        s = pd.Series(df["value"].to_numpy(), index=t)
        return s[s.index >= 0]

    workers = relative(read("num_workers"))
    backlog = relative(backlog_df)
    latency = relative(read("epoch_latency"))

    w = workers.sort_index()
    worker_seconds = float((w.to_numpy()[:-1] * np.diff(w.index.to_numpy())).sum())

    return {"workers": workers, "backlog": backlog, "latency": latency,
            "worker_seconds": worker_seconds, "meta": meta}


def _annotate_worker_steps(ax, workers: pd.Series, color: str) -> None:
    prev = None
    for t, v in workers.items():
        if prev is not None and v != prev:
            symbol = "▲" if v > prev else "▼"
            yoff = 0.45 if v > prev else -0.6
            ax.text(t + 2, v + yoff, f"{symbol}{int(prev)}→{int(v)}",
                    fontsize=6.5, color=color, va="center")
        prev = v


def _peak_markers(ax, x, y):
    ax.set_xlim(0, 300)
    ax.set_xlabel("Time (s)")
    ax.grid(True, alpha=0.25, lw=0.5)
    for peak_t in (75, 225):
        ax.axvline(peak_t, color="#bbbbbb", lw=0.8, linestyle="--", zorder=0)


def figure_reactive(run: dict) -> None:
    w, b, l = run["workers"], run["backlog"], run["latency"]
    fig, (ax_w, ax_b, ax_l) = plt.subplots(1, 3, figsize=(11, 3.2), gridspec_kw={"wspace": 0.38})

    # (a) worker count
    ax_w.step(w.index, w.to_numpy(), where="post", color=C_REACTIVE, lw=1.8)
    ax_w.set_ylabel("Worker count")
    ax_w.set_title("(a) Worker count")
    ax_w.set_yticks([4, 5, 6, 7, 8, 9, 10])
    ax_w.set_ylim(3, 11)
    _annotate_worker_steps(ax_w, w, C_REACTIVE)
    ax_w.text(75, 10.6, "peak 1", ha="center", fontsize=6, color="#aaaaaa")
    ax_w.text(225, 10.6, "peak 2", ha="center", fontsize=6, color="#aaaaaa")

    # (b) queue backlog
    ax_b.plot(b.index, b.to_numpy() / 1e3, color=C_REACTIVE, lw=1.5)
    ax_b.fill_between(b.index, b.to_numpy() / 1e3, alpha=0.15, color=C_REACTIVE)
    ax_b.set_ylabel("Queue backlog (K messages)")
    ax_b.set_title("(b) Queue backlog")
    ax_b.set_ylim(bottom=0)
    first_up = w[w.diff() > 0]
    if not first_up.empty:
        t_up = first_up.index[0]
        bl = float(b.reindex([t_up], method="nearest").iloc[0])
        ax_b.axvline(t_up, color=C_REACTIVE, lw=1, linestyle="--", alpha=0.6)
        ax_b.annotate(f"1st trigger\n{bl/1e3:.0f}K", xy=(t_up, bl / 1e3),
                      xytext=(t_up + 18, bl / 1e3 + 35), fontsize=6.5, color=C_REACTIVE,
                      arrowprops=dict(arrowstyle="->", color=C_REACTIVE, lw=0.7))
    drained = b[(b.index > 100) & (b.to_numpy() < 500)]
    if not drained.empty:
        ax_b.annotate("backlog→0", xy=(drained.index[0], 0),
                      xytext=(drained.index[0] + 12, 30), fontsize=6.5, color=C_REACTIVE,
                      arrowprops=dict(arrowstyle="->", color=C_REACTIVE, lw=0.7))

    # (c) epoch latency
    ax_l.plot(l.index, l.to_numpy(), color=C_REACTIVE, lw=1.5, marker="o", markersize=3)
    ax_l.axhline(LATENCY_THRESHOLD_MS, color=C_THRESH, lw=1, linestyle=":", alpha=0.8)
    ax_l.text(302, LATENCY_THRESHOLD_MS, "250 ms\nthreshold", fontsize=6, color=C_THRESH,
              va="center", clip_on=False)
    ax_l.set_ylabel("Avg epoch latency (ms)")
    ax_l.set_title("(c) Epoch latency")
    ax_l.set_ylim(bottom=0)
    trough = l[(l.index > 150) & (l.index < 230)]
    if not trough.empty:
        ax_l.annotate(f"{trough.min():.0f} ms", xy=(trough.idxmin(), trough.min()),
                      xytext=(trough.idxmin() + 12, trough.min() + 300), fontsize=6.5,
                      color=C_REACTIVE, arrowprops=dict(arrowstyle="->", color=C_REACTIVE, lw=0.7))

    for ax in (ax_w, ax_b, ax_l):
        _peak_markers(ax, None, None)
    fig.suptitle("Reactive policy — cosine YCSB-T, 300 s", fontsize=9, y=1.01)
    out = FIGDIR / "eval_reactive_policy.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=200)
    plt.close(fig)
    print(f"  wrote {out.name}")


def _single(figname: str, plot_fn) -> None:
    fig, ax = plt.subplots(figsize=(3.5, 2.0))
    plot_fn(ax)
    _peak_markers(ax, None, None)
    fig.tight_layout()
    out = FIGDIR / figname
    fig.savefig(out, bbox_inches="tight", dpi=200)
    plt.close(fig)
    print(f"  wrote {out.name}")


def figures_styx(run: dict) -> None:
    w, b, l = run["workers"], run["backlog"], run["latency"]

    def workers(ax):
        ax.step(w.index, w.to_numpy(), where="post", color=C_STYX, lw=1.8)
        ax.set_ylabel("Worker count"); ax.set_title("(a) Worker count")
        ax.set_yticks([4, 5, 6, 7, 8, 9, 10]); ax.set_ylim(3, 11)
        _annotate_worker_steps(ax, w, C_STYX)
        ax.text(75, 10.6, "peak 1", ha="center", fontsize=6, color="#aaaaaa")
        ax.text(225, 10.6, "peak 2", ha="center", fontsize=6, color="#aaaaaa")

    def backlog(ax):
        ax.plot(b.index, b.to_numpy() / 1e3, color=C_STYX, lw=1.5)
        ax.fill_between(b.index, b.to_numpy() / 1e3, alpha=0.15, color=C_STYX)
        ax.set_ylabel("Queue backlog (K messages)"); ax.set_title("(b) Queue backlog")
        ax.set_ylim(bottom=0)
        first_up = w[w.diff() > 0]
        if not first_up.empty:
            t_up = first_up.index[0]
            bl = float(b.reindex([t_up], method="nearest").iloc[0])
            ax.axvline(t_up, color=C_STYX, lw=1, linestyle="--", alpha=0.6)
            ax.annotate(f"1st trigger\n{bl/1e3:.0f}K", xy=(t_up, bl / 1e3),
                        xytext=(t_up + 18, bl / 1e3 + 35), fontsize=6.5, color=C_STYX,
                        arrowprops=dict(arrowstyle="->", color=C_STYX, lw=0.7))

    def latency(ax):
        ax.plot(l.index, l.to_numpy(), color=C_STYX, lw=1.5, marker="o", markersize=3)
        ax.axhline(LATENCY_THRESHOLD_MS, color=C_THRESH, lw=1, linestyle=":", alpha=0.8)
        ax.text(302, LATENCY_THRESHOLD_MS, "250 ms\nthreshold", fontsize=6, color=C_THRESH,
                va="center", clip_on=False)
        ax.set_ylabel("Avg epoch latency (ms)"); ax.set_title("(c) Epoch latency")
        ax.set_ylim(bottom=0)
        post = l[l.index > 90]
        if not post.empty:
            ax.annotate(f"{post.min():.0f} ms", xy=(post.idxmin(), post.min()),
                        xytext=(post.idxmin() + 15, post.min() + 400), fontsize=6.5,
                        color=C_STYX, arrowprops=dict(arrowstyle="->", color=C_STYX, lw=0.7))

    _single("eval_styx_workers.pdf", workers)
    _single("eval_styx_backlog.pdf", backlog)
    _single("eval_styx_latency.pdf", latency)


def main() -> None:
    FIGDIR.mkdir(parents=True, exist_ok=True)
    reactive = load_run(DATA / "reactive_policy")
    styx = load_run(DATA / "builtin_styx_autoscaler")

    print("Eval figures:")
    figure_reactive(reactive)
    figures_styx(styx)

    print("\nSummary (post-warmup window):")
    for name, run in [("Reactive policy", reactive), ("Built-in Styx", styx)]:
        b, l = run["backlog"], run["latency"]
        print(f"  {name:16s} worker-seconds={run['worker_seconds']:.0f}  "
              f"peak_backlog={b.max():.0f}  end_backlog={b.iloc[-1]:.0f}  "
              f"peak_latency={l.max():.0f}ms")
    print(f"\nFigures written to {FIGDIR}")


if __name__ == "__main__":
    main()
