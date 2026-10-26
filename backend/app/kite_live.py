"""Kite streaming + closed-day scanner. All broker credentials stay on the server."""
import asyncio
import os
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from kiteconnect import KiteConnect, KiteTicker
from twisted.internet import reactor
from .analysis import Candle, indicators, direction_for, trade_plan, major_moves, backtest
from .automation import Automation

IST=ZoneInfo('Asia/Kolkata')
class KiteLive:
    def __init__(self,rules,path,client=None):
        self.rules=rules
        self.api_key=os.getenv('KITE_API_KEY','')
        self.access_token=os.getenv('KITE_ACCESS_TOKEN','')
        self.client=client or KiteConnect(api_key=self.api_key,timeout=10)
        if not client: self.client.set_access_token(self.access_token)
        self.auto=Automation(path,self.client,os.getenv('FO_LIVE_ORDERS','false').lower()=='true')
        self.lock=threading.RLock()
        self.connected=False;self.authenticated=False;self.error=None
        self.instruments=[];self.universe={};self.tokens={};self.quotes={};self.results={}
        self.ticker=None;self.task=None;self.running=False;self.last_tick=None
        self.complete=False;self.scan_errors=0;self.last_reconcile=0
    def start(self):
        self.running=True;self.task=asyncio.create_task(self.run())
    async def stop(self):
        self.running=False;self.auto.pause('Server stopped; re-arm explicitly')
        if self.ticker: self.ticker.close()
        if self.task:
            self.task.cancel()
            try: await self.task
            except asyncio.CancelledError: pass
    def initialize(self):
        profile=self.client.profile()  # Validate existing session; never log profile or tokens.
        self.auto.bind_account(profile['user_id'])
        self.authenticated=True
        self.instruments=self.client.instruments()
        names={x['name'] for x in self.instruments if x.get('instrument_type')=='FUT' and x.get('exchange') in ('NFO','BFO')}
        cash=[x for x in self.instruments if x.get('exchange') in ('NSE','BSE') and x.get('instrument_type')=='EQ' and x['tradingsymbol'] in names]
        # One underlying per symbol, NSE preferred. Coverage explicitly reported.
        for x in sorted(cash,key=lambda x:0 if x['exchange']=='NSE' else 1):
            self.universe.setdefault(x['tradingsymbol'],x)
        if not self.universe: raise ValueError('No derivative-eligible cash instruments found')
        self.tokens={x['instrument_token']:x['exchange']+':'+x['tradingsymbol'] for x in self.universe.values()}
        for x in self.auto.orders():
            if x['state'] not in ('CLOSED','REJECTED'):
                instrument=next((i for i in self.instruments if i['exchange']==x['exchange'] and i['tradingsymbol']==x['contract']),None)
                if instrument: self.tokens[instrument['instrument_token']]=x['exchange']+':'+x['contract']
        if len(self.tokens)>3000: raise ValueError('Single Kite socket instrument limit exceeded')
        self.ticker=KiteTicker(self.api_key,self.access_token,reconnect=True,reconnect_max_tries=50)
        def on_connect(ws,response):
            ws.subscribe(list(self.tokens));ws.set_mode(ws.MODE_FULL,list(self.tokens))
            self.connected=True;self.error=None
        def disconnected(*args):
            self.connected=False;self.auto.pause('Kite disconnected; re-arm after feed recovers')
        self.ticker.on_connect=on_connect
        self.ticker.on_ticks=self.on_ticks
        self.ticker.on_close=disconnected
        self.ticker.on_error=disconnected
        self.ticker.on_noreconnect=disconnected
        self.ticker.connect(threaded=True)  # TLS verification is enabled by default.
    def on_ticks(self,ws,ticks):
        now=datetime.now(IST)
        with self.lock:
            for t in ticks:
                key=self.tokens.get(t['instrument_token'])
                stamp=t.get('exchange_timestamp')
                if not key or stamp is None: continue
                if stamp.tzinfo is None: stamp=stamp.astimezone(IST) # SDK decodes epoch into host-local naive datetime
                else: stamp=stamp.astimezone(IST)
                age=(now-stamp).total_seconds()
                if age< -2 or age>3: continue
                previous=self.quotes.get(key)
                if previous and stamp<datetime.fromisoformat(previous['exchange_time']): continue
                depth=t.get('depth',{});buy=depth.get('buy',[]);sell=depth.get('sell',[])
                self.quotes[key]=dict(price=float(t['last_price']),bid=float(buy[0]['price']) if buy else 0,
                    ask=float(sell[0]['price']) if sell else 0,volume=int(t.get('volume_traded',0)),oi=int(t.get('oi',0)),
                    received=time.monotonic(),exchange_time=stamp.isoformat(),exchange_age=max(age,0))
                self.last_tick=time.monotonic()
    def quote_view(self):
        with self.lock:
            now=time.monotonic()
            return {k:dict(**v,age=round(now-v['received']+v['exchange_age'],3)) for k,v in self.quotes.items()}
    def ready(self):
        return self.authenticated and self.connected and self.complete and self.last_tick is not None and time.monotonic()-self.last_tick<3 and not self.error
    def status(self):
        return dict(mode='kite',authenticated=self.authenticated,feed_connected=self.connected,
            ready=bool(self.ready()),tick_age_ms=round((time.monotonic()-self.last_tick)*1000) if self.last_tick else None,
            universe_count=len(self.universe),analysed_count=len(self.results),scan_complete=self.complete,
            scan_errors=self.scan_errors,error=self.error,
            coverage='Kite derivative-eligible cash underlyings; NSE preferred for duplicate symbols',
            execution='Long CE/PE options, one lot, ATM liquidity filter; no delta/IV feed assumed')
    def scan_symbol(self,symbol,instrument):
        today=datetime.now(IST).date()
        raw=self.client.historical_data(instrument['instrument_token'],today-timedelta(days=550),today,'day')
        candles=[]
        for c in raw:
            stamp=c['date']
            if stamp.date()>=today: continue  # Never confirm from an incomplete daily candle.
            if c['volume']<=0 or not 0<c['low']<=min(c['open'],c['close'])<=max(c['open'],c['close'])<=c['high']: continue
            candles.append(Candle(stamp.date().isoformat(),c['open'],c['high'],c['low'],c['close'],c['volume']))
        candles.sort(key=lambda c:c.time)
        if len(candles)<201: return None
        if (today-datetime.fromisoformat(candles[-1].time).date()).days>5: return None
        i=indicators(candles);direction=direction_for(candles,self.rules);moves=major_moves(candles)
        tests=[backtest(candles,self.rules,n) for n in (5,10,20)];w=self.rules['weights']
        score=round((w['setup'] if direction else 0)+w['volume']*min(i['volume_ratio']/3,1)+w['moves']*min(len(moves)/5,1)+w['backtest']*(tests[1]['win_rate'] or 0)/100)
        confirmed=bool(direction and score>=self.rules['min_score'])
        return dict(symbol=symbol,exchange=instrument['exchange'],sector='Unavailable',price=candles[-1].close,
            change_pct=round(100*(candles[-1].close/candles[-2].close-1),2),score=score,direction=direction or 'WATCH',confirmed=confirmed,
            volume_ratio=round(i['volume_ratio'],2),indicators=i,candles=[c.__dict__ for c in candles[-80:]],major_moves=moves,backtests=tests,
            plan=trade_plan(candles,direction) if confirmed else None,option=None,option_chain=[],fundamentals=None,
            warnings=['Daily setups use completed candles; current tick is separate','Fundamentals, corporate actions and event filters not supplied','No millisecond latency guarantee'],data_as_of=candles[-1].time,mode='kite')
    def contracts(self,setup):
        today=datetime.now(IST).date();typ='CE' if setup['direction']=='LONG' else 'PE'
        price=self.quote_view().get(self.universe[setup['symbol']]['exchange']+':'+setup['symbol'],{}).get('price',setup['price'])
        options=[i for i in self.instruments if i.get('name')==setup['symbol'] and i.get('instrument_type')==typ and i.get('exchange') in ('NFO','BFO') and (i['expiry']-today).days>=10]
        if not options: return []
        expiry=min(i['expiry'] for i in options)
        return sorted([i for i in options if i['expiry']==expiry],key=lambda x:abs(x['strike']-price))[:3]
    def evaluate(self):
        if time.monotonic()-self.last_reconcile>=1:
            self.auto.reconcile() # Protective handling continues when new entries are off.
            self.last_reconcile=time.monotonic()
        if datetime.now(IST).strftime('%H:%M')>='15:00': self.auto.cancel_session_entries()
        close_session=datetime.now(IST).strftime('%H:%M')>='15:15'
        quotes=self.quote_view();self.auto.prices(quotes,close_session)
        if close_session: self.auto.pause('Session closing; exit limits submitted where quotes are fresh; verify broker fills')
        if not self.auto.config.enabled: return
        if not self.ready(): self.auto.pause('Feed stale or scanner not ready');return
        for symbol,setup in list(self.results.items()):
            if not setup['confirmed']: continue
            key=self.universe[symbol]['exchange']+':'+symbol;q=quotes.get(key)
            if not q or q['age']>3: continue
            sign=1 if setup['direction']=='LONG' else -1;entry=setup['plan']['entry']
            if not 0<=sign*(q['price']/entry-1)<=.003: continue # Do not chase breakout gaps.
            for instrument in self.contracts(setup):
                key=instrument['exchange']+':'+instrument['tradingsymbol'];oq=quotes.get(key)
                if oq:
                    contract=dict(**instrument,type=instrument['instrument_type'],days_to_expiry=(instrument['expiry']-datetime.now(IST).date()).days)
                    self.auto.consider(setup,contract,oq,datetime.now(IST),self.ready())
                elif instrument['instrument_token'] not in self.tokens:
                    with self.lock: self.tokens[instrument['instrument_token']]=key
                    reactor.callFromThread(self.ticker.subscribe,[instrument['instrument_token']]);reactor.callFromThread(self.ticker.set_mode,self.ticker.MODE_FULL,[instrument['instrument_token']])
    async def run(self):
        try:
            if not self.api_key or not self.access_token: raise ValueError('Missing server-side Kite credentials')
            await asyncio.to_thread(self.initialize)
            for symbol,instrument in self.universe.items():
                try:
                    result=await asyncio.to_thread(self.scan_symbol,symbol,instrument)
                    if result: self.results[symbol]=result
                    else: self.scan_errors+=1
                except Exception: self.scan_errors+=1
                await asyncio.sleep(.4) # Historical API rate limit; no tight retry loops.
            self.complete=True
            while self.running:
                await asyncio.to_thread(self.evaluate)
                await asyncio.sleep(.25)
        except asyncio.CancelledError: raise
        except Exception:
            self.error='Kite initialization/session failed; check server configuration and broker access'
            self.authenticated=False;self.auto.pause(self.error)
