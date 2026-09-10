import copy
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from product_video.common import VideoError, write_json
from product_video.config import load
from product_video.motion import PRESETS, TRANSITIONS, blend_transition, camera_rect, interaction_for, pointer_position
from product_video.render import Renderer


class InteractionRenderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, color in [('before', '#c62828'), ('after', '#1565c0')]:
            Image.new('RGB', (1440, 900), color).save(self.root / f'{name}.png')
        self.project = {
            'schema_version': 1, 'product': {'name': 'Motion fixture'},
            'video': {'width': 1280, 'height': 720, 'subtitles': 'none'},
            'chapters': [{'id': 'click', 'title': 'Click fixture', 'narration': 'Test.',
                          'steps': [
                              {'at': 0, 'images': ['before.png'], 'cursor': [.1, .2]},
                              {'at': .4, 'images': ['after.png'], 'cursor': [.2, .3], 'click': True}]}],
        }

    def renderer(self, project=None):
        write_json(self.root / 'project.json', project or self.project)
        config = load(self.root / 'project.json')
        chapters = [{**copy.deepcopy(c), 'start': 0, 'end': 11, 'lead': .6,
                     'audio_duration': 10, 'cues': []} for c in config['chapters']]
        return Renderer(config, chapters)

    def test_result_does_not_appear_before_pointer_click(self):
        renderer = self.renderer()
        # The result step starts at 4.6 s, but the pointer is still travelling.
        image = renderer.frame(4.85)
        self.assertEqual(image.getpixel((640, 360)), (198, 40, 40))
        image = renderer.frame(6.3)
        self.assertEqual(image.getpixel((640, 360)), (21, 101, 192))

    def test_explicit_click_and_drag_keep_before_until_release(self):
        for kind in ('click', 'drag'):
            project = copy.deepcopy(self.project)
            step = project['chapters'][0]['steps'][1]
            step.pop('cursor'); step.pop('click')
            step['interaction'] = {'kind': kind, 'from': [.1, .2], 'to': [.2, .3],
                                   'move': .8, 'hold': .25, 'settle': .2}
            renderer = self.renderer(project)
            for elapsed in (.1, .5, 1.1, 1.24):
                self.assertEqual(renderer.frame(4.6 + elapsed).getpixel((640, 360)), (198, 40, 40))
            self.assertEqual(renderer.frame(6.3).getpixel((640, 360)), (21, 101, 192))

    def test_short_automatic_action_reserves_visible_result(self):
        renderer = self.renderer()
        step = self.project['chapters'][0]['steps'][1]
        track = interaction_for(step, self.project['chapters'][0]['steps'][0], renderer.v, .6, .12)
        self.assertLessEqual(track['reveal'] + .12, .48 + 1e-9)
        self.assertLess(track['press'], track['release'])
        self.assertLessEqual(track['release'], track['reveal'])

    def test_explicit_timing_cannot_silently_drop_click(self):
        project = copy.deepcopy(self.project)
        step = project['chapters'][0]['steps'][1]
        step.pop('cursor'); step.pop('click')
        step['at'] = .95
        step['interaction'] = {'kind': 'click', 'to': [.2, .3], 'move': 2}
        with self.assertRaisesRegex(VideoError, '时间超过'):
            self.renderer(project)
        step['interaction']['kind'] = 'move'
        with self.assertRaisesRegex(VideoError, '时间超过'):
            self.renderer(project)

    def test_profiles_override_defaults_without_overriding_authored_values(self):
        for style in PRESETS:
            project = copy.deepcopy(self.project)
            project['video'].update(style=style, accent='#123456', cursor_move=1.2)
            renderer = self.renderer(project)
            self.assertEqual(renderer.v['accent'], '#123456')
            self.assertEqual(renderer.v['cursor_move'], 1.2)
            self.assertEqual(renderer.frame(1).size, (1280, 720))
        self.assertEqual(renderer.v['camera_motion'], 'none')

    def test_invalid_motion_contracts_fail_during_load(self):
        for bad_step in (
            {'interaction': {'kind': 'click', 'to': [.2, .3]}, 'cursor': [.2, .3]},
            {'interaction': {'kind': 'drag', 'to': [.2, .3]}},
            {'interaction': {'kind': 'move', 'to': [float('nan'), .3]}},
            {'interaction': {'kind': 'click', 'to': [.2, .3], 'move': 0}},
            {'camera': {'zoom': 10}}, {'transition': 'unknown'},
        ):
            project = copy.deepcopy(self.project)
            step = project['chapters'][0]['steps'][1]
            step.pop('cursor'); step.pop('click'); step.update(bad_step)
            with self.assertRaises(VideoError):
                self.renderer(project)

    def test_new_click_requires_before_and_matching_viewport(self):
        project = copy.deepcopy(self.project)
        project['chapters'][0]['steps'][0] = {'at': 0, 'images': ['before.png'],
                                             'interaction': {'kind': 'click', 'to': [.2, .3]}}
        with self.assertRaisesRegex(VideoError, '操作前截图'):
            self.renderer(project)
        Image.new('RGB', (400, 800)).save(self.root / 'after.png')
        with self.assertRaisesRegex(VideoError, '比例不同'):
            self.renderer()

    def test_camera_keeps_before_view_stable_during_click(self):
        project = copy.deepcopy(self.project)
        project['chapters'][0]['steps'][0]['camera'] = {'zoom': 1.7, 'center': [.2, .3]}
        renderer = self.renderer(project)
        track = renderer.tracks[0, 1]
        camera, progress, push = renderer.camera(0, 1, .3, track['reveal'], True)
        self.assertEqual(camera, {'zoom': 1.7, 'center': [.2, .3]})
        self.assertEqual(progress, 1)
        self.assertFalse(push)

    def test_preview_covers_movement_press_result_and_transition(self):
        renderer = self.renderer()
        phases = renderer.review_times(0, 1)
        self.assertTrue({'move', 'press', 'result', 'transition'} <= set(phases))
        self.assertLess(phases['move'], phases['press'])
        self.assertLess(phases['press'], phases['result'])
        self.assertTrue(all(4.6 <= t < 10.6 for t in phases.values()))

    def test_reduced_motion_disables_camera_and_effects_but_keeps_causality(self):
        project = copy.deepcopy(self.project)
        project['video']['reduced_motion'] = True
        project['chapters'][0]['steps'][0]['camera'] = {'zoom': 2, 'center': [.2, .3]}
        renderer = self.renderer(project)
        self.assertEqual(renderer.camera(0, 0, 1, 0, False), ({}, 1, False))
        self.assertTrue(all(kind == 'cut' and duration == 0 for kind, duration in renderer.transitions.values()))
        self.assertEqual(renderer.frame(4.85).getpixel((640, 360)), (198, 40, 40))


class MotionMathTests(unittest.TestCase):
    def test_transitions_have_exact_endpoints_and_distinct_midframes(self):
        a, b = Image.new('RGB', (160, 90), 'red'), Image.new('RGB', (160, 90), 'blue')
        background = Image.new('RGB', a.size, '#171717')
        mids = set()
        for kind in TRANSITIONS:
            with self.subTest(kind=kind):
                self.assertEqual(blend_transition(a, b, 1, kind, background).tobytes(), b.tobytes())
                if kind != 'cut':
                    self.assertEqual(blend_transition(a, b, 0, kind, background).tobytes(), a.tobytes())
                middle = blend_transition(a, b, .4, kind, background)
                self.assertEqual(middle.mode, 'RGB')
                self.assertEqual(middle.size, a.size)
                mids.add(middle.tobytes())
        self.assertGreaterEqual(len(mids), 7)

    def test_pointer_arrives_exactly_and_does_not_teleport_at_start(self):
        track = {'kind': 'click', 'from': [.1, .2], 'to': [.8, .7], 'move': .8, 'hold': .2}
        self.assertEqual(pointer_position(track, 0), (.1, .2))
        for time in (.8, 1, 2):
            self.assertAlmostEqual(pointer_position(track, time)[0], .8)
            self.assertAlmostEqual(pointer_position(track, time)[1], .7)
        start = pointer_position(track, .01)
        self.assertLess(abs(start[0] - .1), .001)
        for i in range(100):
            self.assertTrue(all(0 <= n <= 1 for n in pointer_position(track, i / 100)))
        track['kind'] = 'drag'
        self.assertEqual(pointer_position(track, .1), (.1, .2))
        self.assertAlmostEqual(pointer_position(track, 1)[0], .8)

    def test_camera_and_pointer_share_image_coordinates(self):
        rect = (100, 100, 800, 500)
        self.assertEqual(camera_rect(rect, {}, 1), rect)
        zoomed = camera_rect(rect, {'zoom': 2, 'center': [.4, .4]}, 1)
        x, y, w, h = zoomed
        self.assertAlmostEqual(x + w * .4, 500)
        self.assertAlmostEqual(y + h * .4, 350)
        for center in ([0, 0], [1, 1]):
            x, y, w, h = camera_rect(rect, {'zoom': 2, 'center': center}, 1)
            self.assertLessEqual(x, rect[0]); self.assertLessEqual(y, rect[1])
            self.assertGreaterEqual(x + w, 900); self.assertGreaterEqual(y + h, 600)
