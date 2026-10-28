from datetime import datetime,timedelta,timezone
import pytest
import app.paper_auto as module
from app.paper_auto import PaperAuto,signal

NOW=datetime(2026,10,28,15,tzinfo=timezone.utc)
CONFIG=dict(symbol='AAPL',timeframe='5m',capital=1000,risk_pct=.5,rr=2)
META=dict(security_type='STK',min_tick=.01,multiplier=1,con_id=1)
QUOTE=dict(price=100,data_type='delayed',age=1)

def bars(count):
    start=NOW-timedelta(minutes=190)
    return [dict(time=(start+timedelta(minutes=5*i)).isoformat(),open=100,high=100.2,low=99.9,close=100.1,volume=10) for i in range(count)]

def engine(tmp_path):
    e=PaperAuto(str(tmp_path/'auto.db'));e.configure(CONFIG);return e

def fixed_signal(candles,timeframe):
    return dict(direction='LONG',stop=99.5,signal_time=candles[-1]['time'],reason='test causal signal')

def open_position(e,monkeypatch):
    monkeypatch.setattr(module,'signal',fixed_signal)
    for count in (30,31,32):e.process(bars(count),META,QUOTE,NOW)
    return e.status()['trades'][-1]

def test_next_open_risk_and_stop_first(tmp_path,monkeypatch):
    e=engine(tmp_path);monkeypatch.setattr(module,'signal',fixed_signal)
    e.process(bars(30),META,QUOTE,NOW)
    assert not e.status()['trades'] and not e.status()['pending']
    e.process(bars(31),META,QUOTE,NOW)
    assert not e.status()['trades'] and e.status()['pending']['signal_time']==bars(31)[-1]['time']
    e.process(bars(32),META,QUOTE,NOW);t=e.status()['trades'][-1]
    assert t['entry']==100 and t['entry_time']>t['signal_time'] and t['state']=='OPEN'
    assert t['quantity']*(t['entry']-t['stop'])+2+.01*t['quantity']<=5
    assert t['quantity']*t['entry']<=1000
    fees=2+.01*t['quantity']
    assert (t['target']-t['entry'])*t['quantity']-fees>=2*t['planned_risk']-.01
    c=bars(33);c[-1].update(high=102,low=98)
    e.process(c,META,QUOTE,NOW);t=e.status()['trades'][-1]
    assert t['state']=='STOP' and t['pnl']<0
    e.process(c,META,QUOTE,NOW)
    assert len(e.status()['trades'])==1

@pytest.mark.parametrize('dtype',['live','frozen','delayed_frozen','synthetic','unknown'])
def test_only_delayed_quotes(tmp_path,dtype):
    e=engine(tmp_path);e.process(bars(30),META,dict(QUOTE,data_type=dtype),NOW)
    assert e.status()['cursor'] is None and not e.status()['trades']

def test_gap_restart_no_invented_exits(tmp_path,monkeypatch):
    e=engine(tmp_path);open_position(e,monkeypatch)
    e.process(bars(34),META,QUOTE,NOW)
    assert e.status()['trades'][-1]['state']=='DATA_GAP_UNRESOLVED'
    assert e.status()['trades'][-1]['exit_price'] is None
    assert not e.status()['enabled']
    with pytest.raises(ValueError,match='Unresolved'):e.configure(CONFIG)
    restarted=PaperAuto(str(tmp_path/'auto.db'))
    assert not restarted.status()['enabled'] and not restarted.status()['pending']

def test_day_limit_invalid_capital(tmp_path,monkeypatch):
    e=engine(tmp_path);monkeypatch.setattr(module,'signal',fixed_signal)
    e.process(bars(30),META,QUOTE,NOW)
    e.s['risk'].update(day=NOW.date().isoformat(),day_pnl=-20)
    e.process(bars(31),META,QUOTE,NOW)
    assert not e.status()['pending'] and 'limit' in e.status()['reason']
    e.pause()
    with pytest.raises(ValueError):e.configure(dict(CONFIG,capital=10000))

def test_incomplete_stale_bars(tmp_path):
    e=engine(tmp_path);c=bars(30);c[-1]['time']=NOW.isoformat();e.process(c,META,QUOTE,NOW)
    assert e.status()['cursor'] is None
    e.process(bars(30),META,QUOTE,NOW+timedelta(hours=2))
    assert e.status()['cursor'] is None

def test_signal_prefix_invariance():
    c=bars(35);original=signal(c[:30],'5m');c[-1].update(high=200,close=199)
    assert signal(c[:30],'5m')==original

def test_api_requires_delayed_stock(monkeypatch,tmp_path):
    from app import main
    from fastapi.testclient import TestClient
    e=PaperAuto(str(tmp_path/'api.db'))
    class Session:
        requested_data_type='live';results={'AAPL':{'security_type':'STK'}};connected=False
        def start(self):pass
        async def stop(self):pass
    session=Session()
    monkeypatch.setattr(main,'paper_auto',e);monkeypatch.setattr(main,'service',session)
    monkeypatch.setattr(main,'MODE','ibkr');monkeypatch.setattr(main,'API_TOKEN','private-test-token')
    with TestClient(main.app) as c:
        h={'Authorization':'Bearer private-test-token'}
        assert c.get('/paper-auto').status_code==401
        assert c.post('/paper-auto',headers=h,json=dict(CONFIG,enabled=True)).status_code==409
        session.requested_data_type='delayed'
        r=c.post('/paper-auto',headers=h,json=dict(CONFIG,enabled=True))
        assert r.status_code==200 and r.json()['simulation'] and not r.json()['orders_enabled']
        assert c.post('/paper-auto',headers=h,json=dict(CONFIG,enabled=True,risk_pct=2)).status_code==422
        assert not c.post('/paper-auto',headers=h,json={'enabled':False}).json()['enabled']
        from types import SimpleNamespace
        session.specs=[SimpleNamespace(symbol=s,security_type='STK') for s in ('AAPL','MSFT')]
        response=c.post('/paper-auto',headers=h,json=dict(CONFIG,symbol='ALL',enabled=True))
        assert response.status_code==200 and response.json()['config']['symbol']=='ALL'
        assert response.json()['eligible_symbols']==['AAPL','MSFT']


@pytest.mark.parametrize('field,value',[('day_pnl',-20),('entries',10),('losses',3)])
def test_each_risk_circuit_breaker(tmp_path,monkeypatch,field,value):
    e=engine(tmp_path);monkeypatch.setattr(module,'signal',fixed_signal)
    e.process(bars(30),META,QUOTE,NOW)
    e.s['risk'].update(day=NOW.date().isoformat());e.s['risk'][field]=value
    e.process(bars(31),META,QUOTE,NOW)
    assert not e.status()['pending'] and not e.status()['trades']


def test_entry_sizing_ignores_next_candle_extremes(tmp_path,monkeypatch):
    monkeypatch.setattr(module,'signal',fixed_signal)
    result=[]
    for n,(high,low) in enumerate([(100.2,99.9),(103,98)]):
        e=PaperAuto(str(tmp_path/f'{n}.db'));e.configure(CONFIG)
        e.process(bars(30),META,QUOTE,NOW);e.process(bars(31),META,QUOTE,NOW)
        c=bars(32);c[-1].update(high=high,low=low)
        e.process(c,META,QUOTE,NOW);t=e.status()['trades'][-1]
        result.append((t['entry'],t['quantity'],t['stop'],t['target']))
    assert result[0]==result[1]


def test_scalp_time_exit_after_30_minutes(tmp_path,monkeypatch):
    e=engine(tmp_path);open_position(e,monkeypatch)
    for count in range(33,38):e.process(bars(count),META,QUOTE,NOW)
    t=e.status()['trades'][0]
    assert t['state']=='TIME_EXIT' and t['exit_price']==100.1


def test_no_entries_or_signals_outside_regular_session(tmp_path,monkeypatch):
    e=engine(tmp_path);monkeypatch.setattr(module,'signal',fixed_signal)
    for count in (30,31):
        c=bars(count)
        for b in c:b['time']=(datetime.fromisoformat(b['time'])-timedelta(hours=6)).isoformat()
        e.process(c,META,QUOTE,NOW-timedelta(hours=6))
    assert not e.status()['trades'] and not e.status()['pending']



def test_all_symbols_share_one_position_and_balance(tmp_path,monkeypatch):
    e=PaperAuto(str(tmp_path/'multi.db'));e.configure(dict(CONFIG,symbol='ALL'))
    monkeypatch.setattr(module,'signal',fixed_signal)
    for count in (30,31,32):
        for symbol,cid in [('AAPL',1),('MSFT',2)]:
            e.process_symbol(symbol,bars(count),dict(META,con_id=cid),QUOTE,NOW)
    state=e.status();opened=[t for t in state['trades'] if t['state']=='OPEN']
    assert len(opened)==1 and opened[0]['symbol']=='AAPL'
    assert state['risk']['entries']==1 and state['risk']['balance']==1000
    assert set(state['symbol_states'])=={'AAPL','MSFT'}
    assert state['symbol_states']['MSFT']['cursor']==bars(32)[-1]['time']
    # A newly initialized symbol must not invalidate another symbol's open position.
    e.process_symbol('NVDA',bars(32),dict(META,con_id=3),QUOTE,NOW)
    assert e.status()['enabled'] and e.status()['trades'][0]['state']=='OPEN'
    c=bars(33);c[-1].update(low=98)
    e.process_symbol('AAPL',c,META,QUOTE,NOW)
    assert e.status()['risk']['balance']<1000
    assert e.status()['symbol_states']['MSFT']['cursor']==bars(32)[-1]['time']


def test_expanded_watchlist_is_valid_and_bounded():
    from app.us_market import load_watchlist
    from pathlib import Path
    specs=load_watchlist(Path(__file__).resolve().parents[2]/'deploy/us-watchlist.json')
    assert len(specs)==40
    assert sum(s.security_type=='STK' for s in specs)==36
    assert len({s.symbol for s in specs})==40



def test_no_overlapping_same_bar_entries_after_an_intrabar_exit(tmp_path,monkeypatch):
    e=PaperAuto(str(tmp_path/'overlap.db'));e.configure(dict(CONFIG,symbol='ALL'))
    monkeypatch.setattr(module,'signal',fixed_signal)
    for count in (30,31):
        for symbol,cid in [('AAPL',1),('MSFT',2)]:e.process_symbol(symbol,bars(count),dict(META,con_id=cid),QUOTE,NOW)
    c=bars(32);c[-1].update(high=104,low=98)
    for symbol,cid in [('AAPL',1),('MSFT',2)]:e.process_symbol(symbol,c,dict(META,con_id=cid),QUOTE,NOW)
    assert len(e.status()['trades'])==1 and e.status()['trades'][0]['state']=='STOP'
    assert e.status()['risk']['entries']==1
