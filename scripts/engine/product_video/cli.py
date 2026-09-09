import argparse
import copy
import csv
import json
from pathlib import Path
import sys

from . import credentials, voices
from .common import VideoError, write_json
from .config import load, text
from .demo import create
from .pipeline import build, project_lock
from .tts import DEFAULT_VOICE, generate


def parser():
    p = argparse.ArgumentParser(description="本地产品介绍视频：配音、字幕、截图和模拟操作。")
    sub = p.add_subparsers(dest="command", required=True)
    auth = sub.add_parser("credentials", help="配置本地密钥；输入不回显")
    auth.add_argument("action", choices=("set", "setup", "status"))
    auth.add_argument("--timeout", type=int, default=900)
    auth.add_argument("--no-open", action="store_true")
    auth.add_argument("--replace", action="store_true", help="主动重新配置已有密钥")
    capture = sub.add_parser("capture", help="自动操作目标并采集真实界面，不调用语音 API")
    capture.add_argument("project")
    auto = sub.add_parser("auto", help="自动截图、首次密钥引导、配音和成片")
    auto.add_argument("project")
    auto.add_argument("--voice", help="本次使用的音色名称或 ID")
    inspect = sub.add_parser("inspect-app", help="读取指定 macOS 窗口的控件名称，供截图计划定位")
    inspect.add_argument("bundle_id")
    inspect.add_argument("--window-title", default="")
    inspect.add_argument("--output", default=".captures")
    init = sub.add_parser("init", help="创建可直接生成短片的示例项目")
    init.add_argument("directory")
    listing = sub.add_parser("voices", help="列出全部官方 TTS 音色，可搜索")
    listing.add_argument("--search", default="")
    listing.add_argument("--language", default="")
    listing.add_argument("--model", choices=("1.0", "2.0"), default="")
    listing.add_argument("--json", action="store_true")
    listing.add_argument("--csv", metavar="PATH")
    select = sub.add_parser("select-voice", help="保存音色到项目；省略名称时交互选择")
    select.add_argument("project")
    select.add_argument("name", nargs="?")
    sample = sub.add_parser("preview-voice", help="API 生成短试听；相同内容会复用缓存")
    sample.add_argument("--voice", required=True)
    sample.add_argument("--text", default="欢迎使用。你可以把文稿和产品截图放进项目，生成自己的介绍视频。")
    sample.add_argument("--output", default="output/voice-previews")
    for name, help_text in (("check", "检查配置和素材，不调用 API"), ("voice", "生成各章配音，不渲染"),
                            ("preview", "用已生成配音导出关键帧，不调用 API"),
                            ("render", "只使用已有配音渲染，不调用 API"), ("build", "生成配音并渲染完整视频")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("project")
        command.add_argument("--voice", help="本次使用的音色名称或 ID，不改项目配置")
    return p


def show_voices(rows):
    for i, v in enumerate(rows, 1):
        print(f"{i:3}  {' / '.join(v['names'])}  |  {' / '.join(v['languages'])}  |  {v['model']}\n     {v['id']}")
    print(f"共 {len(rows)} 个角色；账号是否已授权以 API 结果为准。")


def choose():
    if not sys.stdin.isatty():
        raise VideoError("非交互环境请提供完整音色名称或 ID。")
    rows = voices.search(input("搜索名称或语言（直接回车显示全部）：").strip())
    if not rows:
        raise VideoError("没有匹配音色，请重新搜索。")
    show_voices(rows)
    selected = input("输入角色序号（回车取消）：").strip()
    if not selected:
        return None
    if not selected.isdigit() or not 1 <= int(selected) <= len(rows):
        raise VideoError("序号不在列表内。")
    return rows[int(selected) - 1]["id"]


def apply_voice(config, name):
    selected = voices.settings(name)
    config["voice"].update(selected)
    return selected


def execute(args):
    if args.command == "credentials":
        if args.action == "setup":
            from .onboarding import setup
            if not 1 <= args.timeout <= 1800:
                raise VideoError("配置等待时间必须在 1–1800 秒之间。")
            return setup(timeout=args.timeout, open_browser=not args.no_open, replace=args.replace)
        return credentials.configure() if args.action == "set" else credentials.status()
    if args.command == "init":
        return create(args.directory)
    if args.command == "voices":
        rows = voices.search(args.search, args.language, args.model)
        if args.csv:
            destination = Path(args.csv).expanduser()
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("x", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(("角色", "音色 ID", "语言", "模型", "接口"))
                writer.writerows((" / ".join(v["names"]), v["id"], " / ".join(v["languages"]),
                                  v["model"], v["transport"]) for v in rows)
            print(f"音色表已保存：{destination}")
        elif args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            show_voices(rows)
        return
    if args.command == "preview-voice":
        text(args.text, "试听文案", 300)
        voice = copy.deepcopy(DEFAULT_VOICE) | voices.settings(args.voice)
        with project_lock(Path(args.output).expanduser().resolve()):
            folder, meta = generate({"id": "preview", "narration": args.text}, voice, Path(args.output).expanduser().resolve())
        print(f"试听：{folder / 'voice.mp3'}（{meta['duration']:.2f} 秒）")
        return
    if args.command == "inspect-app":
        from .native_capture import NativeCapture
        target = {"bundle_id": args.bundle_id, "window_title": args.window_title}
        print(json.dumps(NativeCapture(target, Path(args.output).resolve()).inspect(), ensure_ascii=False))
        return
    if args.command in ("capture", "auto"):
        from .capture import capture_project
        from .onboarding import setup
        path = Path(args.project).expanduser().resolve()
        raw = json.loads(path.read_text())
        if args.command == "capture" or "capture" in raw:
            path = capture_project(path)
        if args.command == "capture":
            return
        config = load(path)
        if args.voice:
            apply_voice(config, args.voice)
        setup()
        return build(config, allow_api=True)
    config = load(args.project)
    if args.command == "select-voice":
        name = args.name or choose()
        if name is None:
            print("已取消，配置未修改。")
            return
        selected = voices.settings(name)
        path = Path(args.project).expanduser().resolve()
        original = json.loads(path.read_text())
        original.setdefault("voice", {}).update(selected)
        backup = path.with_suffix(path.suffix + ".before-voice")
        if not backup.exists():
            write_json(backup, json.loads(path.read_text()))
        write_json(path, original)
        print(f"已保存：{' / '.join(voices.resolve(name)['names'])}；接口 {selected['transport']}。")
        return
    if args.voice:
        apply_voice(config, args.voice)
    if args.command == "check":
        print(f"配置与素材检查通过：{config['product']['name']}，{len(config['chapters'])} 章。")
        print(f"配音：{config['voice']['speaker']}；接口：{voices.transport(config['voice'])}。未调用 API。")
    elif args.command == "voice":
        with project_lock(Path(config["output"])):
            for chapter in config["chapters"]:
                folder, meta = generate(chapter, config["voice"], Path(config["output"]))
                print(f"{chapter['id']}：{meta['duration']:.2f} 秒，{folder / 'voice.mp3'}")
    else:
        build(config, allow_api=args.command == "build", preview=args.command == "preview")


def main():
    try:
        execute(parser().parse_args())
    except (VideoError, FileExistsError) as e:
        print(f"未完成：{e}", file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, KeyError):
        print("未完成：配置、素材或本地文件处理失败。请检查输入格式、输出目录权限和剩余空间。", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("已取消。已完成的配音缓存会保留。", file=sys.stderr)
        return 130
    return 0
