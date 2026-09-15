# Product Video 2.2 验证记录

验证日期：2026-09-15。环境：macOS Intel、Python 3.12、Node.js 26.8.1、FFmpeg 9.0.1。新增运行依赖固定为 Hyperframes 0.8.40、GSAP 3.14.2，检查与渲染使用 Chromium 152.0.7977.30。

Hyperframes 将独立 HTML 镜头渲染为视频片段；Remotion 继续管理整片、旁白、字幕、音乐和音效。验证覆盖这条实际集成路径。

| 范围 | 已验证结果 |
| --- | --- |
| 原有 Python 引擎 | 117 项测试通过，包含截图操作、七种二维风格、采集录屏、三维场景、语音缓存与字幕 |
| 新增集成测试 | 7 项通过，覆盖共享帧边界、旁白时间、采集引用、字段互斥、素材检查、编译绑定、资源排除与浏览器检查结果解析 |
| HTML 浏览器检查 | 图文入场、流程展开、遮罩对照均经过 Hyperframes 实际 `check`，解析完成的运行时与布局检查结果后渲染 |
| 混合镜头样片 | 3 个 HTML 镜头、2 个截图操作片段和 1 个内容镜头；675 帧、1280×720、30 fps、约 22.55 秒；H.264/AAC 完整解码通过 |
| 带旁白的集成样片 | HTML、Shotcraft 和内容镜头混排；573 帧、约 19.16 秒，2 章已有小何配音、8 条字幕；H.264/AAC 完整解码通过 |
| 实际成片画面 | 从上述两份 MP4 分别提取 21、15 张关键帧，检查文字、截图、主题对照、操作前后状态和字幕安全区 |
| 1080p 减少动态效果 | 遮罩对照在 1920×1080 下通过运行时、布局和对比度检查；0.5、3.5、4.365 秒的三张实际浏览器快照像素一致，静态对照保持可读 |
| 缓存复用 | 同一带旁白项目再次生成工程，断言 TTS 调用与 Hyperframes 检查/渲染调用均为 0；源素材哈希与两份最终成片的记录一致 |
| 工作台 | TypeScript / Vite 构建与原有集成检查通过，包含 15 种转场及 330.9 秒导出完整解码；构建仍有已有的大体积 bundle 提示 |
| 安装 | 本机 Skill 安装新增锁定依赖与浏览器后，CLI 项目检查通过；Skill 结构检查通过 |

[无旁白混合样片](assets/hyperframes-demo.mp4) · [实际画面预览](assets/hyperframes-poster.webp)

样片使用明确标记的演示界面。带旁白样片复用已有音频及其时间戳；本次没有新发起配音请求。

## 成片校验值

无旁白混合样片：

```text
115be73d2653d8d23cae7bc7dbad61e3f7d40d1899e8d387a2ada95914199139
```

带小何配音的集成样片：

```text
a8bb1590736255201b75b7e5580f1b9c8347612306f017bc62f6a4029f1c0a2b
```

## 复现

先按 [安装说明](../README.md#安装) 配置运行环境，在空目录生成演示项目：

```sh
cd scripts/engine
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python examples/render_hyperframes_demo.py ~/Movies/product-video-html-demo
./run.sh review ~/Movies/product-video-html-demo/project.json

cd ../../vendor/video-shotcraft/workbench
npm run build
npm run test:integration
```

`--width 1920 --reduced-motion` 可生成减少动态效果的 1080p 项目。单个 HTML 工程的检查与快照命令见 [Hyperframes 说明](../references/hyperframes.md)。

## 验证边界

- 抽帧复核与完整解码已经完成；连续播放观感和主观听感仍为 `unverified`。
- 新增路径验证了 GSAP / CSS 遮罩与本地图片素材，未逐一验证上游所有动画适配器、媒体格式、目录组件或 HDR 功能。
- 上游目录搜索在本机出现部分资源抓取超时，返回结果不代表完整目录；本次本地 HTML 镜头不依赖这些远程资源。
- 主时间轴仍支持 16:9；本次未验证 Windows、Linux 或其他画幅。
- HTML 内的声音不进入成片，统一使用 Product Video 音轨。主工作台将 HTML 显示为视频片段；修改镜头内部构图需编辑源 HTML 后重新渲染。
