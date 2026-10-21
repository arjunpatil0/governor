"""Descriptive summary of the B-review finding-3 Nsight Systems traces (journal 0019). usage: python -I analysis/nsys_queue_summary.py <1800|unlocked>
Needs the .sqlite exported with `nsys export --type sqlite` from data/nsys/fma60_membg_<level>.nsys-rep. Counts WDDM 3D-engine queue packets per CUDA process."""
import sqlite3, sys, numpy as np
lv = sys.argv[1]
c = sqlite3.connect(f"data/nsys/fma60_membg_{lv}.sqlite")
pids = [r[0] for r in c.execute("select processId from TARGET_INFO_CUDA_CONTEXT_INFO")]
pid_of = lambda gt: (gt >> 24) & 0xFFFFFF
rows = c.execute("""select s.globalTid, s.start, e.end, e.preempted, e.timeouted, s.packetType, s.dmaBufferSize, s.present
 from WDDM_QUEUE_PACKET_START_EVENTS s join WDDM_QUEUE_PACKET_STOP_EVENTS e on s.queuePacket=e.queuePacket
 where s.engineType=1 and s.dmaBufferSize>0""").fetchall()
res = {}
for p in pids:
    v = [r for r in rows if pid_of(r[0]) == p]
    if not v: print(p, "none"); continue
    a = np.array([(r[1], r[2]) for r in v], float); a = a[np.argsort(a[:, 0])]; d = (a[:, 1] - a[:, 0]) / 1e6
    res[p] = a
    print(f"pid {p}: 3D queue packets {len(v)}  preempted-flag {sum(r[3] for r in v)}  submit->stop ms med/p90/max {np.round([np.median(d), np.percentile(d,90), d.max()],2)}  submit period ms med {np.median(np.diff(a[:,0]))/1e6:.2f}  active {(a[-1,1]-a[0,0])/1e9:.2f}s")
if len(res) == 2:
    (pa, A), (pb, B) = res.items()
    # busy fraction: how much of pid B's active span is covered by packets of A (overlapping queue intervals = both in flight)
    def cov(X, Y):
        n = 0
        for s, e in X: n += int(np.any((Y[:, 0] < e) & (Y[:, 1] > s)))
        return n
    print(f"packets of {pa} overlapping an in-flight packet of {pb}: {cov(A,B)}/{len(A)};   of {pb} overlapping {pa}: {cov(B,A)}/{len(B)}")
hw = c.execute("select count(*) from WDDM_HW_QUEUE_EVENTS").fetchone()[0]
kern = c.execute("select count(*) from sqlite_master where name like 'CUPTI_ACTIVITY_KIND_KERNEL'").fetchone()[0]
print(f"WDDM_HW_QUEUE_EVENTS rows: {hw} (queue creation only); CUDA kernel activity table present: {bool(kern)}; DMA packets owned by our pids: see journal 0019")
