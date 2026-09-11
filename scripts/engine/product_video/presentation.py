"""Distinct two-dimensional compositions, surface treatments and entrance motion."""
from PIL import Image, ImageColor, ImageDraw, ImageFilter

from .common import VideoError
from .motion import smooth
from .text_scenes import wrap_text


class Presentation:
    def __init__(self, renderer):
        self.r = renderer
        self.v = renderer.v
        self.style = self.v['style']

    def color(self, first, second, mix):
        a, b = (ImageColor.getrgb(self.v.get(c, c))[:3] for c in (first, second))
        return tuple(round(x + (y - x) * mix) for x, y in zip(a, b))

    def boxes(self, count):
        bounds = {
            'product': (492, 172, 1352, 738),
            'promo': (168, 264, 1616, 650),
            'tutorial': (468, 174, 1380, 718),
            'cinema': (104, 124, 1712, 716),
            'gallery': (304, 180, 1312, 656),
            'minimal': (176, 274, 1568, 578),
        }
        if self.style == 'gallery' and count == 2:
            return [(120, 182, 800, 630), (1000, 224, 800, 630)]
        x, y, width, height = bounds[self.style]
        gap = 48 if self.style in ('gallery', 'minimal') else 32
        width = (width - gap * (count - 1)) / count
        return [(x + i * (width + gap), y, width, height) for i in range(count)]

    def background(self):
        r = self.r
        image = Image.new('RGB', (r.w, r.h), self.v['background'])
        d = ImageDraw.Draw(image)
        if self.style == 'product':
            d.line(tuple(r.px(v) for v in (424, 174, 424, 916)), fill=self.color('surface', 'background', .35), width=max(1, r.px(2)))
        elif self.style == 'promo':
            d.rectangle(tuple(r.px(v) for v in (0, 0, 1920, 208)), fill=self.v['surface'])
            d.rectangle(tuple(r.px(v) for v in (64, 288, 80, 858)), fill=self.v['accent'])
        elif self.style == 'tutorial':
            d.rectangle(tuple(r.px(v) for v in (0, 138, 412, 956)), fill=self.color('background', 'surface', .6))
        elif self.style == 'cinema':
            for y in range(r.h):
                p = max(0., 1 - abs(y / r.h - .46) / .5)
                d.line((0, y, r.w, y), fill=self.color('background', 'surface', p * .55))
            d.rectangle((0, 0, r.w, r.px(22)), fill=self.color('background', '#000000', .65))
            d.rectangle((0, r.h-r.px(22), r.w, r.h), fill=self.color('background', '#000000', .65))
        elif self.style == 'gallery':
            d.line(tuple(r.px(v) for v in (96, 130, 1824, 130)), fill=self.v['surface'], width=max(1, r.px(2)))
        elif self.style == 'minimal':
            d.line(tuple(r.px(v) for v in (96, 208, 1824, 208)), fill=self.v['surface'], width=max(1, r.px(2)))
        return image

    def surface(self, rects, content=False):
        r = self.r
        image = Image.new('RGB', (r.w, r.h), self.v['background']) if content and self.style in ('product', 'tutorial') else r.base.copy()
        shadow = Image.new('RGBA', image.size)
        d = ImageDraw.Draw(shadow)
        floating = self.style in ('product', 'cinema', 'gallery')
        for x, y, w, h in rects:
            pad = r.px(24) if self.style == 'gallery' else 0
            if floating:
                offset = r.px(24 if self.style != 'gallery' else 14)
                d.rectangle((x-pad, y-pad+offset, x+w+pad, y+h+pad+offset), fill=(0, 0, 0, 90 if self.style != 'cinema' else 140))
        if floating:
            image = Image.alpha_composite(image.convert('RGBA'), shadow.filter(ImageFilter.GaussianBlur(r.px(24)))).convert('RGB')
        d = ImageDraw.Draw(image)
        for x, y, w, h in rects:
            if self.style == 'promo':
                offset = r.px(18)
                d.rectangle((x+offset, y+offset, x+w+offset, y+h+offset), fill=self.v['accent'])
            elif self.style == 'gallery':
                pad = r.px(24)
                d.rectangle((x-pad, y-pad, x+w+pad, y+h+pad), fill=self.color('background', '#ffffff', .7))
            elif self.style == 'tutorial':
                pad = r.px(10)
                d.rectangle((x-pad, y-pad, x+w+pad, y+h+pad), fill=self.v['surface'])
        return image

    def progress(self, elapsed, duration):
        if self.v['reduced_motion'] or self.style == 'tutorial':
            return 1.
        length = {'product': .9, 'promo': .65, 'cinema': 1.4, 'gallery': 1., 'minimal': .75}[self.style]
        return min(1., max(0., elapsed) / max(.1, min(length, duration * .3)))

    def place(self, rects, progress):
        p = smooth(progress)
        if p >= 1 or self.style in ('tutorial', 'minimal'):
            return tuple(rects)
        scale, dx, dy = {
            'product': (.96 + .04*p, 0, 54*(1-p)),
            'promo': (.90 + .10*p, 122*(1-p), 0),
            'cinema': (.92 + .08*p, 0, 0),
            'gallery': (.98 + .02*p, 0, 34*(1-p)),
        }[self.style]
        return tuple((round(x + w*(1-scale)/2 + self.r.px(dx)),
                      round(y + h*(1-scale)/2 + self.r.px(dy)),
                      max(1, round(w*scale)), max(1, round(h*scale))) for x, y, w, h in rects)

    def heading(self, image, value, box, size, color=None):
        r = self.r
        x, y, width, height = (r.px(v) for v in box)
        for candidate in range(size, 23, -2):
            face = r.font(candidate)
            lines = wrap_text(value, face, width)
            if len(lines) > 1 and len(lines[-1].strip()) == 1:
                continue
            line_height = max(round(face.size * 1.25), sum(face.getmetrics()))
            if len(lines) * line_height <= height:
                d = ImageDraw.Draw(image)
                for line in lines:
                    d.text((x, y), line, font=face, fill=color or self.v['foreground'], anchor='lt')
                    y += line_height
                return
        raise VideoError('章节标题无法完整放入当前风格的标题区，请缩短标题。')

    def chrome(self, image, ci, si):
        r, style = self.r, self.style
        chapter, step = r.chapters[ci], r.chapters[ci]['steps'][si]
        d = ImageDraw.Draw(image)
        left = 96
        logo = r.config['product'].get('logo')
        if logo:
            from PIL import ImageOps
            icon = ImageOps.contain(r.source(logo), (r.px(32), r.px(32)))
            image.paste(icon, (r.px(left), r.px(36)), icon)
            left += 46
        r.label(d, r.config['product']['name'], (left, 52), 23, 1200-left, self.v['accent'], 'lm')
        r.label(d, r.narration_label, (1824, 52), 18, 220, self.v['accent'], 'rm')
        # Authored text owns the center and split regions, so keep the chapter heading compact.
        if 'content' in step:
            r.label(d, chapter['title'], (96, 108), 28, 1680, anchor='lm')
        elif style == 'product':
            r.label(d, f'{ci+1:02d}', (64, 210), 26, 320, self.v['accent'], 'lm')
            self.heading(image, chapter['title'], (64, 272, 316, 360), 64)
            if step['labels'] and step['labels'][0]:
                self.heading(image, step['labels'][0], (64, 760, 316, 128), 28, self.v['accent'])
        elif style == 'promo':
            self.heading(image, chapter['title'], (96, 94, 1700, 110), 82)
        elif style == 'tutorial':
            r.label(d, chapter['title'], (468, 108), 40, 1370, anchor='lm')
            r.label(d, '操作步骤', (64, 192), 23, 290, self.v['accent'], 'lm')
            first = max(0, min(si-2, len(chapter['steps'])-5))
            for index in range(first, min(len(chapter['steps']), first+5)):
                item = chapter['steps'][index]
                label = next((v for v in item['labels'] if v), f'画面 {index+1}')
                y = 254 + (index-first)*124
                active = index == si
                if active:
                    d.rounded_rectangle(tuple(r.px(v) for v in (40, y-18, 384, y+86)), radius=r.px(8), fill=self.v['surface'])
                    d.rectangle(tuple(r.px(v) for v in (40, y-18, 44, y+86)), fill=self.v['accent'])
                r.label(d, f'{index+1:02d}', (64, y+15), 24, 44, self.v['accent'], 'lm')
                self.heading(image, label, (126, y, 228, 86), 28)
        elif style == 'cinema':
            r.label(d, chapter['title'], (104, 908), 48, 1340, anchor='lm')
        elif style == 'gallery':
            r.label(d, chapter['title'], (960, 98), 38, 1480, anchor='mm')
        elif style == 'minimal':
            self.heading(image, chapter['title'], (96, 108, 1728, 100), 64)
        rects = r.layout(ci, si)
        for label, (x, y, w, h) in zip(step['labels'], rects):
            if not label or (style in ('product', 'tutorial') and len(rects) == 1 and 'content' not in step):
                continue
            baseline = min(950, (y+h)/r.scale + (48 if style == 'gallery' else 34))
            if style == 'cinema' and 'content' not in step:
                baseline = 948
            r.label(d, label, ((x+w/2)/r.scale, baseline), 21, w/r.scale, self.v['accent'], 'mm')
        return image
