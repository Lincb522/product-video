"""Render three authored HTML compositions alongside existing Product Video shots.

Uses labeled synthetic screens and silent fixture audio, with no TTS requests.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from product_video.common import audio_duration, file_hash, run, write_json
from product_video.config import load
from product_video.demo import create
from product_video.shotcraft import build
from product_video.tts import cache_location


def create_project(output, width=1280, reduced_motion=False):
    path = create(output, schema_version=2)
    raw = json.loads(path.read_text())
    raw['product']['name'] = 'Product Video · HTML 镜头示例'
    raw['video'].update(width=width, height=round(width*9/16), fps=30,
        background='#182e29', surface='#23382f', foreground='#f3f2e9', accent='#d7e795',
        transition=.3, chapter_pause=.2, subtitles='none', progress=False, reduced_motion=reduced_motion)
    shutil.copytree(Path(__file__).parent/'hyperframes', path.parent/'scenes')
    scenes = [
        ('reveal', '图文构图', {'screen': 'assets/light-0.png'}),
        ('flow', '流程展开', {'screen': 'assets/dark-0.png', 'detail': 'assets/dark-1.png'}),
        ('compare', '主题对照', {'light': 'assets/light-1.png', 'dark': 'assets/dark-1.png'}),
    ]
    raw['chapters'] = [{'id': key, 'title': title, 'narration': f'无旁白示例：{title}。',
        'steps': [{'at': 0, 'hyperframes': {'entry': f'scenes/{key}/index.html', 'media': media}}]}
        for key, title, media in scenes]
    raw['chapters'].append({'id': 'operation', 'title': '操作与结果', 'narration': '无旁白示例：先点击，再显示结果。',
        'steps': [{'at': 0, 'images': ['assets/dark-0.png']},
            {'at': .45, 'images': ['assets/dark-1.png'],
             'interaction': {'kind': 'click', 'from': [.4,.4], 'to': [.1,.27]}}]})
    raw['chapters'].append({'id': 'editorial', 'title': '内容镜头', 'narration': '无旁白示例：既有内容镜头。',
        'steps': [{'at': 0, 'editorial': {'layout': 'pair', 'headline': 'HTML 与现有镜头共同编排',
            'motion': 'paired-slide', 'items': [{'source': 'assets/light-0.png', 'label': '项目'},
                {'source': 'assets/light-1.png', 'label': '配音'}]}}]})
    write_json(path, raw)
    config = load(path)
    for chapter in config['chapters']:
        folder = cache_location(Path(config['output']), chapter, config['voice'])
        folder.mkdir(parents=True, exist_ok=True)
        audio = folder/'voice.mp3'
        run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'anullsrc=r=24000:cl=mono',
            '-t', '4', '-c:a', 'libmp3lame', audio])
        write_json(folder/'metadata.json', {'duration': audio_duration(audio), 'sha256': file_hash(audio),
            'source': 'silent-html-fixture', 'events': [], 'speaker': 'none'})
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--reduced-motion', action='store_true')
    parser.add_argument('--mode', choices=('prepare', 'preview', 'render'), default='render')
    args = parser.parse_args()
    path = create_project(args.output, args.width, args.reduced_motion)
    result = build(load(path), allow_api=False, preview=args.mode=='preview', project_only=args.mode=='prepare')
    print(f'示例：{result}。无旁白，界面为演示素材，未调用 TTS。')
