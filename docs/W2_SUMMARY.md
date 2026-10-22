# W2 phase summary (characterisation), closed 2026-10-22
Scope: (a) residual-wait model for a foreground sharing the GPU with a time-sliced background, (b) effect of a device-wide SM clock lock on a compute-bound foreground, (c) decode-like background with a measured clock knee. Pre-registered in experiments/w2_colocation.yaml with dated addenda; reviewer checkpoint after each result. Every number below traces to the file named. Hardware: RTX 4070 Laptop (36 SMs), Windows 11, HAGS on, driver 616.92.

| Part | Result | Evidence |
|---|---|---|
| C: decode proxy knee | fp16 proxy knee 1050 MHz; HC1 supported; the int4 proxy lacks construct validity (hand-written scalar-dequant kernel) and is not used in governor claims | data/w2_C_results.md, journal 0014, f6f61ec |
| B: clock lock vs compute-bound fg | service time ratio vs 1800 MHz 1.999 / 1.500 / 1.203 at 900 / 1200 / 1500 MHz (predicted 2.000 / 1.500 / 1.202): HB1 supported; HB2 supported without background, not testable with the memory background (the reference itself was overloaded) | data/w2_B_results.md, journal 0016, c51b499 |
| A: residual-wait model | HA1 (wait proportional to the residual slice) NOT supported, classified preempted_or_concurrent; HA2 not supported | data/w2_A_results.md, journal 0020, ea8546a |
| A2: secondary | wait independent of arrival phase; plateau fit tau 0.260 ms (exploratory); no priority effect; superlinear fg slowdown with duty; SA2 k corrected to 0.983 after the regressor artefact | data/w2_A_secondary_results.md, journals 0023, 0024, 9cb6f82, 4f8216d |
| L: llama.cpp validation | knee 1500 MHz (intermediate), energy optimum 1050 MHz at 0.526 J/token vs 0.915 unlocked, 97.25 tok/s at 56.3 W at 1500 MHz vs 101.1 tok/s at 92.0 W unlocked, token ids identical in 10/10 blocks | data/w2_L_results.md, journal 0027, 47a64be |
| G: %globaltimer timeline | Registered: P1, P2, P7 held; P3-P6 and P8 did not hold; q = 0.374 ms, s = 0.148 ms. Post-hoc: the fg/bg overlaps are probably a block-edge measurement artefact, not concurrency; the context switch is nearly synchronous across SMs (spread 1-5 us). The plateau replicated on fresh seeds (0.226 / 0.262 / 0.295 / 0.304 ms vs A 0.226 / 0.255 / 0.287 / 0.298). | data/w2_G_results.md, data/w2_G_posthoc.md, journals 0032, 0033, 0f78435, 3137cff |

## What carries into the governor (W4-5)
1. A compute-bound foreground slows 1:1 with the SM clock (B), so the governor must not lower the clock of a compute-bound deadline task beyond its slack.
2. A co-run foreground waits up to about 0.26 ms regardless of background slice length beyond that (A2 fit, G P1/P2 replication); the wait is time-slice mechanics, not residual-slice length (HA1 failed).
3. For a decode background the clock knee depends on the engine; measure it on the actual workload (ADR-0002, proxy lesson). On llama.cpp Q4_K_M the energy optimum is 1050 MHz (0.526 vs 0.915 J/token unlocked, -42.5%; 0.884 of the unlocked-relative throughput at that level) and the 95%-throughput knee is 1500 MHz.
4. Time-slice quantum about 0.375 ms with a switch gap of about 0.15 ms; the slowdown of a long fg is about 2 + 2s/q = 2.79 (post-hoc reading, between A2's observed 2.65 and 2.91).

## Limitations
- WhatsApp and Discord ran idle in the background during W1-W2 (no process list recorded before journal 0032); in G they were quit at an unrecorded time, block 0 flagged, verdicts identical without it.
- Armoury Crate mode "not recorded; inferred non-Turbo" for A/B/C; Performance for A2 and G (journal 0022).
- One GPU, one driver, one OS configuration; the llama.cpp validation is one model, one quantisation, batch 1.
- G: the block-edge artefact hypothesis is untested directly; q and s share the on-interval definition; the Nsight Compute check of the intra-SM starvation was not done.
- G raw rec files (523 MB) are stored outside git (SHA-256 manifest in git).

## Follow-ups (not scheduled; characterisation stops here)
Per-warp timing to settle the block-edge artefact; Nsight Compute warp-state check of the 4th-6th block starvation; why the unlocked smoke control showed no overlap while locked-clock data did.
