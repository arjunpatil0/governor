# Review: W5a selection re-run (addendum N, data/w5a/selection2.md, journal 0049)
Reviewer: Claude (cloud session). Status key: [DECISION] · [CHANGE] · [NOTE]

## Overall
Run as registered, nothing changed after results, fallback applied. Correct. The result also contains a real finding that must not get lost.

## Decisions
1. [DECISION] Confirm the registered fallback: d'B in W5b uses the grey-box ModelController with the safety shield. That is what addendum
   N fixed in advance, and the integrity of the study depends on honouring it.
2. [DECISION] HGB's near-miss is recorded as a FINDING, not only a limitation: the data-driven model predicted feasibility far more safely
   than the physics-based grey-box (false-feasible cells 0.8% [0–4.6%] vs 22.5%; picks 0/8 vs 4/10), with the lowest regret (0.18) and a
   2.4 W power error, but missed the tok/s coverage gate by 1.8 points (88.2% vs 90%), driven by the 1B fold. Under the registered rule it
   was not adopted. Report exactly that, plus the limitation that a per-workload throughput scale (1B is 6–14x faster) is what the
   interval method lacked.

## Changes before W5b data (dated addendum O, committed before T1)
3. [CHANGE] The grey-box is OPTIMISTIC about feasibility on this data (39 false-feasible cells). The registered yaml already lets the
   tuning blocks T1–T3 set d'B's constants. State explicitly in addendum O that d'B's feasibility safety margin (the k in predicted
   p99/miss + k·sigma, or the equivalent feasibility threshold) is one of those constants, tuned on T1–T3 known-workload data only by a
   pre-stated rule: the smallest margin that gives ≤ 1% mean miss across the T1–T3 d'B cells. The W5a result motivates it; no W5a number
   is used to set it.
4. [CHANGE] Optional but recommended: an EXPLORATORY arm d'B-HGB (the hybrid with HGB as the active-branch predictor, same shield,
   margin tuned by the same rule on T1–T3), run only in S1 and S5 at 60 W in evaluation blocks 4–8 (10 extra cells, ~12 min). It is
   outside every confirmatory family and is reported descriptively. This tells you whether the confirmatory verdict on d'B is about
   learning in general or about the weaker predictor that the fallback forced. Register it in addendum O before any W5b data, or decline it
   explicitly.

## Notes
5. [NOTE] No candidate picked on c14 in leave-one-condition-out: report that the heaviest condition had no informative decisions.
6. [NOTE] First elevated check of the Ctrl+C fix at the start of T1: one press, prompt back within ~2 s, "clock reset done" printed.
