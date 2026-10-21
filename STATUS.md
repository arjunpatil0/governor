# STATUS (overwritten at every stop)
Updated 2026-10-21 · Phase: W2 (A done; A2 false start fixed, A2 awaiting rerun; part L code not written)

## Just did (commits)
- A2 crash fixed test-first (frame units now loaded for any part with a frame cell; smoke covers every fg stream) and logged (journal 0021). Armoury Crate mode now required via --armoury-mode and stored in meta.json; CLAUDE.md protocol updated. Memory-clock 8101 incident logged.
- Earlier: ea8546a/081f148 (Experiment A results, journal 0020).

## Waiting for
- Arjun: the Armoury Crate mode name used for A/B/C (to put in the A2 command), then Arjun reruns A2 from scratch. I execute nothing while it runs.

## Decisions needed
1. Armoury Crate mode name that A/B/C used (one word, e.g. what the app shows). Recommendation: state it exactly as shown.
2. Reviewer checkpoint on A's results (journal 0020) is still due. Recommendation: send before interpreting A2.

## Reviewer checkpoint due?
- Results before interpretation: A (yes). Surprise: yes (A2 harness bug + clock mismatch are process, not science). No design change.
