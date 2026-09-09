from contextlib import contextmanager
import fcntl
import json
import math
from pathlib import Path
import wave

from . import __version__
from .common import VideoError, atomic_write, digest, file_hash, probe, run, write_json
from .render import Renderer, encode_video
from .subtitles import from_events, srt
from .tts import cache_location, cached_audio, generate


@contextmanager
def project_lock(output):
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".build.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise VideoError("同一个输出目录已有生成任务，请等待该任务结束。") from None
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def prepare(config, allow_api):
    output = Path(config["output"])
    chapters, cursor = [], 0.0
    v = config["video"]
    for chapter in config["chapters"]:
        folder = cache_location(output, chapter, config["voice"])
        metadata = cached_audio(folder)
        if metadata is None:
            if not allow_api:
                raise VideoError(f"{chapter['id']} 尚未生成配音，请先运行 voice 或 build。")
            folder, metadata = generate(chapter, config["voice"], output)
        duration = metadata["duration"]
        lead = max(0.25, v["transition"])
        length = math.ceil((lead + duration + v["chapter_pause"]) * v["fps"]) / v["fps"]
        if "captions" in chapter:
            cues = chapter["captions"]
            if any(c["end"] > duration for c in cues):
                raise VideoError(f"{chapter['id']} 的手动字幕超过配音时长。")
        elif v["subtitles"] == "none":
            cues = []
        else:
            cues = from_events(metadata["events"], chapter["narration"], duration)
        cues = [{**cue, "start": cue["start"] + cursor + lead, "end": cue["end"] + cursor + lead} for cue in cues]
        chapters.append({**chapter, "start": cursor, "end": cursor + length, "lead": lead,
                         "audio_duration": duration, "audio": str(folder / "voice.mp3"),
                         "audio_sha256": metadata["sha256"], "cues": cues})
        cursor += length
    return chapters


def master_audio(chapters, folder):
    sample_rate = 48000
    destination = folder / "narration.wav"
    with wave.open(str(destination), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        written = 0
        for chapter in chapters:
            start = round((chapter["start"] + chapter["lead"]) * sample_rate)
            if start < written:
                raise VideoError("配音时间轴出现重叠。")
            out.writeframes(b"\x00" * (start - written) * 4)
            pcm = run(["ffmpeg", "-v", "error", "-i", chapter["audio"], "-ar", str(sample_rate), "-ac", "2",
                       "-f", "s16le", "pipe:1"])
            out.writeframes(pcm)
            written = start + len(pcm) // 4
        end = round(chapters[-1]["end"] * sample_rate)
        if written > end:
            raise VideoError("配音超出视频时间轴。")
        out.writeframes(b"\x00" * (end - written) * 4)
    return destination


def verify(path, config, duration):
    data = probe(path)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    if not video or not audio:
        raise VideoError("成片缺少画面或音轨。")
    v = config["video"]
    if (video["width"], video["height"], video["pix_fmt"]) != (v["width"], v["height"], "yuv420p"):
        raise VideoError("成片画面规格不符合配置。")
    if abs(float(data["format"]["duration"]) - duration) > 0.12:
        raise VideoError("成片时长与配音时间轴不一致。")
    if abs(float(audio["duration"]) - duration) > 0.12:
        raise VideoError("成片音轨时长与时间轴不一致。")
    run(["ffmpeg", "-v", "error", "-xerror", "-i", path, "-f", "null", "-"], timeout=max(120, int(duration * 3)))
    return {"full_decode": "passed", "width": video["width"], "height": video["height"],
            "fps": video["avg_frame_rate"], "video_codec": video["codec_name"],
            "audio_codec": audio["codec_name"], "duration": float(data["format"]["duration"])}


def build(config, allow_api=True, preview=False):
    output = Path(config["output"])
    with project_lock(output):
        chapters = prepare(config, allow_api)
        assets = {p for c in chapters for s in c["steps"] for p in s["images"]}
        if config["product"].get("logo"):
            assets.add(config["product"]["logo"])
        assets.add(config["video"]["font"])
        hashes = {p: file_hash(p) for p in sorted(assets)}
        source_hash = digest({p.name: file_hash(p) for p in Path(__file__).parent.glob("*.py")})
        signature = digest({"version": __version__, "source": source_hash, "config": config, "assets": hashes,
                            "audio": [c["audio_sha256"] for c in chapters]})[:16]
        folder = output / "renders" / signature
        folder.mkdir(parents=True, exist_ok=True)
        renderer = Renderer(config, chapters)
        write_json(folder / "timeline.json", {"chapters": chapters, "duration": renderer.total})
        atomic_write(folder / "subtitles.srt", srt([cue for c in chapters for cue in c["cues"]]).encode())
        atomic_write(folder / "narration.txt", "\n\n".join(c["narration"] for c in chapters).encode())
        write_json(folder / "project.resolved.json", config)
        previews = folder / "preview"
        previews.mkdir(exist_ok=True)
        for i, chapter in enumerate(chapters):
            for j, step in enumerate(chapter["steps"]):
                next_at = chapter["steps"][j+1]["at"] if j+1 < len(chapter["steps"]) else 1
                shift = min(0.7, (next_at - step["at"]) * chapter["audio_duration"] * 0.8)
                t = chapter["start"] + chapter["lead"] + chapter["audio_duration"] * step["at"] + shift
                t = min(t, chapter["end"] - 0.05)
                renderer.frame(t).save(previews / f"{i + 1:02}-{chapter['id']}-{j + 1:02}.png")
        if preview:
            print(f"预览已保存：{previews}")
            return folder
        movie, report_path = folder / "product-introduction.mp4", folder / "verification.json"
        if movie.exists() and report_path.exists():
            report = json.loads(report_path.read_text())
            if report["sha256"] == file_hash(movie):
                write_json(output / "latest.json", {"movie": str(movie), "report": str(report_path)})
                print(f"复用已验证成片：{movie}")
                return folder
            raise VideoError("已有成片校验失败，请移走此 renders 子目录后重新渲染。")
        master = master_audio(chapters, folder)
        partial = folder / "product-introduction.pending.mp4"
        try:
            frames = encode_video(renderer, master, partial)
            report = verify(partial, config, renderer.total)
            partial.replace(movie)
        finally:
            partial.unlink(missing_ok=True)
        report.update(sha256=file_hash(movie), bytes=movie.stat().st_size, frames=frames,
                      chapters=len(chapters), subtitle_cues=sum(len(c["cues"]) for c in chapters),
                      assets=hashes, voice=config["voice"]["speaker"], api="Volcengine TTS v3",
                      caption_alignment="API word timestamps or explicit chapter captions; see project.resolved.json",
                      visual_review="unverified", listening_review="unverified")
        write_json(report_path, report)
        write_json(output / "latest.json", {"movie": str(movie), "report": str(report_path)})
        print(f"成片已生成并通过完整解码：{movie}")
        return folder
