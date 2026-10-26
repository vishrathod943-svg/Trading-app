"""Single-account option automation. No network is performed at module import.
Live mutations are never retried. Unknown submissions require reconciliation.
"""
import json
import math
import sqlite3
import threading
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field

IST = ZoneInfo('Asia/Kolkata')
class AutoConfig(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra='forbid')
    enabled: bool = False
    mode: str = 'paper'
    capital: float = Field(100000, gt=0, le=1e9)
    risk_pct: float = Field(1, gt=0, le=2)
    rr: float = Field(3, ge=2, le=10)
    max_positions: int = Field(3, ge=1, le=5)
    daily_loss_pct: float = Field(3, gt=0, le=5)
    premium_stop_pct: float = Field(25, ge=5, le=50)
    confirmation: str = ''

class Automation:
    def __init__(self, path, broker=None, allow_live=False):
        self.broker=broker
        self.allow_live=allow_live
        self.lock=threading.RLock()
        self.config=AutoConfig()
        self.reason='Off; explicit arming required after each server restart'
        self.db=sqlite3.connect(path,check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        self.db.execute('''CREATE TABLE IF NOT EXISTS auto_orders (
        id TEXT PRIMARY KEY, signal TEXT UNIQUE, mode TEXT, symbol TEXT,
        contract TEXT, exchange TEXT, quantity INTEGER, state TEXT, entry_id TEXT,
        exit_id TEXT, filled INTEGER DEFAULT 0, fill REAL, stop REAL, target REAL,
        pnl REAL, created_day TEXT, details TEXT)''')
        self.db.commit()
    def bind_account(self,user_id):
        with self.lock,self.db:
            self.db.execute('CREATE TABLE IF NOT EXISTS broker_identity(account TEXT)')
            row=self.db.execute('SELECT account FROM broker_identity LIMIT 1').fetchone()
            if row and row[0]!=user_id: raise ValueError('Automation database belongs to another broker account')
            if not row: self.db.execute('INSERT INTO broker_identity VALUES(?)',(user_id,))
    def orders(self):
        with self.lock: return [dict(x) for x in self.db.execute('SELECT * FROM auto_orders ORDER BY rowid DESC')]
    def save(self, ident, **fields):
        with self.db:
            self.db.execute('UPDATE auto_orders SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',(*fields.values(),ident))
    def pause(self, reason):
        with self.lock:
            self.config.enabled=False
            self.reason=reason
    def configure(self, config, ready):
        with self.lock:
            if config.mode not in ('paper','live'): raise ValueError('Mode must be paper or live')
            if any(o['state'] not in ('CLOSED','REJECTED') for o in self.orders()) and config.mode!=self.config.mode:
                raise ValueError('Resolve positions before changing execution mode')
            if config.enabled:
                if not ready: raise ValueError('Fresh Kite feed and completed initial scan are required')
                if any(o['state'] in ('ENTRY_UNKNOWN','PROTECTION_UNKNOWN','REVIEW','EMERGENCY_UNKNOWN','EMERGENCY_PENDING','TARGET_MODIFY_UNKNOWN','PARTIAL_CANCEL_UNKNOWN','ENTRY_CANCEL_UNKNOWN') for o in self.orders()):
                    raise ValueError('Resolve unknown/unprotected broker orders before arming')
                if config.mode=='live' and (not self.allow_live or config.confirmation!='ENABLE LIVE ORDERS'):
                    raise ValueError('Server live-order permission and explicit confirmation are required')
                if config.mode=='live':
                    try:
                        positions=self.broker.positions()['net']
                        expected={o['exchange']+':'+o['contract']:o['filled'] for o in self.orders() if o['mode']=='live' and o['state'] in ('PROTECTED','TARGET_PENDING')}
                        for p in positions:
                            if int(p['quantity'])!=expected.get(p['exchange']+':'+p['tradingsymbol'],0):
                                raise ValueError('Broker positions differ from app ledger; reconcile before arming')
                        for key,quantity in expected.items():
                            if not any(p['exchange']+':'+p['tradingsymbol']==key and int(p['quantity'])==quantity for p in positions):
                                raise ValueError('Tracked position absent from broker; reconcile before arming')
                    except ValueError: raise
                    except Exception: raise ValueError('Cannot verify broker positions')
                if any(o['state'] not in ('CLOSED','REJECTED') and o['mode']!=config.mode for o in self.orders()):
                    raise ValueError('Resolve positions before changing execution mode')
            self.config=config.model_copy(update={'confirmation':''})
            self.reason='Armed' if config.enabled else 'New entries stopped; existing positions still monitored'
    def status(self):
        with self.lock:
            return dict(**self.config.model_dump(exclude={'confirmation'}),live_allowed=self.allow_live,reason=self.reason,orders=self.orders())
    def consider(self, setup, contract, quote, now, ready):
        """Called only for a confirmed closed-candle setup whose underlying entry crossed.
        Capital at risk is the ENTIRE premium, not just estimated stop loss.
        """
        with self.lock:
            c=self.config
            if not c.enabled or not ready: return None
            day=now.astimezone(IST).date().isoformat()
            if now.astimezone(IST).weekday()>4 or not '09:20'<=now.astimezone(IST).strftime('%H:%M')<'15:00': return None
            if not setup.get('confirmed') or not setup.get('plan'): return None
            if setup.get('mode')!='kite': return None
            orders=self.orders()
            active=[o for o in orders if o['state'] not in ('CLOSED','REJECTED')]
            losses=sum(min(o['pnl'] or 0,0) for o in orders if o['created_day']==day and o['mode']==c.mode)
            if -losses>=c.capital*c.daily_loss_pct/100:
                self.pause('Daily realized loss limit hit'); return None
            if len(active)>=c.max_positions or any(o['symbol']==setup['symbol'] for o in active): return None
            if contract['type']!=('CE' if setup['direction']=='LONG' else 'PE') or contract['days_to_expiry']<10: return None
            bid,ask=quote['bid'],quote['ask']
            if bid<=0 or ask<=bid or (ask-bid)/ask>.03 or quote['oi']<10000 or quote['volume']<1000 or quote['age']>3: return None
            # One lot only; the full premium must fit the risk budget. No borrowed capital.
            qty=int(contract['lot_size']); price=round(math.ceil((ask-1e-9)/contract['tick_size'])*contract['tick_size'],4)
            if qty<=0 or price*qty>c.capital*c.risk_pct/100: return None
            committed=sum((o['fill'] or json.loads(o['details'])['limit'])*o['quantity'] for o in active)
            if committed+price*qty>c.capital*c.daily_loss_pct/100+losses: return None
            signal=f"{day}:{setup['symbol']}:{setup['direction']}:{setup['data_as_of']}"
            if any(o['signal']==signal for o in orders): return None
            ident=uuid.uuid4().hex[:16]
            details=json.dumps(dict(limit=price,tick=contract['tick_size'],rr=c.rr,stop_pct=c.premium_stop_pct))
            with self.db:
                self.db.execute('INSERT INTO auto_orders(id,signal,mode,symbol,contract,exchange,quantity,state,created_day,details) VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (ident,signal,c.mode,setup['symbol'],contract['tradingsymbol'],contract['exchange'],qty,'ENTRY_UNKNOWN' if c.mode=='live' else 'PAPER_OPEN',day,details))
            if c.mode=='paper':
                self._levels(ident,price,qty)
            else:
                try:
                    oid=self.broker.place_order(variety='regular',exchange=contract['exchange'],tradingsymbol=contract['tradingsymbol'],transaction_type='BUY',quantity=qty,product='NRML',order_type='LIMIT',price=price,validity='DAY',tag='e'+ident)
                    self.save(ident,entry_id=str(oid),state='ENTRY_PENDING')
                except Exception:
                    self.pause('Entry submission uncertain; inspect broker orders. No automatic retry.')
            return ident
    def _levels(self,ident,fill,qty):
        o=next(o for o in self.orders() if o['id']==ident);d=json.loads(o['details']); tick=d['tick']
        stop=math.floor(fill*(1-d['stop_pct']/100)/tick)*tick
        target=math.ceil((fill+(fill-stop)*d['rr'])/tick)*tick
        self.save(ident,fill=fill,filled=qty,stop=round(stop,4),target=round(target,4))
    def reconcile(self):
        """Broker is source of truth. Protect filled buys; target modifies same sell order.
        Unknown placement tags are recovered, but absence is never treated as permission to resend.
        """
        with self.lock:
            rows=[o for o in self.orders() if o['mode']=='live' and o['state'] not in ('CLOSED','REJECTED')]
            if not rows: return
            try: snapshots=self.broker.orders()
            except Exception:
                self.pause('Broker reconciliation unavailable'); return
            by_id={str(o['order_id']):o for o in snapshots}
            for o in rows:
                ident=o['id']
                entry=by_id.get(o['entry_id']) or next((x for x in snapshots if x.get('tag')=='e'+ident),None)
                if not entry:
                    self.pause('Unresolved entry intent; reconcile manually');continue
                self.save(ident,entry_id=str(entry['order_id']))
                filled=int(entry.get('filled_quantity',0))
                if entry['status'] not in ('COMPLETE','CANCELLED','REJECTED'):
                    # Avoid partial fills being left without protection. Cancel remainder once.
                    if filled and o['state'] not in ('PARTIAL_CANCEL_UNKNOWN','ENTRY_CANCEL_UNKNOWN'):
                        self.save(ident,state='PARTIAL_CANCEL_UNKNOWN')
                        try: self.broker.cancel_order('regular',str(entry['order_id']))
                        except Exception: self.pause('Partial fill cancellation uncertain; inspect immediately')
                    continue
                if not filled:
                    self.save(ident,state='REJECTED');continue
                if not o['fill']: self._levels(ident,float(entry['average_price']),filled)
                o=next(x for x in self.orders() if x['id']==ident)
                protection=next((x for x in snapshots if x.get('tag')=='x'+ident),None) or by_id.get(o['exit_id']) or next((x for x in snapshots if x.get('tag')=='s'+ident),None)
                if protection:
                    self.save(ident,exit_id=str(protection['order_id']))
                    if protection['status']=='COMPLETE':
                        pnl=(float(protection['average_price'])-o['fill'])*o['filled']
                        self.save(ident,state='CLOSED',pnl=pnl)
                    elif protection['status'] in ('CANCELLED','REJECTED'):
                        self.pause('Protective order rejected/cancelled; emergency exit attempted, inspect broker immediately')
                        if o['state'] not in ('EMERGENCY_UNKNOWN','EMERGENCY_PENDING','REVIEW'):
                            self.save(ident,state='EMERGENCY_UNKNOWN')
                            try:
                                oid=self.broker.place_order(variety='regular',exchange=o['exchange'],tradingsymbol=o['contract'],transaction_type='SELL',quantity=o['filled'],product='NRML',order_type='MARKET',market_protection=-1,validity='DAY',tag='x'+ident)
                                self.save(ident,exit_id=str(oid),state='EMERGENCY_PENDING')
                            except Exception: self.pause('Emergency exit uncertain; immediate broker review required')
                        else: self.save(ident,state='REVIEW')
                    elif int(protection.get('quantity',0))!=o['filled']:
                        self.save(ident,state='REVIEW');self.pause('Protective quantity mismatch; immediate broker review required')
                    elif o['state'] not in ('TARGET_MODIFY_UNKNOWN','TARGET_PENDING','EMERGENCY_UNKNOWN','EMERGENCY_PENDING','REVIEW'):
                        self.save(ident,state='PROTECTED')
                elif o['state'] not in ('PROTECTION_UNKNOWN','REVIEW','TARGET_MODIFY_UNKNOWN','TARGET_PENDING','EMERGENCY_UNKNOWN','EMERGENCY_PENDING'):
                    self.save(ident,state='PROTECTION_UNKNOWN')
                    try:
                        d=json.loads(o['details']);limit=max(d['tick'],math.floor(o['stop']*.97/d['tick'])*d['tick'])
                        oid=self.broker.place_order(variety='regular',exchange=o['exchange'],tradingsymbol=o['contract'],transaction_type='SELL',quantity=o['filled'],product='NRML',order_type='SL',price=round(limit,4),trigger_price=o['stop'],validity='DAY',tag='s'+ident)
                        self.save(ident,exit_id=str(oid),state='PROTECTION_UNKNOWN')
                    except Exception: self.pause('Protection submission uncertain; immediate broker review required')
                else: self.pause('Unconfirmed protective order; no retry, inspect broker')
    def cancel_session_entries(self):
        with self.lock:
            self.pause('Session entry window closed; pending buys being reconciled')
            for o in self.orders():
                if o['mode']=='live' and o['state']=='ENTRY_PENDING' and o['entry_id']:
                    self.save(o['id'],state='ENTRY_CANCEL_UNKNOWN')
                    try: self.broker.cancel_order('regular',o['entry_id'])
                    except Exception: self.pause('Pending-buy cancellation uncertain; inspect broker')
    def prices(self, quotes, close_session=False):
        with self.lock:
            for o in self.orders():
                q=quotes.get(o['exchange']+':'+o['contract'])
                if not q or q['age']>3 or not o['fill']: continue
                price=q['bid']
                if price<=0: continue
                if o['mode']=='paper' and o['state']=='PAPER_OPEN' and (price<=o['stop'] or price>=o['target']):
                    self.save(o['id'],state='CLOSED',pnl=(price-o['fill'])*o['filled'])
                elif o['mode']=='live' and o['state']=='PROTECTED' and (price>=o['target'] or close_session):
                    self.save(o['id'],state='TARGET_MODIFY_UNKNOWN')
                    try:
                        # Reuse the protective sell: never create a competing second exit.
                        self.broker.modify_order(variety='regular',order_id=o['exit_id'],order_type='LIMIT',price=price,trigger_price=0)
                        self.save(o['id'],state='TARGET_PENDING')
                    except Exception: self.pause('Exit modification uncertain; broker stop/exit must be reconciled')
