# ADR-0004 — SM clock locking is the GPU power actuator
Status: accepted · Date: 2026-10-20
## Context
NVML power limit unsupported on this laptop; -lgc/-rgc works with admin, applies in ~81 ms, reverts cleanly.
## Options considered
(a) power limit; (b) clock lock; (c) no GPU power control
## Decision
(b)
## Rationale
Only working option. Caveat added 2026-10-21: device-wide, affects foreground too (journal 0006).
## Evidence
data/capability_audit.md.
