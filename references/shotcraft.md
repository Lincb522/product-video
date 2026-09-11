# Shotcraft 镜头与旁白

Product Video 2.0 的新项目使用 Remotion 主时间轴。`vendor/video-shotcraft` 内含完整上游源码、镜头说明、纹理、音效和可编辑工作台。上游快照固定到 `5e71af35a2daee492dd3ea93e5e8903f32dcd13c`；不在制作过程中自动拉取或更换效果。

## 选择镜头

```sh
"$RUN" motions --search 转场
"$RUN" motions --search 开场
"$RUN" motions --kind sfx --search soft
"$RUN" motions --kind bgm
```

`motion-catalog.json` 记录 218 个运行镜头、157 张镜头卡对应的 214 个画廊样式，以及每个组件的时长、源文件和分类。目录生成会检查画廊映射，缺失时直接失败。目录有条目只证明已经注册，视觉质量仍需渲染检查。

按内容选效果：开场与品牌、文字、界面登场、运镜与空间、数据、交互、转场、节奏、光效、收尾。先确定要讲的功能与对应画面，再选择效果；不要将每种效果塞进普通产品介绍。用户要求完整效果展示时按分类编排。

## 项目结构

```json
{
  "schema_version": 2,
  "product": {"name": "目标产品"},
  "output": "output",
  "voice": {"speaker": "zh_female_xiaohe_uranus_bigtts"},
  "video": {"width": 1920, "height": 1080, "fps": 30, "style": "product"},
  "audio": {"sfx": [
    {"source": "shotcraft:sfx/transition/transition-soft.mp3", "start": 3.2, "volume": 0.12}
  ]},
  "chapters": [{
    "id": "overview",
    "title": "项目编排",
    "narration": "从产品界面选择素材，按介绍内容编排镜头，配合语音和字幕展示使用过程。",
    "steps": [{
      "at": 0,
      "shotcraft": {
        "style": "deck-deal-flyin",
        "media": {"textures/live/card1.png": "assets/screen.png"},
        "timing": "fit"
      }
    }, {
      "at": 0.6,
      "images": ["assets/screen.png"],
      "transition": "focus-dissolve"
    }]
  }]
}
```

`steps[].shotcraft` 参数：

| 字段 | 用途 |
| --- | --- |
| `style` | `motions` 返回的准确样式名；也接受组件名或卡 ID |
| `text` | 原文到新文的映射；按完整原文替换，支持逐字动画拆分前替换 |
| `media` | 原 `staticFile` 路径到实际图片/录屏文件的映射；路径相对项目 JSON |
| `colors` | 原色值到目标色值的映射 |
| `font_family` | 字体；默认加载项目 `video.font` |
| `timing` | `fit` 适配旁白镜头长度，`hold` 原速播放后保留末帧 |

同一步选择 Shotcraft 或原生镜头。不要同时放 `shotcraft` 与 `images`、`content`、`interaction`、`camera`、`scene3d`；需组合时用相邻步骤。截图里的文字是像素，必须更换截图；文字映射不做 OCR。依赖固定截图切片的效果需按真实页面重绑纹理和位置，不能只换一张尺寸完全不同的截图就宣称完成。

工作台的文字、素材、配色控件允许选择原值再填入目标内容。默认图像是上游演示素材，正式成片应替换全部可见演示内容。自定义 SVG 字形只覆盖组件声明的字符集；更换字标时需补齐字形。布局、模型或特殊参数超出内容映射范围时，由 Agent 修改对应 TSX 组件并验证；不能把未知字段当作已支持参数。

## 配音时间轴

1. 使用已有 TTS 配置分章生成声音，复用内容与声音参数相同的缓存。
2. 使用实际音频时长和字级时间戳，生成镜头边界与字幕。
3. `at` 仍是本章声音时长比例；第一个镜头从章节开始，后续镜头按声音比例定位。
4. 所有相邻边界只舍入一次到工程帧；转场在新镜头头部完成，不改变旁白速度。
5. 字幕、旁白、音效、BGM、画面分别上轨。音效/BGM 的 `start`、`duration` 用秒，`volume` 范围 0–2；配乐默认 0.12、音效默认 0.3。

中文、英文字幕仍使用原有字级匹配与校验。其他语言沿用已确认字幕或关闭字幕，不增加未经验证的自动对齐能力。文稿仍遵守 `narration.md` 和 `narration-review.md`。

原生截图操作先渲染为视频片段，保留移动、停留、按下/释放、结果和驻留的时序。操作前一镜头要提供真实的操作前状态。原生三维设备与真实录屏同样作为片段加入主时间轴；它们仍由原 Three.js 引擎负责几何、灯光与录屏取帧。

## 工作台与输出

```sh
"$RUN" check project.json
"$RUN" voice project.json
"$RUN" prepare-motion project.json
"$RUN" studio project.json
"$RUN" render project.json
```

`prepare-motion` 默认只用已有配音；`--generate-voice` 才为缺少缓存的章节调用语音服务。`studio` 打开工程后可编辑内容、轨道、裁剪、速度、转场、字幕、旁白、音效和 BGM。旁白面板生成成功后会更新字幕和镜头长度，保留已编辑的镜头内容与位置。重新生成会以源项目的章节和镜头结构为准；大量手动剪辑前先完成旁白，修改前导出工作台 JSON。

`studio/project.json` 是 Remotion 工作台工程，原始 `project.json` 是 Product Video 配音项目，两者用途不同。工作台导出的 JSON 可重新导入工作台。CLI `render` 从配音项目重新编排；要保留工作台手动剪辑，使用工作台“导出成片”。

CLI 成片位置由 `output/latest.json` 指向；同目录包含 MP4、SRT、确认稿、解析后的配置、可编辑工程和校验报告。工作台“导出成片”将当前剪辑保存到该工作台工程的 `exports/`，并生成同名 `.verify.json`。两条导出路径均完整解码 MP4，并核对画面规格、音轨与总时长；文案、操作因果和听感仍需播放复核。

## 维护与许可

镜头源码在 `vendor/video-shotcraft/demos/`，共享组件在 `assets/lib/`，整合层在 `workbench/src/product-video/`。升级上游时重新核对适配和映射，运行目录生成、TypeScript/Vite 构建、起始/中间/结束帧检查和带旁白的混合成片验证。

保留上游 Apache-2.0 许可证、音频来源与第三方通知。Remotion 和 npm 依赖使用各自的许可；Product Video 的 MIT 不替代它们。
