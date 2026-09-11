"""Record an interactive fixture and render a complete 3D sample without TTS."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from product_video.common import file_hash, write_json
from product_video.config import load
from product_video.pipeline import verify
from product_video.recording import record_web
from product_video.render import Renderer, encode_video


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def recorded_fixture(folder):
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(Path(__file__).parent)))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        for name, size in [('phone', (440, 956)), ('desktop', (1728, 1117))]:
            dest = folder / f'{name}.mp4'
            if dest.exists():
                report = json.loads(dest.with_suffix('.recording.json').read_text())
                if file_hash(dest) != report['sha256']:
                    raise ValueError('Existing fixture recording changed; use a new output directory.')
                continue
            field = {'role': 'textbox', 'name': '搜索记录'}
            plan = {'schema_version': 1, 'target': {'provider': 'web',
                'url': f'http://127.0.0.1:{server.server_port}/studio-notes.html',
                'viewport': {'width': size[0], 'height': size[1]}, 'color_scheme': 'dark'},
                'shots': [
                    {'id': 'initial', 'ready': {'role': 'heading', 'name': '项目记录'}},
                    {'id': 'search', 'actions': [{'action': 'fill', 'target': field, 'value': '界面'}],
                     'ready': {'role': 'heading', 'name': '界面录屏'}},
                    {'id': 'mark', 'actions': [{'action': 'click', 'target': {'role': 'button', 'name': '标记界面录屏'}}],
                     'ready': {'role': 'button', 'name': '标记界面录屏'}},
                    {'id': 'saved', 'actions': [{'action': 'press', 'target': field, 'value': 'ControlOrMeta+A'},
                        {'action': 'press', 'target': field, 'value': 'Backspace'},
                        {'action': 'click', 'target': {'role': 'button', 'name': '已标记'}}],
                     'ready': {'role': 'heading', 'name': '界面录屏'}},
                ]}
            write_json(folder / f'{name}.capture.json', plan)
            record_web(folder / f'{name}.capture.json', dest)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--width', type=int, default=1920)
    parser.add_argument('--preview-only', action='store_true')
    args = parser.parse_args()
    folder = args.output.expanduser().resolve(); folder.mkdir(parents=True, exist_ok=True)
    media = folder / 'media'; media.mkdir(exist_ok=True)
    recorded_fixture(media)
    phone, desktop = str(media / 'phone.mp4'), str(media / 'desktop.mp4')
    stages = [
        ('hero', 6., '屏幕与镜头同步', {'background': '#d8d8d3', 'lighting': 'soft', 'motion': 'reveal',
            'camera': {'position': [0, .6, 12.7], 'end_position': [.2, .25, 12.3]},
            'devices': [{'model': 'iphone-17-pro-max', 'source': phone, 'rotation': [5, -14, -6], 'color': '#bbc0c5'}]}),
        ('pair', 5., '多设备与材质', {'background': '#171c1f', 'lighting': 'rim', 'motion': 'orbit',
            'camera': {'position': [0, .5, 13]},
            'devices': [{'model': 'iphone-17-pro-max', 'source': phone, 'rotation': [8, 15, -9], 'position': [-1.48, .12, 0], 'color': '#bbc0c5'},
                        {'model': 'iphone-17-pro-max', 'source': phone, 'in': 1.5, 'rotation': [8, 168, 9], 'position': [1.35, -.05, -.65], 'color': '#c76b3a'}]}),
        ('laptop', 6., '真实操作录屏', {'background': '#d8d8d3', 'lighting': 'studio', 'motion': 'orbit',
            'camera': {'position': [0, 3.2, 16], 'target': [0, -.35, .6]},
            'devices': [{'model': 'macbook-pro-16', 'source': desktop, 'rotation': [0, -14, -3], 'color': '#aeb2b6'}]}),
        ('copy', 5., '图文与三维镜头', {'background': '#d8d8d3', 'lighting': 'soft', 'motion': 'rise',
            'camera': {'position': [0, .4, 12.8]},
            'devices': [{'model': 'iphone-17-pro-max', 'source': phone, 'rotation': [5, -12, -5]}]}),
    ]
    raw = {'schema_version': 1, 'product': {'name': 'Product Video'}, 'output': str(folder / 'narrated-output'),
           'video': {'style': 'gallery', 'width': args.width, 'height': round(args.width * 9 / 16), 'fps': 30,
                     'background': '#d8d8d3', 'foreground': '#202723', 'accent': '#56634f', 'progress': False,
                     'transition_style': 'fade', 'transition': .5}, 'chapters': []}
    for sid, duration, title, scene in stages:
        step = {'at': 0, 'scene3d': scene}
        if sid == 'copy':
            step['content'] = {'layout': 'split', 'eyebrow': 'PRODUCT VIDEO · 3D',
                'headline': '三维设备\n与真实录屏', 'body': '编排设备、灯光和镜头。\n文案、配音与字幕沿用同一份项目。', 'animation': 'reveal'}
        raw['chapters'].append({'id': sid, 'title': title, 'narration': title + '。', 'steps': [step]})
    write_json(folder / 'project.json', raw)
    config = load(folder / 'project.json')
    chapters, cursor = [], 0.
    for c, (_, duration, _, _) in zip(config['chapters'], stages):
        chapters.append(dict(c, start=cursor, end=cursor + duration + .5, lead=.5, audio_duration=duration, cues=[]))
        cursor += duration + .5
    previews = folder / 'preview'; previews.mkdir(exist_ok=True)
    started = time.monotonic()
    with Renderer(config, chapters, narration_label='无配音样片') as renderer:
        index = []
        for ci, chapter in enumerate(chapters):
            for phase, at in renderer.review_times(ci, 0).items():
                name = f'{chapter["id"]}-{phase}.png'
                renderer.frame(at).save(previews / name)
                index.append({'file': name, 'time': at, 'phase': phase})
        write_json(previews / 'index.json', index)
        write_json(folder / 'timeline.json', {'chapters': chapters, 'duration': renderer.total})
        if args.preview_only:
            print(f'Preview: {previews}; {renderer.studio.info}', flush=True)
            return
        audio = folder / 'silence.wav'
        with wave.open(str(audio), 'wb') as out:
            out.setparams((2, 2, 48000, 0, 'NONE', 'not compressed'))
            out.writeframes(b'\x00' * round(renderer.total * 48000) * 4)
        pending = folder / 'studio-demo.pending.mp4'
        try:
            frames = encode_video(renderer, audio, pending, metadata_comment='Silent 3D rendering sample; recorded interactive fixture; no TTS')
            report = verify(pending, config, renderer.total)
            pending.replace(folder / 'studio-demo.mp4')
        finally:
            pending.unlink(missing_ok=True)
        movie = folder / 'studio-demo.mp4'
        report.update(frames=frames, sha256=file_hash(movie), renderer_3d=renderer.studio.info,
                      elapsed_seconds=round(time.monotonic() - started, 2),
                      narration='none', screen_media='recorded interactive fixture, not a customer product',
                      visual_review='unverified')
        write_json(folder / 'verification.json', report)
        print(f'3D sample: {movie}', flush=True)


if __name__ == '__main__':
    main()
