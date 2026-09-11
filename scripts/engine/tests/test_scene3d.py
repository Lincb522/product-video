import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops

from product_video.capture import resolve_images
from product_video.common import VideoError, audio_duration, file_hash, run, write_json
from product_video.config import load
from product_video.pipeline import build
from product_video.render import Renderer
from product_video.studio3d import Studio3D
from product_video.tts import cache_location


class Scene3DTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name).resolve()
        Image.new('RGB', (320, 200), '#ee1010').save(cls.root / 'red.png')
        Image.new('RGB', (320, 200), '#1010ee').save(cls.root / 'blue.png')
        run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=red:s=320x200:r=24:d=2',
             '-vf', "drawbox=color=blue:t=fill:enable='gte(t,1)'", '-c:v', 'libx264', '-pix_fmt', 'yuv420p', cls.root / 'clip.mp4'])
        cls.raw = {'schema_version': 1, 'product': {'name': '3D fixture'}, 'output': str(cls.root / 'output'),
                   'video': {'width': 640, 'height': 360, 'fps': 24, 'progress': False, 'style': 'gallery'},
                   'chapters': [{'id': 'demo', 'title': '3D fixture', 'narration': '测试。', 'steps': [{'at': 0,
                     'scene3d': {'motion': 'still', 'floor': False, 'background': '#000000',
                       'camera': {'position': [0, 0, 12], 'target': [0, 0, 0]},
                       'devices': [{'model': 'panel', 'source': str(cls.root / 'red.png'),
                                    'position': [0, 0, 0], 'rotation': [0, 0, 0]}]}}]}]}
        write_json(cls.root / 'project.json', cls.raw)
        cls.config = load(cls.root / 'project.json')

    @property
    def studio(self):
        if not hasattr(self, '_studio'):
            self._studio = Studio3D(self.config['video'])
            self.addCleanup(self._studio.close)
        return self._studio

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def scene(self):
        return copy.deepcopy(self.config['chapters'][0]['steps'][0]['scene3d'])

    def test_video_seek_is_reproducible_forward_backward_and_at_end(self):
        spec = self.scene()
        spec['devices'][0]['source'] = str(self.root / 'clip.mp4')
        early = self.studio.frame('video', spec, .2, .1)
        late = self.studio.frame('video', spec, 1.4, .7)
        again = self.studio.frame('video', spec, .2, .1)
        last = self.studio.frame('video', spec, 20, 1)
        r, g, b = early.getpixel((320, 180)); self.assertGreater(r, b + 150)
        r, g, b = late.getpixel((320, 180)); self.assertGreater(b, r + 150)
        self.assertEqual(early.tobytes(), again.tobytes())
        self.assertEqual(late.tobytes(), last.tobytes())

    def test_device_rotation_reveals_geometry_and_occludes_screen(self):
        spec = self.scene()
        spec['devices'][0]['keyframes'] = [
            {'at': 0, 'position': [0, 0, 0], 'rotation': [0, 0, 0]},
            {'at': 1, 'position': [0, 0, 0], 'rotation': [0, 180, 0]}]
        front = self.studio.frame('rotation', spec, 0, 0)
        edge = self.studio.frame('rotation', spec, 1, .5)
        back = self.studio.frame('rotation', spec, 2, 1)
        self.assertIsNotNone(ImageChops.difference(front, edge).getbbox())
        self.assertIsNotNone(ImageChops.difference(edge, back).getbbox())
        r, g, b = front.getpixel((320, 180)); self.assertGreater(r, b + 120)
        r, g, b = back.getpixel((320, 180)); self.assertLess(abs(r - b), 90)

    def test_all_device_models_and_multiple_devices_produce_visible_frames(self):
        for model in ('phone', 'tablet', 'laptop', 'panel', 'iphone-17-pro-max', 'macbook-pro-16'):
            with self.subTest(model=model):
                spec = self.scene(); spec['devices'][0]['model'] = model
                spec['devices'].append({**spec['devices'][0], 'position': [2, 0, -1], 'rotation': [5, -20, 5], 'finish': 'clay'})
                frame = self.studio.frame(model, spec, .3, .2)
                self.assertEqual(frame.size, (640, 360))
                self.assertGreater(sum(1 for px in frame.get_flattened_data() if max(px) > 70), 3000)

    def test_named_devices_occlude_screen_at_camera_cutouts_and_rear(self):
        for model in ('iphone-17-pro-max', 'macbook-pro-16'):
            with self.subTest(model=model):
                raw = copy.deepcopy(self.raw)
                device = raw['chapters'][0]['steps'][0]['scene3d']['devices'][0]
                device.update(model=model, fit='cover')
                write_json(self.root / 'named.json', raw)
                spec = load(self.root / 'named.json')['chapters'][0]['steps'][0]['scene3d']
                front = self.studio.frame(model + '-front', spec, 0, 0)
                is_red = lambda pixel: pixel[0] > pixel[1] + 100 and pixel[0] > pixel[2] + 100
                red = [(x, y) for y in range(360) for x in range(640) if is_red(front.getpixel((x, y)))]
                x0, x1 = min(x for x, y in red), max(x for x, y in red)
                y0, y1 = min(y for x, y in red), max(y for x, y in red)
                center, side = (x0 + x1) // 2, max(10, (x1 - x0) // 4)
                cutout_rows = [y for y in range(y0, y0 + (y1 - y0) // 6)
                               if is_red(front.getpixel((center - side, y)))
                               and is_red(front.getpixel((center + side, y)))
                               and not is_red(front.getpixel((center, y)))]
                self.assertGreaterEqual(len(cutout_rows), 2, 'Camera cutout must occlude the screen')
                self.assertTrue(is_red(front.getpixel((center, (y0 + y1) // 2))))
                spec['devices'][0]['rotation'] = [0, 180, 0]
                back = self.studio.frame(model + '-back', spec, 0, 0)
                self.assertLess(sum(is_red(px) for px in back.get_flattened_data()), 30)

    def test_capture_source_resolution_includes_3d_devices(self):
        raw = copy.deepcopy(self.raw)
        raw['chapters'][0]['steps'][0]['scene3d']['devices'][0]['source'] = 'capture:phone'
        resolve_images(raw, self.root, {'phone': str(self.root / 'red.png')})
        self.assertEqual(raw['chapters'][0]['steps'][0]['scene3d']['devices'][0]['source'], str(self.root / 'red.png'))

    def test_split_render_stays_inside_reserved_region(self):
        spec = self.scene()
        frame = self.studio.frame('region', spec, 0, 0, [340, 50, 280, 250])
        self.assertIsNone(frame.crop((0, 0, 340, 360)).getbbox())
        self.assertIsNone(frame.crop((0, 0, 640, 50)).getbbox())
        self.assertIsNone(frame.crop((0, 300, 640, 360)).getbbox())
        self.assertIsNotNone(frame.crop((340, 50, 620, 300)).getbbox())

    def test_invalid_scene_contracts_fail_before_rendering(self):
        invalid = [{'devices': []}, {'motion': 'unknown'}, {'camera': {'position': [0, 0, 0], 'target': [0, 0, 0]}},
                   {'devices': [{'model': 'watch', 'source': str(self.root / 'red.png')}]},
                   {'devices': [{'source': str(self.root / 'clip.mp4'), 'in': 50}]},
                   {'devices': [{'source': str(self.root / 'red.png'), 'rotation': [1, 2]}]}]
        for change in invalid:
            raw = copy.deepcopy(self.raw); raw['chapters'][0]['steps'][0]['scene3d'].update(change)
            write_json(self.root / 'invalid.json', raw)
            with self.assertRaises(VideoError): load(self.root / 'invalid.json')

    def test_split_copy_and_original_2d_mix_with_3d_in_pipeline(self):
        raw = copy.deepcopy(self.raw)
        raw['chapters'][0]['steps'][0]['content'] = {'layout': 'split', 'headline': '三维设备', 'body': '完整文案。'}
        raw['chapters'][0]['steps'][0]['scene3d']['devices'][0]['model'] = 'iphone-17-pro-max'
        raw['chapters'][0]['steps'].append({'at': .6, 'images': [str(self.root / 'blue.png')]})
        write_json(self.root / 'mixed.json', raw)
        config = load(self.root / 'mixed.json')
        folder = cache_location(self.root / 'output', config['chapters'][0], config['voice'])
        folder.mkdir(parents=True)
        audio = folder / 'voice.mp3'
        audio.write_bytes(run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1.2',
                               '-c:a', 'libmp3lame', '-f', 'mp3', 'pipe:1']))
        write_json(folder / 'metadata.json', {'duration': audio_duration(audio), 'sha256': file_hash(audio),
                    'events': [{'event': 364, 'data': {'words': [{'word': '测试。', 'startTime': .05, 'endTime': .9}]}}]})
        with patch('product_video.pipeline.generate', side_effect=AssertionError('No API')):
            rendered = build(config, allow_api=False)
        report = json.loads((rendered / 'verification.json').read_text())
        self.assertEqual(report['full_decode'], 'passed')
        self.assertEqual(report['renderer_3d']['revision'], '186')
        self.assertIn(str(self.root / 'red.png'), report['assets'])
        self.assertIn('middle', {p['phase'] for p in json.loads((rendered / 'preview/index.json').read_text())})

    def test_reduced_motion_freezes_3d_pose(self):
        config = copy.deepcopy(self.config); config['video']['reduced_motion'] = True
        config['chapters'][0]['steps'][0]['scene3d']['motion'] = 'orbit'
        chapters = [dict(config['chapters'][0], start=0, end=3, lead=0, audio_duration=3, cues=[])]
        with Renderer(config, chapters) as renderer:
            self.assertEqual(renderer.frame(.5).tobytes(), renderer.frame(2.5).tobytes())
