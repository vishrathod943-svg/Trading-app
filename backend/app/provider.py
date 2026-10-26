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
