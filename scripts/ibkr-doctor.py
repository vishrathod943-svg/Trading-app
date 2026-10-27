#!/usr/bin/env python3
"""Check a logged-in paper gateway without reading broker credentials or placing orders."""
import argparse
import asyncio
import json
import logging
from ib_async import IB, StartupFetch

async def check(host,port):
    logging.getLogger('ib_async').setLevel(logging.CRITICAL)
    client=IB()
    try:
        await client.connectAsync(host,port,clientId=72,timeout=8,readonly=True,fetchFields=StartupFetch(0))
        print(json.dumps(dict(socket_connected=True,read_only=True,orders_tested=False,market_data_verified=False)))
        print('Gateway login/socket verified only. Check /broker/status and individual feed labels for live-data entitlements.')
    except Exception:
        raise SystemExit('Gateway connection failed. Confirm the official TWS/IB Gateway is running, logged into paper trading, and allows read-only socket clients on the selected port. No orders were sent.') from None
    finally:client.disconnect()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,choices=(4002,7497),default=4002)
    args=p.parse_args();asyncio.run(check(args.host,args.port))
