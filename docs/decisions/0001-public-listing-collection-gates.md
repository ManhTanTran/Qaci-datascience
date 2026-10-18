# Decision 0001 — Public listing collection and promotion gates

- Status: Accepted for offline implementation; live source permission remains open.
- Date: 2026-10-14.

## Context

WardPriceDaily needs daily listing observations, while the public listing sites
reviewed so far do not provide clear permission for systematic extraction and
storage. The existing database separates unverified candidates from the
statistics warehouse.

## Decision

1. Keep every unapproved source disabled and the global live gate off. A readable
   `robots.txt` does not grant permission to reuse listing content.
2. Use a shared configured HTML/JSON-LD collector behind the `BaseCollector`
   interface. Source-specific URL templates and detail URL patterns remain
   disabled until reviewed and authorized.
3. Store discovered category URLs as audit records only. Candidate identity uses
   source listing ID or canonical direct-listing URL; exact cross-source content
   fingerprints create a review link instead of an automatic merge.
4. Mark source page evidence verified only when a directly retrieved detail page
   agrees on displayed and structured price/area and the requested ward context.
   A target without one reviewed current administrative mapping is not promoted.
5. Keep candidates and candidate observations separate from canonical listings.
   Promotion additionally requires both the global and source-specific
   `auto_ingest_verified` gates. Only promoted, validated records enter the
   existing Python statistics warehouse.
6. Cap collection at 10 candidates per target and 500 HTTP requests / candidate
   observations per run/day. These are ceilings, not fill targets. 403/429 stops
   a source; the collector does not retry or follow redirects.
7. Initialize collection tables only through `collection-init`, which snapshots
   and verifies the existing SQLite database first. Demo mode is never a
   production collection target.

## Consequences

The pipeline can be tested end-to-end with local fixtures but is not declared
production-ready until at least one source grants permission and passes a small
live pilot. With the current source registry, live collection exits before
network access. Scheduler registration remains an explicit, separate action.

## Evidence

- [Source permission audit](../collection_sources_audit.md)
- [Daily collection operations](../daily_collection.md)
