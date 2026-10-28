"""Read-only IBKR socket adapter. Never submits or modifies broker orders."""
import asyncio
import copy
import logging
import math
import os
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from ib_async import IB, Stock, Future, StartupFetch
from .analysis import Candle
from .us_market import load_watchlist, select_future, build_analysis

REQUEST_TYPES={'live':1,'delayed':3,'delayed_frozen':4}
DATA_TYPES={1:'live',2:'frozen',3:'delayed',4:'delayed_frozen'}

class ResearchOnly:
    def status(self):return dict(enabled=False,mode='research',live_allowed=False,reason='IBKR is read-only: no order submission or automatic execution',orders=[])
    def pause(self,reason):pass

class IBKRLive:
    def __init__(self,rules,client=None):
        self.rules=rules;self.ib=client;self.auto=ResearchOnly()
        self.specs=load_watchlist(os.getenv('IBKR_WATCHLIST_FILE'))
        self.host=os.getenv('IBKR_HOST','127.0.0.1');self.port=int(os.getenv('IBKR_PORT','4002'))
        self.client_id=int(os.getenv('IBKR_CLIENT_ID','71'))
        self.requested_data_type=os.getenv('IBKR_DATA_TYPE','live')
        if self.requested_data_type not in REQUEST_TYPES:raise ValueError('IBKR_DATA_TYPE must be live, delayed or delayed_frozen')
        if self.client_id<=0:raise ValueError('IBKR_CLIENT_ID must be positive; client 0 is not permitted')
        if not 1<=self.port<=65535:raise ValueError('Invalid IBKR port')
        self.results={};self.contracts={};self.tickers={};self.quotes={};self.by_id={}
        self.lock=threading.RLock();self.connected=False;self.complete=False
        self.error='Waiting for logged-in TWS or IB Gateway';self.errors={};self.scan_errors=0
        self.running=False;self.task=None;self.last_tick=None;self.last_refresh=None
    def start(self):
        self.running=True;self.task=asyncio.create_task(self.run())
    async def stop(self):
        self.running=False
        if self.task:
            self.task.cancel()
            try:await self.task
            except asyncio.CancelledError:pass
        if self.ib:self.ib.disconnect()
        self.connected=False
    def on_disconnect(self,*args):
        with self.lock:
            self.connected=False;self.complete=False;self.quotes.clear();self.last_tick=None
            self.error='IBKR disconnected. Restore the logged-in read-only gateway; reconnect is automatic.'
    def on_error(self,req_id,code,message,contract=None):
        # Never publish raw broker messages, which may include account identifiers.
        if code in (2104,2106,2107,2108,2158):return
        if code==1100:self.on_disconnect();return
        cid=getattr(contract,'conId',None)
        if code==10197:
            reason='Competing IBKR trading session: end other live/paper market-data sessions using this username'
        elif code in (354,10167,10168,10089,10090):
            reason='Live market-data entitlement unavailable or session restricted; check broker subscriptions before paying'
        elif code in (162,165,166):reason='Historical data unavailable, pacing limited, or instrument expired'
        elif code==200:reason='Contract could not be qualified'
        else:reason='Broker request failed; check gateway status'
        with self.lock:
            self.errors[str(cid or req_id)]=dict(code=code,reason=reason)
    @staticmethod
    def number(value,positive=False):
        try:value=float(value)
        except (TypeError,ValueError):return None
        if not math.isfinite(value) or (positive and value<=0) or value<0:return None
        return value
    def on_tickers(self,tickers):
        now=datetime.now(timezone.utc)
        with self.lock:
            for t in tickers:
                cid=int(t.contract.conId);key=self.by_id.get(cid)
                if not key:continue
                stamp=t.time
                if not isinstance(stamp,datetime):continue
                if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc)
                age=(now-stamp).total_seconds()
                if age< -2 or age>15:continue
                prev=self.quotes.get(key)
                if prev and stamp<datetime.fromisoformat(prev['exchange_time']):continue
                bid=self.number(t.bid,True);ask=self.number(t.ask,True);last=self.number(t.last,True)
                price=last;source='last'
                if price is None and bid is not None and ask is not None and ask>=bid:
                    price=(bid+ask)/2;source='midpoint'
                dtype=DATA_TYPES.get(t.marketDataType,'unknown')
                self.quotes[key]=dict(price=price,bid=bid,ask=ask,volume=self.number(t.volume),oi=self.number(getattr(t,'futuresOpenInterest',None)),
                    data_type=dtype,price_source=source if price is not None else 'unavailable',
                    received=time.monotonic(),base_age=max(age,0),exchange_time=stamp.isoformat(),timestamp_basis='broker_receive')
                self.last_tick=time.monotonic()
    def quote_view(self):
        with self.lock:
            now=time.monotonic()
            return {k:dict(**v,age=round(v['base_age']+now-v['received'],3)) for k,v in self.quotes.items()}
    def ready(self):
        return bool(self.connected and self.complete and any(q['data_type']=='live' and q['price'] is not None and q['age']<15 for q in self.quote_view().values()))
    def status(self):
        quotes=self.quote_view();types={t:sum(q['data_type']==t for q in quotes.values()) for t in DATA_TYPES.values()}
        return dict(mode='ibkr',market='US',currency='USD',authenticated=self.connected,feed_connected=self.connected,
            ready=self.ready(),requested_data_type=self.requested_data_type,read_only=True,orders_enabled=False,universe_count=len(self.specs),analysed_count=sum(bool(x['indicators']) for x in self.results.values()),
            qualified_count=len(self.contracts),scan_complete=self.complete,scan_errors=self.scan_errors,
            tick_age_ms=round((time.monotonic()-self.last_tick)*1000) if self.last_tick else None,
            data_types=types,error=self.error,request_errors=list(self.errors.values())[-10:],
            coverage='Configured US-stock / CME-index-futures watchlist; not the entire market',
            timestamp_basis='broker_receive',execution='Research only; real and broker-paper orders disabled')
    async def qualify(self,spec):
        requested=Stock(spec.symbol,'SMART','USD') if spec.security_type=='STK' else Future(symbol=spec.symbol,exchange=spec.exchange,currency='USD')
        details=await self.ib.reqContractDetailsAsync(requested)
        if spec.security_type=='FUT':d=select_future(details,spec.symbol,datetime.now(ZoneInfo('America/Chicago')).date())
        else:
            matches=[d for d in details if d.contract.secType=='STK' and d.contract.symbol==spec.symbol and d.contract.currency=='USD']
            if len(matches)!=1:raise ValueError('Ambiguous stock contract')
            d=matches[0]
        c=d.contract
        multiplier=float(c.multiplier or 1) if spec.security_type=='FUT' else 1.0
        if multiplier<=0 or not math.isfinite(multiplier) or not d.minTick>0:raise ValueError('Broker contract metadata incomplete')
        meta=dict(symbol=spec.symbol,security_type=spec.security_type,exchange=spec.exchange,currency='USD',sector=spec.sector,
            con_id=int(c.conId),local_symbol=c.localSymbol or spec.symbol,multiplier=multiplier,min_tick=float(d.minTick),tick_value=round(multiplier*d.minTick,4),
            expiry=c.lastTradeDateOrContractMonth if spec.security_type=='FUT' else None,
            timezone=getattr(d,'timeZoneId',''),liquid_hours=getattr(d,'liquidHours',''))
        return c,meta
    async def refresh(self):
        self.complete=False;self.scan_errors=0;self.errors={}
        for spec in self.specs:
            try:
                contract,meta=await self.qualify(spec)
                old=self.contracts.get(spec.symbol)
                if old and old.conId!=contract.conId:
                    self.ib.cancelMktData(old)
                    with self.lock:
                        self.quotes.pop(spec.exchange+':'+spec.symbol,None);self.by_id.pop(old.conId,None)
                self.contracts[spec.symbol]=contract
                self.by_id[int(contract.conId)]=spec.exchange+':'+spec.symbol
                self.results[spec.symbol]=build_analysis(spec.symbol,meta,[],self.rules)
                if not old or old.conId!=contract.conId:
                    self.tickers[spec.symbol]=self.ib.reqMktData(contract,genericTickList='588' if spec.security_type=='FUT' and self.requested_data_type=='live' else '',snapshot=False,regulatorySnapshot=False)
                bars=await self.ib.reqHistoricalDataAsync(contract,endDateTime='',durationStr='2 Y',barSizeSetting='1 day',
                    whatToShow='ADJUSTED_LAST' if spec.security_type=='STK' else 'TRADES',useRTH=spec.security_type=='STK',formatDate=2,timeout=20)
                today=datetime.now(ZoneInfo('America/New_York' if spec.security_type=='STK' else 'America/Chicago')).date()
                unique={}
                for b in bars:
                    day=b.date.date() if isinstance(b.date,datetime) else b.date
                    if day>=today:continue
                    values=[float(x) for x in (b.open,b.high,b.low,b.close,b.volume)]
                    if not all(math.isfinite(x) and x>0 for x in values):continue
                    if not b.low<=min(b.open,b.close)<=max(b.open,b.close)<=b.high:continue
                    unique[day]=Candle(day.isoformat(),b.open,b.high,b.low,b.close,float(b.volume))
                candles=[unique[d] for d in sorted(unique)]
                self.results[spec.symbol]=await asyncio.to_thread(build_analysis,spec.symbol,meta,candles,self.rules)
                if len(candles)<201:self.scan_errors+=1
            except asyncio.CancelledError:raise
            except Exception:
                self.scan_errors+=1
                if spec.symbol in self.results:self.results[spec.symbol]['warnings'].append('Historical/qualification request failed or timed out; current quotes may still be available')
            await asyncio.sleep(1) # Conservative pacing; never issue retry storms.
        self.complete=True;self.last_refresh=datetime.now(ZoneInfo('America/New_York')).date()
    async def run(self):
        logging.getLogger('ib_async').setLevel(logging.CRITICAL)
        if self.ib is None:self.ib=IB()
        self.ib.pendingTickersEvent+=self.on_tickers
        self.ib.disconnectedEvent+=self.on_disconnect
        self.ib.errorEvent+=self.on_error
        wait=2
        try:
            while self.running:
                try:
                    if not self.ib.isConnected():
                        self.contracts={};self.tickers={};self.by_id={};self.quotes={}
                        await self.ib.connectAsync(self.host,self.port,clientId=self.client_id,timeout=8,readonly=True,fetchFields=StartupFetch(0))
                        self.connected=True;self.error=None;wait=2
                        self.ib.reqMarketDataType(REQUEST_TYPES[self.requested_data_type]) # Actual broker response type remains authoritative.
                        await self.refresh()
                    today=datetime.now(ZoneInfo('America/New_York')).date()
                    if today!=self.last_refresh:await self.refresh()
                    await asyncio.sleep(2)
                except asyncio.CancelledError:raise
                except Exception:
                    self.error='Cannot connect/synchronise with TWS or IB Gateway. Check login, API enablement, host and paper socket port.'
                    self.connected=False;self.complete=False
                    if self.ib.isConnected():self.ib.disconnect()
                    await asyncio.sleep(wait);wait=min(wait*2,60)
        finally:
            self.ib.pendingTickersEvent-=self.on_tickers
            self.ib.disconnectedEvent-=self.on_disconnect
            self.ib.errorEvent-=self.on_error
            self.ib.disconnect();self.connected=False
