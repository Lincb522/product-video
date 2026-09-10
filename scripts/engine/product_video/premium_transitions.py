"""Restrained depth, aperture and optical transitions on the existing frame canvas."""
import math

from PIL import Image, ImageDraw, ImageFilter


PREMIUM_TRANSITIONS = ('focus-dissolve', 'depth-slide', 'mask-up',
                       'iris', 'split-reveal', 'glass-sweep')


def _place(image, background, scale=1., dx=0., dy=0.):
    w, h = image.size
    layer = image.convert('RGBA').transform(image.size, Image.Transform.AFFINE,
        (1 / scale, 0, (w / 2 * (scale - 1) - dx) / scale,
         0, 1 / scale, (h / 2 * (scale - 1) - dy) / scale), Image.Resampling.BICUBIC)
    result = background.copy()
    result.paste(layer, (0, 0), layer)
    return result


def _reveal_mask(size, progress, vertical=False, reverse=False):
    w, h = size
    length = h if vertical else w
    feather = max(1, length * .025)
    edge = progress * (length + 2 * feather) - feather
    values = [round(255 * min(1, max(0, (edge - x) / feather + .5))) for x in range(length)]
    if reverse:
        values.reverse()
    strip = Image.new('L', (1, h) if vertical else (w, 1))
    strip.putdata(values)
    return strip.resize(size)


def premium_transition(before, after, progress, kind, background):
    # The public dispatcher supplies eased progress and exact original end frames.
    p = progress
    w, h = after.size
    if kind == 'focus-dissolve':
        outgoing = _place(before, background, 1 - .018 * p).filter(
            ImageFilter.GaussianBlur(w * .006 * p ** 1.5))
        incoming = _place(after, background, 1 + .038 * (1 - p)).filter(
            ImageFilter.GaussianBlur(w * .005 * (1 - p) ** 1.5))
        return Image.blend(outgoing, incoming, p)
    if kind == 'depth-slide':
        outgoing = _place(before, background, 1 - .07 * p, -w * .045 * p).filter(
            ImageFilter.GaussianBlur(w * .002 * p))
        incoming = _place(after, background, 1 + .04 * (1 - p), w * .12 * (1 - p), h * .018 * (1 - p))
        return Image.blend(outgoing, incoming, p)
    if kind == 'mask-up':
        incoming = _place(after, background, 1., 0., h * .055 * (1 - p))
        return Image.composite(incoming, before, _reveal_mask(after.size, p, vertical=True, reverse=True))
    if kind == 'iris':
        mask = Image.new('L', after.size)
        x, y = (w / 2 + 1) * (1 - p) - 1, (h / 2 + 1) * (1 - p) - 1
        radius = min(w * .04 * (1 - p), max(0, h / 2 - y))
        ImageDraw.Draw(mask).rounded_rectangle((x, y, w - x, h - y), radius=radius, fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(max(.1, w * .001 * (1 - p))))
        incoming = _place(after, background, 1 + .025 * (1 - p))
        return Image.composite(incoming, before, mask)
    if kind == 'split-reveal':
        result = _place(after, background, 1 + .025 * (1 - p))
        center = w // 2
        distance = round((w - center) * p)
        result.paste(before.crop((0, 0, center, h)), (-distance, 0))
        result.paste(before.crop((center, 0, w, h)), (center + distance, 0))
        return result
    if kind == 'glass-sweep':
        result = Image.composite(after, before, _reveal_mask(after.size, p))
        edge = w * p
        band = max(1., w * .048)
        strength = math.sin(math.pi * p)
        strip = Image.new('L', (w, 1))
        strip.putdata([round(180 * strength * math.exp(-((x - edge) / band) ** 2)) for x in range(w)])
        refraction = _place(result, background, 1.002, w * .004 * (1 - p)).filter(
            ImageFilter.GaussianBlur(w * .0015))
        refraction = Image.blend(refraction, Image.new('RGB', after.size, '#ffffff'), .035)
        return Image.composite(refraction, result, strip.resize(after.size))
    raise ValueError(f'Unknown premium transition: {kind}')
