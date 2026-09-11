"""Compare every 2D preset with identical screenshot assets and shot timings."""
import argparse
import copy
import html
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw, ImageFont
from product_video.common import write_json
from product_video.config import load
from product_video.demo import create
from product_video.motion import PRESETS, STYLE_LABELS
from product_video.compositor import Renderer
from product_video.pipeline import verify
from render_motion_demo import export_silent


def compare(destination, before=None, after=None, width=1280):
    destination = Path(destination).expanduser().resolve()
    raw = json.loads(create(destination).read_text())
    if before and after:
        for path, name in [(before, 'dark-0.png'), (after, 'dark-1.png')]:
            with Image.open(path) as im:
                im.convert('RGB').save(destination/'assets'/name)
    raw['chapters'] = [{'id': 'theme', 'title': '主题与实时预览', 'narration': '无旁白风格对比。', 'steps': [
        {'at': 0, 'images': ['assets/dark-0.png'], 'labels': ['选择主题']},
        {'at': .34, 'images': ['assets/dark-1.png'], 'labels': ['查看结果'],
         'interaction': {'kind': 'click', 'from': [.4,.6], 'to': [.1,.27]}},
        {'at': .72, 'images': ['assets/dark-0.png','assets/dark-1.png'], 'labels': ['调整前','调整后']}]}]
    tiles, videos = [], []
    for style in PRESETS:
        raw['product']['name'] = 'Product Video · '+STYLE_LABELS[style]
        raw['video'] = {'style': style, 'width': width, 'height': round(width*9/16), 'fps': 30}
        path = destination/f'{style}.json'
        write_json(path, raw)
        config = load(path)
        chapter = {**config['chapters'][0], 'start': 0, 'end': 12.8, 'lead': .6,
                   'audio_duration': 12., 'cues': []}
        movie = destination/style/f'{style}.mp4'
        export_silent(config, [chapter], movie.parent, movie.name, style=style,
                      comparison='identical screenshots and shot timings')
        videos.append(movie)
        with Renderer(config, [chapter], '无旁白对比') as renderer:
            renderer.frame(2.5).save(destination/style/'poster.png')
            tile = Image.new('RGB', (640,400), '#17191d')
            tile.paste(renderer.frame(2.5).resize((640,360)), (0,40))
            ImageDraw.Draw(tile).text((16,7), STYLE_LABELS[style]+' / '+style,
                font=ImageFont.truetype(config['video']['font'],24), fill='#f5f5f3')
            tiles.append(tile)
        text_raw = copy.deepcopy(raw)
        text_raw['chapters'][0]['steps'] = [{'at':0,'content':{'layout':'title','eyebrow':'PRODUCT VIDEO',
            'headline':'从界面到成片','body':'编排镜头、旁白与字幕。\n按产品内容选择展示方式。'}}]
        text_path = destination/f'{style}-text.json'
        write_json(text_path,text_raw)
        text_config=load(text_path)
        with Renderer(text_config,[{**chapter, **text_config['chapters'][0]}],'无旁白对比') as renderer:
            renderer.frame(2.5).save(destination/style/'text.png')
        split_raw = copy.deepcopy(text_raw)
        split_raw['chapters'][0]['steps'][0].update(images=['assets/dark-0.png'])
        split_raw['chapters'][0]['steps'][0]['content']['layout']='split'
        split_path=destination/f'{style}-split.json';write_json(split_path,split_raw)
        split_config=load(split_path)
        with Renderer(split_config,[{**chapter,**split_config['chapters'][0]}],'无旁白对比') as renderer:
            renderer.frame(2.5).save(destination/style/'split.png')
    sheet=Image.new('RGB',(1280,1600),'#17191d')
    for i,tile in enumerate(tiles):sheet.paste(tile,(i%2*640,i//2*400))
    sheet.save(destination/'styles.jpg',quality=94)
    concat=destination/'sequence.txt'
    concat.write_text(''.join(f"file '{p.relative_to(destination)}'\n" for p in videos))
    sequence=destination/'all-styles.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(concat),
                    '-c','copy','-movflags','+faststart',str(sequence)],check=True)
    write_json(destination/'sequence-verification.json',verify(sequence,config,12.8*len(videos)))
    cards=''.join(f'<article><h2>{html.escape(STYLE_LABELS[s])} <small>{s}</small></h2>'
        f'<video controls muted loop playsinline preload="metadata" poster="{s}/poster.png" src="{s}/{s}.mp4"></video>'
        f'<p><a href="{s}/{s}.mp4">视频文件</a> · <a href="{s}/text.png">文字版式</a> · <a href="{s}/split.png">图文版式</a></p></article>' for s in PRESETS)
    (destination/'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Product Video · 二维风格对比</title><style>body{margin:0;background:#17191d;color:#eee;font:16px system-ui;padding:24px}h1{font-size:28px}p{color:#aeb3be;line-height:1.7}main{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:28px}article{min-width:0}h2{font-size:18px}small{font-weight:400;color:#aeb3be}video{display:block;width:100%;background:#111}a{color:#b9d6f4}button{font:inherit;background:#e9edf2;border:0;border-radius:6px;padding:9px 16px;margin:0 10px 20px 0;cursor:pointer}@media(max-width:760px){main{grid-template-columns:1fr}body{padding:16px}}</style>'
        '<h1>Product Video · 二维风格对比</h1><p>相同截图、相同镜头时序。分别观察构图、入场、点击结果与双图对照。无旁白，界面为示例素材。</p>'
        '<button id="play">从头同时播放</button><button id="pause">全部暂停</button><a href="all-styles.mp4">下载完整对比视频</a>'
        '<main>'+cards+'</main><script>document.querySelector("#play").onclick=()=>document.querySelectorAll("video").forEach(v=>{v.currentTime=0;v.play()});document.querySelector("#pause").onclick=()=>document.querySelectorAll("video").forEach(v=>v.pause());</script></html>')
    print(f'风格对比已生成：{sequence}',flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    parser.add_argument('--before',type=Path)
    parser.add_argument('--after',type=Path)
    parser.add_argument('--width',type=int,choices=[1280,1920],default=1280)
    args=parser.parse_args()
    if bool(args.before) != bool(args.after):parser.error('--before and --after must be supplied together')
    compare(args.directory,args.before,args.after,args.width)
