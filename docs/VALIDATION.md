# Verified in the cloud workspace

- Backend: `cd backend && ../.venv/bin/python -m pytest -q` — **13 passed**. The runner emitted one dependency deprecation warning from Starlette/AnyIO.
- Backend startup: `./scripts/backend.sh` — server started and was restarted successfully with persistent SQLite data.
- HTTP smoke checks: health reports demo/disconnected-feed status; scan returns eight synthetic symbols; stock details include candles; isolated replay reaches T2_HIT with entry/T1/T2 events; replay fills produce paper P&L; invalid candle range returns HTTP 422.
- WebSocket smoke check: `/live` returned a snapshot with eight symbols, trades and events.
- Android bootstrap: `python scripts/bootstrap-android-cloud.py` — passed repeat invocation. Downloaded toolchains were checked against pinned artifact checksums; TLS verification remained enabled.
- Android build and lint: `./scripts/android-build.sh lintDebug` — **BUILD SUCCESSFUL**, lint **0 errors, 1 warning**. The remaining warning suggests an additional legacy fullBackupContent attribute; allowBackup is already false and Android 12+ has explicit data-extraction exclusions.
- Final APK: Android API 26 minimum / API 35 target, launchable MainActivity, signature verified with Android SDK apksigner. Bundled scan and all eight stock detail snapshots confirmed present inside the final APK.

Not run: Android emulator/physical-device or instrumented UI tests, Docker execution, GitHub-hosted CI, live market/broker integration, FCM delivery, production/load tests, cloud snapshot publication or restoration into a fresh task. A successful compile and lint run do not establish device behavior or production readiness.
