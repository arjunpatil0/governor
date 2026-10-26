# STATUS (overwritten at every stop)
Updated 2026-10-26 - Phase: W4-5, evaluation. Session 1 (blocks 4 and 9, 85 cells) DONE: eval_trial2 TRIAL CHECK PASS (7 cells); session 1 INTEGRITY PASS (0 problems, 0 flags). No outcome analysis until all 10 blocks are done. Waiting for YOU: session 2 = blocks 5 and 10 (restart, helper, then the command in docs/W5B_EVALUATION.md, section 'Session 2'), then the integrity command with --blocks 5 10.

## Session 2 command (constants sha256 f7b99650efe7fea9d392a1aee2e49a18a84a00fe69d56fb4e41bf562cc6fb4a9)
python experiments/w5b/evaluate.py --blocks 5 10 --constants data/w5b/constants.json --constants-sha256 f7b99650efe7fea9d392a1aee2e49a18a84a00fe69d56fb4e41bf562cc6fb4a9 --out data/w5b/eval --armoury-mode Performance

## Remaining sessions: (6 11) (7 12) (8 13). Constants, runner code and exe hash identical across sessions (git head differs only by commits of data, docs and the integrity tool).

## Risks / not verified
- Helper log of session 1 not seen by me. Outcomes deliberately not looked at.
