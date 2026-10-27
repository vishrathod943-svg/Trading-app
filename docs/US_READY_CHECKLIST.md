# Handoff checklist

Ready in source: USD research model; 12-instrument synthetic demo; read-only IBKR adapter; per-instrument live/delayed/frozen labels; futures expiry/multiplier/tick metadata; multiplier-aware synthetic P&L and risk estimate; Android US dataset; iPhone browser dashboard; authenticated REST/WebSocket support; private deployment configuration; Ubuntu bootstrap; gateway connectivity doctor; automated checks.

Still requires the user: confirmation that AWS credits cover the intended server; creation/access to the new VM; NEW static IP and DNS update; official IB Gateway/TWS installation in an available computer or secured server desktop; login/2FA; paper/API/data entitlements; hosted TLS and live feed verification. No AWS instance, IBKR account login, subscription, deposit, or order was performed by the coding agent.

Not included: actual IBKR order execution or broker paper orders, automated cloud purchasing, a preinstalled graphical IB Gateway desktop, whole-US-market scanning, US options data, production high availability or instrumented Android device testing.

Use `US_START_HERE.md` for the exact staged procedure. Start with synthetic `us_demo`; do not switch to IBKR until its gateway prerequisite is met. Never use the deleted AWS instance's old IP.
