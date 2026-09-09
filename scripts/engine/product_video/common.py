import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


class VideoError(Exception):
    """An actionable error safe for the command-line boundary."""


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_write(path, data, mode=0o644):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            os.fchmod(f.fileno(), mode)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def write_json(path, data):
    atomic_write(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode())


def run(argv, timeout=120):
    try:
        p = subprocess.run([str(x) for x in argv], capture_output=True, timeout=timeout)
    except FileNotFoundError:
        raise VideoError(f"缺少 {argv[0]}，请安装后重试。") from None
    except subprocess.TimeoutExpired:
        raise VideoError(f"{argv[0]} 超过 {timeout} 秒，已终止本次子进程。") from None
    if p.returncode:
        raise VideoError(f"{argv[0]} 失败（退出码 {p.returncode}）：{p.stderr.decode(errors='replace')[-1600:]}")
    return p.stdout


def probe(path):
    return json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path]))


def audio_duration(path):
    data = probe(path)
    if not any(s["codec_type"] == "audio" for s in data["streams"]):
        raise VideoError("音频文件没有音轨。")
    duration = float(data["format"]["duration"])
    if duration <= 0:
        raise VideoError("音频时长为零。")
    return duration
