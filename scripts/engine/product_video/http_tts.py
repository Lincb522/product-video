import asyncio
import base64
import binascii
import json
import uuid
from urllib.request import getproxies, proxy_bypass

import httpx

from .common import VideoError

ENDPOINT = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"


class StreamResult:
    def __init__(self):
        self.audio = bytearray()
        self.events = []
        self.done = False
        self.counts = {}

    def feed(self, line):
        if not line.strip():
            return
        try:
            value = json.loads(line)
            code = value["code"]
            if type(code) is not int:
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise VideoError("TTS HTTP 流不是有效响应；未保存不完整音频。") from None
        self.counts[str(code)] = self.counts.get(str(code), 0) + 1
        if code not in (0, 20000000):
            raise VideoError(f"TTS 合成失败（code={code}）。请检查该音色权限、资源版本与额度。")
        if self.done:
            raise VideoError("TTS 在结束标记之后仍返回内容。")
        if value.get("data"):
            try:
                self.audio.extend(base64.b64decode(value["data"], validate=True))
            except (binascii.Error, ValueError, TypeError):
                raise VideoError("TTS 音频数据无法解码。") from None
        sentence = value.get("sentence")
        if isinstance(sentence, dict) and sentence.get("words"):
            self.events.append({"event": 364, "data": {k: sentence[k] for k in
                                ("text", "words") if k in sentence}})
        self.done = code == 20000000

    def result(self):
        if not self.done or not self.audio:
            raise VideoError("TTS HTTP 音频流未完整结束；没有保存成功结果，可手动重试。")
        return bytes(self.audio), self.events, self.counts


async def synthesize_http(text, voice, key, params, timeout=240):
    headers = {"X-Api-Key": key, "X-Api-Resource-Id": voice["resource_id"],
               "X-Api-Request-Id": str(uuid.uuid4())}
    proxies = getproxies()
    proxy = None if proxy_bypass("openspeech.bytedance.com") else proxies.get("https", proxies.get("all"))
    if proxy and proxy.startswith("socks://"):
        proxy = proxy.replace("socks://", "socks5://", 1)
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(proxy=proxy, timeout=httpx.Timeout(45, connect=20), follow_redirects=False) as client:
                async with client.stream("POST", ENDPOINT, headers=headers,
                                         json={"req_params": {**params, "text": text}}) as response:
                    if response.status_code != 200:
                        raise VideoError(f"TTS HTTP 请求失败（HTTP {response.status_code}）。请检查音色权限、API Key 与额度。")
                    result = StreamResult()
                    # Bound individual records as well as the entire request.
                    pending = b""
                    async for chunk in response.aiter_bytes():
                        pending += chunk
                        while b"\n" in pending:
                            line, pending = pending.split(b"\n", 1)
                            if len(line) > 8 * 1024 * 1024:
                                raise VideoError("TTS 响应单条数据过大。")
                            result.feed(line)
                        if len(pending) > 8 * 1024 * 1024 or len(result.audio) > 128 * 1024 * 1024:
                            raise VideoError("TTS 响应超过单章节上限。")
                    result.feed(pending)
                    return result.result()
    except (httpx.HTTPError, TimeoutError, OSError):
        raise VideoError("TTS HTTP 连接中断或超时；没有自动重复计费请求，可手动重试。") from None
