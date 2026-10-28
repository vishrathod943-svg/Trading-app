# v0.3 US research validation

- Backend: **62 tests passed**, one Starlette/AnyIO dependency deprecation warning. Includes prior India behavior plus US contract qualification, ambiguity/expiry rejection, read-only lifecycle, delayed/frozen/unknown/stale quote handling, absent-price handling, sanitized broker errors, private US configuration, futures tick alignment and multiplier-aware risk/P&L, protected APIs and browser WebSocket authentication. Early sandbox-restricted runs were interrupted and are not counted as passes; the completed run used the socket permissions required by async tests.
- Android: **0.3.0 / version code 3**, API 26 minimum / API 35 target, debug signature verified, **BUILD SUCCESSFUL** with lint **0 errors / 3 warnings**. Confirmed the packaged APK contains 12 US synthetic scan records and all 12 detail assets. No Android emulator/physical device test was run.
- Browser: actual Chromium run at a 390×844 viewport passed authenticated connection, 12-instrument rendering, four-future filtering, MES details, USD/multiplier-aware risk calculation, search, empty URL query (no token in URL), and zero JavaScript page errors. Screenshot in `docs/images/us-research-mobile.png` is synthetic data. This validates responsive Chromium, not actual iOS Safari hardware.
- Static/configuration: JavaScript syntax, shell bootstrap syntax and Docker Compose US configuration validated. Private configuration and gateway doctor CLI help run. The Ubuntu provisioning/bootstrap was not executed on a new AWS instance.
- Container: backend image built with TLS verification enabled (optional public CA-bundle BuildKit secret in this proxied cloud). `us_demo` passed authentication, public dashboard route, 12-instrument scan, MES metadata, futures risk estimate, USD synthetic replay and WebSocket checks. `ibkr` without a gateway remained not-ready with no synthetic fallback, exposed read-only status, and rejected automation even with `FO_LIVE_ORDERS=true` in the container environment. Both test containers were removed after testing.
- Gateway/account/market data: **not verified**. No official IB Gateway/TWS was installed or logged in here, no IBKR credentials were supplied, and no live/delayed broker feed was received. Mocked quotes are never described as actual broker validation. Real and broker-paper IBKR order submission are not implemented.
- Hosting: no replacement AWS instance, static IP, DNS change, TLS certificate or billing action was performed. Credit eligibility remains a user/account check. Old deleted-server IP/DNS must not be reused without correct reconfiguration. Cloud publication/restoration into a new task and GitHub-hosted CI outcomes are not claimed.

The sections below retain earlier-release evidence for the India/Kite workflow.

# v0.2 validation in this cloud workspace

- Backend: `cd backend && ../.venv/bin/python -m pytest -q` — **31 passed**, one Starlette/AnyIO dependency deprecation warning.
- Coverage includes causal indicators, risk sizing, paper lifecycle/persistence, duplicate ticks, gap/stop-first behavior, rule validation, REST/WebSocket contracts, authentication, real-data mode without synthetic fallback, daily-loss limits, full-premium option sizing, liquidity/expiry checks, concurrent duplicate signals, timeout reconciliation without repeated entry submissions, protection rejection/emergency intent, partial fills, account binding, session cancellation and target reuse of the same exit order.
- Kite SDK timestamp regression: current host-local naive timestamps are converted correctly to IST; old/missing/out-of-order ticks are rejected. The SDK's installed timestamp-decoding implementation was inspected; **no live broker ticks were received**.
- Android: `./scripts/android-build.sh lintDebug` — **BUILD SUCCESSFUL**. Version 0.2.0 / code 2, Android API 26 minimum / API 35 target. Lint: **0 errors, 3 warnings** (one legacy-backup attribute suggestion and two SharedPreferences KTX style suggestions in encrypted token storage). APK signature verified using Android SDK `apksigner`.
- Compose: live deployment configuration validated by Docker Compose with explicitly dummy, noncredential settings and `config --quiet`.
- Docker backend image built successfully. This cloud's TLS proxy required the optional **public** CA-bundle BuildKit secret; certificate verification remained enabled. Non-root source ownership and default automation database location were corrected after startup testing found permission issues.
- Container smoke tests: demo health, eight-symbol scan and replay to T2 passed; Kite mode with intentionally missing broker credentials required authentication, reported not-ready, returned no synthetic scan items and left automation disarmed. No broker login or live order submission occurred.
- Daily-login CLI `--help` runs. Actual session exchange is not tested.

Not verified: real Kite authentication/market-data permissions, live tick accuracy, exchange instruments/contract selection against an actual account, real orders/fills/protection, hosted VM/DNS/HTTPS deployment, Caddy certificate issuance, actual broker token expiry/reconnects, overnight handling, Android device/emulator/UI tests, push delivery, operator escalation, high availability/load capacity, GitHub-hosted CI outcomes or cloud snapshot restoration. Broker doubles and container checks do not establish production-ready unattended trading.

Docker build command used in this proxied cloud:

```bash
BUILDX_CONFIG=/workspace/toolchains/buildx docker build \
  --secret id=build_ca,src=/etc/ssl/certs/ca-certificates.crt \
  -t fo-compass:0.2 backend
```

Normal non-proxied servers can omit the optional CA secret. Never use `--trusted-host`, disable TLS or replace expected artifact checksums to make setup pass.

Callback follow-up: the focused public-callback test passes, verifying a non-reflecting, no-store landing page and continued authentication on broker endpoints. Live Compose also validates with an empty access token for initial HTTPS/login bootstrap. Actual hosted redirect and broker session exchange remain unverified.

Editor-free configuration helper: 3 focused tests pass for private file creation, token preservation, input rejection without file overwrite, and symlink rejection. Only synthetic test credentials were used.

Daily-login mobile follow-up: focused tests cover extraction of a token from the full expected HTTPS redirect URL or raw input; reject wrong-host, duplicate/missing token, failed status, embedded credentials and fragments; and verify diagnostic messages never echo exception contents. Real broker session exchange remains unverified.


## Intraday ICT update · 28 October 2026

- 69 backend tests passed, including completed UTC bar filtering, zero-volume acceptance, cache reuse, disconnect rejection, sanitized broker-history errors, chart authentication and timeframe validation. Broker requests use test doubles; no real broker connection or order submission occurred.
- Android assembleDebug and lintDebug passed. Version 0.3.1/code 4 adds timeframe controls and completed-bar ICT overlays.
- Chromium at a 390 × 844 mobile viewport passed all five timeframe selections, synthetic labels and overlay toggle with no JavaScript page exceptions. Screenshot: `docs/images/intraday-mobile.png`. Actual Safari/iOS and physical Android remain untested.
- This update is source/APK preparation, not AWS provisioning or a verified live-data deployment. Charts poll cached historical bars, not millisecond streaming candles.


## Optional phone desktop HTTPS proxy

Two focused tests pass for bcrypt-only private configuration, mode 600, symlink rejection and password length validation. Combined Compose preserves literal bcrypt dollars and replaces only the Caddyfile mount. Caddy 2.10.0 validates the config. A temporary local Caddy container verified unauthenticated/wrong-password desktop requests and unauthenticated WebSocket paths return 401, valid credentials proxy the stripped desktop path with no-store headers, and `/app` routing remains intact. No real desktop, phone browser, broker login or user server was accessed in these checks. The opt-in helper requires loopback listeners and leaves real trading disabled.


## Selectable delayed IBKR data

75 backend tests pass. New checks verify requested IBKR market-data type 3/4, actual delayed labels, false live readiness for delayed ticks, read-only socket initialization, omission of unsupported generic futures ticks in delayed mode, private-token preservation, persistent feed selection, and distinct sanitized competing-session errors. Compose configuration and browser JavaScript syntax validate. Tests use broker doubles; availability of delayed quotes on the user's account is not verified here. No subscription or broker order was initiated.
