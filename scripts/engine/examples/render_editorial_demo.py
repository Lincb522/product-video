"""Create an offline content-layout project with explicitly silent fixture audio."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from product_video.common import audio_duration, file_hash, run, write_json
from product_video.config import load
from product_video.demo import create
from product_video.shotcraft import build
from product_video.tts import cache_location


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--mode', choices=('prepare', 'preview', 'render'), default='preview')
    args = parser.parse_args()
    path = create(args.output, schema_version=2)
    raw = json.loads(path.read_text())
    raw['product']['name'] = 'Product Video · 布局示例'
    raw['video'].update(width=args.width, height=round(args.width*9/16), fps=30,
        background='#151c1b', surface='#23312c', foreground='#f4f2e9', accent='#b9d8a0',
        transition=.3, chapter_pause=.2, subtitles='none', progress=False)
    items = [{'source': f'assets/{name}.png', 'label': label} for name, label in [
        ('dark-0', '项目界面'), ('dark-1', '配音界面'), ('light-0', '浅色项目'), ('light-1', '浅色配音')]]
    scenes = [
        (12, {'layout': 'overview', 'headline': '先看全貌，再展开重点', 'items': items, 'focus_at': [.12,.29,.46,.63]}),
        (3, {'layout': 'portal', 'headline': '从总览进入具体功能', 'items': items}),
        (4, {'layout': 'fan', 'headline': '同组界面\n依次展开', 'eyebrow': '素材陈列', 'notes': ['保持图片原始比例'], 'items': items[:3]}),
        (4, {'layout': 'side', 'headline': '文案说明\n紧邻对应界面', 'notes': ['界面呈现操作位置', '文字补充必要背景'], 'items': items[:1], 'motion': 'content-lift'}),
        (4, {'layout': 'pair', 'headline': '两种状态，同时比较', 'items': [items[1], items[3]], 'motion': 'paired-slide'}),
        (5, {'layout': 'pair', 'headline': '同一界面的主题变化', 'items': [items[1], items[3]], 'motion': 'comparison-wipe'}),
    ]
    for motion, title in [
        ('none','完整界面'), ('panel-assemble','按实际分栏拼合'), ('row-embed','按内容行依次展开'),
        ('camera-tour','推近并移动视点'), ('focus-pull','焦点回到界面'), ('orbit-level','倾斜回正'),
        ('mask-reveal','遮罩展开'), ('panel-unfold','线条展开为面板'), ('pull-back','拉远呈现全貌'),
        ('filmstrip','同类内容连续浏览'), ('card-flip','两种状态翻面切换')]:
        spec = {'layout': 'full', 'headline': title, 'motion': motion,
                'items': items if motion=='filmstrip' else items[:2] if motion=='card-flip' else items[:1]}
        if motion=='panel-assemble': spec['slices']=[0, .2, 1]
        if motion=='row-embed': spec['slices']=[0, .2, .4, .6, .8, 1]
        scenes.append((7 if motion=='filmstrip' else 3, spec))
    raw['chapters']=[{'id':f'layout-{i}', 'title':spec['layout'], 'narration':f'无旁白示例：{spec["headline"]}。',
        'steps':[{'at':0,'editorial':spec}]} for i, (_,spec) in enumerate(scenes)]
    write_json(path,raw)
    config=load(path)
    for chapter,(duration,_) in zip(config['chapters'],scenes):
        folder=cache_location(Path(config['output']),chapter,config['voice'])
        folder.mkdir(parents=True,exist_ok=True)
        audio=folder/'voice.mp3'
        run(['ffmpeg','-v','error','-f','lavfi','-i','anullsrc=r=24000:cl=mono','-t',str(duration),'-c:a','libmp3lame',audio])
        write_json(folder/'metadata.json', {'duration':audio_duration(audio),'sha256':file_hash(audio),
            'source':'silent-layout-fixture','events':[], 'speaker':'none'})
    result=build(config,allow_api=False,preview=args.mode=='preview',project_only=args.mode=='prepare')
    print(f'Offline layout example: {result}. Audio is silent; no TTS request was made.')


if __name__=='__main__':
    main()
