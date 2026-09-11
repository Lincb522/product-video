# 内容镜头

`steps[].editorial` 是 2.1 新增的产品内容组件，使用 Remotion 与 Shotcraft 运动基础，和旁白、字幕、音效共用一条时间轴。它直接接收目标产品的图片、标签和正文，无需复制某个项目的 TSX。标题、布局和运动由 Agent 按内容选择。

## 配置

```json
{
  "at": 0,
  "editorial": {
    "layout": "overview",
    "headline": "从项目管理到内容发布",
    "items": [
      {"source": "capture:projects", "label": "项目管理"},
      {"source": "capture:editor", "label": "内容编辑"},
      {"source": "capture:publish", "label": "发布结果"}
    ],
    "focus_at": [0.1, 0.32, 0.56]
  }
}
```

这里的功能名只说明格式，必须替换成目标产品已核实的内容。`capture:*` 由采集步骤解析；使用已有图片时填写相对项目路径。图片包含 EXIF 方向时按显示方向计算宽高。全局 `product.name`、可选 `product.logo` 和 `video` 的字体、四种颜色用于内容镜头。

| `layout` | 图片数量 | 布局与运动 |
| --- | --- | --- |
| `overview` | 2–6 | 功能网格，依次将重点图放大，其余图移到侧栏，结束时回到总览 |
| `portal` | 2–6 | 从网格进入第一张图，用于总览之后的具体功能 |
| `fan` | 2–3 | 同组图片入场、扇形展开，文字在左侧 |
| `full` | 通常 1 | 宽幅图片，上方标题与短说明 |
| `side` | 通常 1 | 左侧说明，右侧图片 |
| `pair` | 2 | 两图并排，或同视图遮罩比较 |

`headline` 必填，最多 32 字符；`eyebrow` 最多 36 字符；`notes` 最多三条，每条最多 24 字符；图片标签最多 20 字符。总览和入口图必须有标签。引擎按项目字体检查正文安全区，过多换行或说明会在配音前报错；字符上限不等于应填满的字数，仍需检查实际画面。不要靠上限填满画面。

`overview`、`portal`、`fan` 自带运动，不额外填 `motion`。`full`、`side` 的 `motion` 可选择：

| 效果 | 用途 |
| --- | --- |
| `none` | 完整、稳定地阅读界面 |
| `panel-assemble` / `row-embed` | 按实际分栏或内容行拼合 |
| `camera-tour` | 小幅推近并平移视点 |
| `focus-pull` / `orbit-level` | 焦点回归、倾斜回正 |
| `mask-reveal` / `panel-unfold` | 遮罩展示、线条展开为面板 |
| `content-lift` / `pull-back` | 提升重点内容、拉远呈现整体 |
| `paired-slide` | 带轻微旋转的横向入场 |
| `filmstrip` | 2–6 张图片连续平移切换 |
| `card-flip` | 两张图片作为正反面翻转，第二张为结果 |

`pair` 仅使用 `none`、`paired-slide` 或 `comparison-wipe`。`comparison-wipe` 需要相同比例的两张对应截图，展示主题或同视图状态变化；不同页面用普通并排比较。`video.reduced_motion: true` 显示完成状态，旁白播放速度保持不变。

## 对齐真实内容

`focus_at` 只适用于 `overview`，每张图对应一个严格递增的 0–0.9 比例。它以**当前镜头完整时长**为基准，包括该镜头拥有的片头和片尾停留；根据实际字幕时间戳换算：

```text
focus_at = (目标句开始的全片秒数 − 镜头开始秒数) / 镜头时长
```

省略时均匀安排聚焦。正式介绍应按旁白检查并调整，不能假定均匀切换恰好对应讲解。长总览的后半段继续按实际时长运动，不受组件默认六秒预览长度限制。

`slices` 定义 `row-embed` 的纵向边界或 `panel-assemble` 的横向边界：3–9 个严格递增比例，起点 0、终点 1。例如左侧栏占截图宽度 20% 时，`[0, 0.2, 1]` 将其与内容区分开。省略时按三等分；只有实际界面适合等分时才沿用默认值。

一个步骤只能有一个主要视觉来源。`editorial` 不与该步骤的 `images`、`content`、`scene3d`、`shotcraft` 或指针字段叠加；需要点击因果时另用原生截图操作步骤，连续变化用真实录屏。

## 工作台与验证

`prepare-motion` 将图片按内容哈希复制到工程素材目录，生成 `pv-editorial` 时间轴片段。工作台可调片段时长、顺序、标题与颜色；`items`、`layout`、`motion`、`focus_at` 和 `slices` 在源项目 JSON 中调整后重新生成，当前属性面板未提供这些嵌套字段的完整表单。

```sh
"$RUN" check ./project.json
"$RUN" prepare-motion ./project.json
"$RUN" preview ./project.json
"$RUN" render ./project.json
"$RUN" review ./project.json
```

除非先运行 `voice` 或使用 `--generate-voice`，这些命令只使用已有配音。预览额外采样入场中段和每次总览聚焦。`review` 检查保存的成片哈希，再从 MP4 提取相同帧，覆盖长视频的大量复核点；自动解码不替代目视检查。

离线示例使用明确标记的演示界面和静音音轨，不访问语音服务，也不是某个真实产品的宣传片：

```sh
cd "$SKILL/scripts/engine"
.venv/bin/python examples/render_editorial_demo.py ~/Movies/editorial-demo --mode preview
./run.sh render ~/Movies/editorial-demo/project.json
./run.sh review ~/Movies/editorial-demo/project.json
```

布局回归示例：

```sh
.venv/bin/python examples/check_editorial_layouts.py ~/Movies/editorial-demo/project.json --output ~/Movies/editorial-layout-check
```

该入口使用明确的边角标记测试图，覆盖 2/6 项总览、横竖图片、长标题、720p/1080p、30/60 fps、长镜头末段与 reduced motion；不会修改产品图片或生成旁白。
