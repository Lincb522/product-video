import asyncio
import base64
import copy
import gzip
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from product_video import credentials, voices
from product_video.common import VideoError, file_hash, write_json
from product_video.config import load
from product_video.demo import create
from product_video.http_tts import StreamResult
from product_video.pipeline import project_lock
from product_video.protocol import blob, decode, encode
from product_video.render import Renderer, fit_rect
from product_video.subtitles import from_events, srt, timestamp
from product_video.tts import DEFAULT_VOICE, cache_location, cached_audio, exchange, request_params


def event_frame(event, payload=b'{}', sid='session', kind=9):
    identity = b'connection' if event in (50, 51, 52) else sid.encode()
    return bytes([0x11, (kind << 4) | 4, 0x10, 0]) + struct.pack('>I', event) + blob(identity) + blob(payload)


class ProtocolTests(unittest.TestCase):
    def test_start_frame(self):
        self.assertEqual(encode(1), bytes.fromhex('1114100000000001000000027b7d'))

    def test_session_audio(self):
        msg = decode(event_frame(352, b'abc', kind=11))
        self.assertEqual((msg.event, msg.payload, msg.session_id), (352, b'abc', 'session'))

    def test_truncated_frames(self):
        frame = event_frame(364)
        for end in range(len(frame)):
            with self.assertRaises(VideoError):
                decode(frame[:end])
        with self.assertRaises(VideoError):
            decode(frame + b'x')

    def test_compression_and_error(self):
        frame = bytearray(event_frame(364, gzip.compress(b'{}')))
        frame[2] = 0x11
        self.assertEqual(decode(bytes(frame)).payload, b'{}')
        error = bytes([0x11, 0xf0, 0x10, 0]) + struct.pack('>I', 45000000) + blob(b'private detail')
        self.assertEqual(decode(error).error_code, 45000000)


class ExchangeTests(unittest.IsolatedAsyncioTestCase):
    def socket(self, ending=None, audio=True):
        class Socket:
            def __init__(self):
                self.sent = []
                self.responses = [event_frame(50), event_frame(150)]
                if audio:
                    self.responses.append(event_frame(352, b'mp3', kind=11))
                self.responses += [ending or event_frame(152), event_frame(52)]

            async def recv(self):
                await asyncio.sleep(0)
                return self.responses.pop(0)

            async def send(self, value):
                self.sent.append(value)
        return Socket()

    async def test_end_to_end_protocol(self):
        ws = self.socket()
        with patch('product_video.tts.uuid.uuid4', return_value='session'):
            result = await exchange(ws, '测试', request_params(DEFAULT_VOICE))
        self.assertEqual(result[0], b'mp3')
        self.assertEqual([struct.unpack('>I', x[4:8])[0] for x in ws.sent], [1, 100, 200, 102, 2])

    async def test_no_audio_is_not_success(self):
        with patch('product_video.tts.uuid.uuid4', return_value='session'), self.assertRaises(VideoError):
            await exchange(self.socket(audio=False), '测试', request_params(DEFAULT_VOICE))

    async def test_session_mismatch(self):
        with self.assertRaises(ExceptionGroup):
            with patch('product_video.tts.uuid.uuid4', return_value='session'):
                await exchange(self.socket(event_frame(152, sid='other')), '测试', request_params(DEFAULT_VOICE))

    async def test_timeout_is_finite(self):
        class Socket:
            async def send(self, value):
                pass
            async def recv(self):
                await asyncio.Event().wait()
        with self.assertRaises(TimeoutError):
            await exchange(Socket(), '测试', {}, idle_timeout=0.01)


class HttpTests(unittest.TestCase):
    def test_stream_complete(self):
        stream = StreamResult()
        stream.feed(json.dumps({'code': 0, 'data': base64.b64encode(b'mp3').decode(), 'sentence': {'words': [{'word': 'a'}], 'text': 'a'}}))
        stream.feed('{"code":20000000}')
        audio, events, _ = stream.result()
        self.assertEqual(audio, b'mp3')
        self.assertEqual(events[0]['event'], 364)

    def test_truncated_and_empty(self):
        for line in ('{"code":0}', '{"code":20000000}'):
            stream = StreamResult()
            stream.feed(line)
            with self.assertRaises(VideoError):
                stream.result()

    def test_error_redaction(self):
        with self.assertRaises(VideoError) as e:
            StreamResult().feed('{"code":45000000,"message":"secret-test-credential"}')
        self.assertNotIn('secret-test-credential', str(e.exception))
        self.assertIn('45000000', str(e.exception))

    def test_malformed(self):
        for value in ('[]', '{}', '{"code":"secret"}', '{"code":0,"data":"%%%"}'):
            with self.assertRaises(VideoError):
                StreamResult().feed(value)


class SubtitleTests(unittest.TestCase):
    def cues(self, values, text):
        return from_events([{'event': 364, 'data': {'words': [
            {'startTime': i * 0.5, 'endTime': i * 0.5 + 0.4, 'word': s} for i, s in enumerate(values)]}}], text, 10)

    def test_chinese_punctuation(self):
        result = self.cues(['你', '好，', '世', '界。'], '你好，世界。')
        self.assertEqual([c['text'] for c in result], ['你好，', '世界。'])
        self.assertEqual(result[1]['start'], 1)

    def test_english_spacing(self):
        result = self.cues(['Hello', 'world.', 'Start', 'now.'], 'Hello world. Start now.')
        self.assertEqual([c['text'] for c in result], ['Hello world.', 'Start now.'])

    def test_standalone_punctuation_extends_spoken_word(self):
        result = self.cues(['测', '试', '。'], '测试。')
        self.assertEqual(result, [{'start': 0, 'end': 1.4, 'text': '测试。'}])

    def test_punctuation_and_whitespace_never_create_empty_cues(self):
        result = self.cues(['“', 'Hello', ' ', 'world', '.', '”', ' ', 'Next', '!'], '“Hello world.” Next!')
        self.assertTrue(all(c['text'].strip() for c in result))
        self.assertEqual(''.join(c['text'] for c in result), '“Hello world.” Next!')
        self.assertEqual(result[-1]['end'], 4.4)

    def test_punctuation_timestamps_are_still_validated(self):
        words = [{'word': 'a', 'startTime': 0, 'endTime': .4},
                 {'word': '.', 'startTime': .5, 'endTime': .1}]
        with self.assertRaisesRegex(VideoError, '时间戳'):
            from_events([{'event': 364, 'data': {'words': words}}], 'a.', 2)

    def test_mismatch_and_no_captions(self):
        with self.assertRaises(VideoError):
            self.cues(['一'], '1')
        with self.assertRaises(VideoError):
            from_events([], 'hello', 1)

    def test_invalid_timestamps(self):
        for start, end in ((-1, 1), (1, 0), (0, 20), (float('nan'), 1)):
            with self.assertRaises(VideoError):
                from_events([{'event': 364, 'data': {'words': [{'word': 'a', 'startTime': start, 'endTime': end}]}}], 'a', 2)

    def test_srt_rounding(self):
        self.assertEqual(timestamp(59.9999), '00:01:00,000')
        self.assertIn('00:00:01,000 --> 00:00:02,000', srt([{'start': 1, 'end': 2, 'text': '你好'}]))


class VoiceTests(unittest.TestCase):
    def test_complete_catalog(self):
        catalog = voices.catalog()
        self.assertEqual(catalog['source_rows'], 552)
        self.assertEqual(len(catalog['voices']), 547)
        self.assertEqual(len({v['id'] for v in catalog['voices']}), 547)
        self.assertEqual(len(voices.search(model='2.0')), 444)

    def test_selection_and_search(self):
        self.assertEqual(voices.resolve('小何2.0')['id'], DEFAULT_VOICE['speaker'])
        self.assertTrue(voices.search(language='日'))
        self.assertEqual(voices.resolve('Sven')['transport'], 'http')
        for entry in voices.catalog()['voices']:
            self.assertEqual(voices.settings(entry['id'])['resource_id'], 'seed-tts-' + entry['model'])
        with self.assertRaises(VideoError):
            voices.resolve('not-a-real-voice')

    def test_no_context_for_context_voice_or_legacy(self):
        for name in ('Sven', voices.search(model='1.0')[0]['id']):
            voice = copy.deepcopy(DEFAULT_VOICE) | voices.settings(name)
            self.assertNotIn('context_texts', json.loads(request_params(voice)['additions']))
        self.assertIn('context_texts', json.loads(request_params(DEFAULT_VOICE)['additions']))


class LocalTests(unittest.TestCase):
    def test_credentials_with_synthetic_store(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / 'auth' / 'credentials.json'
            credentials.save_key('synthetic-key-only', p)
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            self.assertEqual(credentials.load_key(p), 'synthetic-key-only')
            p.chmod(0o644)
            with self.assertRaises(VideoError):
                credentials.load_key(p)

    def test_cache_integrity_and_invalidation(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'voice.mp3').write_bytes(b'mock')
            write_json(folder / 'metadata.json', {'sha256': file_hash(folder / 'voice.mp3'), 'duration': 1})
            self.assertEqual(cached_audio(folder)['duration'], 1)
            (folder / 'voice.mp3').write_bytes(b'changed')
            with self.assertRaises(VideoError):
                cached_audio(folder)
            self.assertNotEqual(cache_location(folder, {'narration': 'a'}, DEFAULT_VOICE),
                                cache_location(folder, {'narration': 'b'}, DEFAULT_VOICE))
            self.assertEqual(cache_location(folder, {'narration': 'a'}, DEFAULT_VOICE),
                             cache_location(folder, {'narration': 'a'}, DEFAULT_VOICE | voices.settings('小何 2.0')))

    def test_output_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            with project_lock(Path(temp)):
                with self.assertRaises(VideoError):
                    with project_lock(Path(temp)):
                        pass


class ConfigRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.project = create(Path(cls.temp.name) / 'project')
        cls.original = json.loads(cls.project.read_text())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        write_json(self.project, self.original)

    def test_validation_failures(self):
        for field, value in (('fps', True), ('width', 1921), ('height', 720), ('subtitles', 'fake'), ('background', 3)):
            bad = copy.deepcopy(self.original)
            bad['video'][field] = value
            write_json(self.project, bad)
            with self.assertRaises(VideoError):
                load(self.project)

    def test_old_voice_resource_derived(self):
        bad = copy.deepcopy(self.original)
        bad['voice'] = {'speaker': voices.search(model='1.0')[0]['id']}
        write_json(self.project, bad)
        self.assertEqual(load(self.project)['voice']['resource_id'], 'seed-tts-1.0')

    def test_renderer_720_and_1080(self):
        for w, h in ((1280, 720), (1920, 1080)):
            c = load(self.project)
            c['video'].update(width=w, height=h)
            chapters = [{**chapter, 'start': i*5, 'end': (i+1)*5, 'lead': .6, 'audio_duration': 4,
                         'cues': [{'start': i*5+1, 'end': i*5+4, 'text': '中文 English 测试字幕。'}]}
                        for i, chapter in enumerate(c['chapters'])]
            renderer = Renderer(c, chapters)
            for t in (0, 1, 3.1, 5, 5.3, 7, 9.99):
                frame = renderer.frame(t)
                self.assertEqual(frame.size, (w, h))
            for ci in range(2):
                for si in range(len(chapters[ci]['steps'])):
                    _, rects = renderer.step_frame(ci, si)
                    for x, y, rw, rh in rects:
                        self.assertTrue(0 <= x < x + rw <= w)
                        self.assertTrue(0 <= y < y + rh < h)

    def test_fit_preserves_entire_image(self):
        self.assertEqual(fit_rect((400, 800), (0, 0, 400, 400)), (100, 0, 200, 400))


if __name__ == '__main__':
    unittest.main()
