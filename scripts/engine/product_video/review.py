"""Extract review frames from the encoded movie using its saved timeline."""
import json
import math
from pathlib import Path
import tempfile

from .common import VideoError, file_hash, probe, run, write_json


def selection(frames):
    # A flat sum of many eq() calls exceeds FFmpeg's expression parser depth.
    if len(frames) == 1:
        return f'eq(n,{frames[0]})'
    middle = len(frames) // 2
    return f'({selection(frames[:middle])}+{selection(frames[middle:])})'


def extract_frames(movie, frames, destination):
    movie, destination = Path(movie), Path(destination)
    frames = sorted(set(frames))
    if not frames or any(type(f) is not int or f < 0 for f in frames):
        raise VideoError('复核帧需为非负整数，至少提供一帧。')
    info = probe(movie)
    video = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
    if not video:
        raise VideoError('复核文件没有视频轨。')
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.review-', dir=destination) as temp:
        run(['ffmpeg', '-v', 'error', '-xerror', '-i', movie, '-vf',
             "select='" + selection(frames) + "'", '-fps_mode', 'vfr',
             '-frames:v', str(len(frames)), Path(temp) / '%06d.png'],
            timeout=max(120, math.ceil(float(info['format']['duration']) * 3)))
        files = sorted(Path(temp).glob('*.png'))
        if len(files) != len(frames):
            raise VideoError('部分复核帧超出视频范围；请按实际时间轴重新选择。')
        index = []
        for frame, source in zip(frames, files):
            target = destination / f'frame-{frame:06d}.png'
            source.replace(target)
            index.append({'frame': frame, 'file': target.name})
    return index


def review(project):
    from .config import load
    from .editorial import review_offsets
    config = load(project)
    latest = Path(config['output']) / 'latest.json'
    if not latest.is_file():
        raise VideoError('尚无已验证成片，请先运行 render 或 build。')
    saved = json.loads(latest.read_text())
    movie = Path(saved['movie'])
    report = json.loads(Path(saved['report']).read_text())
    if not movie.is_file() or file_hash(movie) != report.get('sha256'):
        raise VideoError('成片与校验记录不一致，请重新渲染或使用对应版本的记录。')
    frames = set()
    if saved.get('studio'):
        timeline = json.loads(Path(saved['studio']).read_text())
        for track in timeline['tracks']:
            if track['id'] != 'shots':
                continue
            for shot in track['clips']:
                duration = shot['duration']
                offsets = review_offsets(duration, shot['props'], timeline['fps']) if shot['cardId'] == 'pv-editorial' else [0, duration//2, duration-1]
                frames.update(shot['start'] + offset for offset in offsets)
    previews = movie.parent / 'preview/index.json'
    if previews.is_file():
        for item in json.loads(previews.read_text()):
            if 'frame' in item:
                frames.add(item['frame'])
            elif 'time' in item:
                frames.add(round(item['time'] * config['video']['fps']))
    if not frames:
        raise VideoError('未找到镜头复核时间，请先对该项目运行 preview。')
    destination = movie.parent / 'review'
    index = extract_frames(movie, frames, destination)
    write_json(destination / 'index.json', {'movie_sha256': report['sha256'], 'frames': index,
        'visual_review': 'unverified', 'listening_review': 'unverified'})
    print(f'已从成片提取 {len(index)} 张复核帧：{destination}')
    return destination
