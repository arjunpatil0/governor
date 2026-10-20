# 0003 — Re-analysis: barriers, not launch overhead
Date: 2026-10-18 · Phase: pre-project · Author: reviewer
## Question
Does launch overhead explain v2's results?
## What we did
Re-analysed v2 scheduler traces (variance_gpu_project experiments/variance_adaptive_v2/analysis/barrier_model.py).
## What happened
- Host overhead (t_total_chunk − t_kernel) summed to only 5–34 ms per run; the multi-second gaps were inside kernel time.
- Per-chunk time ≈ a + b·(max task cost) + c·(Σ warp maxima) fit R² 0.97–0.98; per-arm totals within ~5%.
  This is Graham's list-scheduling bound: T ≈ W/S + Σ L_i. Every chunk boundary is a barrier that pays the slowest warp.
- ADAPTIVE vs STATIC-MATCHED at equal chunk counts: ADAPTIVE put its extra barriers where the tail was heaviest.
- Warp efficiency: 0.46 (B/C), 0.19 (D); GPU ~14% occupied.
- Literature: dynamic loop self-scheduling (Kruskal & Weiss 1985; factoring, Hummel et al. 1992; adaptive factoring,
  Banicescu) supports variance → smaller chunks only with many independent workers and no global barrier.
  v2 had one worker plus a barrier, so the theory inverts.
## Interpretation
The project's core idea was sound in another execution model and wrong in the one implemented.
## Next
Evaluate the original governor brief (0004).
