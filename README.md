# Compass v0.4.1 · US stocks and index-futures research

**US setup starts here: [US_START_HERE.md](docs/US_START_HERE.md).** Version 0.3 adds a read-only IBKR research adapter, USD contract metadata, futures multiplier-aware risk calculations, a 12-instrument synthetic US demo, and an iPhone browser dashboard at `/app`. It does not submit IBKR orders. A separately installed/logged-in official TWS or IB Gateway and market-data entitlements are required for live data. No new AWS server has been provisioned; don't reuse the deleted server's old IP. See the [handoff checklist](docs/US_READY_CHECKLIST.md) and [synthetic mobile browser preview](docs/images/us-research-mobile.png).

Version 0.3.1 adds 1m, 5m, 15m, hourly and daily chart selection with completed-bar ICT overlays. See [rules and limits](docs/ICT.md) and the [synthetic intraday preview](docs/images/intraday-mobile.png). Broker intraday charts require IBKR historical-data access; updates are cached, not millisecond candle streaming.

Version 0.4 adds a separate **delayed-only automatic paper scalping monitor**, not broker orders: $1,000 virtual balance, at most 0.5% risk/entry, net fee-model RR targets, daily/consecutive-loss limits and chart levels. See [paper scalping rules](docs/PAPER_SCALPING.md). It is stopped until explicitly armed and never resumes automatically after restart.

Version 0.4.1 expands the deployment watchlist to 36 stocks/ETFs plus four research-only futures. Paper scope `ALL` scans the eligible configured stocks using one shared $1,000 virtual account and one-position limit. This is bounded watchlist coverage, not every US listing.

The sections below also document the retained India/Kite workflow.

Native Kotlin/Jetpack Compose app and Python FastAPI backend for research, paper trading and a guarded Zerodha Kite option-order path. Version 0.2 adds streaming broker prices, authenticated server access, Android Keystore token storage and optional server-side automation. **Live broker connectivity, real order execution and hosted deployment have not been verified. Keep real orders disabled until account/deployment verification is completed.**

## Get the APK

The debug APK is in [`apk/FO-Compass-debug.apk`](apk/FO-Compass-debug.apk). It supports Android 8+ and targets Android 15. This is a debug build, not a signed Play Store release.

Demo mode includes eight explicitly synthetic NSE stock snapshots for offline dashboard/chart exploration. Paper replay requires the backend. Live mode never substitutes synthetic data when the **Require real Kite data** setting is enabled.

## Online and automatic trading

Start with the [AWS Lightsail hosting guide](docs/HOSTING.md). Read **[Kite connection, hosting and automation setup](docs/LIVE_SETUP.md)** before configuring real-money orders. The repository contains a Docker/Caddy HTTPS deployment recipe in `deploy/`. A real server, hostname and valid Kite session are still required; the APK is not itself a hosted service.

Live quotes arrive from Kite full-mode WebSocket ticks. The server forwards coalesced current prices to the phone at up to 10 Hz, with broker exchange timestamps and age. It does not promise millisecond quotes or fills. Setup indicators use completed daily candles and startup-loaded histories, while LTP is streamed independently.

The server can monitor and execute without the phone open. Automation starts **OFF** after every server restart. Start with **paper automation** against the real feed. Live orders require a separate server permission (`FO_LIVE_ORDERS=true`), fresh feed/readiness checks and typing `ENABLE LIVE ORDERS` in Android. Credentials remain on the server. The phone holds only an encrypted backend access token.

Option entries are one-lot long CE/PE limit buys, with ATM/liquidity/expiry checks. Full premium must fit the per-trade risk budget; daily committed premium and realized losses are limited. Stop and target levels use option fill prices and configurable premium R:R. Broker-side stop-limit sells, persistent order intents, tag-based recovery, no blind retries, partial-fill cancellation/protection and target modifications of the same exit order are implemented. Gaps, rejections, partial fills, server outages and order limits can prevent protection or fills. This is not exchange-atomic OCO or production-ready unattended trading. **Stop new entries** does not flatten positions or cancel pending buys.

## Local backend

Requires Python 3.12+.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
cd backend
../.venv/bin/python -m pytest -q
../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --timeout-graceful-shutdown 5
```

Or run `./scripts/backend.sh`. Default `FO_MODE=demo` needs no broker credentials. SQLite stores paper trades and events. `.env.example` documents environment variables; it is not automatically loaded. Use exported variables or Uvicorn `--env-file` for local work. `compose.yaml` runs a loopback-only demo server; `deploy/compose.live.yaml` is the separate HTTPS Kite deployment. Do not expose the unauthenticated demo publicly.

## Build Android

Open `android/` in Android Studio with JDK 17/21, SDK 35 and Build Tools 35.0.0:

```bash
cd android
./gradlew assembleDebug lintDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

In this prepared Linux cloud workspace use `python scripts/bootstrap-android-cloud.py`, then `./scripts/android-build.sh lintDebug`. Downloads retain TLS and pinned checksum verification.

The default emulator URL is `http://10.0.2.2:8000`. For a USB device run `adb reverse tcp:8000 tcp:8000` and set `http://127.0.0.1:8000`. All other destinations require HTTPS. Set the backend token and **Require real Kite data** in Settings for a live server. Dashboard, search/filters, candle-volume chart, technical context, hidden small-sample backtests, paper desk, alert history and execution controls are included. FCM/background push, multi-user login and cloud sync are not implemented.

## Rules and analysis

`backend/rules.example.json` shows configurable thresholds and weights. Copy it outside tracked source and export `FO_RULES_FILE=/absolute/path/rules.json`, then restart. Weights must sum to 100 and invalid rules fail startup.

A long requires price > EMA50 > EMA200, a prior-20-session high breakout, volume >1.5× prior average, RSI 50–75 and positive MACD; shorts mirror it. Weight defaults are setup 30, volume 20, major moves 15, holdout win rate 20 and fundamentals 15. Missing fundamentals and insufficient sample statistics earn zero. Backtests use non-overlapping 5/10/20-session underlying close returns in a chronological 30% holdout, with 25 bps assumed round-trip costs; samples under 20 are hidden. These are not option backtests or guarantees of performance. The automated option-premium target R:R is separate from the underlying research plan.

## API

Kite mode requires an `Authorization: Bearer <FO_API_TOKEN>` header for HTTP and WebSocket connections. Demo can optionally require it too.

- `GET /health`, `/broker/status`, `/scan`, `/stock/{symbol}`, `/rules`
- `GET /automation`, `POST /automation`, `POST /automation/stop`
- `GET /trades`, `/alerts`; `POST /trades`; `DELETE /trades/{id}` (paper desk)
- `POST /position-size`, `/replay/demo`, `/replay/{id}/tick` (demo paper replay)
- `WS /live`: snapshots plus separate price/timestamp tick messages in Kite mode

See [implementation boundaries](docs/ARCHITECTURE.md), [online deployment](docs/LIVE_SETUP.md) and [validation](docs/VALIDATION.md). GitHub CI builds/lints Android, runs backend tests and uploads a debug APK artifact. Hosted CI is not claimed until its actual results are checked.

Educational tool. Not investment advice. F&O can lose the full premium. Alerts and orders may be delayed; realized fills and risk may differ from plans.
