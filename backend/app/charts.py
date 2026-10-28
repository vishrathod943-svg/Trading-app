"""Bounded, completed-bar research charts. Broker history never falls back to demo."""
import asyncio
import math
import random
import time
from datetime import datetime, timezone
from .ict import analyse_ict

TIMEFRAMES={'1m':(60,'1 min','1 D'),'5m':(300,'5 mins','3 D'),'15m':(900,'15 mins','1 W'),'1h':(3600,'1 hour','2 W')}

def clean_bars(bars, seconds, now):
    unique={}
    for b in bars:
        stamp=b.date
        if not isinstance(stamp,datetime) or stamp.tzinfo is None:continue
        stamp=stamp.astimezone(timezone.utc)
        if stamp.timestamp()+seconds>now.timestamp():continue
        values=[float(getattr(b,k)) for k in ('open','high','low','close','volume')]
        o,h,l,c,v=values
        if not all(math.isfinite(x) for x in values) or min(o,h,l,c)<=0 or v<0 or not l<=min(o,c)<=max(o,c)<=h:continue
        unique[stamp]=dict(time=stamp.isoformat(),open=o,high=h,low=l,close=c,volume=v)
    return [unique[t] for t in sorted(unique)][-240:]

def payload(symbol,timeframe,candles,source,**extra):
    ict=analyse_ict(candles,timeframe=timeframe)
    return dict(symbol=symbol,timeframe=timeframe,candles=candles,ict=ict,source=source,
        completed_only=True,fetched_at=datetime.now(timezone.utc).isoformat(),
        last_bar=candles[-1]['time'] if candles else None,
        warning='Completed historical bars; refreshed at most once per minute. Quotes are separate. Historical bars do not verify live-data entitlements. No latency guarantee.',**extra)

def demo_chart(symbol,timeframe,anchor):
    seconds=TIMEFRAMES[timeframe][0];end=int(time.time()//seconds)*seconds
    rng=random.Random(symbol+timeframe+str(end));price=anchor;candles=[]
    for i in range(240):
        o=price;price=max(.01,o*(1+rng.gauss(0,.0015)));pad=max(o,price)*rng.uniform(.0001,.001)
        candles.append(dict(time=datetime.fromtimestamp(end-(240-i)*seconds,timezone.utc).isoformat(),open=o,high=max(o,price)+pad,low=max(.00001,min(o,price)-pad),close=price,volume=rng.randint(100,50000)))
    return payload(symbol,timeframe,candles,'synthetic',warning_demo='SYNTHETIC: arbitrary simulated bars, including non-market hours; not exchange history')

class BrokerCharts:
    def __init__(self):self.cache={};self.lock=asyncio.Lock();self.next_request=0
    async def get(self,service,symbol,timeframe):
        if not service.connected or not service.ib.isConnected():raise ValueError('Gateway disconnected; broker chart unavailable')
        contract=service.contracts.get(symbol)
        if not contract:raise ValueError('Contract not qualified yet')
        key=(contract.conId,timeframe)
        async with self.lock:
            cached=self.cache.get(key)
            if cached and time.monotonic()-cached[0]<60:
                if isinstance(cached[1],str):raise ValueError(cached[1])
                return cached[1]
            # Limit aggregate historical requests, including rapid timeframe changes.
            if time.monotonic()<self.next_request:raise ValueError('Historical request pacing: wait a few seconds and retry')
            self.next_request=time.monotonic()+3
            try:
                seconds,size,duration=TIMEFRAMES[timeframe]
                bars=await service.ib.reqHistoricalDataAsync(contract,endDateTime='',durationStr=duration,barSizeSetting=size,whatToShow='TRADES',useRTH=False,formatDate=2,timeout=20)
                if not service.connected or service.contracts.get(symbol) is not contract:raise ValueError('Connection or contract changed; retry chart')
                candles=clean_bars(bars,seconds,datetime.now(timezone.utc))
                if not candles:raise ValueError('No completed broker bars returned; check permissions and historical-data availability')
                result=payload(symbol,timeframe,candles,'ibkr_historical',regular_hours_only=False)
            except asyncio.CancelledError:raise
            except Exception:
                result='Broker chart unavailable. Check historical-data permissions, gateway and pacing; no simulated fallback.'
            if len(self.cache)>=160:self.cache.pop(next(iter(self.cache)))
            self.cache[key]=(time.monotonic(),result)
            if isinstance(result,str):raise ValueError(result)
            return result
