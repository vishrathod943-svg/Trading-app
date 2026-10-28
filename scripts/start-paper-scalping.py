#!/usr/bin/env python3
"""Arm a local delayed-only simulation; no broker orders or credentials requested."""
import argparse
import json
from pathlib import Path
import urllib.request
import urllib.error

p=argparse.ArgumentParser(description='Start the $1,000 delayed paper monitor, not real trading')
p.add_argument('--symbol',default='ALL')
p.add_argument('--timeframe',choices=('5m','15m'),default='5m')
a=p.parse_args()
path=Path.home()/'compass-private/us.env'
try:
    values={}
    for line in path.read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k,v=line.split('=',1);values[k.strip()]=v.strip().strip('\"\'')
    if values.get('FO_MODE')!='ibkr' or values.get('IBKR_DATA_TYPE')!='delayed':raise ValueError('Configure IBKR delayed mode first')
    token=values['FO_API_TOKEN']
    body=json.dumps(dict(enabled=True,symbol=a.symbol.upper(),timeframe=a.timeframe,capital=1000,risk_pct=.5,rr=2)).encode()
    request=urllib.request.Request('http://127.0.0.1:8000/paper-auto',data=body,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=15) as r:result=json.load(r)
    if not result.get('simulation') or result.get('orders_enabled'):raise ValueError('Unexpected simulation status')
    print('DELAYED PAPER MONITOR ARMED: $1,000 virtual balance, max 0.5% risk, $20 daily loss limit.')
    print('No broker orders sent. '+result.get('reason',''))
except urllib.error.HTTPError as e:
    try:message=json.load(e).get('detail','Request rejected')
    except (ValueError,AttributeError):message='Request rejected'
    raise SystemExit(f'Could not arm paper monitor: HTTP {e.code}. {message}')
except (OSError,ValueError,KeyError):raise SystemExit('Could not arm paper monitor. Check private delayed settings, backend and qualified symbol. No broker orders sent.')
