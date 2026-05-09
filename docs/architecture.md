# 服装电商内容工厂 — 系统架构与演示讲稿

> 版本：v1.0 · 演示稿
> 日期：2026-05-05
> 范围：图片链路 + 视频链路统一内容生产系统
> 样板 SKU：YN-BRA-001（黑色高弹速干运动内衣 · 前拉链款）

---

## 1. 一句话定位

**这套系统是一台"产品资料进、商用图片和视频出"的自动流水线 —— 您在飞书表里录一条 SKU，半小时之内拿到一组场景图、一组商品图、一条 10–15 秒的卖点视频，所有候选结果在同一张飞书表里一键审核、一键归档到您的阿里云 OSS。第一个产品打样跑通后，第二、第三个 SKU 复用同一条流水线，只换素材、不改流程。**

---

## 2. 整体架构图

```
+---------------------------------------------------------------------------------------+
|                           客 户 侧 ( 浏 览 器 / 手 机 飞 书 )                          |
|                                                                                       |
|   [ 飞书多维表 · 任务输入 ]      [ 飞书多维表 · 审核工作台 ]    [ 飞书消息机器人 ]     |
|         录入 SKU / 卖点                  审核 / 打回 / 归档           告警 + 进度       |
+----------------|-------------------------------|----------------------|---------------+
                 |  Webhook ( 飞书事件订阅 )      |  Webhook              |  outgoing
                 v                               v                      ^
+---------------------------------------------------------------------------------------+
|                              VPS · 2C4G · Ubuntu 22.04                                |
|                                                                                       |
|   +-----------------------+   docker network: factory_net  +---------------------+    |
|   |  Caddy ( 反向代理 )   |  :80 / :443                    |   N8N ( 工作流引擎  ) |   |
|   |  自动 HTTPS           |--------------------------------|   container: n8n    |    |
|   +-----------|-----------+   /webhook/*                   |   port: 5678 内网    |   |
|               |                                            +----|--------|-------+   |
|               |                                                 |        |           |
|               |  /n8n/*  (admin UI 仅内网/IP 白名单)             |        |           |
|               +-------------------------------------------------+        |           |
|                                                                          |           |
|   +-----------------------+    +------------------------+    +-----------|--------+   |
|   |  PostgreSQL 16        |<-->|  Redis 7 ( 队列+缓存 ) |    |  N8N Worker x2     |   |
|   |  container: pg        |    |  container: redis      |    |  ( 长任务执行器 )  |   |
|   |  port: 5432 内网       |    |  port: 6379 内网        |   +--------|-----------+   |
|   |  库: factory_db       |    +------------------------+             |               |
|   +-----------------------+                                           |               |
|                                                                       |               |
+-----------------------------------------------------------------------|---------------+
                                                                        |
                                            HTTPS 出站调用              |
              +---------------------------------------------------------+
              |                          |                              |
              v                          v                              v
   +--------------------+    +-----------------------+    +----------------------------+
   |  火山方舟 API      |   |  火山方舟 API         |    |  5dock NewAPI 网关          |
   |  Seedream 4.0      |    |  Seedance 2.0         |    |  ( Claude Sonnet 4.6 )     |
   |  ( 图片生成 )       |    |  ( 视频生成 )         |    |  ( 文案 / 分镜 / 提示词 )    |
   +--------------------+    +-----------------------+    +----------------------------+
              |                          |                              |
              +-----------+--------------+                              |
                          |                                             |
                          v                                             |
              +------------------------------+                          |
              |  阿里云 OSS                  |  <---------- 结果归档 / 回链 ----+
              |  Bucket: yn-content-factory  |
              |  Region: oss-cn-shanghai     |
              |  路径前缀: /sku/<SKU>/...     |
              +------------------------------+

  数据流图例：
   ──>   触发 / 调用 ( 同步 HTTP )
   ==>   异步任务 ( 队列 + 回调 / 轮询 )
   ←──   写回 ( 飞书表 / PG / OSS )
```

**端口与暴露面（最小公开面）**：仅 `:80 / :443` 对公网开放，由 Caddy 终结 TLS 并按路径分发；`5678 / 5432 / 6379` 全部跑在 docker 内网 `factory_net`，外部不可达；N8N 管理 UI 走 `https://n8n.<客户域名>/` 并启用 IP 白名单 + Basic Auth 双层。

---

## 3. 数据流详解 — YN-BRA-001 完整 13 步链路

下面以样板 SKU 为例，把"录入一条飞书行 → 拿到全套素材入库"的全过程拆为 13 步。每步注明：触发条件、运行节点、调用接口、产出、落库 / 落对象存储位置。

### 步骤 1 · 任务录入

- **触发**：运营在飞书多维表 `t_sku_intake` 新增一行，必填字段填齐：`sku_code=YN-BRA-001`、`name=黑色高弹速干运动内衣（前拉链款）`、`selling_points=透气网眼面料/前置拉链/高弹支撑/速干`、`scene_tags=瑜伽馆,跑步,健身房,户外`、`audience=25-40 岁运动女性`、`ref_images=[3 张产品平铺图 url]`、`run_mode=full`（图片+视频）。
- **节点**：飞书事件订阅推送到 `https://factory.<域名>/webhook/intake`。
- **接口**：飞书 OpenAPI `bitable.v1.app.table.record.search` 拉详细字段。
- **产出**：N8N 启动一个 `run_id=R-20260505-0001`，写入 PG `runs` 表，状态 `received`。
- **落点**：PG `runs(run_id, sku_code, payload_json, status, created_at)`。

### 步骤 2 · SKU 资料解析与卖点拆解

- **触发**：步骤 1 完成后立即流转。
- **节点**：N8N `LLM-Parser` 节点 → 5dock NewAPI → Claude Sonnet 4.6。
- **调用**：`POST /v1/messages`，system prompt = `prompts/sku_parser.system.md`，输入是飞书原始字段。
- **产出**：结构化 JSON `{ core_features:[...], material:[...], selling_points_ranked:[...], hero_keywords:[...], forbidden_words:[...] }`。
- **落点**：PG `sku_profiles(sku_code, profile_json, version)`，OSS `sku/YN-BRA-001/profile/v1.json`。

### 步骤 3 · 风格 Token 解析

- **触发**：与步骤 2 并行。
- **节点**：N8N `Style-Resolver`，读取 PG `brand_styles` 表中预置的"YN 品牌包"。
- **产出**：`{ palette:[#0A0A0A,#C9A96E], lighting:"soft daylight + rim", lens:"50mm f1.8", composition:"rule of thirds, mid shot", mood:"energetic, clean" }`。
- **落点**：内存对象 + PG `runs.style_snapshot_json`（快照保存便于复现）。

### 步骤 4 · 图片 Prompt 生成（场景图 ×4 + 商品图 ×2）

- **触发**：步骤 2、3 全部完成。
- **节点**：N8N `Image-Prompt-Builder` → Claude Sonnet 4.6。
- **调用**：使用 `prompts/image_prompt.system.md` + 场景列表（瑜伽馆 / 跑步 / 健身房 / 户外）。
- **产出**：6 条 prompt + 6 条 negative prompt + 每条的尺寸与种子建议（`1024x1536` 竖图为主）。
- **落点**：PG `image_jobs(job_id, run_id, prompt, neg_prompt, scene, status='queued')`，OSS `sku/YN-BRA-001/prompts/image_v1.json`。

### 步骤 5 · 图片生成（Seedream 4.0）

- **触发**：步骤 4 入库即派发。
- **节点**：N8N `Seedream-Submit` worker，并发 3。
- **调用**：火山方舟 `POST /api/v3/images/generations`，model=`seedream-4.0`，每个 prompt 出 2 张候选 → 共 12 张。
- **产出**：原始 PNG / JPG。
- **落点**：OSS `sku/YN-BRA-001/images/raw/<scene>/<job_id>_<idx>.jpg`，CDN 公网 URL 写回 PG `image_jobs.result_urls`。

### 步骤 6 · 图片质检与一致性打分

- **触发**：步骤 5 任一图返回。
- **节点**：N8N `Image-QC`，调用 Claude Sonnet 4.6 的多模态接口对 12 张图打分（品牌一致性 / 卖点呈现 / 真实感 / 合规性 4 个维度，各 0–10）。
- **产出**：每张图一条评分 + Top-N 推荐。
- **落点**：PG `image_jobs.qc_score_json`，飞书表 `t_image_review` 自动新增 12 行（每行带缩略图 + 分数 + 一键"通过 / 打回"按钮）。

### 步骤 7 · 视频分镜脚本生成

- **触发**：步骤 2 完成即可启动（不依赖图片完成）。
- **节点**：N8N `Storyboard-Builder` → Claude Sonnet 4.6。
- **调用**：`prompts/video_storyboard.system.md`，输出 4 个分镜的 12 秒结构（开场 2s 产品出现 → 3s 拉链特写 → 4s 跑步动态 → 3s logo 收尾）。
- **产出**：JSON `[{shot_id, duration, camera, action, on_screen_text, voiceover}]`。
- **落点**：PG `video_runs(run_id, storyboard_json)`，OSS `sku/YN-BRA-001/video/storyboard_v1.json`。

### 步骤 8 · 分镜参考图生成

- **触发**：步骤 7 完成。
- **节点**：N8N `Storyboard-Frames` → Seedream 4.0。
- **调用**：每个分镜出 1 张关键帧（共 4 张）作为视频生成的 first-frame 输入。
- **产出**：4 张 1080×1920 关键帧。
- **落点**：OSS `sku/YN-BRA-001/video/keyframes/shot<n>.jpg`。

### 步骤 9 · 视频提示词生成

- **触发**：步骤 8 完成。
- **节点**：N8N `Video-Prompt-Builder`。
- **产出**：4 条 Seedance 2.0 prompt（包含运镜、节奏、时长、首帧引用）。
- **落点**：PG `video_jobs(job_id, run_id, shot_id, prompt, first_frame_url, status='queued')`。

### 步骤 10 · 视频生成（Seedance 2.0）

- **触发**：步骤 9 入库。
- **节点**：N8N `Seedance-Submit` + `Seedance-Poll`（异步任务，30s 轮询一次，最多 20 分钟）。
- **调用**：火山方舟 `POST /api/v3/contents/generations/tasks`，model=`seedance-2.0-pro`，传 first-frame、prompt、duration。
- **产出**：4 段 3 秒分镜 mp4。
- **落点**：OSS `sku/YN-BRA-001/video/shots/shot<n>.mp4`，PG `video_jobs.result_url`。

### 步骤 11 · 视频拼接与合成

- **触发**：4 段分镜全部生成完毕。
- **节点**：N8N `FFmpeg-Compose` 节点（容器内 ffmpeg），按分镜顺序拼接 + 加 logo 水印 + 加片尾 + 可选字幕。
- **产出**：1 条 12 秒成片 + 1 张封面图。
- **落点**：OSS `sku/YN-BRA-001/video/final/<run_id>.mp4` 和 `.../cover.jpg`。

### 步骤 12 · 审核工作台回写

- **触发**：步骤 6（图片）和步骤 11（视频）任一完成。
- **节点**：N8N `Feishu-Writeback`，写入飞书表 `t_review_console`。
- **产出**：一条主任务行展开两个子表 — 图片候选 12 行 + 视频候选 1 行（如多版本则多行），每行带"通过 / 打回 / 备注"操作列。
- **审核动作**：
  - **通过** → 触发步骤 13。
  - **打回** → 写 `feedback` 字段，N8N 监听到事件后回到步骤 4 或 9，自动二次生成（最多 2 轮，超出走人工兜底）。

### 步骤 13 · 最终归档

- **触发**：审核通过事件。
- **节点**：N8N `Archive-Finalize`。
- **动作**：
  1. 把通过的素材从 `raw/` 移动到 `approved/` 路径。
  2. PG `runs.status` 置为 `archived`，写入 `approved_assets_json`。
  3. 飞书机器人推送总结消息到运营群（含成片 URL、缩略图、耗时、Token 消耗）。
- **最终落点**：
  - OSS `sku/YN-BRA-001/approved/images/*.jpg`
  - OSS `sku/YN-BRA-001/approved/video/final.mp4`
  - PG `runs` 留档可追溯。

**端到端耗时基线**：从步骤 1 录入到步骤 13 归档，YN-BRA-001 实测约 **22–35 分钟**（取决于火山侧排队），其中视频生成是最长环节（10–18 分钟）。

---

## 4. 多产品复用机制

样板跑通之后，第二个 SKU（例如 **YN-PNT-002 · 高腰提臀瑜伽裤 · 鲨鱼裤**）进来时，系统按"零改 / 配置 / 新写"三档划分。

### 4.1 零改动（直接复用）

- N8N 工作流图谱本身：13 步流程节点、连线、错误重试、回写逻辑全部不动。
- 数据库 schema：`runs / sku_profiles / image_jobs / video_jobs / brand_styles / review_logs` 6 张主表结构不动。
- OSS 路径规范：`sku/<SKU_CODE>/...` 命名约定不动。
- 飞书审核工作台：表结构、按钮、回写脚本不动。
- Seedream / Seedance / Claude 的调用代码、密钥、超时、重试策略不动。
- Caddy / Postgres / Redis / Worker 容器不动。

### 4.2 仅改配置（在飞书表里填即可，不进代码）

- SKU 基础字段：编码、名称、卖点、场景标签、目标受众。
- 参考图：`ref_images` 列上传新的 3–5 张产品图。
- 场景标签：瑜伽裤可能换成 "瑜伽馆 / 普拉提 / 街拍 / 通勤"。
- 出图数量、视频时长（10s / 12s / 15s）。
- 是否启用真人模特参考图（YN-PNT-002 由于需要展示版型可能勾选）。

### 4.3 需要新写（一次性，约半天工时）

- **品类专属 Prompt 片段**：在 `prompts/category_pants.md` 新增"瑜伽裤摄影常识"（侧位 45°、提臀线条、面料褶皱光影、避免裆部不自然）。
- **品类负向词库**：`prompts/neg_pants.md` 增加 "无版型、卡裆、布料穿透、不规则缝线"。
- **分镜脚本品类模板**：瑜伽裤强调动作展示，分镜节奏与内衣不同（瑜伽裤多用前后对比 + 拉伸动作）。
- **审核打分维度权重**：内衣重"支撑感"、瑜伽裤重"提臀效果与版型"，需要在 `prompts/image_qc.md` 调整权重表。

**复用结论**：第二款 SKU 的接入时间预计 **0.5–1 个工作日**（绝大部分时间在写品类 prompt 和验证 1 轮效果），第三款及以后通常 **2–4 小时** 即可。

---

## 5. 跨链路一致性

图片链路与视频链路最容易出问题的就是"两边长得不一样" — 同一个 SKU，图片是冷色调极简，视频成了暖色调健身房，客户必然投诉。架构层面用三个机制锁死一致性：

### 5.1 共享 SKU Profile

步骤 2 产出的 `sku_profile_json`（含核心卖点、面料关键词、禁用词）由两条链路共同读取。**这意味着两条链路看到的"产品是什么"是同一份事实，从源头消除歧义。**

### 5.2 共享品牌 Style Token

步骤 3 产出的 `style_snapshot_json` 是品牌侧的视觉锁定（色卡、光线、镜头、构图、情绪），写入 `runs.style_snapshot_json` 并固化为 run 级快照，**任何分镜、任何图片都引用同一个 token**，包括重生成也用同一份，杜绝"二次生成视觉漂移"。

### 5.3 模特 / 真人参考图统一池

如果客户提供模特参考图（face reference），存放于 OSS `brand/models/<model_id>/face.jpg` 与 `body.jpg`。Seedream 与 Seedance 调用时都把同一组参考图作为 `reference_image` 输入，确保**图片中的模特和视频中的模特一眼看就是同一个人**。视频分镜的关键帧（步骤 8）会先用 Seedream 生成、视频再 i2v 演化，这本身就是"图驱动视频"的强一致性范式。

### 5.4 一致性自检

步骤 11 拼接完成后增加一道"图片 Top-1 vs 视频封面"相似度检查（Claude 多模态 0–10 打分），低于 7 分自动触发打回 + 通知运营。

---

## 6. 部署拓扑

### 6.1 服务清单（docker-compose.yml）

| 服务 | 镜像 | 容器名 | 端口（容器内） | 暴露 | 角色 |
|------|------|--------|---------------|------|------|
| caddy | caddy:2.8-alpine | caddy | 80 / 443 | 公网 | TLS 终结 + 反向代理 |
| n8n | n8nio/n8n:1.85 | n8n | 5678 | 内网 | 工作流主控 + UI |
| n8n-worker | n8nio/n8n:1.85 | n8n-worker-1/2 | – | 内网 | 长任务执行 |
| postgres | postgres:16-alpine | pg | 5432 | 内网 | N8N 元数据 + 业务库 |
| redis | redis:7-alpine | redis | 6379 | 内网 | 队列 + 缓存 |
| ffmpeg-runner | jrottenberg/ffmpeg:6 | ffmpeg | – | 按需启动 | 视频拼接 |
| watchtower | containrrr/watchtower | wt | – | – | 镜像自动更新（可选） |

### 6.2 资源开销估算（2C4G VPS · Ubuntu 22.04）

| 服务 | CPU 平均 | 内存平均 | 磁盘 |
|------|---------|---------|------|
| n8n + worker×2 | 0.4 核 | 1.0 GB | 2 GB |
| postgres | 0.1 核 | 350 MB | 5 GB（含 1 年数据） |
| redis | 0.05 核 | 80 MB | 200 MB |
| caddy | 0.02 核 | 40 MB | – |
| ffmpeg（峰值） | 1.5 核（短时） | 600 MB | – |
| 系统 + 余量 | 0.3 核 | 800 MB | 5 GB |
| **合计平均** | **0.9 核** | **2.3 GB** | **12 GB** |
| **峰值** | 2.0 核（短时拼接时） | 3.0 GB | – |

**结论**：2C4G VPS 在常态吞吐（每天 5–15 个 SKU run）下完全够用；如果并发上 30 个 run/天，建议升 4C8G。视频生成本身不消耗本地算力（火山侧），本地只承担调度与拼接。

### 6.3 环境变量与密钥

`.env` 文件统一管理，挂载到容器，**密钥不进 Git**：

```
ARK_API_KEY=...                  # 火山方舟
NEWAPI_BASE=https://newapi.5dock.cn/v1
NEWAPI_KEY=...                   # 5dock 网关
OSS_ACCESS_KEY=...
OSS_SECRET=...
OSS_BUCKET=yn-content-factory
OSS_ENDPOINT=oss-cn-shanghai.aliyuncs.com
FEISHU_APP_ID=...
FEISHU_APP_SECRET=...
PG_PASSWORD=...
N8N_BASIC_AUTH_USER=admin
N8N_BASIC_AUTH_PASSWORD=...
```

### 6.4 备份策略

- PG：每日 03:00 `pg_dump` → OSS `backup/pg/YYYYMMDD.sql.gz`，保留 30 天。
- N8N 工作流：每次发布前导出 JSON 入仓库 `n8n/workflows/`。
- OSS：开启版本控制，`approved/` 路径加生命周期规则（180 天后转低频）。

---

## 7. 演示讲稿（3–5 分钟现场版）

> 现场环境：投影仪 + 飞书桌面端 + 浏览器 N8N + 阿里云 OSS 控制台四窗口预排好。

### 7.1 开场（30 秒）

> "X 总，今天给您看的不是 PPT，是已经在跑的真东西。我们用您给的样板内衣 YN-BRA-001 演示一遍：从一条飞书表录入，到产出 12 张候选场景图、1 条 12 秒卖点视频，再到您一键审核入库。整个过程不超过半小时，但今天为了节省时间，图和视频我提前跑了一份，我会同时启动一份新的让大家看流程是真在动。"

> "请记住三个数字：**1 个 SKU 启动、6 类素材产出、22 分钟全自动归档**。"

### 7.2 飞书多维表（45 秒）

切到飞书 `t_sku_intake` 表。

> "看这一行 —— SKU 编码、产品名、卖点、场景、参考图，您团队现在录商品的字段，几乎一模一样。我们故意没让您学新工具，运营在这填，下游全自动。"

> "现在我新增一行，run_mode 选 full（图片+视频），保存。"

回车保存的瞬间，切到 N8N 的执行视图。

### 7.3 N8N 工作流跑动（45 秒）

> "您看 N8N 这个图，每一个绿色方块代表一步。现在右上角已经亮起来了 —— 飞书 webhook 进来了，跳到 SKU 解析、风格解析、Prompt 生成 …… 这就是我刚才讲的 13 步链路在自己跑。"

> "这里我先暂停讲流程细节，咱们直接去看产出物，不然要等 20 分钟。"

### 7.4 图片成果展示（60 秒）

切到飞书 `t_image_review` 工作台，展示已经预跑好的 YN-BRA-001 图片候选。

> "这是上一轮跑出来的 12 张候选。每一张都标了品牌一致性、卖点呈现、真实感、合规四个维度的 AI 评分。这张瑜伽馆场景的得了 9.2，您看面料质感、模特动作、构图都符合您的样品风格。"

> "右边这一列是审核操作 —— 通过、打回、备注。打回会自动重新生成，最多 2 轮。"

> 现场点一下"通过"演示一下飞书内的视觉反馈。

### 7.5 视频成果展示（60 秒）

切到 OSS 控制台或预先打开的播放器，播放 12 秒成片。

> "这条 12 秒视频是 4 个分镜拼出来的：开场产品悬浮、拉链特写、跑步动态、logo 收尾。声音、节奏、字幕都已经在分镜脚本里规划好了。"

> "关键是 —— 您注意视频里的模特和刚才图片里的，是不是同一个人、同一个妆面、同一个发型？这就是我们做的跨链路一致性。换其他品牌、换其他 SKU，这个机制都成立。"

### 7.6 审核归档与多产品复用（45 秒）

> "审核通过后，所有素材自动归档到您的阿里云 OSS，按 SKU 分目录。您随时可以下载、可以挂到您电商后台。"

> "**最关键的一点 —— 第二款产品（瑜伽裤、运动 T 恤）进来，运营只在飞书表填资料就行，工作流一行代码不改。我们这边只在第一次接入新品类时写一个品类提示词包，半天搞定。后面您每加一个 SKU，几乎是零边际成本。**"

### 7.7 收尾（30 秒）

> "总结一下：**统一输入是飞书、统一审核是飞书、统一归档是 OSS、引擎是 VPS 上一套 docker。** 单产品打样达标后，多产品复用是开关级的事。"

> "我们今天演示用的就是您的 YN-BRA-001 真实数据。如果效果您 OK，下周我们就可以开始接您的第二款产品，同时把客户老板您最关心的退款 / 返工边界条款落到合同里。"

---

## 8. 风险与未决项

下面这些事项**今天演示后必须得到客户书面确认**，否则进入打样阶段会卡住。客户角色不一定都是技术人，所以右侧准备了"标准应答口径"。

### 8.1 必须确认事项清单

| # | 事项 | 期望客户给出 | 备注 |
|---|------|-------------|------|
| 1 | 阿里云 OSS 账号 | 提供子账号 AK/SK，bucket 写权限 | 如客户没有，可由我方代开但费用由客户承担 |
| 2 | 是否接受飞书作为入口 | 接受 / 不接受（不接受则提供 Notion / Lark / 自研后台二选一） | 飞书是默认推荐，最快上线 |
| 3 | 火山方舟账号 | 已开通的 ARK_API_KEY + 充值额度 | 默认按量计费，建议预存 ¥3000 |
| 4 | 5dock NewAPI 网关账号 | API Key + 月配额 | 用于 Claude 调用 |
| 5 | 参考图与样品视频提供方式 | 多少张原图、是否有版权 | 必须客户拥有商用授权 |
| 6 | 模特肖像权 | 真人模特：肖像授权书；AI 模特：无授权问题 | 真人模特用作参考图必须授权 |
| 7 | VPS 提供方 | 客户提供 / 我方代购转售 | 推荐 4C8G 起 |
| 8 | 验收口径 | "和样本一样或更高" 的具体判定人和评分维度 | 必须落到合同 |
| 9 | 返工边界 | 单 SKU 二次生成 ≤2 轮，超出按人工返工计 | 防无限返工 |
| 10 | 保修期范围 | 1 个月内：bug 修复、参数微调；不含新需求 | PDF 已注明 |

### 8.2 客户问、我们答（演练）

**Q1：能不能换更便宜的图片模型？**
> A：可以替换，架构是模型解耦的 —— 只需在 N8N 的 `Image-Submit` 节点改一个 endpoint 和参数映射，业务流不动。但**首期打样建议先用 Seedream 4.0 把效果天花板打出来**，确认验收通过后，再讨论降本替换。同样的话适用于视频侧（可换 Kling、Runway）。

**Q2：万一火山或 OpenAI 节点挂了怎么办？**
> A：链路里每个外部调用都设了三档保护 —— 超时 60s、自动重试 2 次、失败写入飞书告警表通知运营。整个 run 不会因为某一步失败而丢，会停在失败步骤等人工 / 自动恢复。Postgres 里 run 状态机完整，**任何时候断点续跑都可以**。

**Q3：审核打回循环会不会无限烧钱？**
> A：硬性上限 —— 同一个 run 自动二次生成 2 轮，超出锁定状态等人工介入。每个 run 在 PG 有 token / 调用次数累计，超过预设阈值（例如单 run ¥30）自动告警。可以做到**不会有意外账单**。

**Q4：我们换一个品类，比如做瑜伽裤、做运动 T，是不是要重新做？**
> A：不需要。架构那一节我讲了 —— 流程零改动、配置在飞书填、只多写一份品类提示词，半天完成。第二款产品的边际成本极低，这就是"内容工厂"的核心价值。

**Q5：数据安全和私有化？**
> A：所有数据落您自己的 VPS、自己的阿里云 OSS、自己的飞书 —— 我们这边不持有任何素材副本。N8N 是自托管的，工作流定义文件您可以随时导出。**所有权 100% 是您的**。

**Q6：交付完之后我们想自己改怎么办？**
> A：N8N 是低代码，运营懂一点逻辑就能改节点参数。代码层面我们交付 docker-compose、prompt 模板、PG schema、运维手册。**保修期 1 个月内 bug 免费修，参数级调优也免费；新增功能按工作量另算**。

### 8.3 演示后的"今天必须签"清单（提示销售同事）

1. 阿里云 OSS 账号开通确认。
2. 火山方舟 + NewAPI key 提供时间。
3. 验收口径（"和样本一样或更高"由谁评、按什么标准评）。
4. 返工 2 轮上限的认可。
5. 真人 vs AI 模特路线决策。

---

## 附录 A · 关键数据库表速览

```sql
-- 主任务流水
CREATE TABLE runs (
  run_id        VARCHAR(32) PRIMARY KEY,
  sku_code      VARCHAR(32) NOT NULL,
  payload_json  JSONB NOT NULL,
  style_snapshot_json JSONB,
  status        VARCHAR(16) NOT NULL,  -- received|running|review|archived|failed
  approved_assets_json JSONB,
  created_at    TIMESTAMPTZ DEFAULT now(),
  updated_at    TIMESTAMPTZ DEFAULT now()
);

-- SKU 解析结果（可版本化）
CREATE TABLE sku_profiles (
  sku_code      VARCHAR(32),
  version       INT,
  profile_json  JSONB NOT NULL,
  PRIMARY KEY(sku_code, version)
);

-- 图片任务
CREATE TABLE image_jobs (
  job_id        VARCHAR(32) PRIMARY KEY,
  run_id        VARCHAR(32) REFERENCES runs(run_id),
  scene         VARCHAR(32),
  prompt        TEXT,
  neg_prompt    TEXT,
  result_urls   JSONB,
  qc_score_json JSONB,
  status        VARCHAR(16),
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- 视频任务（同时记录分镜 + 成片）
CREATE TABLE video_jobs (
  job_id        VARCHAR(32) PRIMARY KEY,
  run_id        VARCHAR(32) REFERENCES runs(run_id),
  shot_id       INT,
  prompt        TEXT,
  first_frame_url TEXT,
  result_url    TEXT,
  status        VARCHAR(16),
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- 品牌风格字典
CREATE TABLE brand_styles (
  brand_code    VARCHAR(32) PRIMARY KEY,
  style_json    JSONB NOT NULL,
  updated_at    TIMESTAMPTZ DEFAULT now()
);

-- 审核日志
CREATE TABLE review_logs (
  log_id        BIGSERIAL PRIMARY KEY,
  run_id        VARCHAR(32),
  asset_type    VARCHAR(8), -- image|video
  asset_ref     VARCHAR(64),
  action        VARCHAR(16), -- pass|reject|comment
  reviewer      VARCHAR(64),
  feedback      TEXT,
  created_at    TIMESTAMPTZ DEFAULT now()
);
```

## 附录 B · OSS 路径规范

```
yn-content-factory/
├── brand/
│   ├── styles/yn.json
│   └── models/<model_id>/{face.jpg,body.jpg,license.pdf}
├── sku/
│   └── YN-BRA-001/
│       ├── profile/v1.json
│       ├── prompts/{image_v1.json,video_v1.json}
│       ├── images/raw/<scene>/<job_id>_<idx>.jpg
│       ├── images/approved/*.jpg
│       ├── video/storyboard_v1.json
│       ├── video/keyframes/shot<n>.jpg
│       ├── video/shots/shot<n>.mp4
│       └── video/final/<run_id>.{mp4,cover.jpg}
└── backup/
    └── pg/YYYYMMDD.sql.gz
```

---

*文档结束。本架构文档随项目演进维护，所有命名、字段、路径以本文为准。*
