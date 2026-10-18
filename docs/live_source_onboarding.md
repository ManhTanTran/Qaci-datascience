# Live source onboarding checklist

Reviewed on **2026-10-15**. This document records public information useful for
choosing a source; it is not a legal opinion or a grant of permission. No
website is enabled. A public page, robots allowance, API product page, trial or
third-party scraper does not by itself grant WardPriceDaily permission to
collect, retain, transform, display or pass listing content to an AI system.

## Source candidates

| Candidate | API/feed/file | Permission and non-commercial research | Price | Direct listing URL and publication date | Ward-level / Vietnam coverage | Current decision |
|---|---|---|---|---|---|---|
| **Partner CSV/JSON** from a brokerage, portal or research owner | CSV/JSON is straightforward; frequency and schema can be agreed directly. | Contract or written permission must cover collection/source, retention, transformations, attribution, research use, display, AI context and deletion. Non-commercial use must be stated. | Negotiated; request a small pilot/trial. | Require stable source listing ID, direct URL and authoritative `published_at` as feed fields. | Require ward/province values and a mapping sample for the Top 50. | **Preferred Pilot A** once written scope and storage permission are present. |
| **Housing Market Group Partner Property API** | Official product describes REST/JSON with listing IDs, sale/rent type, province/city, optional address, price, area, and publication date. Daily updates; IP allowlist and API key. | Paid product page does not publish data reuse terms. Ask whether the account supports non-commercial study and long-term storage, derived statistics and AI context. | Per-country pricing is quoted; trial details are provided by request. Not publicly free. | Public schema documents an ID and detail endpoint but no source-page URL field. Confirm canonical URL, linking/display rights and data retention in full docs/contract. | Vendor lists Vietnam, but public filters are province/city, not ward. Address-level ward coverage is not guaranteed. | **Promising only if** vendor confirms direct URL, ward match, exact Vietnam coverage, non-commercial storage/re-display and AI use in writing. |
| **Bộ Xây dựng housing and real estate information system** | Public portal has government statistics and reports. Current framework is in Decree 357/2025/NĐ-CP; exact API/export availability for this use was not confirmed. | Access and use are governed by the applicable framework and the data owner's grant. A visible report or portal account is not a bulk-use license. Public materials describe reporting/project-market data rather than public listing ads. | No fee or open-data license for this specific use was confirmed. Ask the data owner. | Listing-level ad URLs and publication timestamps are not shown in the reviewed public system pages. | Public pages include province/report/project views; public listing-level Top 50 ward coverage was not established. | **Use for official aggregate context** only after verifying fields and use conditions; not a demonstrated source for daily ads. |
| **Batdongsan.com.vn** | Public listing pages exist; no official public listing API/feed was identified in this review. | Its agreement covers website content and requires lawful access/use. No bulk storage or AI-reuse permission was confirmed. Request a written data/API agreement. | Pages can be browsed publicly; automated access and retained data are not thereby free. API pricing unknown. | Listing pages have URLs; reliable publication-date field and reuse/display rights need confirmation. | Listings may contain ward addresses, but coverage/structured ward field needs a sample and contract confirmation. | `REVIEW_REQUIRED`, disabled. |
| **Nhà Tốt / Chợ Tốt** | Official site links its terms/rules; no public listing API/feed was identified in this review. | Terms and data-owner permission must be reviewed for the proposed use. Non-commercial bulk collection/storage/AI use was not confirmed. | API pricing unknown. | Direct URLs exist for listings; authoritative publication date and linking rights need confirmation. | Ward coverage needs a source export/sample and permission. | `REVIEW_REQUIRED`, disabled. |
| **Alonhadat.com.vn** | Public listing pages exist; no official public API/feed was identified. | The site states copyright ownership and that copying without written consent is prohibited. Request written permission for a defined feed/API/export and retention. | API pricing unknown. | Category and listing URLs exist; published-date authority and permitted retention need confirmation. | Ward-level address may appear on individual ads; structured coverage must be verified. | `REVIEW_REQUIRED`, disabled. |
| **Homedy.com** | Public listing pages and platform rules exist; no public listing API/feed was identified. | The public materials reviewed do not establish a bulk data, non-commercial research, retention or AI-context license. Request written permission. | API pricing unknown. | Direct listing URLs may be available; publication date and derivative/link rights need confirmation. | Ward-level coverage must be tested using an authorized export. | `REVIEW_REQUIRED`, disabled. |
| **User-supplied Gemini/ChatGPT JSON** | Offline JSON/CSV/XLSX intake is implemented. | The person supplying the file must identify the underlying source and provide permission for storage and intended use. Model-generated claims are not proof. | No API cost for local import. Any upstream provider cost/terms are separate. | Keep exact supplied URL and classify `CATEGORY` vs `DIRECT_LISTING`; no URL is inferred. | Must match one of the 50 registry targets; otherwise quarantine. | Intake supported, but source must pass the registry gate; AI output remains unverified without independent evidence. |

The Housing Market API documentation currently describes Vietnam as one of its
market databases, sale/rent listings, API authentication, province/city filters
and `published_date`. Its published response schema does not show a canonical
listing URL or ward filter. The public plans page says pricing is quoted by
market and trial details are provided by request. Therefore this is **not yet
approved or proven fit for a 50-ward listing pipeline**.

The Ministry system is a plausible official source for reports and aggregate
market context, not a demonstrated source of individual sale advertisements.
The current government framework is Decree 357/2025/NĐ-CP, but the public pages
reviewed here do not establish that individual listing data, a public API, or
bulk retention rights are available for this project. Exact data grain,
request/access process, fees, allowed storage and endpoint/format need a written
answer from the data owner.

## Minimum permission record

Before changing a source to `AUTHORIZED` and `enabled=true`, save evidence in
`config/ingestion_sources.json` and confirm each item below:

- The rights holder, dataset/API and the individual or organization granting
  permission are identified.
- Allowed source, fields, locations, request rate, volume and refresh schedule
  are written down.
- Storage duration, cached/raw text retention, backups, deletion and termination
  behavior are defined.
- Display of listing excerpts, direct URL links, attribution and derived
  statistics are permitted.
- Non-commercial research/study use is explicitly allowed if that is the
  project's basis; any future commercial use needs a separate permission review.
- Sending fields/content to Gemini or another AI provider is explicitly allowed
  or explicitly excluded.
- Publication-date and expiry semantics, stable listing IDs and ward-level
  coverage are confirmed with examples.
- Request quotas, billing, trial end date, support contact and failure behavior
  are known; credentials are stored outside source control.

Do not enable a source based only on `robots.txt`, public browser access, a
vendor's claim that it collects from original sites, or an API key without the
data-use terms.

## Permission request template

```text
Subject: Request for a small, non-commercial research data pilot

We are building WardPriceDaily, a local research/learning project that computes
asking-price-per-square-metre summaries for a fixed list of 50 Vietnamese
wards/communes. We are requesting a pilot of up to 50 listing records first,
with a possible later ceiling of 500 newly published records per day if the
pilot and permission scope support it.

Please confirm:
1. Whether you can provide an official API, feed, partner CSV/JSON, or other
   permitted export, and a sample schema.
2. Whether Vietnam, the named target wards, sale/rent type, price, area,
   property type, address, stable listing ID, direct listing URL, published
   date and expiry date are available and authoritative.
3. Whether we may retain raw fields and source URLs locally, compute and retain
   derived price-per-square-metre statistics, and display summaries/citations
   to users in a private demo.
4. Whether non-commercial research/learning use is allowed, and whether any
   future integration with an AI system is allowed.
5. Attribution wording, retention/deletion rules, rate/volume limits, data
   update frequency, expiry/deletion signals and any redistribution restrictions.
6. Pilot fees, subscription/contract requirements, trial limits and the process
   for credentials or IP allowlisting.

We will not circumvent access controls, CAPTCHAs, robots restrictions or
technical limits. We will not use an unapproved third-party scraper in place of
permission from the relevant data owner.
```

## Public references reviewed

- [Housing Market Group Partner Property API — product and coverage](https://housingmarketapi.com/vi)
- [Housing Market Group — Vietnam coverage](https://housingmarketapi.com/vi/coverage)
- [Housing Market Group — API response and fields](https://housingmarketapi.com/vi/reference)
- [Housing Market Group — plans and quote-based pricing](https://housingmarketapi.com/plans)
- [Government of Viet Nam — Decree 357/2025/NĐ-CP](https://vanban.chinhphu.vn/?docid=216395&pageid=27160&typegroupid=4)
- [Bộ Xây dựng — national housing and real-estate database announcement](https://moc.gov.vn/vn/Pages/chitiettin.aspx?ChuyenmucID=1206&IDNews=96698)
- [Batdongsan.com.vn — agreement](https://wiki.batdongsan.com.vn/wiki/dieu-khoan-thoa-thuan-17568)
- [Nhà Tốt — official site/footer links to terms](https://www.nhatot.com/start.php)
- [Alonhadat — listing page and copyright notice](https://alonhadat.com.vn/nha-dat/can-ban/dat-tho-cu-dat-o/quang-nam/363/thi-xa-dien-ban.html)
- [Homedy — registration page references its terms and policies](https://homedy.com/account/register)
