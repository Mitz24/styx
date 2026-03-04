import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from decimal import Decimal

import requests
import re

PROM = "http://localhost:9090"


def save_data(data, save_dir, filename):
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    with open(os.path.join(save_dir, filename), "w") as f:
        json.dump(data, f, indent=2)


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
    migration_start_time: Optional[float] = None
    migration_end_time: Optional[float] = None
    zipf_const: Optional[float] = None
    interval_seconds: Optional[int] = None
    delta_tps: Optional[int] = None
    n_threads: int = 1

def get_migration_times(url: str) -> tuple[float, float]:
    resp = requests.get(f"{url}")

    match = re.search(r'^migration_end_time_ms.*$', resp.text, re.MULTILINE)
    migration_end_time = match.group(0).split(" ")[1] if match else None
    match = re.search(r'^migration_start_time_ms.*$', resp.text, re.MULTILINE)
    migration_start_time = match.group(0).split(" ")[1] if match else None
    #print(f"Returning migration times: {migration_start_time}, {migration_end_time}")
    return float(Decimal(migration_start_time)), float(Decimal(migration_end_time)) # handle scientific notations safely

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
        "migration_start_time": params.migration_start_time if params.migration_start_time is not None else None,
        "migration_end_time": params.migration_end_time if params.migration_end_time is not None else None,
    }
    if params.zipf_const is not None:
        metadata["zipf_const"] = params.zipf_const
    if params.interval_seconds is not None:
        metadata["increase_interval"] = params.interval_seconds
    if params.delta_tps is not None:
        metadata["increase_amount"] = params.delta_tps

    metadata["n_threads"] = params.n_threads

    save_data(metadata, params.out_path, "metadata.json")
