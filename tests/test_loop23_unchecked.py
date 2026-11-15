from duckcore import ink, inkcheck


def test_two_frame_line_is_unchecked_not_clean(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('A two-frame line cannot establish steady strokes')
    monkeypatch.setattr(ink, 'build', forbidden)
    edit = {'clean': [{'id': 'short', 'kind': 'fill',
                      'box': {'x': .1, 'y': .1, 'w': .4, 'h': .1},
                      'ranges': [{'start': 0, 'end': 2/30}]}]}
    result = inkcheck.check('unused', edit, {'width':320,'height':240,'fps':30}, source='unused')
    assert result['checked'] == 0
    assert result['frames'] == 0
    assert 'under 5 frames' in result['unchecked'][0]['reason']


def test_no_strokes_is_unchecked_not_clean(monkeypatch):
    monkeypatch.setattr(ink, 'build', lambda *args, **kwargs: None)
    edit = {'clean': [{'id':'no-strokes','kind':'fill',
                      'box':{'x':.1,'y':.1,'w':.4,'h':.1},
                      'ranges':[{'start':0,'end':2}]}]}
    result = inkcheck.check('unused', edit, {'width':320,'height':240,'fps':30}, source='unused')
    assert result['checked'] == result['frames'] == 0
    assert result['unchecked'][0]['reason'] == 'no steady strokes were found'
