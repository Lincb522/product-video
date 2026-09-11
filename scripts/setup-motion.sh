#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
RUNTIME="$ROOT/vendor/video-shotcraft/workbench"
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo '镜头运行库需要 Node.js 22 或更高版本及 npm。' >&2
  exit 1
fi
if ! node -e 'process.exit(Number(process.versions.node.split(".")[0]) < 22 ? 1 : 0)'; then
  echo '请升级到 Node.js 22 或更高版本后重新运行 setup-motion.sh。' >&2
  exit 1
fi
cd "$RUNTIME"
npm ci --no-audit --no-fund
node scripts/gen-index.mjs
echo 'Remotion 镜头运行库已安装。未调用语音 API。'
