# STATUS (overwritten at every stop)
Updated 2026-10-23 · Phase: W4-5. W5 yaml committed (1683d3c). Models downloaded and verified, load pre-check PASSED, held-out = Llama-3.1-8B, W5a list FROZEN. Ready for W5a session 1 (your hands; commands in chat and docs/W5A_SESSION1.md).

## Just did (journals 0044-0045; plan addenda J and K)
- Final review applied and committed; change 7 explained (analysis artefact); analysis/w5_analysis.py (13 tests); W5a design/metrics/runner (tests green); driver context shift; build test restores the exe.
- Downloads sha256-OK; load pre-check: 1B 17/17, 3B 29/29, Phi-3.5-mini 33/33, 8B 33/33 layers on the GPU at context 2048. Held-out = Llama-3.1-8B (no fallback). Other family = Phi-3.5-mini.
- W5a list frozen: seed 20261023, 280 cells, sessions 94 / 93 / 93, sha256 8f913519a9988a316ad1c8275b303d60ed25c49ce0831cc240f4f8b8f7458d77.

## Waiting for
1. You: W5a session 1 (docs/W5A_SESSION1.md): helper restart (Admin), then in a normal shell: `shift` smoke, one trial cell (--limit 1), then the session. Paste back the outputs of the first two steps before running the full session.
2. Reviewer: nothing pending.

## Risks (not verified yet)
- experiments/w5a/run.py and the `shift` smoke step have had no hardware run; the trial cell is the first.
- Session length: estimate 2.2 h for 94 cells (yaml says at most 2 h); stop between cells if needed, the runner resumes.

## Notes
- Windows Update and NVIDIA driver updates paused by you. Do NOT rebuild the driver exe, run the build test, or change the tree between sessions (clean committed tree is required by the runner).
- Run checklist: Administrator PowerShell for the helper; AC power; Armoury mode stated (Performance); Chrome closed; tray apps quit; no clicking; hands off.
