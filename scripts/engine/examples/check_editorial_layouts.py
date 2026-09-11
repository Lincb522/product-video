"""Render layout boundary fixtures from a prepared editorial example; no TTS."""
import argparse,copy,json,shutil,sys
from pathlib import Path
from PIL import Image,ImageChops,ImageDraw,ImageStat
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from product_video.shotcraft import invoke,clip
from product_video.common import write_json
from product_video.config import load
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('project',type=Path)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
config=load(args.project)
studio=json.loads((Path(config['output'])/'studio.json').read_text())
base=json.loads(Path(studio['project']).read_text())
out=args.output.expanduser().resolve();out.mkdir(parents=True,exist_ok=True)
public=out/'public';public.mkdir(exist_ok=True)
font=Path(base['fontFile']);(public/font).parent.mkdir(parents=True,exist_ok=True)
shutil.copyfile(Path(studio['directory'])/'public'/font,public/font)
items=[]
for name,size in [('landscape',(1440,900)),('portrait',(600,1200))]:
 im=Image.new('RGB',size,'#395a4d');d=ImageDraw.Draw(im)
 for color,(x,y) in zip(['#ff3020','#18e545','#3057ff','#ffe023'],[(0,0),(size[0]-100,0),(0,size[1]-100),(size[0]-100,size[1]-100)]):d.rectangle((x,y,x+99,y+99),fill=color)
 path=public/'media'/f'boundary-{name}.png';im.save(path)
 items.append({'file':'media/'+path.name,'width':size[0],'height':size[1],'label':'项目版本与详细功能对照'})
source=next(t for t in base['tracks'] if t['id']=='shots')['clips'][0]['props']
for width,fps in [(1280,30),(1920,60)]:
 project=copy.deepcopy(base);project.update(width=width,height=width*9//16,fps=fps)
 shots=[];frames=[];start=0
 cases=[
 ('overview-2',{'layout':'overview','items':items},[1,4,9,11.9],12),
 ('overview-6',{'layout':'overview','items':items*3},[1,6,12,19.9],20),
 ('portal',{'layout':'portal','items':items*2},[1,3.9],4),
 ('fan',{'layout':'fan','items':items+[items[0]]},[1,3.9],4),
 ('side-long',{'layout':'side','items':items[1:],'headline':'根据实际内容组织功能总览与详细操作演示并展示完整结果',
    'eyebrow':'界面与说明','notes':['对应当前版本中的具体功能与可见结果说明内容','对应当前版本中的具体功能与可见结果说明内容','对应当前版本中的具体功能与可见结果说明内容'],'motion':'content-lift'},[1,3.9],4),
 ('full-long',{'layout':'full','items':items[:1],'headline':'根据实际内容组织功能总览与详细操作演示并展示完整结果',
    'eyebrow':'长标题与说明边界','notes':['对应当前版本中的具体功能与可见结果说明内容']*3},[2],4),
 ('pair-mixed',{'layout':'pair','items':items,'motion':'paired-slide'},[1,3.9],4),
 ('reduced',{'layout':'overview','items':items*3,'reducedMotion':True},[0,9.9],10),
 ]
 for name,over,times,seconds in cases:
  props=copy.deepcopy(source);props.pop('focus_at',None);props.update(over)
  duration=round(seconds*fps);shots.append(clip(name,'pv-editorial',start,duration,props=props))
  for t in times:frames.append({'frame':start+round(t*fps),'output':str(out/f'{width}-{name}-{t}.png')})
  start+=duration
 project['tracks']=[{'id':'shots','name':'Boundary fixtures','clips':shots}]
 write_json(out/f'project-{width}.json',project)
 invoke('still',{'project':project,'publicDir':str(public),'frames':frames},out)
 print(width,'passed',len(frames),flush=True)

for width in (1280,1920):
 with Image.open(out/f'{width}-reduced-0.png') as first, Image.open(out/f'{width}-reduced-9.9.png') as last:
  assert ImageChops.difference(first,last).getbbox() is None, 'Reduced motion changed between frames.'
 with Image.open(out/f'{width}-overview-6-6.png') as early, Image.open(out/f'{width}-overview-6-19.9.png') as late:
  assert sum(ImageStat.Stat(ImageChops.difference(early,late)).mean)>10, 'Long overview froze at its library preview length.'
 for name in ('full-long-2','pair-mixed-3.9','side-long-3.9'):
  with Image.open(out/f'{width}-{name}.png') as frame:
   channels=frame.convert('RGB').split()
   for color in ((255,48,32),(24,229,69),(48,87,255),(255,224,35)):
    masks=[channel.point(lambda value,c=c:255 if abs(value-c)<12 else 0) for channel,c in zip(channels,color)]
    mask=ImageChops.multiply(ImageChops.multiply(masks[0],masks[1]),masks[2])
    assert mask.histogram()[255]>25, f'Missing screenshot corner: {width} {name} {color}'
for name in ('full-long-2','pair-mixed-3.9','overview-6-19.9','reduced-0'):
 with Image.open(out/f'1280-{name}.png') as small, Image.open(out/f'1920-{name}.png') as large:
  error=sum(ImageStat.Stat(ImageChops.difference(small,large.resize(small.size,Image.Resampling.LANCZOS))).mean)/3
  assert error<3, f'Frame timing or layout differs across 30/60 fps and 720p/1080p: {name} {error}'
write_json(out/'verification.json',{'frames':38,'sizes':[1280,1920],'fps':[30,60],
 'corner_markers':'passed','reduced_motion':'passed','long_overview':'passed','normalized_frames':'passed','visual_review':'unverified'})
print('Corner markers, reduced motion, long duration and cross-size timing checks passed.')
