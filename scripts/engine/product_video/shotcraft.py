"""Remotion composition driven by the existing narration and capture contracts."""
import copy
import json
import math
from pathlib import Path
import shutil
import subprocess

from PIL import Image, ImageOps

from .common import VideoError, atomic_write, digest, file_hash, probe, run, write_json


def runtime_root():
    root = Path(__file__).resolve().parents[3] / 'vendor' / 'video-shotcraft'
    if not (root / 'motion-catalog.json').is_file():
        raise VideoError('缺少镜头运行库，请使用完整的 Product Video Skill 安装包。')
    return root


def catalogue():
    return json.loads((runtime_root() / 'motion-catalog.json').read_text())


def motion_item(key):
    matches = [m for m in catalogue()['motions'] if key in (m['id'], m['style'], m['component'])]
    if len(matches) != 1:
        raise VideoError(f'镜头名称不明确或不存在：{key}。使用 motions 查看准确的样式名称。')
    return matches[0]


def validate_motion(spec, base):
    from .config import known, text
    known(spec, ('style', 'text', 'media', 'colors', 'font_family', 'timing'), 'shotcraft')
    text(spec.get('style'), 'shotcraft.style', 160)
    motion_item(spec['style'])
    if spec.get('timing', 'fit') not in ('fit', 'hold'):
        raise VideoError('shotcraft.timing 仅支持 fit（适配旁白）或 hold（原速播放后停留）。')
    for name in ('text', 'media', 'colors'):
        values = spec.get(name, {})
        if not isinstance(values, dict):
            raise VideoError(f'shotcraft.{name} 必须是原值与新值组成的对象。')
        for key, value in values.items():
            text(key, f'shotcraft.{name} 原值', 4096)
            if not isinstance(value, str) or len(value) > 4096:
                raise VideoError(f'shotcraft.{name} 新值必须为文本。')
            if name == 'media':
                file = (base / Path(value).expanduser()).resolve()
                if not file.is_file() or file.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp', '.svg', '.mp4', '.mov', '.webm'):
                    raise VideoError(f'镜头素材不存在或格式不支持：{file.name}。')
                values[key] = str(file)
    if 'font_family' in spec:
        text(spec['font_family'], 'shotcraft.font_family', 160)


def validate_audio(audio, base):
    from .config import known, number, text
    known(audio, ('bgm', 'sfx'), 'audio')
    for kind, clips in audio.items():
        if not isinstance(clips, list):
            raise VideoError(f'audio.{kind} 必须是音频片段数组。')
        for clip in clips:
            known(clip, ('source', 'start', 'duration', 'volume'), f'audio.{kind}')
            source = clip.get('source')
            text(source, '音频素材', 4096)
            if source.startswith('shotcraft:'):
                root = (runtime_root() / 'assets/audio').resolve()
                file = (root / source.removeprefix('shotcraft:')).resolve()
                if not file.is_relative_to(root):
                    raise VideoError('音效库路径超出 assets/audio。')
            else:
                file = (base / Path(source).expanduser()).resolve()
            if not file.is_file():
                raise VideoError(f'音频素材不存在：{file.name}。')
            streams = probe(file)['streams']
            if not any(s['codec_type'] == 'audio' for s in streams):
                raise VideoError(f'素材没有音轨：{file.name}。')
            clip['source'] = str(file)
            number(clip.get('start', 0), 0, 36000, '音频开始时间')
            number(clip.get('volume', .12 if kind == 'bgm' else .3), 0, 2, '音频音量')
            if 'duration' in clip:
                number(clip['duration'], .01, 36000, '音频时长')


def runtime_sources():
    root = runtime_root()
    for folder in ('demos', 'assets/lib', 'workbench/src', 'workbench/scripts'):
        for p in sorted((root / folder).rglob('*')):
            if p.name in ('mediaManifest.ts', 'projMeta.ts'):
                continue
            if p.is_file() and p.suffix in ('.tsx', '.ts', '.json', '.mjs', '.css'):
                yield p
    yield root / 'workbench/package-lock.json'
    for p in sorted((Path(__file__).parent / 'data').rglob('*.js')):
        yield p


def invoke(action, request, folder):
    wb = runtime_root() / 'workbench'
    if not (wb / 'node_modules/remotion/package.json').is_file() or not shutil.which('node'):
        raise VideoError('Remotion 环境未就绪，请运行 Skill 的 scripts/setup-motion.sh。')
    request_file = folder / f'{action}-request.json'
    write_json(request_file, request)
    log = folder / f'{action}.log'
    print(f'Remotion {action} 已启动，日志：{log}', flush=True)
    with log.open('w') as out:
        proc = subprocess.Popen(['node', str(wb / 'scripts/product-video.mjs'), action, str(request_file)], cwd=wb, stdout=out, stderr=subprocess.STDOUT)
        try:
            code = proc.wait(timeout=7200)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            raise VideoError(f'Remotion 已停止；已生成文件保留。查看日志：{log}') from None
    if code:
        raise VideoError(f'Remotion {action} 失败（退出码 {code}）。查看日志：{log}')


def clip(identifier, card, start, duration, *, props=None, speed=1, label=''):
    return dict(id=identifier, cardId=card, start=start, duration=max(1, duration), inOffset=0,
                speed=speed, opacity=1, scale=1, x=0, y=0, props=props or {}, label=label)


def timeline(config, chapters, public, render_plate):
    """Round each boundary once; adjacent shots share the exact same frame."""
    v, fps = config['video'], config['video']['fps']
    total = math.ceil(chapters[-1]['end'] * fps - 1e-8)
    tracks = {kind: [] for kind in ('captions', 'narration', 'sfx', 'bgm', 'shots')}
    public.mkdir(parents=True, exist_ok=True)

    def asset(source):
        source = Path(source)
        name = file_hash(source)[:20] + source.suffix.lower()
        destination = public / 'media' / name
        destination.parent.mkdir(exist_ok=True)
        if not destination.exists():
            pending = destination.with_suffix(destination.suffix + '.pending')
            shutil.copyfile(source, pending)
            pending.replace(destination)
        return 'media/' + name

    font_file = asset(v['font'])
    for ci, chapter in enumerate(chapters):
        voice_start = round((chapter['start'] + chapter['lead']) * fps)
        tracks['narration'].append(clip(f'voice-{ci}', 'pv-narration', voice_start,
            min(total - voice_start, math.ceil(chapter['audio_duration'] * fps)),
            props={'file': asset(chapter['audio']), 'volume': 1}, label=chapter['title']))
        for qi, cue in enumerate(chapter['cues']):
            start, end = round(cue['start'] * fps), round(cue['end'] * fps)
            tracks['captions'].append(clip(f'caption-{ci}-{qi}', 'pv-caption', start, end-start,
                props={'text': cue['text'], 'color': v['foreground'], 'background': v['surface'], 'fontFamily': 'ProductVideoFont'}, label=cue['text']))
        for si, step in enumerate(chapter['steps']):
            start = round((chapter['start'] if si == 0 else chapter['start'] + chapter['lead'] + step['at'] * chapter['audio_duration']) * fps)
            next_step = chapter['steps'][si+1] if si+1 < len(chapter['steps']) else None
            end = round((chapter['start'] + chapter['lead'] + next_step['at'] * chapter['audio_duration'] if next_step else chapter['end']) * fps)
            if end <= start:
                raise VideoError('镜头不足一帧，请合并镜头或延长旁白。')
            if 'editorial' in step:
                spec = step['editorial']
                items = []
                for item in spec['items']:
                    with Image.open(item['source']) as image:
                        image = ImageOps.exif_transpose(image)
                        width, height = image.size
                    items.append({'file': asset(item['source']), 'width': width, 'height': height, 'label': item.get('label', '')})
                props = {**spec, 'items': items, 'productName': config['product']['name'],
                         'section': chapter['title'], 'duration': end-start,
                         'background': v['background'], 'surface': v['surface'],
                         'foreground': v['foreground'], 'accent': v['accent'],
                         'reducedMotion': v['reduced_motion']}
                if config['product'].get('logo'):
                    props['logo'] = asset(config['product']['logo'])
                tracks['shots'].append(clip(f'shot-{ci}-{si}', 'pv-editorial', start, end-start,
                    props=props, label=spec['headline']))
            elif 'shotcraft' in step:
                spec = step['shotcraft']
                item = motion_item(spec['style'])
                speed = (item['frames'] - 1) / max(1, end - start - 1) if spec.get('timing', 'fit') == 'fit' else 30 / fps
                props = {'textMap': spec.get('text', {}), 'colorMap': spec.get('colors', {}),
                         'mediaMap': {key: asset(source) for key, source in spec.get('media', {}).items()},
                         'fontFamily': spec.get('font_family', 'ProductVideoFont')}
                if v['reduced_motion']:
                    speed = 0
                motion = clip(f'shot-{ci}-{si}', item['id'], start, end-start, props=props, speed=speed, label=item['name'])
                if v['reduced_motion']:
                    motion['inOffset'] = max(0, item['frames']-1)
                tracks['shots'].append(motion)
            else:
                plate = render_plate(ci, si, start, end)
                tracks['shots'].append(clip(f'shot-{ci}-{si}', 'video-clip', start, end-start,
                    props={'file': asset(plate), 'muted': True, 'fit': 'contain'}, label=chapter['title']))
    # Native action-to-result transitions stay inside their plates. Cross-engine
    # and chapter boundaries use the shared timeline without moving narration.
    shots = tracks['shots']
    for ci, chapter in enumerate(chapters):
        for si, step in enumerate(chapter['steps']):
            shot = next(x for x in shots if x['id'] == f'shot-{ci}-{si}')
            external = si == 0 or any(k in item for item in (step, chapter['steps'][si-1]) for k in ('shotcraft', 'editorial'))
            if not external or shot['start'] == 0 or v['reduced_motion']:
                continue
            if si == 0:
                kind = chapter.get('transition', v['transition_style'])
                seconds = min(chapter.get('transition_duration', v['transition']), chapter['lead'])
            else:
                kind = step.get('transition', v['step_transition'])
                seconds = min(step.get('transition_duration', v['transition']), shot['duration']/fps*.3)
            shot['transition'] = {'kind': kind, 'duration': min(shot['duration'], round(seconds*fps))}
    for kind, values in config.get('audio', {}).items():
        for i, sound in enumerate(values):
            start = round(sound.get('start', 0) * fps)
            actual = float(probe(sound['source'])['format']['duration'])
            duration = min(total - start, round(min(sound.get('duration', actual), actual) * fps))
            if duration <= 0:
                raise VideoError('背景音乐或音效的开始时间已超过成片。')
            tracks[kind].append(clip(f'{kind}-{i}', 'audio-clip', start, duration,
                props={'file': asset(sound['source']), 'volume': sound.get('volume', .12 if kind == 'bgm' else .3)}, label=Path(sound['source']).stem))
    names = {'shots': '画面', 'captions': '字幕', 'narration': '语音旁白', 'sfx': '音效', 'bgm': '背景音乐'}
    return {'name': config['product']['name'], 'fps': fps, 'width': v['width'], 'height': v['height'],
            'background': v['background'], 'fontFile': font_file,
            'source': digest({'config': config, 'audio': [c['audio_sha256'] for c in chapters]}),
            'tracks': [{'id': key, 'name': names[key], 'clips': clips} for key, clips in tracks.items()]}


def build(config, allow_api=False, preview=False, project_only=False):
    from .pipeline import prepare, project_lock, verify
    from .render import Renderer, encode_video
    from .subtitles import srt
    output = Path(config['output'])
    with project_lock(output):
        chapters = prepare(config, allow_api)
        assets = {p for c in chapters for s in c['steps'] for p in s['images']}
        assets.update(p for c in chapters for s in c['steps'] for p in s.get('shotcraft', {}).get('media', {}).values())
        assets.update(i['source'] for c in chapters for s in c['steps'] for i in s.get('editorial', {}).get('items', []))
        assets.update(d['source'] for c in chapters for s in c['steps'] for d in s.get('scene3d', {}).get('devices', []))
        assets.update(x['source'] for clips in config.get('audio', {}).values() for x in clips)
        assets.add(config['video']['font'])
        if config['product'].get('logo'):
            assets.add(config['product']['logo'])
        hashes = {str(p): file_hash(p) for p in assets}
        sources = {str(p.relative_to(runtime_root())) if p.is_relative_to(runtime_root()) else 'native/' + p.name: file_hash(p) for p in runtime_sources()}
        sources.update({p.name: file_hash(p) for p in Path(__file__).parent.glob('*.py')})
        source_hash = digest(sources)
        signature = digest({'config': config, 'audio': [c['audio_sha256'] for c in chapters], 'assets': hashes, 'motion': source_hash})[:16]
        folder = output / 'renders' / signature
        folder.mkdir(parents=True, exist_ok=True)
        public = folder / 'studio' / 'public'
        public.mkdir(parents=True, exist_ok=True)
        plates = folder / 'plates'
        plates.mkdir(exist_ok=True)
        legacy = copy.deepcopy(chapters)
        for ci, chapter in enumerate(legacy):
            for i, step in enumerate(chapter['steps']):
                if any(k in step for k in ('shotcraft', 'editorial')):
                    step.clear()
                    step.update(at=chapters[ci]['steps'][i]['at'], images=[], labels=[])
                if i and any(k in chapters[ci]['steps'][i-1] for k in ('shotcraft', 'editorial')):
                    step.update(transition='cut')
        with Renderer(config, legacy) as renderer:
            def render_plate(ci, si, start, end):
                plate_key = digest({'chapter': legacy[ci], 'step': si, 'range': [start, end],
                    'video': config['video'], 'product': config['product'], 'assets': hashes,
                    'renderer': {name: value for name, value in sources.items() if name.startswith('native/') or name in ('compositor.py', 'presentation.py', 'motion.py', 'premium_transitions.py', 'text_scenes.py', 'studio3d.py', 'scene3d.py')}})[:20]
                plate_cache = output / 'plates'
                plate_cache.mkdir(exist_ok=True)
                destination = plate_cache / f'{plate_key}.mp4'
                if destination.exists():
                    try:
                        verify(destination, config, (end-start)/config['video']['fps'])
                        return destination
                    except VideoError:
                        destination.unlink()
                silent = plates / f'{ci:02}-{si:02}.wav'
                duration = (end-start) / config['video']['fps']
                run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-t', str(duration), str(silent)])
                class Plate:
                    v = config['video']
                    total = duration
                    chapters = legacy
                    def frame(self, t):
                        return renderer.scene(ci, start / self.v['fps'] - chapters[ci]['start'] + t)
                pending = destination.with_suffix('.pending.mp4')
                try:
                    encode_video(Plate(), silent, pending)
                    pending.replace(destination)
                finally:
                    silent.unlink(missing_ok=True)
                    pending.unlink(missing_ok=True)
                return destination
            project = timeline(config, chapters, public, render_plate)
        write_json(folder / 'studio/project.json', project)
        write_json(folder / 'timeline.json', {'chapters': chapters, 'duration': chapters[-1]['end']})
        write_json(folder / 'project.resolved.json', config)
        atomic_write(folder / 'subtitles.srt', srt([cue for c in chapters for cue in c['cues']]).encode())
        atomic_write(folder / 'narration.txt', '\n\n'.join(c['narration'] for c in chapters).encode())
        write_json(output / 'studio.json', {'directory': str(folder / 'studio'), 'project': str(folder / 'studio/project.json')})
        if project_only:
            print(f'可编辑工程已生成：{folder / "studio/project.json"}')
            return folder
        request = {'project': project, 'publicDir': str(public)}
        if preview:
            previews = folder / 'preview'
            previews.mkdir(exist_ok=True)
            items = []
            for shot in next(t for t in project['tracks'] if t['id'] == 'shots')['clips']:
                offsets = [('start', 0), ('middle', shot['duration']//2), ('end', shot['duration']-1)]
                if shot['cardId'] == 'pv-editorial':
                    from .editorial import review_offsets
                    offsets = [(f'phase-{offset}', offset) for offset in review_offsets(shot['duration'], shot['props'], config['video']['fps'])]
                for phase, offset in offsets:
                    frame = shot['start'] + offset
                    items.append({'frame': frame, 'output': str(previews / f'{shot["id"]}-{phase}.png')})
            invoke('still', {**request, 'frames': items}, folder)
            write_json(previews / 'index.json', items)
            return folder
        movie = folder / 'product-introduction.mp4'
        pending = folder / 'product-introduction.pending.mp4'
        try:
            invoke('render', {**request, 'output': str(pending)}, folder)
            report = verify(pending, config, chapters[-1]['end'])
            pending.replace(movie)
        finally:
            pending.unlink(missing_ok=True)
        report.update(sha256=file_hash(movie), bytes=movie.stat().st_size, assets=hashes,
            frames=math.ceil(chapters[-1]['end'] * config['video']['fps'] - 1e-8), chapters=len(chapters),
            subtitle_cues=sum(len(c['cues']) for c in chapters), renderer='Remotion + video-shotcraft',
            upstream=catalogue()['upstream'], studio=str(folder / 'studio/project.json'),
            visual_review='unverified', listening_review='unverified')
        write_json(folder / 'verification.json', report)
        write_json(output / 'latest.json', {'movie': str(movie), 'report': str(folder / 'verification.json'), 'studio': str(folder / 'studio/project.json')})
        print(f'成片已生成并通过完整解码：{movie}')
        return folder
