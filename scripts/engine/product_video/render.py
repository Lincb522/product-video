import math
import selectors
import os
import subprocess
import tempfile
import time

from .common import VideoError
from .compositor import Renderer, fit_rect


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
