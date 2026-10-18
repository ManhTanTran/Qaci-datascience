# Experiment log

## 2026-10-15 — Phase F1 synthetic ingestion performance

- **Purpose:** measure normalization, validation, deduplication and SQLite
  insert/replay behavior at the 500-record daily planning goal.
- **Fixture:** 500 generated synthetic listing rows over the read-only Top 50
  target identities. The source and database were temporary and disposed after
  the run.
- **Database:** temporary SQLite under the system temp directory; no production,
  demo, historical or ingestion pilot database was written.
- **Network:** not attempted.
- **Result:** PASS; 500 inserted on the first pass, 500 unique listings,
  500 unique observations, 0 replay insertions and 500 replayed existing
  candidates. End-to-end elapsed time was 0.8366 seconds. `tracemalloc` measured
  a 2,061,137-byte peak of traced Python allocations; this is not total process
  RSS and excludes SQLite/native-library allocations.
- **Interpretation:** the normalized local path handled the 500-row synthetic
  fixture and was idempotent on replay. This does not establish live source
  access, listing quality, 500 real listings/day, or production throughput under
  concurrent jobs.
- **Reproduction:** `python -m wardprice.ingestion_pilot benchmark --count 500`.
