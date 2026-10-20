# 0001 — Origin: from a resource-governor brief to GPU chunking (reconstructed)
Date: 2026-08-20 (reconstructed 2026-10-21 from git history and docs) · Phase: pre-project · Author: reviewer
## Question
Original brief: an "AI-based personal device resource governor": a local agent that reallocates CPU/GPU/RAM
between competing tasks with a learned model.
## What we did
Before any code, the problem got narrowed to "variance-aware adaptive chunking": one synthetic CUDA kernel,
chunk size adjusted from the variance of recent chunk times. First commit 9b6ea32 (variance_gpu_project).
v1 reported tuned adaptive 4.9% faster than static (n=5 trials).
## Setbacks / surprises (identified later)
The narrowing dropped every defining element of the brief: competing apps, a user-facing QoS metric,
power/thermal limits, learning, real workloads. Only "dynamic" and "GPU" survived. The 4.9% claim was later
contradicted (0002) and retracted (variance_gpu_project a9239b8).
## Lesson
Write down the objective and the actuators before narrowing a problem. A narrowing that discards the objective
is a different project.
