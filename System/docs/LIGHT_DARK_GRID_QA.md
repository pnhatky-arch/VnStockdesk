# Light/Dark data grids — 2026-08-26

The dashboard appearance switch previously changed CSS and Styler body cells,
but Streamlit's native canvas headers and editors still used the browser's
native Streamlit theme. The two themes could disagree.

All dashboard dataframe/editor calls now use the local `src/desk_grid.py`
component and `assets/desk_grid/`. Header, body, controls and inputs use the
same explicit palette in either appearance. No CDN or extra dependency.

Features: sticky header, sort, search, 50-row pagination, horizontal scrolling,
CSV export of filtered/sorted rows, safe news links, numeric formatting and
fixed-row portfolio editing. Column labels follow the existing dashboard
translations. No changes to account stores, analysis or trading rules.

Portfolio editors remain inside Streamlit forms. Edits are submitted once with
the form. Server validation rejects negative/non-finite prices, fractional
quantities, invalid sides and malformed row counts. Disabled symbols cannot be
edited. Old responses cannot overwrite a newly selected portfolio. Invalid
input leaves the form available for correction and blocks save/analysis.

Verification:

- Browser: Light/Dark headers, body, links and inputs; stock price 21.987
  submitted on first click; futures SHORT; search/sort; invalid price rejected
  and corrected without losing submit buttons.
- Python: 91 tests passed, including 9 grid regression tests; offline pipeline
  passed. Palette tests require 4.5:1 normal-text contrast.
- Preview: `streamlit run tests/preview_valuation.py` uses synthetic data only.
  Production dashboard rendering can still wait on external market providers.
