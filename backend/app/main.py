import asyncio
import os
from threading import RLock
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .analysis import DEFAULT_RULES, indicators, direction_for, major_moves, backtest, trade_plan, position_size
from .provider import DemoProvider, UNIVERSE
from .engine import Engine
from .rules import load_rules

DEFAULT_RULES = load_rules()

if os.getenv('FO_MODE','demo')!='demo':
    raise RuntimeError('Only demo provider implemented. Live mode requires a licensed broker adapter.')
provider=DemoProvider(); engine=Engine(os.getenv('FO_DATABASE','screener.db'))
app=FastAPI(title='F&O Compass',version='0.1.0',description='Educational synthetic-data paper screener. No orders or live prices.')
cache={}
analysis_lock=RLock()
def analyse(symbol):
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
def health(): return dict(status='ok',mode='demo',feed_connected=False,push_configured=False,universe='8 synthetic NSE symbols; BSE not connected',time=datetime.now(timezone.utc).isoformat())
@app.get('/scan')
def scan(min_score:float=Query(0,ge=0,le=100),exchange:str|None=None,sector:str|None=None,direction:str|None=None):
    items=[analyse(s) for s,_,_ in UNIVERSE]
    filtered=[x for x in items if x['score']>=min_score and (not exchange or x['exchange']==exchange) and (not sector or x['sector']==sector) and (not direction or x['direction']==direction)]
    confirmed=[x for x in items if x['confirmed']]
    return dict(items=[{k:v for k,v in x.items() if k not in ('candles','major_moves','backtests','indicators')} for x in filtered],
        confirmed_count=len(confirmed),average_score=round(sum(x['score'] for x in confirmed)/len(confirmed),1) if confirmed else 0,
        advances=sum(x['change_pct']>0 for x in items),declines=sum(x['change_pct']<0 for x in items),mode='demo',updated_at=datetime.now(timezone.utc).isoformat())
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
    # Explicit isolated sample, never a generated recommendation.
    try: t=engine.create('DEMO','LONG',dict(entry=100,stop=95,target1=107.5,target2=115))
    except ValueError as e: raise HTTPException(409,str(e))
    for p in (99.8,100,108,115): t=engine.tick(t['id'],p)
    return dict(trade=t,events=[e for e in engine.alerts() if e['trade_id']==t['id']])
@app.get('/rules')
def rules(): return DEFAULT_RULES
@app.websocket('/live')
async def live(ws:WebSocket):
    await ws.accept()
    try:
        while True:
            snapshot = await asyncio.to_thread(scan, 0)
            await ws.send_json(dict(type='snapshot',mode='demo',scan=snapshot,trades=engine.trades(),alerts=engine.alerts()))
            await asyncio.sleep(5)
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
