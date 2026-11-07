# CHANGELOG

## v1.0.0 (2026-11-07)

What this release is: the toolkit as it stood at the end of the pre-registered evaluation, packaged so that someone else can read it, install the importable part and reproduce the no-GPU path. No registered data, results or constants were changed for the release.

Added in the packaging pass
- `README.md` rewritten as a short entry point (three sourced results, a diagram, a component table, a no-GPU and a GPU quickstart, the registered verdict). The previous README is kept in full as `docs/PROJECT_DETAILS.md`.
- `docs/FRAME_HINT_SPEC.md`: the frame-hint record as a spec another team can implement (layout, seqlock protocol, versioning, failure behaviour, a C writer and a C reader that were compiled and checked against the Python binding).
- Importable package `python/governor` with `FrameHintWriter`, `FrameHintReader` and `DeadlineGate`, thin wrappers over `python/slackhint`; `pyproject.toml` (`pip install -e ".[test]"`); `examples/minimal_gate.py` (plant simulator plus the gate in simulated time, no GPU); `tests/test_governor_package.py`.
- `LICENSE` (MIT).

Already in the repository at this version
- The frame hint library (`include/slackhint.h`, `python/slackhint`), the governed llama.cpp driver, the four controllers, the NVML admin helper, the plant simulator, the dashboard, the registered evaluation protocols and analysis, the audits (`docs/AUDIT_590W.md`) and the technical report (`docs/report/REPORT.pdf`, 6 pages).

Known limits of v1.0.0
- One laptop, one GPU, one driver (616.92), one synthetic foreground; Windows only.
- The learned governor did not meet its registered target (late frames above 1% in two of five scenes; non-inferiority against the primary reactive controller failed). Details in the report.
- The sampled NVML power reading glitches to about 588 W at idle on this driver. The registered power figures are energy-counter differences and are not affected; the guard that rejects such readings exists on the `v2-foreground` branch and is not part of v1.0.0.
- The energy-read sweep that would settle the worst-case counter overhead (`docs/W5B_ENERGY_READ_SWEEP_PROTOCOL.md`) was not run.
