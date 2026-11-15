import time
import builtins
import pytest
from duckcore import story, render
from duckcore.engine import textfill
from duckcore.engine.textfill import custom


def test_long_scenes_have_sentence_beats():
    check={'scenes':[{'id':n,'start':n*120,'end':(n+1)*120} for n in range(3)]}
    cues=[{'start':n*120+i*10,'end':n*120+i*10+10,'text':'A complete sentence.'} for n in range(3) for i in range(12)]
    result=story.write_story(check,{'segments':cues},model=lambda payload: {})
    assert 15 <= result['runtime'] <= 90
    assert all(any(b['start']==c['start'] and b['end']==c['end'] for c in cues) for b in result['beats'])
    assert story.fallback_story([])['reason']


def test_estimate_never_opens_custom_model(tmp_path,monkeypatch):
    p=tmp_path/'model.pt';p.write_bytes(b'PK\x03\x04'+b'x'*2048)
    monkeypatch.setattr(textfill,'custom_fill_model',lambda root:(p,None))
    calls=[]
    monkeypatch.setattr(custom,'open_filler',lambda folder:calls.append(folder))
    render._estimate_key({'id':'test'},{},tmp_path)
    render.estimate_edit({}, {}, tmp_path)
    assert calls == []


def test_bad_model_fails_at_fill_time(tmp_path,monkeypatch):
    p=tmp_path/'model.pt';p.write_bytes(b'PK\x03\x04'+b'x'*2048)
    monkeypatch.setattr(textfill,'custom_fill_model',lambda root:(p,None))
    monkeypatch.setattr(custom,'open_filler',lambda folder: (_ for _ in ()).throw(ValueError('Your fill model did not load: invalid archive.')))
    with pytest.raises(textfill.FillError,match='did not load'):
        textfill.prepare_span(source='unused',meta={'width':100,'height':100,'fps':30},
                              start=0,duration=1,layers=[{'box':{'x':.1,'y':.1,'w':.4,'h':.1}}],
                              method='lama',cache_dir=tmp_path/'fill',data_root=tmp_path)


@pytest.mark.parametrize('available',[False,True])
def test_onnx_import_cases(tmp_path,monkeypatch,available):
    (tmp_path/'model.onnx').write_bytes(b'x'*2048)
    original=builtins.__import__
    def importer(name,*args,**kwargs):
        if name=='onnxruntime':
            if not available: raise ImportError('absent')
            return object()
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',importer)
    assert (custom.problem(tmp_path) is None) == available


def test_background_story_returns_before_model(tmp_path, monkeypatch):
    import json
    from fastapi.testclient import TestClient
    from duckcore.main import create_app
    folder=tmp_path/'projects/prj_test';folder.mkdir(parents=True)
    (folder/'check.json').write_text(json.dumps({'scenes':[{'id':n,'start':n*10,'end':n*10+10} for n in range(3)],'meta':{'duration':30}}))
    def stub(*a,**k):
        time.sleep(.15)
        return {'beats':[{'scene_id':n,'start':n*10,'end':n*10+10,'seconds':10} for n in range(3)],'scene_ids':[0,1,2]}
    monkeypatch.setattr(story,'write_story',stub)
    with TestClient(create_app('token',tmp_path)) as client:
        headers={'Authorization':'Bearer token'}
        start=time.monotonic()
        row=client.post('/api/projects/prj_test/edits/story/write?background=true',headers=headers,json={'count':3}).json()
        assert time.monotonic()-start < 1
        assert row['state']=='working'
        for _ in range(100):
            row=client.get('/api/projects/prj_test/edits/story/jobs/'+row['id'],headers=headers).json()
            if row['state']!='working': break
            time.sleep(.01)
        assert row['state']=='done'


def test_player_scheduling_and_missing_paths():
    import re, subprocess
    from pathlib import Path
    source=Path('static/duck/app.js').read_text()
    names=['setupSequencePlayer','playRender','latestRender','doneCard','renderQueueRow','queueCard','screenWelcome']
    functions='\n'.join(re.search(r'(?:async )?function '+n+r'\([^\n]*\) \{.*?\n\}',source,re.S).group() for n in names)
    subprocess.run(['node','-e',functions+'''
const assert=require('node:assert/strict');
let pending, delay, advanced=0, opened=0;
global.setTimeout=(fn,ms)=>{pending=fn;delay=ms;return 1;};
global.clearTimeout=()=>{pending=null;};
const listeners={};
const video={currentTime:1,playbackRate:1,paused:false,seeking:false,isConnected:true,
 readyState:0,addEventListener:(n,fn)=>{(listeners[n] ||= []).push(fn);}};
const document={querySelector:()=>video};
const state={sequenceActive:true,sequenceIndex:0,sequenceSegments:[{start:0,end:3}],queue:[]};
const paintSequence=()=>{};const advanceSequence=()=>{advanced++;video.paused=true;};
const esc=x=>x;const toast=()=>{};const mediaUrl=x=>x;const openVideoModal=()=>opened++;
const icon=()=>'';const queueLabel=x=>x;const queueActiveCount=()=>0;const engineLabel=()=>'';
setupSequencePlayer();
const fire=n=>listeners[n].forEach(fn=>fn());
fire('ratechange');assert.equal(delay,2000);
video.playbackRate=2;fire('ratechange');assert.equal(delay,1000);
video.seeking=true;fire('seeking');assert.equal(pending,null);
video.currentTime=2;video.seeking=false;fire('seeked');assert.equal(delay,500);
video.paused=true;fire('pause');assert.equal(pending,null);
video.paused=false;fire('ratechange');pending();assert.equal(advanced,1);
const missing={id:'gone',project_id:'p',edit_id:'e',state:'done',output:'gone',output_missing:true};
state.queue=[missing];
state.projects=[];state.welcomeQuery='';
assert(!queueCard(missing).includes('play-render'));
assert(!screenWelcome().includes('play-render'));
assert.equal(latestRender(),null);
assert(!doneCard(missing).includes('play-render'));
assert(!renderQueueRow(missing).includes('play-render'));
playRender('p','e','gone');assert.equal(opened,0);
'''],check=True)
