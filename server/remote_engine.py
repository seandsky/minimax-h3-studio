"""HTTP-only ComfyUI engine; no local GPU or ComfyUI imports."""
import json
import threading
import time
import uuid
from pathlib import Path

import requests
from PIL import Image
from engine_errors import Canceled


class RemoteEngine:
    family = unet = audio_cpp = llm = None

    def __init__(self, url, workflows):
        self.url = url.rstrip('/')
        self.workflows = Path(workflows)
        self.stopped = threading.Event()
        self.prompt_id = None

    def request(self, method, path, **kwargs):
        # Tailscale addresses must not go through an environment HTTP proxy.
        with requests.Session() as session:
            session.trust_env = False
            response = session.request(method, self.url + path, timeout=(10, 120), **kwargs)
            if not response.ok:
                raise RuntimeError(f'ComfyUI {path}: {response.status_code} {response.text[:2000]}')
            return response

    def bootstrap(self):
        pass

    def load(self):
        # Missing nodes/models must not prevent the workbench from starting.
        pass

    def cancel(self):
        self.stopped.set()
        if self.prompt_id:
            # Remove only our waiting prompt; never interrupt another client's GPU job.
            self.request('POST', '/queue', json={'delete': [self.prompt_id]})

    def unload(self):
        return {'remote': True, 'message': 'Shared remote models are managed by ComfyUI.'}

    def execute(self, kind, **values):
        self.stopped.clear()
        template = self.workflows / f'{kind}.json'
        if not template.is_file() and kind not in ('t2v', 'i2v', 'fl2v', 'r2v'):
            raise ValueError(f'Missing remote API workflow: {template}. See doc/remote-macos.md.')
        on_progress = values.pop('on_progress')
        outputs = {k: Path(v) for k, v in values.items()
                   if k in ('video_path', 'image_path', 'audio_path', 'model_path', 'thumb_path') and v}
        context = {}
        def upload(path):
            path = Path(path)
            with path.open('rb') as file:
                result = self.request('POST', '/upload/image',
                    files={'image': (uuid.uuid4().hex + path.suffix, file)},
                    data={'type': 'input', 'overwrite': 'false'}).json()
            return '/'.join(filter(None, (result.get('subfolder'), result['name'])))
        for key, value in values.items():
            if key in outputs:
                continue
            if key.endswith('_paths'):
                context[key] = [upload(p) for p in value]
            elif key.endswith('_path'):
                context[key] = upload(value) if value else None
            else:
                context[key] = value
        # Exact placeholders preserve numbers, lists and null; partial interpolation is deliberately unsupported.
        def bind(value):
            if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                key = value[2:-1]
                if key not in context:
                    raise ValueError(f'Unknown workflow parameter: {key}')
                return context[key]
            if isinstance(value, list):
                return [bind(v) for v in value]
            if isinstance(value, dict):
                return {k: bind(v) for k, v in value.items()}
            return value
        if template.is_file():
            graph = bind(json.loads(template.read_text()))
        else:
            from remote_video import video_graph
            graph = video_graph(context)
        on_progress('encoding', 0.0)
        if self.stopped.is_set():
            raise Canceled()
        self.prompt_id = self.request('POST', '/prompt', json={'prompt': graph, 'client_id': uuid.uuid4().hex}).json()['prompt_id']
        if self.stopped.is_set():
            self.request('POST', '/queue', json={'delete': [self.prompt_id]})
        started = time.monotonic()
        try:
            while not self.stopped.wait(1):
                entry = self.request('GET', '/history/' + self.prompt_id).json().get(self.prompt_id)
                if not entry:
                    on_progress('sampling', 0.0)
                    continue
                if entry.get('status', {}).get('status_str') == 'error':
                    raise RuntimeError(json.dumps(entry['status'].get('messages', [])))
                artifacts = []
                for output in entry.get('outputs', {}).values():
                    for items in output.values():
                        if isinstance(items, list):
                            artifacts.extend(v for v in items if isinstance(v, dict) and 'filename' in v)
                extensions = {'video_path': ('.mp4', '.webm', '.mov'), 'image_path': ('.png', '.jpg', '.webp'),
                              'audio_path': ('.mp3', '.wav', '.flac', '.ogg'), 'model_path': ('.glb',)}
                on_progress('saving', 0.0)
                for key, target in outputs.items():
                    if key == 'thumb_path':
                        continue
                    artifact = next((a for a in artifacts if Path(a['filename']).suffix.lower() in extensions[key]), None)
                    if artifact is None:
                        raise RuntimeError(f'Workflow produced no saved output for {key}; add a Save node.')
                    response = self.request('GET', '/view', params={k: artifact[k] for k in ('filename', 'subfolder', 'type') if k in artifact})
                    target.write_bytes(response.content)
                if 'thumb_path' in outputs:
                    if 'image_path' in outputs:
                        with Image.open(outputs['image_path']) as image:
                            image.convert('RGB').save(outputs['thumb_path'])
                    elif 'video_path' in outputs:
                        import av
                        with av.open(str(outputs['video_path'])) as container:
                            next(container.decode(video=0)).to_image().save(outputs['thumb_path'])
                return {'remote_prompt_id': self.prompt_id, 'seconds': values.get('duration', 0),
                        'timings': {'remote': round(time.monotonic() - started, 1)}}
            raise Canceled()
        finally:
            self.prompt_id = None

    def generate(self, **kwargs):
        kind = 'r2v' if kwargs.get('ref_paths') or kwargs.get('ref_video_paths') else 'fl2v' if kwargs.get('last_image_path') else 'i2v' if kwargs.get('image_path') else 't2v'
        return self.execute(kind, **kwargs)

    def generate_image(self, **kwargs):
        return self.execute('image-' + kwargs['image_model'], **kwargs)

    def generate_music(self, **kwargs):
        return self.execute('music', **kwargs)

    def generate_3d(self, **kwargs):
        return self.execute('3d', **kwargs)

    def upscale_video(self, **kwargs):
        return self.execute('seedvr2', **kwargs)

    def flashvsr_video(self, **kwargs):
        return self.execute('flashvsr', **kwargs)

    def generate_speech(self, **kwargs):
        return self.execute('speech', **kwargs)

    def transcribe(self, **kwargs):
        raise ValueError('Remote transcription requires a transcript export adapter.')
