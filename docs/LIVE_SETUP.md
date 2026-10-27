# Online Kite mode (v0.2)

This release includes a Kite SDK streaming adapter and a guarded option-order path, but it has **not been connected to a real broker account or validated with real orders**. No hosted endpoint is provisioned by building the APK. Existing demo mode remains available. This is a single-account personal backend, not a multi-user trading service.

## What is needed

1. A Zerodha account, a Kite Connect application with the required historical/live market-data and order API permissions, and a valid daily broker session. Follow Zerodha's current authentication process and any account/app/IP requirements. The app does not collect your Zerodha password or bypass daily login/2FA.
2. An always-on Linux server and hostname pointing to it, with ports 80/443 accessible and Docker Compose installed. Broker orders remain on your account even if the server or phone disconnects.
3. A securely supplied server API key, access token and independently generated backend access token. Do not send secrets in chat, commit them or embed them in the APK. The backend token must be at least 32 characters. You can generate one locally using `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'` and keep the output private.

## Configure from a phone without an editor

After cloning/updating the repository, run this in your server SSH terminal:

```bash
python3 scripts/configure-server.py --domain YOUR_HOST
```

For this deployment use `--domain tradeliveerrrs.duckdns.org`. Paste the Kite API key at the hidden terminal prompt and press Enter; the key will not appear on screen. The helper requires only standard Python, saves `~/fo-private/live.env` with owner-only permissions, preserves existing backend/access tokens, creates a random backend token if absent, and keeps real trading OFF. It never asks for a broker password or prints credentials. Do not share the settings file or a screenshot of its contents. If a text editor is already open, close that SSH browser tab and open a new SSH connection before running the command.

## Deploy

Copy `deploy/live.env.example` to a private file outside the checkout, set `FO_DOMAIN`, `FO_API_TOKEN`, `KITE_API_KEY` and `KITE_ACCESS_TOKEN`, and keep `FO_LIVE_ORDERS=false` for paper verification. Restrict the file to its owner. From the checkout:

```bash
docker compose --env-file /absolute/private/live.env -f deploy/compose.live.yaml up -d --build
```

Caddy terminates HTTPS and proxies WebSockets. The broker service is not exposed directly. The server needs outbound HTTPS to `api.kite.trade` and WSS to `ws.kite.trade`. Authentication/login may also use `kite.trade`. Installation uses the package registries documented by the cloud setup. No TLS/signature verification should be disabled to fix connectivity. Provisioning, DNS, TLS issuance and Docker deployment were not performed in this cloud workspace.

In Android Settings enter `https://YOUR_HOST`, the **backend** access token, and enable **Require real Kite data**; save. The phone encrypts this token with Android Keystore. Kite credentials remain on the server. Watch the analysed-symbol count and broker tick age. Warm-up requires one rate-limited historical request per eligible underlying and may take several minutes. Synthetic data is never substituted in this live mode.

## Kite developer redirect URL

Register `https://YOUR_HOST/kite/callback` as the redirect URL in the Kite developer app (for this setup: `https://tradeliveerrrs.duckdns.org/kite/callback`). The callback must be reachable through the deployed HTTPS server before doing the login flow. The initial deployment permits an empty KITE_ACCESS_TOKEN: the API and callback start, while market data remains not-ready and automation stays off. After the helper saves a verified session, restart the backend to load it. The public GET landing page never reflects query values, exchanges credentials or enables trading; complete session exchange in the private terminal helper. Default Docker/helper startup disables HTTP access logging so request-token query strings aren't logged. If using another proxy/server, keep callback query strings out of its access logs too. Merely visiting this page does not prove broker authentication.

## Daily broker login helper

On your own secure server terminal, install the backend requirements in a virtual environment and run:

```bash
.venv/bin/python scripts/kite-login.py --env-file /absolute/private/live.env
```

The file must already exist outside the checkout with mode 600. This helper uses Kite's official login URL and session-exchange SDK. Complete login/2FA in your browser and copy the complete final redirect URL from the browser address bar into the hidden terminal prompt. The helper validates its hostname and extracts the single request token; a raw token is also accepted. Request tokens are short-lived and single-use, so use the new login link printed by each helper run. The API secret is requested without echo and is not saved. The verified access token is written to the private env file, never printed. The login URL contains your app's API key; keep the terminal private. Never send request/access tokens or secrets in chat. Restart the deployment to load the new session and explicitly re-arm after readiness checks. This helper's live session exchange has not been exercised with an actual account.

## How scanning and execution work

- The instrument master comes from Kite. Cash-equity underlyings are matched against listed NFO/BFO futures, with NSE preferred for duplicate symbols. Actual counts and failed-history counts are exposed, rather than claiming an exhaustive exchange-certified universe. The master and completed-day histories load at startup; restart with a fresh daily session to refresh them.
- Signals use **completed daily candles** (EMA/RSI/volume/breakout rules), not an incomplete day or a millisecond technical backtest. Streaming LTP is separate. Historical fundamentals, event calendars, corporate-action verification, Greeks and a full option-chain data service are not supplied by this adapter.
- Incoming full-mode ticks require an exchange timestamp no more than three seconds old. Android receives coalesced latest-price updates at up to 10 Hz; broker monitoring checks latest prices about four times a second when broker calls are responsive. Broker order reconciliation is limited to once per second. This is not HFT, every-tick strategy execution or a latency SLA. No exchange/broker/Internet system can promise a new quote or fill every millisecond.
- When armed, a confirmed setup must have its underlying within 0.3% past entry; the service skips gaps rather than chasing. It considers the three nearest strikes at the earliest expiry at least ten days away, CE for a long setup and PE for a short setup. It requires OI >=10,000, volume >=1,000 and a <=3% spread. This is an ATM liquidity heuristic, **not** a verified delta/IV model.
- Buys are NRML limit orders of **one lot**. The full option premium must fit capital × risk% (maximum 2%); aggregate committed premium plus realized daily losses must fit the configured daily limit. This is intentionally more conservative than sizing only to a stop that can gap. External broker positions block live arming when they don't match the app ledger.
- R:R applies to **option premium**. With a 25% stop and 3R target, a ₹100 fill produces a ₹75 stop trigger and ₹175 target (rounded to instrument tick size). Levels are recalculated from actual fills. Costs are not subtracted from displayed P&L and realized R:R can differ.
- After a filled entry is confirmed, the server submits a broker-side stop-limit sell. At the target, it modifies **that same sell order** to a marketable limit, avoiding two competing sell orders. Stop-limit and target-limit orders can remain unfilled in a gap, halt, illiquid market or rejected modification. There is a period between entry fill and protection acknowledgement; this is **not** an exchange-atomic bracket/OCO order.
- Partial entries trigger one cancellation of their remaining quantity, then protection of confirmed fills after the broker reports a terminal entry status. Unknown submissions never auto-retry; persisted tags are reconciled against broker order history. Unresolved entry/protection pauses automation for immediate manual review. A confirmed rejected/cancelled protective order triggers one durable emergency market sell with broker automatic market protection; unsupported/rejected/uncertain emergency exits require immediate operator action, never blind resubmission.
- New entries are restricted to weekdays 09:20–15:00 IST and require fresh exchange ticks (no synthetic holiday trading). At 15:00 pending entry orders are cancelled once and reconciled. At 15:15 the server stops new entries and attempts marketable-limit exits via existing protective orders. Fills are not guaranteed. DAY protective orders expire at session end; verify all positions and orders before market close. Overnight unattended holding is **not supported**.
- Arming is intentionally reset after every process restart. Feed disconnect or reconciliation failure pauses new entries. A reconnect does not silently re-arm. Exits are still monitored while entry arming is off.

## Enable only after broker-side verification

First verify live data and paper automation with your account. Then separately configure `FO_LIVE_ORDERS=true` on your server and restart, reconnect the phone, choose **Real orders**, review capital/risk/R:R/limits, and type `ENABLE LIVE ORDERS` in the confirmation. That switch authorizes actual orders without requiring the phone to remain open. It does not supply a broker session or provide high availability.

**Stop new entries** stops future submissions. It does not cancel already-submitted buys, close positions, or cancel protective sells. Review/cancel/exit through Zerodha when needed. Unknown order and protection failures must be resolved at the broker before any re-arming. Never delete the automation database to bypass an unresolved intent. The database is bound to the Kite account ID to prevent accidental account switching.

## Limits before unattended real-money use

Broker integration, exchange behavior, rejection/partial-fill ordering, token expiry, hosted TLS, server restarts, market-close residual positions and Android background lifecycle still require actual account/deployment verification. External manual trades while automation runs can invalidate its ledger; don't share the account's positions with another strategy. The system does not currently continuously reconcile externally modified position quantities or supply an operator paging service. No FCM push is wired yet, so broker/app checks are still necessary for errors and session close. This release must not be represented as production-ready unattended trading.

Tests use broker doubles and never place actual orders. Keep live order permission off until these deployment and broker checks are completed.
