# 0065 - 2026-10-28 - session 4 stopped by Arjun (Ctrl+C), block 7 discarded, rerun as block 15

Facts (files only; no outcome was looked at):
- Session 20261027T113024Z (blocks 7 and 12, estimate 2.36 h, constants hash f7b99650..., git head 291c0aa, exe bb875fbcaa2cf792): Arjun stopped it with Ctrl+C at 2026-10-27 12:23:12 UTC (urgent work). Block 7 had 32 cell folders, 31 with cell.json; the 32nd (ev07_S1d_cBb_35) holds only incident.json (KeyboardInterrupt, aborted: true). No block.json. Block 12 never started.
- This is the first time the BaseException handler written after the session 3 attempt-2 mystery fired on hardware: the interrupt left a record (cell, error type, UTC).
- Rule (addendum O-5/O-6): an incomplete block is discarded whole, rerun under the next free number with the same seed list. Discarded with the runner's own `prepare_block` (same code path as block 6): data/w5b/eval/discarded/block07_20261027T195815Z (31 measured cells + the aborted one, kept, not counted; the folder name's timestamp is the time of the move, not of the interruption).
- Next free rerun number: 15 (14 = block 6's rerun). Command: `--blocks 7 12 --as-block 15 12`. check_session([15, 12], seed_blocks=[7, 12]) = None; estimate 2.36 h (55 + 30 cells at 100 s) < 3 h limit. Block 15 composes the 55 cells of block 7's seed list (ids ev15_...).
- After session 4 the complete blocks will be 4 5 9 10 11 14 15 12, then session 5 = 8 13: 10 blocks.
- Nothing about the 31 partial cells is used: the block is rerun in full under the same seed list. Whether a Ctrl+C-ed block's cells could be kept is not what the registered rule says; not changed.
