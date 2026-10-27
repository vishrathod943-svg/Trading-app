# ICT research overlays

The stock-detail endpoint now includes `ict`, calculated from the same last 80 completed daily candles displayed on the chart. Android displays active zones, equilibrium and recent structure events; the browser adds candlesticks, event labels, a recent event list and an overlay toggle.

Supported rules:
- Unique two-left/two-right swing pivots, available only when both right bars close.
- Close beyond an unbroken confirmed pivot: BOS; reversal of the last break direction: CHoCH.
- Wick beyond the pivot with a close back inside: liquidity sweep (repeat sweeps can appear).
- Three-bar wick imbalance: bullish/bearish FVG. Full traversal marks it filled; partial mitigation does not.
- Last opposite candle within ten bars before a structure break: candidate order block using its full range. These are deliberately labelled candidates.
- Latest confirmed swing high and low: dealing range and midpoint; premium above and discount below.

Events include the detection candle and pivot origin. Zones start when detected, not backdated to suggest prior knowledge. Detection is causal within the supplied window; older omitted history can change initial trend classification. Filled zones are retained in the API and hidden on the chart. Zone expiry uses full traversal and is not a validated mitigation model.

This is a first subset, not all ICT concepts. Kill zones, intraday session levels, opening ranges, SMT across synchronized instruments, breakers, mitigation blocks, OTE entries and multi-timeframe bias are not implemented. The existing broker connection streams quotes separately from completed daily history; tick messages do not fabricate intraday candles or recalculate daily overlays. Broker daily refresh supplies new completed-bar analysis. Synthetic mode remains synthetic. No new order execution or profitability claim is attached to these labels.
