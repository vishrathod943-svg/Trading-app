import asyncio
import os
from threading import RLock
from contextlib import asynccontextmanager
import secrets
import re
from pathlib import Path
from urllib.parse import urlsplit
from fastapi.responses import JSONResponse, PlainTextResponse, FileResponse
from .automation import AutoConfig
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .analysis import DEFAULT_RULES, indicators, direction_for, major_moves, backtest, trade_plan, position_size
from .provider import DemoProvider, USDemoProvider, UNIVERSE, US_UNIVERSE
from .us_market import build_analysis, futures_risk
from .charts import BrokerCharts, TIMEFRAMES, demo_chart
from .ict import analyse_ict
from .engine import Engine
from .rules import load_rules

DEFAULT_RULES = load_rules()

MODE=os.getenv('FO_MODE','demo')
if MODE not in ('demo','kite','us_demo','ibkr'): raise RuntimeError('FO_MODE must be demo, us_demo, kite or ibkr')
API_TOKEN=os.getenv('FO_API_TOKEN','')
if MODE in ('kite','ibkr') and len(API_TOKEN)<32: raise RuntimeError('Broker modes require a random FO_API_TOKEN of at least 32 characters')
provider=USDemoProvider() if MODE=='us_demo' else DemoProvider()
market_universe=US_UNIVERSE if MODE=='us_demo' else UNIVERSE
engine=Engine(os.getenv('FO_DATABASE','screener.db'))
service=None
if MODE=='kite':
    from .kite_live import KiteLive
    service=KiteLive(DEFAULT_RULES,os.getenv('FO_AUTO_DATABASE','automation.db'))
elif MODE=='ibkr':
    from .ibkr_live import IBKRLive
    service=IBKRLive(DEFAULT_RULES)

@asynccontextmanager
async def lifespan(app):
    if service: service.start()
    yield
    if service: await service.stop()

app=FastAPI(title='F&O Compass',version='0.3.1',lifespan=lifespan,
    description='Single-account Kite streaming and guarded option automation; demo remains available.')

@app.middleware('http')
async def authenticate(request,call_next):
    if not (request.method=='GET' and request.url.path in ('/kite/callback','/app','/app/','/app.js','/app.css')) and API_TOKEN and not secrets.compare_digest(request.headers.get('authorization',''), 'Bearer '+API_TOKEN):
        return JSONResponse(status_code=401,content={'detail':'Backend authentication required'})
    return await call_next(request)

cache={}
analysis_lock=RLock()
def analyse(symbol):
    if service:
        result=service.results.get(symbol)
        if not result: raise HTTPException(404,'Symbol not analysed yet or history unavailable')
        return result
    with analysis_lock:
        return _analyse(symbol)

def _analyse(symbol):
    if symbol in cache: return cache[symbol]
    if MODE=='us_demo':
        if symbol not in {x[0] for x in US_UNIVERSE}:raise HTTPException(404,'Unknown US demo symbol')
        result=build_analysis(symbol,provider.metadata(symbol),provider.history(symbol),DEFAULT_RULES,mode='us_demo')
        result['warnings'].insert(0,'SYNTHETIC US DEMO: all prices, volumes and setups are simulated')
        result['data_type']='synthetic';cache[symbol]=result;return result
    metadata=next((x for x in UNIVERSE if x[0]==symbol),None)
    if not metadata: raise HTTPException(404,'Unknown demo symbol')
    candles=provider.history(symbol); i=indicators(candles); direction=direction_for(candles,DEFAULT_RULES)
    bt=[backtest(candles,DEFAULT_RULES,h) for h in (5,10,20)]; moves=major_moves(candles)
    # Missing fundamentals and insufficient backtests contribute zero, never guessed points.
    weights=DEFAULT_RULES['weights']
    score=round((weights['setup'] if direction else 0)+weights['volume']*min(i['volume_ratio']/3,1)+weights['moves']*min(len(moves)/5,1)+(weights['backtest']*(bt[1]['win_rate'] or 0)/100))
    confirmed=bool(direction and score>=DEFAULT_RULES['min_score'])
    result=dict(symbol=symbol,sector=metadata[1],exchange=metadata[2],price=candles[-1].close,
        change_pct=round(100*(candles[-1].close/candles[-2].close-1),2),direction=direction or 'WATCH',score=score,
        confirmed=confirmed,volume_ratio=round(i['volume_ratio'],2),indicators={k:round(v,3) for k,v in i.items()},
        candles=[c.__dict__ for c in candles[-80:]],major_moves=moves,backtests=bt,
        plan=trade_plan(candles,direction) if confirmed else None,option=None,option_chain=[],fundamentals=None,
        warnings=['Synthetic history: not live or tradable','Fundamentals and licensed option chain unavailable','Historical sample may be insufficient'],
        data_as_of=candles[-1].time,mode='demo')
    cache[symbol]=result; return result

@app.get('/health')
def health(): return dict(status='ok',mode=MODE,feed_connected=bool(service and service.connected),push_configured=False,universe=service.status() if service else ('12 synthetic US stocks/index futures' if MODE=='us_demo' else '8 synthetic NSE symbols; BSE not connected'),time=datetime.now(timezone.utc).isoformat())
@app.get('/scan')
def scan(min_score:float=Query(0,ge=0,le=100),exchange:str|None=None,sector:str|None=None,direction:str|None=None):
    items=list(service.results.values()) if service else [analyse(s) for s,_,_ in market_universe]
    quotes=service.quote_view() if service else {}
    overlaid=[]
    for item in items:
        row=dict(item);q=quotes.get(item['exchange']+':'+item['symbol'])
        if q:
            row.update(tick_age_ms=round(q['age']*1000),data_type=q.get('data_type','live'),bid=q.get('bid'),ask=q.get('ask'),price_as_of=q.get('exchange_time'),timestamp_basis=q.get('timestamp_basis','exchange'))
            if q['price'] is not None:row.update(price=q['price'],price_source=q.get('price_source','last'))
        overlaid.append(row)
    items=overlaid
    filtered=[x for x in items if x['score']>=min_score and (not exchange or x['exchange']==exchange) and (not sector or x['sector']==sector) and (not direction or x['direction']==direction)]
    confirmed=[x for x in items if x['confirmed']]
    return dict(items=[{k:v for k,v in x.items() if k not in ('candles','major_moves','backtests','indicators')} for x in filtered],
        confirmed_count=len(confirmed),average_score=round(sum(x['score'] for x in confirmed)/len(confirmed),1) if confirmed else 0,
        advances=sum((x.get('change_pct') or 0)>0 for x in items),declines=sum((x.get('change_pct') or 0)<0 for x in items),mode=MODE,market='US' if MODE in ('us_demo','ibkr') else 'India',currency='USD' if MODE in ('us_demo','ibkr') else 'INR',updated_at=datetime.now(timezone.utc).isoformat())
@app.get('/stock/{symbol}')
def stock(symbol:str):
    result=dict(analyse(symbol.upper()))
    if service:
        q=service.quote_view().get(result['exchange']+':'+result['symbol'])
        if q:
            result.update(data_type=q.get('data_type','live'),bid=q.get('bid'),ask=q.get('ask'),tick_age_ms=round(q['age']*1000),price_as_of=q.get('exchange_time'),timestamp_basis=q.get('timestamp_basis','exchange'))
            if q['price'] is not None: result.update(price=q['price'],price_source=q.get('price_source','last'))
    result['ict']=analyse_ict(result.get('candles',[]))
    return result
chart_service=BrokerCharts()
@app.get('/chart/{symbol}')
async def chart(symbol:str,timeframe:str=Query('5m',pattern='^(1m|5m|15m|1h|1D)$')):
    symbol=symbol.upper()
    if timeframe=='1D':
        result=stock(symbol)
        return dict(symbol=symbol,timeframe='1D',candles=result['candles'],ict=result['ict'],source='synthetic' if MODE in ('demo','us_demo') else 'broker_daily_history',completed_only=True,warning='Completed daily bars; current quotes are separate.')
    if MODE=='ibkr':
        try:return await chart_service.get(service,symbol,timeframe)
        except ValueError as e:raise HTTPException(503,str(e))
    if MODE=='kite':raise HTTPException(409,'Intraday charts currently support IBKR and synthetic demo only')
    result=analyse(symbol)
    return demo_chart(symbol,timeframe,result['price'])

@app.get('/alerts')
def alerts(): return engine.alerts()
@app.get('/trades')
def trades(): return engine.trades()
class InputModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

class Track(InputModel):
    symbol:str
    capital:float=Field(100000,gt=0,le=1e10)
    risk_pct:float=Field(1,gt=0,le=2)
@app.post('/trades',status_code=201)
def track(body:Track):
    if MODE=='ibkr':raise HTTPException(409,'IBKR is read-only research. Broker and live-feed paper orders are disabled in this release.')
    a=analyse(body.symbol.upper())
    if not a['confirmed']: raise HTTPException(409,'No confirmed setup; use replay demo to test alerts')
    if a.get('security_type')=='FUT':
        estimate=futures_risk(body.capital,body.risk_pct,a['plan']['entry'],a['plan']['stop'],a['contract']['multiplier'],a['contract']['min_tick'])
        size={'units':estimate['contracts']}
    else: size=position_size(body.capital,body.risk_pct,a['plan']['entry'],a['plan']['stop'])
    if not size['units']: raise HTTPException(409,'Capital/risk budget too small')
    try: return engine.create(a['symbol'],a['direction'],a['plan'],size['units'],currency=a.get('currency','INR'),multiplier=a.get('contract',{}).get('multiplier',1))
    except ValueError as e: raise HTTPException(409,str(e))
@app.delete('/trades/{trade_id}')
def cancel(trade_id:int):
    try: engine.cancel(trade_id)
    except KeyError: raise HTTPException(404,'Trade not found')
    return {'status':'cancelled'}
class Size(InputModel):
    capital:float=Field(gt=0)
    risk_pct:float=Field(gt=0,le=2)
    entry:float=Field(gt=0)
    stop:float=Field(gt=0)
    lot_size:int=Field(1,ge=1)
@app.post('/position-size')
def size(body:Size):
    try: return position_size(**body.model_dump())
    except ValueError as e: raise HTTPException(422,str(e))
@app.post('/replay/demo')
def replay_demo():
    if service: raise HTTPException(409,'Demo replay is unavailable in Kite mode')
    # Explicit isolated sample, never a generated recommendation.
    try: t=engine.create('DEMO_US_FUT' if MODE=='us_demo' else 'DEMO','LONG',dict(entry=100,stop=95,target1=107.5,target2=115),currency='USD' if MODE=='us_demo' else 'INR',multiplier=5 if MODE=='us_demo' else 1)
    except ValueError as e: raise HTTPException(409,str(e))
    for p in (99.8,100,108,115): t=engine.tick(t['id'],p)
    return dict(trade=t,events=[e for e in engine.alerts() if e['trade_id']==t['id']])
@app.get('/rules')
def rules(): return DEFAULT_RULES
@app.websocket('/live')
async def live(ws:WebSocket):
    header=ws.headers.get('authorization','')
    if API_TOKEN and header and not secrets.compare_digest(header,'Bearer '+API_TOKEN):
        await ws.close(code=1008);return
    browser_auth=bool(API_TOKEN and not header)
    if browser_auth:
        origin=urlsplit(ws.headers.get('origin',''))
        if origin.scheme not in ('https','http') or origin.netloc!=ws.headers.get('host'):
            await ws.close(code=1008);return
    await ws.accept()
    if browser_auth:
        try:
            message=await asyncio.wait_for(ws.receive_json(),timeout=5)
            value=message.get('token') if isinstance(message,dict) else None
            if not isinstance(value,str) or len(value)>1024 or not secrets.compare_digest(value,API_TOKEN):
                await ws.close(code=1008);return
        except (asyncio.TimeoutError,ValueError,WebSocketDisconnect):
            await ws.close(code=1008);return
    try:
        while True:
            snapshot = await asyncio.to_thread(scan, 0)
            await ws.send_json(dict(type='snapshot',mode=MODE,scan=snapshot,trades=engine.trades(),alerts=engine.alerts(),broker=broker_status(),automation=automation_status()))
            if service:
                for _ in range(50):
                    await asyncio.sleep(.1)
                    quotes=service.quote_view()
                    await ws.send_json(dict(type='ticks',mode=MODE,quotes={k:{'price':v['price'],'age_ms':round(v['age']*1000),'exchange_time':v['exchange_time'],'data_type':v.get('data_type','live'),'bid':v.get('bid'),'ask':v.get('ask'),'timestamp_basis':v.get('timestamp_basis','exchange')} for k,v in quotes.items()},broker=broker_status()))
            else: await asyncio.sleep(5)
    except (WebSocketDisconnect,RuntimeError): pass

class ReplayTick(InputModel):
    price: float = Field(gt=0)
    volume_confirmed: bool = True
    candle_close: bool = True
    high: float | None = Field(None, gt=0)
    low: float | None = Field(None, gt=0)
    @model_validator(mode='after')
    def valid_range(self):
        if self.high is not None and self.price>self.high: raise ValueError('Price exceeds high')
        if self.low is not None and self.price<self.low: raise ValueError('Price below low')
        if self.low is not None and self.high is not None and self.low>self.high: raise ValueError('Low exceeds high')
        return self

@app.post('/replay/{trade_id}/tick')
def replay_tick(trade_id:int,body:ReplayTick):
    try: return engine.tick(trade_id,**body.model_dump())
    except KeyError: raise HTTPException(404,'Trade not found')

@app.get('/broker/status')
def broker_status():
    return service.status() if service else dict(mode=MODE,market='US' if MODE=='us_demo' else 'India',currency='USD' if MODE=='us_demo' else 'INR',ready=False,feed_connected=False,universe_count=len(market_universe),error='Synthetic demo. A configured broker gateway is required for live data')

@app.get('/automation')
def automation_status():
    return service.auto.status() if service else dict(enabled=False,mode='paper',live_allowed=False,reason='Synthetic mode: broker automation is unavailable',orders=[])

@app.post('/automation')
def configure_automation(body:AutoConfig):
    if MODE=='ibkr':raise HTTPException(409,'IBKR research is read-only; automation cannot be enabled')
    if not service: raise HTTPException(409,'Broker service required; synthetic signals cannot trigger automation')
    try: service.auto.configure(body,service.ready())
    except ValueError as e: raise HTTPException(409,str(e))
    return service.auto.status()

@app.post('/automation/stop')
def stop_automation():
    if service: service.auto.pause('Stopped by user; pending orders/positions remain at broker; protective exits continue')
    return automation_status()

@app.get('/kite/callback', include_in_schema=False)
def kite_callback():
    # This landing page does not exchange tokens, authorize the phone, or enable orders.
    # Never echo query parameters; the private CLI performs the authenticated exchange.
    return PlainTextResponse(
        'Kite login redirect received. Return to your private server terminal and continue '
        'scripts/kite-login.py. Copy the request_token from this page address into the hidden '
        'terminal prompt. Do not share the address or token. This page does not verify a '
        'broker session or enable trading.',
        headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer',
                 'Content-Security-Policy':"default-src 'none'; frame-ancestors 'none'",
                 'X-Content-Type-Options':'nosniff'})

class FuturesRisk(InputModel):
    symbol:str
    capital:float=Field(gt=0,le=1e9)
    risk_pct:float=Field(gt=0,le=2)
    entry:float=Field(gt=0)
    stop:float=Field(gt=0)

@app.post('/futures-risk')
def estimate_futures_risk(body:FuturesRisk):
    result=analyse(body.symbol.upper())
    if result.get('security_type')!='FUT':raise HTTPException(409,'Select a futures contract')
    meta=result['contract']
    try:return futures_risk(body.capital,body.risk_pct,body.entry,body.stop,meta['multiplier'],meta['min_tick'])
    except ValueError as error:raise HTTPException(422,str(error))

_WEB=Path(__file__).parent/'web'
@app.get('/app',include_in_schema=False)
@app.get('/app/',include_in_schema=False)
def web_app(request:Request):
    host=request.headers.get('host','')
    connect="'self'"+(f' wss://{host} ws://{host}' if re.fullmatch(r'[A-Za-z0-9.:-]+',host) else '')
    return FileResponse(_WEB/'index.html',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer',
        'Content-Security-Policy':f"default-src 'self'; script-src 'self'; style-src 'self'; connect-src {connect}; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})

@app.get('/app.js',include_in_schema=False)
def web_js():return FileResponse(_WEB/'app.js',media_type='application/javascript',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

@app.get('/app.css',include_in_schema=False)
def web_css():return FileResponse(_WEB/'app.css',media_type='text/css',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
