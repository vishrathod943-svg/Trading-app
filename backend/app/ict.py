"""Causal, explicit daily-bar ICT heuristics; never an execution signal."""
def analyse_ict(candles):
    events=[]; zones=[]; swings={'high':None,'low':None}; broken=set(); trend=None
    def event(kind,i,price,direction,origin):
        events.append(dict(kind=kind,index=i,time=candles[i]['time'],price=price,direction=direction,origin_index=origin))
    for i,c in enumerate(candles):
        # A two-bar pivot becomes available only after both right bars close.
        p=i-2
        if p>=2:
            window=candles[p-2:p+3]
            for side,compare in [('high',max),('low',min)]:
                value=candles[p][side]
                if value==compare(x[side] for x in window) and sum(x[side]==value for x in window)==1:
                    swings[side]=(p,value)
        if i>=2:
            a=candles[i-2]
            if c['low']>a['high']:
                zones.append(dict(kind='FVG',direction='bullish',start=i,low=a['high'],high=c['low'],filled_at=None))
            if c['high']<a['low']:
                zones.append(dict(kind='FVG',direction='bearish',start=i,low=c['high'],high=a['low'],filled_at=None))
        for z in zones:
            if i>z['start'] and z['filled_at'] is None:
                if (z['direction']=='bullish' and c['low']<=z['low']) or (z['direction']=='bearish' and c['high']>=z['high']):z['filled_at']=i
        for side,direction in [('high','bullish'),('low','bearish')]:
            pivot=swings[side]
            if not pivot or (side,pivot[0]) in broken:continue
            origin,level=pivot
            crossed=c['close']>level if side=='high' else c['close']<level
            swept=c['high']>level and c['close']<=level if side=='high' else c['low']<level and c['close']>=level
            if crossed:
                event('CHoCH' if trend and trend!=direction else 'BOS',i,level,direction,origin)
                trend=direction;broken.add((side,origin))
                for j in range(i-1,max(origin-1,i-11),-1):
                    b=candles[j]
                    if (b['close']<b['open'] if direction=='bullish' else b['close']>b['open']):
                        zones.append(dict(kind='OB candidate',direction=direction,start=i,origin_index=j,low=b['low'],high=b['high'],filled_at=None));break
            elif swept:event('Liquidity sweep',i,level,'bearish' if side=='high' else 'bullish',origin)
    dealing=None
    if all(swings.values()):
        lo=swings['low'][1];hi=swings['high'][1]
        if hi>lo:dealing=dict(low=lo,high=hi,equilibrium=(lo+hi)/2)
    return dict(timeframe='1D',basis='Completed daily candles only; live quotes do not form intraday bars',events=events,zones=zones,dealing_range=dealing,
        rules='Unique 2-left/2-right pivots confirmed after 2 bars; close breaks = BOS/CHoCH; wick rejection = sweep; three-bar wick gaps = FVG; last opposite candle within 10 bars before break = OB candidate. Full gap traversal marks a zone filled.',
        limitations=['Heuristic research labels, not validated trade confirmations','No intraday kill zones, opening ranges, SMT divergence, breaker or mitigation-block detection','Range uses latest confirmed swing high/low; not a higher-timeframe bias'])
