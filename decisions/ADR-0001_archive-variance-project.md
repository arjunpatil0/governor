# ADR-0001 — Archive the variance chunking project instead of extending it
Status: accepted · Date: 2026-10-19
## Context
Re-analysis (journal 0003) showed the premise inverts under the implemented execution model.
## Options considered
(a) fix and extend v2; (b) scrap; (c) archive as a corrected negative result and reuse method + CudaExecutor in a new repo
## Decision
(c)
## Rationale
Keeps the honest finding and the transferable assets without inheriting a broken premise.
## Evidence
ARCHIVE_NOTE.md in variance_gpu_project (a9239b8); new repo governor/.
