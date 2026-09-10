"""Deterministic transitions and screenshot interaction timing, in seconds."""
import math

from PIL import Image, ImageFilter

from .common import VideoError
from .premium_transitions import PREMIUM_TRANSITIONS, premium_transition


TRANSITIONS = ('cut', 'fade', 'slide-left', 'slide-right', 'slide-up',
               'wipe-left', 'wipe-right', 'zoom', 'blur') + PREMIUM_TRANSITIONS
STYLE_LABELS = {'product': '产品演示', 'promo': '节奏宣传', 'tutorial': '教学演示',
                'cinema': '影院', 'gallery': '画廊', 'minimal': '极简', 'classic': '原始版'}
PRESETS = {
    'classic': {'transition': .6, 'transition_style': 'fade', 'step_transition': 'fade',
                'chapter_pause': .7, 'camera_motion': 'none', 'cursor_move': .55,
                'cursor_hold': .18, 'cursor_linger': .8, 'progress': True,
                'background': '#17191f', 'surface': '#23262e', 'foreground': '#f8f6f2', 'accent': '#d5ac86'},
    'product': {'transition': .65, 'transition_style': 'slide-up', 'step_transition': 'fade',
                'chapter_pause': .7, 'camera_motion': 'push', 'cursor_move': .65,
                'cursor_hold': .18, 'cursor_linger': .8, 'progress': False,
                'background': '#101720', 'surface': '#263340', 'foreground': '#f5f7fa', 'accent': '#a8cfe4'},
    'promo': {'transition': .5, 'transition_style': 'zoom', 'step_transition': 'slide-left',
              'chapter_pause': .35, 'camera_motion': 'push', 'cursor_move': .48,
              'cursor_hold': .12, 'cursor_linger': .5, 'progress': False,
              'background': '#13121c', 'surface': '#302d43', 'foreground': '#faf7ff', 'accent': '#c9b8ee'},
    'tutorial': {'transition': .3, 'transition_style': 'fade', 'step_transition': 'cut',
                 'chapter_pause': 1., 'camera_motion': 'none', 'cursor_move': .85,
                 'cursor_hold': .3, 'cursor_linger': 2., 'progress': True,
                 'background': '#edf1f5', 'surface': '#d8e0e9', 'foreground': '#1d2c3c', 'accent': '#346780'},
    'cinema': {'transition': .9, 'transition_style': 'focus-dissolve', 'step_transition': 'depth-slide',
               'chapter_pause': .8, 'camera_motion': 'push', 'cursor_move': .72,
               'cursor_hold': .24, 'cursor_linger': 1., 'progress': False,
               'background': '#0c1016', 'surface': '#202832', 'foreground': '#f1f2f4', 'accent': '#a5b4c3'},
    'gallery': {'transition': .9, 'transition_style': 'iris', 'step_transition': 'fade',
                'chapter_pause': .85, 'camera_motion': 'none', 'cursor_move': .8,
                'cursor_hold': .26, 'cursor_linger': 1., 'progress': False,
                'background': '#efebe4', 'surface': '#ddd7cd', 'foreground': '#2d2924', 'accent': '#7f6954'},
    'minimal': {'transition': .75, 'transition_style': 'mask-up', 'step_transition': 'cut',
                'chapter_pause': .65, 'camera_motion': 'none', 'cursor_move': .7,
                'cursor_hold': .22, 'cursor_linger': .8, 'progress': False,
                'background': '#f2f3f1', 'surface': '#dee1dc', 'foreground': '#20241f', 'accent': '#55634f'},
}


def smooth(value):
    value = min(1., max(0., value))
    # Rounded frame times can make the polynomial exceed 1 by a few ulps.
    return min(1., max(0., value ** 3 * (10 + value * (-15 + 6 * value))))


def blend_transition(before, after, progress, kind, background):
    if progress >= 1 or kind == 'cut':
        return after.copy()
    if progress <= 0:
        return before.copy()
    p = smooth(progress)
    w, h = after.size
    if kind == 'fade':
        return Image.blend(before, after, p)
    if kind == 'blur':
        radius = math.sin(math.pi * p) * w / 180
        return Image.blend(before.filter(ImageFilter.GaussianBlur(radius)),
                           after.filter(ImageFilter.GaussianBlur(radius)), p)
    if kind in PREMIUM_TRANSITIONS:
        return premium_transition(before, after, p, kind, background)
    if kind.startswith('slide-'):
        result = background.copy()
        if kind == 'slide-up':
            distance = round(h * p)
            result.paste(before, (0, -distance))
            result.paste(after, (0, h - distance))
        else:
            direction = -1 if kind == 'slide-left' else 1
            distance = round(w * p)
            result.paste(before, (direction * distance, 0))
            result.paste(after, (direction * (distance - w), 0))
        return result
    if kind.startswith('wipe-'):
        # A short feather avoids a hard seam on fine UI text.
        feather = max(1, round(w * .025))
        boundary = p * (w + 2 * feather) - feather
        values = [round(255 * min(1, max(0, (boundary - x) / feather + .5))) for x in range(w)]
        if kind == 'wipe-left':
            values.reverse()
        mask = Image.new('L', (w, 1))
        mask.putdata(values)
        return Image.composite(after, before, mask.resize((w, h)))
    if kind == 'zoom':
        def scaled(image, scale):
            size = (max(1, round(w * scale)), max(1, round(h * scale)))
            layer = background.copy()
            layer.paste(image.resize(size, Image.Resampling.BICUBIC), ((w - size[0]) // 2, (h - size[1]) // 2))
            return layer
        return Image.blend(scaled(before, 1 + .055 * p), scaled(after, .945 + .055 * p), p)
    raise VideoError(f'不支持的转场：{kind}。')


def interaction_for(step, previous, video, duration, transition):
    spec = step.get('interaction')
    if spec is None and 'cursor' not in step:
        return None
    spec = dict(spec or {})
    kind = spec.get('kind', 'click' if step.get('click') else 'move')
    target = spec.get('to', step.get('cursor'))
    previous_spec = previous.get('interaction', {}) if previous else {}
    origin = spec.get('from', previous_spec.get('to', previous.get('cursor') if previous else None))
    if origin is None:
        origin = [max(.02, target[0] - .14), min(.97, target[1] + .16)]
    move, hold, settle = (spec.get('move', video['cursor_move']),
                          spec.get('hold', video['cursor_hold']), spec.get('settle', .12))
    changes_state = kind in ('click', 'drag') and previous is not None
    # Reserve time for the result. Automatic timings compress as a unit; explicit
    # timings must fit, so an authored press can never be silently skipped.
    budget = duration - transition - min(.45, duration * .2)
    if budget < .12:
        raise VideoError('操作步骤过短，无法显示移动、点击和结果；请拉开 steps.at。')
    if move + hold + settle > budget:
        if any(key in spec for key in ('move', 'hold', 'settle')):
            raise VideoError('interaction 时间超过本步骤可用时长；请缩短操作或拉开 steps.at。')
        ratio = budget / (move + hold + settle)
        move, hold, settle = move * ratio, hold * ratio, settle * ratio
    press = hold if kind == 'drag' else move + hold
    release = hold + move if kind == 'drag' else press + min(.09, settle)
    reveal = move + hold + settle if changes_state else 0.
    return {'kind': kind, 'from': origin, 'to': target, 'move': move, 'hold': hold,
            'press': press, 'release': release, 'reveal': reveal,
            'linger': spec.get('linger', video['cursor_linger']), 'changes_state': changes_state}


def pointer_position(track, elapsed, reduced_motion=False):
    start = track['hold'] if track['kind'] == 'drag' else 0
    p = smooth((elapsed - start) / track['move'])
    if reduced_motion:
        p = float(elapsed >= start + track['move'])
    a, b = track['from'], track['to']
    dx, dy = b[0] - a[0], b[1] - a[1]
    bend = 0 if track['kind'] == 'drag' else .12 * math.sin(math.pi * p)
    return (min(1, max(0, a[0] + dx * p - dy * bend)),
            min(1, max(0, a[1] + dy * p + dx * bend)))


def camera_rect(rect, camera, progress, push=False):
    x, y, w, h = rect
    p = smooth(progress)
    zoom = 1 + (camera.get('zoom', 1) - 1) * p
    if zoom == 1 and push:
        zoom = .985 + .015 * p
    cx, cy = camera.get('center', [.5, .5])
    nw, nh = w * zoom, h * zoom
    # Zoom about the requested subject, clamped so no empty edge is exposed.
    nx = min(x, max(x + w - nw, x + w / 2 - cx * nw)) if zoom >= 1 else x + (w - nw) / 2
    ny = min(y, max(y + h - nh, y + h / 2 - cy * nh)) if zoom >= 1 else y + (h - nh) / 2
    return nx, ny, nw, nh
