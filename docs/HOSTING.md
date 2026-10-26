# Hosting recommendation: AWS Lightsail, Mumbai

Use a single always-on **Ubuntu 24.04 LTS, x86_64 server with 2 vCPUs and 4 GB RAM**, an attached static public IPv4 address, and a hostname you control. Check the current Lightsail price and account charges before purchasing; this repository does not create or bill for cloud resources. This size is a starting point for one account, not a tested capacity guarantee. Mumbai reduces one geographical leg of latency; broker/exchange latency is still outside the app's control.

1. Create/sign in to your own AWS account and open Lightsail. Create a Linux/Unix Ubuntu instance in Mumbai. Keep account billing alerts enabled as appropriate for your account.
2. Attach a Lightsail static IP so the server address survives restarts. Configure any IP registration required by your Kite application with Zerodha using that address.
3. Allow HTTPS (443) and certificate issuance HTTP (80) inbound. Restrict SSH (22) to your own IP where possible. Don't expose port 8000 to the Internet.
4. Create a DNS A record, for example `trading.your-domain.com`, pointing to the static IP. Configure/remove AAAA records consistently with the server's actual IPv6 connectivity.
5. Connect through the Lightsail browser SSH terminal or your own SSH client. Do not paste SSH private keys, passwords or broker secrets into chat. Install Git and Docker Engine/Compose using the official Ubuntu instructions: https://docs.docker.com/engine/install/ubuntu/ .
6. Clone `https://github.com/vishrathod943-svg/Trading-app.git` and follow `docs/LIVE_SETUP.md`. Keep the actual environment file outside the checkout and mode 600. Start with `FO_LIVE_ORDERS=false`.
7. Launch the deployment, then check container state (`docker compose ... ps`), HTTPS, authenticated broker status and the historical warm-up count. The broker session must actually work; an online server alone does not establish live data access. Do not print expanded Compose configuration because it can contain credentials; use `config --quiet` for syntax checks.
8. Put the HTTPS hostname and backend access token in Android Settings, enable **Require real Kite data**, and save. Observe live prices/timestamps first, then test paper automation. Only consider live orders after actual broker rejection/reconnect/fill/protection behavior has been verified.

The VPS continues running if the phone is closed. A Lightsail VM, domain, valid daily Kite session and operator availability for failures are still required. The current release does not provide redundant servers, an alert escalation service or guaranteed overnight protection. See the real-order limits in `LIVE_SETUP.md`. Server creation, Docker deployment, certificates and broker login have not been performed by this chat.
