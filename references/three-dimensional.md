# 三维设备与录屏镜头

用户要求 Rotato 类设备展示、真实三维透视、金属边框、双设备构图或镜头环绕时，使用 `step.scene3d`。这是独立的 Three.js / WebGL 2 渲染层，可与原来的七种二维风格、纯文案、旁白和字幕混排。无需 Rotato 或 Blender。Three.js 0.186.0 随 Skill 分发，渲染阶段不从 CDN 加载代码。

## 编排与素材选择

- 先确定要讲的产品功能和实际画面，再选择设备。指定 iPhone 17 Pro Max 用 `iphone-17-pro-max`，16 英寸 MacBook Pro 用 `macbook-pro-16`；通用手机、平板、笔记本仍可用 `phone`、`tablet`、`laptop`，独立界面用按素材比例生成的 `panel`。不要把宽屏界面强行裁成手机屏幕。
- 设备由本项目程序生成；具名设备参照官方机身尺寸比例和外观建模，细部为视觉近似，并非 Apple 官方 CAD 或工业制造模型。保留用户要求的 `classic` 和其他既有镜头，不把整支视频强制换为三维。
- 需要输入、滚动、拖拽中的内容变化时使用真实录屏；截图只用于静态展示和明确标注的模拟操作。三维设备上的录屏不会自动叠加二维鼠标。
- 每段运动留出完整界面的阅读时间。功能操作可用 `motion: still` 或小角度运动；避免在关键操作期间把屏幕转到侧面。自定义关键帧覆盖整个镜头，默认用平滑起止。
- 正文仍按 [文案规范](narration.md) 和 [复核清单](narration-review.md) 处理。三维镜头支持 `content.layout: split`，纯文案镜头单独编排。字幕按已确认旁白生成，不用镜头说明填充旁白。

## 具名设备与素材比例

| 模型 | 外观与比例 | 建议素材 |
| --- | --- | --- |
| `iphone-17-pro-max` | 78 × 163.4 × 8.75 mm 机身比例；灵动岛、横向三摄平台、背板、侧键与 USB-C 外观 | 1320 × 2868 或 440 × 956 的竖屏录屏 |
| `macbook-pro-16` | 355.7 × 248.1 × 16.8 mm 合盖外廓比例；固定 102° 开盖、刘海屏、键盘、扬声器、触控板和接口外观 | 3456 × 2234 或 1728 × 1117 的桌面录屏 |

尺寸与屏幕依据：[iPhone 17 Pro Max 官方规格](https://support.apple.com/en-ie/125091)、[MacBook Pro 官方规格](https://www.apple.com/macbook-pro/specs/)；手机背面依据 [Apple 发布图](https://www.apple.com/newsroom/2025/09/apple-unveils-iphone-17-pro-and-iphone-17-pro-max/)。未捆绑 Apple 产品照片或第三方商业模型。颜色为渲染参考值，不是官方色值：Pro Max 银色 `#bbc0c5`、橙色 `#c76b3a`、深蓝 `#35445f`，Mac 银色 `#aeb2b6`、深空黑 `#353638`。`clay` 仍可用于哑光造型。

每款设备在场景中独立归一化；默认手机高 5.2、Mac 宽 6.8 个单位，并非共同毫米单位。需要真实大小对照时，把手机 `scale` 设为约 `0.60`，Mac 保持 `1`，再调整构图。灵动岛和刘海会真实遮挡屏幕顶端；素材必须留出对应安全区域。默认 `contain` 保留源内容并可能留黑边，不拉伸界面；仅在检查过裁切后使用 `cover`。

## 一个三维镜头

下面是 `chapters[].steps[]` 的一项；`source` 相对项目 JSON，也可以使用绝对路径。配合采集项目时可用 `capture:shot-id` 引用截图。

```json
{
  "at": 0,
  "scene3d": {
    "background": "#e5e3df",
    "lighting": "studio",
    "motion": "orbit",
    "floor": true,
    "camera": {
      "position": [0, 0.6, 13],
      "target": [0, 0, 0],
      "end_position": [0.3, 0.3, 12.6],
      "fov": 32
    },
    "devices": [{
      "model": "iphone-17-pro-max",
      "source": "assets/screen.mp4",
      "position": [0, 0, 0],
      "rotation": [6, -14, -5],
      "scale": 1,
      "finish": "metal",
      "color": "#bbc0c5",
      "fit": "contain",
      "in": 0,
      "rate": 1
    }]
  }
}
```

| 字段 | 支持范围 / 含义 |
| --- | --- |
| `devices` | 1–4 台设备，每台独立素材和姿态 |
| `model` | `iphone-17-pro-max`、`macbook-pro-16`、`phone`、`tablet`、`laptop`、`panel`；默认 `phone` |
| `source` | 可读图片，或 MP4 / MOV / WebM / M4V；视频先用 FFmpeg 统一解码与显示方向 |
| `fit` | 默认 `contain` 保留完整界面；`cover` 会裁掉溢出部分，只在明确需要时使用 |
| `position` | 世界空间 `[x,y,z]`，Y 向上，Z 正方向朝向默认相机 |
| `rotation` | X/Y/Z 欧拉角，单位为度；显式 0→360 可完整旋转 |
| `scale` | 0.1–5；多设备需逐帧检查相互遮挡和画面边界 |
| `finish` | `metal` 金属或 `clay` 哑光 |
| `lighting` | `studio` 主光与轮廓光、`soft` 较柔和、`rim` 较强冷色轮廓光 |
| `motion` | `orbit` 环绕、`reveal` 侧面展开、`push` 推近、`rise` 升起、`still` 固定 |
| `camera` | 起止位置、起止观察目标 `target` / `end_target`、15–75 度视场角 |
| `in` / `rate` | 仅视频使用：开始秒数 / 0.25–4 倍速。到达素材结尾后保持末帧，不默认循环 |

屏幕视频按当前镜头的时间取样，与渲染速度无关；预览可向前或向后取帧。视频自带音轨不混入旁白，避免意外重叠。原来 `step.camera`、`cursor`、`interaction`、`images` 不用于三维镜头。

设备自定义 `keyframes` 时，预设运动不再作用于该设备。每项必须填写 `at`、`position`、`rotation`；`scale` 可省略。`at` 是镜头内 0–1 的进度，首尾必须为 0 和 1，中间严格递增；`ease` 为到达该帧的插值方式，默认 `smooth`，也可 `linear`。

```json
"keyframes": [
  {"at": 0, "position": [0, -0.3, 0], "rotation": [8, 55, -8]},
  {"at": 0.6, "position": [0, 0, 0], "rotation": [4, -12, -4]},
  {"at": 1, "position": [0, 0, 0], "rotation": [4, -12, -4]}
]
```

## 同屏文案

在同一步增加 `content`；引擎为设备分配另一半视口。文字使用视频风格的文字颜色，`scene3d.background` 应与其保持足够对比。

```json
"content": {
  "layout": "split",
  "image_side": "right",
  "headline": "整理项目记录",
  "body": "输入关键词查找记录。\n标记后可在收藏列表查看。"
}
```

正文仍使用已有的完整文本测量与换行，底部留给字幕。三维镜头不重复绘制二维的页眉和截图标签。

## 真实网页录屏

复用 [capture.json](capture.md) 的 web 计划，先观察真实控件再填定位器。第一项只声明初始 `ready`，后面的项目执行操作。只录制当前任务已授权的产品操作。

```sh
"$RUN" record-web capture.json --output assets/screen.mp4
"$RUN" check project.json
"$RUN" preview project.json
"$RUN" render project.json
```

`record-web` 不调用 TTS。输入按字符录制，滚动使用连续页面滚动，点击保留实际页面反馈；文件旁保存 `.recording.json`，含计划哈希、时长和完整解码结果。计划事件为观察用墙钟时间，精确剪辑应检查录屏关键帧。当前不支持视频遮盖 `mask`，只使用已去除私人内容的演示页面；原生 App 可直接提供已准备好的录屏文件。现有 macOS 自动采集仍为截图。

## 验收与边界

1. 先运行 `check`，确认素材、设备参数、文字和录屏起点合法。
2. 在 `preview/index.json` 检查每个三维镜头的开始、中间、结束，以及三维/二维之间的转场。检查设备边界、屏幕完整性、正文与字幕的位置。
3. 用录屏中的一个实际动作检查操作前、动作中和结果画面，确认相机运动没有遮住操作。
4. 导出后检查 `verification.json` 中的 `renderer_3d`，并观看完整短片；完整解码成功不等于视觉或听感已验收。

macOS 使用 Chromium 的 Metal 路径；其他平台由 Chromium 提供 WebGL 2。首次初始化比后续帧慢；不支持 WebGL 2 时会明确失败，不输出二维替代图冒充三维。

当前输出沿用 16:9、H.264/AAC MP4、24–60 fps 的既有管线。已实现真实几何、透视、环境反射和投影；尚未实现光学景深、运动模糊、透明背景导出、GLB 导入、设备盖板动画或 Rotato 的完整交互编辑器。不要把当前能力写成与 Rotato 完全等价。

## 无配音验收样片

在引擎目录，用已安装依赖的 Python 运行：

```sh
python examples/render_studio_demo.py /path/to/studio-review --width 1920
```

脚本启动临时本机页面，录制仓库内明确标注的交互测试界面，生成 24 秒、30 fps 的三维短片、项目 JSON、关键帧、时间轴和解码报告。使用 `--preview-only` 仅导出关键帧。该样片不调用配音 API；正式配音仍走 `build` 或已有配音的 `render`。
