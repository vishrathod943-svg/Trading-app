import asyncio
from datetime import date,datetime,timedelta,timezone
from types import SimpleNamespace as NS
import math
import pytest
from eventkit import Event
from ib_async import Contract
from app.us_market import InstrumentSpec,load_watchlist,select_future,build_analysis,futures_risk
from app.ibkr_live import IBKRLive,ResearchOnly
from app.analysis import DEFAULT_RULES
from app.provider import DemoProvider,USDemoProvider
from app.engine import Engine

def details(symbol='MES',expiry='20500315',cid=1):
    c=Contract(secType='FUT',symbol=symbol,exchange='CME',currency='USD',conId=cid,localSymbol=symbol+'H0',multiplier='5',lastTradeDateOrContractMonth=expiry)
    return NS(contract=c,realExpirationDate=expiry,minTick=.25,timeZoneId='US/Central',liquidHours='')

def test_future_selection_and_ambiguous_rejection():
    a=details(expiry='20261120',cid=1);b=details(expiry='20261218',cid=2)
    assert select_future([b,a],'MES',date(2026,11,17)) is b
    with pytest.raises(ValueError):select_future([a],'MES',date(2026,11,17))
    with pytest.raises(ValueError):select_future([a,details(expiry='20261120',cid=3)],'MES',date(2026,10,1))

def test_watchlist_validation(tmp_path):
    assert len(load_watchlist())==12
    path=tmp_path/'watch.json';path.write_text('[{"symbol":"MES","security_type":"FUT","exchange":"SMART"}]')
    with pytest.raises(ValueError):load_watchlist(path)

def test_us_short_history_retains_quotes_metadata_without_fake_indicators():
    p=USDemoProvider();m=p.metadata('MES');a=build_analysis('MES',m,p.history('MES')[:100],DEFAULT_RULES)
    assert a['currency']=='USD' and a['security_type']=='FUT'
    assert not a['confirmed'] and not a['indicators'] and a['plan'] is None

def test_multiplier_risk_and_tick_alignment():
    r=futures_risk(10000,1,5500,5495,5,.25)
    assert r['contracts']==4 and r['risk_per_contract']==25 and r['tick_value']==1.25
    assert r['margin_verified'] is False
    for args in [(10000,1,5500.1,5495,5,.25),(10000,3,5500,5495,5,.25),(math.inf,1,5500,5495,5,.25)]:
        with pytest.raises(ValueError):futures_risk(*args)

def test_paper_pnl_in_usd_uses_multiplier(tmp_path):
    e=Engine(str(tmp_path/'paper.db'))
    t=e.create('MES','LONG',dict(entry=100,stop=95,target1=107.5,target2=115),currency='USD',multiplier=5)
    e.tick(t['id'],100);t=e.tick(t['id'],115)
    assert t['pnl']==75 and t['currency']=='USD'
    assert Engine(str(tmp_path/'paper.db')).trades()[0]['multiplier']==5
    assert e.alerts()[0]['currency']=='USD'

class FakeIB:
    def __init__(self):
        self.pendingTickersEvent=Event();self.disconnectedEvent=Event();self.errorEvent=Event()
        self.connected=False;self.connect_args=None;self.tickers=[];self.cancelled=[]
    async def connectAsync(self,host,port,**kwargs):self.connect_args=kwargs;self.connected=True
    def isConnected(self):return self.connected
    def disconnect(self):self.connected=False
    def reqMarketDataType(self,value):self.requested_type=value
    async def reqContractDetailsAsync(self,c):
        if c.secType=='FUT':return [details(c.symbol)]
        c.conId=2;c.localSymbol=c.symbol
        return [NS(contract=c,minTick=.01,timeZoneId='US/Eastern',liquidHours='')]
    def reqMktData(self,c,**kwargs):
        self.request_kwargs=kwargs
        t=NS(contract=c,time=datetime.now(timezone.utc),last=100,bid=99,ask=101,volume=10000,futuresOpenInterest=3000,marketDataType=3)
        self.tickers.append(t);return t
    def cancelMktData(self,c):self.cancelled.append(c.conId)
    async def reqHistoricalDataAsync(self,c,**kwargs):
        return [NS(date=date.fromisoformat(x.time),open=x.open,high=x.high,low=x.low,close=x.close,volume=x.volume) for x in DemoProvider().history(c.symbol)[-220:]]
    def placeOrder(self,*args):raise AssertionError('Read-only adapter attempted an order')

def test_delayed_frozen_unknown_and_stale_quotes_never_claim_live(monkeypatch):
    live=IBKRLive(DEFAULT_RULES,FakeIB());live.connected=True;live.complete=True;live.by_id={1:'CME:MES'}
    t=NS(contract=details().contract,time=datetime.now(timezone.utc),last=5500,bid=5499.75,ask=5500,volume=5,futuresOpenInterest=100,marketDataType=3)
    for dtype in (3,4,2,99):
        t.marketDataType=dtype;live.on_tickers([t]);assert not live.ready()
    t.marketDataType=1;live.on_tickers([t]);assert live.ready()
    assert live.quote_view()['CME:MES']['timestamp_basis']=='broker_receive'
    t.time=datetime.now(timezone.utc)-timedelta(seconds=60);t.last=200
    live.on_tickers([t]);assert live.quote_view()['CME:MES']['price']==5500
    live.on_disconnect();assert not live.ready() and not live.quote_view()

def test_missing_last_does_not_fabricate_a_close_price():
    live=IBKRLive(DEFAULT_RULES,FakeIB());live.by_id={1:'CME:MES'}
    t=NS(contract=details().contract,time=datetime.now(timezone.utc),last=math.nan,bid=math.nan,ask=math.nan,volume=math.nan,futuresOpenInterest=math.nan,marketDataType=1)
    live.on_tickers([t]);assert live.quote_view()['CME:MES']['price'] is None
    assert not live.ready()

def test_read_only_lifecycle_and_contract_metadata():
    async def scenario():
        fake=FakeIB();live=IBKRLive(DEFAULT_RULES,fake)
        live.specs=[InstrumentSpec(symbol='MES',security_type='FUT',exchange='CME')]
        live.start()
        try:
            for _ in range(300):
                if live.complete:break
                await asyncio.sleep(.01)
            assert live.complete and fake.connect_args['readonly'] is True
            assert fake.requested_type==1
            assert fake.connect_args['clientId']!=0
            assert fake.connect_args['fetchFields'].value==0
            assert live.results['MES']['contract']['multiplier']==5
            live.on_tickers(fake.tickers)
            assert live.status()['data_types']['delayed']==1
            assert live.auto.status()['live_allowed'] is False
        finally:await live.stop()
    asyncio.run(scenario())

def test_broker_errors_are_sanitized():
    live=IBKRLive(DEFAULT_RULES,FakeIB());live.on_error(1,354,'private-account-value',details().contract)
    assert 'private-account-value' not in str(live.status())

def test_ibkr_research_api_and_browser_socket(monkeypatch,tmp_path):
    from app import main
    from fastapi.testclient import TestClient
    p=USDemoProvider();result=build_analysis('MES',p.metadata('MES'),[],DEFAULT_RULES)
    class Session:
        results={'MES':result};connected=True;auto=ResearchOnly()
        def start(self):pass
        async def stop(self):pass
        def ready(self):return False
        def status(self):return dict(mode='ibkr',read_only=True,ready=False,feed_connected=True)
        def quote_view(self):return {'CME:MES':dict(price=5500,bid=5499.75,ask=5500,age=.1,exchange_time=datetime.now(timezone.utc).isoformat(),data_type='delayed',timestamp_basis='broker_receive')}
    monkeypatch.setattr(main,'service',Session());monkeypatch.setattr(main,'MODE','ibkr');monkeypatch.setattr(main,'API_TOKEN','x'*32)
    with TestClient(main.app) as c:
        headers={'Authorization':'Bearer '+'x'*32}
        assert c.get('/app').status_code==200
        assert c.get('/scan').status_code==401
        assert c.get('/scan',headers=headers).json()['items'][0]['data_type']=='delayed'
        assert c.post('/automation',headers=headers,json={'enabled':True}).status_code==409
        assert c.post('/trades',headers=headers,json={'symbol':'MES'}).status_code==409
        risk=c.post('/futures-risk',headers=headers,json=dict(symbol='MES',capital=10000,risk_pct=1,entry=5500,stop=5495)).json()
        assert risk['contracts']==4
        with c.websocket_connect('/live',headers={'Origin':'http://testserver'}) as ws:
            ws.send_json({'type':'auth','token':'x'*32})
            assert ws.receive_json()['mode']=='ibkr'
            assert ws.receive_json()['quotes']['CME:MES']['data_type']=='delayed'
        with pytest.raises(Exception):
            with c.websocket_connect('/live',headers={'Origin':'https://wrong.example'}) as ws:ws.receive_json()

def test_stale_history_cannot_confirm_live_setup(monkeypatch):
    import app.us_market as market
    monkeypatch.setattr(market,'direction_for',lambda *args:'LONG')
    p=USDemoProvider();candles=p.history('MES')
    from dataclasses import replace
    candles=[replace(c,time=(date(2000,1,1)+timedelta(days=n)).isoformat()) for n,c in enumerate(candles)]
    a=market.build_analysis('MES',p.metadata('MES'),candles,dict(DEFAULT_RULES,min_score=0),'ibkr')
    assert not a['confirmed'] and a['plan'] is None
    assert any('stale' in s for s in a['warnings'])

def test_us_private_config_does_not_request_or_write_broker_password(tmp_path):
    import importlib.util
    from pathlib import Path
    path=Path(__file__).resolve().parents[2]/'scripts/configure-us.py'
    spec=importlib.util.spec_from_file_location('configure_us',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    dest=tmp_path/'private/us.env'
    module.configure(dest,'example.duckdns.org')
    first=dest.read_text();token=next(l for l in first.splitlines() if l.startswith('FO_API_TOKEN='))
    assert 'FO_MODE=us_demo' in first and 'FO_LIVE_ORDERS=false' in first
    assert 'PASSWORD' not in first and (dest.stat().st_mode & 0o777)==0o600
    module.configure(dest,'example.duckdns.org','ibkr',4002)
    assert token in dest.read_text() and 'FO_MODE=ibkr' in dest.read_text()
    with pytest.raises(ValueError):module.configure(dest,'example.duckdns.org','ibkr',4001)


@pytest.mark.parametrize('requested,code',[('delayed',3),('delayed_frozen',4)])
def test_requested_delayed_feed_stays_read_only(monkeypatch,requested,code):
    monkeypatch.setenv('IBKR_DATA_TYPE',requested)
    async def scenario():
        fake=FakeIB();live=IBKRLive(DEFAULT_RULES,fake)
        live.specs=[InstrumentSpec(symbol='MES',security_type='FUT',exchange='CME')]
        live.start()
        try:
            for _ in range(300):
                if live.complete:break
                await asyncio.sleep(.01)
            assert live.complete and fake.requested_type==code
            assert fake.connect_args['readonly'] is True
            assert fake.request_kwargs['genericTickList']==''
            live.on_tickers(fake.tickers)
            assert live.status()['requested_data_type']==requested
            assert live.status()['data_types']['delayed']==1
            assert not live.ready() and not live.auto.status()['live_allowed']
        finally:await live.stop()
    asyncio.run(scenario())


def test_delayed_setting_preserves_tokens_and_survives_reconfigure(tmp_path):
    import importlib.util
    from pathlib import Path
    path=Path(__file__).resolve().parents[2]/'scripts/configure-us.py'
    spec=importlib.util.spec_from_file_location('configure_us_delayed',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    dest=tmp_path/'private/us.env';module.configure(dest,'example.duckdns.org','ibkr')
    token=next(l for l in dest.read_text().splitlines() if l.startswith('FO_API_TOKEN='))
    module.configure(dest,'example.duckdns.org','ibkr',data_type='delayed')
    assert token in dest.read_text() and 'IBKR_DATA_TYPE=delayed' in dest.read_text()
    module.configure(dest,'example.duckdns.org','ibkr')
    assert 'IBKR_DATA_TYPE=delayed' in dest.read_text() and 'FO_LIVE_ORDERS=false' in dest.read_text()
    original=dest.read_text()
    with pytest.raises(ValueError):module.configure(dest,'example.duckdns.org','ibkr',data_type='invalid')
    assert dest.read_text()==original


def test_competing_session_error_is_distinguished():
    live=IBKRLive(DEFAULT_RULES,FakeIB());live.on_error(1,10197,'private-account-value')
    assert 'Competing' in live.status()['request_errors'][0]['reason']
    assert 'private-account-value' not in str(live.status())
