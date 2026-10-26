# F&O Compass

Native Android research and paper-trading app with a Python FastAPI backend, based on the supplied NSE/BSE screener specification. **This is a working demo foundation, not a production trading service.** All market history is deterministic synthetic data. No real orders, live quotes, executable option ideas, or background push delivery are provided.

## Run the backend

Requires Python 3.12+.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
cd backend
../.venv/bin/python -m pytest -q
../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The tested transitive versions are pinned in `backend/requirements.lock`; `requirements.txt` lists the direct dependencies.

Alternatively run `./scripts/backend.sh` from the checkout, or `docker compose up --build` (Docker required). Docker binds only to loopback. Interactive API documentation is available at the server's `/docs` path. SQLite persists paper trades and events; the demo data itself is repeatable. `FO_DATABASE` selects the database file. `.env.example` is a reference; export variables explicitly or use Uvicorn's `--env-file` option.

## Build and run Android

Open `android/` in Android Studio with JDK 17 or 21, SDK platform 35 and Build Tools 35.0.0. Android 8+ (API 26) is supported.

```bash
cd android
./gradlew assembleDebug
# APK: app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

In this cloud workspace, `python scripts/bootstrap-android-cloud.py` prepares checksum-verified tools and `./scripts/android-build.sh` builds with them. Standard Android Studio builds do not need this cloud helper.

The default API is `http://10.0.2.2:8000` for the Android emulator. For a USB-connected device, run `adb reverse tcp:8000 tcp:8000`, then set `http://127.0.0.1:8000` in Settings. Remote servers require HTTPS. Accept the first-launch educational disclaimer. Use **Overview → Run paper alert replay** to generate an isolated DEMO paper trade and see persisted entry/T1/T2 events in Trades and Alerts. Swipe/system back returns from stock details. The refresh button retries failed connections.

The app includes five tabs, dark/light themes, score/direction/exchange/search filters, sorting, daily candles with volume, indicators, major moves, holdout statistics, paper trade tracking/cancellation, risk preferences and server configuration. The last successful scan is cached in private app storage and shown with a stale banner if disconnected. Eight explicitly synthetic stock snapshots are bundled so a fresh install can explore the dashboard and charts without a backend. They remain labelled offline/stale. Paper trades and replay require the backend. WebSocket snapshots update while the app process runs; this is **not** Android background alert delivery.

## Scanner and rules

`backend/app/analysis.py` implements EMA20/50/200, Wilder RSI and ATR, MACD/signal, previous 20-session breakout bands, volume ratio, major-move detection, setup rules, position sizing and a liquidity-filtered option selection utility. The provider returns no option contracts, so the app shows options as unavailable.

A long requires close > EMA50 > EMA200, a previous-20-session high breakout, volume >1.5× previous 20-session average, RSI 50–75 and positive MACD. Shorts mirror those conditions. Only confirmed setups above the score threshold get a plan. Entry is the signal candle extreme; an EMA20 pullback reference is also displayed. Stops use the tighter of 1.5 ATR and the recent swing distance, with 1.5R/3R targets. Pullback entries need their own confirmation; they are not separate tracked recommendations.

Score weights: setup 30, volume 20, major moves 15, holdout win rate 20, fundamentals 15. Volume scales up to 3×; move score scales up to five detected moves. Missing fundamentals and hidden/insufficient backtest statistics earn zero points rather than fabricated values. This can produce no confirmed setups, which is valid.

To edit rules, copy `backend/rules.example.json` outside versioned source, edit it and export `FO_RULES_FILE=/absolute/path/rules.json` before starting the server. Weights must sum to 100; invalid configuration fails startup. Restart to apply changes. `/rules` exposes the effective configuration. No arbitrary code or expression evaluation is used.

Backtests use a chronological 70/30 split and non-overlapping signals in the final holdout segment. Signals use only candles available then, with fully matured 5/10/20-session close-to-close outcomes and a 25 bps round-trip cost assumption. Statistics with fewer than 20 samples are hidden. Average drawdown is average adverse closing excursion, not portfolio maximum drawdown. These are underlying-return tests, not option-premium or stop/target execution backtests. There is no tuned training phase, walk-forward validation or sector-wide backtest yet.

## API

- `GET /health`: explicit feed/push/demo status
- `GET /scan?min_score=0&exchange=NSE&sector=Banking&direction=LONG`
- `GET /stock/INFY`: candles, analysis, plans and sample counts
- `GET /rules`, `GET /trades`, `GET /alerts`
- `POST /position-size`: capital, risk_pct (max 2), entry, stop, lot_size
- `POST /trades`: confirmed symbol, capital, risk_pct; server derives the plan and quantity
- `DELETE /trades/{id}`: cancel tracking
- `POST /replay/demo`: deterministic sample lifecycle, never a trade recommendation
- `POST /replay/{id}/tick`: replay price, volume_confirmed, candle_close, optional high/low
- `WS /live`: scan, trades and alert snapshots every five seconds

See [architecture and remaining production work](docs/ARCHITECTURE.md). Do not expose this unauthenticated demo server publicly. Production requires authenticated per-user access, isolation and a licensed market-data source. No credentials are needed to run the demo; do not put broker tokens into Android settings.

Educational tool. Not investment advice. Trading in F&O involves substantial risk. Alerts may be delayed and gaps can exceed planned loss.

## Validation

See [verified checks and limits](docs/VALIDATION.md). A GitHub Actions workflow is included for backend tests and Android build/lint; it has not been run on GitHub from this workspace. The APK is debug-signed, not a Play Store release.
