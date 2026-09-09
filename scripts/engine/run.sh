#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  echo '请先创建 .venv 并运行 .venv/bin/python -m pip install -e .' >&2
  exit 1
fi
exec "$ROOT/.venv/bin/python" -m product_video "$@"
