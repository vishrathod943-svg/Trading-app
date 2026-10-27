from app.ict import analyse_ict

def bars(values):
    return [dict(time=f'2026-01-{i+1:02}',open=o,high=h,low=l,close=c) for i,(o,h,l,c) in enumerate(values)]

def test_gap_fill_only_after_creation():
    c=bars([(9,10,8,9),(11,12,10,11),(14,15,13,14),(13,14,9,10)])
    z=analyse_ict(c)['zones'][0]
    assert z['kind']=='FVG' and z['low']==10 and z['high']==13
    assert analyse_ict(c[:3])['zones'][0]['filled_at'] is None
    assert z['filled_at']==3

def test_pivot_confirmation_break_and_sweep():
    c=bars([(8,9,7,8),(9,10,8,9),(10,12,9,11),(10,11,8,9),(9,10,7,8),(11,13,10,11),(12,14,11,13)])
    assert not analyse_ict(c[:4])['events']
    events=analyse_ict(c)['events']
    assert events[0]['kind']=='Liquidity sweep' and events[0]['index']==5
    assert events[1]['kind']=='BOS' and events[1]['index']==6
    for n in range(1,len(c)+1):
        assert analyse_ict(c[:n])['events']==[e for e in events if e['index']<n]

def test_empty_has_no_invented_range():
    assert analyse_ict([])['dealing_range'] is None
