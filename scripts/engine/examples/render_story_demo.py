"""Render original-style and text-led samples without narration API requests."""
import argparse
import copy
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from product_video.common import write_json
from product_video.config import load
from product_video.demo import create
from product_video.motion import PRESETS
from render_motion_demo import export_silent


def timed_chapters(config, durations):
    chapters, cursor = [], 0.
    for chapter, duration in zip(config['chapters'], durations):
        lead = max(.25, chapter.get('transition_duration', config['video']['transition']))
        length = math.ceil((lead + duration + .25) * config['video']['fps']) / config['video']['fps']
        chapters.append({**chapter, 'start': cursor, 'end': cursor + length, 'lead': lead,
                         'audio_duration': duration, 'cues': [{'start': cursor + lead,
                         'end': cursor + lead + duration, 'text': '无配音样片 · 示例界面 · 正文与旁白分别编排'}]})
        cursor += length
    return chapters


def render_story(destination, style='gallery', width=1920):
    destination = Path(destination).expanduser().resolve()
    original = json.loads(create(destination).read_text())
    original['product']['name'] = 'Product Video'
    original['video'] = {'style': 'classic', 'width': width, 'height': round(width * 9 / 16), 'fps': 30}
    original['chapters'] = [
        {'id': 'original', 'title': '原始版 · 界面与操作', 'narration': '保留原始界面布局，依次展示点击前后的状态。', 'steps': [
            {'at': 0, 'images': ['assets/dark-0.png'], 'labels': ['示例界面 · 操作前']},
            {'at': .4, 'images': ['assets/dark-1.png'], 'labels': ['示例界面 · 操作结果'],
             'interaction': {'kind': 'click', 'to': [.1, .27], 'from': [.42, .6]}}]},
        {'id': 'comparison', 'title': '原始版 · 双图对照', 'narration': '深色与浅色界面按原始双图布局并排显示。', 'steps': [
            {'at': 0, 'images': ['assets/dark-1.png', 'assets/light-1.png'], 'labels': ['深色示例', '浅色示例']}]}]
    path = destination / 'classic.json'
    write_json(path, original)
    config = load(path)
    export_silent(config, timed_chapters(config, [7.5, 2.2]), destination / 'classic',
                  'classic-original-look.mp4', style='classic', fixture_type='original presentation with corrected interactions')
    story = copy.deepcopy(original)
    story['video']['style'] = style
    split = {'layout': 'split', 'eyebrow': '03 / 图文讲解', 'headline': '进入配音设置',
             'body': '单击「配音」，显示配音设置界面。\n界面说明与操作画面并排显示。'}
    story['chapters'] = [
        {'id': 'opening', 'title': '文案开场', 'narration': '产品介绍可组合文案、界面截图和操作演示，配音与字幕按介绍稿生成。', 'steps': [
            {'at': 0, 'content': {'layout': 'title', 'eyebrow': 'PRODUCT VIDEO / 版式样例',
                'headline': '编排产品介绍视频', 'body': '组合文案、界面截图和操作演示。\n配音与字幕按介绍稿生成。'}}]},
        {'id': 'points', 'title': '分点介绍', 'narration': '文案镜头支持标题、正文和要点列表，图文镜头可选择左右布局。', 'steps': [
            {'at': 0, 'content': {'layout': 'bullets', 'eyebrow': '02 / 信息层次',
                'headline': '文案、界面与操作分步编排', 'bullets': ['纯文案镜头用于开场和章节说明',
                '图文并排呈现功能说明与界面细节', '模拟点击后显示对应的操作结果']}}]},
        {'id': 'split', 'title': '图文与操作', 'narration': '单击「配音」后显示设置界面；指针完成点击前，画面保持操作前状态。', 'steps': [
            {'at': 0, 'content': split, 'images': ['assets/dark-0.png'], 'labels': ['示例素材 · 操作前']},
            {'at': .4, 'content': copy.deepcopy(split), 'images': ['assets/dark-1.png'], 'labels': ['示例素材 · 操作结果'],
             'interaction': {'kind': 'click', 'from': [.42, .6], 'to': [.1, .27]}}]},
        {'id': 'screen', 'title': '恢复完整界面', 'narration': '恢复完整界面，保留页面结构与功能位置。', 'steps': [
            {'at': 0, 'images': ['assets/dark-1.png'], 'labels': ['示例素材 · 非真实产品录屏']} ]},
        {'id': 'closing', 'title': '文案收尾', 'narration': '完成编排后，导出视频、字幕和旁白原稿。仅修改画面时，可复用原有配音。', 'steps': [
            {'at': 0, 'content': {'layout': 'title', 'eyebrow': '片尾 / 下一步', 'headline': '导出视频与字幕',
                'body': '生成 MP4 视频、SRT 字幕和旁白原稿。\n修改画面时可复用未变更的配音。'}}]},
    ]
    path = destination / 'story.json'
    write_json(path, story)
    config = load(path)
    export_silent(config, timed_chapters(config, [4., 4.8, 6., 3., 4.]), destination / 'story',
                  'copy-story-demo.mp4', style=style, layouts=['title', 'bullets', 'split', 'screenshots'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    parser.add_argument('--style', choices=list(PRESETS), default='gallery')
    parser.add_argument('--width', type=int, choices=[1280, 1920], default=1920)
    args = parser.parse_args()
    render_story(args.directory, args.style, args.width)
