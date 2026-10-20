import sys, threading, time
import numpy as np, pynvml as nv
sys.path.insert(0, r"C:\Users\arjun\governor\experiments\w2_colocation"); sys.path.insert(0, r"C:\Users\arjun\governor\workloads\common")
import pilot as pl
from loadgen import poisson_arrivals, latencies
nv.nvmlInit(); h = nv.nvmlDeviceGetHandleByIndex(0)
w = pl.W2()
cal = {"fma": pl.calibrate(w, 1, [2000, 8000, 32000, 64000]), "mem": pl.calibrate(w, 0, [200, 800, 2000, 4096, 8192])}
log = []; stop = threading.Event()
def poll():
    while not stop.is_set():
        log.append((w.d.w2_qpc_now(), nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_SM), nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_MEM), nv.nvmlDeviceGetPowerUsage(h)/1000, nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU))); time.sleep(0.02)
threading.Thread(target=poll, daemon=True).start()
for nm, kind in (("fma",1),("mem",0)):
    for ms in (0.1, 1.0, 1.0, 1.0):
        u = int(pl.units_for(cal[nm], ms))
        a = poisson_arrivals(200.0, 2000, seed=3, t0=w.d.w2_qpc_now() + 0.5)
        tl, tc, g = w.fg_run(kind, a, u); lat = latencies(a, tc)*1e3
        bad = np.flatnonzero(lat > 20)
        s = f"{nm} {ms}: p50 {np.median(lat):.2f} max {lat.max():.0f} ms >20ms:{len(bad)}"
        if len(bad):
            ep = np.split(bad, np.flatnonzero(np.diff(bad) > 1) + 1)
            for e in ep:
                i0 = e[0]; worst = e[np.argmax(lat[e])]
                # the stalled request is the one that did not complete in time: find first request in the episode with gpu_ms >> service
                big = np.flatnonzero(g > 20)
                s += f" | episode starts req {i0} (t=+{a[i0]-a[0]:.2f}s) len {len(e)} worst {lat[worst]:.0f}; gpu_ms>20 reqs: {big[:3].tolist()} ({g[big[:1]].round(0).tolist()} ms)"
                t_a = a[i0]; near = [(round(t - t_a, 2), c, m, round(p), tmp) for (t, c, m, p, tmp) in log if -0.1 < t - t_a < 0.3][:4]
                s += f" | nvml near: {near}"
        print(s)
stop.set()
