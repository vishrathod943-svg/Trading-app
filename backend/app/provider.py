"""Provider boundary. Demo is deterministic synthetic history, NOT exchange prices."""
from typing import Protocol
from datetime import date, timedelta
import random
from .analysis import Candle

UNIVERSE=[('RELIANCE','Energy','NSE'),('HDFCBANK','Banking','NSE'),('INFY','Technology','NSE'),('TCS','Technology','NSE'),('ICICIBANK','Banking','NSE'),('SBIN','Banking','NSE'),('LT','Industrials','NSE'),('ITC','Consumer','NSE')]
class MarketProvider(Protocol):
    def history(self,symbol:str)->list[Candle]: ...
    def option_chain(self,symbol:str)->list[dict]: ...

class DemoProvider:
    mode='demo'
    def history(self,symbol):
        rng=random.Random(symbol); price=800+rng.random()*1800; candles=[]
        day=date(2023,1,2)
        while len(candles)<800:
            day+=timedelta(days=1)
            if day.weekday()>4: continue
            change=rng.gauss(.0006,.017); opening=price; price*=1+change
            candles.append(Candle(str(day),round(opening,2),round(max(opening,price)*(1+rng.uniform(.001,.012)),2),round(min(opening,price)*(1-rng.uniform(.001,.012)),2),round(price,2),rng.randint(500000,3000000)))
        # No forced confirmations: the same rules screen synthetic history honestly.
        return candles
    def option_chain(self,symbol):
        return []  # Never manufacture executable option recommendations.

US_UNIVERSE=[('AAPL','Technology','SMART'),('MSFT','Technology','SMART'),('NVDA','Technology','SMART'),('TSLA','Consumer','SMART'),('AMZN','Consumer','SMART'),('META','Technology','SMART'),('SPY','ETF','SMART'),('QQQ','ETF','SMART'),('MES','Equity index futures','CME'),('MNQ','Equity index futures','CME'),('ES','Equity index futures','CME'),('NQ','Equity index futures','CME')]
US_FUTURES={'MES':(5,.25),'MNQ':(2,.25),'ES':(50,.25),'NQ':(20,.25)}
class USDemoProvider(DemoProvider):
    mode='us_demo'
    def history(self,symbol):
        source=super().history(symbol)
        anchor=20000 if symbol in ('MNQ','NQ') else 5500 if symbol in US_FUTURES else 250
        scale=anchor/source[-1].close
        # Explicitly synthetic prices. Anchor values are demo constants, not quotes.
        return [Candle(c.time,round(c.open*scale,2),round(c.high*scale,2),round(c.low*scale,2),round(c.close*scale,2),c.volume) for c in source]
    def metadata(self,symbol):
        row=next(x for x in US_UNIVERSE if x[0]==symbol)
        multiplier,tick=US_FUTURES.get(symbol,(1,.01))
        return dict(symbol=symbol,sector=row[1],exchange=row[2],currency='USD',security_type='FUT' if symbol in US_FUTURES else 'STK',
            local_symbol=symbol+' · DEMO',con_id=0,multiplier=multiplier,min_tick=tick,tick_value=multiplier*tick,
            expiry='SYNTHETIC' if symbol in US_FUTURES else None,timezone='America/New_York',liquid_hours='Synthetic; no market-hours guarantee')
