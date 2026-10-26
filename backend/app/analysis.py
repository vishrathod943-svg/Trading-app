"""Causal daily analysis. All price data supplied by the provider, never invented as live."""
import math
from dataclasses import dataclass
from statistics import mean

@dataclass(frozen=True)
class Candle:
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float

def ema(values, period):
    result = [values[0]]
    for value in values[1:]:
        result.append(value * 2 / (period + 1) + result[-1] * (1 - 2 / (period + 1)))
    return result

def indicators(candles):
    if len(candles) < 201:
        raise ValueError('At least 201 candles required')
    closes = [c.close for c in candles]
    changes = [b - a for a, b in zip(closes, closes[1:])]
    def wilder(values, period=14):
        result = mean(values[:period])
        for v in values[period:]:
            result = (result * (period - 1) + v) / period
        return result
    gains = wilder([max(c, 0) for c in changes])
    losses = wilder([max(-c, 0) for c in changes])
    rsi = 100 - 100 / (1 + gains / losses) if losses else (100 if gains else 50)
    ranges = [max(c.high-c.low, abs(c.high-p.close), abs(c.low-p.close)) for p,c in zip(candles,candles[1:])]
    macds = [a-b for a,b in zip(ema(closes,12),ema(closes,26))]
    return dict(ema20=ema(closes,20)[-1], ema50=ema(closes,50)[-1], ema200=ema(closes,200)[-1],
                rsi=rsi, atr=wilder(ranges), macd=macds[-1], macd_signal=ema(macds,9)[-1],
                volume_ratio=candles[-1].volume / mean(c.volume for c in candles[-21:-1]),
                high20=max(c.high for c in candles[-21:-1]), low20=min(c.low for c in candles[-21:-1]))

DEFAULT_RULES = dict(min_score=65, volume_ratio=1.5, bullish_rsi_min=50, bullish_rsi_max=75,
                     bearish_rsi_min=25, bearish_rsi_max=50,
                     weights=dict(setup=30, volume=20, moves=15, backtest=20, fundamentals=15))

def direction_for(candles, rules):
    i=indicators(candles); price=candles[-1].close
    if i['volume_ratio'] < rules['volume_ratio']:
        return None
    if price > i['ema50'] > i['ema200'] and price > i['high20'] and rules['bullish_rsi_min'] <= i['rsi'] <= rules['bullish_rsi_max'] and i['macd'] > 0:
        return 'LONG'
    if price < i['ema50'] < i['ema200'] and price < i['low20'] and rules['bearish_rsi_min'] <= i['rsi'] <= rules['bearish_rsi_max'] and i['macd'] < 0:
        return 'SHORT'
    return None

def major_moves(candles):
    moves=[]
    for n in range(201,len(candles)):
        c=candles[n]; prev=candles[n-1]
        prior=indicators(candles[:n])
        pct=100*(c.close/prev.close-1)
        vr=c.volume/mean(x.volume for x in candles[n-20:n])
        if (abs(c.close-prev.close)>2*prior['atr'] or abs(pct)>5) and vr>1.5:
            moves.append(dict(date=c.time,direction='LONG' if pct>0 else 'SHORT',change_pct=round(pct,2),volume_ratio=round(vr,2),
                forward_5=round((candles[n+5].close/c.close-1)*100,2) if n+5<len(candles) else None,
                forward_10=round((candles[n+10].close/c.close-1)*100,2) if n+10<len(candles) else None))
    return moves[-5:]

def backtest(candles, rules, horizon=10, cost_bps=25):
    """Chronological 70/30 holdout; only evaluate fully matured signals in holdout.
    Non-overlapping close-to-close trades. Not a claim about option performance.
    """
    split=max(201,int(len(candles)*.7)); results=[]; last_exit=-1
    for n in range(split,len(candles)-horizon):
        if n<=last_exit: continue
        direction=direction_for(candles[:n+1],rules)
        if not direction: continue
        sign=1 if direction=='LONG' else -1
        entry=candles[n].close; risk=1.5*indicators(candles[:n+1])['atr']
        net=sign*(candles[n+horizon].close/entry-1)-cost_bps/10000
        adverse=min(sign*(c.close/entry-1) for c in candles[n+1:n+horizon+1])
        results.append((net,net*entry/risk,adverse)); last_exit=n+horizon
    count=len(results)
    return dict(horizon=horizon,sample_size=count,statistics_available=count>=20,
        win_rate=round(mean(r[0]>0 for r in results)*100,1) if count>=20 else None,
        average_return=round(mean(r[0] for r in results)*100,2) if count>=20 else None,
        average_r=round(mean(r[1] for r in results),2) if count>=20 else None,
        average_drawdown=round(mean(r[2] for r in results)*100,2) if count>=20 else None,
        cost_bps=cost_bps,method='Chronological 30% holdout, non-overlapping, underlying close returns')

def trade_plan(candles, direction):
    i=indicators(candles); sign=1 if direction=='LONG' else -1
    entry=candles[-1].high if sign==1 else candles[-1].low
    swing=min(c.low for c in candles[-6:]) if sign==1 else max(c.high for c in candles[-6:])
    risk=min(1.5*i['atr'],abs(entry-swing))
    if risk<=0: raise ValueError('Invalid risk distance')
    return dict(entry=round(entry,2),pullback=round(i['ema20'],2),stop=round(entry-sign*risk,2),
                target1=round(entry+sign*1.5*risk,2),target2=round(entry+sign*3*risk,2),rr=3.0,risk_per_share=round(risk,2))

def position_size(capital,risk_pct,entry,stop,lot_size=1):
    if capital<=0 or not 0<risk_pct<=2 or entry<=0 or stop<=0 or entry==stop or lot_size<1:
        raise ValueError('Positive capital/prices, risk in (0,2], and a valid lot required')
    budget=capital*risk_pct/100
    units=min(math.floor(budget/abs(entry-stop)/lot_size)*lot_size, math.floor(capital/entry/lot_size)*lot_size)
    return dict(units=units,lots=units//lot_size,risk_budget=round(budget,2),planned_loss=round(units*abs(entry-stop),2),
                warning='Underlying sizing only; option premium sizing needs verified live contracts. Gaps can exceed planned loss.')

def select_option(chain,direction):
    eligible=[c for c in chain if c['type']==('CE' if direction=='LONG' else 'PE') and 0.45<=abs(c['delta'])<=0.6 and c['days_to_expiry']>=10 and c['oi']>=10000 and c['volume']>=1000 and c['ask']>0 and 0<=(c['ask']-c['bid'])/c['ask']<=.03]
    return min(eligible,key=lambda c:abs(abs(c['delta'])-.5)) if eligible else None
