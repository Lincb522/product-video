import contextlib
import copy
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from PIL import Image

from product_video import credentials
from product_video.capture import capture_project, capture_web, read_plan, web_error, web_session
from product_video.common import VideoError, file_hash, write_json
from product_video.onboarding import SetupServer, setup


@contextlib.contextmanager
def serving(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown(); server.server_close(); thread.join(5)


class SetupTests(unittest.TestCase):
    def request(self, server, method='GET', path='/', fields=None, headers=None):
        c = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        h = {'Origin': server.origin, 'Content-Type': 'application/x-www-form-urlencoded'} | (headers or {})
        c.request(method, path, body=urlencode(fields) if fields else None, headers=h)
        r = c.getresponse(); status = r.status; body = r.read().decode(); c.close()
        return status, body

    def test_safe_save_and_no_response_echo(self):
        with tempfile.TemporaryDirectory() as d, serving(SetupServer(Path(d)/'settings/credentials.json')) as s:
            status, page = self.request(s)
            self.assertEqual(status, 200)
            self.assertIn('type="password"', page)
            self.assertIn('method="post" action="/save"', page)
            fake = 'synthetic-key-for-unit-test'
            status, body = self.request(s, 'POST', '/save', {'csrf': s.csrf, 'key': fake})
            self.assertEqual(status, 200); self.assertNotIn(fake, body); self.assertTrue(s.saved)
            self.assertEqual(credentials.load_key(s.credential_file), fake)
            self.assertEqual(s.credential_file.stat().st_mode & 0o777, 0o600)
            status, _ = self.request(s, 'POST', '/save', {'csrf': s.csrf, 'key': 'another-synthetic-key'})
            self.assertEqual(status, 409)

    def test_origin_host_csrf_and_invalid_input_do_not_write(self):
        with tempfile.TemporaryDirectory() as d, serving(SetupServer(Path(d)/'credentials.json')) as s:
            data = {'csrf':s.csrf, 'key':'synthetic-test-key'}
            self.assertEqual(self.request(s,'POST','/save',data,{'Origin':'https://example.org'})[0],403)
            self.assertEqual(self.request(s,'POST','/save',data,{'Host':'attacker.invalid'})[0],403)
            self.assertEqual(self.request(s,'POST','/save',data | {'csrf':'wrong'})[0],403)
            self.assertEqual(self.request(s,'POST','/save',data | {'key':'bad key'})[0],400)
            self.assertFalse(s.credential_file.exists())

    def test_cancel_and_write_failure(self):
        with tempfile.TemporaryDirectory() as d, serving(SetupServer(Path(d)/'credentials.json')) as s:
            with patch('product_video.credentials.save_key', side_effect=PermissionError()):
                code, body = self.request(s, 'POST','/save',{'csrf':s.csrf,'key':'synthetic-key'})
                self.assertEqual(code, 500); self.assertNotIn('synthetic-key', body); self.assertFalse(s.saved)
            self.assertEqual(self.request(s,'POST','/cancel',{'csrf':s.csrf})[0],200)
            self.assertTrue(s.cancelled); self.assertFalse(s.credential_file.exists())

    def test_existing_key_setup_reads_metadata_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'config/credentials.json'; credentials.save_key('synthetic-test-key',p)
            with patch.object(Path, 'read_text', side_effect=AssertionError('must not read')), patch('webbrowser.open') as browser:
                setup(path=p); browser.assert_not_called()

    def test_setup_timeout_is_finite(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaisesRegex(VideoError,'超时'):
            setup(timeout=.05, open_browser=False, path=Path(d)/'credentials.json')

    def test_no_javascript_form_uses_post_not_url(self):
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory() as d, serving(SetupServer(Path(d)/'credentials.json')) as server, sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            try:
                page=browser.new_page(java_script_enabled=False)
                page.goto(server.origin)
                page.get_by_label('豆包语音 API Key').fill('synthetic-browser-test')
                page.get_by_role('button',name='保存并继续').click()
                page.wait_for_url(server.origin+'/save')
                self.assertTrue(server.saved)
                self.assertNotIn('synthetic-browser-test', page.url)
                self.assertNotIn('synthetic-browser-test', page.locator('body').inner_text())
            finally: browser.close()

    def test_setup_resumes_after_submission(self):
        results=[];threads=[]
        def ready(server):
            thread=threading.Thread(target=lambda: results.append(self.request(server,'POST','/save',{'csrf':server.csrf,'key':'synthetic-resume-test'})))
            threads.append(thread);thread.start()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'auth/credentials.json'
            setup(timeout=5,open_browser=False,path=path,on_ready=ready)
            for thread in threads: thread.join(5)
            self.assertEqual(results[0][0],200);self.assertTrue(credentials.is_configured(path))


PAGE = b'''<!doctype html><meta charset="utf-8"><style>body{font:24px sans-serif;background:#f3f6fc}body.dark{background:#172c43;color:white}.secret{position:absolute;left:100px;top:200px;width:180px;height:45px;background:red}</style><h1>Capture Fixture</h1><button onclick="document.body.className='dark';document.querySelector('h1').textContent='Dark Ready'">Dark theme</button><input aria-label="Search" onchange="document.querySelector('#query').textContent=this.value"><p id="query"></p><div class="secret">PRIVATE FIXTURE</div><input type="password" value="synthetic-secret"><img src="/pixel.png"><a href="https://example.org/">Leave site</a>'''

SCROLL_PAGE = b'''<!doctype html><style>body{margin:0;font:24px sans-serif}h2{margin:0}section{height:150px}footer{height:1200px}</style><header style="height:200px">Overview</header><section><h2>Features</h2><p>Feature details</p></section><section><h2>Install</h2><pre>install product-video</pre></section><footer>End</footer>'''


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        if self.path == '/pixel.png':
            import io
            f=io.BytesIO();Image.new('RGB',(10,10),'blue').save(f,format='PNG');body=f.getvalue();ct='image/png'
        else: body=SCROLL_PAGE if self.path == '/scroll' else PAGE;ct='text/html'
        self.send_response(200)
        if self.path == '/csp':
            self.send_header('Content-Security-Policy', "script-src 'self'")
        self.send_header('Content-Type',ct);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)


class CaptureTests(unittest.TestCase):
    def test_captured_points_resolve_to_real_control_center_at_both_densities(self):
        with tempfile.TemporaryDirectory() as d, serving(ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)) as server:
            for width in (390, 1440):
                folder = Path(d) / str(width); folder.mkdir()
                plan = self.project(folder, f'http://127.0.0.1:{server.server_port}')
                plan['target']['viewport']['width'] = width
                plan['shots'][0]['points'] = {'theme': {'role': 'button', 'name': 'Dark theme'}}
                write_json(folder / 'capture.json', plan)
                raw = json.loads((folder / 'project.json').read_text())
                raw['chapters'][0]['steps'][1]['interaction'] = {'kind': 'click', 'to': 'capture:before:theme'}
                write_json(folder / 'project.json', raw)
                compiled = capture_project(folder / 'project.json')
                project = json.loads(compiled.read_text())
                point = project['chapters'][0]['steps'][1]['interaction']['to']
                manifest = json.loads((compiled.parent / 'manifest.json').read_text())
                self.assertEqual(point, manifest['shots'][0]['points']['theme'])
                self.assertEqual(manifest['shots'][0]['size'], [width * 2, 1200])
                with web_session(plan['target']) as page:
                    box = page.get_by_role('button', name='Dark theme').bounding_box()
                    self.assertAlmostEqual(point[0] * width, box['x'] + box['width'] / 2, delta=.1)
                    self.assertAlmostEqual(point[1] * 600, box['y'] + box['height'] / 2, delta=.1)

    def test_unknown_points_stop_before_browser_launch(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d); self.project(folder, 'http://localhost:9000')
            raw = json.loads((folder / 'project.json').read_text())
            raw['chapters'][0]['steps'][1]['cursor'] = 'capture:before:missing'
            write_json(folder / 'project.json', raw)
            with patch('product_video.capture.web_session', side_effect=AssertionError('No browser expected')):
                with self.assertRaisesRegex(VideoError, '不存在的操作坐标'):
                    capture_project(folder / 'project.json')

    def test_mixed_existing_and_captured_images_validate_real_geometry(self):
        with tempfile.TemporaryDirectory() as d, serving(ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)) as server:
            folder = Path(d); self.project(folder, f'http://127.0.0.1:{server.server_port}')
            Image.new('RGB', (960, 600), 'blue').save(folder / 'existing.png')
            raw = json.loads((folder / 'project.json').read_text())
            raw['chapters'][0]['steps'][1].update(images=['existing.png'], cursor=[.2, .3], click=True)
            write_json(folder / 'project.json', raw)
            compiled = capture_project(folder / 'project.json')
            self.assertTrue(compiled.is_file())
            Image.new('RGB', (400, 800), 'blue').save(folder / 'existing.png')
            with self.assertRaisesRegex(VideoError, '比例不同'):
                capture_project(folder / 'project.json')

    def test_hidden_or_masked_point_is_not_published(self):
        with tempfile.TemporaryDirectory() as d, serving(ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)) as server:
            target = {'url': f'http://127.0.0.1:{server.server_port}', 'viewport': {'width': 960, 'height': 600}}
            with web_session(target) as page:
                for hidden in (False, True):
                    spec = {'css': '.secret'}
                    shot = {'id': 'masked', 'actions': [], 'mask': [spec] if not hidden else [],
                            'ready': {'role': 'heading', 'name': 'Capture Fixture'}, 'points': {'private': spec}}
                    if hidden:
                        page.locator('.secret').evaluate("element => element.style.top = '1000px'")
                    with self.assertRaisesRegex(VideoError, '遮盖|视口'):
                        capture_web(page, target, shot, Path(d) / 'private.png')
                    self.assertFalse((Path(d) / 'private.png').exists())

    def test_scroll_offset_avoids_fixed_header_and_restores_style(self):
        with tempfile.TemporaryDirectory() as d, serving(ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)) as server:
            target = {'url': f'http://127.0.0.1:{server.server_port}/scroll', 'viewport': {'width': 960, 'height': 600}}
            with web_session(target) as page:
                page.locator('body').evaluate("""body => {
                    const bar = document.createElement('aside');
                    bar.style.cssText = 'position:fixed;top:0;left:0;right:0;height:48px;background:red;z-index:9';
                    bar.textContent = 'Navigation'; body.appendChild(bar);
                }""")
                loc = page.get_by_role('heading', name='Install')
                loc.evaluate("element => element.style.setProperty('scroll-margin-top', '7px', 'important')")
                locator = {'role': 'heading', 'name': 'Install'}
                shot = {'id': 'install', 'actions': [{'action': 'scroll', 'target': locator, 'offset': 64}],
                        'ready': locator, 'mask': []}
                capture_web(page, target, shot, Path(d) / 'offset.png')
                self.assertAlmostEqual(loc.bounding_box()['y'], 64, delta=1)
                self.assertTrue(loc.evaluate("element => {const r=element.getBoundingClientRect(); return element.contains(document.elementFromPoint(r.x+10,r.y+r.height/2));}"))
                self.assertEqual(loc.evaluate("element => [element.style.getPropertyValue('scroll-margin-top'), element.style.getPropertyPriority('scroll-margin-top')]"), ['7px', 'important'])

    def test_scroll_offset_validation(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            base = self.project(folder, 'http://localhost:9000')
            for value in (-1, 600, True, '64'):
                plan = copy.deepcopy(base)
                plan['shots'][0]['actions'] = [{'action': 'scroll', 'target': {'text': 'Fixture'}, 'offset': value}]
                write_json(folder / 'capture.json', plan)
                with self.assertRaises(VideoError):
                    read_plan(folder / 'capture.json')

    def test_capture_under_strict_csp_without_disabling_policy(self):
        with tempfile.TemporaryDirectory() as d, serving(ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)) as server:
            target = {'url': f'http://127.0.0.1:{server.server_port}/csp', 'viewport': {'width': 960, 'height': 600}}
            with web_session(target) as page:
                # Deferred page code is subject to CSP, unlike the initial DevTools evaluation.
                policy = page.evaluate("""() => new Promise(resolve => setTimeout(() => {
                    try { eval('1'); resolve('allowed'); } catch (error) { resolve(error.name); }
                }, 0))""")
                self.assertEqual(policy, 'EvalError')
                destination = Path(d) / 'csp.png'
                capture_web(page, target, {'id': 'csp', 'actions': [], 'mask': [],
                                          'ready': {'role': 'heading', 'name': 'Capture Fixture'}}, destination)
                with Image.open(destination) as image:
                    self.assertEqual(image.size, (1920, 1200))

    def test_scroll_re_resolves_detached_node_with_finite_retry(self):
        from playwright.sync_api import Locator
        original_evaluate = Locator.evaluate
        with tempfile.TemporaryDirectory() as d, serving(ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)) as server:
            target = {'url': f'http://127.0.0.1:{server.server_port}/scroll', 'viewport': {'width': 960, 'height': 600}}
            with web_session(target) as page:
                locator = {'role': 'heading', 'name': 'Install'}
                shot = {'id': 'install', 'actions': [{'action': 'scroll', 'target': locator}], 'ready': locator, 'mask': []}
                for persistent in (False, True):
                    calls = []
                    def replace_node(loc, expression, *args, **kwargs):
                        if 'element.scrollIntoView' in expression:
                            calls.append(1)
                            if persistent or len(calls) == 1:
                                expression = expression.replace('if (!element.isConnected)',
                                    'element.replaceWith(element.cloneNode(true)); if (!element.isConnected)')
                        return original_evaluate(loc, expression, *args, **kwargs)
                    destination = Path(d) / f'replaced-{persistent}.png'
                    with patch.object(Locator, 'evaluate', replace_node):
                        if persistent:
                            with self.assertRaisesRegex(VideoError, '持续被页面替换'):
                                capture_web(page, target, shot, destination)
                            self.assertEqual(len(calls), 3)
                            self.assertFalse(destination.exists())
                        else:
                            capture_web(page, target, shot, destination)
                            self.assertEqual(len(calls), 2)
                            self.assertAlmostEqual(page.get_by_role('heading', name='Install').bounding_box()['y'], 0, delta=1)

    def test_capture_errors_identify_stage_without_echoing_page_data(self):
        from playwright.sync_api import Error, TimeoutError
        for error, expected in ((TimeoutError('synthetic-private'), '等待超时'),
                                (Error('strict mode violation synthetic-private'), '多个控件'),
                                (Error('net::ERR_CONNECTION_RESET https://private/?key=synthetic-private'), 'ERR_CONNECTION_RESET'),
                                (Error("Executable doesn't exist synthetic-private"), 'scripts/setup.sh'),
                                (Error('synthetic-private'), '浏览器操作失败')):
            result = str(web_error(error, '等待 ready 控件'))
            self.assertIn(expected, result)
            self.assertIn('等待 ready 控件', result)
            self.assertNotIn('synthetic-private', result)
            self.assertNotIn('https://private', result)

        with tempfile.TemporaryDirectory() as d, serving(ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)) as server:
            target = {'url': f'http://127.0.0.1:{server.server_port}', 'viewport': {'width': 960, 'height': 600}}
            with web_session(target) as page:
                page.set_default_timeout(200)
                shot = {'id': 'missing', 'actions': [], 'mask': [], 'ready': {'text': 'synthetic-private'}}
                with self.assertRaisesRegex(VideoError, '截图 missing / 等待 ready 控件') as error:
                    capture_web(page, target, shot, Path(d) / 'missing.png')
                self.assertNotIn('synthetic-private', str(error.exception))
                page.set_content('<h1>Ready</h1><img width="100" height="100" src="/invalid-image">')
                shot['ready'] = {'role': 'heading', 'name': 'Ready'}
                with self.assertRaisesRegex(VideoError, '可见图片或字体加载失败'):
                    capture_web(page, target, shot, Path(d) / 'broken.png')

    def test_scroll_aligns_visible_sections_at_narrow_and_wide_sizes(self):
        with tempfile.TemporaryDirectory() as d, serving(ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)) as server:
            for width in (390, 1440):
                target = {'provider': 'web', 'url': f'http://127.0.0.1:{server.server_port}/scroll',
                          'viewport': {'width': width, 'height': 600}}
                with web_session(target) as page:
                    files = []
                    for name in ('Features', 'Install'):
                        locator = {'role': 'heading', 'name': name}
                        shot = {'id': name.lower(), 'actions': [{'action': 'scroll', 'target': locator}],
                                'ready': locator, 'mask': []}
                        destination = Path(d) / f'{width}-{name}.png'
                        capture_web(page, target, shot, destination)
                        self.assertAlmostEqual(page.get_by_role('heading', name=name).bounding_box()['y'], 0, delta=1)
                        files.append(destination)
                    self.assertNotEqual(file_hash(files[0]), file_hash(files[1]))

    def project(self, folder, url):
        plan={'schema_version':1,'target':{'provider':'web','url':url,'viewport':{'width':960,'height':600}},'shots':[
            {'id':'before','ready':{'role':'heading','name':'Capture Fixture'},'mask':[{'css':'.secret'}]},
            {'id':'after','actions':[{'action':'click','target':{'role':'button','name':'Dark theme'}}],
             'ready':{'role':'heading','name':'Dark Ready'},'mask':[{'css':'.secret'}]}]}
        write_json(folder/'capture.json',plan)
        project={'schema_version':1,'product':{'name':'Capture Fixture'},'capture':'capture.json','output':'output',
                 'video':{'width':1280,'height':720},'chapters':[{'id':'intro','title':'Capture Fixture','narration':'测试截图。',
                 'steps':[{'at':0,'images':['capture:before']},{'at':.5,'images':['capture:after']}]}]}
        write_json(folder/'project.json',project)
        return plan

    def test_real_browser_click_screenshot_mask_and_project(self):
        with tempfile.TemporaryDirectory() as d, serving(ThreadingHTTPServer(('127.0.0.1',0),FixtureHandler)) as server:
            folder=Path(d);self.project(folder,f'http://127.0.0.1:{server.server_port}')
            compiled=capture_project(folder/'project.json')
            data=json.loads(compiled.read_text());self.assertNotIn('capture',data)
            self.assertEqual(data['output'],str((folder/'output').resolve()))
            files=[Path(s['images'][0]) for s in data['chapters'][0]['steps']]
            self.assertNotEqual(file_hash(files[0]),file_hash(files[1]))
            with Image.open(files[0]) as im:
                self.assertEqual(im.size,(1920,1200));self.assertEqual(im.convert('RGB').getpixel((250,450)),(255,0,255))
            with Image.open(files[1]) as im: self.assertEqual(im.convert('RGB').getpixel((1800,1100)),(23,44,67))
            report=json.loads((compiled.parent/'manifest.json').read_text());self.assertEqual(len(report['shots']),2)
            self.assertEqual(report['shots'][0]['sha256'],file_hash(files[0]))
            self.assertIn('capture:', (folder/'project.json').read_text())

    def test_preflight_rejects_unknown_refs_without_browser(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d);self.project(folder,'http://localhost:9000')
            p=json.loads((folder/'project.json').read_text());p['chapters'][0]['steps'][0]['images']=['capture:absent'];write_json(folder/'project.json',p)
            with patch('product_video.capture.web_session') as browser, self.assertRaises(VideoError): capture_project(folder/'project.json')
            browser.assert_not_called()

    def test_invalid_plan_and_cross_origin(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);base=self.project(p,'http://localhost:9000')
            for change in ('origin','id','ready','script'):
                plan=copy.deepcopy(base)
                if change=='origin': plan['shots'][0]['actions']=[{'action':'goto','url':'https://other.example'}]
                if change=='id': plan['shots'][0]['id']='../escape'
                if change=='ready': plan['shots'][0].pop('ready')
                if change=='script': plan['shots'][0]['actions']=[{'action':'eval','value':'process.exit()'}]
                write_json(p/'capture.json',plan)
                with self.assertRaises(VideoError): read_plan(p/'capture.json')

    def test_partial_capture_never_publishes_and_preserves_latest(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);self.project(p,'http://localhost:9000')
            root=p/'.captures';write_json(root/'latest.json',{'project':'previous'})
            @contextlib.contextmanager
            def browser(_): yield object()
            count=0
            def shot(page,target,shot,destination):
                nonlocal count
                count+=1
                if count==2: raise VideoError('failure fixture')
                Image.new('RGB',(120,120)).save(destination)
            with patch('product_video.capture.web_session',browser), patch('product_video.capture.capture_web',shot), self.assertRaises(VideoError): capture_project(p/'project.json')
            self.assertEqual(json.loads((root/'latest.json').read_text()),{'project':'previous'})
            self.assertEqual(list((root/'runs').iterdir()),[])

    def test_native_screenshot_uses_window_id_never_desktop(self):
        from product_video.native_capture import NativeCapture
        native=object.__new__(NativeCapture)
        calls=[]
        native.call=lambda command,locator=None: calls.append(command) or {'id':12345}
        with patch('product_video.native_capture.native_run') as run:
            native.capture({'actions':[],'ready':{'role':'AXButton','name':'Ready'}},Path('/tmp/fixture.png'))
            self.assertEqual(run.call_args.args[0],['/usr/sbin/screencapture','-x','-o','-l','12345',Path('/tmp/fixture.png')])
        self.assertEqual(calls,['wait','window'])

    def test_web_login_closes_visible_preparation_then_captures_headless(self):
        from unittest.mock import MagicMock
        from product_video.capture import web_session
        pw=MagicMock();login=MagicMock();background=MagicMock()
        pw.chromium.launch.side_effect=[login,background]
        login.new_context.return_value.new_page.return_value.url='https://example.com'
        login.new_context.return_value.storage_state.return_value={'cookies':[], 'origins':[]}
        with patch('playwright.sync_api.sync_playwright') as factory:
            factory.return_value.__enter__.return_value=pw
            with web_session({'url':'https://example.com','viewport':{'width':960,'height':600},
                              'login':{'ready':{'role':'button','name':'Ready'}}}) as page:
                login.close.assert_called_once()
                self.assertIs(page,background.new_context.return_value.new_page.return_value)
            self.assertEqual([c.kwargs['headless'] for c in pw.chromium.launch.call_args_list],[False,True])
            self.assertEqual(background.new_context.call_args.kwargs['storage_state'],{'cookies':[], 'origins':[]})
            background.close.assert_called_once()

    def test_native_background_launch_and_permission_stop(self):
        from product_video.native_capture import NativeCapture
        with tempfile.TemporaryDirectory() as d, patch('product_video.native_capture.platform.system',return_value='Darwin'), patch('product_video.native_capture.shutil.which',return_value='/usr/bin/swiftc'), patch('product_video.native_capture.file_hash',return_value='fixture'), patch('product_video.native_capture.native_run') as run:
            helper=Path(d)/'helpers/fixture/capture-macos';helper.parent.mkdir(parents=True);helper.touch()
            run.side_effect=[b'{"accessibility":true,"screen_recording":true}',b'',b'{"ready":true}']
            NativeCapture({'bundle_id':'com.example.Fixture'},Path(d))
            self.assertEqual(run.call_args_list[1].args[0],['/usr/bin/open','-g','-b','com.example.Fixture'])
            run.reset_mock();run.side_effect=[b'{"accessibility":false,"screen_recording":false}']
            with self.assertRaisesRegex(VideoError,'辅助功能'): NativeCapture({'bundle_id':'com.example.Fixture'},Path(d))
            self.assertEqual(run.call_count,1)


if __name__ == '__main__': unittest.main()
