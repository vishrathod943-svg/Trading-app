# Delayed-only automatic paper scalping (v0.4)

This is a separate server-side simulation, not an IBKR order engine, brokerage paper order, or validated scalping strategy. No order API is imported or called. The existing read-only IBKR integration and rejection of broker automation remain intact. Do not interpret delayed historical OHLC fills as executable market prices.

## Start on the configured server

Keep Gateway logged in and the backend in `ibkr` mode with `IBKR_DATA_TYPE=delayed`. Update and restart with the existing short commands:

```bash
git pull --ff-only
bash scripts/start-us.sh --desktop
python3 scripts/start-paper-scalping.py
```

The last command arms ALL eligible watchlist stocks/ETFs / 5-minute monitoring by sending an authenticated local request, reading the backend token privately. Or use **Automatic paper scalping** in the browser or Android **Trades** tab. Select `ALL` (default) to scan all eligible watchlist stocks/ETFs, or select one qualified stock/ETF, and 5m or 15m. All symbols share one virtual account and daily limits. The browser allows 1–3R targets; the CLI and Android default to 2R. The service remains stopped until armed. API endpoints GET/POST `/paper-auto` require the normal backend authentication. A POST with `enabled:false` pauses the simulation.

Only a broker-reported `delayed` quote with a valid price and receipt age <=90 seconds qualifies. Live, frozen, delayed-frozen, unknown, synthetic and missing feeds are rejected. Closed historical bars must be recent (last close within 45 minutes), correctly ordered and complete. Historical access may still be unavailable without permissions; no synthetic fallback is allowed. The worker polls once per minute and shares the broker chart cache. It is not millisecond automation.

## Capital and risk

- $1,000 initial **virtual** balance, with at most 0.5% risk per entry (initially $5), including illustrative costs. Risk capital is capped at the smaller of current simulated balance and $1,000.
- One open simulated position, whole stock/ETF shares, long-only. Positions must fit virtual cash, including the illustrative fees. Shorts and futures are skipped: borrowing and actual futures margin are unverified.
- Illustrative round-trip fee model: $2 plus $0.01 per share. This is a model, not an IBKR fee quote; no slippage model. Targets aim for the selected net R under this fee model, rounded outward to the broker tick. Gaps can exceed planned risk and the $20 daily loss threshold.
- Stop new entries at $20 realised daily loss, 3 consecutive losses, or 10 entries/day. Counters reset by UTC day; balance and journal persist. Pause/rearm does not reset losses or balance.
- New signals are restricted to regular-session weekdays: signal close 09:35–15:25 New York time, next-bar entry before 15:30. This is a clock window, not a full exchange holiday/early-close calendar; no bars means no entries. Positions exit on a modeled stop/target, after 30 minutes, or at the first supplied close at/after 15:55. Gaps/missing bars do not create hindsight exits.

## Causal supported setup rules

All currently supported rules are considered for the selected symbol: BOS/CHoCH with a recent unfilled same-direction FVG; BOS/CHoCH with a candidate order block; liquidity sweep with a recent unfilled same-direction FVG. These use the documented pivot/zone heuristics, not every ICT concept. A recent FVG is within five bars. Unsupported short setups can be detected but receive no fill.

Arming establishes a baseline at the latest completed bar and ignores pre-existing historical setups. A signal is recorded only after a NEW candle closes. Its stop uses only the signal-time zone plus a one-tick buffer. A simulated entry occurs at a later contiguous candle's open, and size uses that open and the stored stop; that candle's high/low/close never informs the entry or size. Since bars arrive after closing (and may be delayed), the recorded next-open price is a hypothetical OHLC fill, not a contemporaneous execution or measured performance.

The entry candle can also stop/target out. If OHLC touches both, stop wins. Stop gaps fill at the adverse open; target gaps receive only the target. No same-bar re-entry is allowed. Multiple unseen bars, missing bars or contract changes establish a fresh baseline and mark an open simulation unresolved, with no invented exit. An unresolved position disarms the monitor and prevents re-arming until its journal is reconciled; unknown P&L is not silently ignored. Expiry/contract checks are retained in the processor even though futures fills are currently excluded.

## Visibility and persistence

Browser and Android charts plot the most recent matching paper trade's entry/stop/target/exit levels when within the visible price range. Journals label every result PAPER and distinguish unresolved states. This does not change daily setup scores. The service continues while clients are closed as long as the backend and Gateway remain available. A server/backend restart deliberately disarms it; open simulations become restart-unresolved rather than automatically resuming. Pausing also leaves unresolved open simulations without fabricated P&L and blocks re-arming until reconciliation. No automatic reconciliation is implemented.

State is saved atomically in SQLite beside `FO_DATABASE`, with suffix `.auto`, in the existing data volume. The most recent 200 trades and 100 event messages are retained; this is not a regulatory audit archive. Initial capital and cumulative balance/counters remain persisted. No actual $1,000 is moved or reserved. Actual phone/Android device interactions and real delayed-data availability remain deployment checks.


## Larger-watchlist mode (v0.4.1)

The supplied deployment watchlist now contains 40 unique instruments: 36 US stocks/ETFs and four CME index futures. Only the 36 STK symbols are eligible for automatic paper entries. `ALL` means all eligible symbols in this configured watchlist, not every listing in the US market. IBKR permissions and data capacity still control availability. Default in-code/demo universes remain the original small samples; deployment uses `deploy/us-watchlist.json`.

Each symbol has its own bar cursor, pending setup and contract baseline, persisted atomically with the shared journal. Virtual balance, loss limits, daily entry count and max-one-open-position apply across the entire watchlist, not separately per symbol. A new symbol cannot enter before the previous position’s exit bar has completed, preventing overlap hidden by OHLC-only sequencing. Quote/history requests are serialized, use the existing cache and are spaced at least 3.2 seconds apart. This is rotating research coverage, not simultaneous full-market or millisecond scanning. The worker checks available stocks when flat; once a paper position opens it prioritizes that symbol's exits, resuming the broader scan afterward. Missing intervening bars establish fresh baselines rather than generating retrospective entries.

The browser shows the active symbol scope/timeframe from server configuration, disables changing the fields while running, offers the eligible symbols and reports initialized symbol count. Android shows actual server scope. Entering `ALL` or running the updated CLI without `--symbol` arms all eligible configured stocks. A single symbol remains supported. Let an open simulated position finish before updating/restarting; unresolved paper positions block re-arming and no automatic reconciliation is provided. The monitor must be explicitly armed after a software restart.
