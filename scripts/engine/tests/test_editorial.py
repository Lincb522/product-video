import copy
import json
from pathlib import Path
import tempfile
import unittest
import wave

from PIL import Image

from product_video.capture import resolve_images
from product_video.common import VideoError
from product_video.config import load
from product_video.editorial import review_offsets
from product_video.shotcraft import timeline


class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        Image.new('RGB', (640, 400), '#336655').save(self.root/'a.png')
        Image.new('RGB', (640, 400), '#dddddd').save(self.root/'b.png')
        Image.new('RGB', (400, 640)).save(self.root/'portrait.png')
        self.raw = {'schema_version': 2, 'product': {'name': 'Sample'}, 'video': {}, 'chapters': [
            {'id': 'overview', 'title': 'Overview', 'narration': 'Two product functions.', 'steps': [
                {'at': 0, 'editorial': {'layout': 'overview', 'headline': '功能总览',
                 'items': [{'source': 'a.png', 'label': '项目'}, {'source': 'b.png', 'label': '配音'}], 'focus_at': [.1, .55]}}]}]}

    def config(self, raw=None):
        path = self.root/'project.json'
        path.write_text(json.dumps(raw or self.raw))
        return load(path)

    def test_card_cannot_silently_drop_other_visual_or_pointer_fields(self):
        for key, value in [('images', ['a.png']), ('cursor', [.5, .5]), ('click', True),
                           ('content', {}), ('scene3d', {}), ('shotcraft', {})]:
            raw = copy.deepcopy(self.raw)
            raw['chapters'][0]['steps'][0][key] = value
            with self.subTest(key=key), self.assertRaises(VideoError):
                self.config(raw)
        self.raw['video']['renderer'] = 'legacy'
        with self.assertRaisesRegex(VideoError, 'Remotion'):
            self.config()

    def test_invalid_geometry_and_timing_fail_before_narration(self):
        spec = self.raw['chapters'][0]['steps'][0]['editorial']
        for change in [{'focus_at': [.7, .2]}, {'focus_at': [.1]}, {'focus_at': [0, float('nan')]},
                       {'items': []}, {'layout': 'invented'}, {'motion': 'row-embed'}]:
            raw = copy.deepcopy(self.raw)
            raw['chapters'][0]['steps'][0]['editorial'].update(change)
            with self.subTest(change=change), self.assertRaises(VideoError):
                self.config(raw)
        del spec['focus_at']
        spec.update(layout='full', motion='row-embed', items=spec['items'][:1], slices=[0, .15, .4, 1])
        self.assertEqual(self.config()['chapters'][0]['steps'][0]['editorial']['slices'], [0, .15, .4, 1])
        for cuts in [[0, .4, .2, 1], [0, .5, .9], [0, 0, 1], [0, 1]]:
            spec['slices'] = cuts
            with self.assertRaises(VideoError): self.config()

    def test_comparison_requires_corresponding_aspect_ratio(self):
        spec = self.raw['chapters'][0]['steps'][0]['editorial']
        del spec['focus_at']
        spec.update(layout='pair', motion='comparison-wipe')
        self.config()
        spec['items'][1]['source'] = 'portrait.png'
        with self.assertRaisesRegex(VideoError, '相同比例'): self.config()
        spec['motion'] = 'paired-slide'
        self.config()

    def test_capture_references_resolve_for_content_images(self):
        spec = self.raw['chapters'][0]['steps'][0]['editorial']
        spec['items'][0]['source'] = 'capture:overview'
        resolve_images(self.raw, self.root, {'overview': str(self.root/'a.png')})
        self.assertEqual(spec['items'][0]['source'], str(self.root/'a.png'))
        self.config()

    def test_multiline_copy_cannot_overlap_the_screenshot(self):
        spec = self.raw['chapters'][0]['steps'][0]['editorial']
        spec['headline'] = '项目管理\n详细操作'
        self.config()
        spec['notes'] = ['补充说明']
        with self.assertRaisesRegex(VideoError, '安全区'):
            self.config()
        spec['layout'] = 'side'
        spec['items'] = spec['items'][:1]
        del spec['focus_at']
        self.config()

    def test_overview_uses_real_assets_and_shared_voice_clock_beyond_six_seconds(self):
        config = self.config()
        audio = self.root/'voice.wav'
        with wave.open(str(audio), 'wb') as out:
            out.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            out.writeframes(b'\0' * 16000 * 20)
        chapter = config['chapters'][0] | {'start': 0, 'end': 20.5, 'lead': .25, 'audio_duration': 20,
            'audio': str(audio), 'audio_sha256': 'fixture', 'cues': [{'start': .25, 'end': 9, 'text': '项目'}, {'start': 9, 'end': 20.25, 'text': '配音'}]}
        def plate(*args):
            self.fail('Editorial content must render directly on the shared timeline.')
        result = timeline(config, [chapter], self.root/'public', plate)
        tracks = {t['id']: t['clips'] for t in result['tracks']}
        shot = tracks['shots'][0]
        self.assertEqual((shot['cardId'], shot['duration'], shot['props']['duration']), ('pv-editorial', 615, 615))
        self.assertEqual(shot['props']['focus_at'], [.1, .55])
        self.assertEqual(shot['props']['items'][0]['width'], 640)
        self.assertEqual((self.root/'public'/shot['props']['items'][0]['file']).read_bytes(), (self.root/'a.png').read_bytes())
        self.assertEqual(tracks['narration'][0]['start'], tracks['captions'][0]['start'])
        self.assertEqual(tracks['narration'][0]['speed'], 1)
        frames = review_offsets(615, shot['props'], 30)
        self.assertIn(round(.55 * 615 + 48), frames)
        self.assertEqual(frames[-1], 614)


if __name__ == '__main__':
    unittest.main()
