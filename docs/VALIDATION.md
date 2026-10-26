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
