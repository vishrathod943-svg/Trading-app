"""Persistent, idempotent paper trade lifecycle with conservative OHLC replay."""
import sqlite3
from datetime import datetime, timezone
from threading import RLock

class Engine:
    def __init__(self,path):
        self.lock=RLock()
        self.db=sqlite3.connect(path,check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY, symbol TEXT, direction TEXT, state TEXT, entry REAL, stop REAL, target1 REAL, target2 REAL, quantity INTEGER, last_price REAL, created_at TEXT);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, trade_id INTEGER, event TEXT, price REAL, time TEXT, message TEXT, UNIQUE(trade_id,event));
        ''')
        columns={row[1] for row in self.db.execute('PRAGMA table_info(trades)')}
        for column in ('fill_entry','exit_price'):
            if column not in columns: self.db.execute(f'ALTER TABLE trades ADD COLUMN {column} REAL')
        for column,sql in [('currency',"TEXT NOT NULL DEFAULT 'INR'"),('multiplier','REAL NOT NULL DEFAULT 1')]:
            if column not in columns:self.db.execute(f'ALTER TABLE trades ADD COLUMN {column} {sql}')
        self.db.commit()
    def trades(self):
        with self.lock:
            rows=[dict(r) for r in self.db.execute('SELECT * FROM trades ORDER BY id DESC')]
            for t in rows:
                t['pnl']=round(((t['exit_price'] if t['exit_price'] is not None else t['last_price'])-t['fill_entry'])*(1 if t['direction']=='LONG' else -1)*t['quantity']*t['multiplier'],2) if t['fill_entry'] is not None else None
                t['pnl_kind']='realized' if t['exit_price'] is not None else 'unrealized' if t['fill_entry'] is not None else 'not entered'
            return rows
    def alerts(self):
        with self.lock: return [dict(r) for r in self.db.execute('SELECT events.*,trades.symbol,trades.currency FROM events JOIN trades ON trades.id=events.trade_id ORDER BY events.id DESC LIMIT 200')]
    def event(self,t,event,price,message):
        self.db.execute('INSERT OR IGNORE INTO events(trade_id,event,price,time,message) VALUES(?,?,?,?,?)',(t['id'],event,price,datetime.now(timezone.utc).isoformat(),message))
    def create(self,symbol,direction,plan,quantity=1,currency='INR',multiplier=1):
        with self.lock, self.db:
            active=[t for t in self.trades() if t['state'] in ('WAITING_ENTRY','ENTRY_TRIGGERED','T1_HIT')]
            if len(active)>=5: raise ValueError('Maximum 5 active paper trades')
            if any(t['symbol']==symbol for t in active): raise ValueError('Symbol already tracked')
            cursor=self.db.execute('INSERT INTO trades(symbol,direction,state,entry,stop,target1,target2,quantity,last_price,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (symbol,direction,'WAITING_ENTRY',plan['entry'],plan['stop'],plan['target1'],plan['target2'],quantity,plan['entry'],datetime.now(timezone.utc).isoformat()))
            self.db.execute('UPDATE trades SET currency=?,multiplier=? WHERE id=?',(currency,multiplier,cursor.lastrowid))
            t=next(t for t in self.trades() if t['id']==cursor.lastrowid)
            self.event(t,'NEW_SETUP',t['entry'],'Paper setup tracked; replay data only')
            return t
    def cancel(self,trade_id):
        with self.lock,self.db:
            t=next((t for t in self.trades() if t['id']==trade_id),None)
            if not t: raise KeyError(trade_id)
            if t['state'] in ('WAITING_ENTRY','ENTRY_TRIGGERED','T1_HIT'):
                self.db.execute('UPDATE trades SET state=? WHERE id=?',('CANCELLED',trade_id))
                self.event(t,'CANCELLED',t['last_price'],'Tracking stopped')
    def tick(self,trade_id,price,volume_confirmed=True,candle_close=True,high=None,low=None):
        if price<=0: raise ValueError('Price must be positive')
        with self.lock,self.db:
            t=next((t for t in self.trades() if t['id']==trade_id),None)
            if not t: raise KeyError(trade_id)
            state=t['state']; sign=1 if t['direction']=='LONG' else -1
            if state not in ('WAITING_ENTRY','ENTRY_TRIGGERED','T1_HIT'): return t
            if state=='WAITING_ENTRY':
                if abs(price/t['entry']-1)<=.003: self.event(t,'ENTRY_NEAR',price,'Price near planned entry')
                if sign*(price-t['entry'])>=0:
                    if sign*(price/t['entry']-1)>.015:
                        state='EXPIRED'; self.event(t,'GAP',price,'Entry exceeded by >1.5%; skipped instead of chasing')
                    elif volume_confirmed and candle_close:
                        state='ENTRY_TRIGGERED'; self.db.execute('UPDATE trades SET fill_entry=? WHERE id=?',(price,trade_id)); self.event(t,state,price,'Paper entry confirmed at actual replay price')
            elif candle_close:
                adverse=low if sign==1 and low is not None else high if sign==-1 and high is not None else price
                favorable=high if sign==1 and high is not None else low if sign==-1 and low is not None else price
                if sign*(adverse-t['stop'])<=0:
                    state='SL_HIT'; fill=price if sign*(price-t['stop'])<0 else t['stop']
                    self.db.execute('UPDATE trades SET exit_price=? WHERE id=?',(fill,trade_id))
                    self.event(t,state,fill,'Stop first if both stop and target occur in the same candle')
                elif sign*(favorable-t['target2'])>=0:
                    self.event(t,'T1_HIT',t['target1'],'T1 passed; no partial exit assumed')
                    state='T2_HIT'; self.db.execute('UPDATE trades SET exit_price=? WHERE id=?',(t['target2'],trade_id)); self.event(t,state,t['target2'],'Paper final target reached')
                elif state=='ENTRY_TRIGGERED' and sign*(favorable-t['target1'])>=0:
                    state='T1_HIT'; self.event(t,state,t['target1'],'Review stop; no automatic stop change')
            self.db.execute('UPDATE trades SET state=?,last_price=? WHERE id=?',(state,price,trade_id))
            return next(x for x in self.trades() if x['id']==trade_id)
