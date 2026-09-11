import copy
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw, ImageChops

from product_video.common import write_json
from product_video.config import load
from product_video.compositor import Renderer
from product_video.motion import PRESETS


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, color in [('before', '#c62828'), ('after', '#1565c0')]:
            image = Image.new('RGB', (1440, 900), color)
            d = ImageDraw.Draw(image)
            for x, y, shade in [(0, 0, '#ffcd00'), (1380, 0, '#00cc88'), (0, 840, '#bb44ff'), (1380, 840, '#ffffee')]:
                d.rectangle((x, y, x+60, y+60), fill=shade)
            image.save(self.root/f'{name}.png')
        self.raw = {'schema_version': 1, 'product': {'name': 'Product'},
                    'video': {'width': 1280, 'height': 720, 'camera_motion': 'none', 'subtitles': 'none'},
                    'chapters': [{'id': 'workflow', 'title': '主题与实时预览', 'narration': 'Test.', 'steps': [
                        {'at': 0, 'images': ['before.png'], 'labels': ['选择主题']},
                        {'at': .4, 'images': ['after.png'], 'labels': ['查看结果'],
                         'interaction': {'kind': 'click', 'from': [.3, .6], 'to': [.2, .3]}},
                        {'at': .8, 'images': ['before.png', 'after.png'], 'labels': ['调整前', '调整后']}]}]}

    def renderer(self, style, **video):
        raw = copy.deepcopy(self.raw)
        raw['video'].update(style=style, **video)
        path = self.root/'project.json'
        write_json(path, raw)
        config = load(path)
        chapters = [{**c, 'start': 0, 'end': 11, 'lead': .6, 'audio_duration': 10., 'cues': []}
                    for c in config['chapters']]
        renderer = Renderer(config, chapters)
        self.addCleanup(renderer.close)
        return renderer

    def test_styles_have_distinct_geometry_even_with_identical_colors(self):
        for count, step in [(1, 0), (2, 2)]:
            bounds, frames = set(), set()
            for style in PRESETS:
                r = self.renderer(style, background='#f0f0f0', surface='#cccccc', foreground='#101010', accent='#555555')
                bounds.add(tuple(r.layout(0, step)))
                frames.add(r.frame(2 if count == 1 else 10).convert('L').tobytes())
            self.assertEqual(len(bounds), len(PRESETS), 'Changing style must change the actual composition, not only its palette.')
            self.assertEqual(len(frames), len(PRESETS))

    def test_each_layout_preserves_all_four_screenshot_corners_at_delivery_sizes(self):
        for width in (1280, 1920):
            for style in PRESETS:
                with self.subTest(style=style, width=width):
                    r = self.renderer(style, width=width, height=round(width*9/16))
                    for step in (0, 2):
                        frame, _ = r.step_frame(0, step)
                        for x, y, w, h in r.layout(0, step):
                            self.assertGreaterEqual(x, 0); self.assertGreaterEqual(y, 0)
                            self.assertLessEqual(x+w, r.w); self.assertLessEqual(y+h, r.h-100*r.scale)
                            for u, v, color in [(.02, .03, (255,205,0)), (.98,.03,(0,204,136)), (.02,.97,(187,68,255)), (.98,.97,(255,255,238))]:
                                actual = frame.getpixel((round(x+w*u), round(y+h*v)))
                                self.assertTrue(all(abs(a-b) < 3 for a,b in zip(actual,color)), (style, actual, color))

    def test_entrances_are_visible_and_reduced_motion_holds_the_complete_image(self):
        for style in PRESETS:
            r = self.renderer(style)
            early, late = (r.frame(t).crop((0, 0, r.w, r.h-8)) for t in (.8, 2.5))
            changed = ImageChops.difference(early, late).getbbox() is not None
            self.assertEqual(changed, style not in ('classic', 'tutorial'), style)
            quiet = self.renderer(style, reduced_motion=True)
            self.assertEqual(quiet.frame(.8).crop((0,0,r.w,r.h-8)).tobytes(), quiet.frame(2.5).crop((0,0,r.w,r.h-8)).tobytes(), style)

    def test_all_styles_keep_click_before_state_and_pointer_in_the_same_viewport(self):
        for style in PRESETS:
            r = self.renderer(style)
            track = r.tracks[0, 1]
            rect = r.layout(0, 0)[0]
            x,y,w,h = rect
            center = (round(x+w*.6), round(y+h*.6))
            for elapsed in (track['press']*.5, track['press'], track['reveal']-.01):
                frame = r.frame(4.6+elapsed)
                self.assertEqual(frame.getpixel(center), (198,40,40), style)
            result_time = 4.6+track['reveal']+r.transitions[0,1][1]+.1
            self.assertEqual(r.frame(result_time).getpixel(center), (21,101,192), style)
            self.assertEqual(r.layout(0,0), r.layout(0,1), style)

    def test_long_chapter_titles_and_tutorial_step_window_render_completely(self):
        self.raw['chapters'][0]['title'] = '界面主题与实时预览 · Appearance and live preview'
        self.raw['chapters'][0]['steps'] = [
            {'at': i/12, 'images': ['before.png'], 'labels': [f'第 {i+1} 步：查看主题变化']}
            for i in range(12)]
        for style in PRESETS:
            r = self.renderer(style)
            self.assertEqual(r.frame(10).size, (1280,720))

    def test_short_heading_does_not_leave_one_character_on_a_separate_line(self):
        r = self.renderer('product')
        image = Image.new('RGB', (r.w,r.h))
        r.presentation.heading(image, '画面与版式', (64,272,316,360), 64)
        box = image.getbbox()
        self.assertIsNotNone(box)
        self.assertLessEqual(box[3]-box[1], r.px(64))


if __name__ == '__main__':
    unittest.main()
