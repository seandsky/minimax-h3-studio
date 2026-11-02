import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from remote_engine import RemoteEngine
from remote_video import video_graph
from model_catalog import LORAS


class RemoteTests(unittest.TestCase):
    def test_download_and_typed_template(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / 'music.json').write_text(json.dumps({'1': {'class_type': 'SaveAudio', 'inputs': {'seed': '${seed}'}}}))
            engine = RemoteEngine('http://example', folder)
            responses = [Mock(json=lambda: {'prompt_id': 'ours'}),
                         Mock(json=lambda: {'ours': {'outputs': {'1': {'audio': [{'filename': 'result.mp3', 'type': 'output'}]}}}}),
                         Mock(content=b'audio')]
            with patch.object(engine, 'request', side_effect=responses) as request, patch.object(engine.stopped, 'wait', return_value=False):
                engine.generate_music(seed=42, duration=10, audio_path=folder / 'local.mp3', on_progress=Mock())
            self.assertEqual((folder / 'local.mp3').read_bytes(), b'audio')
            self.assertEqual(request.call_args_list[0].kwargs['json']['prompt']['1']['inputs']['seed'], 42)
            self.assertIsNone(engine.prompt_id)

    def test_cancel_only_deletes_owned_prompt(self):
        engine = RemoteEngine('http://example', '.')
        engine.prompt_id = 'ours'
        with patch.object(engine, 'request') as request:
            engine.cancel()
            request.assert_called_once_with('POST', '/queue', json={'delete': ['ours']})

    def test_video_graph_has_valid_links(self):
        for lora in LORAS:
            graph = video_graph(dict(lora=lora, lora_strength=1, prompt='test', width=960, height=544,
                duration=5, seed=42, ref_paths=[], ref_video_paths=[]))
            def check(value):
                if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str) and isinstance(value[1], int):
                    self.assertIn(value[0], graph)
                elif isinstance(value, dict):
                    for v in value.values():
                        check(v)
            for node in graph.values():
                check(node['inputs'])
            self.assertEqual(list(graph.values())[-1]['class_type'], 'SaveVideo')

    def test_remote_execution_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / 'music.json').write_text('{}')
            engine = RemoteEngine('http://example', folder)
            responses = [Mock(json=lambda: {'prompt_id': 'ours'}), Mock(json=lambda: {
                'ours': {'status': {'status_str': 'error', 'messages': [['execution_error', {'exception_message': 'missing model'}]]}}})]
            with patch.object(engine, 'request', side_effect=responses), patch.object(engine.stopped, 'wait', return_value=False):
                with self.assertRaisesRegex(RuntimeError, 'missing model'):
                    engine.generate_music(audio_path=folder / 'out.mp3', on_progress=Mock())
            self.assertIsNone(engine.prompt_id)
