# STATUS (overwritten at every stop)
Updated 2026-10-22 · Phase: W4-5. Objective changed to "max tok/s s.t. SLO + power budget"; power-budget rerun, exe quirk, start-up reset, frame loop and W5 yaml DRAFT done without GPU/admin. STOPPED before the hardware smoke and before committing the yaml.

## Just did (commits; see git log)
- Recorded the objective change and the AI model-selection plan in docs/W45_PLAN.md (addendum) before the work; journal 0037.
- Power-budget rerun (post-hoc, 60 W and 35 W; data/w45_sim_budget.md): without a budget the old winners are infeasible (e 74-80 W). Best static = unlocked clock + constant duty throttle (27-37 tok/s at 47-55 W at 60 W). c'B beats it in S0/S1d/S3/S2, loses in S1/S4; d'B ties or loses vs the static (S1 -5.3, S1d -2.4) and beats it only in the idle scene (idle drop, same as eB). d'B vs c'B fails the pre-stated "earns its place" rule (-5.0 S0, -8.1 S1d). At 35 W the per-scenario static is best. Diagnosed d'B deficiencies (rate over-prediction ~9%, 0.1 duty grid, conservative guard probable): journal 0037. Simulation only.
- Fresh-exe double run: not a harness retry. Reproduced with named shared-memory side effects only on a never-seen exe hash; Avast is the active AV (Defender stopped). Inference, not proof. Rule: warm every new exe once (workloads/common/exe_warm.py). I have NOT checked whether the earlier L runs (separately built llama_decode_bench.exe) were affected.
- Start-up reset (helper RESET + nvidia-smi -rgc/-rmc) in Governor.start; synthetic frame loop (workloads/foreground/frame_loop.py, fake-runner tests); docs/W45_SMOKE_SETUP.md with the admin commands.
- experiments/w5_governor.yaml DRAFT written, NOT committed (excluded via .git/info/exclude). Needs your review; open questions at its end.

## Waiting for
- Your review of experiments/w5_governor.yaml (then I commit it with your changes as a dated addendum).
- Your go for the hardware smoke after you ran docs/W45_SMOKE_SETUP.md in an Administrator PowerShell and report its output.

## Decisions needed
1. One question: should I check the L runs (llama_decode_bench.exe) for the double-execution effect before anything else (it affects how far journal 0027's token counts can be trusted), or go straight to the smoke?

## Notes
- Hard kill of the helper leaves the clock locked until restart or nvidia-smi -rgc (the governor start-up now resets).
- Run checklist: Administrator PowerShell; AC power; clean committed tree; Armoury Crate mode stated; Chrome closed; tray apps quit; no clicking in the console; warm every new exe once.
