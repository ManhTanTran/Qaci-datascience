# Operator dashboard page

This page is available only when `WARDPRICE_ADMIN_VIEW=1` is set. The flag is a
visibility switch, not an authentication mechanism.

## Layout

- Use the shared WardPriceDaily brand bar and top-level Tra cứu / Quản trị switch.
- Start with the operator heading and a short description of the data controls.
- Keep coverage, pipeline, listings, and exports in separate tabs.
- Use compact metrics and tables because this page is intended for the operator.

## Behaviors

- Keep the live Gemini action behind its existing explicit acknowledgement.
- Pipeline preview must not make a network request or write to SQLite.
- Exports and Gmail preview remain operator-triggered; Gmail preview never sends mail.
- Do not add scheduler activation or live Gmail sending to the UI.
- Do not fabricate coverage, listing, or price values when the local database is empty.
