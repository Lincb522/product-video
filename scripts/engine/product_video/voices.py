import json
from importlib.resources import files

from .common import VideoError


def catalog():
    return json.loads(files("product_video").joinpath("data/voices.json").read_text(encoding="utf-8"))


def search(query="", language="", model=""):
    return [v for v in catalog()["voices"]
            if query.casefold() in " ".join([v["id"], *v["names"], *v["languages"], *v["categories"]]).casefold()
            and language.casefold() in " ".join(v["languages"]).casefold()
            and (not model or v["model"] == model)]


def resolve(value):
    key = "".join(value.split()).casefold()
    matches = [v for v in catalog()["voices"] if key in
               ["".join(s.split()).casefold() for s in [v["id"], *v["names"]]]]
    if len(matches) != 1:
        raise VideoError("音色名称不存在或有重名，请用 voices 搜索后选择完整音色 ID。")
    return matches[0]


def settings(value):
    v = resolve(value)
    return {"speaker": v["id"], "resource_id": v["resource_id"], "transport": v["transport"]}


def transport(voice):
    if "transport" in voice:
        return voice["transport"]
    try:
        return resolve(voice["speaker"])["transport"]
    except VideoError:
        return "websocket"


def context_supported(voice):
    try:
        return resolve(voice["speaker"])["context_instructions"]
    except VideoError:
        return voice["resource_id"] == "seed-tts-2.0"
