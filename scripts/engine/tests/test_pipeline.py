import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from product_video.common import VideoError, audio_duration, file_hash, run, write_json
from product_video.config import load
from product_video.pipeline import build
from product_video.tts import cache_location


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        Image.new('RGB', (640, 400), '#234567').save(self.root / 'image.png')
        project = {
            'schema_version': 1, 'product': {'name': 'Pipeline fixture'}, 'output': 'output',
            'video': {'width': 1280, 'height': 720, 'fps': 24, 'transition': .25, 'chapter_pause': .1},
            'chapters': [{'id': 'intro', 'title': 'Fixture', 'narration': '测试。',
                          'steps': [{'at': 0, 'images': ['image.png']}]}],
        }
        write_json(self.root / 'project.json', project)
        self.config = load(self.root / 'project.json')
        folder = cache_location(self.root / 'output', self.config['chapters'][0], self.config['voice'])
        folder.mkdir(parents=True)
        self.audio = folder / 'voice.mp3'
        self.audio.write_bytes(run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                                    'sine=frequency=440:duration=0.6', '-ar', '24000',
                                    '-c:a', 'libmp3lame', '-f', 'mp3', 'pipe:1']))
        self.metadata = folder / 'metadata.json'
        write_json(self.metadata, {
            'duration': audio_duration(self.audio), 'sha256': file_hash(self.audio),
            'events': [{'event': 364, 'data': {'words': [
                {'word': '测试。', 'startTime': .05, 'endTime': .45},
            ]}}],
        })

    def latest(self):
        return json.loads((self.root / 'output/latest.json').read_text())

    def test_cached_render_updates_latest_without_encoding_or_synthesis(self):
        with patch('product_video.pipeline.generate', side_effect=AssertionError('No API in regression test')):
            first = build(self.config, allow_api=False)
            changed = copy.deepcopy(self.config)
            changed['product']['name'] = 'Changed visual'
            second = build(changed, allow_api=False)
            self.assertNotEqual(first, second)
            self.assertEqual(self.latest()['movie'], str(second / 'product-introduction.mp4'))
            original_hash = file_hash(first / 'product-introduction.mp4')
            audio_state = (file_hash(self.audio), self.audio.stat().st_mtime_ns)
            with patch('product_video.pipeline.encode_video', side_effect=AssertionError('Must reuse cached video')):
                self.assertEqual(build(self.config, allow_api=False), first)
                self.assertEqual(self.latest(), {'movie': str(first / 'product-introduction.mp4'),
                                                'report': str(first / 'verification.json')})
                build(changed, allow_api=False, preview=True)
                self.assertEqual(self.latest()['movie'], str(first / 'product-introduction.mp4'))
            self.assertEqual(file_hash(first / 'product-introduction.mp4'), original_hash)
            self.assertEqual((file_hash(self.audio), self.audio.stat().st_mtime_ns), audio_state)

            (second / 'product-introduction.mp4').write_bytes(b'corrupt cached fixture')
            with self.assertRaisesRegex(VideoError, '校验失败'):
                build(changed, allow_api=False)
            self.assertEqual(self.latest()['movie'], str(first / 'product-introduction.mp4'))

    def test_standalone_punctuation_renders_and_decodes(self):
        metadata = json.loads(self.metadata.read_text())
        metadata['events'][0]['data']['words'] = [
            {'word': '测', 'startTime': .05, 'endTime': .2},
            {'word': '试', 'startTime': .2, 'endTime': .35},
            {'word': '。', 'startTime': .35, 'endTime': .45},
        ]
        write_json(self.metadata, metadata)
        folder = build(self.config, allow_api=False)
        self.assertEqual(json.loads((folder / 'verification.json').read_text())['full_decode'], 'passed')
        cues = json.loads((folder / 'timeline.json').read_text())['chapters'][0]['cues']
        self.assertEqual([cue['text'] for cue in cues], ['测试。'])
