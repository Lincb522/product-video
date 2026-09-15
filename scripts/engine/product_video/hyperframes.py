"""Render authored HTML shots on Product Video's narration-derived frame clock."""
import html
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
from urllib.parse import quote

from .common import VideoError, atomic_write, digest, file_hash, run, write_json

HEAD = '<!-- product-video:head -->'
TOKEN = re.compile(r'\{\{pv\.([a-zA-Z0-9_.-]+)\}\}')
TEXT_FILES = {'.html', '.css', '.js', '.mjs'}
SOURCE_FILES = TEXT_FILES | {'.png', '.jpg', '.jpeg', '.webp', '.svg', '.avif', '.mp4', '.mov',
    '.webm', '.woff', '.woff2', '.ttf', '.otf', '.ttc', '.json', '.gltf', '.glb', '.bin'}
MEDIA_FILES = SOURCE_FILES - TEXT_FILES - {'.json', '.bin'}


def runtime_root():
    return Path(__file__).resolve().parents[2] / 'hyperframes'


def runtime_files():
    root = runtime_root()
    return [root / name for name in ('package.json', 'package-lock.json', 'run.sh', 'browser.mjs')]


def source_files(spec):
    root = Path(spec['entry']).parent
    for file in sorted(root.rglob('*')):
        rel = file.relative_to(root)
        if any(p.startswith('.') or p in ('node_modules', 'output', 'renders', '_pv') for p in rel.parts):
            continue
        if file.suffix.lower() not in SOURCE_FILES or file.name.lower().startswith('credentials'):
            continue
        if file.is_symlink():
            raise VideoError(f'HTML 镜头目录不能包含符号链接：{rel}。请复制所需素材。')
        if file.is_file():
            yield file


def replace_tokens(source, context, *, javascript=False):
    def replace(match):
        value = context
        for key in match[1].split('.'):
            if not isinstance(value, dict) or key not in value:
                raise VideoError(f'未知 HTML 镜头变量：pv.{match[1]}。请检查镜头源码与配置。')
            value = value[key]
        if not isinstance(value, (str, int, float, bool)):
            raise VideoError(f'pv.{match[1]} 不是标量；请在脚本中读取 PRODUCT_VIDEO。')
        if javascript and isinstance(value, str):
            raise VideoError('JS 文件中的文本与路径请通过 PRODUCT_VIDEO 读取，不使用 HTML 占位符。')
        scalar = json.dumps(value) if isinstance(value, (int, float, bool)) else value
        return scalar if javascript else html.escape(scalar, quote=True)
    return TOKEN.sub(replace, source)


class Composition(HTMLParser):
    def __init__(self):
        super().__init__()
        self.roots = []
        self.templates = 0

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == 'template':
            self.templates += 1
        if 'data-composition-id' in data:
            self.roots.append((data, self.templates))

    def handle_endtag(self, tag):
        if tag == 'template':
            self.templates = max(0, self.templates - 1)


def validate_root(source, video, duration):
    parser = Composition()
    parser.feed(source)
    if not parser.roots or parser.roots[0][1]:
        raise VideoError('HTML 镜头需要直接位于 body 的 data-composition-id 根节点。')
    root = parser.roots[0][0]
    try:
        matches = (int(root['data-width']) == video['width'] and int(root['data-height']) == video['height']
                   and abs(float(root['data-duration']) - duration) < 1e-7)
    except (KeyError, ValueError, TypeError):
        matches = False
    if not matches:
        raise VideoError('HTML 根节点的宽高与时长必须使用 pv.width、pv.height、pv.duration，匹配当前镜头。')
    if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]*', root.get('data-composition-id', '')):
        raise VideoError('HTML data-composition-id 需要有效的唯一名称，并与 __timelines 的键相同。')
    return root['data-composition-id']


def context_for(spec, video, duration, chapter=None, start=0):
    cues = [] if chapter is None else [dict(text=c['text'], start=max(0, c['start'] - start),
        end=min(duration, c['end'] - start)) for c in chapter['cues']
        if c['end'] > start and c['start'] < start + duration]
    return {'width': video['width'], 'height': video['height'], 'fps': video['fps'],
        'duration': duration, 'reduced_motion': video['reduced_motion'],
        'font': '_pv/font' + Path(video['font']).suffix, 'gsap': '_pv/gsap.min.js',
        'media': {key: '_pv/media/' + key + Path(value).suffix.lower() for key, value in spec.get('media', {}).items()},
        'variables': spec.get('variables', {}), 'cues': cues,
        'voice_start': 0 if chapter is None else chapter['start'] + chapter['lead'] - start,
        'chapter': {} if chapter is None else {'id': chapter['id'], 'title': chapter['title'],
            'narration': chapter['narration'], 'audio_duration': chapter['audio_duration']}}


def validate_scene(spec, base, video):
    from .config import known, text
    known(spec, ('entry', 'media', 'variables'), 'hyperframes')
    text(spec.get('entry'), 'hyperframes.entry', 4096)
    entry = (base / Path(spec['entry']).expanduser()).resolve()
    if not entry.is_file() or entry.suffix.lower() != '.html':
        raise VideoError('hyperframes.entry 需要存在的 HTML 文件。')
    if entry.parent == base.resolve():
        raise VideoError('请将 HTML 镜头放入独立素材目录（例如 scenes/intro/index.html），避免把项目输出一起复制。')
    spec['entry'] = str(entry)
    for field in ('media', 'variables'):
        known_values = spec.get(field, {})
        if not isinstance(known_values, dict):
            raise VideoError(f'hyperframes.{field} 必须为名称与值组成的对象。')
        for key, value in known_values.items():
            if not isinstance(key, str) or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,63}', key):
                raise VideoError(f'hyperframes.{field} 名称需为字母开头的字母、数字、下划线或连字符。')
            if field == 'media':
                text(value, 'HTML 镜头素材', 4096)
                file = (base / Path(value).expanduser()).resolve()
                if not file.is_file() or file.suffix.lower() not in MEDIA_FILES:
                    raise VideoError(f'HTML 镜头素材不存在或格式不支持：{file.name}。')
                known_values[key] = str(file)
            elif type(value) not in (str, bool, int, float) or (isinstance(value, float) and not math.isfinite(value)):
                raise VideoError('hyperframes.variables 仅接受文本、有限数值和布尔值。')
    source = entry.read_text()
    if source.count(HEAD) != 1:
        raise VideoError(f'HTML 镜头 head 内需要且只能有一个 {HEAD}。')
    context = context_for(spec, video, 1.25)
    validate_root(replace_tokens(source, context), video, 1.25)
    for file in source_files(spec):
        if file.suffix.lower() in TEXT_FILES:
            replace_tokens(file.read_text(), context, javascript=file.suffix.lower() in ('.js', '.mjs'))


def invoke(action, directory, arguments=(), *, timeout=7200):
    root = runtime_root()
    cli = root / 'node_modules/hyperframes/bin/hyperframes.mjs'
    if not cli.is_file() or not shutil.which('node'):
        raise VideoError('Hyperframes 环境未就绪，请运行 Skill 的 scripts/setup-hyperframes.sh。')
    log = directory.parent / f'hyperframes-{action}.log'
    print(f'Hyperframes {action}：{directory}；日志：{log}', flush=True)
    browser = run(['node', root / 'browser.mjs']).decode().strip()
    env = os.environ | {'HYPERFRAMES_NO_TELEMETRY': '1', 'HYPERFRAMES_BROWSER_PATH': browser}
    with log.open('w') as output:
        process = subprocess.Popen(['node', str(cli), action, str(directory), *map(str, arguments)],
            cwd=directory, env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise VideoError(f'Hyperframes {action} 已停止；已生成文件保留。查看日志：{log}') from None
    if code:
        raise VideoError(f'Hyperframes {action} 失败（退出码 {code}）。查看日志：{log}')
    return log


def check_report(log):
    # A CLI exit alone is not proof that browser audits actually completed.
    source = Path(log).read_text()
    for match in re.finditer(r'^\{', source, re.MULTILINE):
        try:
            report, _ = json.JSONDecoder().raw_decode(source[match.start():])
        except ValueError:
            continue
        if all(key in report for key in ('lint', 'runtime', 'layout', 'contrast')):
            if (report.get('ok') is True and report['runtime'].get('ok') is True
                    and report['layout'].get('samples')):
                return report
            break
    raise VideoError(f'Hyperframes 没有完成有效的浏览器检查，请查看日志后重试：{log}')


def compile_scene(spec, video, chapter, start, end, destination):
    """Freeze local inputs; scene timing uses the same rounded boundaries as Remotion."""
    duration = (end - start) / video['fps']
    context = context_for(spec, video, duration, chapter, start / video['fps'])
    entry = Path(spec['entry'])
    source = replace_tokens(entry.read_text(), context)
    composition_id = validate_root(source, video, duration)
    support = destination / '_pv'
    support.mkdir(parents=True, exist_ok=True)
    script = 'window.PRODUCT_VIDEO = ' + json.dumps(context, ensure_ascii=False).replace('<', '\\u003c') + ';\n'
    atomic_write(support / 'timing.js', script.encode())
    shutil.copyfile(runtime_root() / 'node_modules/gsap/dist/gsap.min.js', destination / context['gsap'])
    shutil.copyfile(video['font'], destination / context['font'])
    for key, source_file in spec.get('media', {}).items():
        target = destination / context['media'][key]
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(source_file, target)
    inject = ('<script src="_pv/timing.js"></script>\n'
              '<script src="_pv/gsap.min.js"></script>\n'
              '<style>@font-face{font-family:ProductVideoFont;src:url("' + quote(context['font']) + '");}</style>')
    for file in source_files(spec):
        target = destination / file.relative_to(entry.parent)
        target.parent.mkdir(parents=True, exist_ok=True)
        if file.suffix.lower() in TEXT_FILES:
            rendered = replace_tokens(file.read_text(), context, javascript=file.suffix.lower() in ('.js', '.mjs'))
            if file == entry:
                rendered = rendered.replace(HEAD, inject)
            atomic_write(target, rendered.encode())
        else:
            shutil.copyfile(file, target)
    if entry.name != 'index.html':
        # Preserve relative imports while exposing Hyperframes' canonical entrypoint.
        (destination / entry.name).replace(destination / 'index.html')
    write_json(destination / '_pv/timing.json', context)
    return context, composition_id


def render_scene(spec, config, chapter, start, end, folder):
    from .pipeline import verify
    video = config['video']
    inputs = set(source_files(spec)) | {Path(p) for p in spec.get('media', {}).values()} | {Path(video['font'])}
    hashes = {str(p): file_hash(p) for p in sorted(inputs)}
    signature = digest({'inputs': hashes, 'spec': spec, 'video': video,
        'timing': context_for(spec, video, (end-start)/video['fps'], chapter, start/video['fps']),
        'adapter': file_hash(Path(__file__)), 'runtime': {p.name: file_hash(p) for p in runtime_files()}})[:20]
    shot = folder / signature
    shot.mkdir(parents=True, exist_ok=True)
    movie, report_file = shot / 'shot.mp4', shot / 'verification.json'
    if movie.exists() and report_file.exists():
        report = json.loads(report_file.read_text())
        if report.get('sha256') == file_hash(movie):
            return movie
        raise VideoError(f'HTML 镜头缓存校验失败：{shot}。请检查文件后移走该缓存再渲染。')
    project = shot / 'project'
    context, composition_id = compile_scene(spec, video, chapter, start, end, project)
    checks = check_report(invoke('check', project, ('--json',), timeout=600))
    write_json(shot / 'check.json', checks)
    silent_video, pending = shot / 'picture.mp4', shot / 'shot.pending.mp4'
    try:
        invoke('render', project, ('--output', silent_video, '--fps', video['fps'], '--quality', 'delivery',
            '--workers', '1', '--strict', '--no-best-effort'))
        # Narration, SFX and BGM belong to the shared project timeline, never a shot.
        run(['ffmpeg', '-v', 'error', '-y', '-i', silent_video, '-f', 'lavfi', '-i',
            'anullsrc=r=48000:cl=stereo', '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy',
            '-c:a', 'aac', '-t', str(context['duration']), '-movflags', '+faststart', pending], timeout=600)
        report = verify(pending, config, context['duration'])
        pending.replace(movie)
    finally:
        pending.unlink(missing_ok=True)
        silent_video.unlink(missing_ok=True)
    report.update(sha256=file_hash(movie), renderer='Hyperframes', version='0.8.40',
        composition=composition_id, entry=str(project / 'index.html'), inputs=hashes,
        visual_review='unverified', listening_review='not applicable: silent shot')
    write_json(report_file, report)
    return movie
