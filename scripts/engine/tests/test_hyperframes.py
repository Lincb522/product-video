import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from product_video.capture import resolve_images
from product_video.common import VideoError
from product_video.config import load
from product_video.hyperframes import check_report, compile_scene, source_files
from product_video.shotcraft import timeline


HTML = '''<!doctype html><html><head><!-- product-video:head --></head><body>
<div data-composition-id="custom" data-width="{{pv.width}}" data-height="{{pv.height}}" data-duration="{{pv.duration}}">
<h1>{{pv.variables.title}}</h1><img src="{{pv.media.screen}}"></div>
<script>const tl=gsap.timeline({paused:true}); window.__timelines.custom=tl;</script></body></html>'''


class HyperframesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        scene = self.root / 'scenes/hero'
        scene.mkdir(parents=True)
        self.entry = scene / 'index.html'
        self.entry.write_text(HTML)
        self.image = self.root / 'screen.png'
        Image.new('RGB', (640, 400), '#234567').save(self.image)
        self.raw = {'schema_version': 2, 'product': {'name': 'HTML fixture'},
            'chapters': [{'id': 'intro', 'title': 'Title', 'narration': '测试。', 'steps': [
                {'at': 0, 'images': ['screen.png']},
                {'at': .4, 'hyperframes': {'entry': 'scenes/hero/index.html',
                    'media': {'screen': 'screen.png'}, 'variables': {'title': 'A < B & "C"'}}},
                {'at': .8, 'images': ['screen.png']}]}]}

    def config(self, raw=None):
        path = self.root / 'project.json'
        path.write_text(json.dumps(raw or self.raw))
        return load(path)

    def chapter(self, config):
        return config['chapters'][0] | {'start': 2, 'end': 7, 'lead': .25, 'audio_duration': 4,
            'audio': str(self.image), 'audio_sha256': 'fixture',
            'cues': [{'start': 3, 'end': 4.2, 'text': '测试。'}, {'start': 5.5, 'end': 6, 'text': '后段'}]}

    def test_html_shot_keeps_shared_frame_boundaries_and_voice_clock(self):
        config = self.config()
        chapter = self.chapter(config)
        calls = []
        project = timeline(config, [chapter], self.root/'public', lambda *args: calls.append(args) or self.image)
        tracks = {t['id']: t['clips'] for t in project['tracks']}
        shots = tracks['shots']
        self.assertEqual([s['start'] for s in shots], [60, 116, 164])
        self.assertEqual([s['duration'] for s in shots], [56, 48, 46])
        self.assertTrue(shots[1]['props']['muted'])
        self.assertEqual(tracks['narration'][0]['start'], 68)
        self.assertEqual(calls[1], (0, 1, 116, 164))
        self.assertIn('transition', shots[1])
        self.assertIn('transition', shots[2])

    def test_capture_resolves_html_entry_and_media_before_rebasing(self):
        self.raw['chapters'][0]['steps'][1]['hyperframes']['media']['screen'] = 'capture:home'
        resolve_images(self.raw, self.root, {'home': str(self.image)})
        spec = self.raw['chapters'][0]['steps'][1]['hyperframes']
        self.assertEqual(spec['entry'], str(self.entry))
        self.assertEqual(spec['media']['screen'], str(self.image))
        self.config()
        spec['media']['screen'] = 'capture:missing'
        with self.assertRaisesRegex(VideoError, '不存在的截图'):
            resolve_images(self.raw, self.root, {})

    def test_custom_motion_cannot_discard_other_step_fields(self):
        for field, value in [('images', ['screen.png']), ('camera', {}), ('shotcraft', {}),
                             ('editorial', {}), ('content', {}), ('scene3d', {}), ('interaction', {})]:
            raw = copy.deepcopy(self.raw)
            raw['chapters'][0]['steps'][1][field] = value
            with self.subTest(field=field), self.assertRaises(VideoError):
                self.config(raw)
        self.raw['video'] = {'renderer': 'legacy'}
        with self.assertRaisesRegex(VideoError, '共享旁白'):
            self.config()

    def test_invalid_html_inputs_fail_before_synthesis(self):
        for bad in (HTML.replace('{{pv.duration}}', '5'), HTML.replace('{{pv.width}}', '600'),
                    HTML.replace('<!-- product-video:head -->', ''), HTML.replace('pv.media.screen', 'pv.media.missing')):
            self.entry.write_text(bad)
            with self.assertRaises(VideoError):
                self.config()
        self.entry.write_text(HTML)
        self.raw['chapters'][0]['steps'][1]['hyperframes']['media']['screen'] = 'missing.png'
        with self.assertRaises(VideoError):
            self.config()

    def test_compile_freezes_assets_and_exposes_local_cue_timing(self):
        config = self.config()
        spec = config['chapters'][0]['steps'][1]['hyperframes']
        chapter = self.chapter(config)
        chapter['title'] = '</script><script>bad()</script>'
        runtime = self.root/'runtime'
        gsap = runtime/'node_modules/gsap/dist/gsap.min.js'
        gsap.parent.mkdir(parents=True)
        gsap.write_text('// fixture runtime')
        with patch('product_video.hyperframes.runtime_root', return_value=runtime):
            context, identifier = compile_scene(spec, config['video'], chapter, 116, 164, self.root/'compiled')
        self.assertEqual(identifier, 'custom')
        self.assertEqual(context['duration'], 48/30)
        self.assertAlmostEqual(context['voice_start'], 2.25-116/30)
        self.assertEqual(len(context['cues']), 1)
        self.assertEqual(context['cues'][0]['start'], 0)
        self.assertAlmostEqual(context['cues'][0]['end'], 4.2-116/30)
        compiled = (self.root/'compiled/index.html').read_text()
        self.assertIn('A &lt; B &amp; &quot;C&quot;', compiled)
        self.assertNotIn('{{pv.', compiled)
        self.assertNotIn('</script>', (self.root/'compiled/_pv/timing.js').read_text())
        self.assertEqual((self.root/'compiled'/context['media']['screen']).read_bytes(), self.image.read_bytes())
        self.assertEqual((self.root/'compiled'/context['font']).read_bytes(), Path(config['video']['font']).read_bytes())

    def test_source_collection_excludes_environment_and_generated_output(self):
        self.entry.with_name('.env').write_text('synthetic fixture')
        self.entry.with_name('credentials.json').write_text('{}')
        self.entry.with_name('motion.js').write_text('/* local motion */')
        output = self.entry.parent/'output'
        output.mkdir()
        (output/'frame.png').write_bytes(b'fixture')
        spec = self.config()['chapters'][0]['steps'][1]['hyperframes']
        self.assertEqual({p.name for p in source_files(spec)}, {'index.html', 'motion.js'})

    def test_browser_check_requires_completed_audits_even_after_zero_exit(self):
        log = self.root/'check.log'
        report = {'ok': True, 'lint': {'ok': True}, 'runtime': {'ok': True},
            'layout': {'ok': True, 'samples': [.25, .75]}, 'contrast': {'ok': True}}
        log.write_text('browser started\n'+json.dumps(report))
        self.assertEqual(check_report(log), report)
        for content in ['browser started\n', json.dumps(report | {'ok': False}),
                        json.dumps(report | {'layout': {'ok': True, 'samples': []}})]:
            log.write_text(content)
            with self.assertRaisesRegex(VideoError, '没有完成'):
                check_report(log)


if __name__ == '__main__':
    unittest.main()
