"""One-shot local credential setup; the browser owns secret input."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets
import time
from urllib.parse import parse_qs
import webbrowser

from . import credentials
from .common import VideoError

GUIDE_URL = 'https://www.volcengine.com/docs/6561/1167802?lang=zh'
CONSOLE_URL = 'https://console.volcengine.com/speech/new/overview'


class SetupServer(HTTPServer):
    allow_reuse_address = False

    def __init__(self, path=None):
        self.credential_file = path or credentials.credential_path()
        self.csrf = secrets.token_urlsafe(32)
        self.saved = False
        self.cancelled = False
        super().__init__(('127.0.0.1', 0), SetupHandler)
        self.origin = f'http://127.0.0.1:{self.server_port}'
        self.timeout = 0.5

    def get_request(self):
        sock, address = super().get_request()
        sock.settimeout(5)
        return sock, address

    def handle_error(self, request, client_address):
        # The HTTP body can contain a credential; never dump a request or traceback.
        pass


class SetupHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, value, content_type='application/json; charset=utf-8'):
        body = value.encode() if isinstance(value, str) else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        for k, v in {'Content-Type': content_type, 'Content-Length': str(len(body)),
                     'Cache-Control': 'no-store', 'Referrer-Policy': 'same-origin',
                     'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
                     'Content-Security-Policy': "default-src 'none'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"}.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def host_ok(self):
        return self.headers.get('Host') == self.server.origin.removeprefix('http://')

    def do_GET(self):
        if not self.host_ok():
            return self.reply(403, {'error': '仅允许本机配置页面访问。'})
        if self.path == '/':
            body = (Path(__file__).parent / 'data' / 'setup.html').read_text()
            return self.reply(200, body.replace('{{CSRF}}', self.server.csrf), 'text/html; charset=utf-8')
        if self.path == '/setup.js':
            return self.reply(200, (Path(__file__).parent / 'data' / 'setup.js').read_text(), 'text/javascript; charset=utf-8')
        return self.reply(404, {'error': '页面不存在。'})

    def do_POST(self):
        if not self.host_ok() or self.headers.get('Origin') != self.server.origin:
            return self.reply(403, {'error': '请从本机配置页面提交。'})
        if self.path not in ('/save', '/cancel'):
            return self.reply(404, {'error': '页面不存在。'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/x-www-form-urlencoded':
            return self.reply(415, {'error': '提交格式不支持。'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096:
                raise ValueError()
            form = parse_qs(self.rfile.read(length).decode(), strict_parsing=True, keep_blank_values=True)
            if not secrets.compare_digest(form.get('csrf', [''])[0], self.server.csrf):
                return self.reply(403, {'error': '配置页面已失效，请重新打开。'})
            if self.server.saved or self.server.cancelled:
                return self.reply(409, {'error': '此次配置已结束。'})
            if self.path == '/cancel':
                self.server.cancelled = True
                return self.reply(200, {'message': '已取消，原有配置未改动。'})
            if set(form) != {'csrf', 'key'} or len(form['key']) != 1:
                raise ValueError()
            credentials.save_key(form['key'][0].strip(), self.server.credential_file)
        except (ValueError, UnicodeError, VideoError):
            return self.reply(400, {'error': '密钥为空、包含空白或格式不正确，请重新粘贴。'})
        except OSError:
            return self.reply(500, {'error': '凭据未保存，请检查本地配置目录的写入权限后重试。'})
        self.server.saved = True
        return self.reply(200, {'message': '已保存。关闭此页即可，制作任务会继续。配音权限将在首次生成时验证。'})


def setup(timeout=900, open_browser=True, replace=False, path=None, on_ready=None):
    path = path or credentials.credential_path()
    if not replace and credentials.is_configured(path):
        print('本地凭据已配置，自动沿用；未修改密钥。')
        return
    with SetupServer(path) as server:
        print(f'首次配置：{server.origin}', flush=True)
        print('按页面指引获取豆包语音 API Key，然后在本机页面粘贴一次。不要发到对话里。', flush=True)
        if on_ready:
            on_ready(server)
        if open_browser:
            webbrowser.open(server.origin)
        deadline = time.monotonic() + timeout
        while not server.saved and not server.cancelled and time.monotonic() < deadline:
            server.handle_request()
        if server.saved:
            print('凭据已安全保存，后续自动读取。未额外调用计费 API。')
            return
        if server.cancelled:
            raise VideoError('首次配置已取消；再次运行任务可继续，原有文件未改动。')
        raise VideoError('等待密钥配置超时，本机页面已关闭；重新运行 credentials setup 后继续。')
