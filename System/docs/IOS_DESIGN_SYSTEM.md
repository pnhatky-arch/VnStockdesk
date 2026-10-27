# iOS-inspired appearance

The dashboard uses one presentation system for Paper and Live. This is a web
interpretation of Apple's layered surfaces and Liquid Glass navigation, not
native iOS UI or a claim of pixel-identical rendering.

## Shared components

- `src/ui_theme.py`: Light/Dark palettes, system font stack and signal colors.
- `assets/ios_theme.css`: navigation, Control Center, cards, tabs, forms,
  multi-selects, account metrics, explanations, dialogs, AI and responsive rules.
- `app.py`: loads styles with `st.html` (not Markdown), and supplies the same
  colors to Plotly, TradingView Lightweight and styled data tables.

Use semantic colors: green for positive, red for negative, blue for interactive
items, purple/amber for technical overlays. Never override every `span` or `svg`:
that destroys trading status colors. Never hide the sidebar reopen control.
All selected tabs retain the requested 3px rounded red underline.

Content is solid for readability; translucency is reserved for navigation.
Controls have 44px minimum height, metrics use tabular numerals, and captions
remain distinct from headings. Reduced-motion and reduced-transparency
preferences have fallbacks. SF is used when installed, with system-font fallbacks;
no Apple font files are redistributed.

## Compatibility and verification

Streamlit 1.62 uses React Aria tabs/selects; style semantic roles or stable test
IDs instead of generated Emotion classes. Canvas table headers and editable
cells are still rendered by Streamlit, not by HTML CSS. Read-only cells use
Pandas Styler; editing behavior, sorting and form submission remain native.

Run `.venv/bin/python -m unittest discover -s tests -q`. Theme tests verify
palette parity, >=4.5:1 text contrast on base and card surfaces, complete CSS
variables, HTML stylesheet loading and named futures-chart symbol arguments.
Browser checks should cover both themes, both system modes, selects and tabs;
never start a bot, submit an order, reset an account or save test portfolios
just to validate styling.

If a long-running dashboard keeps old code, reopen it with the existing STOP
and START dashboard launchers. Restart only the UI, not trading bot processes.

### Verification on 2026-08-26

- 39 unit tests passed; Python compilation passed.
- Browser: Light/Dark overview, language dropdown (Vietnamese/English),
  Paper/Live switching, futures chart, AI tab and portfolio forms inspected.
- Computed selected-tab underline: 3px in both modes. Light inputs:
  white background, dark text, 12px radius. No Streamlit exception in the
  final LIVE futures/portfolio checks.
- Browser viewport override did not take effect (remained 1280×720), so mobile
  rules exist but mobile visual QA remains unverified.
- Main service at port 8503 could not be restarted due process permissions;
  visual verification used an isolated service at 8504. The user must reopen
  the main dashboard to guarantee the new code is loaded.

## References

- https://www.apple.com/newsroom/2025/06/apple-introduces-a-delightful-and-elegant-new-software-design/
- https://developer.apple.com/design/human-interface-guidelines/dark-mode
