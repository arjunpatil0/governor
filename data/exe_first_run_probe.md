# Fresh-exe double-start investigation (no GPU; probe = tests/cpp/probe_start.cpp, appends pid,parent pid,QPC s,image per start)

| launcher | first run of a never-seen exe: seconds | starts | byte-identical copy (new path): seconds | starts | rerun of the same exe: seconds | starts |
|---|---|---|---|---|---|---|
| python_subprocess | 1.3 | 1 | 0.2 | 1 | 0.3 | 1 |
| cmd_c | 1.3 | 1 | 0.3 | 1 | 0.3 | 1 |
| powershell_start_process | 2.4 | 1 | 1.4 | 1 | 1.4 | 1 |
| popen_poll | 1.4 | 1 | 0.3 | 1 | 0.3 | 1 |

Process starts recorded on the first run (pid, parent pid, QPC seconds, image):

- python_subprocess:
  - 38364,31304,468311.227213,C:\Users\arjun\AppData\Local\Temp\exe_probe_szu93yc6\probe_python_subprocess.exe
- cmd_c:
  - 37804,32672,468315.505931,C:\Users\arjun\AppData\Local\Temp\exe_probe_szu93yc6\probe_cmd_c.exe
- powershell_start_process:
  - 9416,18632,468320.299898,C:\Users\arjun\AppData\Local\Temp\exe_probe_szu93yc6\probe_powershell_start_process.exe
- popen_poll:
  - 19544,31304,468327.694572,C:\Users\arjun\AppData\Local\Temp\exe_probe_szu93yc6\probe_popen_poll.exe

## Same measurement with test_shm.exe (named file mappings + ring pushes; 5 pushes = one body execution)

| launcher | run | seconds | body executions (ring pushes / 5) | pid lines | distinct pids |
|---|---|---|---|---|---|
| python_subprocess | first | 0.8 | 2 | 1 | 1 |
| python_subprocess | copy | 0.0 | 1 | 1 | 1 |
| python_subprocess | rerun | 0.0 | 1 | 1 | 1 |
| popen_poll | first | 0.8 | 2 | 1 | 1 |
| popen_poll | copy | 0.1 | 1 | 1 | 1 |
| popen_poll | rerun | 0.1 | 1 | 1 | 1 |