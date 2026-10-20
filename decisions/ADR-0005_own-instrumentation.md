# ADR-0005 — Own instrumentation for frame times and per-process GPU accounting; PresentMon deferred to W9–10
Status: accepted · Date: 2026-10-20
## Context
PDH does not attribute CUDA compute; PresentMon only sees presented frames.
## Options considered
(a) rely on OS counters; (b) instrument our own fg/bg workloads with CUDA events/QPC
## Decision
(b)
## Rationale
We own both synthetic workloads; OS attribution is unreliable on WDDM.
## Evidence
data/capability_audit.md.
