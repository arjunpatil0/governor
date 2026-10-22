"""analysis/smoke2_report.py: the join of ring timestamps with the driver CSV must not lose rows. The first version rounded both sides to 6 decimals; QPC ticks are 100 ns, so every
timestamp whose 7th decimal is 5 is a rounding tie and about 5% of the rows were lost, which looked like a 5% 'admission mismatch' of the driver (journal 0044, reviewer change 7).
Instruction (reviewer, 2026-10-23): "explain the ~5% admission mismatch offline from the smoke-3 CSV"."""
import numpy as np

from analysis.smoke2_report import match_logged


def test_match_is_exact_on_100ns_ticks_with_ties_at_the_seventh_decimal():
    ticks = np.arange(0, 2000) * 1e-7 + 492583.0                      # every 7th-decimal digit, including 5
    csv_t = np.array([float(f"{t:.9f}") for t in ticks])                # as the driver prints them (%.9f)
    vals = np.arange(len(ticks), dtype=float)
    got = match_logged(ticks, csv_t, vals)
    assert not np.isnan(got).any() and (got == vals).all()


def test_missing_rows_are_nan_not_wrong_rows():
    csv_t = np.array([1.0, 2.0, 3.0])
    got = match_logged([1.0, 2.5, 3.0], csv_t, [10.0, 20.0, 30.0])
    assert got[0] == 10.0 and np.isnan(got[1]) and got[2] == 30.0
