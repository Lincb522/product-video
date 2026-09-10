---
name: product-video
description: "自动制作或修改产品介绍视频：编排文案与真实界面，按需采集网页或 macOS 画面，生成角色配音与字幕、运镜、转场和模拟操作。支持产品演示、节奏宣传、教学演示及声音试听，不用于应用代码开发或纯图标设计。"
---

# 产品介绍视频

从产品目标和介绍需求开始，由 Agent 整理有依据的文稿、编排正文与所需的真实界面、引导首次配音配置并生成视频。交付可播放的 MP4、SRT、原稿和校验结果；用户不用手写采集计划或项目 JSON。

## 先保留当前任务

- 从当前对话和用户指定目录恢复产品、确认过的文稿、素材、配音、主题、语言与输出规格；已有项目继续编辑，不另起一个相似产品。
- 用户只要求改旁白、试听或换角色时，只处理对应步骤，不擅自重做成片。用户确认的文稿不在合成时再次改写。
- 默认在后台静默采集当前真实界面，不主动激活应用、抢占前台或移动系统鼠标；用户要求最新版本或指定主题时，先核对版本、主题和画面状态。读取 [references/capture.md](references/capture.md)，优先执行已观察到的自动采集路径，不把找截图的工作交还用户；环境不具备权限或工具时说明具体缺项，不用旧图或示例 UI 冒充。
- 未指定规格时可用 16:9、1080p、30 fps；保留用户明确规格。其他画幅不在本引擎支持范围，不静默改成横屏。
- 仅缺少关键素材、真实功能依据或用户指定的声音无法定位时，完成独立准备后再问缺失项。

## 本地入口

`SKILL` 为**本次加载的 SKILL.md 所在目录**，不要把安装路径写死在项目里。

```sh
RUN="$SKILL/scripts/engine/run.sh"
"$RUN" --help
"$RUN" credentials status
```

首次使用若缺少运行环境，执行 `sh "$SKILL/scripts/setup.sh"`；也可把已确认的 Python 3.11+ 可执行文件路径作为唯一参数传入。setup 在 Skill 自身的 `scripts/engine/.venv` 安装依赖和 Playwright 专用 Chromium，不修改系统 Python。它不安装 FFmpeg、不开通云资源。首次密钥配置走下面的本机设置页。

生成环境需要 FFmpeg、ffprobe 和可用字体。Mac 默认系统中文字体；非 Mac 需要在项目 `video.font` 指定相应字体。不要为一个打包或检查任务额外调用计费 API。

凭据沿用 `~/.config/product-video/credentials.json`。只用 `credentials status` 查看元数据；不要读取、展示、复制到项目或装入分发包。未配置时读取 [references/first-run.md](references/first-run.md)，自动打开 `credentials setup` 本机设置页，教用户在官网获取 Key，粘贴一次后自动保存并继续。登录、验证码、开通和付款由用户确认；不读取输入框、剪贴板或官网显示的密钥。不要让用户把 Key 发到聊天里。

## 全自动主路径

1. 从用户给出的产品目标和需求取得实际功能依据，按 [文案与旁白规范](references/narration.md) 整理并自查文稿；已有确认稿直接沿用。
2. 按介绍内容编写 `project.json`。需要正文开场、要点、解释或收尾时读取 [references/content.md](references/content.md)，可使用纯文案、图文并排、截图与操作镜头混排；不要求每个镜头都有截图。需要真实界面时观察并编写 `capture.json`，用 `capture:<id>` 关联画面，采集规则见 [references/capture.md](references/capture.md)。风格与动效见 [references/motion.md](references/motion.md)：原始版用 `classic`，增强风格用 `product`、`promo`、`tutorial`、`cinema`、`gallery`、`minimal`；用户未指定时默认 `product`。风格和镜头内容分别选择，不必额外进行风格访谈。
3. 文稿和素材方向确定后运行 `"$RUN" auto /path/to/project.json`：自动截图 → 缺失密钥时引导配置 → 分章配音 → 字幕与视频。没有采集计划的既有截图项目也能使用 `auto`。
4. 沿用同一个进程等待。登录或本机配置界面需要用户完成时仅提示该步骤；完成后自动继续，不要求用户手动串联命令。
5. 查看采集画面与最终成片，确认主题、操作前后状态、文字和字幕。采集器的 ready 控件通过只是加载条件，不等于视觉检查已通过。

已确认文稿不在此过程中再次改写。仅维护/打包 Skill 不触发配音 API；仅改声音不重新采集界面。

## 文稿、角色与画面

需要写或改介绍文案时，读取 [references/narration.md](references/narration.md)；需要把文案放进画面时，再读取 [references/content.md](references/content.md)。只介绍已确认的功能、开发初衷和使用场景；不代编产品经历。画面正文、旁白和试听稿统一采用简洁、专业的陈述句：禁用反问、设问、宣传套话和过度口语，删除重复解释，不自动添加“所有工作都在本地”等空泛收尾。最后一项信息表达完整即可结束。

角色搜索、接口参数、字幕限制、完整项目 JSON 和故障处理见 [scripts/engine/README.md](scripts/engine/README.md)。只按当前需要读取对应部分，不把整张音色表载入上下文。

```sh
"$RUN" voices --search 小何
"$RUN" voices --language 英语
"$RUN" select-voice /path/to/project.json '小何 2.0'
```

- 优先使用用户选定的名称或完整 ID；自动化调用明确传入名称，不停在交互选择提示。只有终端人工使用时才省略名称。
- 用户没选角色时沿用项目已有设置；新项目默认小何 2.0，可随时换。公开列表快照含 547 个不同 TTS ID，1.0、2.0 和单向限制由引擎路由；不把目录存在等同账号已获授权。
- 用户需要试听时用 `preview-voice --voice NAME --text TEXT --output DIR` 生成短样；不要批量合成整个音色目录。试听与 `voice`、`build` 会发送文稿并消耗 API 额度。
- 不因为 403、额度或音色错误自行换声、购买资源或重复请求。保留已成功的缓存，说明失败项。
- `init DIR` 生成的是**示例界面**与配置。正式介绍中使用的界面必须换成真实截图；纯文案镜头无需图片。输出写在用户项目目录，不写回 Skill。
- 鼠标动画是截图上的模拟操作。新项目优先用 `steps[].interaction`，兼容旧的 `cursor/click`；点击或拖动步骤的 `images` 放操作后截图，前一步放操作前截图。引擎先移动、停留、按下，再切结果。`at` 是本章音频时长比例，首项必须是 0；给操作和结果都留时间。
- 网页控件优先在采集计划里声明 `points`，引用真实位置，不凭估计落点。运镜、鼠标和截图共用坐标变换；截图动画不能冒充真实打字、滚动或拖动中的内容变化。
- 多主题展示用真实主题截图；并排展示每次最多两张，其余通过步骤切换。默认完整等比展示；只在明确聚焦某个功能时使用 `camera` 局部放大，检查完整目标与上下文，不裁边掩盖缺失内容。

## 生成与检查

已有配置直接执行对应步骤；新项目由 Agent 编写实际配置，`init` 只用于结构示例。所有文件路径相对项目 JSON 所在目录解析。

```sh
"$RUN" auto /path/to/project.json     # 自动采集、首次配置、配音与视频
"$RUN" capture /path/to/project.json  # 仅采集，输出解析后的 project.json
"$RUN" check /path/to/project.json    # 已有素材项目；不调用 API
"$RUN" voice /path/to/project.json    # 生成各章配音
"$RUN" preview /path/to/project.json  # 已有配音生成关键帧；不调用 API
"$RUN" render /path/to/project.json   # 已有配音生成成片；不调用 API
# 文稿与素材已确认、需要直接成片时：
"$RUN" build /path/to/project.json
```

1. 首先核对文稿与素材，自查信息重复、反问、套话、冗长解释与结尾表态；按文案规范修正新稿后进入已授权的生成流程。短试听可用于新的声音选择，已确认角色不必重复试听。
2. 中文、英文自动字幕使用 API 字级时间戳并检查原稿匹配。其他语言使用用户确认的 `captions` 时间轴，或明确设 `video.subtitles: "none"`；不要编造自动对齐结果。数字、缩写和发音转写出现文本不一致时，保留音频并处理对应字幕，不伪造成功。
3. 同一输出目录不要并行启动生成。长任务沿用同一个进程句柄等待；报错时保留已完成章节，不无限重试计费请求。
4. 用 `output/latest.json` 找到已验证成片。引擎会完整解码 MP4、核对尺寸和时长、写入素材与成片 SHA-256；只完成配音不等于视频已完成。
5. 查看 `preview/index.json` 对应的移动、按下、结果和转场中间帧，再播放成片检查速度和连续性，覆盖截图切换、主题对照及字幕。点击前不能提前显示结果；放大时目标文字应完整。对当前任务要求的听感实际试听；解码成功不等于“声音自然”。报告未能验证的听感或实时交互。

交付 MP4、SRT、项目路径和必要限制。不要把示例短片称为某个产品的完整介绍，不覆盖旧成片，除非用户明确要求。

## 维护与分发

引擎源码、音色快照与回归测试都在 `scripts/engine/`。修改引擎时运行 `.venv/bin/python -m unittest discover -s tests -v`，并验证被改动的实际路径；仅修改 Skill 指南不需要重新调用 API。动效修改可用 `examples/render_motion_demo.py` 离线生成各风格样片；文案与原始风格可用 `examples/render_story_demo.py` 检查，见 [references/content.md](references/content.md)。两者均不调用配音 API。

分发保留这个目录结构和可执行脚本；排除 `.venv`、`__pycache__`、`*.egg-info`、`output`、`.env*` 及真实凭据。新机器独立运行 setup 并配置自己的密钥。不要把个人虚拟环境或历史项目绝对路径固化进包。
