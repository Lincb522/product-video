"""Capture a bounded, observed UI plan and publish verified project assets."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit
import uuid

from PIL import Image

from .common import VideoError, file_hash, write_json
from .config import known, load, number, text
from .pipeline import project_lock


def origin(value):
    text(value, '页面 URL', 4096)
    u = urlsplit(value)
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password:
        raise VideoError('截图 URL 必须为不含账号密码的 HTTP(S) 地址。')
    try:
        port = u.port
    except ValueError:
        raise VideoError('截图 URL 端口不正确。') from None
    return f'{u.scheme}://{u.hostname}' + (f':{port}' if port and port != (443 if u.scheme == 'https' else 80) else '')


def locator_spec(value):
    known(value, ('role', 'name', 'css', 'text'), '界面定位')
    if 'role' in value:
        text(value['role'], 'role', 60)
        text(value.get('name'), '控件名称', 300)
        if set(value) != {'role', 'name'}:
            raise VideoError('role 定位必须只包含 role 和 name。')
    elif set(value) in ({'css'}, {'text'}):
        text(next(iter(value.values())), '界面定位', 500)
    else:
        raise VideoError('界面定位使用 role/name、css 或 text 其中一种。')


def read_plan(path):
    try:
        plan = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        raise VideoError('截图计划不可读或不是有效 JSON。') from None
    known(plan, ('schema_version', 'target', 'shots'), '截图计划')
    if plan.get('schema_version') != 1:
        raise VideoError('截图计划 schema_version 必须为 1。')
    target = plan.get('target')
    known(target, ('provider', 'url', 'viewport', 'color_scheme', 'channel', 'headless', 'login',
                   'bundle_id', 'window_title'), '截图目标')
    provider = target.get('provider')
    if provider == 'web':
        origin(target.get('url'))
        if any(k in target for k in ('bundle_id', 'window_title')):
            raise VideoError('网页目标不能包含原生应用字段。')
        viewport = target.setdefault('viewport', {'width': 1440, 'height': 900})
        known(viewport, ('width', 'height'), 'viewport')
        for key in ('width', 'height'):
            number(viewport.get(key), 320, 3840, key)
            if not isinstance(viewport[key], int):
                raise VideoError('viewport 宽高必须为整数。')
        if target.get('color_scheme', 'light') not in ('light', 'dark') or target.get('channel', 'chromium') not in ('chromium', 'chrome', 'msedge'):
            raise VideoError('网页主题或浏览器不受支持。')
        if target.get('headless', True) is not True:
            raise VideoError('截图阶段只支持后台无头模式；需要登录时设置 login，登录完成会关闭前台窗口再采集。')
        if 'login' in target:
            known(target['login'], ('ready', 'timeout'), '登录等待')
            locator_spec(target['login'].get('ready'))
            number(target['login'].get('timeout', 300), 1, 900, '登录等待秒数')
    elif provider == 'macos':
        if any(k in target for k in ('url', 'viewport', 'color_scheme', 'channel', 'headless', 'login')):
            raise VideoError('macOS 目标不能包含网页字段。')
        if not isinstance(target.get('bundle_id'), str) or not re.fullmatch(r'[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+', target['bundle_id']):
            raise VideoError('请指定应用真实的 bundle_id。')
        if 'window_title' in target:
            text(target['window_title'], '窗口标题', 500)
    else:
        raise VideoError('自动截图目前支持 web 和 macos。')
    shots = plan.get('shots')
    if not isinstance(shots, list) or not 1 <= len(shots) <= 60:
        raise VideoError('截图计划需包含 1–60 个画面。')
    seen = set()
    for shot in shots:
        known(shot, ('id', 'actions', 'ready', 'mask', 'points'), '截图画面')
        sid = shot.get('id')
        if not isinstance(sid, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', sid) or sid in seen:
            raise VideoError('截图 id 必须唯一，只用小写字母、数字、连字符和下划线。')
        seen.add(sid)
        if 'ready' not in shot:
            raise VideoError('每张截图必须指定 ready 控件，不能仅凭固定等待时间判断页面已加载。')
        validate_locator(shot['ready'], provider)
        actions = shot.setdefault('actions', [])
        if not isinstance(actions, list) or len(actions) > 30:
            raise VideoError('每张截图最多 30 个操作。')
        for action in actions:
            known(action, ('action', 'target', 'value', 'url', 'offset'), '截图操作')
            kind = action.get('action')
            allowed = ('goto', 'click', 'fill', 'press', 'scroll', 'wait') if provider == 'web' else ('press', 'wait')
            if kind not in allowed:
                raise VideoError('截图操作不受此目标支持。')
            expected = {'action', 'url'} if kind == 'goto' else {'action', 'target', 'value'} if kind in ('fill',) or (kind == 'press' and provider == 'web') else {'action', 'target'}
            if kind == 'scroll' and 'offset' in action:
                expected.add('offset')
                number(action['offset'], 0, target['viewport']['height'] - 1, '滚动顶部留白')
            if set(action) != expected:
                raise VideoError('截图操作字段不匹配，请对照截图计划说明。')
            if kind == 'goto':
                if origin(action['url']) != origin(target['url']):
                    raise VideoError('自动导航只能前往目标网站的同源页面；其他网站需另建明确目标。')
            else:
                validate_locator(action['target'], provider)
            if 'value' in action:
                text(action['value'], '操作内容', 1000)
        masks = shot.setdefault('mask', [])
        if not isinstance(masks, list) or len(masks) > 30 or (masks and provider == 'macos'):
            raise VideoError('mask 仅支持网页控件列表；原生应用应先隐藏私人内容再截图。')
        for m in masks:
            locator_spec(m)
        points = shot.get('points', {})
        if not isinstance(points, dict) or len(points) > 30 or (points and provider != 'web'):
            raise VideoError('points 仅支持网页上的最多 30 个命名控件。')
        for name, locator in points.items():
            if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', name):
                raise VideoError('points 名称只用小写字母、数字、连字符和下划线。')
            locator_spec(locator)
    return plan


def validate_locator(value, provider):
    if provider == 'web':
        locator_spec(value)
    else:
        known(value, ('role', 'name'), '原生控件定位')
        text(value.get('role'), 'AX role', 100)
        text(value.get('name'), '控件名称', 300)


def web_locator(page, spec):
    if 'role' in spec:
        return page.get_by_role(spec['role'], name=spec['name'], exact=True)
    if 'text' in spec:
        return page.get_by_text(spec['text'], exact=True)
    return page.locator(spec['css'])


def web_error(error, stage):
    from playwright.sync_api import TimeoutError

    # Playwright messages can contain URLs, field values and DOM text. Export only known categories.
    message = str(error)
    if isinstance(error, TimeoutError):
        reason = '等待超时；请检查此步骤的定位器、登录状态和内容加载条件。'
    elif 'strict mode violation' in message:
        reason = '定位器匹配了多个控件；请使用唯一定位器。'
    elif code := re.search(r'\bnet::(ERR_[A-Z_]+)\b', message):
        reason = f'网络请求失败（{code.group(1)}）；请检查网络后重试。'
    elif "Executable doesn't exist" in message:
        reason = '未找到采集浏览器；请重新运行 Skill 的 scripts/setup.sh。'
    elif 'Element is not visible' in message:
        reason = '目标控件尚不可见；请先等待实际内容出现。'
    else:
        reason = '浏览器操作失败；请检查页面状态和截图计划后重试。'
    return VideoError(f'网页采集失败（{stage}）：{reason}')


@contextmanager
def web_session(target, record_dir=None):
    try:
        from playwright.sync_api import sync_playwright, Error
    except ImportError:
        raise VideoError('缺少网页采集环境，请执行 Skill 的 scripts/setup.sh。') from None
    stage = '启动浏览器'
    try:
        with sync_playwright() as pw:
            channel = target.get('channel', 'chromium')
            options = {'channel': channel} if channel != 'chromium' else {}
            state = None
            if 'login' in target:
                print('需先登录：请在临时浏览器完成登录；检测成功后关闭该窗口，再在后台静默截图。', flush=True)
                stage = '启动登录浏览器'
                login_browser = pw.chromium.launch(headless=False, **options)
                try:
                    login_context = login_browser.new_context(viewport=target['viewport'], accept_downloads=False)
                    login_page = login_context.new_page()
                    stage = '打开登录页面'
                    login_page.goto(target['url'], wait_until='domcontentloaded', timeout=30000)
                    stage = '等待登录完成'
                    web_locator(login_page, target['login']['ready']).wait_for(state='visible', timeout=target['login'].get('timeout', 300) * 1000)
                    if origin(login_page.url) != origin(target['url']):
                        raise VideoError('登录没有返回目标网站，已停止采集。')
                    # Task-owned session handoff stays in memory, never a cookie file or log.
                    state = login_context.storage_state()
                finally:
                    login_browser.close()
                print('登录已完成，前台准备窗口已关闭，开始后台截图。', flush=True)
            stage = '启动后台浏览器'
            browser = pw.chromium.launch(headless=True, **options)
            try:
                context = browser.new_context(viewport=target['viewport'], device_scale_factor=2,
                                              color_scheme=target.get('color_scheme', 'light'), accept_downloads=False,
                                              storage_state=state,
                                              **({'record_video_dir': str(record_dir), 'record_video_size': target['viewport']}
                                                 if record_dir else {}))
                state = None
                page = context.new_page()
                page.set_default_timeout(15000)
                page.set_default_navigation_timeout(30000)
                page.on('dialog', lambda dialog: dialog.dismiss())
                stage = '打开目标页面'
                page.goto(target['url'], wait_until='domcontentloaded')
                yield page
                context.close()
            finally:
                browser.close()
    except Error as error:
        raise web_error(error, stage) from None


def capture_web(page, target, shot, destination, recording=False):
    from playwright.sync_api import Error

    try:
        def same_origin():
            if origin(page.url) != origin(target['url']):
                raise VideoError('页面已离开指定网站，已停止截图；请确认目标地址或完成登录。')
        stage = '检查页面来源'
        same_origin()
        for index, action in enumerate(shot['actions'], 1):
            stage = f"操作 {index}/{len(shot['actions'])} {action['action']}"
            print(f"  操作 {index}/{len(shot['actions'])}：{action['action']}", flush=True)
            if action['action'] == 'goto':
                page.goto(action['url'], wait_until='domcontentloaded')
            else:
                loc = web_locator(page, action['target'])
                kind = action['action']
                if kind == 'fill':
                    if loc.get_attribute('type') == 'password' or loc.get_attribute('autocomplete') in ('current-password', 'new-password', 'one-time-code'):
                        raise VideoError('不能从截图计划填写密码或验证码，请使用手动登录等待。')
                    if recording:
                        loc.fill('')
                        loc.press_sequentially(action['value'], delay=65)
                    else:
                        loc.fill(action['value'])
                elif kind == 'click':
                    loc.click()
                elif kind == 'press':
                    if loc.get_attribute('type') == 'password':
                        raise VideoError('截图计划不能操作密码输入框。')
                    loc.press(action['value'])
                elif kind == 'scroll':
                    # A hydrated page can replace the node after locator resolution. Re-resolve
                    # only this idempotent operation, never retry clicks or form submissions.
                    for attempt in range(3):
                        loc.wait_for(state='visible')
                        if loc.evaluate("""(element, options) => {
                            const offset = options.offset;
                            if (!element.isConnected) return false;
                            const margin = element.style.getPropertyValue('scroll-margin-top');
                            const priority = element.style.getPropertyPriority('scroll-margin-top');
                            try {
                                if (offset) element.style.setProperty('scroll-margin-top', `${offset}px`, 'important');
                                element.scrollIntoView({block: 'start', inline: 'nearest', behavior: options.smooth ? 'smooth' : 'instant'});
                            } finally {
                                if (offset) {
                                    if (margin) element.style.setProperty('scroll-margin-top', margin, priority);
                                    else element.style.removeProperty('scroll-margin-top');
                                }
                            }
                            return true;
                        }""", {'offset': action.get('offset', 0), 'smooth': recording}):
                            break
                    else:
                        raise VideoError(f"截图 {shot['id']} 的滚动目标持续被页面替换；请等待内容加载完成后重试。")
                else:
                    loc.wait_for(state='visible')
            same_origin()
            if recording:
                page.wait_for_timeout(450)
        stage = '等待 ready 控件'
        web_locator(page, shot['ready']).wait_for(state='visible')
        # Native load promises avoid wait_for_function's repeated string eval under strict CSP.
        stage = '等待可见图片和字体'
        assets = page.evaluate("""async () => {
            let timer;
            const images = [...document.images].filter(image => {
                const r = image.getBoundingClientRect();
                return r.width && r.height && r.bottom > 0 && r.top < innerHeight;
            });
            try {
                return await Promise.race([
                    Promise.all([document.fonts.ready, ...images.map(image => image.decode())])
                        .then(() => 'ready', () => 'failed'),
                    new Promise(resolve => { timer = setTimeout(() => resolve('timeout'), 15000); })
                ]);
            } finally { clearTimeout(timer); }
        }""")
        if assets != 'ready':
            reason = '等待超时' if assets == 'timeout' else '加载失败'
            raise VideoError(f"截图 {shot['id']} 的可见图片或字体{reason}；请检查页面资源后重试。")
        stage = '定位遮盖区域'
        masks = [page.locator('input[type=password],input[autocomplete=one-time-code]')]
        for spec in shot['mask']:
            loc = web_locator(page, spec)
            loc.wait_for(state='attached')
            masks.append(loc)
        stage = '记录操作坐标'
        points = {}
        for name, spec in shot.get('points', {}).items():
            loc = web_locator(page, spec)
            loc.wait_for(state='visible')
            # Read geometry only. The hit test rejects covered or offscreen controls
            # instead of recording a plausible but unusable pointer destination.
            geometry = loc.evaluate("""element => {
                const r = element.getBoundingClientRect();
                const x = r.x + r.width / 2, y = r.y + r.height / 2;
                return {x, y, width: innerWidth, height: innerHeight,
                    visible: r.width > 0 && r.height > 0 && x >= 0 && y >= 0 &&
                        x < innerWidth && y < innerHeight && element.contains(document.elementFromPoint(x, y))};
            }""")
            if not geometry['visible']:
                raise VideoError(f"截图 {shot['id']} 的 points.{name} 不在可点击视口内；请调整采集位置。")
            for mask in masks:
                for item in mask.all():
                    box = item.bounding_box()
                    if box and box['x'] <= geometry['x'] <= box['x'] + box['width'] and box['y'] <= geometry['y'] <= box['y'] + box['height']:
                        raise VideoError('操作坐标位于已遮盖的区域；请使用不含私人内容的演示控件。')
            points[name] = [geometry['x'] / geometry['width'], geometry['y'] / geometry['height']]
        stage = '保存截图'
        page.screenshot(path=str(destination), full_page=False, animations='allow' if recording else 'disabled', mask=masks)
        for name, spec in shot.get('points', {}).items():
            current = web_locator(page, spec).evaluate("""element => {
                const r = element.getBoundingClientRect();
                return [(r.x + r.width / 2) / innerWidth, (r.y + r.height / 2) / innerHeight];
            }""")
            if any(abs(a - b) > .001 for a, b in zip(current, points[name])):
                raise VideoError(f"截图 {shot['id']} 的 points.{name} 在采集时移动了；请等待布局稳定后重试。")
        same_origin()
        return points

    except Error as error:
        raise web_error(error, f"截图 {shot['id']} / {stage}") from None


def capture_project(project):
    project = Path(project).expanduser().resolve()
    raw = json.loads(project.read_text())
    if not isinstance(raw, dict) or not isinstance(raw.get('capture'), str):
        raise VideoError('项目需用 capture 字段指向截图计划 JSON。')
    plan_path = (project.parent / raw['capture']).resolve()
    plan = read_plan(plan_path)
    # Validate the whole video contract before interacting with a real application.
    from .config import load as load_project
    with tempfile.TemporaryDirectory(prefix='product-video-plan-') as tmp:
        dummy = Path(tmp)/'pending.png'; Image.new('RGB', (32, 32)).save(dummy)
        pending = json.loads(json.dumps(raw)); pending.pop('capture')
        resolve_images(pending, project.parent, {s['id']: str(dummy) for s in plan['shots']})
        resolve_points(pending, {f"capture:{s['id']}:{name}": [.5, .5]
                                for s in plan['shots'] for name in s.get('points', {})})
        pending_path = Path(tmp)/'project.json'; write_json(pending_path, pending)
        # Placeholder images have no capture geometry. Check actual ratios after capture,
        # including projects that mix existing screenshots and newly captured ones.
        load_project(pending_path, check_image_geometry=False)
    root = project.parent / '.captures'
    with project_lock(root):
        run = root / 'runs' / uuid.uuid4().hex[:16]
        run.mkdir(parents=True)
        records = []
        try:
            target = plan['target']
            if target['provider'] == 'web':
                with web_session(target) as page:
                    for shot in plan['shots']:
                        capture_one(shot, run, records, lambda s, d: capture_web(page, target, s, d))
            else:
                from .native_capture import NativeCapture
                native = NativeCapture(target, root)
                for shot in plan['shots']:
                    capture_one(shot, run, records, native.capture)
            resolved = json.loads(json.dumps(raw)); resolved.pop('capture')
            resolve_images(resolved, project.parent, {r['id']: str(run / r['file']) for r in records})
            resolve_points(resolved, {f"capture:{r['id']}:{name}": point
                                      for r in records for name, point in r.get('points', {}).items()})
            compiled = run / 'project.json'; write_json(compiled, resolved)
            load(compiled)
            source = origin(target['url']) if target['provider'] == 'web' else target['bundle_id']
            report = {'source': source, 'provider': target['provider'], 'plan_sha256': file_hash(plan_path),
                      'project_sha256': file_hash(project), 'shots': records, 'project': str(compiled)}
            write_json(run / 'manifest.json', report)
            write_json(root / 'latest.json', {'manifest': str(run / 'manifest.json'), 'project': str(compiled)})
        except BaseException:
            shutil.rmtree(run)
            raise
        print(f'真实界面采集完成：{len(records)} 张；项目：{compiled}', flush=True)
        return compiled


def capture_one(shot, run, records, action):
    print(f"截图 {len(records) + 1}：{shot['id']}", flush=True)
    dest = run / f"{shot['id']}.png"
    points = action(shot, dest)
    with Image.open(dest) as im:
        im.verify()
    with Image.open(dest) as im:
        if im.width < 100 or im.height < 100:
            raise VideoError('采集画面过小，请检查目标窗口是否可见。')
        size = [im.width, im.height]
    records.append({'id': shot['id'], 'file': dest.name, 'size': size, 'sha256': file_hash(dest),
                    'captured_at': datetime.now(timezone.utc).isoformat()})
    if shot.get('points'):
        records[-1]['points'] = points


def resolve_points(raw, points):
    for chapter in raw.get('chapters', []):
        for step in chapter.get('steps', []):
            fields = [(step, 'cursor')]
            if isinstance(step.get('interaction'), dict):
                fields += [(step['interaction'], key) for key in ('from', 'to')]
            for obj, key in fields:
                value = obj.get(key)
                if isinstance(value, str):
                    if value not in points:
                        raise VideoError('视频引用了不存在的操作坐标；使用 capture:截图id:point名称。')
                    obj[key] = points[value]


def resolve_images(raw, base, captured):
    for chapter in raw.get('chapters', []):
        for step in chapter.get('steps', []):
            images = []
            for value in step.get('images', []):
                if value.startswith('capture:'):
                    sid = value.removeprefix('capture:')
                    if sid not in captured:
                        raise VideoError('视频引用了不存在的截图 id。')
                    images.append(captured[sid])
                else:
                    images.append(str((base / Path(value).expanduser()).resolve()))
            step['images'] = images
            for key, value in step.get('shotcraft', {}).get('media', {}).items():
                if value.startswith('capture:'):
                    sid = value.removeprefix('capture:')
                    if sid not in captured:
                        raise VideoError('Shotcraft 镜头引用了不存在的截图 id。')
                    step['shotcraft']['media'][key] = captured[sid]
                else:
                    step['shotcraft']['media'][key] = str((base / Path(value).expanduser()).resolve())
            for item in step.get('editorial', {}).get('items', []):
                value = item.get('source', '')
                if value.startswith('capture:'):
                    sid = value.removeprefix('capture:')
                    if sid not in captured:
                        raise VideoError('内容镜头引用了不存在的截图 id。')
                    item['source'] = captured[sid]
                else:
                    item['source'] = str((base / Path(value).expanduser()).resolve())
            for device in step.get('scene3d', {}).get('devices', []):
                source = device.get('source', '')
                if source.startswith('capture:'):
                    sid = source.removeprefix('capture:')
                    if sid not in captured:
                        raise VideoError('三维屏幕引用了不存在的截图 id。')
                    device['source'] = captured[sid]
                else:
                    device['source'] = str((base / Path(source).expanduser()).resolve())
    if raw.get('product', {}).get('logo'):
        raw['product']['logo'] = str((base / raw['product']['logo']).resolve())
    if raw.get('video', {}).get('font'):
        raw['video']['font'] = str((base / raw['video']['font']).resolve())
    raw['output'] = str((base / raw.get('output', 'output')).resolve())
    for clips in raw.get('audio', {}).values():
        for clip in clips:
            if not clip['source'].startswith('shotcraft:'):
                clip['source'] = str((base / Path(clip['source']).expanduser()).resolve())
