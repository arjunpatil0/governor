# Review: W2 pre-registration draft (experiments/w2_colocation.yaml, uncommitted)
Reviewer: Claude (cloud session). Reviewed the uncommitted draft on top of HEAD.
Status key: [CHANGE] edit the draft before committing · [NOTE] no action needed

## Overall
Strong draft. Ten blocks is correct: the minimum one-sided Wilcoxon p is 1/2^n, so n=5 (0.031) could never survive Holm over 6.
The HA1 failure classification, using realised durations, the ρ term, the pilot-motivated secondary labelled as such, clock
validity flags and the finally-block resets are all right. Four changes before committing.

## Findings
1. [CHANGE] HA1(i) regression is underspecified. State "OLS of observed_wait on predicted_wait WITH intercept; the equivalence
   test is on the slope; the intercept and its CI are reported". If the GPU adds a constant switch cost (pilot: ~0.3 ms), a
   no-intercept fit would bias the slope, and a reader can't tell which fit was meant.
2. [CHANGE] HB1's reference level is confounded by boost behaviour. Frames run at ~53% duty, and the pilot showed the unlocked
   SM clock drops during idle gaps (P3: 210 MHz after idle, ~1500 MHz at light load). W1's relative throughputs were measured under
   continuous load, so an unlocked frame may run at a lower average clock than W1 assumed, and HB1 would fail for a reason unrelated
   to the hypothesis. Use the locked 1800 MHz level as HB1's reference: predicted service(L)/service(1800) = rel_W1(1800)/rel_W1(L)
   for L in {900, 1200, 1500}. Report unlocked descriptively, with the per-frame median SM clock logged. Frame sizes stay as piloted.
3. [CHANGE] HC1 compares discrete knee levels, so ties are likely. Specify the zero handling (e.g. scipy zero_method="wilcox",
   zeros dropped) and a pre-stated rule: if fewer than 6 blocks have a nonzero int4−fp16 knee difference, HC1 is reported
   inconclusive (not "not supported"). Also report the per-block knee table.
4. [CHANGE] Overload in B. Where predicted fma service exceeds the frame period (from W1: about 18.2 ms at 1200 MHz and 24.2 ms at
   900 MHz against 16.67 ms at 60 Hz; 120 Hz frames similarly), periodic frames queue without bound and latency measured from
   scheduled release grows with window length. State that at overloaded levels only miss fraction and gpu service time are
   interpreted; latency percentiles are reported but flagged "non-stationary (overload)".
5. [NOTE] A block-cluster percentile bootstrap with only 10 clusters tends to give CIs that are too narrow. Add one line to
   limitations; no design change.
6. [NOTE] SA4's 1 + d reference line is a rough equal-sharing approximation, and the yaml already calls it descriptive. Keep it.

## Requested action
Apply 1–4 to the draft (5 as a limitations line), note them in journal 0012 or a new entry, then commit the yaml with the journal
and respond in reviews/2026-10-21_w2_prereg_response.md.
