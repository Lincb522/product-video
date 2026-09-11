# 产品介绍视频生成器

2.1 新项目默认使用 Remotion 镜头编排，支持完整 Shotcraft 库与可编辑工作台；本文保留原有采集、语音和截图项目字段。新镜头字段、音频轨和工作台见 [镜头与语音集成](../../references/shotcraft.md)。`schema_version: 1` 默认沿用原合成器，`schema_version: 2` 默认使用 Remotion。

```sh
./run.sh motions --search 转场
./run.sh prepare-motion project.json
./run.sh studio project.json
```


从产品真实界面到带配音和字幕的介绍视频。Skill 负责整理有依据的文稿和采集计划，引擎执行后台截图、首次配音配置、合成和导出。

- **后台截图**：网页用独立无头浏览器按步骤导航、点击、搜索和滚动；macOS 按窗口 ID 采集，支持指定控件的后台操作，不主动激活应用或移动系统鼠标。每张图等待目标状态，记录时间、尺寸和 SHA-256。
- **首次配置**：自动打开本机设置页，提供豆包语音 Key 获取指引。粘贴一次后保存并继续，已有配置自动沿用。
- **配音角色**：内置官方音色表的 547 个不同音色 ID，支持名称、语言、模型搜索，交互选择和短试听。小何 2.0 是默认值，不是唯一选项。
- **画面**：`classic`、`product`、`promo`、`tutorial`、`cinema`、`gallery`、`minimal` 七种风格；15 种切换方式、局部聚焦、完整截图与两图对照。章节与步骤可以分别覆盖预设，默认不裁边。
- **三维设备与录屏**：iPhone 17 Pro Max、16 英寸 MacBook Pro，以及通用手机、平板、笔记本和屏幕面板；真实透视、金属/哑光材质、环境反射、设备投影、多设备与关键帧。`record-web` 可录制实际网页操作，`scene3d` 可导入图片或录屏。与原有文案、旁白和字幕混排，见 [三维镜头](../../references/three-dimensional.md)。
- **模拟操作**：曲线移动、停留、按下反馈，再显示真实结果；支持指针拖动及真实网页控件坐标。视频内标注“操作演示”，静态截图不能还原输入、滚动或拖动中的内容变化。参数与适用场景见 [镜头与动效](../../references/motion.md)。
- **字幕**：中文、英文使用 API 返回的字级时间戳。其他语言可提供手动时间轴，或明确关闭字幕。字幕对不上原稿时会保留配音并停止渲染，不估算一个时间轴冒充对齐。
- **导出**：16:9，默认 1080p / 30 fps，H.264 + AAC MP4，附 SRT、配音、关键帧和校验报告。
- **重复运行**：相同文稿和配音设置复用已验证音频。改截图、转场、颜色不重新合成语音。网络失败不自动重复调用计费接口。

直接调用脚本需要文稿和计划；通过 Skill 使用时由 Agent 根据真实产品整理这些内容。示例界面仅用于理解格式，正式视频自动采集目标产品的实际界面。

## 内容编排与成片复核

完整产品介绍先建立功能总览，再沿操作流程展开；版式与镜头按内容选择。2.1 新增 `steps[].editorial`，提供六种内容版式、逐行/分栏展开、推近回正、遮罩对照、翻面和连续浏览，图片与说明来自当前项目。配置与离线示例见 [内容镜头](../../references/editorial.md)，分镜决策见 [内容组织](../../references/storytelling.md)。

`review PROJECT` 从 `output/latest.json` 指向的已验证 MP4 提取复核帧；保存成片哈希与帧号，可检查入场、总览逐项聚焦、操作结果和长视频末段。它不会调用语音 API，也不自动宣称视觉与听感通过。

## 全自动制作

对 Agent 说：

> 使用 $product-video，为这个产品做一支介绍视频。自动采集当前界面，后台静默截图，配音用小何 2.0。

提供产品网址或应用名称，以及要介绍的功能即可。Agent 核对实际界面，整理文稿和采集计划；无需用户自己找图或手写 JSON。

```sh
./run.sh auto /path/to/project.json
```

执行顺序为后台采集 → 缺失密钥时首次引导 → 分章配音 → 字幕 → 视频校验。网页登录单独打开准备窗口，登录后关闭，再无头截图。macOS 不拉前台、不移动系统鼠标；目标窗口不可采集或应用要求前台操作时停止，不退回全屏截图。

视频项目可增加 `"capture": "capture.json"`，图片使用 `"capture:overview"` 引用采集计划的画面 ID。完成后 `.captures/latest.json` 指向解析后的项目和采集清单，原项目保持不变。仅采集可运行 `capture PROJECT`；后续单独 `check` / `voice` / `render` 使用采集输出的项目。

完整计划格式见 [自动采集说明](../../references/capture.md)。浏览器和系统权限仍受所在环境约束；登录、验证码、服务开通和付款由用户在提示时确认。

## 本机直接使用

在本目录运行：

```sh
./run.sh voices --search 小何
./run.sh voices --language 英语
./run.sh select-voice examples/demo/project.json
./run.sh build examples/demo/project.json
```

`select-voice` 会让你搜索并选择角色，保存到项目。也可以直接指定：

```sh
./run.sh select-voice examples/demo/project.json 'Vivi 2.0'
./run.sh select-voice examples/demo/project.json '小何 2.0'
```

首次修改前的项目保存在同目录 `project.json.before-voice`。选择不会调用 API。

只想本次更换、不修改项目：

```sh
./run.sh build examples/demo/project.json --voice 'Vivi 2.0'
```

## 全部配音角色

音色表来自[火山引擎官方音色列表](https://docs.volcengine.com/docs/6561/1257544?lang=zh)，采集于 2026-09-09，文档更新日期为 2026-08-31。552 条公开 TTS 记录合并同 ID 的别名后，共 **547 个角色：2.0 音色 444 个，1.0 音色 103 个**。官方另列的 25 条 S2S 对话音色不是文本配音音色，不混入列表。账号私有的复刻音色也不在公开列表中。

```sh
# 完整列表，没有默认截断
./run.sh voices

# 按名称、语言或版本筛选
./run.sh voices --search 小何
./run.sh voices --language 日语
./run.sh voices --model 1.0

# 导出，已存在的文件不会被覆盖
./run.sh voices --csv /tmp/配音角色.csv
./run.sh voices --json

# 生成短试听。会使用 API 额度；相同文字与角色复用缓存
./run.sh preview-voice --voice '小何 2.0' --text '根据介绍稿生成配音与字幕，并按章节合成产品视频。'
./run.sh preview-voice --voice Bill --text 'Choose a voice for your product introduction.'
```

返回的 `voice.mp3` 可直接打开试听。完整角色表也在 [examples/voices.csv](examples/voices.csv)，可用 Numbers 或 Excel 打开。

角色有重名时使用完整音色 ID。不同语言请写对应语言的文稿，脚本不会把文稿自动翻译成另一种语言。

**音色可选不代表账号已开通该音色。** 根据官方表，Context 类型中仅支持单向流的角色使用 HTTP 接口；1.0 音色使用对应的 1.0 资源。其他默认使用双向 WebSocket。额外授权、旧版资源、额度限制以账号实际 API 响应为准，失败时不会悄悄换一个角色。目录覆盖的角色未逐个合成验证；角色是否可用，以当前账号的服务授权和接口响应为准。

新增的官方音色、账号私有的已授权复刻音色可直接在项目里填写 `speaker`、对应 `resource_id` 和 `transport`。不要把公开音色 ID 当作账号授权凭据。

## 新建其他产品

```sh
./run.sh init ~/Movies/my-product-intro
```

修改新目录里的 `project.json`，将 `assets/` 图片换成真实素材：

```json
{
  "schema_version": 1,
  "product": {"name": "你的产品", "logo": "assets/logo.png"},
  "output": "output",
  "voice": {
    "speaker": "zh_female_xiaohe_uranus_bigtts",
    "speech_rate": 0,
    "loudness_rate": 0,
    "context_texts": ["语气专业、平稳，发音清晰，语速适中，按语义自然停顿。重音克制，陈述句自然收尾，避免闲聊、促销和夸张播报。"]
  },
  "video": {
    "style": "product",
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "transition": 0.6,
    "chapter_pause": 0.7,
    "background": "#17191f",
    "surface": "#23262e",
    "foreground": "#f8f6f2",
    "accent": "#d5ac86",
    "subtitles": "auto"
  },
  "chapters": [
    {
      "id": "overview",
      "title": "项目工作区",
      "narration": "这里填入已确认的介绍文稿。",
      "steps": [
        {"at": 0, "images": ["assets/before.png"], "labels": ["项目列表"], "cursor": [0.12, 0.25]},
        {"at": 0.5, "images": ["assets/after.png"], "labels": ["项目详情"], "cursor": [0.3, 0.42], "click": true}
      ]
    },
    {
      "id": "themes",
      "title": "主题",
      "narration": "这里介绍实际提供的主题，以及适合使用这些界面的场景。",
      "steps": [
        {"at": 0, "images": ["assets/dark.png", "assets/light.png"], "labels": ["深色", "浅色"]}
      ]
    }
  ]
}
```

文案与默认朗读语气遵守 [文案与旁白规范](../../references/narration.md)。稿件在合成前完成编辑，TTS 仅朗读传入的原稿。项目显式设置的 `context_texts` 优先于默认值；语气参数变化会生成新的配音缓存，已有缓存不删除。

### 配置规则

| 字段 | 含义 |
| --- | --- |
| `product.name` / `logo` | 画面左上角的产品名称、可选标志 |
| `output`、图片路径、`video.font` | 相对 `project.json` 所在目录解析，也可使用绝对路径 |
| `chapters` | 播放顺序。章节 ID 唯一；单章文稿上限 2000 字符是客户端限制，长介绍分章编排 |
| `steps[].at` | 开始展示画面或模拟操作的时间，占本章**配音时长**的比例；第一项 0，后续递增且小于 1 |
| `images` / `labels` | 图片镜头为 1–2 张图片及同数量标签；纯文案镜头可省略图片 |
| `content` | `title` / `bullets` / `split` 正文版式；可与截图和操作镜头混排，详见 [文案镜头](../../references/content.md) |
| `cursor` | 相对原截图的 `[x, y]`，左上角 `[0,0]`、右下角 `[1,1]`，只用于单图 |
| `click` | 兼容旧配置；先在上一张图移动并点击，再切到本步结果图，应预留操作与结果阅读时间 |
| `interaction` / `camera` | 操作时间轴 / 局部运镜；结构见 [镜头与动效](../../references/motion.md) |
| `video.style` | `classic`（原始版）、`product`（默认）、`promo`、`tutorial`、`cinema`、`gallery`、`minimal`；显式字段覆盖预设 |
| `transition` / `chapter_pause` | 转场时长 / 章末留白，单位秒；0 可关闭转场 |
| `width` / `height` / `fps` | 16:9 偶数尺寸，建议 1920×1080 或 1280×720；24–60 fps |
| `encoder` | 默认 `libx264`；Mac 可选 `h264_videotoolbox`，速度/画质请自行对比 |
| `speech_rate` / `loudness_rate` | -50 至 100 的整数；0 是正常语速和音量 |
| `context_texts` | 2.0 支持指令的音色可用；旧版与 Context-only 音色不发送不适用的指令 |
| `transport` | 通常不必填；自动匹配音色，可显式选 `http` 或 `websocket` |
| `resource_id` | 通常由音色确定；1.0 并发版可显式填 `seed-tts-1.0-concurr`，须已有对应授权 |

文案正文放在 `steps[].content`，旁白仍在 `chapters[].narration`，字幕继续跟随旁白；纯文案项目不要求图片。正文超出安全区会在配音前报错，需拆分画面。

图片镜头默认使用完整截图等比放入画面；横竖比例不同会留边。显式 `camera.zoom` 用于局部放大，需检查目标文字完整性。过长的标题会缩至最低字号，仍放不下时明确报错，不省略文字。

### 其他语言与手动字幕

配音角色的语言范围与自动字幕的语言范围不是一回事。当前官方接口自动字幕只承诺中文、英文。其他语言配音仍可生成，视频可以明确设置：

```json
"video": {"subtitles": "none"}
```

或在该章节增加已对齐的字幕，时间相对该章 MP3 开头，单位为秒：

```json
"captions": [
  {"start": 0.2, "end": 2.8, "text": "这句字幕对应的完整文字。"},
  {"start": 3.1, "end": 5.4, "text": "下一句字幕。"}
]
```

章节 `captions` 优先于全局设置；字幕不能重叠或超出音频时长。它也可用于数字读法、外文缩写、发音词典引起的字面不一致。`voice.pronunciation_dict` 可填官方支持的规则数组，例如 `["北京/(bei3)(jing1)"]`；文本转写会改变读法，必要时需提供手动字幕。

## 制作步骤

```sh
# 1. 只检查，不联网合成
./run.sh check ~/Movies/my-product-intro/project.json

# 2. 分章生成配音，先试听
./run.sh voice ~/Movies/my-product-intro/project.json

# 3. 导出关键帧，检查截图、字幕和位置，不再调用 API
./run.sh preview ~/Movies/my-product-intro/project.json

# 4. 只使用已有配音渲染，不调用 API
./run.sh render ~/Movies/my-product-intro/project.json

# 或把步骤 2–4 合并
./run.sh build ~/Movies/my-product-intro/project.json
```

`output/latest.json` 指向最新已验证的 MP4 与报告。`output/renders/<版本摘要>/` 包含：

- `product-introduction.mp4`：介绍视频，含配音。
- `subtitles.srt`：外挂字幕；视频中也烧录字幕。
- `narration.wav`、`narration.txt`：整段配音及原稿。
- `preview/`：各步骤移动、按下、结果、转场中间态与稳定关键帧；`index.json` 记录对应秒数。
- `timeline.json`、`project.resolved.json`：实际时间轴和配置。
- `verification.json`：尺寸、编码、时长、素材摘要和完整解码结果。视觉与听感审查不会由自动解码冒充通过。

章节间保留静音用于转场，不截断配音。所有输出均在本地；**只有文稿与音色参数发送给火山引擎**，截图不上传。视频与音频保留 AI 配音标识。

API 调用有 20 秒连接、45 秒接收空闲、240 秒整体时限。同一输出目录只允许一个生成进程。API 失败可手动重试；成功的章节缓存仍保留。改文稿或音色会产生新的 API 用量。

## 安装与本地密钥

首次使用需要 Python 3.11+、FFmpeg（包含 ffprobe）和可用字体。以下命令在本目录执行：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m playwright install chromium
./run.sh credentials setup
./run.sh credentials status
```

Mac 默认使用系统中文字体，Linux 可在 `video.font` 指定 Noto CJK。Windows 运行环境未验证。

`credentials setup` 自动打开本机设置页，包含[豆包语音控制台](https://console.volcengine.com/speech/new/overview)与 Key 获取指引。只需登录官网，在所选项目的「开通管理」确认语音合成服务，再在「API Key 管理」复制 Key，粘贴到本机页即可继续。默认小何 2.0 使用语音合成 2.0；不需要为预置角色购买声音复刻槽位。

已有配置直接沿用；更换时用 `credentials setup --replace`。设置页只监听 127.0.0.1，默认等待 15 分钟；取消或超时结束。远程主机需端口转发，或使用 `credentials set` 在交互终端无回显输入。保存到 `~/.config/product-video/credentials.json`，权限 `0600`。后续 API 调用自动读取；无需每次复制密钥。密钥不写进脚本、项目配置、输出报告或分发包。`status` 只查看文件元数据，不输出密钥。当前用户本地配置不随项目移动而丢失。

## 验证

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q product_video
```

测试覆盖音色选择与模型路由、二进制帧、HTTP 结束标记、超时、空音频、错误脱敏、字幕原稿匹配、英文空格、缓存损坏、输出锁、凭据权限、720p/1080p 画面及图片边界。凭据测试使用临时合成密钥，不读取本机真实值。

## 接口依据

- [官方控制台与 API Key 获取](https://www.volcengine.com/docs/6561/1167802?lang=zh)：新版控制台项目与 API Key 管理。
- [Playwright 自动等待](https://playwright.dev/python/docs/locators)、[截图接口](https://playwright.dev/python/docs/screenshots)：网页采集路径。
- [双向 WebSocket](https://docs.volcengine.com/docs/6561/2532486?lang=zh)：2.0 配音及字级时间戳。
- [单向 HTTP](https://docs.volcengine.com/docs/6561/2528925?lang=zh)：单向音色配音。
- [历史版 HTTP 接口说明](https://docs.volcengine.com/docs/6561/1598757?lang=zh)：1.0 资源、成功结束状态与时间戳区别。
- [公开音色列表](https://docs.volcengine.com/docs/6561/1257544?lang=zh)：角色、语言及单向限制。
