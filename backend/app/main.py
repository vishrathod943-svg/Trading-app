import asyncio
import os
from threading import RLock
from contextlib import asynccontextmanager
import secrets
from fastapi.responses import JSONResponse
from .automation import AutoConfig
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .analysis import DEFAULT_RULES, indicators, direction_for, major_moves, backtest, trade_plan, position_size
from .provider import DemoProvider, UNIVERSE
from .engine import Engine
from .rules import load_rules

DEFAULT_RULES = load_rules()

MODE=os.getenv('FO_MODE','demo')
if MODE not in ('demo','kite'): raise RuntimeError('FO_MODE must be demo or kite')
API_TOKEN=os.getenv('FO_API_TOKEN','')
if MODE=='kite' and len(API_TOKEN)<32: raise RuntimeError('Kite mode requires a random FO_API_TOKEN of at least 32 characters')
provider=DemoProvider(); engine=Engine(os.getenv('FO_DATABASE','screener.db'))
service=None
if MODE=='kite':
    from .kite_live import KiteLive
    service=KiteLive(DEFAULT_RULES,os.getenv('FO_AUTO_DATABASE','automation.db'))

@asynccontextmanager
async def lifespan(app):
    if service: service.start()
    yield
    if service: await service.stop()

app=FastAPI(title='F&O Compass',version='0.2.0',lifespan=lifespan,
    description='Single-account Kite streaming and guarded option automation; demo remains available.')

@app.middleware('http')
async def authenticate(request,call_next):
    if API_TOKEN and not secrets.compare_digest(request.headers.get('authorization',''), 'Bearer '+API_TOKEN):
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
def health(): return dict(status='ok',mode=MODE,feed_connected=bool(service and service.connected),push_configured=False,universe=service.status() if service else '8 synthetic NSE symbols; BSE not connected',time=datetime.now(timezone.utc).isoformat())
@app.get('/scan')
def scan(min_score:float=Query(0,ge=0,le=100),exchange:str|None=None,sector:str|None=None,direction:str|None=None):
    items=list(service.results.values()) if service else [analyse(s) for s,_,_ in UNIVERSE]
    quotes=service.quote_view() if service else {}
    items=[dict(x,**({'price':quotes[x['exchange']+':'+x['symbol']]['price'],'tick_age_ms':round(quotes[x['exchange']+':'+x['symbol']]['age']*1000)} if x['exchange']+':'+x['symbol'] in quotes else {})) for x in items]
    filtered=[x for x in items if x['score']>=min_score and (not exchange or x['exchange']==exchange) and (not sector or x['sector']==sector) and (not direction or x['direction']==direction)]
    confirmed=[x for x in items if x['confirmed']]
    return dict(items=[{k:v for k,v in x.items() if k not in ('candles','major_moves','backtests','indicators')} for x in filtered],
        confirmed_count=len(confirmed),average_score=round(sum(x['score'] for x in confirmed)/len(confirmed),1) if confirmed else 0,
        advances=sum(x['change_pct']>0 for x in items),declines=sum(x['change_pct']<0 for x in items),mode=MODE,updated_at=datetime.now(timezone.utc).isoformat())
@app.get('/stock/{symbol}')
def stock(symbol:str): return analyse(symbol.upper())
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
    a=analyse(body.symbol.upper())
    if not a['confirmed']: raise HTTPException(409,'No confirmed setup; use replay demo to test alerts')
    size=position_size(body.capital,body.risk_pct,a['plan']['entry'],a['plan']['stop'])
    if not size['units']: raise HTTPException(409,'Capital/risk budget too small')
    try: return engine.create(a['symbol'],a['direction'],a['plan'],size['units'])
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
    try: t=engine.create('DEMO','LONG',dict(entry=100,stop=95,target1=107.5,target2=115))
    except ValueError as e: raise HTTPException(409,str(e))
    for p in (99.8,100,108,115): t=engine.tick(t['id'],p)
    return dict(trade=t,events=[e for e in engine.alerts() if e['trade_id']==t['id']])
@app.get('/rules')
def rules(): return DEFAULT_RULES
@app.websocket('/live')
async def live(ws:WebSocket):
    if API_TOKEN and not secrets.compare_digest(ws.headers.get('authorization',''),'Bearer '+API_TOKEN):
        await ws.close(code=1008); return
    await ws.accept()
    try:
        while True:
            snapshot = await asyncio.to_thread(scan, 0)
            await ws.send_json(dict(type='snapshot',mode=MODE,scan=snapshot,trades=engine.trades(),alerts=engine.alerts(),broker=broker_status(),automation=automation_status()))
            if service:
                for _ in range(50):
                    await asyncio.sleep(.1)
                    quotes=service.quote_view()
                    await ws.send_json(dict(type='ticks',mode='kite',quotes={k:{'price':v['price'],'age_ms':round(v['age']*1000),'exchange_time':v['exchange_time']} for k,v in quotes.items()},broker=broker_status()))
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
    return service.status() if service else dict(mode='demo',ready=False,feed_connected=False,universe_count=8,error='Start server in Kite mode to use live data')

@app.get('/automation')
def automation_status():
    return service.auto.status() if service else dict(enabled=False,mode='paper',live_allowed=False,reason='Kite service not configured',orders=[])

@app.post('/automation')
def configure_automation(body:AutoConfig):
    if not service: raise HTTPException(409,'Kite service required; synthetic signals cannot trigger automation')
    try: service.auto.configure(body,service.ready())
    except ValueError as e: raise HTTPException(409,str(e))
    return service.auto.status()

@app.post('/automation/stop')
def stop_automation():
    if service: service.auto.pause('Stopped by user; pending orders/positions remain at broker; protective exits continue')
    return automation_status()
