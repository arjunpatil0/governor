# ADR-0003 — Windows primary platform; Linux arm optional
Status: accepted · Date: 2026-10-19
## Context
RTX AI PC users are on Windows (WDDM); Linux offers MPS/RAPL/sched_ext.
## Options considered
(a) Windows only; (b) Linux only; (c) Windows primary, Linux later
## Decision
(c)
## Rationale
Realism of the target platform first; Linux used only if Windows actuation proves insufficient.
## Evidence
capability audit.
