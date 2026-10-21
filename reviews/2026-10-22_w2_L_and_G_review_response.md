# Response to reviews/2026-10-22_w2_L_and_G_review.md (journal 0028)
1. [NOTE] Noted.
2. [ADD] DONE: data/w2_L_results.md now has tok/s, board power, relative throughput and J/token side by side (regenerated from the raw data; 1500 MHz 97.25 tok/s at 56.3 W, 1050 MHz 89.4 tok/s at 47.1 W, unlocked 101.1 tok/s at 92.0 W). The "~36 W less" is 92.0 - 56.3 = 35.7 W, arithmetic on the medians; it is the board counter, one GPU. Journal 0028.
3. [ADD] DONE as an interpretation section in the L report, labelled as such. The Q4_K_M dequantisation explanation is the reviewer's and was not tested here; the report says so.
4. [NOTE] VERIFIED and recorded as resolved: Reliability appears in exactly the 10 llama_unlocked cells (checked from results.csv by cell_id), in no locked cell.
5. [NOTE] Noted; policy for W4-5, not a W2 result.
6. [APPROVE] Registered: renamed without _DRAFT, header changed, committed before any G data or G code (journal 0028).
