from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .common import VideoError, write_json
from .config import font_path

FIRST_NARRATION = "根据介绍稿生成配音与字幕，按章节合成文案和界面画面。"


def create(folder, schema_version=1):
    folder = Path(folder).expanduser().resolve()
    if folder.exists() and any(folder.iterdir()):
        raise VideoError("示例目录不是空目录，请另选一个目录；不会覆盖已有项目。")
    assets = folder / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    font = font_path(None, folder)
    for dark in (True, False):
        for selected in (0, 1):
            bg, surface, fg, muted = ("#1b1e26", "#272b35", "#f0eee9", "#a3a7b2") if dark else (
                "#f4f3f0", "#ffffff", "#252932", "#666a75")
            im = Image.new("RGB", (1440, 900), bg)
            d = ImageDraw.Draw(im)

            def label(x, y, text, size=24, color=fg):
                d.text((x, y), text, font=ImageFont.truetype(font, size), fill=color)

            d.rounded_rectangle((20, 20, 270, 880), radius=24, fill=surface)
            label(44, 50, "示例工作台", 30)
            for i, title in enumerate(("项目", "配音", "素材", "导出")):
                y = 148 + i * 72
                if i == selected:
                    d.rounded_rectangle((34, y - 6, 254, y + 45), 12, fill="#926f53" if dark else "#e9cfb8")
                label(55, y, title)
            label(310, 45, "配音与字幕" if selected else "产品介绍", 36)
            label(310, 102, "示例素材 · 请替换为你自己产品的真实截图", 21, muted)
            for i, (title, body) in enumerate((("文稿", "使用你确认过的介绍文案"),
                                               ("配音角色", "小何 2.0"), ("画面", "截图、主题对照与模拟操作"))):
                y = 190 + i * 174
                d.rounded_rectangle((310, y, 1400, y + 145), 20, fill=surface)
                label(340, y + 20, title, 21, muted)
                label(340, y + 65, body, 30)
            d.rounded_rectangle((1190, 770, 1400, 836), 16, fill="#c59a75")
            label(1230, 785, "生成视频", 28, "#181b21")
            im.save(assets / f"{'dark' if dark else 'light'}-{selected}.png")
    config = {
        "schema_version": schema_version, "product": {"name": "产品视频示例"}, "output": "output",
        "voice": {"speaker": "zh_female_xiaohe_uranus_bigtts"},
        "video": {"width": 1920, "height": 1080, "fps": 30},
        "chapters": [
            {"id": "workflow", "title": "文稿、配音和画面", "narration": FIRST_NARRATION,
             "steps": [
                 {"at": 0, "images": ["assets/dark-0.png"], "labels": ["示例素材"], "cursor": [0.1, 0.19]},
                 {"at": 0.45, "images": ["assets/dark-1.png"], "labels": ["示例素材"],
                  "cursor": [0.1, 0.27], "click": True}]},
            {"id": "appearance", "title": "展示不同界面", "narration": "深色与浅色界面可并排展示，便于比较布局和视觉差异。",
             "steps": [{"at": 0, "images": ["assets/dark-1.png", "assets/light-1.png"],
                        "labels": ["深色示例", "浅色示例"]}]}]}
    write_json(folder / "project.json", config)
    print(f"示例已创建：{folder / 'project.json'}\n其中的界面是演示素材，请换成真实截图。")
    return folder / "project.json"
