from functools import lru_cache
import math
from pathlib import Path
import selectors
import os
import subprocess
import tempfile
import time

from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps

from .common import VideoError


def smooth(value):
    value = min(1, max(0, value))
    return value * value * (3 - 2 * value)


def fit_rect(size, box):
    x, y, w, h = box
    scale = min(w / size[0], h / size[1])
    width, height = round(size[0] * scale), round(size[1] * scale)
    return (round(x + (w - width) / 2), round(y + (h - height) / 2), width, height)


class Renderer:
    def __init__(self, config, chapters):
        self.config, self.chapters = config, chapters
        self.v = config["video"]
        self.w, self.h = self.v["width"], self.v["height"]
        self.scale = self.w / 1920
        self.total = chapters[-1]["end"]
        self.base = Image.new("RGB", (self.w, self.h))
        draw = ImageDraw.Draw(self.base)
        bg, surface = ImageColor.getrgb(self.v["background"]), ImageColor.getrgb(self.v["surface"])
        for y in range(self.h):
            mix = 0.35 * (1 - y / self.h)
            color = tuple(round(a * (1 - mix) + b * mix) for a, b in zip(bg, surface))
            draw.line((0, y, self.w, y), fill=color)

    def px(self, value):
        return round(value * self.scale)

    @lru_cache(maxsize=20)
    def font(self, size):
        return ImageFont.truetype(self.v["font"], max(10, self.px(size)))

    def label(self, draw, value, xy, size, width, color=None, anchor="la"):
        # Titles remain complete; oversized copy fails rather than being silently clipped.
        font = self.font(size)
        while draw.textlength(value, font=font) > self.px(width) and size > 18:
            size -= 1
            font = self.font(size)
        if draw.textlength(value, font=font) > self.px(width):
            raise VideoError("标题或标签过长，无法完整放入画面，请缩短该文字。")
        draw.text(tuple(self.px(a) for a in xy), value, font=font,
                  fill=color or self.v["foreground"], anchor=anchor)

    @lru_cache(maxsize=12)
    def step_frame(self, chapter_index, step_index):
        chapter = self.chapters[chapter_index]
        step = chapter["steps"][step_index]
        image = self.base.copy()
        draw = ImageDraw.Draw(image)
        product = self.config["product"]
        left = 72
        if product.get("logo"):
            with Image.open(product["logo"]) as logo:
                logo = ImageOps.contain(logo.convert("RGBA"), (self.px(48), self.px(48)))
                image.paste(logo, (self.px(72), self.px(57)), logo)
            left = 138
        self.label(draw, product["name"], (left, 82), 32, 530 - left, anchor="lm")
        self.label(draw, chapter["title"], (960, 82), 34, 680, anchor="mm")
        self.label(draw, "AI 配音", (1848, 82), 20, 150, self.v["accent"], "rm")
        count = len(step["images"])
        box_width = (1776 - 30 * (count - 1)) / count
        rects = []
        for i, path in enumerate(step["images"]):
            label = step["labels"][i]
            box = tuple(self.px(v) for v in (72 + i * (box_width + 30), 158, box_width, 730))
            with Image.open(path) as source:
                source = ImageOps.exif_transpose(source).convert("RGBA")
                rect = fit_rect(source.size, box)
                x, y, w, h = rect
                draw.rounded_rectangle((x - self.px(1), y - self.px(1), x + w + self.px(1), y + h + self.px(1)),
                                       radius=self.px(12), outline=self.v["surface"], width=self.px(2))
                source = source.resize((w, h), Image.Resampling.LANCZOS)
                image.paste(source, (x, y), source)
                rects.append(rect)
            if label:
                self.label(draw, label, (72 + i * (box_width + 30) + box_width / 2, 930),
                           24, box_width, self.v["accent"], "mm")
        if any("cursor" in s for s in chapter["steps"]):
            self.label(draw, "操作演示", (1848, 122), 18, 150, self.v["accent"], "rm")
        return image, rects

    def scene(self, index, local_time):
        chapter = self.chapters[index]
        fraction = min(1, max(0, (local_time - chapter["lead"]) / chapter["audio_duration"]))
        steps = chapter["steps"]
        si = max(i for i, s in enumerate(steps) if s["at"] <= fraction)
        step = steps[si]
        frame, rects = self.step_frame(index, si)
        frame = frame.copy()
        since = (fraction - step["at"]) * chapter["audio_duration"]
        transition = min(self.v["transition"], 0.45)
        if si and transition > 0 and since < transition:
            previous, _ = self.step_frame(index, si - 1)
            frame = Image.blend(previous, frame, smooth(since / transition))
        if "cursor" in step:
            target = step["cursor"]
            origin = steps[si - 1].get("cursor", target) if si else target
            move = smooth(since / 0.55)
            x, y, w, h = rects[0]
            cx = x + w * (origin[0] + (target[0] - origin[0]) * move)
            cy = y + h * (origin[1] + (target[1] - origin[1]) * move)
            draw = ImageDraw.Draw(frame)
            points = [(cx + self.px(dx), cy + self.px(dy)) for dx, dy in
                      [(0, 0), (0, 26), (7, 20), (13, 32), (18, 29), (12, 18), (22, 17)]]
            draw.polygon(points, fill="white", outline="#15171a", width=max(1, self.px(2)))
            if step.get("click") and 0.55 <= since <= 1.0:
                r = self.px(12 + 25 * (since - 0.55) / 0.45)
                draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=self.v["accent"], width=max(1, self.px(3)))
        return frame

    def frame(self, time_value):
        index = next((i for i, c in enumerate(self.chapters) if c["start"] <= time_value < c["end"]), len(self.chapters) - 1)
        chapter = self.chapters[index]
        local_time = time_value - chapter["start"]
        image = self.scene(index, local_time)
        transition = min(self.v["transition"], chapter["lead"])
        if index and transition > 0 and local_time < transition:
            previous = self.chapters[index - 1]
            before = self.scene(index - 1, previous["end"] - previous["start"])
            image = Image.blend(before, image, smooth(local_time / transition))
        draw = ImageDraw.Draw(image)
        cue = next((c for c in chapter["cues"] if c["start"] <= time_value < c["end"]), None)
        if cue:
            font = self.font(32)
            lines, line = [], ""
            for c in cue["text"]:
                if line and draw.textlength(line + c, font=font) > self.px(1600):
                    lines.append(line)
                    line = ""
                line += c
            if line:
                lines.append(line)
            if len(lines) > 2:
                raise VideoError("字幕超过两行，请缩短单句或增加字幕分段。")
            width = max(draw.textlength(s, font=font) for s in lines) + self.px(48)
            center_y = self.px(992)
            height = self.px(46 * len(lines) + 12)
            draw.rounded_rectangle((self.w / 2 - width / 2, center_y - height / 2,
                                    self.w / 2 + width / 2, center_y + height / 2),
                                   radius=self.px(14), fill=self.v["surface"])
            for i, line in enumerate(lines):
                draw.text((self.w / 2, center_y + self.px((i - (len(lines) - 1) / 2) * 46)),
                          line, font=font, fill=self.v["foreground"], anchor="mm")
        draw.rectangle((0, self.h - self.px(3), round(self.w * time_value / self.total), self.h), fill=self.v["accent"])
        return image


def encode_video(renderer, audio, destination, timeout=7200):
    v = renderer.v
    frame_count = math.ceil(renderer.total * v["fps"])
    args = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s",
            f"{v['width']}x{v['height']}", "-r", str(v["fps"]), "-i", "pipe:0", "-i", str(audio),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", v["encoder"]]
    args += ["-preset", "fast", "-crf", "18"] if v["encoder"] == "libx264" else ["-b:v", "8M"]
    args += ["-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
             "-af", "apad", "-t", str(frame_count / v["fps"]), "-movflags", "+faststart",
             "-metadata", "comment=AI-generated narration; screenshot-based operation simulation", str(destination)]
    begin = time.monotonic()
    with tempfile.TemporaryFile() as errors:
        proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors)
        try:
            os.set_blocking(proc.stdin.fileno(), False)
            with selectors.DefaultSelector() as selector:
                selector.register(proc.stdin, selectors.EVENT_WRITE)
                for frame_index in range(frame_count):
                    if frame_index % (v["fps"] * 5) == 0:
                        print(f"渲染 {frame_index / frame_count:.0%}（{frame_index / v['fps']:.0f}/{renderer.total:.0f} 秒）", flush=True)
                    buffer = memoryview(renderer.frame(frame_index / v["fps"]).tobytes())
                    while buffer:
                        if time.monotonic() - begin > timeout or not selector.select(timeout=30):
                            raise VideoError("视频编码超时，已停止本次编码进程。")
                        try:
                            sent = os.write(proc.stdin.fileno(), buffer[:65536])
                            buffer = buffer[sent:]
                        except BlockingIOError:
                            continue
            proc.stdin.close()
            proc.wait(timeout=120)
            if proc.returncode:
                raise VideoError(f"视频编码失败（退出码 {proc.returncode}）。")
        except (BrokenPipeError, subprocess.TimeoutExpired):
            errors.seek(0)
            raise VideoError("视频编码中断：" + errors.read()[-1200:].decode(errors="replace")) from None
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
    return frame_count
