#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
RUNTIME="$ROOT/scripts/hyperframes"
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo 'Hyperframes 需要 Node.js 22+ 和 npm。' >&2
  exit 1
fi
node -e 'if (Number(process.versions.node.split(".")[0]) < 22) { console.error("Hyperframes 需要 Node.js 22+。"); process.exit(1); }'
cd "$RUNTIME"
npm ci --no-audit --no-fund
sh "$RUNTIME/run.sh" browser ensure
echo 'Hyperframes HTML 镜头环境已安装。未调用配音 API。'
