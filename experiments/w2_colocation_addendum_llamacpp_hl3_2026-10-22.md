# Addendum to the llama.cpp validation addendum (experiments/w2_colocation_addendum_llamacpp_2026-10-21.md): HL3 reading
Date: 2026-10-22 · Written BEFORE any llama.cpp validation data exists (only the +/-5% driver sanity check and a non-admin smoke run exist, journal 0025) · Reviewer item 5 of reviews/2026-10-22_globaltimer_draft_review.md

HL3 as registered: "the greedy token sequence must be identical in every cell of the same block". Cells run for a fixed time window, so faster clocks decode more tokens and the sequences have different lengths. Reading fixed now:
- Within a block, each cell's sequence is compared with the block's longest sequence over the cell's own length; the cell agrees iff all of its tokens match. The shared-prefix length (tokens matching before the first mismatch, or the full length) is reported per cell.
- A block with any disagreeing cell is flagged (not dropped), as registered.
- The check COUNTS for a block only if every cell has at least 64 tokens; a block where a cell has fewer than 64 is reported as inconclusive, not as passed.
No other part of the llama.cpp addendum changes.
