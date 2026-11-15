"""User-owned local models. Validate before replacing an installed slot."""
import json
import shutil
import uuid
import urllib.request
import threading
import time
from pathlib import Path

from duckcore.providers import local_base_url

FILES = {'transcription': ('config.json',), 'voice': ('kokoro-v1.0.onnx', 'voices-v1.0.bin')}
DIRS = {'transcription': 'stt-user', 'voice': 'voice-user'}
_status_cache = {}
_status_pending = set()
_status_lock = threading.Lock()


def _writing_status(path):
    with _status_lock:
        cached = _status_cache.get(path)
        if cached and time.monotonic() - cached[0] < 30:
            return dict(cached[1])
        if path not in _status_pending:
            _status_pending.add(path)
            def check():
                row = {'path': path, 'file': path, 'ready': False, 'problem': ''}
                try:
                    model_id(path)
                    row['ready'] = True
                except Exception as exc:
                    row['problem'] = str(exc)
                finally:
                    with _status_lock:
                        _status_cache[path] = (time.monotonic(), row)
                        _status_pending.discard(path)
            threading.Thread(target=check, daemon=True, name='writing-status').start()
    return {'path': path, 'file': path, 'ready': False, 'problem': 'Checking the local server…'}


def _remove_copy(root, task, path):
    if task not in DIRS or not path:
        return
    parent = (Path(root) / 'models' / DIRS[task]).resolve()
    candidate = Path(path)
    if not candidate.is_symlink() and candidate.resolve().parent == parent:
        shutil.rmtree(candidate, ignore_errors=True)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('The local server must not redirect requests.')


def request(base, endpoint, payload=None):
    base = local_base_url(base)
    url = base.rstrip('/') + endpoint
    req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=300 if endpoint == '/v1/chat/completions' else 2) as response:
            return json.load(response)
    except Exception as exc:
        raise ValueError(f'Your writing server at {base} is not reachable or returned an invalid response.') from exc


def model_id(base):
    rows = request(base, '/v1/models').get('data') or []
    if not rows or not isinstance(rows[0].get('id'), str):
        raise ValueError(f'Your writing server at {base} lists no usable model.')
    return rows[0]['id']


def validate(task, folder):
    root = Path(folder)
    for name in FILES[task]:
        if not (root / name).is_file() or not (root / name).stat().st_size:
            raise ValueError(f'That folder needs {name}.')
    if task == 'transcription':
        json.loads((root / 'config.json').read_text())
        if not (root / 'weights.npz').is_file() and not list(root.glob('*.safetensors')):
            raise ValueError('That folder needs weights.npz or *.safetensors.')
    if task == 'voice':
        import numpy as np
        try:
            with np.load(root / 'voices-v1.0.bin', allow_pickle=False) as voices:
                if not voices.files:
                    raise ValueError('No voices found.')
        except Exception as exc:
            raise ValueError('The voices-v1.0.bin file is not a usable voices archive.') from exc


def configure(root, task, value):
    from duckcore import app_settings
    root = Path(root)
    settings = app_settings.load(root)
    slots = dict(settings.get('model_slots') or {})
    previous = (slots.get(task) or {}).get('path')
    if not value:
        slots[task] = {'path': '', 'provider': task + '.local', 'enabled': False}
    elif task == 'rewrite':
        value = local_base_url(value)
        model_id(value)
        with _status_lock:
            _status_cache[value] = (time.monotonic(), {'path': value, 'file': value, 'ready': True, 'problem': ''})
        slots[task] = {'path': value, 'provider': 'rewrite.user', 'enabled': True}
    else:
        validate(task, value)
        target = root / 'models' / DIRS[task] / uuid.uuid4().hex
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copytree(value, target)
            validate(task, target)
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise
        slots[task] = {'path': str(target.resolve()), 'provider': task + '.user', 'enabled': True}
    settings['model_slots'] = slots
    app_settings.save(root, settings)
    if previous != slots[task]['path']:
        _remove_copy(root, task, previous)
    if value and task in DIRS:
        imported = Path(value)
        if not imported.is_symlink() and imported.resolve().parent == (root / 'models/slot-imports').resolve():
            shutil.rmtree(imported, ignore_errors=True)
    return status(root, task)


def selected(root, task):
    from duckcore import app_settings
    row = (app_settings.load(root).get('model_slots') or {}).get(task) or {}
    return str(row.get('path') or '') if row.get('enabled') else ''


def status(root, task):
    path = selected(root, task)
    result = {'path': path, 'file': '', 'ready': False, 'problem': ''}
    if not path:
        return result
    if task == 'rewrite':
        return _writing_status(path)
    try:
        if task == 'rewrite':
            model_id(path)
            result['file'] = path
        else:
            validate(task, path)
            result['file'] = 'Local files'
        result['ready'] = True
    except Exception as exc:
        result['problem'] = str(exc)
    return result


def rewrite(root, lines, mode):
    base = selected(root, 'rewrite')
    result = request(base, '/v1/chat/completions', {
        'model': model_id(base), 'messages': [{'role': 'user', 'content':
        f'Rewrite these lines in {mode} style. Return only a JSON array of strings, one per input.\n' + json.dumps(lines)}],
        'temperature': 0,
    })
    try:
        values = json.loads(result['choices'][0]['message']['content'])
        if not isinstance(values, list) or len(values) != len(lines) or not all(isinstance(v, str) for v in values):
            raise ValueError()
        return values
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError(f'Your writing server at {base} returned invalid lines.') from exc
