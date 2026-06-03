# AI 内容工厂图片生成链路设计

版本 v1.0 | 2026-05-05 | 首期样品 SKU：YN-BRA-001（黑色高弹速干运动内衣 - 前拉链款）

---

## 0. 适用范围与设计目标

本文档描述"内容工厂"项目中**图片链路**的端到端实现。链路负责把客户提交的产品资料（SKU、卖点、参考图、风格倾向）转化为一组通过审核的商业级电商图片（白底商品图、模特上身图、场景图、细节特写）。设计同时满足以下硬约束：

1. **可复用模板能力**——首期跑通 YN-BRA-001 之后，再来一款瑜伽裤、运动 T 恤可以走同一条链路、只换 `style_template` 和 `product` 行；
2. **服装类一致性**——同一批 8-12 张图必须是同一个模特、同一种皮肤光感、同一个 logo 位置；
3. **审核闭环**——每张图都进飞书多维表，审核员通过 / 打回，打回后能基于反馈做二次生成而不是从头跑；
4. **成本可控**——每个 SKU 平均出图 30 张候选、过审 8-12 张，单产品图片预算锁在 ¥40 以内。

技术栈：N8N 工作流编排 + Volcengine Ark API（Seedream 4.0，模型 ID `doubao-seedream-4-0-250828`）+ 5dock NewAPI（Claude Sonnet 4.6）+ PostgreSQL 任务库 + 阿里云 OSS 媒体归档 + 飞书多维表审核面板。

---

## 1. 模型介入说明

图片链路中的模型主要分成两类：

1. **文字模型**：Claude Sonnet 4.6  
   负责理解商品资料、提炼卖点、生成 prompt。
2. **图像模型**：Seedream 4.0  
   负责根据 prompt 和参考图实际生成图片。

也就是说，图片链路不是“单次模型调用直接出图”，而是“LLM 先完成理解与提示词构建，再由图像模型执行生成”。

### 1.1 三次 LLM 介入

在图片链路里，Claude 一共介入三次，职责不同：

| 阶段 | 内部代号 | 输入 | 输出 | 作用 |
|---|---|---|---|---|
| 属性提取 | LLM-A | 商品文字资料、参考图 | 结构化属性 JSON | 把原始资料整理成标准字段 |
| 卖点提炼 | LLM-B | 结构化属性、原始卖点 | 卖点列表 + 视觉表达建议 | 把“卖点”转成“适合被拍出来的点” |
| Prompt 组装 | LLM-C | 属性、卖点、风格模板、镜头清单 | 多条英文 prompt | 把生成需求翻译成模型可执行的 prompt |

### 1.2 Seedream 的介入位置

Seedream 在 LLM-C 之后介入。

它拿到的是：

- 英文图片 prompt
- negative prompt
- 模特参考图
- 商品参考图
- 可选场景参考图
- guidance_scale / size / seed 等参数

它产出的是：

- 候选图片 URL
- 对应的生成结果

所以 Seedream 不负责“理解商品是什么”，它只负责“按照前面准备好的 prompt 和参考图来生成”。

### 1.3 哪些步骤不是模型在做

下面这些步骤都不是模型：

- PostgreSQL 读资料
- n8n 的分支调度与重试
- OSS 上传与缩略图归档
- 候选写库
- 飞书回写
- 审核员做通过 / 打回 / 二次生成决策

如果后面要排问题，这个区分很重要：  
“图像质量不理想”通常优先检查 prompt 和参考图；  
“流程没有跑通”通常优先检查 n8n、数据库和回写节点。

---

## 2. 端到端步骤图（ASCII）

```
                                  内容工厂 · 图片链路
   ┌──────────────────────────────────────────────────────────────────────────┐
   │                                                                          │
   │  [0] 飞书多维表 / Web 表单                                                 │
   │      ↓ products 行 + reference imgs + style_template_id                  │
   │                                                                          │
   │  [1] N8N Webhook /trigger/image  ── task_id, product_id ──┐              │
   │                                                            │              │
   │  [2] Postgres 读取 products + style_templates + refs ─────┘              │
   │                                                                          │
   │  [3] LLM-A: 属性提取（24 字段结构化）                                     │
   │      ↳ 5dock NewAPI · claude-sonnet-4-6 · prompt 01                     │
   │                                                                          │
   │  [4] LLM-B: 卖点提炼 5-7 条 + 视觉表达建议                                │
   │      ↳ 5dock NewAPI · claude-sonnet-4-6 · prompt 02                     │
   │                                                                          │
   │  [5] LLM-C: 商品图 / 场景图 prompt 组装（11 个变体英文 prompt）           │
   │      ↳ 5dock NewAPI · claude-sonnet-4-6 · prompt 03 + 04                │
   │      ↳ 注入 brand_palette + model_descriptor + reference image refs     │
   │                                                                          │
   │  [6] Split In Batches → 11 路并发                                        │
   │      每批一个 prompt，写入 generation_runs（status=running）             │
   │                                                                          │
   │  [7] Volcengine Ark · Seedream 4.0                                      │
   │      POST /api/v3/images/generations  (异步任务 ID)                     │
   │      ↳ 轮询 /api/v3/images/generations/{id}  每 6s 一轮，最多 20 轮     │
   │                                                                          │
   │  [8] 下图 + OSS 归档（archive/<sku>/<run_id>/<idx>.png）                │
   │      ↳ 同步生成 1024x1024 缩略图到 archive/.../thumb_<idx>.jpg          │
   │                                                                          │
   │  [9] 写 candidates 表（含 prompt、seed、ref_images、metadata）           │
   │      ↳ 写 audit_log: stage=image_generated                              │
   │                                                                          │
   │ [10] 飞书多维表新增审核行（图片缩略图 + 通过/打回按钮）                   │
   │ [11] 飞书消息群推 @ 审核员                                               │
   │                                                                          │
   │ [E]  任一步异常 → generation_runs.status=failed + 飞书告警               │
   │                                                                          │
   └──────────────────────────────────────────────────────────────────────────┘
```

每个数字节点对应 `n8n/image-workflow.json` 里一个或一组节点，节点 ID 命名规则 `n_NN_short_name`（如 `n_07_seedream_submit`），便于回查。

---

## 3. 每步详解：输入 / 输出 / 依赖 / 失败处理

### Step 1 — Webhook Trigger

* **输入**：`POST /webhook/trigger/image`，body `{ "task_id": "uuid", "product_id": "YN-BRA-001", "style_template_id": 1, "shot_set": "full" }`。
* **输出**：原样透传到 [2]，附 `run_started_at`。
* **失败**：N8N webhook 自身高可用，理论不会失败；外层若调用方未传 task_id，立即 4xx 并不写库。

### Step 2 — Postgres 读取

* **输入**：`task_id`。
* **SQL**：
  ```sql
  SELECT p.*, st.brand_palette, st.model_descriptor, st.lighting, st.negative_prompt
  FROM products p
  JOIN tasks t ON t.product_id = p.id
  JOIN style_templates st ON st.id = $style_template_id
  WHERE t.id = $task_id;
  ```
* **输出**：合并对象 `{ product, style }` 进 N8N item context。
* **失败**：找不到行 → 写 `generation_runs.status='failed', error='task_not_found'`，flow stop。

### Step 3 — LLM-A 属性提取

* **API**：`POST https://5dock.com/v1/chat/completions`，model `claude-sonnet-4-6`，temperature 0.2，response_format `json_object`。
* **输入**：产品文字资料 + 参考图 OSS URL（多模态）+ Prompt 01 模板。
* **输出**：24 字段 JSON（color、material、silhouette、neckline、sleeve、closure、logo_placement、care_instructions...），写入 `products.attributes_json`。
* **失败**：JSON parse 失败 → 二次重试一次；仍失败标 run 失败、不阻塞流程兜底（但下游会因关键字段缺失降级为不带 logo 的 prompt）。

### Step 4 — LLM-B 卖点提炼

* **API**：同上，temperature 0.4。
* **输入**：products.attributes_json + 原始卖点字符串 + Prompt 02。
* **输出**：`selling_points: [{rank, text, visual_hint}, ...]`，5-7 条。
* **失败**：少于 3 条直接判失败。

### Step 5 — LLM-C Prompt 组装

* **API**：同上，temperature 0.6。
* **输入**：attributes + selling_points + style_template + 期望镜头列表（6 商品 + 5 场景 = 11 个）+ Prompt 03/04。
* **输出**：`prompts: [{shot_id, shot_type, en_prompt, negative_prompt, suggested_size, ref_image_ids[], guidance_scale, seed_hint}, ...]`。
* **关键注入**：
  - `brand_palette = "matte black with subtle charcoal undertone, no warm color cast"` → 拼到每条 prompt；
  - `model_descriptor = "East Asian woman, age 28, athletic build, height 168cm, shoulder-length straight black hair, natural makeup, slight tan"` → 拼到所有有模特的 prompt；
  - `reference image refs` → `[reference: model_ref_001.jpg, weight: 0.7]` 形式拼在 prompt 末尾。
* **失败**：缺关键字段 → run 失败。

### Step 6 — Split In Batches

* 把 11 个 prompt 分 11 个分支并发，并发上限由 N8N `Split In Batches` 的 batchSize 控制（设 4，配合下游限流）。

### Step 7 — Seedream 4.0 调用

* **endpoint**：`POST https://ark.cn-beijing.volces.com/api/v3/images/generations`
* **header**：`Authorization: Bearer {{$credentials.volcengineArk.apiKey}}`
* **body**（详见第 3 节）。
* **响应**：同步返回 `data[0].url`（Seedream 走同步直出 PNG URL，无需轮询）。如果未来切到异步任务模式，则需轮询 `/api/v3/images/tasks/{id}`，本设计同时保留该分支并默认走同步。
* **失败**：HTTP 5xx 重试 2 次（指数退避 4s/16s）；429 → 加 30s 等待后重试 1 次；4xx 直接标 candidate 失败但不中断 batch。

### Step 8 — OSS 归档

* **路径规范**（与 schemas/archive 对齐）：`oss://yfn-content-factory/archive/{sku}/{run_id}/{shot_id}_{idx}.png`
* **缩略图**：1024x1024 JPEG quality 80 → `thumb_{shot_id}_{idx}.jpg`
* **EXIF / metadata**：写入 `x-oss-meta-prompt-hash`、`x-oss-meta-seed`、`x-oss-meta-model`、`x-oss-meta-run-id`。
* **失败**：OSS PUT 失败重试 3 次；仍失败 → candidate.status='failed', store_error。

### Step 9 — 写 candidates 表

字段（与另一 agent 在写的 schema 对齐）：

```sql
INSERT INTO candidates (
  id, run_id, product_id, shot_id, shot_type,
  prompt_text, negative_prompt, model_name, seed,
  ref_image_ids, guidance_scale, image_size,
  oss_key, oss_thumb_key, oss_url, oss_thumb_url,
  generation_cost_cny, generation_ms,
  metadata_json, status, created_at
) VALUES ( ... );
```

`metadata_json` 内含：`{ "ark_request_id", "watermark_off", "fabric_keywords", "logo_preserved": true, "brand_palette_hash" }`。

### Step 10 — 飞书多维表回写

* 调用飞书开放平台 `POST /open-apis/bitable/v1/apps/{app_id}/tables/{table_id}/records`。
* 单元格映射：`封面`（附件，传 OSS thumb URL）、`SKU`、`镜头`（单选）、`Prompt`（长文本）、`审核状态`（默认"待审核"）、`run_id`、`candidate_id`、`生成时间`。

### Step 11 — 飞书消息通知

* 群机器人 webhook，发"@审核员 SKU YN-BRA-001 本批生成 11 张候选已就绪，请前往多维表审核"，附多维表筛选链接。

### Step E — 错误兜底分支

* 任意 HTTP / Postgres 节点 `On Error: continue (Use Error Output)`，统一走 `n_E_error_handler` Function 节点：
  1. 更新 `generation_runs SET status='failed', error_code=?, error_msg=?, finished_at=now() WHERE id=?`；
  2. 写 `audit_log` 一行，stage='error'；
  3. 飞书告警群 webhook 发文本。

---

## 4. Seedream 4.0 调用参数策略

### 4.1 Body 模板（POST /api/v3/images/generations）

```json
{
  "model": "doubao-seedream-4-0-250828",
  "prompt": "<英文 prompt 80-150 词，详见 prompts/image/03 和 04>",
  "image": [
    "https://yfn-content-factory.oss-cn-shanghai.aliyuncs.com/refs/YN-BRA-001/model_ref_001.jpg",
    "https://yfn-content-factory.oss-cn-shanghai.aliyuncs.com/refs/YN-BRA-001/product_ref_002.jpg"
  ],
  "size": "2048x2048",
  "seed": 884213,
  "guidance_scale": 5.5,
  "watermark": false,
  "response_format": "url",
  "negative_prompt": "low quality, deformed body, extra fingers, distorted logo, color shift to navy blue or brown, plastic-looking fabric, oversaturated, text artifacts, watermark"
}
```

### 4.2 size 策略

| 用途 | size | 比例 | 备注 |
|---|---|---|---|
| 商品图主图 | `2048x2048` | 1:1 | 电商主图标准 |
| 详情页竖图 | `1536x2048` | 3:4 | 上身全身 |
| 场景图横幅 | `2048x1152` | 16:9 | banner |
| 细节特写 | `2048x2048` | 1:1 | 面料 / 拉链微距 |

### 4.3 watermark

恒定 `false`。Seedream 默认开水印，必须显式关。

### 4.4 guidance_scale

* 商品图（白底 / 纯色背景，要求精准还原）：`6.5-7.5`，prompt 服从度高；
* 场景图（要 AI 自由发挥环境光、构图）：`4.5-5.5`；
* 默认 `5.5`，由 Prompt 03/04 输出 JSON 里的 `guidance_scale` 字段决定。

### 4.5 reference_images（image 数组）传法

Ark 的 Seedream 入参是 `image: [url1, url2, ...]`（最多 4 张）。我们的传法：

| 槽位 | 用途 | weight 表达 |
|---|---|---|
| image[0] | **模特参考图**（必填，保证人脸 / 身材一致） | 在 prompt 文本里加 `[reference: model_ref, weight: 0.75]` |
| image[1] | **产品参考图**（客户提供的实物图，保 logo 和版型） | `[reference: product_ref, weight: 0.85]` |
| image[2] | **场景参考图**（可选，仅场景拍） | `[reference: scene_ref, weight: 0.5]` |
| image[3] | 备用 | — |

注意：Seedream 当前 API 不直接支持 per-image weight 字段，权重是写在 prompt 里给模型读的"语义提示"。模型实测能识别 `[reference: foo, weight: 0.8]` 这种花括号风格的 hint 并优先模仿对应图。

### 4.6 negative_prompt 标准模板

```
low quality, blurry, deformed body, extra fingers, distorted logo, mismatched logo position,
color shift to navy blue or brown or warm tone, plastic-looking fabric, oversaturated,
text artifacts, watermark, multiple people, face swap inconsistent, see-through fabric where not intended,
visible bra straps misaligned, wrinkled poorly, AI hands artifacts
```

### 4.7 seed 策略

* 同一个 SKU 同一次 run：每个 shot 用不同 seed（让画面不重复）；
* 二次生成（审核打回）：复用上一次过审镜头的 seed 作为 `seed_hint`，prompt 微调即可保持模特同款；
* seed 写到 candidates 表，便于复现。

---

## 5. 参考图分类与使用规范

| 分类 | 来源 | 命名 | 何时进 image[] | weight |
|---|---|---|---|---|
| **客户参考图** | 客户实拍或客户提供的同类商品图 | `refs/{sku}/customer_ref_NN.jpg` | 商品图必带 | 0.8-0.9 |
| **模特参考图** | 第一轮 run 里挑出的过审正面图，作为后续所有图的 anchor | `refs/{sku}/model_ref_NN.jpg` | 所有有模特的镜头必带 | 0.7-0.8 |
| **场景参考图** | 客户上传的环境图（瑜伽馆、健身房）或库内备选 | `refs/scenes/{scene_tag}_NN.jpg` | 场景图带 | 0.4-0.6 |

**模特一致性策略（核心）**：

1. 第一次 run，正面镜头 `shot_normal_front` 不带 model_ref（因为还没有），用 `model_descriptor` 文字描述；
2. 这张图过审后，由人工或 LLM 自动选成 `model_ref_001.jpg`，写入 `products.canonical_model_ref`；
3. 之后所有该 SKU 的 run，所有镜头 image[0] 都是 `model_ref_001.jpg`，prompt 加 "same model as reference, identical face shape and skin tone"；
4. 跨 SKU 复用时，由审核员勾选"复用此 SKU 的模特"或"另选新模特"。

---

## 6. 候选图 metadata（写回 candidates 表）

每张候选必带：

```json
{
  "candidate_id": "uuid",
  "run_id": "uuid",
  "product_id": "YN-BRA-001",
  "shot_id": "shot_studio_front",
  "shot_type": "studio | model | detail | scene",
  "model_name": "doubao-seedream-4-0-250828",
  "model_provider": "volcengine_ark",
  "prompt_text": "<英文 prompt 全文>",
  "negative_prompt": "<...>",
  "seed": 884213,
  "guidance_scale": 5.5,
  "image_size": "2048x2048",
  "ref_image_ids": ["model_ref_001", "product_ref_002"],
  "ark_request_id": "20260505-abc123",
  "oss_key": "archive/YN-BRA-001/run-2026-05-05-1430/shot_studio_front_01.png",
  "oss_url": "https://yfn-content-factory.oss-cn-shanghai.aliyuncs.com/...",
  "oss_thumb_url": "https://.../thumb_shot_studio_front_01.jpg",
  "image_bytes": 4823100,
  "image_width": 2048,
  "image_height": 2048,
  "generation_ms": 8230,
  "generation_cost_cny": 0.32,
  "fabric_keywords": ["breathable mesh", "sweat-wicking nylon-spandex blend"],
  "logo_preserved": true,
  "brand_palette_hash": "sha1:matteblack-v1",
  "status": "pending_review",
  "created_at": "2026-05-05T14:30:12+08:00"
}
```

---

## 7. 并发与限流（Volcengine Ark RPM 约束）

* **官方限额参考**：Seedream 4.0 默认 RPM 约 60，TPM 看图片不限制（图片走次数计费，按张）。开通方舟"标准版"后可申请提至 300 RPM。
* **本链路并发模型**：
  - N8N `Split In Batches` 节点 batchSize=4 → 同一时间最多 4 路在调 Ark；
  - 每路单图典型耗时 6-10s → 单分钟实际请求量约 4 × 6-10 = 24-40 次/分钟，远在 60 RPM 内；
  - 多 SKU 同时跑（例如同时 3 个产品）→ 全局信号量在 N8N 用 Redis 锁实现，key=`ark:rpm:slot`，TTL 1s，最多 50 个槽位（保留 10 给手动测试）。
* **重试 / 限流响应**：429 错误码 → 节点配 `Retry On Fail = true, Max Tries = 3, Wait Between Tries = 30000ms`。
* **超时**：单次 HTTP timeout 90s；超过即视为失败进重试。

---

## 8. 风格一致性（style_template 注入机制）

`style_templates` 表（schemas 里另一 agent 在建）核心字段：

```sql
CREATE TABLE style_templates (
  id              SERIAL PRIMARY KEY,
  category        VARCHAR(50),         -- '运动内衣' / '瑜伽裤' / '运动 T 恤'
  brand_palette   TEXT,                -- "matte black with subtle charcoal undertone, no warm cast"
  model_descriptor TEXT,               -- "East Asian woman, age 28, athletic build, ..."
  lighting        TEXT,                -- "soft natural daylight from large window, slight rim light"
  composition     TEXT,                -- "centered subject, rule of thirds for scene shots"
  lens            TEXT,                -- "85mm equivalent, f/2.8"
  mood            TEXT,                -- "calm, professional, energetic but not aggressive"
  negative_prompt TEXT,                -- 共用 negative
  ref_seed_range  INT[]                -- 推荐 seed 区间
);
```

**注入路径**：
- LLM-C 在生成 prompt 时，把上述字段以**结构化引用**形式喂入 system prompt（见 `prompts/image/03-product-shot-prompt.md` 的 System Prompt 段）；
- LLM 输出的英文 prompt 必须把 `brand_palette`、`lighting`、`mood` 三段拷贝/改写进每一条镜头 prompt，保证 11 张图视觉语义对齐；
- `negative_prompt` 直接拷贝到 Seedream 调用参数里。

**横向扩展**：换品类时，只新建一行 `style_templates`，比如瑜伽裤的 mood 可能是 "soft and flexible, emphasis on stretch fabric"，链路代码不改。

---

## 9. 成本估算

公开口径（截至 2026-05）：Seedream 4.0 在火山方舟标准定价约 **¥0.30 / 张** （2048x2048 1:1）；竖图 / 横图同价位段。Claude Sonnet 4.6 走 5dock 价格约 ¥18 / 1M input tokens、¥90 / 1M output tokens。

单 SKU（YN-BRA-001）成本：

| 项 | 用量 | 单价 | 小计 |
|---|---|---|---|
| LLM-A 属性提取（带图多模态） | 4k input + 1k output tokens | — | ¥0.16 |
| LLM-B 卖点提炼 | 2k input + 1k output | — | ¥0.13 |
| LLM-C Prompt 组装 | 6k input + 3k output | — | ¥0.38 |
| Seedream 候选图 | 11 镜头 × 平均 3 张/镜头 = 33 张 | ¥0.30 | ¥9.90 |
| 二次重生（按 30% 重生率） | ~10 张 | ¥0.30 | ¥3.00 |
| OSS 存储（首月 2GB） | 2GB × ¥0.12/GB | — | ¥0.24 |
| **单 SKU 合计** | | | **≈ ¥13.8** |

加上人工审核工时（独立计量），单产品图片预算 ¥15-20，远低于 ¥40 上限。批量跑 50 个 SKU 的月成本约 ¥700-1000（不含审核人工）。

---

## 10. 失败模式总览

| 失败点 | 触发条件 | 兜底动作 |
|---|---|---|
| Postgres 读不到 task | task_id 不存在 | 立即 fail，飞书告警 |
| LLM 返回非 JSON | parse 异常 | 重试 1 次 → 仍失败标 run failed |
| LLM 卖点 < 3 条 | 数量校验失败 | run failed |
| Ark 429 | 限流 | 等 30s 重试 3 次 |
| Ark 5xx | 服务端 | 指数退避重试 2 次 |
| Ark 4xx 内容审核拒绝 | 敏感词 | 该 candidate 标 rejected_by_provider，不重试 |
| OSS PUT 失败 | 网络 / 鉴权 | 重试 3 次 |
| 飞书多维表写入失败 | 字段映射错 | 写本地 retry 队列，5 分钟后重试一次，再失败仅告警不阻塞 |
| 审核员 24h 未审 | 看 audit_log | cron job 每天扫一次 → 飞书 @ 提醒 |

---

## 11. 与 schemas 对齐的关键约束

为避免和另一个 agent 在并行写的 schema 冲突，本文档遵守以下命名约定（已与 `schemas/00-naming-conventions.md` 草案对齐）：

* 表名：`products`、`tasks`、`generation_runs`、`candidates`、`audit_log`、`style_templates`、`reference_images`；
* 主键：`id UUID DEFAULT gen_random_uuid()`，products 例外用 `sku VARCHAR(64)`；
* 时间字段：`created_at TIMESTAMPTZ DEFAULT now()`，`updated_at` 由 trigger 维护；
* OSS 路径前缀：`archive/{sku}/{run_id}/...` 或 `refs/{sku}/...`；
* 状态枚举：generation_runs.status ∈ {pending, running, succeeded, failed, partial}；candidates.status ∈ {pending_review, approved, rejected, archived}；
* 货币：所有金额以 CNY 计，DECIMAL(10,4)。

如发生命名冲突，以 schemas 目录最终落地版本为准，本文档随后改齐。

---

## 12. 二次生成（rework loop）机制

候选图被审核员"打回"后，链路必须支持低成本的二次生成，而不是从头跑整条链路。落地方式：

1. 飞书多维表"打回"按钮触发副 webhook `/trigger/image_rework`，body：`{ candidate_id, feedback_cn }`；
2. N8N 子流程读 candidate 行，把原 prompt + feedback_cn 一起喂回 LLM-C 的"修订模式" system prompt（"You are revising an existing Seedream prompt. The reviewer says: <feedback_cn>. Output a revised en_prompt that addresses the feedback while keeping all other constraints intact, especially logo placement, model identity, brand_palette."）；
3. 修订后的 prompt 用**新 seed**（避免完全重画）+ 复用原 ref_image_ids；
4. 新候选 candidate 行的 `parent_candidate_id` 指向原 candidate，便于审核员对比"改前 / 改后"；
5. 同一 candidate 最多 3 轮修订，超过则锁定为人工干预。

修订模式典型反馈与 LLM 对应改写策略：

| 反馈类型 | 反馈样例 | LLM 改写动作 |
|---|---|---|
| 颜色色偏 | "黑色偏蓝了" | 在 prompt 里强化 "neutral matte black, absolutely no shift to navy or cool blue, slight charcoal warmth acceptable" |
| 模特表情 | "表情太严肃了" | 把 "calm confident expression" 改为 "calm confident with subtle warm smile" |
| 拉链不对 | "拉链拉得太低，露太多" | 改为 "front zipper closed at upper sternum, neckline modest" |
| 场景不像 | "瑜伽馆不像中国的" | 加 "East Asian boutique yoga studio aesthetic, light wood floor, paper-covered windows, minimalist" |
| Logo 跑了 | "logo 位置不对" | 强化 "preserve original tonal logo on left chest, exactly 6cm below collarbone, not on right chest" |
| 镜头太近 | "想看到全身" | 把 "framing chest to lower face" 改为 "full body framing head to mid-thigh" |

修订成本：每次约 ¥0.5（一次 LLM 调 + 一张 Seedream 图）。

---

## 13. 模特一致性的工程实现细节

服装类生成最难的就是"同一批 8-12 张图必须是同一个模特"。Seedream 4.0 的多 image 入参在权重文本提示下能维持一定一致性，但仍有约 10-15% 的样本会出现"脸像但不是同一人"的偏差。本设计的多重防御：

**第一道防线 — model_descriptor 文字描述**
prompt 里固定 7 项可控属性：种族、年龄、身高、体型、发型、肤色、妆容。任何一项变化都会导致跨图差异，所以 LLM-C 必须**逐字复制**这段文字到每条 prompt（不要让 LLM 改写它）。在 system prompt 里硬性要求 "Inject model_descriptor VERBATIM"。

**第二道防线 — 首张过审图作为 model_ref_001**
第一次 run 没有 model_ref，只能靠文字。一旦 `studio_front` 镜头过审，自动把这张写入 `products.canonical_model_ref`，路径为 `oss://yfn-content-factory/refs/{sku}/model_ref_001.jpg`。后续所有 run 的所有镜头都把 model_ref_001 放在 `image[0]`。

**第三道防线 — 跨 SKU 模特库**
如果同一个客户做多 SKU（同品牌运动系列），可以让审核员标记"此 model_ref 复用范围 = 全品牌"，写到 `reference_images.scope = 'brand_global'`。这样新 SKU 的 LLM-C 优先抓全局模特库的 ref，避免每个 SKU 都重新建立一次模特一致性。

**第四道防线 — 一致性体检**
每个 run 结束后跑一个轻量校验：把 11 张候选的人脸 embedding（用本地 InsightFace 或 face_recognition 库，N8N 跑一个 Python Code 节点）算两两余弦相似度。低于阈值 0.55 的两张图标 `face_consistency_warning`，写到 `candidates.metadata_json.face_consistency_score`。审核员看多维表时按这一列过滤，被标警告的优先复审。

**模特"种子"换人流程**
当客户说"这个模特换一下"，操作路径：
1. 在 `reference_images` 表把当前 model_ref 标 `archived`；
2. 单独跑一次"模特候选生成"，只跑 `studio_front` 一个镜头 × 6 张（不同 model_descriptor 微调）；
3. 客户挑一张作为新 model_ref_002；
4. 之后所有该 SKU 的 run 切到新 ref。

---

## 14. 与视频链路的衔接点

虽然本文档只覆盖图片链路，但要预留与视频链路的联通：

1. **图片可作为视频的首帧 / 关键帧 reference**：图片审核通过后，自动写一行到 `video_keyframe_pool` 表，视频链路（Seedance 2.0）调"图生视频"模式时直接拿这些图当 anchor；
2. **共用 style_template**：图片链路的 brand_palette / model_descriptor 直接灌进视频分镜 prompt，保证图、视频视觉语言一致；
3. **共用 candidates 表的 status 流**：审核状态字段对图、视频统一定义，前端审核台不区分；
4. **共用错误告警 & generation_runs**：视频链路的 run_type='video'，图片是 'image'，但表结构同一张。

---

## 15. 验证路径（YN-BRA-001）

1. 把客户给的 3 张参考图（正面、背面、面料特写）传到 `oss://.../refs/YN-BRA-001/`；
2. 在飞书多维表新增一行：SKU=YN-BRA-001, 卖点 = "透气网眼面料 / 前置拉链 / 高弹力支撑 / 速干"，style_template_id=1（运动内衣黑色基线模板）；
3. 飞书"提交"按钮触发 N8N webhook；
4. 等 4-5 分钟（11 个 prompt 并发 4，平均 6-8s/张，含 LLM 阶段约 30s）；
5. 飞书机器人推消息 "本批 11 张候选已就绪"；
6. 当场打开多维表，逐张点击通过 / 打回；过审的进 archive，被打回的可一键"基于反馈二次生成"（写一段中文反馈，由 LLM-C 调整对应 shot 的 prompt 后重跑该 shot）。

完整链路通常可在 5 分钟内返回第一批结果，并完成一轮审核与二次生成验证。

---

## 16. 上线前 checklist

| 项 | 责任方 | 状态 |
|---|---|---|
| Volcengine Ark 账号开通 + Seedream 4.0 接入 + 充值 ≥ ¥500 余额 | 客户 | 待确认 |
| 5dock NewAPI key 申请 + 充值 ≥ ¥200 余额 | 客户 | 待确认 |
| 阿里云 OSS bucket `yfn-content-factory` 创建 + RAM 子账号 + 签名规则 | 我方 | 待办 |
| PostgreSQL 实例（VPS 自建或阿里云 RDS）+ schemas 落库 | 我方 | 与 schemas agent 联动 |
| N8N 容器部署 + credentials 配置（5 套：Postgres、5dock、Ark、OSS、飞书）| 我方 | 待办 |
| 飞书多维表 app_id / table_id 准备 + 字段映射核对 | 客户 + 我方 | 待办 |
| 客户提供 YN-BRA-001 三张参考图 + 上传 OSS | 客户 | 待办 |
| style_templates 表初始化 1 行（运动内衣黑色基线）| 我方 | 待办 |
| 端到端联调 1 次 | 我方 | 待办 |

---

## 17. 后续可演进点

短期（首期交付内能做）：
- 提供"风格预设包"，例如"清爽极简（默认）"、"复古运动"、"街头潮流"，让客户在多维表下拉选，免去每次手填 style_template；
- 在 OSS 旁挂一个静态 web 预览页（按 SKU/run_id 索引），方便不会用多维表的角色直接看图；
- 飞书消息推送从纯文本升级到 interactive card，把"通过 / 打回"按钮直接做进卡片。

中期（保修期内可演进）：
- 接 IC-Light / Comfy-style 的本地光照重打模型，对场景图做"光照统一"后处理，进一步压色一致性；
- 把模特 face embedding 一致性体检从"过后告警"改成"生成前预筛"——先小图试出 4 张候选，体检通过再放大到 2048。

长期（视后续报价）：
- 多品类共用模特库（运动 / 瑜伽 / 户外女装系列）；
- 支持"客户先上传一张草图（手绘 / 拼贴），系统自动转成 prompt"的输入模式；
- 自动 A/B 出图：同一镜头自动出两版（保守 vs 激进），多维表对比挑选。

---

文档维护：本文档随 `n8n/image-workflow.json` 与 `prompts/image/*.md` 一起进入版本管理，任一处改动需同步更新。
