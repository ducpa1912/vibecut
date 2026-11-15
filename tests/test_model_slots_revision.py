import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest
from duckcore import model_slots, app_settings


@pytest.mark.parametrize('task', ['transcription', 'voice'])
def test_choose_choose_clear_removes_owned_folders(tmp_path, task):
    root = tmp_path / 'root'
    for index in range(2):
        folder = root / 'models/slot-imports' / str(index)
        folder.mkdir(parents=True)
        if task == 'transcription':
            (folder/'config.json').write_text('{}')
            (folder/'weights.npz').write_bytes(b'weights')
        else:
            (folder/'kokoro-v1.0.onnx').write_bytes(b'model')
            with (folder/'voices-v1.0.bin').open('wb') as handle:
                np.savez(handle, voice=np.ones((2,3)))
        model_slots.configure(root, task, str(folder))
        assert not folder.exists()
        assert len(list((root/'models'/model_slots.DIRS[task]).iterdir())) == 1
    model_slots.configure(root, task, '')
    assert list((root/'models'/model_slots.DIRS[task]).iterdir()) == []
    assert list((root/'models/slot-imports').iterdir()) == []


def test_external_folder_never_deleted(tmp_path):
    source=tmp_path/'external';source.mkdir()
    (source/'config.json').write_text('{}');(source/'weights.npz').write_bytes(b'w')
    root=tmp_path/'root'
    app_settings.save(root, {'model_slots': {'transcription': {'path':str(source),'enabled':True}}})
    model_slots.configure(root,'transcription','')
    assert source.exists()


def test_settings_does_not_wait_for_unresponsive_server(tmp_path):
    release=threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self): release.wait(4)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    app_settings.save(tmp_path, {'model_slots': {'rewrite': {
        'path':f'http://127.0.0.1:{server.server_port}', 'provider':'rewrite.user', 'enabled':True}}})
    try:
        timings=[]
        for _ in range(3):
            start=time.monotonic();app_settings.snapshot(tmp_path);timings.append(time.monotonic()-start)
        print('Settings latency seconds:', timings)
        assert max(timings)<.3
    finally:
        release.set();server.shutdown();server.server_close();thread.join()


@pytest.mark.parametrize('refuses', [True, False])
def test_down_server_resolves_on_next_open(tmp_path, refuses):
    release=threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self): release.wait(5)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    url=f'http://127.0.0.1:{server.server_port}'
    thread=None
    if refuses: server.server_close()
    else:
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    app_settings.save(tmp_path, {'model_slots': {'rewrite': {'path':url,'enabled':True}}})
    try:
        start=time.monotonic()
        initial=model_slots.status(tmp_path,'rewrite')
        assert initial['checking'] and initial['problem']==''
        time.sleep(3)
        row=model_slots.status(tmp_path,'rewrite')
        assert not row.get('checking') and not row['ready'] and url in row['problem']
        print('Down server resolved on reopen:', refuses, time.monotonic()-start)
    finally:
        if thread:
            release.set();server.shutdown();server.server_close();thread.join()


def test_settings_displays_pending_and_ready_writing_state():
    from pathlib import Path
    import subprocess
    source=Path('static/duck/app.js').read_text()
    start=source.index('async function openSettings()')
    end=source.index('\n}',start)+2
    function=source[start:end]
    subprocess.run(['node','-e',function+'''
const assert=require('node:assert/strict');
let html='';const openModal=value=>{html=value;};
const esc=x=>String(x??'');const icon=()=>'';const engineLabel=()=>'';
const fmtBytes=()=>'';const packListMarkup=()=>'';
const state={voices:[{}],engine:{rewrite:{available:false}},models:[],packs:[],settings:{model_slots:{rewrite:{path:'http://localhost',checking:true,ready:false,problem:''}}}};
const api=async path=>path==='/api/settings'?state.settings:path==='/api/models'?{models:[]}:{packs:[]};
(async()=>{await openSettings();assert(html.includes('Checking…'));assert(!html.includes('Not usable · Checking'));
state.settings.model_slots.rewrite={path:'http://localhost',ready:true,file:'http://localhost'};
await openSettings();assert(html.includes('<span>Rewrite</span><strong>Your writing model</strong>'));})().catch(e=>{console.error(e);process.exit(1);});
'''],check=True)
