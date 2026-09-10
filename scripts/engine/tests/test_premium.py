import copy
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageChops, ImageDraw, ImageStat

from product_video.common import write_json
from product_video.config import load
from product_video.motion import blend_transition, smooth
from product_video.premium_transitions import PREMIUM_TRANSITIONS
from product_video.render import Renderer


class PremiumTransitionTests(unittest.TestCase):
    def test_iris_handles_rounded_timeline_boundary(self):
        # Frame 576 at 30 fps falls just inside this 0.9 s transition.
        progress = (19.2 - 18.3) / .9
        self.assertLess(progress, 1)
        self.assertLessEqual(smooth(progress), 1)
        for size in ((1280, 720), (1920, 1080)):
            a, b, bg = self.frames(size)
            self.assertEqual(blend_transition(a, b, progress, 'iris', bg).tobytes(), b.tobytes())

    def frames(self, size):
        a, b = Image.new('RGB', size, '#232830'), Image.new('RGB', size, '#dedbd5')
        w, h = size
        for image, colors in ((a, ('#81919c', '#b7cbdd')), (b, ('#546151', '#97816a'))):
            draw = ImageDraw.Draw(image)
            draw.rectangle((w // 12, h // 10, w // 4, h * 9 // 10), fill=colors[0])
            for i in range(3):
                draw.rectangle((w // 3, h // 5 + i * h // 5, w * 11 // 12, h // 4 + i * h // 5), fill=colors[1])
        return a, b, Image.new('RGB', size, '#18202a')

    def test_new_effects_have_exact_and_continuous_endpoints(self):
        for size in ((320, 180), (641, 361)):
            a, b, bg = self.frames(size)
            for kind in PREMIUM_TRANSITIONS:
                with self.subTest(size=size, effect=kind):
                    source_bytes = a.tobytes(), b.tobytes(), bg.tobytes()
                    for progress, expected in ((0, a), (1, b)):
                        self.assertEqual(blend_transition(a, b, progress, kind, bg).tobytes(), expected.tobytes())
                    for progress, expected in ((.0001, a), (.9999, b)):
                        actual = blend_transition(a, b, progress, kind, bg)
                        self.assertLess(max(ImageStat.Stat(ImageChops.difference(actual, expected)).mean), 2)
                    self.assertEqual(source_bytes, (a.tobytes(), b.tobytes(), bg.tobytes()))

    def test_each_effect_produces_distinct_motion_at_delivery_sizes(self):
        for size in ((1280, 720), (1920, 1080)):
            a, b, bg = self.frames(size)
            middle_frames = set()
            for kind in PREMIUM_TRANSITIONS:
                with self.subTest(size=size, effect=kind):
                    earlier = blend_transition(a, b, .25, kind, bg)
                    middle = blend_transition(a, b, .5, kind, bg)
                    later = blend_transition(a, b, .75, kind, bg)
                    self.assertEqual(middle.mode, 'RGB')
                    self.assertEqual(middle.size, size)
                    self.assertNotEqual(earlier.tobytes(), middle.tobytes())
                    self.assertNotEqual(later.tobytes(), middle.tobytes())
                    self.assertTrue(all(low > 0 for low, high in middle.getextrema()))
                    middle_frames.add(middle.tobytes())
            self.assertEqual(len(middle_frames), len(PREMIUM_TRANSITIONS))

    def test_aperture_curtains_and_upward_mask_reveal_the_expected_region(self):
        a = Image.new('RGB', (400, 240), 'red')
        b = Image.new('RGB', a.size, 'blue')
        bg = Image.new('RGB', a.size, '#202020')
        for kind in ('iris', 'split-reveal'):
            frame = blend_transition(a, b, .5, kind, bg)
            self.assertEqual(frame.getpixel((200, 120)), (0, 0, 255))
            self.assertEqual(frame.getpixel((10, 120)), (255, 0, 0))
        frame = blend_transition(a, b, .5, 'mask-up', bg)
        self.assertEqual(frame.getpixel((200, 20)), (255, 0, 0))
        self.assertEqual(frame.getpixel((200, 220)), (0, 0, 255))

    def test_glass_band_keeps_areas_away_from_boundary_crisp(self):
        a, b, bg = self.frames((1280, 720))
        frame = blend_transition(a, b, .5, 'glass-sweep', bg)
        self.assertEqual(frame.crop((0, 0, 200, 720)).tobytes(), b.crop((0, 0, 200, 720)).tobytes())
        self.assertEqual(frame.crop((1080, 0, 1280, 720)).tobytes(), a.crop((1080, 0, 1280, 720)).tobytes())

    def test_chapter_and_step_dispatch_support_every_effect_and_reduced_motion(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a, b, _ = self.frames((640, 400))
            a.save(root / 'a.png'); b.save(root / 'b.png')
            project = {'schema_version': 1, 'product': {'name': 'Transition fixture'},
                       'video': {'width': 1280, 'height': 720, 'style': 'cinema', 'camera_motion': 'none'},
                       'chapters': [{'id': 'first', 'title': 'First', 'narration': 'First.',
                                     'steps': [{'at': 0, 'images': ['a.png']}]},
                                    {'id': 'second', 'title': 'Second', 'narration': 'Second.',
                                     'steps': [{'at': 0, 'images': ['b.png']},
                                               {'at': .5, 'images': ['a.png']}]}]}
            for kind in PREMIUM_TRANSITIONS:
                with self.subTest(effect=kind):
                    project['chapters'][1]['transition'] = kind
                    project['chapters'][1]['steps'][1]['transition'] = kind
                    write_json(root / 'project.json', project)
                    config = load(root / 'project.json')
                    chapters = [{**c, 'start': i * 6, 'end': (i + 1) * 6,
                                 'audio_duration': 4, 'lead': 1, 'cues': []} for i, c in enumerate(config['chapters'])]
                    renderer = Renderer(config, chapters)
                    self.assertEqual(renderer.frame(6).tobytes(), renderer.scene(0, 6).tobytes())
                    self.assertNotEqual(renderer.frame(6.4).tobytes(), renderer.frame(7).tobytes())
                    self.assertEqual(renderer.transitions[1, 1][0], kind)
                    self.assertNotEqual(renderer.frame(9.15).tobytes(), renderer.frame(10).tobytes())
                    reduced = copy.deepcopy(config); reduced['video']['reduced_motion'] = True
                    renderer = Renderer(reduced, chapters)
                    self.assertEqual(renderer.frame(6).tobytes(), renderer.scene(1, 0).tobytes())
                    self.assertEqual(renderer.transitions[1, 1], ('cut', 0.))
