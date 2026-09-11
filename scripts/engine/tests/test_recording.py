from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from product_video.common import VideoError, file_hash, run, write_json
from product_video.recording import record_web


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class RecordingTests(unittest.TestCase):
    def test_recorded_click_and_scroll_change_actual_video_pixels(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'index.html').write_text('''<!doctype html><html><body style="background:#ef1010;margin:0">
                <button onclick="document.body.style.background='#1010ef'">Change</button>
                <div style="height:800px"></div><h2>End</h2><div style="height:400px"></div></body></html>''')
            server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(root)))
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            plan = {'schema_version': 1, 'target': {'provider': 'web',
                    'url': f'http://127.0.0.1:{server.server_port}/index.html', 'viewport': {'width': 400, 'height': 400}},
                    'shots': [{'id': 'before', 'ready': {'role': 'button', 'name': 'Change'}},
                              {'id': 'after', 'ready': {'role': 'heading', 'name': 'End'}, 'actions': [
                                  {'action': 'click', 'target': {'role': 'button', 'name': 'Change'}},
                                  {'action': 'scroll', 'target': {'role': 'heading', 'name': 'End'}}]}]}
            write_json(root / 'capture.json', plan)
            try:
                movie = record_web(root / 'capture.json', root / 'recording.mp4')
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=2)
            report = json.loads(movie.with_suffix('.recording.json').read_text())
            self.assertEqual(report['full_decode'], 'passed')
            self.assertEqual(report['sha256'], file_hash(movie))
            for at, channel in [(.2, 0), (report['duration'] - .2, 2)]:
                pixel = run(['ffmpeg', '-v', 'error', '-ss', str(at), '-i', movie, '-frames:v', '1',
                             '-vf', 'crop=100:100:200:100,scale=1:1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', 'pipe:1'])
                self.assertGreater(pixel[channel], 170)
                self.assertLess(pixel[2 - channel], 70)
            with self.assertRaisesRegex(VideoError, '已存在'):
                record_web(root / 'capture.json', movie)
