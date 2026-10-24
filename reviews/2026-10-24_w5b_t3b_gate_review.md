# Review: overnight sitting result, governed-power anomaly, T3b gate (STATUS at 01b658d)
Reviewer: Claude (cloud session). Status key: [BLOCKER] before tonight's run · [FIX] · [NOTE]

## Overall
The sitting itself is clean (137 cells, 0 incidents, Ctrl+C fix confirmed, the no-boost hypothesis confirmed at 1890 MHz). Stopping T3b
behind a diagnostic was the right call. The governed-power anomaly very likely has a known cause that is already in our own record.

## Findings
1. [BLOCKER] Leading explanation for the governed-cell power: NVML energy-counter phantom energy (journal 0005: ~4.2 J per extra read).
   The Governor loop runs at 10 Hz and reads nvmlDeviceGetTotalEnergyConsumption every tick (executors.py ~L313). That is about 10 reads/s,
   so about 4.2 x 10 = 42 W of phantom power on the counter. Statics read 30-70 W; add 42 W and you get 72-112 W. Observed: 63-106 W, mean 90.5 W.
   The temperatures (59-63 C, against 83 C for a real 90 W) agree: the extra power is not real.
   Consequence: the controllers' power loop sees about 40 W that isn't there, so it throttles the background. That would explain 0-10 tok/s.
   Before tonight, pre-register this as addendum O-4:
   (a) Prediction: the energy-counter power on the "Governor with reads" arm exceeds the static arm by ~4.2 J x (Governor reads/s)
       (state the measured read rate); the "Governor without energy reads" arm matches static within 15%; the 250 Hz power-sample mean is
       NOT inflated on any arm.
   (b) Decision rule, so a confirmed diagnosis doesn't cost a night: if (a) holds, the Governor's power signal switches to a source with no
       phantom energy (the mean of nvmlDeviceGetPowerUsage samples over the control window; its ~1.5 s lag is fine for the slow loop),
       and T3b runs with that source. Implement and test that option NOW, behind a flag, so the script can pick it automatically.
       If (a) fails (the no-reads arm is also off), stop. That is a new problem; paste the output.
   (c) The gate output must print all three arms' power on both measures and the predicted vs observed inflation, so the result is readable.
2. [FIX] Audit every earlier hardware result for extra energy reads during a measurement window (trial 1 governed cells, smokes, W5a,
   W1/W2 if any). List which numbers are affected. Cells whose only energy reads are the start/end pair are fine.
   Also make the morning check fail any cell whose energy-counter power and sample-mean power disagree by more than 15% (flag -> fail).
3. [FIX] Token-aware threshold: the clean token duration depends on the clock. A median taken at one clock is wrong after the controller
   changes the clock (downclocking lengthens tokens, so the 3B at a lower clock may not fit even below 6.57 ms). Use the duration scaled to
   the clock being chosen (fg_ratio-style scaling, or a per-clock median once the data exist), or take the conservative upper value.
   Note it in O-3.
4. [NOTE] The clock flip-flops at cell start (1500/1350/1500/1800 in 4 s) are probably the same cause: the power loop reacting to phantom
   power. Re-check after the fix. If they persist, add a short hold or settle period at cell start.
5. [NOTE] At c0 = 7, g'B and eB are infeasible for the 3B and Phi in S0. That's honest and follows from the plant. Before evaluation,
   confirm in writing how the REGISTERED analysis treats an infeasible comparator (counted as 0 tok/s, excluded, or reported separately),
   so the non-inferiority test isn't decided after seeing the data. If the registration is silent, add an addendum now, before any
   evaluation block.
6. Decision on d'B-HGB (O-3 section 5): ACCEPT, with these conditions:
   - It must be d'B with only the feasibility predictor swapped: same margin grid, same slow-loop timing, same fast-loop guard and idle
     branch, same online RLS for the grey-box scalars. Then any difference is the model's.
   - tau(m) = 0.8 + 0.5 m must stay below 1 across the whole margin grid: cap at 0.95. Otherwise the top margins mean "require certainty"
     and the controller never acts.
   - HGB probabilities are not calibrated by default. Calibrate offline on held-out W5a data (isotonic), then freeze. No online re-fitting
     of the HGB itself.
   - It is exploratory (it failed both selection gates), and it is reported that way. Don't build it before tonight's run; the diagnostic
     comes first. If it isn't ready by block 4, drop it as registered.

## Next
O-4 plus the power-source flag and its tests, then the diagnostic + T3b run tonight. Analyse the diagnostic first in the morning.
