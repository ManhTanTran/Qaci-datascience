# WardPriceDaily — 500 synthetic listing fixtures

**WARNING: ALL 500 RECORDS ARE FAKE, SYNTHETIC TEST FIXTURES, NOT LIVE WEB SEARCH RESULTS.**
**DO NOT import into production SQLite or report these as market data.**

## Source of geographic targets

Names, old districts and provinces copied verbatim from the user-provided `WardPriceDaily_Top50/top50_original.csv`.
No new mappings or codes are inferred. This package excludes `n_customers` and `pct`.

## Dataset

- 50 ranked wards/communes; 10 fictional records each; 500 total.
- 200 DAT_O, 200 NHA_RIENG, 100 CHUNG_CU.
- Deterministic fake prices/areas solely for testing calculations; **not estimates of real property prices**.
- 10 daily-batch simulation JSONs of 50 records each in `batches/` and one aggregate of 500.
- Schema matches previously supplied Gemini batch shape, but codebase importer compatibility is NOT tested.
- Every title/address visibly says DEMO / GIẢ LẬP; `source_website=DEMO_SYNTHETIC`; `source_url=null`; `evidence_status=UNVERIFIED`; `web_search_used=false`.
- `expected_statistics_DEMO_ONLY.json`: expected mean and median per group for dedicated demo dashboards only.
- `replay_rank01_duplicate_test.json`: import after the first group; a well-designed importer should count repeated rows as duplicates, not new listings.

## How to use safely on your local WardPriceDaily project

1. Copy / extract this package locally.
2. Ask Codex to inspect the project's actual importer and DB connection settings. Do not assume its CLI consumes these files unmodified.
3. Create isolated database `state/ward_prices.demo.sqlite3` by SQLite backup or fresh migrations/seed. Never replace the production DB.
4. Add a dedicated `WARDPRICE_DEMO_MODE=1` setting with a visible DEMO watermark, and make import of any `DEMO_SYNTHETIC` record fail when demo mode is off.
5. Try `batches/demo_group_01_50.json` first, check 50 records over five target ranks, then all ten batches, checking 500 total and 10 per target rank.
6. Repeat the first batch with `replay_rank01_duplicate_test.json`; count of unique rows must not increase.
7. In demo mode only, calculate summary mean/median and compare to `expected_statistics_DEMO_ONLY.json` (allow small rounding tolerance). In production, synthetic rows must never affect verified metrics.
8. Confirm CLI lookup, local-first API, UI filters, coverage, charts and empty-data behavior. For external fallback, use mocks; do not make live API calls.
9. Once finished, delete the isolated demo DB if no longer needed.

## Sanity check

Run `python verify_demo_fixture.py` in this package folder. No third-party packages needed.

## Key caveat

This tests *storage, lookups, schema handling, deduplication, UI, statistics and scheduling with mocks*.
It does **not** demonstrate Gemini Web search, live crawling, source verification, or ability to obtain 500 real listings per day.
