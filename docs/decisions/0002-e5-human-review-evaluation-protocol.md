# Decision 0002 — Phase E5 human review and evaluation

- Status: Accepted for the isolated historical pilot.
- Date: 2026-10-15.

## Context

The E4 rule classifier produced a 100-title review sample balanced across four
prediction strata. It is not a probability sample of the 1,190 historical
candidates. The TiniX source sample also has no per-listing URL or explicit area
basis. Labels must come from a human reviewer and cannot be inferred from Gemini,
E4 predictions, or this dataset's license/provenance.

## Decision

1. Preserve E4 predictions as the frozen baseline. Human labels are stored only in
   separate review CSVs until reviewed and accepted; the production, demo, and
   historical pilot databases are not modified by packet preparation.
2. Use `SALE`, `RENT`, `AMBIGUOUS`, `CONFLICT`, and
   `INSUFFICIENT_INFORMATION` for transaction review, and
   `DAT_O`, `NHA_RIENG`, `CHUNG_CU`, `OTHER`, and `UNKNOWN` for property review.
3. A reviewed row must have a valid human label and `review_status=REVIEWED`.
   Blank labels remain `NOT_REVIEWED`; no model may fill them.
4. Metrics, confusion matrices, and error analysis are unavailable until human
   labels are supplied. Any later metric is scoped to the review sample; no
   population weighting or production accuracy claim is allowed without an
   appropriate sampling design.
5. Human title review does not set source evidence to verified. A listing URL and
   source-level evidence remain separate requirements.
6. Historical sensitivity scenarios are read-only diagnostics. They report the
   effect of stricter filters but do not delete or mutate candidate records.

## Consequences

The E5 review packet contains stable row identifiers and blank label fields. The
E4 rule confidence field remains blank because no calibrated probability was
produced. E4 remains available for comparison and future rule changes require a
separate version; the 100-title review set must not be reused as an unqualified
holdout after rule tuning.
