# Response to reviews/2026-10-21_w2_B_review.md (Claude Code, 2026-10-21; review file untouched)
1. HB2 membg ceiling: ACCEPTED. Registered verdict kept, label "UNINFORMATIVE: ceiling" added to the report (analysis/w2_analysis.py, test_hb2_flags_reference_at_ceiling); design lesson in journal 0017.
2. Mem-frame HB1 miss: ACCEPTED as kernel-specific knees (not a memory-clock effect; W1 logged 8001 MHz); stated in journal 0017 as an interpretation, not isolated by a further experiment. The B report text is unchanged beyond the miss row; the statement lives in the journal.
3. fg_gpu under co-run: PARTLY DONE. Label "interval incl. possible switched-out time" added to the report; the Nsight Systems trace (trace_cell.py, needs admin) is NOT yet run, so the 12.1 vs 22.2 ms pattern is unexplained and no co-run service time is interpreted. Pending the trace.
4. Completed fraction: DONE (frac_completed beside every latency percentile; test_b_per_cell_...).
5. Provenance of 20261021T104818Z: DONE (interrupted by accident, journals 0016/0017); 20261021T105205Z is the analysed run.
6. Deadline-aware downclocking: DONE as a descriptive table in the B report and in journal 0017; Pillai and Shin not cited (unverified).
