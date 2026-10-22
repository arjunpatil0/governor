"""Telemetry daemon: one process, fixed period (default 20 Hz), QPC timestamps, rows appended to a CSV by a writer thread so a slow disk never stalls the loop.

Every source (callable -> dict of numbers) gets, per row, its fields plus `<name>_changed` (value differs from the previous poll) and `<name>_age_ms`
(time since the value last changed as observed by this loop). This is deliberate: the capability audit shows NVML power updates at a median 22 ms (p90 500 ms),
utilisation at 1 s and temperature at 1.8 s, so a 20 Hz poll mostly returns repeated values and must never present a stale value as fresh.
Shared rings (fg frames, bg tokens) are drained each iteration; records lost to overflow are counted. The first CSV line is `# key=value ...` metadata
(execution mode etc.). Stats: rows, dropped_rows (writer queue full), loop_late_p99_ms, ring_dropped."""
import csv
import queue
import threading
import time

import numpy as np


class Daemon:
    def __init__(self, sources, period_s=0.05, path=None, header=None, rings=None, write_hook=None, queue_max=1024, clock=time.perf_counter):
        self.sources, self.period_s, self.path, self.header = dict(sources), period_s, path, dict(header or {})
        self.rings, self.write_hook, self.clock = dict(rings or {}), write_hook, clock
        self.q = queue.Queue(maxsize=queue_max)
        self.stats = dict(rows=0, dropped_rows=0, loop_late_p99_ms=0.0, ring_dropped={k: 0 for k in self.rings})
        self.latest = {}                                       # latest source values and new ring records, for in-process consumers (the governor loop)
        self._prev, self._changed_at, self._late = {}, {}, []

    # ---- writer thread
    def _writer(self):
        f = open(self.path, "w", newline="", encoding="utf-8") if self.path else None
        w, last_flush = None, time.time()
        try:
            if f:
                f.write("# " + " ".join(f"{k}={v}" for k, v in self.header.items()) + "\n")
            while True:
                row = self.q.get()
                if row is None:
                    break
                if self.write_hook:
                    self.write_hook()
                if f:
                    if w is None:
                        w = csv.DictWriter(f, fieldnames=list(row)); w.writeheader()
                    w.writerow(row)
                    if time.time() - last_flush > 1.0:
                        f.flush(); last_flush = time.time()
        finally:
            if f:
                f.close()

    # ---- one poll
    def poll_once(self, t):
        row = {"t_qpc_s": f"{t:.6f}"}
        for name, src in self.sources.items():
            vals = src()
            prev = self._prev.get(name)
            changed = prev is None or vals != prev
            if changed:
                self._changed_at[name] = t
            self._prev[name] = vals
            for k, v in vals.items():
                row[f"{name}_{k}"] = v
            row[f"{name}_changed"] = int(changed)
            row[f"{name}_age_ms"] = round((t - self._changed_at[name]) * 1000.0, 3)
            self.latest[name] = vals
        for name, ring in self.rings.items():
            rec, dropped = ring.read_new()
            self.stats["ring_dropped"][name] += dropped
            row[f"{name}_n"] = len(rec)
            self.latest[name + "_new"] = rec
        return row

    def run(self, duration_s):
        th = threading.Thread(target=self._writer, daemon=True)
        th.start()
        t0 = self.clock()
        nxt = t0
        while self.clock() - t0 < duration_s:
            while True:                                        # sleep to the absolute schedule; spin the last 2 ms
                rem = nxt - self.clock()
                if rem <= 0:
                    break
                time.sleep(rem - 0.002) if rem > 0.004 else None
            t = self.clock()
            self._late.append(max(0.0, t - nxt) * 1000.0)
            row = self.poll_once(t)
            row["loop_late_ms"] = round(self._late[-1], 3)
            try:
                self.q.put_nowait(row); self.stats["rows"] += 1
            except queue.Full:
                self.stats["dropped_rows"] += 1
            nxt += self.period_s
            if nxt < self.clock() - 5 * self.period_s:        # fell far behind (e.g. suspended): resynchronise rather than burst
                nxt = self.clock()
        self.q.put(None)
        th.join(10)
        self.stats["loop_late_p99_ms"] = float(np.percentile(self._late, 99)) if self._late else 0.0
        return self.stats
