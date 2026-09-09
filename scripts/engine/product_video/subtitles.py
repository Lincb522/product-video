import math
import re
import unicodedata

from .common import VideoError


def normalized(text):
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if c.isalnum())


def from_events(events, narration, duration, max_chars=28):
    words = []
    for event in events:
        if event["event"] == 364:
            words.extend(event["data"].get("words", []))
    if not words:
        raise VideoError("API 未返回字级字幕；当前自动字幕支持中文、英文。配音已保留，未伪造字幕时间。")
    clean = []
    last_end = 0
    for word in words:
        try:
            start, end, value = float(word["startTime"]), float(word["endTime"]), word["word"]
            if not isinstance(value, str) or not value or not math.isfinite(start + end):
                raise ValueError()
            if start < last_end - 0.03 or start < 0 or end <= start or end > duration + 0.15:
                raise ValueError()
        except (KeyError, ValueError, TypeError):
            raise VideoError("API 字幕时间戳无效或乱序；配音已保留，请检查该章。") from None
        clean.append({"start": max(last_end, start), "end": min(duration, end), "text": value})
        last_end = end
    expected = normalized(narration)
    actual = normalized("".join(w["text"] for w in clean))
    if not expected or actual != expected:
        raise VideoError("API 字幕与原稿不一致；未自动改写文案，请检查发音词典或该章旁白。")
    # Standalone punctuation has timing but consumes no characters in the normalized script.
    # Attach its interval to the preceding spoken word instead of creating an empty cue.
    spoken = []
    for word in clean:
        if normalized(word["text"]):
            spoken.append(word)
        elif spoken:
            spoken[-1]["end"] = word["end"]
    clean = spoken
    # Use timing from the API, but preserve the approved script's spaces and punctuation.
    positions = [i for i, c in enumerate(narration) for _ in normalized(c)]
    offset, previous = 0, 0
    for word in clean:
        offset += len(normalized(word["text"]))
        boundary = positions[offset] if offset < len(positions) else len(narration)
        word["text"] = narration[previous:boundary]
        previous = boundary
    cues, group = [], []
    for index, word in enumerate(clean):
        group.append(word)
        value = "".join(w["text"] for w in group)
        punctuation = bool(re.search(r"[，。！？；,.!?;]$", word["text"].rstrip()))
        if punctuation or len(value) >= max_chars or index == len(clean) - 1:
            cues.append({"start": group[0]["start"], "end": group[-1]["end"], "text": value.strip()})
            group = []
    return cues


def timestamp(seconds):
    ms = round(seconds * 1000)
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    seconds, ms = divmod(ms, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"


def srt(cues):
    return "\n".join(f"{i}\n{timestamp(c['start'])} --> {timestamp(c['end'])}\n{c['text']}\n" for i, c in enumerate(cues, 1))
