# ICT research overlays

The stock-detail endpoint includes `ict`, calculated from the same last 80 completed daily candles displayed on the chart. Android displays active zones, equilibrium and recent structure events; the browser adds candlesticks, event labels, a recent event list and an overlay toggle.

Supported rules:
- Unique two-left/two-right swing pivots, available only when both right bars close.
- Close beyond an unbroken confirmed pivot: BOS; reversal of the last break direction: CHoCH.
- Wick beyond the pivot with a close back inside: liquidity sweep (repeat sweeps can appear).
- Three-bar wick imbalance: bullish/bearish FVG. Full traversal marks it filled; partial mitigation does not.
- Last opposite candle within ten bars before a structure break: candidate order block using its full range. These are deliberately labelled candidates.
- Latest confirmed swing high and low: dealing range and midpoint; premium above and discount below.

Events include the detection candle and pivot origin. Zones start when detected, not backdated to suggest prior knowledge. Detection is causal within the supplied window; older omitted history can change initial trend classification. Filled zones are retained in the API and hidden on the chart. Zone expiry uses full traversal and is not a validated mitigation model.

This is a first subset, not all ICT concepts. Kill zones, intraday session levels, opening ranges, SMT across synchronized instruments, breakers, mitigation blocks, OTE entries and multi-timeframe bias are not implemented. The existing broker connection streams quotes separately from completed daily history; tick messages do not fabricate intraday candles or recalculate daily overlays. Broker daily refresh supplies new completed-bar analysis. Synthetic mode remains synthetic. No new order execution or profitability claim is attached to these labels.


## Intraday charts (v0.3.1)

`GET /chart/{symbol}?timeframe=1m|5m|15m|1h|1D` uses the same backend authentication as other data endpoints. Android and browser detail views offer these timeframes, with 30-second client refresh while the chart view is active. IBKR intraday requests are cached for 60 seconds per contract/timeframe, serialized and paced at a minimum of three seconds between requests. Failed requests are cached too. At most 160 responses are retained. Daily charts retain the existing daily refresh behavior.

IBKR requests unadjusted TRADES history with extended hours (`useRTH=False`), UTC timestamps and a maximum of 240 completed bars. Open candles, invalid OHLC, negative volume, naive timestamps and duplicates are excluded. Zero-volume valid bars are accepted. Futures use the qualified expiring contract, not a continuous series. The last-bar timestamp is displayed; stale history and closed-market bars must not be treated as current quotes. Historical bars alone do not establish live-data entitlement or a latency promise. A failed broker request displays unavailable, with no synthetic fallback.

Synthetic charts are labelled and simulate arbitrary bars including non-market hours. They do not model exchange calendars or provide validated setups. Daily setup scores and risk plans remain daily and do not change when selecting an intraday chart. Intraday ICT uses the same explicit pivot/gap heuristics; session kill zones, opening ranges, SMT and multi-timeframe confirmation remain outstanding. Kite intraday charts are not supported in this update.
