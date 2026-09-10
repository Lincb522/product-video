import copy
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageChops

from product_video.capture import resolve_images
from product_video.common import VideoError, write_json
from product_video.config import load
from product_video.motion import PRESETS
from product_video.render import Renderer
from product_video.text_scenes import font


class ContentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        Image.new('RGB', (1440, 900), '#c62828').save(self.root / 'before.png')
        Image.new('RGB', (1440, 900), '#1565c0').save(self.root / 'after.png')
        self.project = {'schema_version': 1, 'product': {'name': 'Copy fixture'},
                        'video': {'width': 1280, 'height': 720, 'camera_motion': 'none', 'progress': False},
                        'chapters': [{'id': 'intro', 'title': '文案与画面', 'narration': '旁白与正文分别编排。',
                                      'steps': [{'at': 0, 'content': {'layout': 'title',
                                                 'eyebrow': 'PRODUCT VIDEO', 'headline': '让介绍有自己的节奏',
                                                 'body': '先说明用途，再展示真实界面。'}}]}]}

    def config(self, raw=None):
        write_json(self.root / 'project.json', raw or self.project)
        return load(self.root / 'project.json')

    def renderer(self, raw=None):
        config = self.config(raw)
        chapters = [{**c, 'start': 0, 'end': 11, 'lead': .6, 'audio_duration': 10., 'cues': []}
                    for c in config['chapters']]
        return Renderer(config, chapters)

    def test_text_only_renders_in_every_style_without_image_assets(self):
        for style in PRESETS:
            with self.subTest(style=style):
                raw = copy.deepcopy(self.project)
                raw['video']['style'] = style
                renderer = self.renderer(raw)
                self.assertEqual(renderer.chapters[0]['steps'][0]['images'], [])
                self.assertEqual(renderer.layout(0, 0), [])
                image = renderer.frame(2.)
                box = (0, 150, 1280, 600)
                self.assertIsNotNone(ImageChops.difference(image.crop(box), renderer.base.crop(box)).getbbox())

    def test_complete_mixed_language_copy_fits_clear_of_subtitles_and_images(self):
        samples = [
            {'layout': 'title', 'headline': '完整显示中文与 English Product Copy', 'body': '第一行保留。\nSecond line keeps whole words, punctuation, and versions like 1.4.0.'},
            {'layout': 'bullets', 'headline': '按内容编排画面', 'bullets': ['完整显示正文与真实画面', 'Narration follows the script.', '保留中文标点和换行。']},
            {'layout': 'split', 'headline': '先讲用途，再演示', 'body': 'Text and screenshots share the frame, each with room to read.'},
        ]
        for width in (1280, 1920):
            for sample in samples:
                for side in ('left', 'right') if sample['layout'] == 'split' else ('right',):
                    raw = copy.deepcopy(self.project)
                    raw['video'].update(width=width, height=round(width * 9 / 16))
                    content = copy.deepcopy(sample)
                    step = {'at': 0, 'content': content}
                    if content['layout'] == 'split':
                        content['image_side'] = side
                        step['images'] = ['before.png']
                    raw['chapters'][0]['steps'] = [step]
                    renderer = self.renderer(raw)
                    for block in renderer.content[0, 0]:
                        self.assertEqual(''.join(''.join(block['lines']).split()), ''.join(block['text'].split()))
                        self.assertGreaterEqual(block['y'], round(228 * width / 1920))
                        self.assertLessEqual(block['y'] + block['height'], round(856 * width / 1920))
                        face = font(renderer.v['font'], block['font_size'])
                        self.assertTrue(all(face.getlength(line) <= block['width'] for line in block['lines']))
                        for x, y, w, h in renderer.layout(0, 0):
                            self.assertTrue(block['x'] + block['width'] <= x or block['x'] >= x + w)
                    self.assertEqual(renderer.frame(2).size, (width, round(width * 9 / 16)))

    def test_reveal_can_be_disabled_and_reduced_motion_keeps_all_copy_visible(self):
        renderer = self.renderer()
        a, _ = renderer.shot(0, 0, {}, 1, False, 0)
        b, _ = renderer.shot(0, 0, {}, 1, False, 1)
        self.assertIsNotNone(ImageChops.difference(a, b).getbbox())
        for field in ('animation', 'reduced_motion'):
            raw = copy.deepcopy(self.project)
            if field == 'animation':
                raw['chapters'][0]['steps'][0]['content']['animation'] = 'none'
            else:
                raw['video']['reduced_motion'] = True
            renderer = self.renderer(raw)
            a, _ = renderer.shot(0, 0, {}, 1, False, 0)
            b, _ = renderer.shot(0, 0, {}, 1, False, 1)
            self.assertEqual(a.tobytes(), b.tobytes())
        self.assertIn('text-reveal', renderer.review_times(0, 0))

    def test_invalid_copy_and_incompatible_assets_fail_during_preflight(self):
        bad_steps = [
            {'at': 0},
            {'at': 0, 'content': {'layout': 'title', 'headline': ''}},
            {'at': 0, 'content': {'layout': 'unknown', 'headline': 'Title'}},
            {'at': 0, 'content': {'layout': 'title', 'headline': 'Title'}, 'images': ['before.png']},
            {'at': 0, 'content': {'layout': 'split', 'headline': 'Title'}},
            {'at': 0, 'content': {'layout': 'title', 'headline': 'Title'}, 'cursor': [.2, .3]},
            {'at': 0, 'content': {'layout': 'bullets', 'headline': 'Title', 'bullets': ['Item'] * 5}},
            {'at': 0, 'content': {'layout': 'title', 'headline': 'Title', 'body': ('长文说明' * 195)}},
        ]
        for step in bad_steps:
            with self.subTest(step=step):
                raw = copy.deepcopy(self.project)
                raw['chapters'][0]['steps'] = [step]
                with self.assertRaises(VideoError):
                    self.config(raw)

    def test_capture_resolution_preserves_copy_only_steps(self):
        raw = copy.deepcopy(self.project)
        raw['chapters'][0]['steps'].append({'at': .5, 'images': ['capture:screen'],
                                           'content': {'layout': 'split', 'headline': '真实截图'}})
        resolve_images(raw, self.root, {'screen': str(self.root / 'before.png')})
        config = self.config(raw)
        self.assertEqual(config['chapters'][0]['steps'][0]['images'], [])
        self.assertEqual(config['chapters'][0]['steps'][1]['images'], [str((self.root / 'before.png').resolve())])

    def test_split_click_preserves_old_image_and_uses_its_rectangle(self):
        raw = copy.deepcopy(self.project)
        content = {'layout': 'split', 'headline': '操作讲解', 'image_side': 'left'}
        raw['chapters'][0]['steps'] = [
            {'at': 0, 'images': ['before.png'], 'content': content},
            {'at': .4, 'images': ['after.png'], 'content': copy.deepcopy(content),
             'interaction': {'kind': 'click', 'from': [.1, .2], 'to': [.2, .3]}},
        ]
        renderer = self.renderer(raw)
        x, y, w, h = renderer.layout(0, 0)[0]
        center = (round(x + w / 2), round(y + h / 2))
        self.assertEqual(renderer.frame(4.85).getpixel(center), (198, 40, 40))
        self.assertEqual(renderer.frame(6.3).getpixel(center), (21, 101, 192))
        raw['chapters'][0]['steps'][1]['content']['image_side'] = 'right'
        with self.assertRaisesRegex(VideoError, '相同的截图版式'):
            self.config(raw)

    def test_classic_restores_original_geometry_and_gradient(self):
        raw = copy.deepcopy(self.project)
        raw['video'] = {'style': 'classic', 'width': 1920, 'height': 1080}
        raw['chapters'][0]['steps'] = [{'at': 0, 'images': ['before.png']}]
        renderer = self.renderer(raw)
        self.assertEqual(renderer.v['background'], '#17191f')
        self.assertEqual(renderer.v['accent'], '#d5ac86')
        self.assertEqual(renderer.v['transition'], .6)
        self.assertEqual(renderer.v['camera_motion'], 'none')
        self.assertTrue(renderer.v['progress'])
        self.assertEqual(renderer.layout(0, 0)[0], (376, 158, 1168, 730))
        self.assertEqual(renderer.base.getpixel((0, 0)), renderer.base.getpixel((1900, 0)))
        self.assertNotEqual(renderer.base.getpixel((0, 0)), renderer.base.getpixel((0, 1000)))
        a, b = Image.new('RGB', (10, 10), 'black'), Image.new('RGB', (10, 10), 'white')
        self.assertEqual(renderer.blend(a, b, .25, 'fade').tobytes(), Image.blend(a, b, .15625).tobytes())
