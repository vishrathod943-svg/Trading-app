"""US research metadata, causal analysis, and futures risk calculations."""
import calendar
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from .analysis import indicators, direction_for, major_moves, backtest, trade_plan

class InstrumentSpec(BaseModel):
    model_config=ConfigDict(extra='forbid')
    symbol: str = Field(pattern=r'^[A-Z][A-Z0-9.]{0,12}$')
    security_type: Literal['STK','FUT']
    exchange: Literal['SMART','CME']
    currency: Literal['USD']='USD'
    sector: str='Unavailable'

DEFAULT_WATCHLIST=[
    dict(symbol=s,security_type='STK',exchange='SMART',sector=sector)
    for s,sector in [('AAPL','Technology'),('MSFT','Technology'),('NVDA','Technology'),('TSLA','Consumer'),('AMZN','Consumer'),('META','Technology'),('SPY','ETF'),('QQQ','ETF')]
]+[dict(symbol=s,security_type='FUT',exchange='CME',sector='Equity index futures') for s in ('MES','MNQ','ES','NQ')]

def load_watchlist(path=None):
    raw=json.loads(Path(path).read_text()) if path else DEFAULT_WATCHLIST
    if not isinstance(raw,list) or not 1<=len(raw)<=40: raise ValueError('Configure between 1 and 40 research instruments')
    specs=[InstrumentSpec.model_validate(x) for x in raw]
    if len({s.symbol for s in specs})!=len(specs): raise ValueError('Watchlist symbols must be unique')
    for s in specs:
        if (s.security_type=='STK')!=(s.exchange=='SMART'): raise ValueError('Stocks use SMART; supported index futures use CME')
    return specs

def expiry_date(text):
    text=(text or '').split(' ')[0]
    if len(text)>=8: return datetime.strptime(text[:8],'%Y%m%d').date()
    if len(text)==6:
        year,month=int(text[:4]),int(text[4:]);return date(year,month,calendar.monthrange(year,month)[1])
    raise ValueError('Broker returned no usable expiry')

def select_future(details,symbol,today):
    eligible=[]
    for d in details:
        c=d.contract
        if c.secType!='FUT' or c.symbol!=symbol or c.currency!='USD': continue
        try: expires=expiry_date(getattr(d,'realExpirationDate','') or c.lastTradeDateOrContractMonth)
        except (ValueError,TypeError): continue
        if expires>=today+timedelta(days=7): eligible.append((expires,int(c.conId),d))
    if not eligible: raise ValueError('No uniquely identified future with at least 7 days remaining')
    eligible.sort(key=lambda x:(x[0],x[1]))
    first=[d for expiry,_,d in eligible if expiry==eligible[0][0]]
    if len({int(d.contract.conId) for d in first})!=1: raise ValueError('Ambiguous front-month contract; qualification required')
    return first[0]

def rounded_plan(candles,direction,meta):
    p=trade_plan(candles,direction);tick=meta['min_tick'];sign=1 if direction=='LONG' else -1
    def away(value):return round((math.ceil((value-1e-9)/tick) if sign==1 else math.floor((value+1e-9)/tick))*tick,8)
    entry=away(p['entry'])
    stop=round((math.ceil((p['stop']-1e-9)/tick) if sign==1 else math.floor((p['stop']+1e-9)/tick))*tick,8)
    risk=sign*(entry-stop)
    if risk<tick*.99: raise ValueError('Stop distance smaller than one tick')
    return dict(entry=entry,pullback=round(round(p['pullback']/tick)*tick,8),stop=stop,
        target1=away(entry+sign*1.5*risk),target2=away(entry+sign*3*risk),rr=3.0,
        risk_per_share=round(risk,8),risk_per_contract=round(risk*meta['multiplier'],2),currency='USD')

def build_analysis(symbol,meta,candles,rules,mode='ibkr'):
    result=dict(symbol=symbol,sector=meta['sector'],exchange=meta['exchange'],currency='USD',market='US',
        security_type=meta['security_type'],contract=meta,price=candles[-1].close if candles else None,
        change_pct=round(100*(candles[-1].close/candles[-2].close-1),2) if len(candles)>1 else None,
        direction='WATCH',score=0,confirmed=False,volume_ratio=None,indicators={},candles=[c.__dict__ for c in candles[-80:]],
        major_moves=[],backtests=[],plan=None,option=None,option_chain=[],fundamentals=None,
        data_as_of=candles[-1].time if candles else None,mode=mode,price_source='HISTORICAL_CLOSE',
        data_type='waiting',warnings=['Research only: no IBKR order submission implemented',
        'Watchlist coverage, not every US listing','Futures history is for the selected expiring contract, not a continuous rolled series'])
    if len(candles)<201:
        result['warnings'].append('At least 201 completed daily candles are required for setup analysis')
        return result
    i=indicators(candles);direction=direction_for(candles,rules);moves=major_moves(candles)
    tests=[backtest(candles,rules,h) for h in (5,10,20)];w=rules['weights']
    score=round((w['setup'] if direction else 0)+w['volume']*min(i['volume_ratio']/3,1)+w['moves']*min(len(moves)/5,1)+w['backtest']*(tests[1]['win_rate'] or 0)/100)
    confirmed=bool(direction and score>=rules['min_score'])
    if mode=='ibkr' and (date.today()-date.fromisoformat(candles[-1].time)).days>7:
        confirmed=False;result['warnings'].append('Daily history is stale; no confirmed setup is issued')
    try: plan=rounded_plan(candles,direction,meta) if confirmed else None
    except ValueError: plan=None;confirmed=False
    result.update(indicators=i,direction=direction or 'WATCH',score=score,confirmed=confirmed,volume_ratio=round(i['volume_ratio'],2),major_moves=moves,backtests=tests,plan=plan)
    result['warnings'].append('Fundamentals/event checks unavailable; insufficient backtest samples are hidden')
    return result

def futures_risk(capital,risk_pct,entry,stop,multiplier,min_tick):
    values=(capital,risk_pct,entry,stop,multiplier,min_tick)
    if not all(math.isfinite(x) and x>0 for x in values) or risk_pct>2 or entry==stop:
        raise ValueError('Use positive finite values, nonzero risk distance and risk <=2%')
    for p in (entry,stop):
        if not math.isclose(p/min_tick,round(p/min_tick),abs_tol=1e-6):raise ValueError('Prices must align to the contract tick size')
    risk=abs(entry-stop)*multiplier;budget=capital*risk_pct/100
    qty=math.floor(budget/risk)
    return dict(contracts=qty,risk_per_contract=round(risk,2),planned_loss=round(qty*risk,2),
        risk_budget=round(budget,2),tick_value=round(multiplier*min_tick,4),currency='USD',
        margin_verified=False,warning='Risk-budget estimate only. Broker margin/buying power is not verified; gaps and costs can exceed the estimate.')
