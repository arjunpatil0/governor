# ADR-0002 — Problem: SLO-aware governor for co-located local AI and interactive workloads on an RTX laptop
Status: accepted · Date: 2026-10-19
## Context
Original brief overclaimed novelty and had no objective or actuators (journal 0004).
## Options considered
(a) original brief as written; (b) cost-aware kernel dispatcher (SpMV); (c) SLO-aware co-location governor
## Decision
(c)
## Rationale
Real, current gap (ConsumerBench open problem; G-Assist); NVIDIA-relevant; reuses v2 barrier insight; testable objective: max bg throughput − λ·energy s.t. fg p99 ≤ SLO, temp ≤ limit.
## Evidence
Prior art list in CLAUDE.md.
