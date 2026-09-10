"""Render an explicitly silent motion demo through the production compositor."""
import argparse
import copy
import json
from pathlib import Path
import sys
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from product_video.common import file_hash, write_json
from product_video.config import load
from product_video.demo import create
from product_video.motion import PRESETS, STYLE_LABELS, TRANSITIONS
from product_video.premium_transitions import PREMIUM_TRANSITIONS
from product_video.pipeline import verify
from product_video.render import Renderer, encode_video
from product_video.subtitles import srt


def render_demo(destination, styles, width=1920, transitions=TRANSITIONS):
    destination = Path(destination).expanduser().resolve()
    # create() refuses a nonempty directory; a review never overwrites older output.
    project_path = create(destination)
    original = json.loads(project_path.read_text())
    for style in styles:
        project = copy.deepcopy(original)
        project['product']['name'] = 'Product Video · 动效示例'
        project['video'] = {'style': style, 'width': width, 'height': round(width * 9 / 16), 'fps': 30}
        project['chapters'] = [
            {'id': 'operation', 'title': f'{STYLE_LABELS[style]} · 操作与局部聚焦',
             'narration': '无配音动效示例。', 'steps': [
                 {'at': 0, 'images': ['assets/dark-0.png'], 'labels': ['示例界面 · 操作前']},
                 {'at': .28, 'images': ['assets/dark-1.png'], 'labels': ['示例界面 · 操作结果'],
                  'interaction': {'kind': 'click', 'from': [.42, .6], 'to': [.1, .27]}},
                 {'at': .65, 'images': ['assets/dark-1.png'], 'labels': ['示例界面 · 细节'],
                  'transition': 'cut', 'camera': {'zoom': 1.25, 'center': [.63, .67]}}]},
            {'id': 'comparison', 'title': '并排对照 · 保持界面比例', 'narration': '无配音动效示例。',
             'steps': [{'at': 0, 'images': ['assets/dark-1.png', 'assets/light-1.png'],
                        'labels': ['深色示例', '浅色示例']}]},
        ]
        for i, transition in enumerate(transitions):
            project['chapters'].append({
                'id': f'effect-{i}', 'title': f'转场示例 · {transition}', 'transition': transition,
                'transition_duration': .9 if transition in PREMIUM_TRANSITIONS else .7 if transition != 'cut' else 0,
                'narration': '无配音转场示例。', 'steps': [
                    {'at': 0, 'images': [f"assets/{'dark' if i % 2 else 'light'}-1.png"],
                     'labels': ['示例素材 · 非真实产品录屏']}]})
        path = destination / f'{style}.json'
        write_json(path, project)
        config = load(path)
        chapters, cursor = [], 0.
        for i, chapter in enumerate(config['chapters']):
            duration = 7.5 if i == 0 else 2.2 if i == 1 else 1.
            lead = max(.25, chapter.get('transition_duration', config['video']['transition']))
            length = lead + duration + .25
            cue = {'start': cursor + lead, 'end': cursor + length - .1,
                   'text': '观察顺序：移动 → 停留 → 点击 → 界面变化' if i == 0 else '无配音样片 · 仅用于检查画面与动效'}
            chapters.append({**chapter, 'start': cursor, 'end': cursor + length, 'lead': lead,
                             'audio_duration': duration, 'cues': [cue]})
            cursor += length
        export_silent(config, chapters, destination / style, f'{style}-motion-demo.mp4',
                      style=style, transitions=list(transitions))


def export_silent(config, chapters, folder, filename, **details):
    folder.mkdir()
    renderer = Renderer(config, chapters, narration_label='无配音样片')
    audio = folder / 'silence.wav'
    with wave.open(str(audio), 'wb') as out:
        out.setnchannels(2); out.setsampwidth(2); out.setframerate(48000)
        out.writeframes(b'\x00' * round(renderer.total * 48000) * 4)
    previews = folder / 'preview'
    previews.mkdir()
    index = []
    for ci, chapter in enumerate(chapters):
        for si, step in enumerate(chapter['steps']):
            for phase, time in renderer.review_times(ci, si).items():
                name = f'{ci:02}-{si:02}-{phase}.png'
                renderer.frame(time).save(previews / name)
                index.append({'file': name, 'time': time, 'phase': phase})
    write_json(previews / 'index.json', index)
    write_json(folder / 'timeline.json', {'chapters': chapters, 'duration': renderer.total})
    (folder / 'subtitles.srt').write_text(srt([cue for c in chapters for cue in c['cues']]))
    movie = folder / filename
    partial = folder / (movie.stem + '.pending.mp4')
    try:
        frames = encode_video(renderer, audio, partial)
        report = verify(partial, config, renderer.total)
        partial.replace(movie)
    finally:
        partial.unlink(missing_ok=True)
    report.update(frames=frames, sha256=file_hash(movie), fixture=True, narration='silent; no API called',
                  visual_review='unverified', **details)
    write_json(folder / 'verification.json', report)
    print(f'无配音动效样片已验证：{movie}', flush=True)
    return report

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    parser.add_argument('--style', choices=['all', 'premium', *PRESETS], default='all')
    parser.add_argument('--transitions', choices=['all', 'premium'], default='all')
    parser.add_argument('--width', type=int, choices=[1280, 1920], default=1920)
    args = parser.parse_args()
    styles = list(PRESETS) if args.style == 'all' else ['cinema', 'gallery', 'minimal'] if args.style == 'premium' else [args.style]
    render_demo(args.directory, styles, args.width, PREMIUM_TRANSITIONS if args.transitions == 'premium' else TRANSITIONS)
