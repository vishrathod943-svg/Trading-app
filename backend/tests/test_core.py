import pytest
from app.analysis import position_size, ema, indicators, backtest, DEFAULT_RULES, select_option
from app.provider import DemoProvider
from app.engine import Engine
from fastapi.testclient import TestClient

def plan(): return dict(entry=100,stop=95,target1=107.5,target2=115)
@pytest.fixture
def engine(): return Engine(':memory:')
def test_ema_and_causal_indicators():
    assert ema([10]*20,5)==pytest.approx([10]*20)
    c=DemoProvider().history('INFY')
    first=indicators(c[:300]); c[-1]=c[0]
    assert indicators(c[:300])==first
    assert 0<=first['rsi']<=100 and first['atr']>0

def test_sizing():
    assert position_size(100000,1,100,95)['units']==200
    assert position_size(100,1,100,95,50)['units']==0
    with pytest.raises(ValueError): position_size(10000,3,100,95)

def test_duplicate_ticks_and_targets(engine):
    t=engine.create('TEST','LONG',plan())
    for p in [100,100,108,108,115,115]: engine.tick(t['id'],p)
    events=[x['event'] for x in engine.alerts()]
    assert events.count('ENTRY_TRIGGERED')==1 and events.count('T1_HIT')==1
    assert engine.trades()[0]['state']=='T2_HIT'

def test_wicks_and_gap(engine):
    t=engine.create('TEST','LONG',plan())
    assert engine.tick(t['id'],100,candle_close=False)['state']=='WAITING_ENTRY'
    assert engine.tick(t['id'],103)['state']=='EXPIRED'
    assert any(e['event']=='GAP' and e['price']==103 for e in engine.alerts())

def test_simultaneous_stop_target_stop_first(engine):
    t=engine.create('TEST','LONG',plan()); engine.tick(t['id'],100)
    assert engine.tick(t['id'],110,high=116,low=94)['state']=='SL_HIT'

def test_short_gap_stop(engine):
    t=engine.create('SHORT','SHORT',dict(entry=100,stop=105,target1=92.5,target2=85))
    engine.tick(t['id'],100)
    assert engine.tick(t['id'],108)['state']=='SL_HIT'
    assert next(e for e in engine.alerts() if e['event']=='SL_HIT')['price']==108

def test_small_samples_hidden():
    bt=backtest(DemoProvider().history('INFY'),DEFAULT_RULES)
    if bt['sample_size']<20: assert bt['win_rate'] is None

def test_no_option_without_liquidity():
    assert select_option([], 'LONG') is None

def test_api(tmp_path,monkeypatch):
    from app import main
    monkeypatch.setattr(main,'engine',Engine(str(tmp_path/'test.db')))
    with TestClient(main.app) as client:
        assert client.get('/health').json()['mode']=='demo'
        data=client.get('/scan').json(); assert len(data['items'])==8
        assert client.get('/stock/INFY').json()['candles']
        assert client.get('/stock/FAKE').status_code==404
        assert client.post('/replay/demo').json()['trade']['state']=='T2_HIT'
        assert len(client.get('/alerts').json())>=4
        assert client.post('/position-size',json=dict(capital=100000,risk_pct=1,entry=100,stop=95)).json()['units']==200
        with client.websocket_connect('/live') as ws: assert ws.receive_json()['type']=='snapshot'

def test_rules_validation():
    from app.rules import Rules
    assert Rules().weights.setup==30
    with pytest.raises(ValueError): Rules.model_validate({'weights':{'setup':99}})
    with pytest.raises(ValueError): Rules.model_validate({'bullish_rsi_min':90,'bullish_rsi_max':20})

def test_active_limits_and_cancel(engine):
    for n in range(5): engine.create(str(n),'LONG',plan())
    with pytest.raises(ValueError): engine.create('six','LONG',plan())
    engine.cancel(1)
    engine.create('six','LONG',plan())
    engine.cancel(1)
    assert sum(e['event']=='CANCELLED' for e in engine.alerts())==1

def test_persistence(tmp_path):
    p=str(tmp_path/'paper.db'); e=Engine(p)
    t=e.create('TEST','LONG',plan()); e.tick(t['id'],100)
    restored=Engine(p)
    assert restored.trades()[0]['state']=='ENTRY_TRIGGERED'
    restored.tick(t['id'],100)
    assert sum(e['event']=='ENTRY_TRIGGERED' for e in restored.alerts())==1

def test_actual_fills_and_pnl(engine):
    t=engine.create('FILL','LONG',plan(),quantity=10)
    t=engine.tick(t['id'],101)
    assert t['fill_entry']==101 and t['pnl']==0
    t=engine.tick(t['id'],93)
    assert t['exit_price']==93 and t['pnl']==-80 and t['pnl_kind']=='realized'
