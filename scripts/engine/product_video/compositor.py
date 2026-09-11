"""Compose real screenshots, camera transforms and an independent pointer layer."""
from functools import lru_cache

from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps

from .common import VideoError
from .motion import blend_transition, camera_rect, interaction_for, pointer_position, smooth
from .presentation import Presentation
from .text_scenes import content_layout, paint_content


def fit_rect(size, box):
    x, y, w, h = box
    scale = min(w / size[0], h / size[1])
    width, height = round(size[0] * scale), round(size[1] * scale)
    return round(x + (w - width) / 2), round(y + (h - height) / 2), width, height


class Renderer:
    def __init__(self, config, chapters, narration_label='AI 配音'):
        self.config, self.chapters = config, chapters
        self.narration_label = narration_label
        self.v = config['video']
        self.w, self.h = self.v['width'], self.v['height']
        self.scale = self.w / 1920
        self.total = chapters[-1]['end']
        self.studio = None
        self.classic = self.v['style'] == 'classic'
        self.presentation = None if self.classic else Presentation(self)
        self.base = self.background()
        self.content = {(ci, si): content_layout(step['content'], self.v)
                        for ci, chapter in enumerate(chapters) for si, step in enumerate(chapter['steps'])
                        if 'content' in step}
        self.tracks, self.transitions, self.durations = {}, {}, {}
        for ci, chapter in enumerate(chapters):
            for si, step in enumerate(chapter['steps']):
                end = chapter['steps'][si + 1]['at'] if si + 1 < len(chapter['steps']) else 1
                duration = (end - step['at']) * chapter['audio_duration']
                is_action = step.get('click') or step.get('interaction', {}).get('kind') in ('click', 'drag')
                kind = step.get('transition', 'fade' if is_action else self.v['step_transition'])
                if self.v['reduced_motion']:
                    kind = 'cut'
                cap = .28 if is_action else .45 if self.classic else .65
                transition = min(step.get('transition_duration', min(self.v['transition'], cap)), duration * .3)
                if kind == 'cut':
                    transition = 0.
                self.transitions[ci, si] = kind, transition
                self.durations[ci, si] = duration
                self.tracks[ci, si] = interaction_for(step, chapter['steps'][si - 1] if si else None,
                                                      self.v, duration, transition)

    def background(self):
        self.base = Image.new('RGB', (self.w, self.h), self.v['background'])
        if self.classic:
            draw = ImageDraw.Draw(self.base)
            bg, surface = (ImageColor.getrgb(self.v[key]) for key in ('background', 'surface'))
            for y in range(self.h):
                mix = .35 * (1 - y / self.h)
                color = tuple(round(a * (1 - mix) + b * mix) for a, b in zip(bg, surface))
                draw.line((0, y, self.w, y), fill=color)
            return self.base
        return self.presentation.background()

    def px(self, value):
        return round(value * self.scale)

    @lru_cache(maxsize=24)
    def font(self, size):
        return ImageFont.truetype(self.v['font'], max(10, self.px(size)))

    def label(self, draw, value, xy, size, width, color=None, anchor='la'):
        font = self.font(size)
        while draw.textlength(value, font=font) > self.px(width) and size > 18:
            size -= 1
            font = self.font(size)
        if draw.textlength(value, font=font) > self.px(width):
            raise VideoError('标题或标签过长，无法完整放入画面，请缩短该文字。')
        draw.text(tuple(self.px(a) for a in xy), value, font=font,
                  fill=color or self.v['foreground'], anchor=anchor)

    @lru_cache(maxsize=12)
    def source(self, path):
        with Image.open(path) as source:
            return ImageOps.exif_transpose(source).convert('RGBA')

    @lru_cache(maxsize=12)
    def layout(self, ci, si):
        step = self.chapters[ci]['steps'][si]
        images = step['images']
        if not images:
            return []
        if step.get('content', {}).get('layout') == 'split':
            x = 104 if step['content'].get('image_side', 'right') == 'left' else 960
            return [fit_rect(self.source(images[0]).size, tuple(self.px(v) for v in (x, 216, 856, 654)))]
        if not self.classic:
            return [fit_rect(self.source(path).size, tuple(self.px(v) for v in box))
                    for path, box in zip(images, self.presentation.boxes(len(images)))]
        x, y, total, height, gap = (72, 158, 1776, 730, 30)
        width = (total - gap * (len(images) - 1)) / len(images)
        return [fit_rect(self.source(path).size, tuple(self.px(v) for v in
                (x + i * (width + gap), y, width, height))) for i, path in enumerate(images)]

    @lru_cache(maxsize=12)
    def stage(self, ci, si):
        image = self.base.copy()
        if self.classic:
            return image
        return self.presentation.surface(self.layout(ci, si), 'content' in self.chapters[ci]['steps'][si])

    @lru_cache(maxsize=12)
    def step_frame(self, chapter_index, step_index):
        return self.shot(chapter_index, step_index, {}, 1, False)

    def close(self):
        if self.studio is not None:
            self.studio.close()
            self.studio = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def shot(self, ci, si, camera, progress, push, text_progress=1., elapsed=None, entrance=1.):
        step = self.chapters[ci]['steps'][si]
        if 'scene3d' in step:
            if self.studio is None:
                from .studio3d import Studio3D
                self.studio = Studio3D(self.v)
            duration = self.durations[ci, si]
            elapsed = duration if elapsed is None else elapsed
            region = None
            if 'content' in step:
                x = 64 if step['content'].get('image_side', 'right') == 'left' else 950
                region = [self.px(v) for v in (x, 110, 906, 830)]
            image = self.studio.frame(f'{ci}:{si}', step['scene3d'], elapsed, elapsed / max(.001, duration), region)
            if (ci, si) in self.content:
                paint_content(image, step['content'], self.content[ci, si], text_progress,
                              self.v['reduced_motion'], self.v['font'])
            return image, []
        rects = tuple(self.layout(ci, si))
        if not self.classic:
            rects = self.presentation.place(rects, entrance)
        views = tuple(camera_rect(rect, camera if len(rects) == 1 else {}, progress,
                                  push and len(rects) == 1) for rect in rects)
        reveal = smooth(entrance) if self.v['style'] == 'minimal' else 1.
        image = self.composed_shot(ci, si, views, rects, reveal).copy()
        if (ci, si) in self.content:
            paint_content(image, self.chapters[ci]['steps'][si]['content'], self.content[ci, si],
                          text_progress, self.v['reduced_motion'], self.v['font'])
        return image, list(views)

    @lru_cache(maxsize=6)
    def composed_shot(self, ci, si, views, rects, reveal=1.):
        step = self.chapters[ci]['steps'][si]
        image = self.stage(ci, si).copy() if self.classic or rects == tuple(self.layout(ci, si)) else self.presentation.surface(rects, 'content' in step)
        for path, rect, view in zip(step['images'], rects, views):
            x, y, w, h = rect
            vx, vy, vw, vh = view
            source = self.source(path)
            if view == rect:
                content = source.resize((w, h), Image.Resampling.LANCZOS)
            else:
                sx, sy = source.width / vw, source.height / vh
                content = source.transform((w, h), Image.Transform.AFFINE,
                    (sx, 0, (x - vx) * sx, 0, sy, (y - vy) * sy), Image.Resampling.BICUBIC)
            d = ImageDraw.Draw(image)
            if self.classic:
                d.rounded_rectangle((x - self.px(1), y - self.px(1), x + w + self.px(1), y + h + self.px(1)),
                                    radius=self.px(12), outline=self.v['surface'], width=self.px(2))
            if reveal < 1:
                visible = round(h * reveal)
                if visible:
                    strip = content.crop((0, h-visible, w, h))
                    image.paste(strip, (x, y+h-visible), strip)
            else:
                image.paste(content, (x, y), content)
            if not self.classic and self.v['style'] not in ('minimal', 'promo', 'gallery'):
                d.rounded_rectangle((x - 1, y - 1, x + w, y + h), radius=self.px(8),
                                    outline=self.v['surface'], width=max(1, self.px(2)))
        return image

    def camera(self, ci, si, elapsed, reveal, action):
        if self.v['reduced_motion']:
            return {}, 1, False
        step = self.chapters[ci]['steps'][si]
        duration = self.durations[ci, si]
        previous = self.chapters[ci]['steps'][si - 1] if si else {}
        target = step.get('camera', {})
        if action and si:
            prior = previous.get('camera', {})
            p = smooth(max(0, elapsed - reveal) / min(.9, max(.1, duration - reveal)))
            a, b = prior.get('center', [.5, .5]), target.get('center', [.5, .5])
            camera = {'zoom': prior.get('zoom', 1) + (target.get('zoom', 1) - prior.get('zoom', 1)) * p,
                      'center': [a[i] + (b[i] - a[i]) * p for i in range(2)]}
            return camera, 1, False
        return target, min(1, max(0, elapsed) / max(.1, min(duration * .65, 1.5))), self.v['camera_motion'] == 'push' and not target

    def chrome(self, image, ci, si):
        if 'scene3d' in self.chapters[ci]['steps'][si]:
            return image
        if self.classic:
            return self.classic_chrome(image, ci, si)
        return self.presentation.chrome(image, ci, si)

    def classic_chrome(self, image, ci, si):
        draw = ImageDraw.Draw(image)
        chapter, product = self.chapters[ci], self.config['product']
        left = 72
        if product.get('logo'):
            logo = ImageOps.contain(self.source(product['logo']), (self.px(48), self.px(48)))
            image.paste(logo, (self.px(72), self.px(57)), logo)
            left = 138
        self.label(draw, product['name'], (left, 82), 32, 530 - left, anchor='lm')
        self.label(draw, chapter['title'], (960, 82), 34, 680, anchor='mm')
        self.label(draw, self.narration_label, (1848, 82), 20, 150, self.v['accent'], 'rm')
        step = chapter['steps'][si]
        count = len(step['images'])
        width = (1776 - 30 * (count - 1)) / count if count else 0
        for i, (label, rect) in enumerate(zip(step['labels'], self.layout(ci, si))):
            if label:
                center = (rect[0] + rect[2] / 2) / self.scale if 'content' in step else 72 + i * (width + 30) + width / 2
                self.label(draw, label, (center, 930), 24, rect[2] / self.scale if 'content' in step else width,
                           self.v['accent'], 'mm')
        if any(self.tracks[ci, i] for i in range(len(chapter['steps']))):
            self.label(draw, '操作演示', (1848, 122), 18, 150, self.v['accent'], 'rm')
        return image

    def blend(self, before, after, progress, kind):
        if self.classic and kind == 'fade':
            p = min(1., max(0., progress))
            return Image.blend(before, after, p * p * (3 - 2 * p))
        return blend_transition(before, after, progress, kind, self.base)

    def pointer(self, image, track, elapsed, view, clip):
        position = pointer_position(track, elapsed, self.v['reduced_motion'])
        x, y, w, h = view
        cx, cy = x + w * position[0], y + h * position[1]
        rx, ry, rw, rh = clip
        if not (rx <= cx <= rx + rw and ry <= cy <= ry + rh):
            return
        ending = max(track['reveal'], track['release']) + track['linger']
        alpha = smooth(elapsed / .12) * (1 - smooth((elapsed - ending) / .22))
        if alpha <= 0:
            return
        # Supersample only the small pointer sprite, preserving crisp screenshot text.
        size, factor = max(72, self.px(130)), 3
        sprite = Image.new('RGBA', (size * factor, size * factor))
        d = ImageDraw.Draw(sprite)
        center = size * factor / 2
        unit = self.scale * factor
        pressed = track['kind'] in ('click', 'drag') and track['press'] <= elapsed < track['release']
        age = elapsed - (track['release'] if track['kind'] == 'drag' else track['press'])
        if track['kind'] != 'move' and 0 <= age < .5:
            p = age / .5
            radius = (10 + 23 * smooth(p)) * unit
            color = ImageColor.getrgb(self.v['accent'])[:3]
            d.ellipse((center - radius, center - radius, center + radius, center + radius),
                      outline=(*color, round(210 * (1 - p))), width=max(1, round(2 * unit)))
        if pressed:
            r = 14 * unit
            d.ellipse((center - r, center - r, center + r, center + r),
                      fill=(*ImageColor.getrgb(self.v['accent'])[:3], 75))
        scale = unit * (.9 if pressed else 1)
        points = [(center + dx * scale, center + dy * scale) for dx, dy in
                  [(0, 0), (1, 27), (8, 20), (14, 33), (20, 30), (14, 18), (24, 17)]]
        d.polygon([(x + unit, y + 2 * unit) for x, y in points], fill=(0, 0, 0, 70))
        d.polygon(points, fill='#fffefa', outline='#17212b', width=max(1, round(1.4 * unit)))
        sprite = sprite.resize((size, size), Image.Resampling.LANCZOS)
        sprite.putalpha(sprite.getchannel('A').point(lambda a: round(a * alpha)))
        image.paste(sprite, (round(cx - size / 2), round(cy - size / 2)), sprite)

    def scene(self, ci, local_time):
        chapter = self.chapters[ci]
        elapsed_audio = max(0, local_time - chapter['lead'])
        fraction = min(1, elapsed_audio / chapter['audio_duration'])
        si = max(i for i, s in enumerate(chapter['steps']) if s['at'] <= fraction)
        step = chapter['steps'][si]
        elapsed = elapsed_audio - step['at'] * chapter['audio_duration']
        track = self.tracks[ci, si]
        reveal = track['reveal'] if track else 0
        action = bool(track and track['changes_state'])
        shown = si - 1 if action and elapsed < reveal else si
        camera, progress, push = self.camera(ci, si, elapsed, reveal, action)
        text_progress = 1. if shown != si else max(0, elapsed - reveal) / min(.85, self.durations[ci, si] * .35)
        entrance = 1.
        if not self.classic and not track and not step.get('camera') and 'content' not in step:
            entrance = self.presentation.progress(elapsed, self.durations[ci, si])
        image, views = self.shot(ci, shown, camera, progress, push, text_progress, elapsed=elapsed, entrance=entrance)
        if self.classic:
            image = self.chrome(image, ci, shown)
        kind, duration = self.transitions[ci, si]
        since = elapsed - reveal
        if si and duration > 0 and 0 <= since < duration:
            before_step = chapter['steps'][si - 1]
            before, _ = self.shot(ci, si - 1, before_step.get('camera', {}), 1, False)
            if self.classic:
                before = self.chrome(before, ci, si - 1)
            image = self.blend(before, image, since / duration, kind)
        if track:
            self.pointer(image, track, elapsed, views[0], self.layout(ci, shown)[0])
        return image if self.classic else self.chrome(image, ci, shown)

    def frame(self, time_value):
        time_value = min(self.total, max(0, time_value))
        ci = next((i for i, c in enumerate(self.chapters) if c['start'] <= time_value < c['end']), len(self.chapters) - 1)
        chapter = self.chapters[ci]
        local_time = time_value - chapter['start']
        image = self.scene(ci, local_time)
        duration = min(chapter.get('transition_duration', self.v['transition']), chapter['lead'])
        kind = chapter.get('transition', self.v['transition_style'])
        if ci and duration > 0 and local_time < duration and not self.v['reduced_motion']:
            previous = self.chapters[ci - 1]
            before = self.scene(ci - 1, previous['end'] - previous['start'])
            image = self.blend(before, image, local_time / duration, kind)
        draw = ImageDraw.Draw(image)
        cue = next((c for c in chapter['cues'] if c['start'] <= time_value < c['end']), None)
        if cue:
            font = self.font(32)
            lines, line = [], ''
            for c in cue['text']:
                if line and draw.textlength(line + c, font=font) > self.px(1600):
                    lines.append(line)
                    line = ''
                line += c
            if line:
                lines.append(line)
            if len(lines) > 2:
                raise VideoError('字幕超过两行，请缩短单句或增加字幕分段。')
            width = max(draw.textlength(s, font=font) for s in lines) + self.px(48)
            spacing = 46 if self.classic else 42
            center_y = self.px(992 if self.classic else 1010)
            height = self.px(spacing * len(lines) + 12)
            draw.rounded_rectangle((self.w / 2 - width / 2, center_y - height / 2,
                                    self.w / 2 + width / 2, center_y + height / 2),
                                   radius=self.px(14 if self.classic else 12), fill=self.v['surface'])
            for i, line in enumerate(lines):
                draw.text((self.w / 2, center_y + self.px((i - (len(lines) - 1) / 2) * spacing)),
                          line, font=font, fill=self.v['foreground'], anchor='mm')
        if self.v['progress']:
            draw.rectangle((0, self.h - max(1, self.px(3)), round(self.w * time_value / self.total), self.h), fill=self.v['accent'])
        return image

    def review_times(self, ci, si):
        chapter = self.chapters[ci]
        start = chapter['start'] + chapter['lead'] + chapter['steps'][si]['at'] * chapter['audio_duration']
        duration = self.durations[ci, si]
        track = self.tracks[ci, si]
        samples = {'settled': duration * .85}
        if 'scene3d' in chapter['steps'][si]:
            samples.update(start=0, middle=duration * .5, end=duration)
        elif not self.classic and chapter['steps'][si]['images'] and not track and 'content' not in chapter['steps'][si]:
            samples['entrance'] = min(.3, duration * .15)
        if (ci, si) in self.content:
            samples['text-reveal'] = min(.85, duration * .35) * .5
        if track:
            samples.update(move=track['move'] * .5, press=track['press'],
                           result=track['reveal'] + self.transitions[ci, si][1] + .08)
        if si and self.transitions[ci, si][1]:
            samples['transition'] = (track['reveal'] if track else 0) + self.transitions[ci, si][1] / 2
        times = {label: start + min(max(0, t), max(0, duration - 1 / self.v['fps'])) for label, t in samples.items()}
        if si == 0 and ci and chapter['lead']:
            times['chapter-transition'] = chapter['start'] + min(chapter['lead'], chapter.get('transition_duration', self.v['transition'])) / 2
        return times
