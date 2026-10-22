"""Snapshot of running processes (name, instance count, summed CPU%) taken at run start and stored in meta.json."""
import time

import psutil


def snapshot(interval=1.0, procs=psutil.process_iter):
    """CPU% is measured over `interval` seconds (first call primes, second reads). Processes that vanish or deny access are skipped."""
    live = []
    for p in procs(["name"]):
        try:
            p.cpu_percent(None); live.append(p)
        except (psutil.Error, OSError):
            pass
    if interval:
        time.sleep(interval)
    agg = {}
    for p in live:
        try:
            c = p.cpu_percent(None); n = p.info.get("name") or "?"
        except (psutil.Error, OSError):
            continue
        e = agg.setdefault(n, {"name": n, "count": 0, "cpu_pct": 0.0}); e["count"] += 1; e["cpu_pct"] += c
    return sorted(agg.values(), key=lambda e: (-e["cpu_pct"], e["name"]))


def chrome_running(processes):
    """True if any browser process of the snapshot is Chrome (the run checklist requires it closed; the state is recorded in meta.json of every run)."""
    return any(str(e.get("name", "")).lower().startswith("chrome") for e in processes)
