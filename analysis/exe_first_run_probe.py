"""Investigation of the "first run of a freshly built exe takes ~14 s and runs its body twice" quirk (journal 0036). Builds tests/cpp/probe_start.cpp, then launches fresh
copies (new bytes = new hash, and byte-identical new file names) through different launchers and counts the process starts each launch produced (pid, parent pid, time).
Writes data/exe_first_run_probe.md. Run: python analysis/exe_first_run_probe.py   (no GPU, no admin)"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VCVARS = r"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
ENV = dict(os.environ, **{"ProgramFiles(x86)": r"C:\Program Files (x86)"})


def build(tmp, tag, define="", src=None):
    src = src or ROOT / "tests" / "cpp" / "probe_start.cpp"
    exe, obj, bat = tmp / f"probe_{tag}.exe", tmp / f"probe_{tag}.obj", tmp / f"b_{tag}.bat"
    bat.write_text("\r\n".join(["@echo off", f'call "{VCVARS}" >nul', f'cl /nologo /O2 /EHsc /std:c++17 {define} "{src}" /I"{ROOT / "workloads" / "background"}" /Fe:"{exe}" /Fo:"{obj}"', ""]))
    subprocess.run([str(bat)], capture_output=True, text=True, timeout=300, env=ENV)
    assert exe.exists()
    return exe


def launch(kind, exe, log):
    t = time.time()
    if kind == "python_subprocess":
        subprocess.run([str(exe), str(log)], timeout=300)
    elif kind == "cmd_c":
        subprocess.run(["cmd", "/c", str(exe), str(log)], timeout=300)
    elif kind == "powershell_start_process":
        subprocess.run(["powershell", "-NoProfile", "-Command", f"Start-Process -Wait -FilePath '{exe}' -ArgumentList '{log}'"], timeout=300)
    elif kind == "popen_poll":
        p = subprocess.Popen([str(exe), str(log)])
        while p.poll() is None:
            time.sleep(0.05)
    return time.time() - t


def starts(log):
    return log.read_text().splitlines() if log.exists() else []


def shm_variant(tmp):
    """Same measurement with test_shm.exe (named file mappings, ring writes): counts ring pushes (5 per body execution) and pid lines per launch."""
    sys.path.insert(0, str(ROOT))
    from telemetry.ring import SeqBlock, SharedRing
    import uuid
    out = []
    for i, kind in enumerate(("python_subprocess", "popen_poll")):
        exe = build(tmp, "shm_" + kind, define=f"/DPROBE_ID={i + 10}", src=ROOT / "tests" / "cpp" / "test_shm.cpp")
        copy = tmp / f"shmcopy_{kind}.exe"
        shutil.copy(exe, copy)
        for label, e in (("first", exe), ("copy", copy), ("rerun", exe)):
            nm = lambda: "Local" + chr(92) + "probe_" + uuid.uuid4().hex
            c, p, r = SeqBlock(nm(), 3, create=True), SeqBlock(nm(), 3, create=True), SharedRing(nm(), 64, 1, create=True)
            log = tmp / f"shm_{kind}_{label}.log"
            env = dict(ENV, PROBE_LOG=str(log))
            t = time.time()
            if kind == "python_subprocess":
                subprocess.run([str(e), c.name, p.name, r.name, "64"], env=env, timeout=300, capture_output=True)
            else:
                pr = subprocess.Popen([str(e), c.name, p.name, r.name, "64"], env=env, stdout=subprocess.DEVNULL)
                while pr.poll() is None:
                    time.sleep(0.05)
            dt = time.time() - t
            out.append((kind, label, dt, r.write_count // 5, len(starts(log)), sorted(set(starts(log)))))
            print("shm", kind, label, f"{dt:.1f}s body-executions(ring/5)={r.write_count / 5:g} pid-lines={len(starts(log))}", flush=True)
    return out


def main():
    tmp = Path(tempfile.mkdtemp(prefix="exe_probe_"))
    rows = []
    for i, kind in enumerate(("python_subprocess", "cmd_c", "powershell_start_process", "popen_poll")):
        exe = build(tmp, kind, define=f"/DPROBE_ID={i + 1}")            # a define changes the bytes, hence the hash: every first launch is a never-seen executable
        l1, l2, l3 = tmp / f"{kind}_first.log", tmp / f"{kind}_copy.log", tmp / f"{kind}_again.log"
        dt1 = launch(kind, exe, l1)
        copy = tmp / f"copy_{kind}.exe"
        shutil.copy(exe, copy)                                           # byte-identical, new path
        dt2 = launch(kind, copy, l2)
        dt3 = launch(kind, exe, l3)
        rows.append((kind, dt1, starts(l1), dt2, starts(l2), dt3, starts(l3)))
        print(kind, f"first {dt1:.1f}s starts={len(starts(l1))} | copy {dt2:.1f}s starts={len(starts(l2))} | rerun {dt3:.1f}s starts={len(starts(l3))}", flush=True)
    L = ["# Fresh-exe double-start investigation (no GPU; probe = tests/cpp/probe_start.cpp, appends pid,parent pid,QPC s,image per start)", "",
         "| launcher | first run of a never-seen exe: seconds | starts | byte-identical copy (new path): seconds | starts | rerun of the same exe: seconds | starts |", "|---|---|---|---|---|---|---|"]
    for kind, dt1, s1, dt2, s2, dt3, s3 in rows:
        L.append(f"| {kind} | {dt1:.1f} | {len(s1)} | {dt2:.1f} | {len(s2)} | {dt3:.1f} | {len(s3)} |")
    L += ["", "Process starts recorded on the first run (pid, parent pid, QPC seconds, image):", ""]
    for kind, dt1, s1, *_ in rows:
        L += [f"- {kind}:"] + [f"  - {x}" for x in s1]
    L += ["", "## Same measurement with test_shm.exe (named file mappings + ring pushes; 5 pushes = one body execution)", "", "| launcher | run | seconds | body executions (ring pushes / 5) | pid lines | distinct pids |", "|---|---|---|---|---|---|"]
    for kind, label, dt, ex, nl, pids in shm_variant(tmp):
        L.append(f"| {kind} | {label} | {dt:.1f} | {ex} | {nl} | {len(pids)} |")
    (ROOT / "data" / "exe_first_run_probe.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
