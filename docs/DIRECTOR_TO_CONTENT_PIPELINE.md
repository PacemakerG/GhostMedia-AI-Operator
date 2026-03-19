# 导演 Agent 到 Content 视频执行器的数据协议

本文档说明当前 GhostMedia 中，`导演 Agent` 如何把选题、文案、素材检索词和渲染参数，传递给 `content-vedio-agent` 执行视频生成。

适用链路：

`热点编排 -> facelessnews 导演层 -> task_request.json -> content-vedio-agent -> 本地 mp4`

## 1. 模块职责

### 导演 Agent（当前由 orchestrator + facelessnews 充当）

负责：

1. 选哪条热点做视频
2. 用哪套平台文案做底稿
3. 生成封面标题、口播稿、素材检索词
4. 生成分镜说明和渲染参数
5. 输出标准化 JSON 给视频执行器

对应代码：

- [faceless_news.py](/home/elon/workspace/GhostMedia-AI-Operator/orchestrator/src/faceless_news.py#L175)

### Content 视频执行器（content-vedio-agent）

负责：

1. 读取 `task_request.json`
2. 生成音频
3. 生成字幕
4. 去 Pexels / Pixabay 按关键词拉素材
5. 把素材、音频、字幕拼成最终视频

对应代码：

- [task.py](/home/elon/workspace/GhostMedia-AI-Operator/content-vedio-agent/app/services/task.py#L246)

## 2. 当前中间产物

每轮热点输出目录下会新增：

- `faceless_news/news_x/brief.json`
- `faceless_news/news_x/task_request.json`
- `faceless_news/news_x/script.txt`
- `faceless_news/news_x/caption.txt`
- `faceless_news/news_x/render_content_api.sh`

### brief.json

这是导演层产物，给人和后续 Agent 看，不直接提交给视频执行器。

包含：

- `cover_title`
- `hook`
- `voice_script`
- `ending_question`
- `visual_search_terms`
- `segments`
- `render_preset`

对应构造逻辑：

- [faceless_news.py](/home/elon/workspace/GhostMedia-AI-Operator/orchestrator/src/faceless_news.py#L175)

### task_request.json

这是真正提交给 `content-vedio-agent` 的执行协议。

对应构造逻辑：

- [faceless_news.py](/home/elon/workspace/GhostMedia-AI-Operator/orchestrator/src/faceless_news.py#L214)

## 3. 导演层输出的 JSON 格式

当前 `task_request.json` 结构如下：

```json
{
  "video_subject": "永辉喊话山姆，真正暴露的是谁急了",
  "video_script": "完整口播稿",
  "video_terms": ["永辉发公开信喊话山姆", "山姆会员店", "零售"],
  "video_aspect": "9:16",
  "video_clip_duration": 4,
  "video_count": 1,
  "video_source": "pexels",
  "voice_name": "zh-CN-YunxiNeural-Male",
  "voice_rate": 1.18,
  "voice_volume": 1.0,
  "bgm_type": "random",
  "bgm_volume": 0.12,
  "subtitle_enabled": true,
  "subtitle_position": "center",
  "font_name": "STHeitiMedium.ttc",
  "font_size": 62,
  "text_fore_color": "#FFFFFF",
  "text_background_color": true,
  "stroke_color": "#000000",
  "stroke_width": 1.8,
  "n_threads": 2
}
```

## 4. 字段映射关系

### 导演层到视频执行器的映射

| 导演层字段 | 来源 | 传给 content-vedio 字段 | 用途 |
| --- | --- | --- | --- |
| `cover_title` | 抖音版标题 | `video_subject` | 作为视频主题，也用于兜底生成脚本/关键词 |
| `voice_script` | `hook + script` 拼接 | `video_script` | 直接作为口播音频和字幕的文本来源 |
| `visual_search_terms` | 标题、标签、切入角度、争议点抽取 | `video_terms` | 作为素材搜索关键词 |
| `render_preset.video_aspect` | 模板预设 | `video_aspect` | 控制横竖屏尺寸 |
| `render_preset.video_clip_duration` | 模板预设 | `video_clip_duration` | 控制每段素材的最大时长 |
| `render_preset.video_source` | 模板预设或命令行 | `video_source` | 指定素材来源，如 `pexels`/`pixabay`/`local` |
| `render_preset.voice_name` | 模板预设 | `voice_name` | 选择 TTS 音色 |
| `render_preset.voice_rate` | 模板预设 | `voice_rate` | 控制语速 |
| `render_preset.voice_volume` | 模板预设 | `voice_volume` | 控制人声音量 |
| `render_preset.subtitle_enabled` | 模板预设 | `subtitle_enabled` | 是否生成字幕 |
| `render_preset.subtitle_position` | 模板预设 | `subtitle_position` | 字幕位置 |
| `render_preset.font_name` | 模板预设 | `font_name` | 字幕字体 |
| `render_preset.font_size` | 模板预设 | `font_size` | 字幕字号 |
| `render_preset.text_fore_color` | 模板预设 | `text_fore_color` | 字幕文字颜色 |
| `render_preset.text_background_color` | 模板预设 | `text_background_color` | 字幕背景色 |
| `render_preset.stroke_color` | 模板预设 | `stroke_color` | 字幕描边颜色 |
| `render_preset.stroke_width` | 模板预设 | `stroke_width` | 字幕描边宽度 |
| `render_preset.bgm_type` | 模板预设 | `bgm_type` | BGM 选择方式 |
| `render_preset.bgm_volume` | 模板预设 | `bgm_volume` | BGM 音量 |
| `render_preset.n_threads` | 模板预设 | `n_threads` | 视频导出线程数 |

`task_request.json` 的字段定义来自：

- [schema.py](/home/elon/workspace/GhostMedia-AI-Operator/content-vedio-agent/app/models/schema.py#L56)

## 5. 素材关键词是怎么来的

关键词不是素材网站自己决定的，而是导演层先生成。

当前逻辑在：

- [faceless_news.py](/home/elon/workspace/GhostMedia-AI-Operator/orchestrator/src/faceless_news.py#L83)

生成规则如下：

1. 优先取热点原始标题
2. 追加 hashtags
3. 从 `core_angle` 和 `debate_point` 中切出较短短语
4. 去重
5. 过滤过长词
6. 最多保留 6 个

示例：

```json
[
  "永辉发公开信喊话山姆",
  "山姆会员店",
  "零售",
  "真正值得聊的不是谁发了信",
  "而是谁先扛不住山姆式竞争",
  "把行业焦虑写成了公开喊话"
]
```

### 这些关键词后续怎么用

`content-vedio-agent` 会把 `video_terms` 逐个拿去请求素材站：

- Pexels 搜索：
  [material.py](/home/elon/workspace/GhostMedia-AI-Operator/content-vedio-agent/app/services/material.py#L34)
- Pixabay 搜索：
  [material.py](/home/elon/workspace/GhostMedia-AI-Operator/content-vedio-agent/app/services/material.py#L91)

下载过程：

- [material.py](/home/elon/workspace/GhostMedia-AI-Operator/content-vedio-agent/app/services/material.py#L197)

处理逻辑：

1. 依次搜索每个关键词
2. 收集符合画幅和最小时长的视频
3. 去重
4. 下载到本地
5. 直到下载素材总时长覆盖口播音频时长

## 6. 文案如何转成口播音频

导演层先把：

- `hook`
- `script`

拼成一个完整的 `voice_script`：

- [faceless_news.py](/home/elon/workspace/GhostMedia-AI-Operator/orchestrator/src/faceless_news.py#L168)

然后写入 `task_request.json` 的 `video_script` 字段：

- [faceless_news.py](/home/elon/workspace/GhostMedia-AI-Operator/orchestrator/src/faceless_news.py#L214)

到了 `content-vedio-agent` 之后：

1. 如果 `video_script` 已传入，直接使用，不再调用 LLM 生成脚本
   - [task.py](/home/elon/workspace/GhostMedia-AI-Operator/content-vedio-agent/app/services/task.py#L16)
2. 用 TTS 把这段文本转成 `audio.mp3`
   - [task.py](/home/elon/workspace/GhostMedia-AI-Operator/content-vedio-agent/app/services/task.py#L73)
3. TTS 实现函数：
   - [voice.py](/home/elon/workspace/GhostMedia-AI-Operator/content-vedio-agent/app/services/voice.py#L1119)

结论：

- 文案到口播，当前是 `文本 -> TTS -> mp3`
- 不是 LLM 朗读
- 也不是数字人先生成嘴型再反推音频

## 7. 字幕是怎么来的

字幕生成入口：

- [task.py](/home/elon/workspace/GhostMedia-AI-Operator/content-vedio-agent/app/services/task.py#L124)

当前默认配置是 `edge`：

- [config.toml](/home/elon/workspace/GhostMedia-AI-Operator/content-vedio-agent/config.toml#L113)

流程：

1. TTS 生成音频时会得到时间信息
2. 优先按 `edge` 方式生成字幕
3. 如果失败，再 fallback 到 `whisper`

最终得到：

- `subtitle.srt`

## 8. 视频是怎么拼出来的

主流程入口：

- [task.py](/home/elon/workspace/GhostMedia-AI-Operator/content-vedio-agent/app/services/task.py#L246)

步骤如下：

1. 读取或生成 `video_script`
2. 读取或生成 `video_terms`
3. 生成音频
4. 生成字幕
5. 下载视频素材
6. 组合素材段落，形成 `combined-1.mp4`
7. 叠加字幕、音频、BGM，导出 `final-1.mp4`

素材拼接逻辑：

- [video.py](/home/elon/workspace/GhostMedia-AI-Operator/content-vedio-agent/app/services/video.py#L117)

字幕、音频、BGM 合成逻辑：

- [video.py](/home/elon/workspace/GhostMedia-AI-Operator/content-vedio-agent/app/services/video.py#L363)

## 9. 当前哪些字段只是导演层内部信息

以下字段当前只存在于 `brief.json`，不会传给 `content-vedio-agent`：

- `selection_reason`
- `core_angle`
- `debate_point`
- `ending_question`
- `segments`

它们的作用主要是：

1. 给人审稿
2. 供后续更强的视频模板使用
3. 作为未来“精细分镜控制”的输入

也就是说，当前 `segments` 只是导演层描述，还没有被 `content-vedio-agent` 直接消费。

## 10. 什么时候会用到 LLM

### 当前 facelessnews 正常路径

如果导演层已经提供：

- `video_script`
- `video_terms`

那么 `content-vedio-agent` 不需要再用 LLM 决策内容。

### 只有在以下情况下才会回退到 LLM

1. 没传 `video_script`
   - 则 `content-vedio-agent` 自己生成视频文案
2. 没传 `video_terms`
   - 则 `content-vedio-agent` 自己生成素材搜索词

相关逻辑：

- [task.py](/home/elon/workspace/GhostMedia-AI-Operator/content-vedio-agent/app/services/task.py#L16)
- [task.py](/home/elon/workspace/GhostMedia-AI-Operator/content-vedio-agent/app/services/task.py#L36)

## 11. 当前架构建议

建议长期保持以下原则：

1. 创意决策在 `orchestrator`
2. 视频执行在 `content-vedio-agent`
3. 发布执行在 `social-auto-upload`

不要把“导演权”交回上游视频项目，否则系统会变得不可控，难以统一风格、节奏和素材策略。

## 12. 后续可升级点

当前协议已经能跑通最小 faceless 视频，但还有 3 个明显升级方向：

1. 把 `segments` 也映射成真正可执行的镜头控制参数
2. 区分不同赛道的素材检索策略
3. 把封面大字、片头卡、结尾 CTA 也纳入模板渲染层
