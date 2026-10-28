# Start fresh: US stocks and index futures

## What is prepared

- Version 0.3 Android app with a bundled **synthetic** US stock/index-futures watchlist, USD prices, stock/futures filters, contract metadata, feed labels, and a futures risk API.
- An iPhone-friendly browser dashboard at `/app`, so an Android phone is not required to inspect research. It uses a backend access token, held only in tab memory. No IBKR password is entered into the dashboard.
- A read-only IBKR adapter using the pinned `ib_async` client. It connects to an already logged-in official TWS/IB Gateway socket. It does **not** implement IBKR order placement, including broker paper orders. API automation requests are rejected in IBKR mode.
- New Linux deployment files and private configuration/bootstrap helpers. No AWS resource has been created from this workspace. The user's old AWS instance was deleted: its old IP is not a valid deployment target and the old DuckDNS record must not be trusted until updated.

## 1. Confirm costs and access before another purchase

The supplied screenshot showed $100 of active AWS Free Tier credit, $0 used, expiring 26 October 2027. It did **not** establish Lightsail eligibility. Check the credit's applicable-services terms in your own AWS console. Only AWS can confirm eligibility/billing. Credits do not pay IBKR exchange-data fees. No account funding, subscription or charge was initiated by this work.

In IBKR, confirm paper-trading availability, TWS API access and the market-data entitlements needed for US stocks and CME index futures. Live prices may require a funded qualifying account and subscriptions. Paper trading can receive delayed data. Do not buy subscriptions merely because the code builds. A mobile/web account login is not a TWS/IB Gateway session.

## 2. Create a new server only after coverage is confirmed

For the documented Linux setup, use Ubuntu 24.04 LTS **x86_64**, with at least 4 GB RAM as a starting point for this small watchlist/backend plus a gateway. Actual gateway/GUI memory and CPU use must be checked; this is not a capacity guarantee. If no computer is available, a separately secured graphical desktop on the server is needed to operate the official gateway and its login/2FA. That graphical desktop/gateway is **not installed automatically** by this repository and is an outstanding prerequisite for the phone-only workflow.

Attach a NEW static IP. Update your hostname's DNS A record to that new IP and confirm it resolves correctly before sending credentials to the hostname. Remove stale AAAA records unless IPv6 is correctly configured. Do not reuse the deleted server's IP. Allow inbound 80/443; restrict SSH to your own access path. Do not expose 8000, TWS/IBKR 4001/4002/7496/7497 or remote-desktop ports to the public Internet.

## 3. Bring up the synthetic demo first (no broker or API key)

In your new server's SSH terminal:

```bash
git clone https://github.com/vishrathod943-svg/Trading-app.git
cd Trading-app
bash scripts/bootstrap-us-server.sh YOUR_NEW_HOSTNAME
```

If the repository already exists, use `cd ~/Trading-app && git pull --ff-only` first. Replace `YOUR_NEW_HOSTNAME` with the hostname that you have verified points to the NEW static IP. Do not type an old IP into the command.

The helper installs Docker/Compose on supported Ubuntu, writes `~/compass-private/us.env` with mode 600 and a random backend token, and starts `deploy/compose.us.yaml` in **us_demo** mode. It preserves an existing backend token. Real orders stay disabled. The bootstrap requires sudo and Internet access to package/image registries; it is a provided recipe, not evidence that a server was provisioned.

After Caddy obtains HTTPS, open `https://YOUR_NEW_HOSTNAME/app` in Safari. Enter the `FO_API_TOKEN` value from your own private file. View/copy that value privately in your SSH app; never send the file, token, or its screenshot through chat. Alternatively install the debug Android APK and enter the same HTTPS URL/backend token in Settings, select the US demo dataset and leave Require live broker data OFF for this step.

The synthetic watchlist includes AAPL, MSFT, NVDA, TSLA, AMZN, META, SPY, QQQ, MES, MNQ, ES and NQ. These are simulated prices, not delayed live data or real recommendations.

Optional personal-phone desktop access: after installing a loopback-only VNC/noVNC desktop, use the [HTTPS desktop guide](PHONE_DESKTOP.md). It adds a separate website password without exposing desktop ports.

## 4. Prepare the official IBKR gateway separately

Use the official [IBKR TWS API documentation](https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/) and [IB Gateway download](https://www.interactivebrokers.com/en/trading/ibgateway-stable.php). Install it on your own computer or the new server's secured graphical desktop. This project does not collect the username, password or MFA code, automate 2FA, or install an unofficial credential-containing gateway image.

Log into **paper trading**. Configure the API settings to allow socket clients, keep **Read-Only API enabled**, and use paper Gateway port **4002** or paper TWS port **7497**. Actual UI labels/settings can vary by IBKR version; confirm the socket port shown in your installation. The backend should use positive client ID 71; diagnostics use 72. Do not use client ID 0.

The Linux Compose recipe uses host networking, so its backend reaches a native gateway on the SAME server at 127.0.0.1. It does not connect automatically to a gateway on a phone or a different computer. The gateway, its graphical login and API socket must remain available; relogin/2FA or maintenance interruptions may require you to act. A paid server is not a guarantee of unattended brokerage access.

If running TWS on a separate laptop, first test the backend locally with that TWS rather than exposing or forwarding its API port over the public Internet.

## 5. Check the gateway and enable read-only research

On the machine running the gateway:

```bash
sudo apt-get install -y python3-venv
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
.venv/bin/python scripts/ibkr-doctor.py --port 4002
```

The doctor confirms only the socket/read-only login, not market-data subscriptions or real-time prices. Then update the private US configuration and restart:

```bash
python3 scripts/configure-us.py --domain YOUR_NEW_HOSTNAME --mode ibkr --port 4002
sudo docker compose --env-file "$HOME/compass-private/us.env" -f deploy/compose.us.yaml up -d --build
```

In the client, refresh and inspect connection diagnostics. Per-instrument labels distinguish **live**, **delayed**, **frozen**, **delayed_frozen**, waiting and stale. A fresh network message carrying delayed data is still delayed. Timestamps in this adapter are broker-receipt timestamps, not exchange timestamps or a measured latency SLA. If all quotes are delayed or unavailable, readiness remains false. There is no synthetic fallback in IBKR mode.

## Instrument and calculation boundaries

The watchlist is configured in `deploy/us-watchlist.json` (1–40 unique symbols). It is not a scanner for every US listing. Stocks route via SMART. Futures are CME equity-index contracts; common examples MES/ES are S&P 500 index futures and MNQ/NQ are Nasdaq-100 index futures. These are not futures on each individual stock. Futures qualification picks the nearest unambiguous contract with at least seven calendar days until expiry; exact contract ID, expiry, tick size and multiplier come from the broker, not a guess. It refreshes on a new New York calendar day and reconnects with bounded backoff.

Daily analysis requests two years of adjusted stock closes (`ADJUSTED_LAST`) or the selected expiring future's trades, excluding the incomplete current daily bar. Futures history is not a continuous back-adjusted series. At least 201 valid daily candles are required for indicators; stale or insufficient history cannot confirm a setup. This release does not supply US options chains, live futures depth ladders, full-market coverage or company fundamentals.

The futures risk calculator uses `abs(entry-stop) × multiplier` per contract and checks tick alignment. For MES, a five-point stop at multiplier 5 is $25 per contract; a $100 risk budget estimates four contracts. This does not verify margin/buying power, include fees or guarantee fills/loss limits. Actual margin and permissions must be checked at the broker. IBKR orders cannot be enabled through this research release.


## Without live-data subscriptions

After confirming socket login, request IBKR delayed data where available (not simulated prices):

```bash
python3 scripts/configure-us.py --domain YOUR_HOSTNAME --mode ibkr --data-type delayed
bash scripts/start-us.sh --desktop
```

Use the short restart helper with `--desktop` when phone desktop access is configured. Otherwise omit `--desktop`. The setting is saved as `IBKR_DATA_TYPE=delayed` and preserved by later configuration runs unless explicitly changed. The default for new configurations remains `live`; `delayed_frozen` is also supported for requesting the most recent delayed frozen data when offered. Generic futures open-interest ticks are not requested in delayed modes because delayed feeds support a limited generic tick set.

Actual returned broker data type controls each label, not the requested setting. Delayed/frozen prices never count as live readiness. No synthetic fallback occurs. Availability and delay vary by exchange, instrument and account; this setting does not bypass entitlements, guarantee historical-data access, or enable trading. No broker subscriptions or charges are initiated. Error 10197 is specifically a competing trading/market-data session; 10089/354 concern permissions/subscriptions.
