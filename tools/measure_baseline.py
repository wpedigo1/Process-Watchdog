#!/usr/bin/env python3
"""Read-only resource baseline measurement for Process Watchdog.

Locates every running process named 'ProcessWatchdog.exe' and reports
memory, CPU, thread, and handle metrics. This script NEVER kills,
terminates, suspends, or otherwise mutates any process. It only reads.

Usage:
    python tools/measure_baseline.py

A PyInstaller --onefile exe normally runs as a parent/child pair; both are
reported. No attempt is made to guess which is the 'real' one.
"""

import sys
import time

import psutil

TARGET_NAME = "ProcessWatchdog.exe"

NUM_CPU_SAMPLES = 12
NUM_MEM_SAMPLES = 3
MEM_SAMPLE_GAP_SECONDS = 10.0


def _median(values):
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return None
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def main():
    procs = [p for p in psutil.process_iter(attrs=["name", "pid", "cmdline"])
             if (p.info.get("name") or "").lower() == TARGET_NAME.lower()]

    if not procs:
        print(f"No running process named '{TARGET_NAME}' was found. Nothing to measure.")
        print("Launch dist\\ProcessWatchdog.exe first, then rerun this script.")
        sys.exit(0)

    print(f"Found {len(procs)} process(es) named {TARGET_NAME}:")
    for p in sorted(procs, key=lambda pr: pr.pid):
        try:
            ppid = p.ppid()
        except Exception as exc:
            ppid = f"UNMEASURED ({exc})"
        print(f"  pid={p.pid} ppid={ppid} cmdline={p.info.get('cmdline')}")
    print()

    print("=== Per-process snapshot ===")
    snapshots = {}
    for p in sorted(procs, key=lambda pr: pr.pid):
        snapshots[p.pid] = {}
        try:
            mi = p.memory_info()
            snapshots[p.pid]["rss"] = mi.rss
            snapshots[p.pid]["private_bytes"] = getattr(mi, "private_bytes", None)
            snapshots[p.pid]["working_set"] = getattr(mi, "wset", None)
        except Exception as exc:
            snapshots[p.pid]["rss"] = snapshots[p.pid]["private_bytes"] = snapshots[p.pid]["working_set"] = \
                f"UNMEASURED ({exc})"
        for key, call in (("num_threads", p.num_threads),
                          ("num_handles", p.num_handles),
                          ("create_time", p.create_time)):
            try:
                snapshots[p.pid][key] = call()
            except Exception as exc:
                snapshots[p.pid][key] = f"UNMEASURED ({exc})"

    for pid, info in sorted(snapshots.items()):
        print(f"pid={pid}")
        for key in ("rss", "private_bytes", "working_set", "num_threads", "num_handles", "create_time"):
            print(f"  {key}={info[key]}")
    print()

    print(f"=== CPU sampling ({NUM_CPU_SAMPLES} x cpu_percent(interval=1.0)) ===")
    cpu_buckets = {p.pid: [] for p in procs}
    for _ in range(NUM_CPU_SAMPLES):
        for p in procs:
            try:
                cpu_buckets[p.pid].append(p.cpu_percent(interval=1.0))
            except Exception as exc:
                cpu_buckets[p.pid].append(f"ERR:{exc}")
    for pid in sorted(cpu_buckets):
        nums = [v for v in cpu_buckets[pid] if isinstance(v, (int, float))]
        if not nums:
            print(f"pid={pid} CPU%: UNMEASURED (no valid samples; raw={cpu_buckets[pid][:1]})")
        else:
            print(f"pid={pid} CPU% min={min(nums):.2f} median={_median(nums):.2f} max={max(nums):.2f} (n={len(nums)})")
    print()

    print(f"=== Memory sampling ({NUM_MEM_SAMPLES} samples, ~{MEM_SAMPLE_GAP_SECONDS}s apart) ===")
    for sample_idx in range(NUM_MEM_SAMPLES):
        if sample_idx > 0:
            time.sleep(MEM_SAMPLE_GAP_SECONDS)
        rows = []
        for p in sorted(procs, key=lambda pr: pr.pid):
            try:
                rows.append(f"pid={p.pid} rss={p.memory_info().rss}")
            except Exception as exc:
                rows.append(f"pid={p.pid} UNMEASURED ({exc})")
        print(f"sample {sample_idx + 1}: " + " | ".join(rows))
    print()

    print("Measurement complete. Read-only; no process was terminated.")


if __name__ == "__main__":
    main()
