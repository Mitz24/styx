from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass
class _Sample:
    batch_size: int
    cpu_work_ms: float
    overhead_ms: float


class WorkerCapacityModel:
    """Estimates per-worker max throughput via an affine cost model."""

    def __init__(self, epoch_max_size: int, window_size: int = 60) -> None:
        self.epoch_max_size = epoch_max_size
        self._window: deque[_Sample] = deque(maxlen=window_size)
        self._overhead_window: deque[float] = deque(maxlen=window_size)

    def record(self, batch_size: int, cpu_work_ms: float, overhead_ms: float) -> None:
        if batch_size > 0 and cpu_work_ms > 0:
            self._window.append(_Sample(batch_size, cpu_work_ms, overhead_ms))
            self._overhead_window.append(overhead_ms)

    def fit(self) -> tuple[float, float] | None:
        if len(self._window) < 5:
            return None

        n = len(self._window)
        sx = sy = sxy = sxx = 0.0
        for s in self._window:
            sx += s.batch_size
            sy += s.cpu_work_ms
            sxy += s.batch_size * s.cpu_work_ms
            sxx += s.batch_size * s.batch_size

        denom = n * sxx - sx * sx
        if abs(denom) < 1e-12:
            return None

        beta = (n * sxy - sx * sy) / denom
        alpha = (sy - beta * sx) / n
        return max(alpha, 0.0), max(beta, 1e-6)

    @property
    def median_overhead_ms(self) -> float:
        if not self._overhead_window:
            return 0.0
        vals = sorted(self._overhead_window)
        mid = len(vals) // 2
        return vals[mid]

    def estimate_max_tps(self) -> float | None:
        """
        Projects cpu_work_ms at epoch_max_size using the fitted
        model, adds the median per-epoch overhead, and converts to TPS.
        """
        params = self.fit()
        if params is None:
            return None
        alpha, beta = params
        max_work_ms = alpha + beta * self.epoch_max_size
        max_epoch_ms = max_work_ms + self.median_overhead_ms
        if max_epoch_ms <= 0:
            return None
        return (self.epoch_max_size / max_epoch_ms) * 1000


class SystemCapacityEstimator:
    """Aggregates per-worker models into a system-level capacity estimate."""

    def __init__(self, sequence_max_size: int = 1000, window_size: int = 60) -> None:
        self.sequence_max_size = sequence_max_size
        self.window_size = window_size
        self._models: dict[int, WorkerCapacityModel] = {}

    def get_model(self, worker_id: int) -> WorkerCapacityModel:
        if worker_id not in self._models:
            self._models[worker_id] = WorkerCapacityModel(
                self.sequence_max_size, self.window_size,
            )
        return self._models[worker_id]

    def record(
        self,
        worker_id: int,
        committed_txns: int,
        cpu_work_ms: float,
        overhead_ms: float,
    ) -> None:
        self.get_model(worker_id).record(committed_txns, cpu_work_ms, overhead_ms)

    def estimate_system_capacity(self) -> float | None:
        """
        Return estimated total system TPS across all workers.
        Uses the minimum per-worker capacity (the bottleneck) multiplied
        by the number of workers
        """
        if not self._models:
            return None

        per_worker: list[float] = []
        for model in self._models.values():
            est = model.estimate_max_tps()
            if est is not None:
                per_worker.append(est)

        if not per_worker:
            return None

        bottleneck = min(per_worker)
        return bottleneck * len(self._models)

    def remove_worker(self, worker_id: int) -> None:
        self._models.pop(worker_id, None)
