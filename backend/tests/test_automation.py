from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor
import pytest
from app.automation import Automation, AutoConfig
from app.kite_live import KiteLive
from app.analysis import DEFAULT_RULES
NOW=datetime(2026,10,26,10,tzinfo=ZoneInfo('Asia/Kolkata'))
SETUP=dict(symbol='TEST',mode='kite',confirmed=True,direction='LONG',data_as_of='2026-10-23',plan={'entry':100})
CONTRACT=dict(tradingsymbol='TEST26NOV100CE',exchange='NFO',type='CE',days_to_expiry=20,lot_size=100,tick_size=.05)
QUOTE=dict(bid=99,ask=100,oi=20000,volume=2000,age=.1)
class Broker:
    def __init__(self): self.book=[];self.calls=[];self.timeout=False;self.net=[]
    def positions(self): return {'net':self.net}
    def orders(self): return self.book
    def place_order(self,**kw):
        self.calls.append(('place',kw));oid=str(len(self.book)+1)
        self.book.append(dict(order_id=oid,status='OPEN' if kw['transaction_type']=='BUY' else 'TRIGGER PENDING',filled_quantity=0,average_price=0,**kw))
        if self.timeout: raise TimeoutError()
        return oid
    def cancel_order(self,variety,order_id):
        self.calls.append(('cancel',order_id));next(o for o in self.book if o['order_id']==order_id)['status']='CANCELLED'
    def modify_order(self,**kw): self.calls.append(('modify',kw))
def armed(mode='paper'):
    b=Broker();a=Automation(':memory:',b,True)
    a.configure(AutoConfig(enabled=True,mode=mode,capital=1000000,confirmation='ENABLE LIVE ORDERS'),True)
    return a,b

def test_gates():
    a=Automation(':memory:',Broker(),False)
    with pytest.raises(ValueError): a.configure(AutoConfig(enabled=True,mode='live',confirmation='ENABLE LIVE ORDERS'),True)
    with pytest.raises(ValueError): a.configure(AutoConfig(enabled=True),False)
    a,b=armed()
    assert a.consider(dict(SETUP,mode='demo'),CONTRACT,QUOTE,NOW,True) is None
    assert a.consider(SETUP,CONTRACT,QUOTE,NOW,False) is None
    assert not b.calls

def test_premium_budget_and_liquidity():
    a,b=armed()
    for q in [dict(QUOTE,age=4),dict(QUOTE,bid=80),dict(QUOTE,oi=10)]:
        assert a.consider(SETUP,CONTRACT,q,NOW,True) is None
    assert a.consider(SETUP,dict(CONTRACT,type='PE'),QUOTE,NOW,True) is None
    assert a.consider(SETUP,dict(CONTRACT,days_to_expiry=2),QUOTE,NOW,True) is None
    a.config.capital=100000
    assert a.consider(SETUP,CONTRACT,QUOTE,NOW,True) is None
    assert not b.calls

def test_paper_rr():
    a,b=armed();a.consider(SETUP,CONTRACT,QUOTE,NOW,True)
    t=a.orders()[0];assert t['stop']==75 and t['target']==175
    a.prices({'NFO:'+CONTRACT['tradingsymbol']:dict(QUOTE,bid=175)})
    assert a.orders()[0]['pnl']==7500 and not b.calls

def test_duplicate_signals_concurrent():
    a,b=armed('live')
    with ThreadPoolExecutor(max_workers=8) as pool: list(pool.map(lambda _:a.consider(SETUP,CONTRACT,QUOTE,NOW,True),range(20)))
    assert len(b.calls)==1 and len(a.orders())==1

def test_timeout_not_retried():
    a,b=armed('live');b.timeout=True;a.consider(SETUP,CONTRACT,QUOTE,NOW,True)
    assert a.orders()[0]['state']=='ENTRY_UNKNOWN' and not a.config.enabled
    with pytest.raises(ValueError): a.configure(AutoConfig(enabled=True,mode='live',confirmation='ENABLE LIVE ORDERS'),True)
    b.timeout=False;b.book[0].update(status='COMPLETE',filled_quantity=100,average_price=100)
    a.reconcile();a.reconcile()
    assert sum(c[0]=='place' and c[1]['transaction_type']=='BUY' for c in b.calls)==1
    assert a.orders()[0]['state']=='PROTECTED'

def test_target_reuses_protective_order():
    a,b=armed('live');a.consider(SETUP,CONTRACT,QUOTE,NOW,True)
    b.book[0].update(status='COMPLETE',filled_quantity=100,average_price=100)
    a.reconcile();a.reconcile();oid=a.orders()[0]['exit_id']
    for bid in [175,176]: a.prices({'NFO:'+CONTRACT['tradingsymbol']:dict(QUOTE,bid=bid)})
    assert len(b.book)==2 and [c[1]['order_id'] for c in b.calls if c[0]=='modify']==[oid]
    b.book[1].update(status='COMPLETE',filled_quantity=100,average_price=175)
    a.reconcile();assert a.orders()[0]['pnl']==7500

def test_protection_failure_pauses():
    a,b=armed('live');a.consider(SETUP,CONTRACT,QUOTE,NOW,True)
    b.book[0].update(status='COMPLETE',filled_quantity=100,average_price=100)
    a.reconcile();b.book[1]['status']='REJECTED';a.reconcile();a.reconcile()
    assert not a.config.enabled and a.orders()[0]['state']=='EMERGENCY_PENDING' and len(b.book)==3
    assert b.book[2]['tag'].startswith('x') and b.book[2]['market_protection']==-1

def test_partial_fill():
    a,b=armed('live');a.consider(SETUP,CONTRACT,QUOTE,NOW,True)
    b.book[0].update(filled_quantity=50,average_price=100)
    a.reconcile();a.reconcile();a.reconcile()
    assert sum(c[0]=='cancel' for c in b.calls)==1 and b.book[1]['quantity']==50

def test_restart_and_identity(tmp_path):
    path=str(tmp_path/'auto.db');a=Automation(path,Broker(),True);a.bind_account('A')
    a.configure(AutoConfig(enabled=True),True);restored=Automation(path,Broker(),True)
    assert not restored.config.enabled
    with pytest.raises(ValueError): restored.bind_account('B')

def test_external_position_blocks_live():
    b=Broker();b.net=[dict(exchange='NFO',tradingsymbol='OTHER',quantity=100)]
    a=Automation(':memory:',b,True)
    with pytest.raises(ValueError): a.configure(AutoConfig(enabled=True,mode='live',confirmation='ENABLE LIVE ORDERS'),True)

def test_tick_freshness():
    live=KiteLive(DEFAULT_RULES,':memory:',client=Broker());live.tokens={1:'NSE:TEST'}
    live.on_ticks(None,[dict(instrument_token=1,last_price=100)])
    live.on_ticks(None,[dict(instrument_token=1,last_price=100,exchange_timestamp=datetime(2020,1,1))])
    assert live.quote_view()=={}

def test_authenticated_api(monkeypatch):
    from app import main
    from fastapi.testclient import TestClient
    monkeypatch.setattr(main,'API_TOKEN','x'*32)
    with TestClient(main.app) as c:
        headers={'Authorization':'Bearer '+'x'*32}
        assert c.get('/broker/status').status_code==401
        assert c.get('/broker/status',headers=headers).json()['mode']=='demo'
        assert c.post('/automation',headers=headers,json={'enabled':True}).status_code==409

def test_close_session_cancels_pending_buy_once():
    a,b=armed('live');a.consider(SETUP,CONTRACT,QUOTE,NOW,True)
    a.cancel_session_entries();a.cancel_session_entries();a.reconcile()
    assert sum(c[0]=='cancel' for c in b.calls)==1
    assert a.orders()[0]['state']=='REJECTED' and not a.config.enabled

def test_disabling_does_not_allow_mode_change_with_open_position():
    a,b=armed('live');a.consider(SETUP,CONTRACT,QUOTE,NOW,True)
    with pytest.raises(ValueError): a.configure(AutoConfig(enabled=False,mode='paper'),False)

def test_target_modification_timeout_never_creates_another_sell():
    a,b=armed('live');a.consider(SETUP,CONTRACT,QUOTE,NOW,True)
    b.book[0].update(status='COMPLETE',filled_quantity=100,average_price=100)
    a.reconcile();a.reconcile()
    def timeout(**kw): raise TimeoutError()
    b.modify_order=timeout
    a.prices({'NFO:'+CONTRACT['tradingsymbol']:dict(QUOTE,bid=175)})
    a.reconcile();a.prices({'NFO:'+CONTRACT['tradingsymbol']:dict(QUOTE,bid=176)})
    assert len(b.book)==2 and not a.config.enabled

def test_live_api_snapshot_and_tick_stream_without_network(monkeypatch):
    from app import main
    from fastapi.testclient import TestClient
    a,b=armed()
    result=dict(main.analyse('INFY'),mode='kite')
    class Session:
        results={'INFY':result}
        connected=True
        auto=a
        def start(self): pass
        async def stop(self): pass
        def ready(self): return True
        def status(self): return dict(mode='kite',ready=True,feed_connected=True)
        def quote_view(self): return {'NSE:INFY':dict(price=1234,age=.01,exchange_time=NOW.isoformat())}
    monkeypatch.setattr(main,'service',Session());monkeypatch.setattr(main,'MODE','kite')
    with TestClient(main.app) as c:
        assert c.get('/scan').json()['items'][0]['price']==1234
        assert c.get('/broker/status').json()['ready']
        with c.websocket_connect('/live') as ws:
            assert ws.receive_json()['mode']=='kite'
            msg=ws.receive_json()
            assert msg['type']=='ticks' and msg['quotes']['NSE:INFY']['age_ms']==10

def test_daily_loss_limit_disarms():
    a,b=armed();ident=a.consider(SETUP,CONTRACT,QUOTE,NOW,True)
    a.save(ident,state='CLOSED',pnl=-30000)
    assert a.consider(dict(SETUP,symbol='SECOND'),CONTRACT,QUOTE,NOW,True) is None
    assert not a.config.enabled

def test_kite_sdk_host_local_timestamp_is_not_reinterpreted_as_ist():
    live=KiteLive(DEFAULT_RULES,':memory:',client=Broker());live.tokens={1:'NSE:TEST'}
    stamp=datetime.now() # Exactly how KiteTicker.fromtimestamp represents the epoch.
    live.on_ticks(None,[dict(instrument_token=1,last_price=100,exchange_timestamp=stamp)])
    assert live.quote_view()['NSE:TEST']['age']<3
    live.on_ticks(None,[dict(instrument_token=1,last_price=90,exchange_timestamp=stamp.replace(microsecond=0))])
    assert live.quote_view()['NSE:TEST']['price']==100

def test_public_callback_does_not_reflect_tokens_or_bypass_api_auth(monkeypatch):
    from app import main
    from fastapi.testclient import TestClient
    monkeypatch.setattr(main,'API_TOKEN','x'*32)
    with TestClient(main.app) as c:
        r=c.get('/kite/callback?request_token=private-test-value&status=success')
        assert r.status_code==200
        assert 'private-test-value' not in r.text
        assert r.headers['cache-control']=='no-store'
        assert r.headers['referrer-policy']=='no-referrer'
        assert c.get('/broker/status').status_code==401
        assert c.post('/kite/callback').status_code==401
