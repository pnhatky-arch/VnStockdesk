# Dashboard startup recovery — 2026-08-26

Symptom: Control Center rendered but the main dashboard appeared empty.
The server log showed repeated 30-second VCI timeouts. Automatic health checks,
futures quotes and three-timeframe history ran synchronously before the main
dashboard could render. Browser reloads repeated those requests.

Changes:

- Dashboard-only provider reads run in bounded daemon workers with one in-flight
  request per key, a six-worker cap and no unbounded queue.
- Futures candles use explicitly labeled local cache while their network load
  is pending. The new cache-only path never calls a provider or rewrites files.
- Quotes return PENDING instead of blocking. Retained quotes preserve their
  original timestamps and their market age is recalculated, not reset to zero.
- The automatic health panel reports pending/previous results without blocking
  the rest of the page. Explicit full data checks remain user-triggered.
- BOT data loaders and order execution paths are unchanged.

Verified: 95 unit tests pass, including stalled-provider, concurrency-limit,
TTL, failure-retention and cache-only tests. A fresh process on temporary port
8506 rendered all eight tabs, OHLC data, Paper and portfolio controls without
Streamlit exceptions. The old 8503 process retained previous compiled code;
restart using STOP VN DASHBOARD.app then START VN DASHBOARD.app to deploy.

Read-only integrity check: 1,396 full-market scan rows, 100 VN100 rows, 30 VN30
rows, 1,511 top-level OHLCV CSV files, nine readable account/portfolio JSON
files. No account reset, portfolio deletion or market rescan was performed.
