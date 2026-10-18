# National administrative source data

## Current registry

- Source: NSO `DanhMucPhuongXa` Web Service, operation documented at <https://danhmuchanhchinh.nso.gov.vn/WebService.aspx>.
- Requested as-of date: `13/10/2026`.
- Raw response: `sources/nso_communes_as_of_2026-10-13.xml`.
- Normalized import/export: `processed/nso_communes_as_of_2026-10-13.csv`.
- Imported registry: 3,321 commune-level units under 34 provinces/cities; source types count 709 phường, 2,599 xã, 13 đặc khu.
- The current import contains 34 province records, 3 source district-label records, and 3,321 commune-level records. The three district-level rows are retained as source labels; they are not counted as current commune units.
- Official codes are stored as text. The import preserves the official values and does not synthesize missing codes.

## Historical data and crosswalks

`sources/nso_communes_as_of_2024-12-31.xml` is retained as a raw NSO service response for review only. It is **not** imported into the registry: it contains 10,134 commune rows and 62 distinct province labels, so this response was not accepted as a validated full pre-reform snapshot. The importer can load an approved historical XML/CSV snapshot without making it current, but this particular file needs source/date semantics reviewed first.

`sources/nso_crosswalk_page_1_of_5_as_of_2026-10-13.html` is the first page of the official NSO crosswalk display (<https://danhmuchanhchinh.nso.gov.vn/Doi_Chieu_Moi.aspx>); the page reports 3,321 items across five pages. It is retained as a source sample and is **not** used to claim a complete historical crosswalk. Top 50 legacy aliases remain in SQLite with their prior review status. Partial transfers, splits and unresolved names must not be linked to a single current ward automatically.

For a source-backed crosswalk, prepare a CSV with columns:

```text
alias_name,province_name,district_name_legacy,source_code,source_version,target_code,relationship_type,mapping_status,effective_date,source_reference
```

Only `OFFICIAL_CROSSWALK_VERIFIED` rows with relationship type `MERGED` or `RENAMED` and one existing current `target_code` become resolvable aliases. `SPLIT`, `PARTIAL_TRANSFER`, and review/pending rows are retained without automatic unit resolution. Import is idempotent by source reference and relation fields:

```powershell
& .\.venv\Scripts\python.exe -m wardprice import-crosswalk --file .\data\administrative\crosswalk_reviewed.csv --source-reference "https://official.example/crosswalk"
```

The snapshots are retained local source/reference data for this project. No property listing, asking price, or nationwide price coverage is implied by the administrative registry. The crosswalk HTML is only page 1 of 5; it is not imported as a complete mapping dataset.
