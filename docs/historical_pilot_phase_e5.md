# Phase E5 — human review preparation and historical quality audit

Date: 2026-10-15 (Asia/Saigon)  
Scope: offline preparation only. No new dataset was downloaded, no external API or
website was called, and no SQLite database was written.

## A. Review completed

0 of the 100 title rows have human labels. E4 selected 25 rows from each of its
four prediction groups: `SALE_CONFIRMED_BY_TEXT`, `RENT_CONFIRMED_BY_TEXT`,
`AMBIGUOUS`, and `CONFLICT`. This is a balanced review sample, not a random
population sample.

## B. Labels still missing

All 100 title rows remain `NOT_REVIEWED`. No precision, recall, F1, macro-F1,
confusion matrix, coverage, abstention, or error analysis is available yet.
Confidence intervals are not calculated. The sample design does not support
population weighting or a production accuracy claim.

## C–F. Human label distribution, metrics, and rule error analysis

Not available until the reviewer supplies independent labels. The evaluation
utility validates all five transaction labels, requires a reviewed status, checks
that the frozen E4 label still matches the original E4 prediction, and reports
mistakes and title/source context only for labeled rows. It does not treat E4 or
Gemini output as ground truth.

## G. Property mapping review

The property review packet has 222 rows: all 18 E4 `DAT_O` candidates, all 191
`UNKNOWN` candidates, and 13 `NHA_RIENG`/`CHUNG_CU` candidates where simple title
cues conflict with the mapped category. The 13 conflict flags are triage signals,
not property labels. All human property labels are blank. Every row remains
`HISTORICAL_DATASET_UNVERIFIED`; human review will not verify the original listing
or land legality.

## H. Sensitivity analysis of the 473 E4-eligible rows

| Scenario | Eligible | Lost vs E4 | Wards with n≥5 in any type | Wards with n≥10 in any type |
| --- | ---: | ---: | ---: | ---: |
| E4 baseline | 473 | 0 | 36 | 17 |
| Exclude 5 title-derived `DAT_O` mappings | 468 | 5 | 36 | 17 |
| Exclude 29 global Tukey flags (diagnostic only) | 444 | 29 | 36 | 14 |
| Require a per-listing URL | 0 | 473 | 0 | 0 |
| Require explicit area basis | 0 | 473 | 0 | 0 |
| Require both URL and area basis | 0 | 473 | 0 | 0 |

The 29 Tukey flags are diagnostic, not a deletion recommendation. No rows were
removed from the pilot database. E4 candidate coverage was 48/50 targets; the 473
eligible rows cover 46/50. Ranks 3, 5, 17, and 22 have no E4-eligible row. Among
the 46 covered wards, 36 have at least five eligible rows in one property type and
17 have at least ten. Removing title-derived `DAT_O` mappings does not change these
counts; removing Tukey-flagged rows reduces the `n≥10` count to 14.

All 473 rows have positive numeric price, area, and price/m² in the pilot. Their
median asking price is 6.99 billion VND, median area is 65 m², and median price/m²
is about 96.36 million VND. These are descriptive historical sample values, not
current market estimates. Tukey flags 29 price/m² values for review.

E4 classifies all 473 as explicit-sale by title rules. The set has 312 `NHA_RIENG`,
156 `CHUNG_CU`, and 5 `DAT_O` mapped from title text. All remain
`HISTORICAL_DATASET_UNVERIFIED`; transaction intent has not been human-confirmed.

The sample has no per-listing URL and no `area_basis` field. It therefore cannot
show whether area means land, floor, or usable area, and the dataset page cannot
substitute for a listing citation. The current dedupe audit found zero stored
duplicate pairs, zero records flagged as duplicate/review, and zero exact
target/type/title/price/area duplicate groups among the 473. Cross-source duplicate
identity cannot be ruled out without listing IDs or direct listing URLs.

## I. Missing source verification

All 473 eligible rows lack a listing detail URL. The pilot stores the dataset
provenance page, not a URL for each listing. No row is `SOURCE_VERIFIED`, and no
historical row was promoted to `CURRENT_VERIFIED`, `DAILY_NEW`, or production AI
context.

## J. Recommendation on expansion to 25,000 rows

Do not scale to 25,000 yet. First complete the human transaction and property
reviews, then decide whether the dataset's missing listing URL and area-basis
fields are acceptable for the intended historical analysis. If it is expanded
later, retain its research-only status and run a separate quality audit before
changing eligibility rules.

## Prepared artifacts

- Title labels: `outputs/historical_quality/tinix-e5-title-review.csv`
- Property labels: `outputs/historical_quality/tinix-e5-property-review.csv`
- Machine-readable sensitivity audit: `outputs/historical_quality/tinix-e5-historical-sensitivity.json`
- Label definitions and CSV instructions: `docs/historical_review_guide.md`
- Evaluation decision: `docs/decisions/0002-e5-human-review-evaluation-protocol.md`

E5 evaluation remains pending the human reviewer. See the README for validation
commands; packet preparation fails rather than overwriting an existing review.
