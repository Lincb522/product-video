import copy
import json
import math
from pathlib import Path
import re
import shutil

from PIL import Image, ImageColor, ImageFont, ImageOps

from .common import VideoError
from .motion import PRESETS, TRANSITIONS
from .text_scenes import content_layout
from .tts import DEFAULT_VOICE
from .voices import resolve

DEFAULT_VIDEO = {"width": 1920, "height": 1080, "fps": 30, "font": None,
                 "encoder": "libx264", "subtitles": "auto", "style": "product",
                 "reduced_motion": False, "renderer": "legacy"} | PRESETS['product']


def known(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise VideoError(f"{label} 包含不支持的字段或不是对象，请对照 README。")


def number(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise VideoError(f"{label} 必须在 {low}–{high} 之间。")


def text(value, label, maximum=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise VideoError(f"{label} 不能为空且最多 {maximum} 字符。")


def point(value, label):
    if not isinstance(value, list) or len(value) != 2:
        raise VideoError(f'{label} 需为截图上的 [x, y] 归一化坐标。')
    for coordinate in value:
        number(coordinate, 0, 1, label)


def transition_fields(value):
    if 'transition' in value and value['transition'] not in TRANSITIONS:
        raise VideoError('transition 类型不受支持，请对照镜头与动效说明。')
    if 'transition_duration' in value:
        number(value['transition_duration'], 0, 2, 'transition_duration')


def validate_content(content, images, video):
    known(content, ('layout', 'eyebrow', 'headline', 'body', 'bullets', 'image_side', 'animation'), 'content')
    layout = content.get('layout')
    if layout not in ('title', 'bullets', 'split'):
        raise VideoError('content.layout 仅支持 title、bullets 或 split。')
    text(content.get('headline'), '画面主标题', 120)
    for key, limit in (('eyebrow', 60), ('body', 800)):
        if key in content:
            text(content[key], f'content.{key}', limit)
    if content.get('animation', 'reveal') not in ('reveal', 'none'):
        raise VideoError('content.animation 仅支持 reveal 或 none。')
    if layout == 'split':
        if len(images) != 1 or content.get('image_side', 'right') not in ('left', 'right'):
            raise VideoError('split 需要一张截图，image_side 仅支持 left 或 right。')
    elif images or 'image_side' in content:
        raise VideoError('title 和 bullets 是纯文案画面；需要配图时请使用 split。')
    if layout == 'bullets':
        items = content.get('bullets')
        if not isinstance(items, list) or not 1 <= len(items) <= 4 or 'body' in content:
            raise VideoError('bullets 版式需要 1–4 项要点，不同时使用 body；长文请拆分画面。')
        for item in items:
            text(item, '文案要点', 180)
    elif 'bullets' in content:
        raise VideoError('bullets 字段只用于 bullets 版式。')
    content_layout(content, video)


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


def load(path, *, check_image_geometry=True):
    path = Path(path).expanduser().resolve()
    try:
        config = json.loads(path.read_text())
    except (OSError, ValueError):
        raise VideoError("项目配置无法读取或不是有效 JSON。") from None
    known(config, ("schema_version", "product", "output", "voice", "video", "chapters", "audio"), "项目")
    if config.get("schema_version") not in (1, 2):
        raise VideoError("schema_version 必须为 1 或 2。")
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
    style = supplied_video.get('style', 'product')
    if not isinstance(style, str) or style not in PRESETS:
        raise VideoError('video.style 仅支持：' + '、'.join(PRESETS) + '。')
    video = DEFAULT_VIDEO | PRESETS[style] | {'renderer': 'remotion' if config['schema_version'] == 2 else 'legacy'} | supplied_video
    if video['renderer'] not in ('legacy', 'remotion'):
        raise VideoError('video.renderer 仅支持 legacy 或 remotion。')
    if 'audio' in config:
        if video['renderer'] != 'remotion':
            raise VideoError('独立音乐与音效轨需要 video.renderer: remotion。')
        from .shotcraft import validate_audio
        validate_audio(config['audio'], base)
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
    for key in ('transition_style', 'step_transition'):
        if video[key] not in TRANSITIONS:
            raise VideoError(f'{key} 类型不受支持，请对照镜头与动效说明。')
    if video['camera_motion'] not in ('none', 'push'):
        raise VideoError('camera_motion 仅支持 none 或 push。')
    for key, low, high in (('cursor_move', .08, 3), ('cursor_hold', 0, 2), ('cursor_linger', 0, 5)):
        number(video[key], low, high, key)
    for key in ('progress', 'reduced_motion'):
        if not isinstance(video[key], bool):
            raise VideoError(f'{key} 必须是布尔值。')
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
        known(chapter, ("id", "title", "narration", "steps", "captions", "transition", "transition_duration"), "章节")
        transition_fields(chapter)
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
        for step_index, step in enumerate(steps):
            known(step, ("at", "images", "labels", "cursor", "click", "interaction", "camera",
                         "transition", "transition_duration", "content", "scene3d", "shotcraft", "editorial"), "画面")
            transition_fields(step)
            number(step.get("at"), 0, 0.99, "画面 at")
            if step["at"] <= previous or (previous == -1 and step["at"] != 0):
                raise VideoError("首个画面的 at 必须为 0，后续按升序且不重复。")
            previous = step["at"]
            if any(k in step for k in ('content', 'scene3d', 'shotcraft', 'editorial')):
                step.setdefault('images', [])
            if not isinstance(step.get("images"), list) or not 0 <= len(step["images"]) <= 2:
                raise VideoError("images 必须是最多两张图片的数组。")
            if 'editorial' in step:
                if video['renderer'] != 'remotion':
                    raise VideoError('editorial 内容镜头需要 Remotion。')
                if step['images'] or step.get('labels') or any(k in step for k in ('content', 'scene3d', 'shotcraft', 'cursor', 'click', 'interaction', 'camera')):
                    raise VideoError('editorial 使用自身图片与版式，不同时使用其他镜头字段。')
                from .editorial import validate_editorial
                validate_editorial(step['editorial'], asset, video['font'])
            if 'shotcraft' in step:
                if video['renderer'] != 'remotion':
                    raise VideoError('Shotcraft 镜头需要 schema_version: 2 或 video.renderer: remotion。')
                if step['images'] or any(k in step for k in ('content', 'scene3d', 'cursor', 'click', 'interaction', 'camera')) or step.get('labels'):
                    raise VideoError('Shotcraft 镜头通过 text、media 与 colors 替换内容，不同时使用其他镜头字段。')
                from .shotcraft import validate_motion
                validate_motion(step['shotcraft'], base)
            if 'scene3d' in step:
                from .scene3d import validate_scene
                validate_scene(step['scene3d'], base, video)
                if step['images'] or any(k in step for k in ('cursor', 'click', 'interaction', 'camera')) or step.get('labels'):
                    raise VideoError('三维画面使用 scene3d.devices，不同时使用二维图片、鼠标或相机字段。')
                if 'content' in step and step['content'].get('layout') != 'split':
                    raise VideoError('三维画面的文案使用 content.layout: split，纯文字镜头单独编排。')
            if 'content' in step:
                validate_content(step['content'], ['3d-screen'] if 'scene3d' in step else step['images'], video)
            elif not step['images'] and 'scene3d' not in step and 'shotcraft' not in step and 'editorial' not in step:
                raise VideoError("每个画面需要 1–2 张图片，或用 content 编排纯文案画面。")
            step["images"] = [asset(x) for x in step["images"]]
            labels = step.setdefault("labels", [""] * len(step["images"]))
            if not isinstance(labels, list) or len(labels) != len(step["images"]) or any(not isinstance(s, str) or len(s) > 60 for s in labels):
                raise VideoError("labels 数量必须与图片一致，每项最多 60 字符。")
            if "cursor" in step:
                if len(step["images"]) != 1:
                    raise VideoError("cursor 需为单图上的 [x, y] 坐标。")
                point(step['cursor'], 'cursor')
            if "click" in step and (not isinstance(step["click"], bool) or "cursor" not in step):
                raise VideoError("click 必须是布尔值，并需指定 cursor。")
            if 'interaction' in step:
                if 'cursor' in step or 'click' in step or len(step['images']) != 1:
                    raise VideoError('interaction 只用于单图，不能与 cursor/click 同时使用。')
                spec = step['interaction']
                known(spec, ('kind', 'from', 'to', 'move', 'hold', 'settle', 'linger'), 'interaction')
                if spec.get('kind') not in ('move', 'click', 'drag'):
                    raise VideoError('interaction.kind 仅支持 move、click 或 drag。')
                point(spec.get('to'), 'interaction.to')
                if 'from' in spec:
                    point(spec['from'], 'interaction.from')
                if spec['kind'] == 'drag' and 'from' not in spec:
                    raise VideoError('拖动需要明确的 interaction.from。')
                for key, low, high in (('move', .08, 3), ('hold', 0, 2), ('settle', .08, 2), ('linger', 0, 5)):
                    if key in spec:
                        number(spec[key], low, high, f'interaction.{key}')
                if spec['kind'] in ('click', 'drag') and step_index == 0:
                    raise VideoError('点击或拖动结果前需有一张操作前截图；请先增加 at: 0 的静态画面。')
            changes_state = step.get('click') or step.get('interaction', {}).get('kind') in ('click', 'drag')
            if changes_state and step_index:
                before = steps[step_index - 1]
                if len(before['images']) != 1:
                    raise VideoError('操作前后必须都是单图；不能在并排对照上点击。')
                def image_layout(item):
                    content = item.get('content', {})
                    return content.get('layout'), content.get('image_side', 'right')
                if image_layout(before) != image_layout(step):
                    raise VideoError('操作前后需使用相同的截图版式和 image_side；请先建立新的静态画面再操作。')
                if check_image_geometry:
                    with Image.open(before['images'][0]) as a, Image.open(step['images'][0]) as b:
                        a, b = ImageOps.exif_transpose(a), ImageOps.exif_transpose(b)
                        if abs(a.width / a.height - b.width / b.height) > .01:
                            raise VideoError('操作前后截图比例不同，无法对齐鼠标；请使用同一视口重新采集。')
            if 'camera' in step:
                if len(step['images']) != 1:
                    raise VideoError('局部运镜只用于单图；并排对照保持全图。')
                camera = step['camera']
                known(camera, ('zoom', 'center'), 'camera')
                number(camera.get('zoom', 1), 1, 2.5, 'camera.zoom')
                point(camera.get('center', [.5, .5]), 'camera.center')
    text(config.get("output", "output"), "输出路径", 4096)
    output = (base / Path(config.get("output", "output")).expanduser()).resolve()
    config.update(voice=voice, video=video, output=str(output))
    for command in ("ffmpeg", "ffprobe"):
        if not shutil.which(command):
            raise VideoError(f"缺少 {command}，请安装 FFmpeg。")
    return config
