"""Measured text layouts independent of narration, screenshots, and subtitle cues."""
from functools import lru_cache
import re

from PIL import ImageColor, ImageDraw, ImageFont

from .common import VideoError
from .motion import smooth


@lru_cache(maxsize=64)
def font(path, size):
    return ImageFont.truetype(path, size)


def wrap_text(value, face, width):
    lines = []
    for paragraph in value.split('\n'):
        line = ''
        tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9'’./:_-]*|[^\S\n]+|[^\s]", paragraph)
        for token in tokens:
            if not line:
                token = token.lstrip()
            if face.getlength(line + token) <= width:
                line += token
                continue
            if line.strip():
                lines.append(line.rstrip())
                line = ''
            token = token.lstrip()
            for char in token:
                if line and face.getlength(line + char) > width:
                    lines.append(line)
                    line = ''
                line += char
        lines.append(line.rstrip())
    return lines


def content_layout(content, video):
    """Fail before synthesis if the complete authored copy cannot fit safely."""
    scale = video['width'] / 1920
    px = lambda value: round(value * scale)
    split = content['layout'] == 'split'
    x, width = (112, 760) if split else (144, 1632)
    if split and content.get('image_side', 'right') == 'left':
        x = 1048
    groups = []
    if content.get('eyebrow'):
        groups.append((content['eyebrow'], 24, 24, 30, video['accent']))
    groups.append((content['headline'], 64 if split else 92, 48 if split else 64, 30, video['foreground']))
    if content.get('body'):
        groups.append((content['body'], 34 if split else 38, 28 if split else 32, 0, video['foreground']))
    if content.get('bullets'):
        for index, item in enumerate(content['bullets'], 1):
            groups.append((f'{index:02d}  {item}', 38, 32, 24, video['foreground']))
    # Shrink within an explicit readable range; never elide authored content.
    for reduction in range(0, 31, 2):
        blocks, y = [], 0
        for value, maximum, minimum, gap, color in groups:
            size = max(minimum, maximum - reduction)
            face = font(video['font'], max(10, px(size)))
            lines = wrap_text(value, face, px(width))
            line_height = max(round(face.size * 1.28), sum(face.getmetrics()))
            height = line_height * len(lines)
            blocks.append({'text': value, 'lines': lines, 'font_size': face.size,
                           'line_height': line_height, 'x': px(x), 'y': y,
                           'width': px(width), 'height': height, 'color': color})
            y += height + px(gap)
        height = y - px(groups[-1][3])
        if height <= px(628):
            top = px(228) + (px(628) - height) // 2
            for block in blocks:
                block['y'] += top
            return blocks
    raise VideoError('画面文案过长，无法完整放入正文区；请拆成多个 steps 或章节，不要塞进字幕。')


def paint_content(image, content, blocks, progress, reduced_motion, font_path):
    animated = content.get('animation', 'reveal') == 'reveal' and not reduced_motion
    draw = ImageDraw.Draw(image, 'RGBA')
    scale = image.width / 1920
    total = .45 + .09 * (len(blocks) - 1)
    for index, block in enumerate(blocks):
        p = smooth((progress * total - .09 * index) / .45) if animated else 1.
        if p <= 0:
            continue
        color = (*ImageColor.getrgb(block['color'])[:3], round(255 * p))
        y = block['y'] + round(18 * scale * (1 - p))
        face = font(font_path, block['font_size'])
        for line in block['lines']:
            draw.text((block['x'], y), line, font=face, fill=color, anchor='lt')
            y += block['line_height']
    return image
