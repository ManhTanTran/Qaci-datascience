# WardPriceDaily UI design

The product has two audiences: residents looking up local asking prices and an
operator reviewing data coverage and collection activity. Lookup is the default
view; management information stays behind the local operator view.

## Visual tokens

| Role | Value | Use |
|---|---|---|
| Canvas | `#F2F4EF` | Main page background |
| Paper | `#FFFEFA` | Search surface, result surfaces, metric panels |
| Ink | `#203431` | Main text |
| Muted | `#63736E` | Explanatory copy and metadata |
| Pine | `#123D35` | Primary actions and the wordmark mark |
| Teal | `#17665B` | Active state and verified-data accents |
| Amber | `#D5A34E` | Caution and evidence-incomplete state |
| Line | `#DCE4DB` | Borders and dividers |

Use Segoe UI Variable Text, Segoe UI, or Arial for interface text. Use Georgia
for the large editorial lookup headline. Keep headings left aligned and set
body copy to a readable line length.

## Lookup layout

```text
┌ brand · Sổ tay giá bất động sản ─────────────── Tra cứu / Quản trị ┐
│ Sổ tay giá, theo từng phường.        How to read verified statistics │
│ Search locality · province · property type · area basis             │
│ Resolved administrative unit                                         │
│ Price statistics by property type · sample listings · source links    │
└──────────────────────────────────────────────────────────────────────┘
```

The lookup view is for the public user. Lead with the locality query and explain
that statistics come from source-verified listings. Keep prices separated by
property type and area basis. If there are no verified listings, show an honest
empty state without sample numbers, estimated prices, or decorative charts.

## Operator view

The operator view contains data coverage, recent pipeline runs, verified listing
statistics, exports, and the explicit live-run acknowledgement. It is shown only
when `WARDPRICE_ADMIN_VIEW=1`; this flag controls visibility, not authentication.
The app binds to localhost by default. Never add live email or scheduler controls
to this page without a separate product decision.

## Interaction and accessibility

- Preserve explicit locality disambiguation; never choose a fuzzy result for the user.
- Make the source link available next to each listing and explain unverified data.
- Maintain visible keyboard focus and text contrast; label status in words as well as color.
- Respect `prefers-reduced-motion`; keep transitions limited to user actions.
- At narrow widths, stack the hero, filters, and metric groups without horizontal scrolling.
- Do not display fabricated prices, coverage figures, listing sources, or citations.
