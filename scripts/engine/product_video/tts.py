import asyncio
import json
import logging
import time
import uuid

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidStatus

from .common import VideoError, atomic_write, audio_duration, digest, file_hash, run, write_json
from .credentials import load_key
from .protocol import decode, encode
from .voices import context_supported, resolve, transport

ENDPOINT = "wss://openspeech.bytedance.com/api/v3/tts/bidirection"
DEFAULT_VOICE = {
    "speaker": "zh_female_xiaohe_uranus_bigtts",
    "resource_id": "seed-tts-2.0",
    "speech_rate": 0,
    "loudness_rate": 0,
    "context_texts": ["用自然、亲切的语气向用户介绍产品，语速适中，停顿自然。"],
}


def request_params(voice):
    additions = {"aigc_metadata": {"enable": True}}
    if context_supported(voice) and voice["context_texts"]:
        additions["context_texts"] = voice["context_texts"]
    if voice.get("pronunciation_dict"):
        additions["pronunciation_dict"] = {"tone": voice["pronunciation_dict"]}
    return {
        "speaker": voice["speaker"],
        "audio_params": {"format": "mp3", "sample_rate": 24000, "enable_subtitle": True,
                         "speech_rate": voice["speech_rate"], "loudness_rate": voice["loudness_rate"]},
        "additions": json.dumps(additions, ensure_ascii=False),
    }


async def exchange(ws, text, params, idle_timeout=45):
    sid = str(uuid.uuid4())
    audio = bytearray()
    events = []
    counts = {}

    async def receive():
        msg = decode(await asyncio.wait_for(ws.recv(), idle_timeout))
        counts[str(msg.event)] = counts.get(str(msg.event), 0) + 1
        if msg.kind == 15 or msg.event in (51, 153):
            # Payloads can echo request fields; only numeric codes cross the error boundary.
            raise VideoError(f"TTS 服务拒绝请求（event={msg.event}, code={msg.error_code}）。请检查音色权限、额度和 API 配置。")
        if msg.session_id and msg.session_id != sid:
            raise VideoError("TTS 返回的会话编号不匹配。")
        return msg

    async def expect(event):
        msg = await receive()
        if msg.event != event:
            raise VideoError(f"TTS 状态不匹配：等待 {event}，收到 {msg.event}。")

    await ws.send(encode(1))
    await expect(50)
    await ws.send(encode(100, {"event": 100, "req_params": params}, sid))
    await expect(150)

    async def send_text():
        # Chunk size limits client frame size, not the vendor's text allowance.
        for start in range(0, len(text), 200):
            await ws.send(encode(200, {"event": 200, "req_params": {**params, "text": text[start:start + 200]}}, sid))
        await ws.send(encode(102, session_id=sid))

    async def collect():
        while True:
            msg = await receive()
            if msg.kind == 11:
                audio.extend(msg.payload)
            elif msg.event in (350, 351, 364, 152):
                try:
                    value = json.loads(msg.payload)
                except (UnicodeError, ValueError):
                    raise VideoError("TTS 字幕响应不是有效 JSON。") from None
                # Keep only content needed for subtitles and usage, never arbitrary server fields.
                events.append({"event": msg.event, "data": {k: value[k] for k in
                               ("text", "words", "start_time", "end_time", "subtitles", "usage") if k in value}})
            if msg.event == 152:
                return

    async with asyncio.TaskGroup() as group:
        group.create_task(send_text())
        group.create_task(collect())
    await ws.send(encode(2))
    await expect(52)
    if not audio:
        raise VideoError("TTS 会话已结束，但没有返回音频；未保存成功结果。")
    return bytes(audio), events, counts


async def synthesize(text, voice, key, timeout=240):
    if transport(voice) == "http":
        from .http_tts import synthesize_http
        return await synthesize_http(text, voice, key, request_params(voice), timeout)
    # The library's debug logger can contain authentication headers.
    logger = logging.Logger("product_video.transport", level=logging.CRITICAL + 1)
    headers = {"X-Api-Key": key, "X-Api-Resource-Id": voice["resource_id"],
               "X-Api-Connect-Id": str(uuid.uuid4())}
    try:
        async with asyncio.timeout(timeout):
            async with connect(ENDPOINT, additional_headers=headers, open_timeout=20,
                               close_timeout=5, max_size=8 * 1024 * 1024, logger=logger) as ws:
                return await exchange(ws, text, request_params(voice))
    except InvalidStatus as e:
        code = e.response.status_code
        advice = "请检查本地 API Key 和语音服务授权。" if code in (401, 403) else "请检查服务额度或稍后手动重试。"
        raise VideoError(f"TTS 连接失败（HTTP {code}）。{advice}") from None
    except (TimeoutError, ConnectionClosed, InvalidHandshake, OSError) as e:
        raise VideoError(f"TTS 连接未完成（{type(e).__name__}）；未自动重复计费请求，可稍后重试。") from None
    except ImportError:
        raise VideoError("系统使用 SOCKS 代理，但缺少代理依赖；请重新运行 pip install -e .。") from None
    except ExceptionGroup as e:
        def first_error(group):
            for err in group.exceptions:
                if isinstance(err, VideoError):
                    return err
                if isinstance(err, BaseExceptionGroup):
                    nested = first_error(err)
                    if nested:
                        return nested
        raise first_error(e) or VideoError("TTS 发送或接收中断；本次结果未完成，可手动重试。") from None


def cache_location(output, chapter, voice):
    effective = dict(voice)
    if "transport" in effective:
        try:
            if effective["transport"] == resolve(effective["speaker"])["transport"]:
                effective.pop("transport")
        except VideoError:
            pass
    signature = digest({"protocol": 1, "text": chapter["narration"], "voice": effective})
    return output / "audio" / signature


def cached_audio(folder):
    audio, meta = folder / "voice.mp3", folder / "metadata.json"
    if not audio.exists() or not meta.exists():
        return None
    try:
        value = json.loads(meta.read_text())
        if value["sha256"] == file_hash(audio) and value["duration"] > 0:
            return value
    except (OSError, ValueError, KeyError, TypeError):
        pass
    raise VideoError("配音缓存损坏；请将对应 audio 子目录移走后重新生成。")


def generate(chapter, voice, output, timeout=240):
    folder = cache_location(output, chapter, voice)
    cached = cached_audio(folder)
    if cached:
        print(f"复用配音：{chapter['id']}", flush=True)
        return folder, cached
    print(f"API 生成配音：{chapter['id']}（{len(chapter['narration'])} 字符）", flush=True)
    begin = time.monotonic()
    audio, events, counts = asyncio.run(synthesize(chapter["narration"], voice, load_key(), timeout))
    folder.mkdir(parents=True, exist_ok=True)
    partial = folder / "voice.pending.mp3"
    try:
        atomic_write(partial, audio)
        duration = audio_duration(partial)
        run(["ffmpeg", "-v", "error", "-xerror", "-i", partial, "-f", "null", "-"], timeout=120)
        partial.replace(folder / "voice.mp3")
        meta = {"duration": duration, "sha256": file_hash(folder / "voice.mp3"),
                "speaker": voice["speaker"], "events": events, "event_counts": counts,
                "elapsed_seconds": round(time.monotonic() - begin, 2), "source": "volcengine-api"}
        write_json(folder / "metadata.json", meta)
        return folder, meta
    finally:
        partial.unlink(missing_ok=True)
