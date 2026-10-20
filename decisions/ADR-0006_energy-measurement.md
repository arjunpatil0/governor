# ADR-0006 — Energy counter primary, sample-based H2 sensitivity; keep 1.5 s pre-roll
Status: accepted · Date: 2026-10-20
## Context
Energy counter biased (per-read cost, state offset); samples lag ~1.5 s.
## Options considered
(a) counter only; (b) samples only; (c) counter primary + pre-specified sample sensitivity, inconclusive if they disagree; pre-roll 1.5 s vs 3 s
## Decision
(c), 1.5 s
## Rationale
3 s only moved lag bias −11% → −9.6%, not worth re-registration. Outcome: both sources agreed (journal 0006).
## Evidence
experiments/w1_downclock_addendum_2026-10-20.md.
