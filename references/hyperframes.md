# Hyperframes HTML 镜头

用于需要独立构图、连续状态变化、文字与界面联动的段落。每个镜头是一份 HTML/CSS/JavaScript 源文件，可使用 GSAP、SVG、CSS 遮罩及 Hyperframes 支持的可寻址动画运行时。镜头按实际旁白时长渲染，再进入现有 Remotion 时间轴；Shotcraft、三维、截图操作、旁白、字幕、音乐与音效继续混排。

当前固定使用 Hyperframes **0.8.40**、GSAP **3.14.2**。来源：[heygen-com/hyperframes](https://github.com/heygen-com/hyperframes)，文档：[Hyperframes](https://hyperframes.heygen.com/introduction)。未修改上游源代码，也不自动安装其创作 Skills、切换语音供应商或执行云端发布。第三方示例是实现资料，不能替代用户确认的文稿、素材与制作要求。

## 选择与设计

先确定这一段需要展示的关系，再设计画面。例如：沿实际操作路径连续移动；把选中的界面局部展开成解释图；通过遮罩同时比较两种状态；将文案中的数量或流程转成动态图。库中的过场只在有明确衔接作用时使用。

不要按镜头序号循环套用示例，不把一组 HTML 模板变成新的固定视频结构。对已有产品对照上一条成片，重新安排开场、讲解顺序、版式与节奏，记录在本次分镜说明中。模板仅用于理解技术契约。

## 环境与效果目录

完整 `setup.sh` 包括此运行环境。已有安装可单独运行：

```sh
sh "$SKILL/scripts/setup-hyperframes.sh"
HF="$SKILL/scripts/hyperframes/run.sh"
sh "$HF" catalog --query "mask reveal" --json
sh "$HF" add <已查到的效果名> --dir /path/to/project/scenes/feature --no-clipboard
```

运行包装器使用锁定依赖，避免 `npx ...@latest` 在制作中更换版本。目录搜索使用英文描述，画面文字沿用用户语言。引入效果后检查源文件、依赖和素材许可，将必需资源放入当前镜头目录；外部 CDN 资源需在渲染前固定为本地文件。只下载当前镜头需要的资源。

目录依赖上游资源可用性。若搜索出现抓取超时或跳过条目的提示，结果可能不完整；不能据此判断某个效果不存在。可按具体名称检查上游仓库内的源文件，确认素材齐全后再使用。

检查、快照与渲染统一使用此版本附带的 Chromium 152.0.7977.30，避免选中其他工具缓存的旧浏览器。自定义浏览器可通过上游支持的 `HYPERFRAMES_BROWSER_PATH` 指定；该设置只作用于当前运行，不写入分发包。

## 项目绑定

```json
{
  "at": 0.35,
  "hyperframes": {
    "entry": "scenes/feature/index.html",
    "media": {
      "screen": "capture:feature",
      "detail": "assets/detail.png"
    },
    "variables": {"title": "按实际内容排版", "count": 3}
  },
  "transition": "iris",
  "transition_duration": 0.35
}
```

使用 `schema_version: 2` 和 `video.renderer: remotion`。`at` 仍是章节配音的时间比例。HTML 镜头不能同时声明 `images`、`editorial`、`shotcraft`、`scene3d`、指针或相机字段；这些作为前后镜头混排。HTML 自己负责内部布局与运动。

每个镜头放在独立目录，入口目录内只保留所需资源。引擎会固定 HTML、CSS、JS、图片、录屏、字体和动画数据，排除环境文件、凭据、依赖目录与生成目录。禁止通过符号链接引用目录外内容；外部素材通过 `media` 明确绑定。资源路径与项目配置相对；`capture:<id>` 会由自动采集解析。

`variables` 支持文本、有限数值和布尔值，名称用字母开头的字母、数字、下划线或连字符。无需用变量表达的内容直接写在源码中。

## HTML 契约

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <!-- product-video:head -->
  <style>
    body { margin: 0; font-family: ProductVideoFont, sans-serif; }
    #root { position: relative; width: 100%; height: 100%; overflow: hidden; background: #eef2ea; }
    #headline { position: absolute; left: 6%; top: 8%; font-size: 4vw; }
    #screen { position: absolute; left: 20%; top: 27%; width: 60%; height: 58%; object-fit: contain; }
  </style>
</head>
<body>
  <div id="root" data-composition-id="feature"
       data-width="{{pv.width}}" data-height="{{pv.height}}" data-duration="{{pv.duration}}">
    <h1 id="headline">{{pv.variables.title}}</h1>
    <img id="screen" src="{{pv.media.screen}}" alt="对应功能界面">
  </div>
  <script>
    const pv = window.PRODUCT_VIDEO;
    if (pv.reduced_motion) document.getElementById('root').setAttribute('data-no-timeline', '');
    const tl = gsap.timeline({paused: true});
    tl.to({}, {duration: pv.duration}, 0);
    if (!pv.reduced_motion) {
      tl.fromTo('#screen', {clipPath: 'inset(0 100% 0 0)'},
        {clipPath: 'inset(0 0% 0 0)', duration: Math.min(1, pv.duration * .25)}, .1);
    }
    window.__timelines.feature = tl;
  </script>
</body>
</html>
```

入口 `<head>` 中保留且只保留一个 `<!-- product-video:head -->`。引擎在此注入本地 GSAP、项目字体和 `window.PRODUCT_VIDEO`；不再重复加载 GSAP。根节点不使用 `<template>` 包裹，其 `data-composition-id` 与 `window.__timelines` 的键一致，宽高与时长使用占位符。子合成可按上游 `data-composition-src` 契约编排。

可用数据：

| 字段 | 含义 |
| --- | --- |
| `width`、`height`、`fps`、`duration` | 当前镜头的实际规格与秒数 |
| `reduced_motion` | 用户的减少动态效果设置；保留可读静态最终状态 |
| `media.<name>` | 已固定为本地资源的相对路径 |
| `variables.<name>` | 配置中绑定的标量 |
| `voice_start` | 本章旁白起点相对当前镜头的秒数，中途切入可为负数 |
| `cues` | 与镜头相交的字幕，裁到镜头范围，起止以镜头开始为零 |
| `chapter` | 当前章节 id、标题、原稿和完整配音时长 |

HTML 的 `{{pv.xxx}}` 只替换标量并做 HTML 转义。JavaScript 中通过 `PRODUCT_VIDEO` 读取文本、路径和对象，避免引号或标签字符破坏脚本。需要更精细的语句动作时，使用 `cues` 或源项目的真实字级时间戳校准；不按字数伪造对齐。

所有动画必须可按时间重新定位：注册暂停的时间轴，不能依赖实际时钟、随机数、计时器或播放回调积累状态。Hyperframes 管理 `.clip` 的显隐，运动放在内部元素上；媒体使用上游可寻址播放契约。字幕占底部安全区，正文与图像需留出空间。当前 Product Video 主时间轴仍为 16:9，不因上游支持其他画幅而宣称已接通。

时间轴保留 `tl.to({}, {duration: pv.duration}, 0)` 作为完整镜头的驻留时段。减少动态效果时，在根节点设置上游支持的 `data-no-timeline`，明确这是有意保持静止的画面；否则上游会把三秒以上的静态画面报为 `sweep_static`。只对有意静止的状态声明，不为通过检查添加无意义运动。位移用 `x/y` 等 transform，避免对 `left/top` 做逐帧运动产生取整抖动。

## 生成与编辑

继续使用 `check`、`voice`、`prepare-motion`、`preview`、`render`、`build`、`review`。HTML 镜头先运行 Hyperframes `check`，通过后生成静音视频片段；章节旁白、字幕、音乐和音效由主时间轴统一合成，HTML 内的音轨不会进入成片。

源码、绑定素材、字体、音频时间和渲染器变化都会进入缓存签名。只改 HTML 布局时继续复用已有配音；失败时保留成功的章节与镜头，不把未验证的视频写入 `latest.json`。

渲染目录的 `hyperframes.json` 记录各镜头的原生可编辑 HTML 工程及片段，主 `studio/project.json` 记录整片时间轴。可以用以下命令检查单镜头：

```sh
sh "$HF" snapshot /path/from/hyperframes.json/project --at 0,1,2
sh "$HF" preview /path/from/hyperframes.json/project --no-open
```

Hyperframes Studio 修改的是生成工程，主工作台修改的是预渲染片段；要使改动在后续整片重建时保留，将 HTML/CSS/JS 改动写回源 `entry` 目录，保留原来的占位符与 head 标记，然后重新运行 `render`。不要以为编辑生成 HTML 会自动回写源稿。

验证默认使用 `examples/render_hyperframes_demo.py`：三种独立 HTML 构图与既有截图操作、内容镜头混合，无配音 API。实际成片需检查 HTML 首帧/中间/末帧、相邻转场、字幕与声音，`check` 或解码通过不等于观感与听感通过。
