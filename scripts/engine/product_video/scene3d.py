"""Validated 3D shots and their local media contract."""
import math
from pathlib import Path

from PIL import Image, ImageOps

from .common import VideoError, probe


MODELS = ('phone', 'tablet', 'laptop', 'panel', 'iphone-17-pro-max', 'macbook-pro-16')
MOTIONS = ('orbit', 'reveal', 'push', 'rise', 'still')
LIGHTS = ('studio', 'soft', 'rim')


def media_info(path):
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            return {'type': 'image', 'width': im.width, 'height': im.height}
    except (OSError, ValueError):
        pass
    if Path(path).suffix.lower() not in ('.mp4', '.mov', '.webm', '.m4v'):
        raise VideoError('三维屏幕素材需为图片或 MP4、MOV、WebM、M4V 录屏。')
    data = probe(path)
    stream = next((s for s in data['streams'] if s['codec_type'] == 'video'), None)
    duration = float(data.get('format', {}).get('duration', 0))
    if not stream or not math.isfinite(duration) or duration <= 0:
        raise VideoError('屏幕录屏没有可解码的视频轨或有效时长。')
    return {'type': 'video', 'width': stream['width'], 'height': stream['height'], 'duration': duration}


def validate_scene(spec, base, video):
    from .config import known, number, text

    def vector(value, label, low=-50, high=50):
        if not isinstance(value, list) or len(value) != 3:
            raise VideoError(f'{label} 需要三个数值 [x, y, z]。')
        for item in value:
            number(item, low, high, label)

    known(spec, ('devices', 'motion', 'lighting', 'background', 'floor', 'camera'), 'scene3d')
    if spec.get('motion', 'orbit') not in MOTIONS:
        raise VideoError('scene3d.motion 仅支持 ' + '、'.join(MOTIONS) + '。')
    if spec.get('lighting', 'studio') not in LIGHTS:
        raise VideoError('scene3d.lighting 仅支持 studio、soft、rim。')
    if not isinstance(spec.get('floor', True), bool):
        raise VideoError('scene3d.floor 必须为布尔值。')
    devices = spec.get('devices')
    if not isinstance(devices, list) or not 1 <= len(devices) <= 4:
        raise VideoError('scene3d.devices 需要 1–4 台设备。')
    from PIL import ImageColor
    if 'background' in spec:
        try:
            ImageColor.getrgb(spec['background'])
        except (ValueError, TypeError, AttributeError):
            raise VideoError('scene3d.background 不是有效颜色。') from None
    for device in devices:
        known(device, ('model', 'source', 'position', 'rotation', 'scale', 'finish', 'color',
                       'fit', 'in', 'rate', 'keyframes'), '三维设备')
        if device.get('model', 'phone') not in MODELS:
            raise VideoError('三维设备 model 仅支持 ' + '、'.join(MODELS) + '。')
        text(device.get('source'), '三维屏幕素材', 4096)
        path = (base / Path(device['source']).expanduser()).resolve()
        if not path.is_file():
            raise VideoError(f'三维屏幕素材不存在：{path.name}。')
        info = media_info(path)
        device['source'] = str(path)
        if device.get('finish', 'metal') not in ('metal', 'clay'):
            raise VideoError('设备 finish 仅支持 metal 或 clay。')
        if device.get('fit', 'contain') not in ('contain', 'cover'):
            raise VideoError('设备 fit 仅支持 contain 或 cover；默认保留完整界面。')
        if 'color' in device:
            try:
                ImageColor.getrgb(device['color'])
            except (ValueError, TypeError, AttributeError):
                raise VideoError('设备 color 不是有效颜色。') from None
        for key, low, high in (('position', -50, 50), ('rotation', -360, 360)):
            if key in device:
                vector(device[key], key, low, high)
        number(device.get('scale', 1), .1, 5, '设备 scale')
        number(device.get('in', 0), 0, max(0, info.get('duration', 0) - .001), '录屏 in')
        number(device.get('rate', 1), .25, 4, '录屏 rate')
        if info['type'] != 'video' and ('in' in device or 'rate' in device):
            raise VideoError('in 和 rate 只用于录屏素材。')
        if 'keyframes' in device:
            frames = device['keyframes']
            if not isinstance(frames, list) or not 2 <= len(frames) <= 30:
                raise VideoError('设备 keyframes 需要 2–30 个关键帧。')
            last = -1
            for frame in frames:
                known(frame, ('at', 'position', 'rotation', 'scale', 'ease'), '设备关键帧')
                number(frame.get('at'), 0, 1, '关键帧 at')
                if frame['at'] <= last:
                    raise VideoError('关键帧 at 必须严格递增。')
                last = frame['at']
                vector(frame.get('position'), '关键帧 position')
                vector(frame.get('rotation'), '关键帧 rotation', -360, 360)
                number(frame.get('scale', device.get('scale', 1)), .1, 5, '关键帧 scale')
                if frame.get('ease', 'smooth') not in ('smooth', 'linear'):
                    raise VideoError('关键帧 ease 仅支持 smooth 或 linear。')
            if frames[0]['at'] != 0 or frames[-1]['at'] != 1:
                raise VideoError('设备关键帧必须覆盖 at: 0 到 at: 1。')
    if 'camera' in spec:
        camera = spec['camera']
        known(camera, ('position', 'target', 'fov', 'end_position', 'end_target'), '三维相机')
        for key in ('position', 'target', 'end_position', 'end_target'):
            if key in camera:
                vector(camera[key], 'camera.' + key)
        number(camera.get('fov', 32), 15, 75, 'camera.fov')
        start = camera.get('position', [0, 1, 15])
        target = camera.get('target', [0, 0, 0])
        if start == target or camera.get('end_position', start) == camera.get('end_target', target):
            raise VideoError('相机位置不能与观察目标重合。')
    return spec
