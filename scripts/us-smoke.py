#!/usr/bin/env python3
"""Unauthenticated local synthetic demo functional check. No broker connection."""
import json
from urllib.request import urlopen, Request
import argparse

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8000);args=p.parse_args()
    def get(path,data=None):
        return json.load(urlopen(Request(f'http://127.0.0.1:{args.port}'+path,data=data,headers={'Content-Type':'application/json'}),timeout=90))
    health=get('/health')
    if health['mode']!='us_demo':raise SystemExit('Refusing to mutate paper state outside synthetic us_demo mode')
    scan=get('/scan');assert len(scan['items'])==12 and scan['currency']=='USD'
    detail=get('/stock/MES');assert detail['contract']['multiplier']==5
    replay=get('/replay/demo',b'{}');assert replay['trade']['state']=='T2_HIT' and replay['trade']['pnl']==75
    print('US synthetic functional checks passed: 12 instruments, contract metadata, USD/multiplier-aware replay. No real data or orders verified.')
