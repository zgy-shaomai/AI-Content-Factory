# 视频生成链路设计（video-pipeline）

适用范围：服装电商内容工厂 — 视频链路。
首期联调样品：**YN-BRA-001 黑色高弹速干运动内衣（前拉链款）**。
目标成片：12 秒、4 镜、TikTok 竖屏 9:16、原生口播 + 烧录字幕。

本文档描述视频链路从 task 触发到候选成片入库的全流程，包含每一步的输入 / 输出 / 调用模型 / 失败处理，以及与图片链路的复用关系、Seedance 调参策略、字幕策略、降级策略与成本估算。

---

## 0. 设计原则

1. **首帧驱动一致性**：每一镜的视频不是独立 text-to-video，而是 image-to-video。每镜首帧由 Seedream 4.0 生成，并与图片链路共用商品主图（白底图、人台图）作为 reference image，从而锁住模特脸型、服装版型、色号、面料质感。
2. **首帧 + 尾帧锚定切镜**：相邻两镜之间，前一镜的尾帧用作后一镜的 prompt reference，避免穿模、换脸、变色。Seedance 2.0 pro 模型支持 `image_url`（首帧）+ `last_frame_image_url`（尾帧）双锚。
3. **口播原生生成**：12 秒文案（约 30 字）以 `<dialogue>...</dialogue>` 段落形式直接写入 Seedance prompt，让模型生成原生中文口播，省一次 TTS。
4. **字幕走 ASR 二次烧录**：原生口播音频通过火山引擎 ASR 转 SRT，再由 FFmpeg drawtext / subtitles filter 烧录。这是双保险：即使 prompt 内置字幕命中率不稳定，ASR + FFmpeg 永远兜得住。
5. **节奏 1-2 / 6-8 / 2-3**：开场吸睛 1-2 秒、卖点展示 6-8 秒、行动召唤 2-3 秒。映射到 4 镜 × 3 秒 = 12 秒。
6. **多候选 + 人审**：每个 task 默认出 N=2 条候选，飞书多维表展示，人工挑选 → 进入归档。

---

## 1. 整体步骤图

```
┌─────────────────────────────────────────────────────────────────────────┐
│ S0  Webhook trigger  (POST /trigger/video, body: {task_id})             │
│      └─ 入参校验、幂等检查（同 task_id 已 running 则拒绝）              │
└──────────────────────────────┬──────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ S1  Postgres 读资料                                                     │
│      products + style_templates + image_candidates(approved)            │
│      └─ 拿到 SKU 卖点、风格模板、已审过的商品图 URL（首帧候选池）       │
└──────────────────────────────┬──────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ S2  LLM 分镜脚本生成（Claude Sonnet 4.6 @ 5dock）                       │
│      Prompt: prompts/video/01-storyboard.md                             │
│      └─ 输出 4 镜 JSON：编号 / 时长 / 画面 / 动作 / 运镜 / 口播 /        │
│         字幕 / 配乐 / 灯光                                              │
└──────────────────────────────┬──────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ S3  Split In Batches（4 镜分别走以下 S4-S8）                            │
└──────────────────────────────┬──────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ S4  LLM 生成首帧 prompt（02-keyframe-prompt.md）→ Seedream 4.0 提交     │
│      POST /api/v3/images/generations  model=doubao-seedream-4-0-...     │
│      └─ 返回 task_id                                                    │
└──────────────────────────────┬──────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ S5  轮询首帧任务（Wait 10s → GET tasks/{id}，最多 12 次）               │
│      └─ status=succeeded 拿 image_url；failed 进 S5b 降级               │
│      S5b 降级：从 image_candidates 池中按场景 tag 兜底取一张            │
└──────────────────────────────┬──────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ S6  LLM 生成视频 prompt（03-video-prompt.md）→ Seedance 2.0 提交        │
│      POST /api/v3/contents/generations/tasks                            │
│      model=doubao-seedance-1-0-pro-250528                               │
│      传 image_url（首帧）、若非镜 1 则附 last_frame_image_url（前镜尾） │
└──────────────────────────────┬──────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ S7  轮询视频任务（Wait 20s → GET tasks/{id}，最多 15 次 ≈ 5 min）       │
│      └─ status=succeeded 拿 video_url；failed → S7b 重试（备用 prompt） │
│      S7b 第二次失败 → 降级 text-to-video（不传首帧）                    │
│      S7c 第三次失败 → 标记该镜失败，进入兜底拼接（用静态首帧 + Ken Burns│
│           推拉）                                                        │
└──────────────────────────────┬──────────────────────────────────────────┘
                               ▼
                  （4 镜分支汇合 ─ Merge by task_id）
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ S8  下载 4 段视频到本地 /tmp/{task_id}/scene_{n}.mp4                    │
└──────────────────────────────┬──────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ S9  ASR：火山引擎语音识别 → SRT                                         │
│      抽 4 段音轨拼接 → 提交 ASR → 拿 utterance 时间戳 → 生成 srt        │
│      （若分镜脚本已带精确字幕时间码，可跳过 ASR 直接用脚本字幕）        │
└──────────────────────────────┬──────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ S10 FFmpeg 拼接 + 烧录字幕                                              │
│      concat demuxer 拼 4 段 → subtitles filter 烧录 srt（指定字号、     │
│      描边、底部居中）→ 输出 final.mp4                                   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ S11 上传 OSS → 拿到 cdn_url + 缩略图                                    │
└──────────────────────────────┬──────────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ S12 Postgres 写 video_candidates；飞书多维表回写一行；飞书群消息通知    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 各步详细规格

### S0 Webhook trigger

- 输入：`POST /trigger/video`，body `{ "task_id": "uuid", "n_candidates": 2 }`。
- 输出：立即返回 `202 {accepted, run_id}`，主流程异步跑。
- 失败：参数校验失败 → 400；同 task_id 已 running → 409。

### S1 Postgres 读资料

- SQL：
  ```sql
  SELECT p.*, s.style_json,
         (SELECT json_agg(c.*) FROM image_candidates c
            WHERE c.product_id = p.id AND c.status='approved') AS images
    FROM products p
    JOIN tasks t ON t.product_id = p.id
    LEFT JOIN style_templates s ON s.id = p.style_template_id
   WHERE t.id = $1;
  ```
- 输出：`{ product, style, image_pool }`。
- 失败：task 不存在 → 终止并写 task.status='failed'。

### S2 分镜脚本生成

- 调用：`POST https://5dock.com/v1/chat/completions`，model `claude-sonnet-4-6`。
- Prompt：`prompts/video/01-storyboard.md`，注入 product 与 style。
- 输出：`storyboard.json`，4 镜数组。校验：必须 4 镜、总时长 = 12.0 ± 0.3 秒、口播总字数 ≤ 36。
- 失败：JSON 解析失败 → 重试一次（temperature 调到 0.3）；二次失败 → 用兜底模板（hardcoded 4 镜，文案空着等人工填）。

### S3 Split In Batches

- batchSize = 1，串行走 4 镜，避免并发同 task 撞 Seedance 配额。

### S4 首帧 prompt + Seedream 4.0 提交

- 调用 LLM 生成英文首帧 prompt（`02-keyframe-prompt.md`）。
- 调用 Seedream：
  ```
  POST https://ark.cn-beijing.volces.com/api/v3/images/generations
  {
    "model": "doubao-seedream-4-0-250528",
    "prompt": "<生成的英文 prompt>",
    "size": "720x1280",       // 9:16
    "response_format": "url",
    "guidance_scale": 3,
    "watermark": false,
    "reference_images": [
      "<image_pool 中第一张白底商品图 URL>"
    ]
  }
  ```
- 输出：`first_frame_url`。
- 失败：Seedream 报错 → 重试 1 次（去掉 reference_images 试纯 text）；再失败走 S5b 降级。

### S5 轮询首帧任务（如走 v3 异步任务接口）

- 同步图像生成接口走 sync 即可，本步主要是“纯文本异步任务接口”兜底。
- 超时阈值：10s × 12 次 = 120s。

### S6 视频 prompt + Seedance 2.0 提交

- 调用 LLM 生成视频 prompt（`03-video-prompt.md`），生成中英混合 prompt，含运镜 / 动作 / `<dialogue>` 口播。
- 调用 Seedance：
  ```
  POST https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks
  Authorization: Bearer {ARK_API_KEY}
  Content-Type: application/json

  {
    "model": "doubao-seedance-1-0-pro-250528",
    "content": [
      { "type": "text",
        "text": "<生成的视频 prompt>  --resolution 720p --ratio 9:16 --duration 3 --fps 24 --camera_fixed false --watermark false" },
      { "type": "image_url",
        "image_url": { "url": "<first_frame_url>" },
        "role": "first_frame" },
      { "type": "image_url",
        "image_url": { "url": "<prev_scene_last_frame_url>" },
        "role": "last_frame" }   // 仅镜 2/3/4 携带
    ]
  }
  ```
- 关键参数策略：
  - `duration=3`：每镜 3 秒，4 镜 × 3 秒 = 12 秒。
  - `resolution=720p` + `ratio=9:16`：竖屏，720×1280。pro 模型支持 480p/720p/1080p；720p 是质量与成本的甜点。
  - `fps=24`：TikTok 风格丝滑度足够。
  - `camera_fixed=false`：允许 prompt 中的运镜指令生效（推、拉、摇）。
  - `watermark=false`：去除模型水印。
  - `seed`：不固定，靠候选数兜底；如客户要求复现某条爆款，再固定。
- 输出：`{ id: "task-xxx" }`。
- 失败：4xx → prompt 长度或非法字符问题，截断后重试；5xx → 间隔 30s 重试 1 次。

### S7 轮询视频任务

- `GET /api/v3/contents/generations/tasks/{id}`，间隔 20s，最多 15 次（5 分钟）。
- 状态机：`queued → running → succeeded / failed / cancelled`。
- 失败重试梯度（参考家纺方案 § 3 经验）：
  1. **第 1 次失败**：换备用 prompt（精简版，去掉复杂动作描述、保留主体 + 运镜 + 口播）。
  2. **第 2 次失败**：降级到 text-to-video（不传 first_frame，纯文本生成），允许人物轻微变化。
  3. **第 3 次失败**：标记该镜 `scene_failed=true`，进入 S10 兜底，用 first_frame 静态图 + FFmpeg Ken Burns 推拉补 3 秒。

### S8 下载视频

- HTTP GET video_url → 落到 N8N runner 的 `/tmp/{task_id}/scene_{n}.mp4`。
- 失败：URL 过期（部分平台短链 1h 失效）→ 重新查询任务详情拿新 URL。

### S9 ASR + 字幕

- 何时启用 ASR：默认启用。原因 — Seedance 内置字幕命中率不稳定，ASR 永远是兜底。
- 何时跳过 ASR：当 storyboard 中已含精确到 0.1 秒的 `subtitle_timing` 段落（人工微调过的复用模板），可直接走 storyboard 字幕。
- 火山引擎 ASR 调用：
  ```
  POST https://openspeech.bytedance.com/api/v1/auc/submit
  audio_url=<concatenated_audio_url>
  language=zh-CN
  enable_punc=true
  enable_itn=true
  ```
- 输出：JSON utterance 列表 → 生成 SRT。
- 失败：ASR 不可用 → 退回 storyboard 文案，用每镜固定时间窗 [0, 3) [3, 6) [6, 9) [9, 12) 平均分配。

### S10 FFmpeg 拼接 + 字幕烧录

- 拼接：
  ```
  ffmpeg -f concat -safe 0 -i list.txt -c copy /tmp/{task_id}/concat.mp4
  ```
- 烧录字幕（描边白字、底部居中）：
  ```
  ffmpeg -i concat.mp4 -vf "subtitles=sub.srt:force_style='FontName=Source Han Sans,FontSize=42,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Alignment=2,MarginV=80'" -c:v libx264 -crf 20 -c:a aac -b:a 128k final.mp4
  ```
- 兜底镜（scene_failed=true）：
  ```
  ffmpeg -loop 1 -t 3 -i scene_n_first_frame.png -vf "zoompan=z='min(zoom+0.0015,1.15)':d=72:s=720x1280" -c:v libx264 scene_n.mp4
  ```

### S11 OSS 上传

- 路径：`oss://content-factory/videos/{yyyymm}/{task_id}/{candidate_n}.mp4`。
- 同时上传缩略图（FFmpeg 抽帧）：`{task_id}/{candidate_n}_thumb.jpg`。

### S12 落库 + 飞书回写

- `INSERT INTO video_candidates (task_id, video_url, thumb_url, storyboard_json, prompts_json, status='pending_review') ...`。
- 飞书多维表 `bitable.record.create`：写一行候选，附预览链接。
- 飞书群机器人：`@运营`：`{SKU} 视频 #{candidate_n} 已生成，请审核：{cdn_url}`。

---

## 3. 与图片链路的资料共用

| 资料 | 图片链路产出 | 视频链路用途 |
| --- | --- | --- |
| `image_candidates(status='approved')` 商品白底图 | 图片链路 S5 落库 | 视频链路 S4 作为 Seedream 的 `reference_images`，锁服装版型与色号 |
| `image_candidates` 场景图（瑜伽馆 / 跑步） | 图片链路 S5 落库 | 视频链路 S5b 兜底首帧 |
| `style_templates.style_json`（灯光、色调、构图） | 图片链路 S2 输入 | 视频链路 S2 输入，保证两条链路视觉风格统一 |
| `products.selling_points` | 共用 | S2 分镜脚本生成的核心输入 |

复用入口在 S1 的一条 SQL 里。这是双链路统一调优层在 schema 层面落地的关键 — 视频不会再独立"再画一张商品图"，省掉一次 Seedream 调用，也保证商品视觉一致。

---

## 4. 字幕处理决策

```
storyboard.subtitle_timing 是否人工标注精确时间码？
   ├─ 是 → 直接生成 SRT，跳过 ASR
   └─ 否 ↓
       Seedance 是否生成原生口播音频？（检查输出 video 的 audio stream）
            ├─ 是 → ASR 转写 → 生成 SRT
            └─ 否（极少数 — Seedance 关音频或失败镜） → 用 storyboard 文案 + 平均时间分配
```

字幕样式统一：思源黑体 42px、白字黑描边 2px、底部居中、距底 80px。这套样式在 720×1280 上人物头肩之外，不挡服装关键卖点。

---

## 5. 失败重试与降级总表

| 失败点 | 第一次降级 | 第二次降级 | 兜底 |
| --- | --- | --- | --- |
| LLM 分镜 JSON 解析失败 | 重试 temperature=0.3 | 用 hardcoded 模板 | 任务标 `failed_user_review` |
| Seedream 首帧失败 | 去 reference_images 重试 | 用 image_pool 兜底图 | 任务转人工 |
| Seedance 视频失败（每镜独立） | 备用精简 prompt | 转 text-to-video | 静态首帧 + Ken Burns 推拉 |
| ASR 失败 | 重试 1 次 | 用 storyboard 文案 + 平均分配时间 | 关字幕仅出原片 |
| OSS 上传失败 | 重试 3 次（指数退避） | 切换备用 endpoint | 失败入队人工处理 |

每一次降级都写入 `task_runs.events` JSONB，最终在飞书消息里附 `degradation_level`，运营一眼看出"这条片子是不是兜底出来的"。

---

## 6. 成本估算（单条 12 秒视频，2 候选）

按"1 元 / 秒（Seedance 2.0 pro 720p 9:16）"口径：

| 项目 | 单价 | 单条数量 | 单条成本 |
| --- | --- | --- | --- |
| Seedance 视频生成（4 镜 × 3 秒） | 1 元 / 秒 | 12 秒 | 12 元 |
| Seedream 首帧（4 张） | ≈ 0.25 元 / 张 | 4 张 | 1 元 |
| Claude Sonnet 4.6（脚本 + 8 次 prompt 改写） | ≈ 0.05 元 / 次 | 9 次 | 0.45 元 |
| 火山 ASR | ≈ 0.0008 元 / 秒 | 12 秒 | 0.01 元 |
| OSS 存储 + 流量 | 忽略 | — | ≈ 0.05 元 |
| **小计 / 候选** | | | **≈ 13.5 元** |
| **× 2 候选** | | | **≈ 27 元** |
| 含降级重试缓冲（×1.3） | | | **≈ 35 元 / 条** |

按客户日产 5-10 条规划：日成本 175 - 350 元，月成本约 5000 - 10000 元。这是 Seedance 直连方舟的口径；若改走 PiAPI 等中转，单价会上浮 30%-50%。

---

## 7. 性能与产能

- 单条端到端预计 4-6 分钟（Seedance 4 镜串行各 1-1.5 分钟 + 拼接 30s + 上传 10s）。
- 4 镜 Seedance 任务可并行（去掉 S3 的 batchSize=1 改 4），端到端可压到 2-3 分钟，代价是同账号配额可能撞 RPS 限制 — 视客户方舟账号配额决定。
- N8N 单 worker 默认配置下并发 10 个 task 上限，再上需要拆 worker pool。

---

## 8. 监控与可观测

- N8N 每个 HTTP Request 节点的 `error workflow` 统一指向 `error_handler` 子工作流，写入 `task_runs.errors`。
- 关键指标（grafana 看板，下一阶段补）：
  - `video_pipeline_success_rate`（按 SKU、按降级层级分组）。
  - `video_pipeline_p50_duration` / `p95_duration`。
  - `seedance_failure_count_by_reason`（content_violation / timeout / quota）。

---

## 9. 演示当天 checklist（YN-BRA-001）

1. `image_candidates` 至少有 3 张已 approved 的白底图与 2 张瑜伽馆场景图。
2. `style_templates` 中 `sportwear_dynamic` 已就绪（暖光、对比度高、轻噪点）。
3. 方舟 API key 余额 ≥ 200 元、ASR 配额 ≥ 1 万秒。
4. OSS bucket `content-factory` 写权限通过。
5. N8N 已 import `video-workflow.json` 并替换 4 条 credentials 引用。
6. 演示前手动跑一条 dry-run，确认成片在飞书多维表可点开播放。
