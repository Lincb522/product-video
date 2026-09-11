import copy
import json
from pathlib import Path
import tempfile
import unittest
import wave

from PIL import Image

from product_video.common import VideoError
from product_video.config import load
from product_video.capture import resolve_images
from product_video.shotcraft import catalogue, motion_item, timeline


class ShotcraftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root / 'screen.png'
        Image.new('RGB', (640, 360), '#258372').save(self.image)
        self.voice = self.root / 'voice.wav'
        with wave.open(str(self.voice), 'wb') as out:
            out.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
            out.writeframes(b'\0' * 48000 * 4 * 4)
        self.raw = {'schema_version': 2, 'product': {'name': 'Test'}, 'video': {}, 'chapters': [
            {'id': 'feature', 'title': 'Feature', 'narration': 'A visible feature.', 'steps': [
                {'at': 0, 'shotcraft': {'style': 'deck-deal-flyin', 'media': {'textures/live/card1.png': 'screen.png'}}},
                {'at': .4, 'images': ['screen.png']},
                {'at': .7, 'shotcraft': {'style': 'row-embed'}}]}]}

    def config(self, raw=None):
        path = self.root / 'project.json'
        path.write_text(json.dumps(raw or self.raw))
        return load(path)

    def test_gallery_variants_resolve_to_present_components(self):
        data = catalogue()
        self.assertEqual(data['missing'], [])
        self.assertEqual(len({m['style'] for m in data['motions']}), len(data['motions']))
        self.assertGreaterEqual(len(data['motions']), data['gallery']['styleCount'])
        for item in data['motions']:
            self.assertEqual(motion_item(item['style'])['component'], item['component'])
            self.assertGreater(item['frames'], 1)

    def test_schema_one_keeps_legacy_and_two_selects_remotion(self):
        self.assertEqual(self.config()['video']['renderer'], 'remotion')
        old = copy.deepcopy(self.raw)
        old['schema_version'] = 1
        old['chapters'][0]['steps'] = [{'at': 0, 'images': ['screen.png']}]
        self.assertEqual(self.config(old)['video']['renderer'], 'legacy')

    def test_motion_cannot_silently_drop_visual_or_pointer_fields(self):
        for field, value in [('images', ['screen.png']), ('cursor', [.5, .5]), ('content', {'layout': 'title', 'headline': 'Hidden'})]:
            raw = copy.deepcopy(self.raw)
            raw['chapters'][0]['steps'][0][field] = value
            with self.assertRaises(VideoError):
                self.config(raw)

    def test_unknown_style_and_missing_media_fail_before_voice(self):
        raw = copy.deepcopy(self.raw)
        raw['chapters'][0]['steps'][0]['shotcraft']['style'] = 'invented-effect'
        with self.assertRaises(VideoError): self.config(raw)
        raw['chapters'][0]['steps'][0]['shotcraft']['style'] = 'deck-deal-flyin'
        raw['chapters'][0]['steps'][0]['shotcraft']['media']['textures/live/card1.png'] = 'missing.png'
        with self.assertRaises(VideoError): self.config(raw)

    def test_capture_reference_reaches_motion_texture(self):
        raw = copy.deepcopy(self.raw)
        raw['chapters'][0]['steps'][0]['shotcraft']['media'] = {'textures/live/card1.png': 'capture:screen'}
        resolve_images(raw, self.root, {'screen': str(self.image)})
        spec = raw['chapters'][0]['steps'][0]['shotcraft']
        self.assertEqual(spec['media']['textures/live/card1.png'], str(self.image))

    def test_voice_boundaries_keep_shots_and_captions_on_shared_frame_clock(self):
        config = self.config()
        chapter = config['chapters'][0] | {'start': 0, 'end': 4.5, 'lead': .25, 'audio_duration': 4,
            'audio': str(self.voice), 'audio_sha256': 'cached', 'cues': [{'start': .25, 'end': 2.11, 'text': 'One'}, {'start': 2.11, 'end': 4.25, 'text': 'Two'}]}
        calls = []
        def plate(ci, si, start, end):
            calls.append((ci, si, start, end))
            return self.image
        project = timeline(config, [chapter], self.root/'public', plate)
        tracks = {t['id']: t['clips'] for t in project['tracks']}
        shots = tracks['shots']
        self.assertEqual(shots[0]['start'], 0)
        self.assertEqual(shots[-1]['start'] + shots[-1]['duration'], 135)
        for before, after in zip(shots, shots[1:]):
            self.assertEqual(before['start'] + before['duration'], after['start'])
        self.assertEqual(calls, [(0, 1, 56, 92)])
        self.assertEqual(tracks['narration'][0]['start'], round(.25 * 30))
        self.assertEqual(tracks['captions'][0]['start'], tracks['narration'][0]['start'])
        self.assertEqual(tracks['captions'][0]['start'] + tracks['captions'][0]['duration'], tracks['captions'][1]['start'])
        self.assertEqual(tracks['narration'][0]['speed'], 1)
        source_frames = motion_item('deck-deal-flyin')['frames']
        self.assertAlmostEqual(shots[0]['speed'] * (shots[0]['duration']-1), source_frames-1)
        copied = self.root/'public'/shots[0]['props']['mediaMap']['textures/live/card1.png']
        self.assertEqual(copied.read_bytes(), self.image.read_bytes())

    def test_external_transitions_do_not_move_audio_boundaries(self):
        config = self.config()
        config['chapters'][0]['steps'][1]['transition'] = 'iris'
        config['chapters'][0]['steps'][2]['transition'] = 'depth-slide'
        chapter = config['chapters'][0] | {'start': 0, 'end': 4.5, 'lead': .25, 'audio_duration': 4,
            'audio': str(self.voice), 'audio_sha256': 'cached', 'cues': []}
        project = timeline(config, [chapter], self.root/'public', lambda *a: self.image)
        shots = next(t for t in project['tracks'] if t['id'] == 'shots')['clips']
        self.assertNotIn('transition', shots[0])
        self.assertEqual(shots[1]['transition']['kind'], 'iris')
        self.assertEqual(shots[2]['transition']['kind'], 'depth-slide')
        self.assertLessEqual(shots[1]['transition']['duration'], shots[1]['duration'])
        self.assertEqual(shots[1]['start'], 56)
        self.assertEqual(shots[2]['start'], 92)

    def test_sound_is_independent_from_narration(self):
        self.raw['audio'] = {'sfx': [{'source': str(self.voice), 'start': 1, 'duration': .5, 'volume': .2}]}
        config = self.config()
        chapter = config['chapters'][0] | {'start': 0, 'end': 4.5, 'lead': .25, 'audio_duration': 4,
            'audio': str(self.voice), 'audio_sha256': 'cached', 'cues': []}
        project = timeline(config, [chapter], self.root/'public', lambda *a: self.image)
        sound = next(t for t in project['tracks'] if t['id'] == 'sfx')['clips'][0]
        self.assertEqual((sound['start'], sound['duration'], sound['props']['volume']), (30, 15, .2))
        narration = next(t for t in project['tracks'] if t['id'] == 'narration')['clips'][0]
        self.assertEqual((narration['speed'], narration['props']['volume']), (1, 1))

    def test_capture_action_requires_native_before_state(self):
        self.raw['chapters'][0]['steps'][1]['interaction'] = {'kind': 'click', 'to': [.5, .5]}
        with self.assertRaisesRegex(VideoError, '操作前后'):
            self.config()

    def test_reduced_motion_holds_completed_card_without_speeding_voice(self):
        self.raw['video']['reduced_motion'] = True
        self.raw['chapters'][0]['steps'] = self.raw['chapters'][0]['steps'][:1]
        config = self.config()
        chapter = config['chapters'][0] | {'start': 0, 'end': 4.5, 'lead': .25, 'audio_duration': 4,
            'audio': str(self.voice), 'audio_sha256': 'cached', 'cues': []}
        project = timeline(config, [chapter], self.root/'public', lambda *a: self.image)
        shot = next(t for t in project['tracks'] if t['id'] == 'shots')['clips'][0]
        self.assertEqual(shot['speed'], 0)
        self.assertEqual(shot['inOffset'], motion_item('deck-deal-flyin')['frames']-1)


if __name__ == '__main__':
    unittest.main()
