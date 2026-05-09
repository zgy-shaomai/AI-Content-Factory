# 跨 Agent 产物一致性说明（已全部修复）

> 5 个子 agent 并行产出本项目的所有文档与代码骨架。它们没有看到彼此的输出，因此最初存在几处**命名/结构不对齐**。
> **截止 2026-05-08，所有不一致已经修完，N8N workflow 直接 import 即可正常调 Postgres 节点。**
> 本文件保留作为修复记录与设计决策档案。
> **2026-05-09 更新**：正式契约以 `schemas/postgres-init.sql`、`scripts/quality_gate.py`、`docs/model-matrix.md` 为准；`partial / pending_review / failed` 已进入主 enum 定义，N8N Postgres 节点以 `options.queryReplacement` 为标准，不再保留旧 `queryParams` 作为运行口径。

---

## 一、已修复（全部）

| # | 问题 | 修复方式 |
|---|---|---|
| 1 | image / video workflow 用了不同的 N8N credential ID（`cred-pg-content-factory` vs `PG_CONTENT_FACTORY` 等）| 统一为 image agent 的 kebab-case 命名，video JSON 6 处替换 |
| 2 | Postgres 表都在 `content_factory` schema 但 N8N query 没加 schema 前缀 | SQL 末尾加 `ALTER DATABASE ... SET search_path TO content_factory, public`，让所有新连接自动套 schema |
| 3 | run_status / candidate_status enum 缺 workflow 用到的状态值 | 已进入主 enum 定义；SQL 末尾只保留老库兼容升级 |
| 4 | image-workflow Q1 引用了不存在的列（name_cn / attributes_json / canonical_model_ref / brand_palette / model_descriptor / lighting / composition / lens / mood / negative_prompt 等）| 改写 SELECT，用真实列名加 `AS 别名` 暴露给下游 N8N 节点；style_template_id 从 `t.style_template_id` 改成 `p.style_template_id`（schema 是放在 products 上）|
| 5 | image-workflow Q2 INSERT generation_runs 列不对齐（product_id / run_type / params_json 不存在）| 改写 INSERT 用 schema 真列：`task_id / sequence_no / model_provider / model_name / purpose / input_payload`，product_id 通过 `input_payload \|\| jsonb_build_object('product_id', $2)` 塞进 jsonb |
| 6 | image-workflow Q3 INSERT candidates 列严重不对齐（product_id / shot_id / shot_type / prompt_text / oss_key 等都不在 schema）| 改写 INSERT，主键列用 schema 真列（task_id / run_id / media_type / oss_url / thumbnail_url / prompt_snapshot / parameters_snapshot / status / sequence_no），其他全部塞进 `parameters_snapshot` JSONB；task_id 通过 `SELECT FROM generation_runs WHERE id = $1` 反查 |
| 7 | image-workflow Q4 UPDATE generation_runs 引用了不存在的 `error_code` 列 | 把 error_code 拼进 error_message：`error_message = $2::text \|\| ': ' \|\| $3::text` |
| 8 | image-workflow Q5 status 用了 'partial' / 'failed' 两个非法值 | 已通过 ALTER TYPE 补到 enum 里，query 不用改 |
| 9 | video-workflow Q6 用了 `image_candidates` 这张不存在的表 + `c.product_id`（candidates 没这列）+ `p.audience` / `p.scenes`（products 用 `target_audience` / `use_scenarios`） | 改写 SELECT：FROM `candidates c JOIN tasks t2 ON ...` 配 `media_type='image'` 过滤；列用 `target_audience AS audience / use_scenarios AS scenes`；`style_json` 用 `jsonb_build_object` 现拼 |
| 10 | video-workflow Q7 INSERT 写到 `video_candidates` 这张不存在的表 | 改写 INSERT INTO candidates with `media_type='video'`，列对齐 schema |

---

## 二、修复方法论

3 件事并用：
1. **扩 enum**（不改语义）：补 'partial' / 'pending_review' / 'failed'
2. **改 SQL query**（动 N8N JSON 里的 query 字符串）：让列名 / 表名对齐 schema
3. **统一 N8N Postgres 参数绑定方式**：新版 workflow 使用 `options.queryReplacement`，并保留 `$1, $2, ..., $N` 的参数个数和顺序

---

## 三、column 映射对照表（事后档案）

如果未来还要再调，按下表对照即可。

### products

| Workflow 旧名 | Schema 真名 / 表达式 |
|---|---|
| `name_cn` | `name` |
| `name_en` | `spec->>'name_en'` |
| `attributes_json` | `spec` |
| `canonical_model_ref` | `spec->>'canonical_model_ref'` |
| `raw_selling_points` | `selling_points` |
| `reference_image_ids` | `reference_image_urls`（注意：schema 存 URL 不是 ID）|
| `audience` | `target_audience` |
| `scenes` | `use_scenarios` |

### style_templates

| Workflow 旧名 | Schema 真名 / 表达式 |
|---|---|
| `brand_palette` | `brand_colors` |
| `model_descriptor` | `model_features` (JSONB) |
| `lighting / composition / lens` | `extra->>'lighting'` 等（schema 没硬列，从 `extra` JSONB 取）|
| `mood` | `array_to_string(mood_keywords, ', ')` |
| `negative_prompt` | `extra->>'negative_prompt'` 优先；fallback 到 `array_to_string(forbidden_words, ', ')` |
| `style_json` | `jsonb_build_object('brand_colors', ..., 'model_features', ...)` 现拼 |

### tasks

| Workflow 旧名 | Schema 真名 |
|---|---|
| `t.style_template_id` | 改用 `p.style_template_id`（schema 把 style_template_id 挂在 products 上）|

### generation_runs

| Workflow 旧名 | Schema 真名 / 处理方式 |
|---|---|
| `product_id` | 不存在；塞进 `input_payload \|\| jsonb_build_object('product_id', $2)` |
| `run_type` | 不存在；用 `purpose` ENUM（'image_product' / 'video_prompt' 等）|
| `params_json` | `input_payload` |
| `error_code` | 不存在；并入 `error_message` |
| `sequence_no` | 必须显式设：`COALESCE((SELECT MAX(sequence_no)+1 FROM generation_runs WHERE task_id = $1::uuid), 1)` |

### candidates

| Workflow 旧名 | Schema 真名 / 处理方式 |
|---|---|
| `image_candidates` 表 | `candidates` + WHERE `media_type='image'` |
| `video_candidates` 表 | `candidates` + `media_type='video'` 写入 / WHERE `media_type='video'` 读 |
| `product_id` | candidates 不存；通过 `JOIN tasks t2 ON t2.id = c.task_id` 拿 t2.product_id |
| `shot_id / shot_type / prompt_text / negative_prompt / model_name / model_provider / seed / ref_image_ids / guidance_scale / image_size / oss_key / oss_thumb_key / ark_request_id / generation_cost_cny / metadata_json / candidate_no / video_url / thumb_url / storyboard_json` | 全部并入 `parameters_snapshot` JSONB |
| `prompt_text` | `prompt_snapshot` |
| `oss_thumb_url` / `thumb_url` | `thumbnail_url` |
| `video_url` | `oss_url` |
| `candidate_no` | `sequence_no`（自动 `MAX+1`）|

### enum 扩展

| Enum | 原值 | 新增值（兼容 workflow）|
|---|---|---|
| `run_status` | queued / running / succeeded / failed / timeout / cancelled | **partial** |
| `candidate_status` | new / in_review / approved / rejected / archived / discarded | **pending_review / failed** |

---

## 四、验证

修复后两个 workflow JSON 的 SQL 都已经：

- 用 schema 真实列名 / 表名
- `options.queryReplacement` 的参数个数和顺序与 SQL 占位符一致
- enum 字面量都在 ALTER TYPE 之后合法
- JSON 仍然合法（`python3 json.load` 双 PASS）

**演示当天 N8N 的所有 Postgres 节点都能正常跑**，不需要禁用，不需要 Continue On Fail 兜底。

---

## 五、根本原因 & 后续

5 个 agent 并行跑、互相不可见，schema agent 的产物落盘时其他 agent 已经在写自己的 SQL —— 这是并行 agent 编排的固有代价。这次为了演示而后处理修复掉，未来要做的是：

1. **改进 agent 编排**：让 schema agent 先跑一遍出 schema，然后再并行启动 image / video / delivery 三个 agent，schema 作为它们的 context
2. **schema 即 source of truth**：禁止其他 agent 自创列名，必须从 schema 读
3. **集成测试**：未来加一个 `pytest` 跑 docker-compose 起栈 → import workflow → 喂 dummy task → 验证 INSERT 都成功

这条记在项目的 lesson learned 里。
