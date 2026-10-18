# Gemini Web pilot integration

## Source and compatibility decisions

The supplied package and its README, `docs/CODEX_INTEGRATION.md`, source,
tests, and 50-record example were reviewed. The package's independent CSV
registry was not integrated. The adapter reads target ranks 1–50 and only the
legacy ward/district/province labels from `ward_target_legacy` in read-only
mode. The canonical schema and the 50 target/mapping rows remain unchanged.

Audit data is stored in sidecar tables `webpilot_runs` and
`webpilot_candidates` in `state\wardprice_webpilot.sqlite3`. The adapter does
not replace canonical tables. It stores prompts, raw response text, request
metadata, wrapper citations, citation URL matches, and each parsed listing.
Exact duplicate fingerprints are idempotent; duplicates are recorded in each
run. Live-response rows with location issues or a model duplicate flag are
quarantined by that processor. Saved-batch imports preserve potential source
conflicts as reviewable candidate statuses instead of discarding the rows.

## Importing a saved Gemini JSON batch

Use `import-batch` for an operator-saved JSON batch. The command is offline and
previews by default. It validates the batch rank against `ward_target_legacy`,
keeps raw batch JSON and per-row decisions, and writes only to the Web pilot
sidecar. Its tables are `webpilot_candidate_batches`,
`webpilot_batch_candidates`, `webpilot_candidate_batch_rows`, and
`webpilot_batch_observations`. It never calls Gemini or a source website.

Preview a batch before applying it:

```powershell
& .\.venv\Scripts\python.exe -m wardprice_webpilot `
  --targets-db .\state\ward_prices.sqlite3 `
  --db .\state\wardprice_webpilot.sqlite3 `
  import-batch --rank 2 --file .\inbox\gemini_rank02_20261014.json
```

After reviewing the accepted, quarantined, duplicate, and rejected counts, add
`--apply` to write the batch. Before creating the candidate schema, the command
creates a SQLite-consistent backup under `state\backups`. It refuses to write
into the production target database or a database marked `DEMO_MODE`.

`SEARCH_SNIPPET_ONLY` stays at that evidence level and is shown in the UI as
“Chưa xác minh nguồn”; it does not become a verified listing or a price
statistic. `DEMO_SYNTHETIC` rows are rejected. Explicit category/search URLs
are stored with `source_url_type=CATEGORY`; individual listing URLs are stored
as `DIRECT_LISTING` when the URL shape or source annotation supports that
classification. Missing or ambiguous URLs remain `UNKNOWN`. URL alone,
especially a category URL, is never the identity key: a supplied listing ID
or the composite rank/type/title/address/price/area fingerprint is used.
Possible duplicates remain visible with `NEEDS_REVIEW` or `SOURCE_CONFLICT`
and keep their warning text. Wrong-whitelist-ward rows are quarantined.

The same command supports later rank 3–50 batches. Use a new file path for each
saved batch; reimporting identical bytes is idempotent, and same-day duplicate
candidate observations are protected by a unique candidate/date constraint.

## Evidence limits and canonical handoff

A candidate remains `UNVERIFIED` unless its listing URL exactly matches an
actual URL returned in the wrapper citations and the response contains both
price and area evidence excerpts. Such a candidate can be labeled
`SEARCH_SNIPPET_ONLY` only when Gemini requested that label (or claimed a page
read). The wrapper currently returns citation title/URL, not source page text,
so those excerpts remain Gemini-provided claims and are not independent source
verification. A self-reported `web_search_used` value never changes evidence.
A self-reported `source_page_read=true` is retained in raw response, but the
stored read-confirmation flag stays false and the candidate is downgraded to
`SEARCH_SNIPPET_ONLY`; this adapter cannot create `SOURCE_PAGE_CONFIRMED`.

The `for_wardprice_import.json` export contains only non-quarantined,
geo-matched candidates with a citation URL match and price/area excerpts. The
`wardprice import-gemini-web` command previews by default. `--apply` is required
to write eligible rows through WardPriceDaily's canonical validator and
history writer. Wrapper citations are preserved in raw payload and are not
marked as Google Search API grounding (`grounding_used=0`). The bridge requires
a unique active whitelist match and exact legacy target labels; it does not
edit mapping review fields.

No listing aggregate is computed from unverified candidates. Canonical
statistics continue to be computed by the existing Python pipeline from rows
that pass its canonical validation.

## Audit schema

- `webpilot_runs`: target rank, prompt, raw response, request metadata, parsed
  result, wrapper citations, citation URL match counts, and run counts/status.
- `webpilot_candidates`: normalized fingerprint, legacy target, address,
  property type, price, area, locally computed price/m², URL, evidence status,
  geographic status, quarantine reason, raw item, and first audit run.

## Offline verification

Run the project tests and lint from PowerShell:

```powershell
& .\.venv\Scripts\python.exe -m pytest
& .\.venv\Scripts\ruff.exe check .
```

The supplied `examples/gemini_batch50_as_received.txt` is copied to
`tests/fixtures/gemini_batch50_as_received.txt`. The offline test uses a
separate temporary SQLite database for audit data and reads the production
legacy target registry only in read-only mode. It checks 50 records, ward
mismatch/quarantine, duplicates on re-import, CSV/JSON export, and canonical
bridge behavior against a separate temporary canonical database. It does not
write to `state/ward_prices.sqlite3`, call Gemini, send Gmail, or register a
task.

## Live boundary

The client is optional and unofficial; it does not use `GEMINI_API_KEY`. It
requires the user to install `gemini_webapi` and configure a permitted local
Gemini Web session in the current process environment using
`GEMINI_SECURE_1PSID` and optionally `GEMINI_SECURE_1PSIDTS`. It does not read
`.env`, extract cookies, print credentials, or perform login. Each CLI
invocation requires both `--live` and `--confirm-single-live-call`, reserves
one attempt, and does not retry at the application layer. The generation
method receives `current_retry=0`. A local guard permits at most three
attempts per Vietnam calendar day by default; `--max-daily-calls 1` or `2` can
lower it. Failed attempts consume a slot. The cap is stored in the selected
audit sidecar database, so live invocations must reuse the same `--db` path.
The guard serializes the daily check and reservation to prevent concurrent
invocations from exceeding the local cap. The wrapper cache is redirected to
a temporary directory and removed after close.

This local cap does not change Google/Gemini account quotas, establish that an
account permits automated access, or guarantee any number of successful
responses. Stop if Google denies access, reports quota exhaustion, or asks for
verification; do not change accounts, proxies, or access methods to bypass
those controls. The wrapper can change independently. Every live invocation
still requires explicit user approval. No additional live request, Gmail send,
or scheduled task was performed for the cap change.

## Phase E1: Gemini Web Deep Research source audit

The installed `gemini_webapi` package is an unofficial reverse-engineered
wrapper. Its Deep Research API is separate from the ordinary
`generate_content()` call used by `collect`: the high-level method performs
`create_deep_research_plan()` → `start_deep_research()` →
`wait_for_deep_research()`. The inline `result.document` carries Markdown and
`result.document.sources` carries citation IDs, titles, URLs, and favicons.
The workflow polls for a report and can take several minutes; the package also
performs internal recovery/retries. The local CLI limits this pilot to one
Deep Research workflow per Vietnam calendar day, but that is not a guarantee
of one underlying HTTP operation or a provider quota. The package README says
Deep Research may require an eligible account/subscription. These facts do not
prove that the signed-in account can use it.

The new command previews a prompt without network or database writes by
default:

```powershell
& .\.venv\Scripts\python.exe -m wardprice_webpilot --targets-db .\state\ward_prices.sqlite3 --db .\state\wardprice_webpilot.sqlite3 doctor
& .\.venv\Scripts\python.exe -m wardprice_webpilot --targets-db .\state\ward_prices.sqlite3 --db .\state\wardprice_webpilot.sqlite3 research --rank 11 --count 5
```

It uses the rank 11 target from `ward_target_legacy`, not a second target
registry. Live execution requires a configured local Gemini Web session,
working Deep Research methods, and an explicit confirmation flag. It is a
single bounded workflow and is capped at one live workflow/day in the adapter
sidecar. This command was not run live for Phase E1; the user must explicitly
approve the call after checking account eligibility and use permission:

```powershell
& .\.venv\Scripts\python.exe -m wardprice_webpilot --targets-db .\state\ward_prices.sqlite3 --db .\state\wardprice_webpilot.sqlite3 research --rank 11 --count 5 --live --confirm-single-live-deep-research
```

The live run writes its prompt, full report Markdown, source list, plan fields,
and parsed candidates to `inbox\webpilot\deep_research` and namespaced
`webpilot_research_*` tables in the sidecar database only. It never writes the
canonical target/listing database. `research-status` displays those audits.
To reprocess an already saved report without any network, use
`research-import --rank 11 --count 5 --file report.md --sources-file
sources.json`. An optional `--source-text-json` is a citation-ID-to-text map
from a permitted source retrieval. The parser itself never fetches URLs.

Candidate URL values are taken only from actual objects in
`document.sources`; a URL in the model's JSON is ignored. Evidence labels are
conservative:

- `SOURCE_VERIFIED`: the cited URL looks like a listing-detail URL and
  independently supplied page text matches the candidate price, area, and
  target ward plus district/province.
- `SOURCE_PARTIAL`: a non-category citation exists but the page text is absent
  or does not confirm every required field.
- `CATEGORY_ONLY`: all linked URLs are category/search pages.
- `UNVERIFIED`: no usable citation URL, ambiguous location, or no candidate
  source link.
- `WEB_SEARCH_UNAVAILABLE`: run-level state used when no report document was
  produced. A report with zero listings is kept distinct from this state; a
  report with no citation objects is `NO_SOURCES_RETURNED`.

Only `SOURCE_VERIFIED` can satisfy the Phase E1 source test. Even this label
does not prove an ad is current, authentic, or legally licensed for reuse; a
human should inspect the actual page. The offline test fixture demonstrates
classification with mock data only and is not evidence that Gemini Web can
retrieve a real listing.

### Search-first fallback design

If one approved Deep Research run produces no independently verifiable listing
sources, keep Gemini Web as an optional research assistant and move retrieval
to this staged design instead of scaling prompts:

```text
Independent permitted search provider
    → candidate listing URLs
    → permitted page retrieval (normal access, service terms and robots rules)
    → Gemini structured extraction from retrieved page text
    → Python ward, price, area, type and URL validation + deduplication
    → SQLite source snapshot and audit
```

Provider selection is deferred until its access terms, quota, price, and
Vietnam coverage are checked. Use only public/authorized access, obey rate
limits and robots/service restrictions, and stop at CAPTCHA or access denial.
No provider was purchased or queried, and no crawler was built in this phase.
An operator can also provide a small set of permitted URLs and saved page text
to `research-import` for deterministic offline validation.
