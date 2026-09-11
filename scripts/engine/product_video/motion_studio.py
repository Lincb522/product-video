"""Run the integrated motion workbench for one explicitly selected project."""
import fcntl
import os
from pathlib import Path
import subprocess
import sys

from .common import VideoError
from .shotcraft import runtime_root


def serve(project, studio, port):
    if not 1024 <= port <= 65535:
        raise VideoError('工作台端口必须在 1024–65535 之间。')
    wb = runtime_root() / 'workbench'
    with (wb / '.product-video-studio.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise VideoError('当前镜头运行库已有工作台，请先关闭该工作台再打开其他工程。') from None
        env = os.environ | {'PRODUCT_VIDEO_PROJECT': str(project), 'PRODUCT_VIDEO_STUDIO': str(studio),
                            'PRODUCT_VIDEO_PYTHON': sys.executable,
                            'PYTHONPATH': str(Path(__file__).resolve().parent.parent)}
        subprocess.run(['node', str(wb / 'scripts/gen-index.mjs')], cwd=wb, env=env, check=True)
        print(f'Product Video 工作台：http://127.0.0.1:{port}', flush=True)
        proc = subprocess.Popen(['node', str(wb / 'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', str(port)], cwd=wb, env=env)
        try:
            result = proc.wait()
            if result:
                raise VideoError(f'工作台启动或运行失败（退出码 {result}）。')
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
