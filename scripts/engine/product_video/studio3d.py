"""Persistent, offline WebGL renderer with deterministic screen-video seeking."""
import base64
from contextlib import ExitStack
import copy
from io import BytesIO
import mimetypes
from pathlib import Path
import re
import tempfile
import sys
from urllib.parse import urlsplit

from PIL import Image, ImageOps

from .common import VideoError, run
from .scene3d import media_info


class Studio3D:
    def __init__(self, video):
        from playwright.sync_api import sync_playwright, Error

        self.video = video
        self.stack = ExitStack()
        self.specs = {}
        self.routes = {}
        self.media = {}
        try:
            self.temp = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix='product-video-3d-')))
            data = Path(__file__).parent / 'data'
            for path in [data / 'studio3d.html', data / 'studio3d.js', *(data / 'three').glob('*.js')]:
                self.routes['/' + path.relative_to(data).as_posix()] = path
            pw = self.stack.enter_context(sync_playwright())
            browser = pw.chromium.launch(headless=True, args=['--use-angle=metal'] if sys.platform == 'darwin' else [])
            self.stack.callback(browser.close)
            self.page = browser.new_page(viewport={'width': video['width'], 'height': video['height']}, device_scale_factor=1)
            self.page.route('**/*', self._route)
            self.page.goto('http://product-video.invalid/studio3d.html', wait_until='load')
            self.page.wait_for_function('window.studio !== undefined', timeout=15000)
            self.info = self.page.evaluate('([w,h]) => studio.init(w,h)', [video['width'], video['height']])
        except Error:
            self.close()
            raise VideoError('三维引擎无法启动。请运行 scripts/setup.sh 安装专用 Chromium，并确认 WebGL 2 可用。') from None
        except BaseException:
            self.close()
            raise

    def _route(self, route):
        url = urlsplit(route.request.url)
        path = self.routes.get(url.path) if url.hostname == 'product-video.invalid' else None
        if path is None:
            route.abort()
            return
        size = path.stat().st_size
        start, end = 0, size - 1
        range_header = route.request.headers.get('range', '')
        match = re.fullmatch(r'bytes=(\d+)-(\d*)', range_header)
        if match:
            start = int(match[1])
            end = min(end, int(match[2])) if match[2] else end
        if start > end or start >= size:
            route.fulfill(status=416, headers={'Content-Range': f'bytes */{size}'})
            return
        headers = {'Accept-Ranges': 'bytes'}
        if match:
            headers['Content-Range'] = f'bytes {start}-{end}/{size}'
        with path.open('rb') as source:
            source.seek(start)
            body = source.read(end - start + 1)
        route.fulfill(status=206 if match else 200, body=body, headers=headers,
                      content_type=mimetypes.guess_type(str(path))[0] or 'application/octet-stream')

    def _prepare(self, spec):
        prepared = copy.deepcopy(spec)
        for device in prepared['devices']:
            source = device['source']
            if source not in self.media:
                info = media_info(source)
                index = len(self.media)
                if info['type'] == 'video':
                    # Normalize codecs and display rotation once; recorded audio is deliberately separate from narration.
                    path = self.temp / f'{index}.mp4'
                    run(['ffmpeg', '-v', 'error', '-y', '-i', source, '-map', '0:v:0', '-an',
                         '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2', '-c:v', 'libx264', '-preset', 'fast',
                         '-crf', '16', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', path],
                        timeout=max(120, int(info['duration'] * 4)))
                    info = media_info(path)
                else:
                    path = self.temp / f'{index}.png'
                    with Image.open(source) as im:
                        ImageOps.exif_transpose(im).convert('RGB').save(path)
                url = '/media/' + path.name
                self.routes[url] = path
                self.media[source] = {'url': url, 'media': info}
            device.update(self.media[source])
        return prepared

    def frame(self, identifier, spec, elapsed, progress, region=None):
        from playwright.sync_api import Error

        try:
            if identifier not in self.specs:
                self.specs[identifier] = self._prepare(spec)
            encoded = self.page.evaluate('payload => studio.frame(payload)', {
                'id': identifier, 'spec': self.specs[identifier], 'elapsed': max(0, elapsed),
                'progress': min(1, max(0, progress)), 'reduced': self.video['reduced_motion'], 'region': region})
            with Image.open(BytesIO(base64.b64decode(encoded))) as frame:
                return frame.convert('RGB')
        except Error:
            raise VideoError('三维帧生成失败：屏幕素材解码、WebGL 或录屏定位未完成。请检查素材并降低预览分辨率后重试。') from None

    def close(self):
        self.stack.close()
