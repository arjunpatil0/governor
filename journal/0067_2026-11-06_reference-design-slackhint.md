# 0067 - 2026-11-06 - package the project as a reusable reference design (frame-slack hints)

Instruction (Arjun): "Package the project as a reusable reference design (no new experiments, no changes to registered results). Create docs/SPEC_FRAME_SLACK_HINTS.md ... Extract a small library: include/slackhint.h ... and a Python binding, with tests. Write a top-level README ... List prior-art search terms as an open TODO; do not claim novelty."

Done (nothing registered was touched; no hardware, no new measurement):
- include/slackhint.h: single-header C99/C++ (Windows), producer (create, publish, frame_started/frame_done/idle), consumer (open with geometry check, seqlock read, last-good-value view = port of shm::PaceView), fit rule (pacing::aligned_may_start), duty wake (pacing::unaligned_wake), clean-unit estimator and overlap rule (tokest::). Seconds API; wire format identical to telemetry/ring.py SeqBlock with nfields 3.
- python/slackhint/: byte-compatible Python binding (Producer, Consumer, may_start, duty_wake, unit_overlapped, Estimator).
- Tests, all passing (22): tests/test_slackhint_py.py (13) and tests/test_slackhint_c.py (9; the C header compiled with MSVC as C against the Python binding and SeqBlock both directions, rules and estimator equal to Python, torn-read stress both ways with a writer publishing as fast as it can, missing/mismatched block refused, header compiles as C++). Two test bugs found and fixed on the way (a named mapping dies with its last handle: the tests dropped their only reference).
- docs/SPEC_FRAME_SLACK_HINTS.md: layout, producer and consumer rules, failure modes (torn reads, stale estimates, units larger than slack), each with evidence from our files and its limits. README.md: what it is, diagram, components, measured results with limits, how to run, prior-art search terms as an open TODO (nothing searched). examples/demo_slack_hint.py: no-GPU spin-loop demo, an illustration (its numbers are not results; ran it twice to check it works).
Deviations and honest gaps:
- The record has NO period field: the experiments' pace block is [busy, next_arrival_s, updated_s] (3 doubles); the spec lists a period field as a v2 item (it would change nfields). Arjun's list named "period"; I documented the as-built record rather than invent a field the evidence does not cover.
- "Seqlock version" is the `seq` word (odd = write in progress).
- Estimate staleness after clock changes (HW7): no analysis exists in the repository; the spec says untested.
- No controlled ablation of the hints against a no-hint baseline exists; the spec says so. No LICENSE file exists. The prior-art TODO is unsearched; no novelty is claimed.
- The library is validated on x86-64 Windows only; no POSIX path.
