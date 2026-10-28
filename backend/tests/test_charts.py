import asyncio
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace as NS
import pytest
from app.charts import clean_bars,demo_chart,BrokerCharts

def bar(t):return NS(date=t,open=100,high=102,low=99,close=101,volume=0)

def test_completed_bars_validation():
    now=datetime(2026,10,28,12,tzinfo=timezone.utc)
    good=bar(now-timedelta(minutes=5));bad=bar(now-timedelta(minutes=10));bad.high=90
    result=clean_bars([good,good,bad,bar(now),bar(now.replace(tzinfo=None))],300,now)
    assert len(result)==1 and result[0]['volume']==0
    assert result[0]['time']==good.date.isoformat()

def test_demo_chart_labels():
    result=demo_chart('MES','5m',5500)
    assert result['source']=='synthetic' and len(result['candles'])==240
    assert result['ict']['timeframe']=='5m' and '5m' in result['ict']['basis']
    assert 'SYNTHETIC' in result['warning_demo']

def test_broker_cache_and_failure():
    async def run():
        class IB:
            calls=0
            def isConnected(self):return True
            async def reqHistoricalDataAsync(self,*args,**kwargs):
                self.calls+=1
                assert kwargs['barSizeSetting']=='5 mins' and not kwargs['useRTH']
                return [bar(datetime.now(timezone.utc)-timedelta(minutes=10))]
        s=NS(ib=IB(),connected=True,contracts={'MES':NS(conId=123)})
        charts=BrokerCharts();result=await charts.get(s,'MES','5m')
        assert result['source']=='ibkr_historical'
        assert await charts.get(s,'MES','5m') is result and s.ib.calls==1
        s.connected=False
        with pytest.raises(ValueError,match='disconnected'):await charts.get(s,'MES','5m')
        s.connected=True
        async def fail(*a,**k):raise RuntimeError('private broker detail')
        s.ib.reqHistoricalDataAsync=fail;charts.next_request=0
        with pytest.raises(ValueError,match='no simulated fallback') as e:await charts.get(s,'MES','1m')
        assert 'private' not in str(e.value)
        with pytest.raises(ValueError,match='no simulated fallback'):await charts.get(s,'MES','1m')
    asyncio.run(run())

def test_chart_api(monkeypatch):
    import app.main as m
    from fastapi.testclient import TestClient
    from app.provider import USDemoProvider
    monkeypatch.setattr(m,'API_TOKEN','test-token');monkeypatch.setattr(m,'MODE','us_demo')
    monkeypatch.setattr(m,'service',None);monkeypatch.setattr(m,'provider',USDemoProvider());monkeypatch.setattr(m,'cache',{})
    with TestClient(m.app) as c:
        h={'Authorization':'Bearer test-token'}
        assert c.get('/chart/MES').status_code==401
        assert c.get('/chart/MES?timeframe=2m',headers=h).status_code==422
        assert c.get('/chart/UNKNOWN?timeframe=5m',headers=h).status_code==404
        assert c.get('/chart/MES?timeframe=1m',headers=h).json()['source']=='synthetic'
        assert c.get('/chart/MES?timeframe=1D',headers=h).json()['ict']['timeframe']=='1D'
