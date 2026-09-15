#!/bin/sh
set -eu
RUNTIME=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CLI="$RUNTIME/node_modules/hyperframes/bin/hyperframes.mjs"
if [ ! -f "$CLI" ]; then
  echo 'Hyperframes 尚未安装，请运行 Skill 的 scripts/setup-hyperframes.sh。' >&2
  exit 1
fi
export HYPERFRAMES_NO_TELEMETRY=1
case "${1:-}" in
  check|snapshot|render|preview)
    HYPERFRAMES_BROWSER_PATH=$(node "$RUNTIME/browser.mjs")
    export HYPERFRAMES_BROWSER_PATH
    ;;
esac
exec node "$CLI" "$@"
