"""Record the existing observed web-capture plan into a screen-video asset."""
from pathlib import Path
import tempfile
import time

from .capture import capture_web, read_plan, web_locator, web_session
from .common import VideoError, file_hash, probe, run, write_json


def record_web(plan_path, destination):
    plan = read_plan(plan_path)
    if plan['target']['provider'] != 'web':
        raise VideoError('record-web 需要 web 采集计划；原生应用录屏请提供已录制的视频素材。')
    if plan['shots'][0]['actions']:
        raise VideoError('录屏计划的第一项应为无 actions 的 ready 初始画面，后续项目再操作。')
    if any(s['mask'] for s in plan['shots']):
        raise VideoError('record-web 不支持截图 mask。请使用已去除私人内容的演示页面，或先准备处理后的录屏。')
    destination = Path(destination).expanduser().resolve()
    if destination.suffix.lower() != '.mp4':
        raise VideoError('record-web 输出路径使用 .mp4。')
    if destination.exists():
        raise VideoError('录屏输出已存在，请使用新文件名以保留已有素材。')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='product-video-record-', dir=destination.parent) as temporary:
        folder = Path(temporary)
        events = []
        with web_session(plan['target'], record_dir=folder) as page:
            web_locator(page, plan['shots'][0]['ready']).wait_for(state='visible')
            source = Path(page.video.path())
            start = time.monotonic()
            page.wait_for_timeout(650)
            for shot in plan['shots']:
                events.append({'shot': shot['id'], 'start': round(time.monotonic() - start, 3)})
                capture_web(page, plan['target'], shot, folder / (shot['id'] + '.png'), recording=True)
            page.wait_for_timeout(900)
            elapsed = time.monotonic() - start
        total = float(probe(source)['format']['duration'])
        offset = max(0, total - elapsed)
        pending = folder / 'screen.mp4'
        run(['ffmpeg', '-v', 'error', '-y', '-i', source, '-ss', str(offset), '-t', str(elapsed),
             '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '16', '-pix_fmt', 'yuv420p',
             '-movflags', '+faststart', pending], timeout=max(120, int(elapsed * 3)))
        run(['ffmpeg', '-v', 'error', '-xerror', '-i', pending, '-f', 'null', '-'])
        duration = float(probe(pending)['format']['duration'])
        write_json(destination.with_suffix('.recording.json'), {
            'provider': 'playwright-video', 'plan_sha256': file_hash(plan_path),
            'sha256': file_hash(pending), 'duration': duration, 'events': events,
            'timing': 'Wall-clock shot starts; inspect frames before using precise action cuts.',
            'full_decode': 'passed', 'visual_review': 'unverified'})
        pending.replace(destination)
    print(f'网页录屏已保存并通过完整解码：{destination}', flush=True)
    return destination
