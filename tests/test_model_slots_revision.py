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
