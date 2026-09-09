#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ENGINE="$HERE/engine"

if [ "$#" -gt 1 ]; then
  echo '用法：setup.sh [Python 3.11+ 可执行文件路径]' >&2
  exit 2
fi

PYTHON=${1:-}
if [ -z "$PYTHON" ]; then
  for candidate in python3.12 python3.11 python3.13 python3.14 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
      PYTHON=$(command -v "$candidate")
      break
    fi
  done
fi
if [ -z "$PYTHON" ] || ! "$PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
  echo '未找到 Python 3.11+；请把可用的 Python 路径作为参数传入。' >&2
  exit 1
fi

if [ -e "$ENGINE/.venv" ] && [ ! -x "$ENGINE/.venv/bin/python" ]; then
  echo '现有 Skill 虚拟环境不完整；请先检查或移走 .venv，再重试。未删除任何文件。' >&2
  exit 1
fi
if [ ! -x "$ENGINE/.venv/bin/python" ]; then
  "$PYTHON" -m venv "$ENGINE/.venv"
fi
"$ENGINE/.venv/bin/python" -m pip install --disable-pip-version-check -e "$ENGINE"
"$ENGINE/.venv/bin/python" -m pip check
"$ENGINE/.venv/bin/python" -m playwright install chromium
"$ENGINE/run.sh" --help >/dev/null
echo 'Skill 运行环境已就绪。未调用语音 API，也未修改密钥。'
for command in ffmpeg ffprobe; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "注意：尚未找到 $command，渲染视频前需要安装 FFmpeg。" >&2
  fi
done
