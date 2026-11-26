import json
from pathlib import Path
import pytest
from duckcore import model_slots, app_settings


@pytest.mark.parametrize('task,files', [('transcription',{'config.json':'{}','weights.npz':'weights'}),
                                      ('voice',{'kokoro-v1.0.onnx':'model','voices-v1.0.bin':'voices'})])
def test_folder_valid_invalid_and_clear(tmp_path,task,files):
    source=tmp_path/'source';source.mkdir()
    root=tmp_path/'root'
    for name,value in files.items(): (source/name).write_text(value)
    if task=='voice':
        (source/model_slots.VOICE_FRONTEND).touch()
        import numpy as np
        with (source/'voices-v1.0.bin').open('wb') as handle:
            np.savez(handle, af_test=np.ones((2,3)))
    assert model_slots.configure(root,task,str(source))['ready']
    stored=app_settings.load(root)['model_slots'][task]
    assert stored['enabled'] and stored['provider']==task+'.user'
    assert Path(stored['path']).is_relative_to(root)
    assert set(stored)=={'path','provider','enabled'}
    last=list(files)[-1];(source/last).unlink()
    before=app_settings.load(root)
    with pytest.raises(ValueError,match='weights|voices'): model_slots.configure(root,task,str(source))
    assert app_settings.load(root)==before
    assert model_slots.configure(root,task,'')['path']==''


def test_writing_endpoint_and_unreachable(tmp_path,monkeypatch):
    calls=[]
    def request(base,endpoint,payload=None):
        calls.append(endpoint)
        return {'data':[{'id':'private-id'}]} if endpoint=='/v1/models' else {'choices':[{'message':{'content':'["Edited"]'}}]}
    monkeypatch.setattr(model_slots,'request',request)
    assert model_slots.configure(tmp_path,'rewrite','http://localhost:8000')['ready']
    assert model_slots.rewrite(tmp_path,['Original'],'clean')==['Edited']
    assert '/v1/chat/completions' in calls
    assert 'private-id' not in json.dumps(model_slots.status(tmp_path,'rewrite'))
    monkeypatch.setattr(model_slots,'request',lambda *a: (_ for _ in ()).throw(ValueError('Not reachable')))
    model_slots._status_cache.clear()
    assert not model_slots.status(tmp_path,'rewrite')['ready']


def test_transcription_uses_user_files(tmp_path,monkeypatch):
    import sys, types
    from duckcore.engine import stt
    source=tmp_path/'user';source.mkdir();(source/'config.json').write_text('{}');(source/'weights.npz').write_bytes(b'x')
    model_slots.configure(tmp_path,'transcription',str(source))
    job=tmp_path/'projects/prj_test';job.mkdir(parents=True)
    calls=[]
    def transcribe(path,**kwargs):
        calls.append(kwargs)
        return {'language':'vi','segments':[{'start':0,'end':1,'text':'Hello'}]}
    monkeypatch.setitem(sys.modules,'mlx_whisper',types.SimpleNamespace(transcribe=transcribe))
    result=stt.transcribe_source(job/'unused.wav',job,1,language='vi')
    assert result['provider']=='user-local'
    assert calls[0]['path_or_hf_repo']==model_slots.selected(tmp_path,'transcription')


def test_unset_rewrite_never_contacts_endpoint(tmp_path,monkeypatch):
    from duckcore import script, edits
    monkeypatch.setattr(model_slots,'request',lambda *a: pytest.fail('Unexpected HTTP'))
    monkeypatch.setattr(script,'_run',lambda *a:['Edited'])
    monkeypatch.setattr(edits,'save_edit',lambda *a:None)
    edit={'captions':{'cues':[{'text':'Original'}]}}
    script.rewrite(edit,tmp_path)
    assert edit['captions']['cues'][0]['text']=='Edited'


def test_voice_listing_and_synthesis_use_slot(tmp_path,monkeypatch):
    import numpy as np, sys, types
    from duckcore import voice
    folder=tmp_path/'user';folder.mkdir();(folder/'kokoro-v1.0.onnx').write_bytes(b'model')
    with (folder/'voices-v1.0.bin').open('wb') as handle: np.savez(handle, af_example=np.ones((2,3)))
    (folder/model_slots.VOICE_FRONTEND).touch()
    model_slots.configure(tmp_path,'voice',str(folder))
    monkeypatch.setattr(voice.subprocess,'run',lambda *a,**k:types.SimpleNamespace(stdout=''))
    assert voice.list_voices(tmp_path)[0]['label']=='Your voice · af_example'
    calls = []
    class Session:
        def __init__(self, path, providers):
            self.file = Path(path)
            assert self.file.parent == Path(model_slots.selected(tmp_path, 'voice'))
        def get_inputs(self):
            fields = [('text','string')] if self.file.name == 'tokenizer.onnx' else [
                ('input_ids','int64'), ('speed','float'), ('style','float')]
            return [types.SimpleNamespace(name=n, type=f'tensor({t})') for n,t in fields]
        def run(self, outputs, inputs):
            calls.append(inputs)
            if 'text' in inputs:
                return [np.array([[5, 7]])]
            return [np.zeros(16)]
    monkeypatch.setitem(sys.modules,'onnxruntime',types.SimpleNamespace(InferenceSession=Session))
    written = []
    monkeypatch.setitem(sys.modules,'soundfile',types.SimpleNamespace(write=lambda *args: written.append(args)))
    voice._synthesize('Text','user:af_example',tmp_path/'result.wav',tmp_path)
    assert calls[0]['text'].tolist() == ['Text']
    assert calls[1]['input_ids'].tolist() == [[0, 5, 7, 0]]
    assert calls[1]['style'].shape == (1,3)
    assert written[0][2] == 24000
    model_slots.configure(tmp_path,'voice','')
    assert voice.list_voices(tmp_path)==[]


def test_rewrite_with_loopback_server(tmp_path):
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a): pass
        def do_GET(self):
            self.send_response(200);self.end_headers();self.wfile.write(b'{"data":[{"id":"test-private"}]}')
        def do_POST(self):
            import time
            time.sleep(3)
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert body['model']=='test-private'
            self.send_response(200);self.end_headers()
            self.wfile.write(json.dumps({'choices':[{'message':{'content':'["Local rewrite"]'}}]}).encode())
    server=HTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        model_slots.configure(tmp_path,'rewrite',f'http://127.0.0.1:{server.server_port}')
        assert model_slots.rewrite(tmp_path,['Input'],'clean')==['Local rewrite']
    finally:
        server.shutdown();server.server_close();thread.join()
