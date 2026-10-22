# Review: W5 governor pre-registration draft (experiments/w5_governor.yaml, uncommitted) + budget sim
Reviewer: Claude (cloud session). Status key: [BLOCKER] fix before committing · [CHANGE] · [ANSWER] to the yaml's open questions · [NOTE]

## Overall
The structure is good: tuning blocks separated from evaluation blocks, a feasibility gate, a pre-stated "earns its place" reading, abort
rules and a run protocol with the lessons learned. Two blockers would make the confirmatory test either impossible to pass or blind to
the one place the learned controller is supposed to win.

## Findings
1. [BLOCKER] HW2 is impossible to pass as written. Evaluation blocks are 4–10 = 7 blocks, so the smallest one-sided Wilcoxon p is
   1/2^7 = 0.0078. Holm over 8 tests needs p ≤ 0.05/8 = 0.00625 for the first rejection, and 0.0078 > 0.00625, so no test can
   ever reject. Fix both:
   (a) primary family = the 60 W budget only (35 W exploratory, as the yaml's open question suggests), and
   (b) 10 EVALUATION blocks (13 total with the 3 tuning blocks), so the floor is 0.00098.
   State the run-time estimate for that size. If one session is too long, register that blocks may run across sessions with identical
   protocol and say how a session break is recorded.
2. [BLOCKER] The confirmatory test never shows the learned controller an unseen workload. W5b's background is Llama-3.2-3B only, which is
   also in the W5a training data, and g'B/c'B constants are tuned on the same workload. The plan's own rationale for the AI (journal 0037,
   plan addendum) is that static settings fail on workloads they weren't tuned for. Add an unseen-workload scene to the primary family:
   - hold one background workload OUT of W5a entirely (e.g. the image generator, or Llama 8B if it loads); its data never touches model
     selection or tuning;
   - in W5b, run it with g'B and c'B constants tuned on the other workloads (the realistic deployment), and d'B with the W5a-selected
     model starting from its prior and learning online;
   - make this scene (call it S5) part of the pre-stated "earns its place" reading: d'B earns its place if it wins in S1 OR S5 under 60 W
     and doesn't lose in S0/S2.
   Without S5 the experiment tests a case where static settings already have oracle knowledge of the workload, which the sim already shows
   they win.
3. [CHANGE] Run the same check in the simulator first (post-hoc, labelled, cheap): an S5 where g'B/c'B are tuned on the L-derived plant and
   evaluated on a plant with a different knee/roofline (e.g. the fp16-proxy curve, knee 1050, or a compute-heavier curve). If d'B can't
   win even there, the learned model needs work before hardware time is spent. Use tuning seeds only for any d'B fixes (the 9% token-rate
   bias, the ~17 W unused budget), then one new held-out evaluation, recorded as a second round.
4. [ANSWER] S3 (emulated thermal cap): keep it exploratory.
5. [ANSWER] W5a size: the full factorial (7 x ~7 x 6 x 4 ≈ 1,176 cells x ~35 s ≈ 11+ h before cool-downs) is too large. Use a
   pre-registered space-filling design (e.g. a Latin-hypercube or random subset of ~250–300 cells), stratified so every remaining workload x
   fg cost pair gets coverage at every clock level, split across two sessions. Keep one workload fully held out (finding 2).
6. [NOTE] Budget sim: reporting that this d'B fails its own rule (−5.0 S0, −8.1 S1d vs c'B) is the right call. It's a property of this
   implementation (9% optimistic token prediction, ~17 W budget left unused), not of learned control. The W5a-selected model replaces it.
7. [NOTE] Double-execution quirk: the warm-once rule is a reasonable mitigation. Record it as a limitation, and verify that no earlier
   experiment's exe was un-warmed on its first measured run (see decision on L below).

## Decision on L
Yes: check part L for the double-execution effect (the first launch of llama_decode_bench.exe: cell counts, token-log line counts, any
duplicated ring/file side effects in the first cell). It's cheap, and L carries the headline power result.
