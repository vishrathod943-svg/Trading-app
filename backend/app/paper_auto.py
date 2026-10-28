"""Delayed-data-only, causal OHLC paper simulation. No broker order API imports."""
import copy
import json
import math
import sqlite3
from datetime import datetime,timezone
from threading import RLock
from zoneinfo import ZoneInfo
from .ict import analyse_ict


def stamp(value):
    result=datetime.fromisoformat(value)
    if result.tzinfo is None:raise ValueError('Timezone required')
    return result.timestamp()


def signal(candles,timeframe):
    """A close-confirmed break plus a same-direction, unfilled recent FVG."""
    if len(candles)<30:return None
    analysis=analyse_ict(candles,timeframe)
    index=len(candles)-1
    breaks=[e for e in analysis['events'] if e['index']==index and e['kind'] in ('BOS','CHoCH','Liquidity sweep')]
    for event in reversed(breaks):
        zones=[z for z in analysis['zones'] if z['kind']=='FVG' and z['direction']==event['direction'] and z['filled_at'] is None and index-5<=z['start']<=index]
        if zones:
            z=zones[-1]
            return dict(direction='LONG' if event['direction']=='bullish' else 'SHORT',stop=z['low'] if event['direction']=='bullish' else z['high'],signal_time=candles[-1]['time'],reason=event['kind']+' with recent unfilled FVG')
        if event['kind'] in ('BOS','CHoCH'):
            blocks=[z for z in analysis['zones'] if z['kind']=='OB candidate' and z['direction']==event['direction'] and z['start']==index]
            if blocks:
                z=blocks[-1]
                return dict(direction='LONG' if event['direction']=='bullish' else 'SHORT',stop=z['low'] if event['direction']=='bullish' else z['high'],signal_time=candles[-1]['time'],reason=event['kind']+' with candidate order block')
    return None


class PaperAuto:
    def __init__(self,path):
        self.lock=RLock();self.db=sqlite3.connect(path,check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS paper_auto_state(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL)')
        row=self.db.execute('SELECT body FROM paper_auto_state WHERE id=1').fetchone()
        self.s=json.loads(row[0]) if row else dict(enabled=False,config=None,cursor=None,pending=None,trades=[],events=[],contract_id=None)
        self.s.setdefault('risk',None)
        self.s['enabled']=False;self.s['pending']=None
        for t in self.s['trades']:
            if t['state']=='OPEN':t['state']='RESTART_UNRESOLVED'
        self.s['reason']='Stopped. Arm explicitly; restarting never resumes or backfills trades.'
        self._save()
    def _save(self):
        with self.db:self.db.execute('INSERT OR REPLACE INTO paper_auto_state VALUES(1,?)',(json.dumps(self.s,allow_nan=False),))
    def status(self):
        with self.lock:return dict(**copy.deepcopy(self.s),simulation=True,orders_enabled=False,data_requirement='delayed',warning='Delayed OHLC simulation only. No broker fills. Illustrative fees only; no slippage, margin or buying-power validation. Long-only stocks; futures and shorts skipped. Not live performance.')
    def event(self,message):
        self.s['events'].append(dict(time=datetime.now(timezone.utc).isoformat(),message=message))
        self.s['events']=self.s['events'][-100:]
    def configure(self,config):
        with self.lock:
            if self.s['enabled']:raise ValueError('Pause the current simulation before reconfiguring')
            if any(t['state'].endswith('UNRESOLVED') for t in self.s['trades']):raise ValueError('Unresolved paper position requires journal reconciliation before new entries; no unknown P&L will be ignored')
            if config['capital']!=1000 or not 0<config['risk_pct']<=.5:raise ValueError('This scalping simulation uses $1,000 and at most 0.5% risk per trade')
            if self.s['risk'] is None:self.s['risk']=dict(balance=1000.0,day=None,day_pnl=0.0,entries=0,losses=0)
            self.s.update(enabled=True,config=config,cursor=None,pending=None,contract_id=None,reason='Waiting for delayed quotes and completed bars; historical setups will not be replayed')
            self.event('Armed delayed-data paper monitor; not a broker order');self._save()
            return self.status()
    def pause(self):
        with self.lock:
            self.s['enabled']=False;self.s['pending']=None
            for t in self.s['trades']:
                if t['state']=='OPEN':t['state']='PAUSED_UNRESOLVED'
            self.s['reason']='Paused. No exit price fabricated for unresolved simulations.'
            self.event(self.s['reason']);self._save();return self.status()
    def waiting(self,reason):
        with self.lock:self.s['reason']=reason;self._save()
    def _baseline(self,candles,cid,reason):
        self.s.update(cursor=candles[-1]['time'],contract_id=cid,pending=None,reason=reason)
        for t in self.s['trades']:
            if t['state']=='OPEN':
                t['state']='DATA_GAP_UNRESOLVED';self.s['enabled']=False;self.s['reason']='Disarmed: unresolved paper position after data gap; reconciliation required'
        self.event(reason)
    def process(self,candles,meta,quote,now=None):
        with self.lock:
            if not self.s['enabled']:return
            now=now or datetime.now(timezone.utc);config=self.s['config'];seconds={'5m':300,'15m':900}[config['timeframe']]
            # Returned broker feed type is authoritative. Even entitled live data is rejected here.
            if quote is None or quote.get('data_type')!='delayed' or quote.get('price') is None or quote.get('age',float('inf'))>90:
                self.waiting('Waiting for a fresh received DELAYED quote; live, frozen, synthetic and missing feeds are excluded');return
            try:
                if meta['security_type']=='FUT':
                    expiry=str(meta['expiry']).split(' ')[0]
                    if len(expiry)!=8 or datetime.strptime(expiry,'%Y%m%d').date()<=now.date():raise ValueError('Expiry invalid')
                tick=float(meta['min_tick']);multiplier=float(meta['multiplier']);cid=int(meta['con_id'])
                if not all(math.isfinite(x) and x>0 for x in (tick,multiplier)) or cid<=0:raise ValueError('Invalid metadata')
                times=[stamp(b['time']) for b in candles]
                if len(times)<30 or any(b<=a for a,b in zip(times,times[1:])):raise ValueError('Invalid bar ordering')
                if any(t+seconds>now.timestamp() for t in times):raise ValueError('Incomplete candle')
                if now.timestamp()-(times[-1]+seconds)>2700:raise ValueError('Historical bars older than 45 minutes')
                for b in candles:
                    o,h,l,c=[float(b[k]) for k in ('open','high','low','close')]
                    if not all(math.isfinite(x) and x>0 for x in (o,h,l,c)) or not l<=min(o,c)<=max(o,c)<=h:raise ValueError('Invalid OHLC')
            except (ValueError,KeyError,TypeError):
                self.waiting('Waiting: valid recent completed bars and unexpired broker contract metadata required');return
            if self.s['cursor'] is None:
                self._baseline(candles,cid,'Baseline set. Waiting for a NEW completed candle; no historical entries replayed');self._save();return
            new=[(i,b) for i,b in enumerate(candles) if stamp(b['time'])>stamp(self.s['cursor'])]
            if not new:self.s['reason']='Waiting for next completed delayed candle';self._save();return
            index,b=new[-1]
            if cid!=self.s['contract_id'] or len(new)!=1 or stamp(b['time'])-stamp(self.s['cursor'])!=seconds:
                self._baseline(candles,cid,'Data gap or contract change: no hindsight fills; unresolved position retained in journal');self._save();return
            risk=self.s['risk']
            today=now.date().isoformat()
            if risk['day']!=today:risk.update(day=today,day_pnl=0.0,entries=0,losses=0)
            blocked=risk['day_pnl']<=-20 or risk['losses']>=3 or risk['entries']>=10 or risk['balance']<=0
            active=next((t for t in reversed(self.s['trades']) if t['state']=='OPEN'),None)
            pending=self.s['pending'];self.s['pending']=None
            market_time=datetime.fromtimestamp(stamp(b['time']),ZoneInfo('America/New_York'))
            minutes=market_time.hour*60+market_time.minute
            entry_session=market_time.weekday()<5 and 575<=minutes<930
            if pending and not active and not blocked and entry_session:
                entry=float(b['open']);sign=1 if pending['direction']=='LONG' else -1
                stop=(math.floor(pending['stop']/tick)-1)*tick if sign==1 else (math.ceil(pending['stop']/tick)+1)*tick
                distance=sign*(entry-stop)
                # Entry and sizing use next-bar OPEN only, never that bar's high/low/close.
                budget=min(risk['balance'],1000)*config['risk_pct']/100
                # Conservative illustrative round-trip costs: $2 + $0.01 per share.
                quantity=math.floor((budget-2)/(distance*multiplier+.01)) if distance>=tick*.99 and budget>2 else 0
                if meta['security_type']=='STK':quantity=min(quantity,math.floor(max(0,risk['balance']-2)/(entry+.01)))
                else:quantity=0 # Futures margin is not verified; no futures scalping simulation fills.
                if pending['direction']=='SHORT':quantity=0 # No borrow/buying-power verification; long-only.

                if quantity>0 and quantity<=100000:
                    cost=2+.01*quantity
                    planned_risk=distance*quantity*multiplier+cost
                    target_distance=(planned_risk*config['rr']+cost)/(quantity*multiplier)
                    target=entry+sign*math.ceil(target_distance/tick)*tick
                    active=dict(id=(self.s['trades'][-1]['id']+1 if self.s['trades'] else 1),symbol=config['symbol'],direction=pending['direction'],state='OPEN',signal_time=pending['signal_time'],entry_time=b['time'],entry=entry,stop=round(stop,8),target=round(target,8),quantity=quantity,planned_risk=round(planned_risk,2),target_net_rr=config['rr'],multiplier=multiplier,currency='USD',last_price=entry,exit_price=None,exit_time=None,pnl=None,observed_at=now.isoformat(),reason=pending['reason'])
                    risk['entries']+=1;self.s['trades'].append(active);self.s['trades']=self.s['trades'][-200:];self.event('Simulated next-candle-open entry: '+config['symbol'])
                else:self.event('Skipped paper entry: risk/notional limit, invalid stop, or unverified short/futures permissions')
            if active:
                sign=1 if active['direction']=='LONG' else -1;o=b['open'];h=b['high'];l=b['low'];stop=active['stop'];target=active['target']
                adverse=l if sign==1 else h;favorable=h if sign==1 else l
                if sign*(o-stop)<=0:exit_price=o;state='STOP_GAP'
                elif sign*(o-target)>=0:exit_price=target;state='TARGET'
                elif sign*(adverse-stop)<=0:exit_price=stop;state='STOP'
                elif sign*(favorable-target)>=0:exit_price=target;state='TARGET'
                elif stamp(b['time'])+seconds-stamp(active['entry_time'])>=1800 or minutes+seconds/60>=955:exit_price=b['close'];state='TIME_EXIT'
                else:exit_price=None;state='OPEN'
                active.update(state=state,last_price=b['close'])
                if exit_price is not None:
                    active.update(exit_price=exit_price,exit_time=b['time'],pnl=round(sign*(exit_price-active['entry'])*active['quantity']*active['multiplier']-(2+.01*active['quantity']),2),cost_model=round(2+.01*active['quantity'],2))
                    risk['balance']=round(risk['balance']+active['pnl'],2);risk['day_pnl']=round(risk['day_pnl']+active['pnl'],2);risk['losses']=risk['losses']+1 if active['pnl']<0 else 0
                    self.event('Simulated '+state+' exit; stop first when intrabar ordering is ambiguous')
            # No re-entry on an exit candle; no signal uses bars after the signal candle.
            signal_session=market_time.weekday()<5 and 575<=minutes+seconds/60<925
            if active is None and not blocked and signal_session:self.s['pending']=signal(candles[:index+1],config['timeframe'])
            if self.s['pending']:self.event('New closed-candle setup; waiting for next candle (paper only)')
            self.s['cursor']=b['time'];self.s['reason']='Daily risk limit reached; new simulated entries blocked' if blocked else 'Monitoring completed delayed bars; simulation only';self._save()
