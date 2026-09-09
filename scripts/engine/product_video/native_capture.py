"""macOS window-only capture with named Accessibility actions."""
import json
from pathlib import Path
import platform
import shutil
import subprocess

from .common import VideoError, file_hash


def native_run(argv, timeout=30):
    try:
        result = subprocess.run([str(x) for x in argv], capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise VideoError('macOS 窗口采集未响应；检查目标应用、辅助功能和屏幕录制权限后重试。') from None
    if result.returncode:
        # AX and application errors may contain private window contents.
        raise VideoError('macOS 窗口采集失败；检查应用是否运行、窗口和控件是否唯一可见，以及辅助功能/屏幕录制权限。不会改截整个桌面。')
    return result.stdout


class NativeCapture:
    def __init__(self, target, root, launch=True):
        if platform.system() != 'Darwin':
            raise VideoError('macos 采集仅支持 macOS；其他桌面系统请使用环境提供的应用截图工具。')
        if not shutil.which('swiftc'):
            raise VideoError('原生窗口采集缺少 Swift 编译工具，请安装 Xcode Command Line Tools；未修改系统。')
        source = Path(__file__).parent / 'data' / 'capture_macos.swift'
        self.helper = Path(root) / 'helpers' / file_hash(source)[:16] / 'capture-macos'
        self.helper.parent.mkdir(parents=True, exist_ok=True)
        if not self.helper.exists():
            pending = self.helper.with_suffix('.pending')
            try:
                native_run(['swiftc', source, '-o', pending], timeout=120)
                pending.replace(self.helper)
            finally:
                pending.unlink(missing_ok=True)
        self.target = target
        permissions = self.call('permissions')
        if not permissions['accessibility']:
            raise VideoError('缺少辅助功能权限：在「系统设置 → 隐私与安全性 → 辅助功能」允许执行 Skill 的宿主，然后重试。不会请求提权或抢占前台。')
        if not permissions['screen_recording']:
            raise VideoError('缺少屏幕录制权限：在「系统设置 → 隐私与安全性 → 屏幕与系统音频录制」允许执行 Skill 的宿主，然后重试。')
        if launch:
            native_run(['/usr/bin/open', '-g', '-b', target['bundle_id']])
        self.call('ready', timeout=20)

    def call(self, command, locator=None, timeout=20):
        args = [self.helper, command, self.target['bundle_id'], self.target.get('window_title', '')]
        if locator:
            args += [locator['role'], locator['name']]
        return json.loads(native_run(args, timeout))

    def inspect(self):
        return self.call('inspect')

    def capture(self, shot, destination):
        for i, action in enumerate(shot['actions'], 1):
            print(f"  操作 {i}/{len(shot['actions'])}：{action['action']}", flush=True)
            self.call(action['action'], action['target'])
        self.call('wait', shot['ready'])
        window = self.call('window')
        native_run(['/usr/sbin/screencapture', '-x', '-o', '-l', str(window['id']), destination])
