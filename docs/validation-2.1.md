# Product Video 2.1 验证记录

验证日期：2026-09-11。环境：macOS、Node.js 26.8.1、Remotion 4.0.484。Shotcraft 快照继续固定为 `5e71af35a2daee492dd3ea93e5e8903f32dcd13c`。

| 范围 | 已验证结果 |
| --- | --- |
| Python 引擎 | 117 项测试通过，包含旧版图片操作、七种二维风格、网页采集录屏、三维场景、语音缓存和字幕边界 |
| 新内容镜头 | 六种布局的配置约束、真实素材绑定、采集引用、切片顺序、总览聚焦、同视图对照比例和正文安全区检查通过 |
| 共享时间轴 | 内容镜头直接进入 Remotion 时间轴；图片按哈希复制，旁白和字幕共享帧边界；长镜头时长不受六秒目录预览限制 |
| 实际内容样片 | 17 个镜头，1280×720、30 fps、H.264/AAC，文件时长约 77.55 秒，完整解码通过；使用标明用途的演示界面和静音 |
| 成片复核 | `review` 从上述 MP4 提取 106 张镜头关键帧；核对总览、卡片展开、图文说明和主题对照等实际画面 |
| 大量抽帧 | 115 个目标帧实际提取成功；逐帧选择与单帧参考的像素一致，越界请求不发布不完整结果 |
| 布局边界 | 720p / 30 fps 与 1080p / 60 fps 共 38 张测试帧，覆盖 2/6 项总览、横竖图片、长标题与说明、图文并排和双图对照 |
| 运动与图片完整性 | 完整界面、并排与图文镜头保留四角测试标记；reduced motion 前后像素一致；长总览后半段与结尾有正确变化；跨规格同时间画面检查通过 |
| 工作台构建 | TypeScript 与 Vite 构建通过；仍有已有的大体积 bundle 提示，不影响此次构建结果 |
| 导出回归 | 330.9 秒 H.264/AAC 测试文件通过工作台共用的完整解码校验；小数时长转换为整数进程超时，错误画幅被拒绝 |
| 原有 JS 集成 | 15 种转场端点、方向、内容替换范围、错误映射与目录时长回归通过 |
| Skill 结构 | `skill-creator` 的 `quick_validate.py` 检查通过 |

本次内容样片 SHA-256：

```text
aa30abe2fac05c7afbec661928f90d3615a38f8763717f380db24491d0b5779e
```

[内容样片](assets/editorial-demo.mp4) · [四种内容场景截图](assets/editorial-poster.webp)

## 复现

```sh
cd scripts/engine
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python examples/render_editorial_demo.py ~/Movies/editorial-demo --mode preview
./run.sh render ~/Movies/editorial-demo/project.json
./run.sh review ~/Movies/editorial-demo/project.json
.venv/bin/python examples/check_editorial_layouts.py ~/Movies/editorial-demo/project.json --output ~/Movies/editorial-layout-check

cd ../../vendor/video-shotcraft/workbench
npm run build
npm run test:integration
```

示例目录应为空。边界检查使用有颜色标记的测试图片，不将其当作产品素材。生产项目仍需对实际界面和原稿执行目视及听感检查。

## 验证边界

- 此次新增镜头使用静音与已有管线测试，不重新调用付费 TTS，不将静音样片当作旁白听感验证。
- 字体、长标题和两种图片比例的边界检查覆盖上述样本，不表示任意图片或无限长正文都可直接使用。
- 218 个原库组件的完整首中末帧覆盖沿用 [2.0 验证](validation-2.0.md)，本次针对新增内容层及受影响路径进行回归，没有重跑整个原库。
- 新内容镜头的布局、图片列表、聚焦和切片仍通过项目 JSON 设置；工作台尚无这些嵌套参数的完整表单。
- 仅验证所列 macOS 环境；未将其扩展为 Windows、Linux 或所有运行时的验证结论。
