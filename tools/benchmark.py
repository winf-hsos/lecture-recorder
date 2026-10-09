"""Test recording with a pause, measuring system load.

    python tools/benchmark.py [--seconds 180]

Every few seconds: total CPU, CPU and memory of OBS, GPU and video encoder
utilization (nvidia-smi). Prints averages idle versus recording.
"""
from __future__ import annotations

import argparse
import statistics
import subprocess
import sys
import time
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import obs_remote as remote

_obs = None


def measure() -> dict:
    """Values averaged over one second; OBS CPU share relative to all cores."""
    global _obs
    if _obs is None or not _obs.is_running():
        _obs = next(p for p in psutil.process_iter(["name"]) if p.info["name"] == "obs64.exe")
        _obs.cpu_percent(None)
    cpu = psutil.cpu_percent(interval=1.0)
    obs_cpu = _obs.cpu_percent(None) / psutil.cpu_count()
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,utilization.encoder",
                          "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout.strip()
    g, e = [x.strip() for x in gpu.split(",")]
    return {"cpu": cpu, "obs_cpu": obs_cpu, "obs_ram": _obs.memory_info().rss // 2**20,
            "gpu": float(g), "enc": float(e)}


def summarize(name: str, values: list[dict]) -> None:
    if values:
        print(f"{name:22}", " | ".join(f"{k} {statistics.mean(v[k] for v in values):.0f}" for k in values[0]),
              f"(n={len(values)})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=180)
    a = ap.parse_args()
    remote.start()
    idle = [measure() for _ in range(4)]
    with remote.Obs() as o:
        o.request("StartRecord")
        start = time.time()
        recording, paused = [], False
        while time.time() - start < a.seconds:
            if not paused and time.time() - start > a.seconds / 2:
                o.request("PauseRecord"); time.sleep(15); o.request("ResumeRecord"); paused = True
                print("paused for 15 s")
            recording.append(measure())
            time.sleep(3)
        path = o.request("StopRecord")["outputPath"]
    print("file:", path)
    print("averages (percent, RAM in MB):")
    summarize("OBS idle", idle)
    summarize("while recording", recording)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
