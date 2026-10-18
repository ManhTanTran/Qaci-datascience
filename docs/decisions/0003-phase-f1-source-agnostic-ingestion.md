# Decision 0003 — Isolate Phase F1 listing ingestion in a pilot warehouse

- **Status:** accepted for Phase F1 pilot
- **Date:** 2026-10-15
- **Scope:** current listing intake for the Top 50 research targets

## Context

The existing database already contains the national registry, legacy valuation
records, demo fixtures, a historical TiniX pilot, and a separate Gemini Web
audit database. New live listing evidence has not been authorized for any
website. Reusing canonical production tables now would mix distinct evidence
classes and make a later migration difficult to audit.

## Decision

1. Write Phase F1 records only to
   `state/ward_prices.ingestion_pilot.sqlite3`; keep production, demo, historical
   and Gemini Web databases separate.
2. Copy only the approved Top 50 target identities from the production registry
   in read-only mode.
3. Use one source-agnostic JSON/CSV/XLSX schema and permission gate for files and
   future authorized API/feed/collector adapters.
4. Keep every current source disabled until written permission covers the
   proposed scope, request frequency, storage, attribution and intended AI or
   display use.
5. Do not trust `evidence_status` or collector-proof fields inside imported
   JSON. Confirmed source evidence is provided out-of-band by the existing
   collector adapter or by explicit operator review with an audit reference.
6. Admit a record to current verified statistics only when the direct source
   page, target address, property type, explicit sale transaction, price and
   area are supported; compute price/m², mean, median, min and max in Python.
7. Keep `NEWLY_POSTED_LAST_24H` distinct from first-seen `NEWLY_DISCOVERED` and
   maintain source/day observations and daily price changes idempotently.
8. Treat 500 new listings/day (10 per target) as a goal, not a requirement or a
   hard row-processing ceiling. Never fill gaps with repeated or synthetic
   records.

## Consequences

- The pilot can accept a permitted file feed without changing canonical listing
  tables or historical observations.
- The management UI can report candidate and verified coverage separately.
- No real-source record is currently eligible until a source is authorized
  and an operator performs a permitted import.
- Promotion to production requires a separate review, migration plan and user
  confirmation after end-to-end source permission and evidence tests.

## Revisit when

A data owner supplies written scope/retention rights, a pilot feed is available,
or the product changes from private research to another use. Review source
terms, sensitive fields, API cost and exact ward/URL coverage before enabling a
connector.
