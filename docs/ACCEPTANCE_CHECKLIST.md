# Listing pipeline acceptance checklist

- [x] Whitelist imported from an operator-provided CSV, maximum 100 wards.
- [x] Legacy Top 50 target/mapping registry imports additively from CSV or ZIP into its own SQLite table.
- [x] Blank current administrative codes remain NULL; customer metrics are excluded from prompt and target-list output.
- [x] Live collection only accepts whitelisted ward codes.
- [x] Global tracked-listing ceiling is configurable up to 500; at capacity, existing records can still be refreshed.
- [x] Legacy ward-level valuation and `AI_ESTIMATE` records are kept separately and excluded from listing statistics.
- [x] Listing prices are total VND asking prices; Python calculates price/m² and ward/type statistics.
- [x] Grounding URL, evidence, address, property type, price and area are validated before statistics.
- [x] Current listing rows and append-only listing history are stored in SQLite.
- [x] CSV/XLSX/daily report export and Gmail dry-run are available.
- [x] Gemini HTTP 429 stops remaining ward requests and records how many wards were not attempted.
- [x] Task Scheduler scripts point to the listing-based CLI; registration is an explicit operator action.
- [x] Unit tests use fake data and do not call Gemini, Gmail or Task Scheduler.

## Operator checks before pilot

- [ ] Import the final 50–100 ward CSV and review the active whitelist.
- [ ] Configure a Gemini API key only after checking model access, quota and current Search grounding pricing in Google AI Studio.
- [ ] Approve a live 2-ward pilot before adding `--live`.
- [ ] Review listing evidence and duplicate behavior after the pilot.
- [ ] Configure Gmail and approve a real message before using `--send-email`.
- [ ] Approve Task Scheduler registration after the pilot.

See [README](../README.md) for Windows commands and operating instructions.
