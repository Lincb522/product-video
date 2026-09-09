import copy
import json
import math
from pathlib import Path
import re
import shutil

from PIL import Image, ImageColor, ImageFont

from .common import VideoError
from .tts import DEFAULT_VOICE
from .voices import resolve

DEFAULT_VIDEO = {"width": 1920, "height": 1080, "fps": 30, "transition": 0.6,
                 "chapter_pause": 0.7, "background": "#17191f", "surface": "#23262e",
                 "foreground": "#f8f6f2", "accent": "#d5ac86", "font": None,
                 "encoder": "libx264", "subtitles": "auto"}


def known(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise VideoError(f"{label} 包含不支持的字段或不是对象，请对照 README。")


def number(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise VideoError(f"{label} 必须在 {low}–{high} 之间。")


def text(value, label, maximum=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise VideoError(f"{label} 不能为空且最多 {maximum} 字符。")


def font_path(configured, base):
    if configured:
        text(configured, "字体路径", 4096)
        p = (base / Path(configured).expanduser()).resolve()
        if not p.is_file():
            raise VideoError("指定的字体文件不存在。")
        return str(p)
    candidates = ["/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Light.ttc",
                  "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
    for p in candidates:
        if Path(p).is_file():
            return p
    raise VideoError("没有找到中文字体，请在 video.font 指定有使用授权的字体。")


def load(path):
    path = Path(path).expanduser().resolve()
    try:
        config = json.loads(path.read_text())
    except (OSError, ValueError):
        raise VideoError("项目配置无法读取或不是有效 JSON。") from None
    known(config, ("schema_version", "product", "output", "voice", "video", "chapters"), "项目")
    if config.get("schema_version") != 1:
        raise VideoError("schema_version 必须为 1。")
    product = config.get("product")
    known(product, ("name", "logo"), "product")
    text(product.get("name"), "产品名称", 60)
    if not isinstance(config.get("chapters"), list) or not config["chapters"]:
        raise VideoError("至少需要一个章节。")
    base = path.parent

    def asset(value):
        text(value, "素材路径", 4096)
        result = (base / Path(value).expanduser()).resolve()
        try:
            with Image.open(result) as im:
                im.verify()
        except (OSError, ValueError):
            raise VideoError(f"素材不是可读图片：{result.name}。") from None
        return str(result)

    if product.get("logo"):
        product["logo"] = asset(product["logo"])
    supplied_voice = config.get("voice", {})
    known(supplied_voice, (*DEFAULT_VOICE, "pronunciation_dict", "transport"), "voice")
    voice = copy.deepcopy(DEFAULT_VOICE) | supplied_voice
    if supplied_voice.get("speaker"):
        text(supplied_voice["speaker"], "speaker", 160)
        try:
            selected = resolve(supplied_voice["speaker"])
        except VideoError:
            if not supplied_voice.get("resource_id"):
                raise
        else:
            voice["speaker"] = selected["id"]
            voice["resource_id"] = supplied_voice.get("resource_id", selected["resource_id"])
            permitted = [selected["resource_id"]]
            if selected["model"] == "1.0":
                permitted.append("seed-tts-1.0-concurr")
            if voice["resource_id"] not in permitted:
                raise VideoError("该音色与 resource_id 模型不匹配。")
            if selected["transport"] == "http" and voice.get("transport") == "websocket":
                raise VideoError("该音色需使用 HTTP 单向流，请去掉 transport 或设置为 http。")
    if voice.get("transport", "websocket") not in ("http", "websocket"):
        raise VideoError("transport 仅支持 http 或 websocket。")
    for key in ("speaker", "resource_id"):
        text(voice[key], key, 160)
    for key in ("speech_rate", "loudness_rate"):
        number(voice[key], -50, 100, key)
        if not isinstance(voice[key], int):
            raise VideoError(f"{key} 必须为整数。")
    if not isinstance(voice["context_texts"], list) or len(voice["context_texts"]) > 10:
        raise VideoError("context_texts 必须为最多 10 项的文本数组。")
    for value in voice["context_texts"]:
        text(value, "音色指令", 1000)
    if "pronunciation_dict" in voice:
        if not isinstance(voice["pronunciation_dict"], list):
            raise VideoError("pronunciation_dict 必须为文本数组。")
        for value in voice["pronunciation_dict"]:
            text(value, "发音词典条目", 100)
    supplied_video = config.get("video", {})
    known(supplied_video, DEFAULT_VIDEO, "video")
    video = DEFAULT_VIDEO | supplied_video
    for key in ("width", "height"):
        number(video[key], 320, 3840, key)
        if not isinstance(video[key], int) or video[key] % 2:
            raise VideoError("画面宽高必须是偶数整数。")
    if abs(video["width"] / video["height"] - 16 / 9) > 0.01:
        raise VideoError("当前模板使用 16:9 横屏，请使用 1920×1080 或 1280×720。")
    number(video["fps"], 24, 60, "fps")
    if not isinstance(video["fps"], int):
        raise VideoError("fps 必须是整数。")
    number(video["transition"], 0, 2, "transition")
    number(video["chapter_pause"], 0, 5, "chapter_pause")
    if video["encoder"] not in ("libx264", "h264_videotoolbox"):
        raise VideoError("encoder 仅支持 libx264 或 h264_videotoolbox。")
    if video["subtitles"] not in ("auto", "none"):
        raise VideoError("subtitles 仅支持 auto 或 none；其他语言也可在章节中提供 captions 时间轴。")
    for key in ("background", "surface", "foreground", "accent"):
        try:
            ImageColor.getrgb(video[key])
        except (ValueError, TypeError, AttributeError):
            raise VideoError(f"{key} 不是有效颜色。") from None
    video["font"] = font_path(video["font"], base)
    ImageFont.truetype(video["font"], 20)
    seen = set()
    for chapter in config["chapters"]:
        known(chapter, ("id", "title", "narration", "steps", "captions"), "章节")
        identifier = chapter.get("id", "")
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", identifier) or identifier in seen:
            raise VideoError("章节 id 必须为不重复的小写字母、数字、连字符或下划线。")
        seen.add(identifier)
        text(chapter.get("title"), "章节标题", 100)
        text(chapter.get("narration"), "章节旁白")
        if "captions" in chapter:
            if not isinstance(chapter["captions"], list):
                raise VideoError("captions 必须为按时间排序的字幕数组。")
            end = 0
            for cue in chapter["captions"]:
                known(cue, ("start", "end", "text"), "字幕")
                number(cue.get("start"), end, 3600, "字幕 start")
                number(cue.get("end"), cue["start"], 3600, "字幕 end")
                if cue["end"] == cue["start"]:
                    raise VideoError("字幕结束时间必须晚于开始时间。")
                text(cue.get("text"), "字幕", 80)
                end = cue["end"]
        steps = chapter.get("steps")
        if not isinstance(steps, list) or not steps:
            raise VideoError("每个章节至少需要一个 steps 画面。")
        previous = -1
        for step in steps:
            known(step, ("at", "images", "labels", "cursor", "click"), "画面")
            number(step.get("at"), 0, 0.99, "画面 at")
            if step["at"] <= previous or (previous == -1 and step["at"] != 0):
                raise VideoError("首个画面的 at 必须为 0，后续按升序且不重复。")
            previous = step["at"]
            if not isinstance(step.get("images"), list) or not 1 <= len(step["images"]) <= 2:
                raise VideoError("每个画面需要 1–2 张图片。")
            step["images"] = [asset(x) for x in step["images"]]
            labels = step.setdefault("labels", [""] * len(step["images"]))
            if not isinstance(labels, list) or len(labels) != len(step["images"]) or any(not isinstance(s, str) or len(s) > 60 for s in labels):
                raise VideoError("labels 数量必须与图片一致，每项最多 60 字符。")
            if "cursor" in step:
                if len(step["images"]) != 1 or not isinstance(step["cursor"], list) or len(step["cursor"]) != 2:
                    raise VideoError("cursor 需为单图上的 [x, y] 坐标。")
                for coordinate in step["cursor"]:
                    number(coordinate, 0, 1, "cursor")
            if "click" in step and (not isinstance(step["click"], bool) or "cursor" not in step):
                raise VideoError("click 必须是布尔值，并需指定 cursor。")
    text(config.get("output", "output"), "输出路径", 4096)
    output = (base / Path(config.get("output", "output")).expanduser()).resolve()
    config.update(voice=voice, video=video, output=str(output))
    for command in ("ffmpeg", "ffprobe"):
        if not shutil.which(command):
            raise VideoError(f"缺少 {command}，请安装 FFmpeg。")
    return config
