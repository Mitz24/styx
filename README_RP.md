**Adaptive Resource Allocation in Stateful Stream Processing - A Control-Based Autoscaling Policy for the Styx Runtime**

Mihai-Valentin Nicolae, TU Delft (CSE3000 Research Project)

This document reproduces the figures and experiments in the paper. All commands are
self-contained and run from the repository root.

## Prerequisites

- **Docker** and **Docker Compose** 
- **Python 3.14**.

## Setup

```bash
# Dependencies (client + plotting)
pip install styx-package/.
pip install -r requirements.txt
pip install pandas numpy matplotlib
```

## 1. Reproduce the figures from the paper

```bash
python scripts/generate_eval_figures.py
python scripts/generate_motivation_figures.py
```

The six figures are written to `results/figures/`:

| Figure file | Source run(s) under `results/paper_experiments/` |
| --- | --- |
| `eval_reactive_policy.pdf` | `reactive_policy/` |
| `eval_styx_workers.pdf`, `eval_styx_backlog.pdf`, `eval_styx_latency.pdf` | `builtin_styx_autoscaler/` |
| `motivation_comparison.pdf`, `motivation_gradient.pdf` | `motivation_static/{4..9}workers/` |

---

## 2. Re-run the experiments

The built-in autoscaler (baseline) uses the Chronos forecaster, so download the model
once before running it. The coordinator image bakes in `models/`, and the run scripts
rebuild the image automatically, so the next baseline run picks it up:

```bash
mkdir -p models/chronos-bolt
pip install -U "huggingface_hub[cli]"
hf download amazon/chronos-bolt-tiny --local-dir models/chronos-bolt
```

The reactive policy runs with `ENABLE_CHRONOS=false` and does **not** use the model.

Each run automatically writes `backlog.csv`, `num_workers.csv`, `epoch_latency.csv`,
`committed_tps.csv`, `metadata.json`, and an `overview.png` into its output directory.

> **Always run `scripts/reset_styx.sh` before and between experiments.** Leftover containers and networks will otherwise cause the next run to crash.

### Static baselines (motivation sweep)

```bash
for w in 4 5 6 7 8 9; do
  bash scripts/run_experiment.sh ycsbt 1500 100000 $w 0.99 4 300 results/static_${w}w 30 1000 cosine
  bash scripts/reset_styx.sh
done
```

### Reactive policy — `main` branch

```bash
ENABLE_CHRONOS=false REACTIVE_DOWNSCALE=true bash scripts/run_autoscale_experiment.sh ycsbt 1500 100000 4 0.99 4 300 results/reactive_policy 30 1000 cosine 6
bash scripts/reset_styx.sh
```

### Built-in Styx autoscaler (baseline) — `baseline-builtin-autoscaler` branch

```bash
git checkout baseline-builtin-autoscaler
bash scripts/run_autoscale_experiment.sh ycsbt 1500 100000 4 0.99 4 300 results/builtin_styx_autoscaler 30 1000 cosine 6
bash scripts/reset_styx.sh
git checkout main
```