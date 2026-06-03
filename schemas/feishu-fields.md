# 飞书多维表字段规格

> AI 内容工厂 - 飞书侧字段标准
> 版本：v1.0  日期：2026-05-05
> 多维表 app_token：填入 `tenants.feishu_app_token`
> 时区：Asia/Shanghai

## 总览

| 表名 | 表英文名 | 主写入方 | 主读取方 |
|---|---|---|---|
| 产品输入表 | `tbl_products_input` | 客户 | N8N（拉取后写 `products`） |
| 任务进度表 | `tbl_tasks_progress` | N8N（写状态） | 客户（看进度） |
| 候选审核表 | `tbl_candidates_review` | N8N（写候选） | 客户（审核） |
| 归档表 | `tbl_archive` | N8N（最终入库） | 客户（验收交付） |

字段命名：`字段中文名` 直接作为飞书表头；`字段英文名` 作为 N8N 节点里 JSON 字段 key（飞书 OpenAPI 通过中文名读写，英文名仅作内部映射约定）。

---

## 1. 产品输入表 `tbl_products_input`

**用途**：客户填写产品资料，N8N 监听新增/修改后落库到 `products` 表。

| 字段中文名 | 字段英文名 | 飞书类型 | 必填 | 默认值 | 示例（YN-BRA-001） | 谁写谁读 |
|---|---|---|---|---|---|---|
| SKU 编码 | `sku` | 单行文本 | 是 | - | `YN-BRA-001` | 客户写 / N8N 读 |
| 产品名称 | `name` | 单行文本 | 是 | - | `黑色高弹速干运动内衣（前拉链款）` | 客户写 / N8N 读 |
| 类目 | `category` | 单选 | 是 | `运动内衣` | 选项：运动内衣 / 运动上衣 / 瑜伽裤 / 运动短裤 / 外套 | 客户写 / N8N 读 |
| 卖点 | `selling_points` | 多行文本 | 是 | - | `透气网眼面料；前置拉链穿脱方便；高弹力支撑；速干`（用换行或分号分隔） | 客户写 / N8N 读 |
| 目标受众 | `target_audience` | 单行文本 | 是 | - | `25-40 岁运动女性` | 客户写 / N8N 读 |
| 使用场景 | `use_scenarios` | 多选 | 是 | - | `瑜伽馆 / 跑步 / 健身房 / 户外`（多选项） | 客户写 / N8N 读 |
| 主色 | `primary_color` | 单行文本 | 是 | `黑色` | `黑色` | 客户写 / N8N 读 |
| 备选色 | `alt_colors` | 多选 | 否 | - | `深灰` | 客户写 / N8N 读 |
| 尺码 | `sizes` | 多选 | 是 | - | `S, M, L, XL` | 客户写 / N8N 读 |
| 参考图 | `reference_images` | 附件 | 是 | - | 上传 3 张：正面、背面、拉链特写 | 客户写 / N8N 读 |
| 风格模板 | `style_template_code` | 单选 | 是 | `YINI-SPORT-V1` | 选项绑定 `style_templates.code` | 客户写 / N8N 读 |
| 物理规格（JSON） | `spec_json` | 多行文本 | 否 | `{}` | `{"fabric":"聚酯纤维 88% 氨纶 12%","support_level":"中高强度"}` | 客户写 / N8N 读 |
| 单价（元） | `price_cny` | 数字 | 否 | - | `159` | 客户写 / N8N 读 |
| 创建人 | `created_by` | 单行文本 | 是 | 当前用户 | `飞飞` | 客户写 / N8N 读 |
| 提交时间 | `submitted_at` | 日期 | 是 | 当前时间 | `2026-05-05 14:30` | 客户写 / N8N 读 |
| 入库状态 | `ingest_status` | 单选 | 否 | `待入库` | 选项：待入库 / 已入库 / 入库失败 | N8N 写 / 客户读 |
| 入库回写时间 | `ingested_at` | 日期 | 否 | - | `2026-05-05 14:31` | N8N 写 / 客户读 |
| 入库错误信息 | `ingest_error` | 多行文本 | 否 | - | - | N8N 写 / 客户读 |
| 备注 | `remark` | 多行文本 | 否 | - | - | 客户写 / N8N 读 |

---

## 2. 任务进度表 `tbl_tasks_progress`

**用途**：N8N 创建任务后回写一行，状态机推进时持续更新；客户实时看进度。

| 字段中文名 | 字段英文名 | 飞书类型 | 必填 | 默认值 | 示例（YN-BRA-001 图片任务） | 谁写谁读 |
|---|---|---|---|---|---|---|
| 任务标题 | `title` | 单行文本 | 是 | - | `YN-BRA-001 首期图片打样：白底图 + 4 场景图` | N8N 写 / 客户读 |
| 任务 ID | `task_id` | 单行文本 | 是 | - | `55555555-5555-5555-5555-555555555501` | N8N 写 / 客户读 |
| 关联 SKU | `sku` | 单向关联 | 是 | - | 关联 `tbl_products_input` 的 SKU 行 | N8N 写 / 客户读 |
| 链路类型 | `pipeline` | 单选 | 是 | - | 选项：图片 / 视频 | N8N 写 / 客户读 |
| 状态 | `status` | 单选 | 是 | `pending` | 选项：pending / analyzing / prompting / generating / candidates_ready / reviewing / approved / rejected / regenerating / archived / delivered / failed_recoverable / failed_terminal | N8N 写 / 客户读 |
| 优先级 | `priority` | 单选 | 是 | `normal` | 选项：low / normal / high / urgent | 客户写 / N8N 读 |
| 期望候选数 | `requested_count` | 数字 | 是 | `4` | `8` | 客户/N8N 写 |
| 已产出候选数 | `candidates_total` | 数字 | 否 | `0` | `8` | N8N 写 / 客户读 |
| 通过候选数 | `candidates_approved` | 数字 | 否 | `0` | `5` | N8N 写 / 客户读 |
| 当前进度 | `progress_percent` | 数字 | 否 | `0` | `60`（百分比） | N8N 写 / 客户读 |
| 重试次数 | `retry_count` | 数字 | 否 | `0` | `0` | N8N 写 / 客户读 |
| 任务参数（JSON） | `parameters_json` | 多行文本 | 否 | `{}` | `{"resolution":"1024x1280","views":["front","back","detail"]}` | N8N 写 / 客户读 |
| 错误信息 | `error_message` | 多行文本 | 否 | - | - | N8N 写 / 客户读 |
| 总成本（元） | `total_cost_cny` | 数字 | 否 | `0` | `12.4` | N8N 写 / 客户读 |
| 创建人 | `created_by` | 单行文本 | 是 | - | `飞飞` | N8N 写 / 客户读 |
| 创建时间 | `created_at` | 日期 | 是 | 当前时间 | `2026-05-05 14:35` | N8N 写 / 客户读 |
| 开始时间 | `started_at` | 日期 | 否 | - | `2026-05-05 14:36` | N8N 写 / 客户读 |
| 完成时间 | `finished_at` | 日期 | 否 | - | - | N8N 写 / 客户读 |
| 候选审核入口 | `review_link` | 链接 | 否 | - | 指向 `tbl_candidates_review` 该任务的视图 URL | N8N 写 / 客户读 |
| 备注 | `remark` | 多行文本 | 否 | - | - | 客户写 / N8N 读 |

---

## 3. 候选审核表 `tbl_candidates_review`

**用途**：N8N 把每个候选物（图片/视频/分镜）写一行，客户审核。审核动作触发 N8N 写 `audit_log` 并推进任务状态。

| 字段中文名 | 字段英文名 | 飞书类型 | 必填 | 默认值 | 示例 | 谁写谁读 |
|---|---|---|---|---|---|---|
| 候选 ID | `candidate_id` | 单行文本 | 是 | - | `c-7f8e...01` | N8N 写 / 客户读 |
| 关联任务 | `task_id` | 单向关联 | 是 | - | 关联 `tbl_tasks_progress` | N8N 写 / 客户读 |
| 关联 SKU | `sku` | 单行文本 | 是 | - | `YN-BRA-001` | N8N 写 / 客户读 |
| 媒介类型 | `media_type` | 单选 | 是 | - | 选项：image / video / storyboard / script / srt | N8N 写 / 客户读 |
| 候选序号 | `sequence_no` | 数字 | 是 | `1` | `1`、`2`... | N8N 写 / 客户读 |
| 主图/视频 | `asset` | 附件 | 是 | - | 直接上传或贴 OSS URL（飞书附件） | N8N 写 / 客户读 |
| 缩略图 | `thumbnail` | 附件 | 否 | - | 缩略图（视频用） | N8N 写 / 客户读 |
| OSS URL | `oss_url` | 链接 | 是 | - | `https://oss.example.com/yini/.../001.jpg` | N8N 写 / 客户读 |
| 使用的 Prompt | `prompt_snapshot` | 多行文本 | 否 | - | 实际下发给模型的 prompt 全文 | N8N 写 / 客户读 |
| 参数快照（JSON） | `parameters_snapshot` | 多行文本 | 否 | `{}` | `{"model":"sd-xl-1.0","seed":12345,"cfg":7.5}` | N8N 写 / 客户读 |
| 模型 | `model_name` | 单行文本 | 否 | - | `sd-xl-1.0` / `seedance-2.0` | N8N 写 / 客户读 |
| 分辨率 | `resolution` | 单行文本 | 否 | - | `1024x1280` | N8N 写 / 客户读 |
| 时长（秒） | `duration_s` | 数字 | 否 | - | `12`（视频） | N8N 写 / 客户读 |
| 候选状态 | `status` | 单选 | 是 | `new` | 选项：new / in_review / approved / rejected / archived / discarded | N8N 写 / 客户读 |
| 审核动作 | `audit_action` | 单选 | 否 | - | 选项：通过 / 驳回 / 要求修改 / 仅评论 | 客户写 / N8N 读 |
| 审核人 | `reviewer` | 单行文本 | 否 | 当前用户 | `飞飞` | 客户写 / N8N 读 |
| 审核评分 | `score` | 数字 | 否 | - | `8.5`（0-10） | 客户写 / N8N 读 |
| 审核意见 | `audit_comment` | 多行文本 | 否 | - | `背景偏暗，需再亮一点；模特表情可更自信` | 客户写 / N8N 读 |
| 审核时间 | `audited_at` | 日期 | 否 | - | `2026-05-05 16:20` | 客户写 / N8N 读 |
| 生成时间 | `created_at` | 日期 | 是 | 当前时间 | `2026-05-05 14:50` | N8N 写 / 客户读 |
| 单次成本（元） | `cost_cny` | 数字 | 否 | - | `1.4` | N8N 写 / 客户读 |

**审核交互约定**：
- 客户在 `审核动作` 列选择"通过/驳回/要求修改"，N8N 通过飞书 webhook 监听单元格变更。
- 选"通过" → 写入 `audit_log` (action=approve)，候选 `status=approved`，触发归档判断。
- 选"驳回" → 写入 `audit_log` (action=reject)，候选 `status=rejected`，任务回 `regenerating` 状态走第二轮。
- 选"要求修改" → 写入 `audit_log` (action=request_revision)，候选 `status=rejected`，任务带客户意见进入新的 prompt 生成。

---

## 4. 归档表 `tbl_archive`

**用途**：审核通过的候选物最终入库登记，供客户验收和交付。

| 字段中文名 | 字段英文名 | 飞书类型 | 必填 | 默认值 | 示例 | 谁写谁读 |
|---|---|---|---|---|---|---|
| 归档 ID | `archive_id` | 单行文本 | 是 | - | `a-9d3e...01` | N8N 写 / 客户读 |
| 关联 SKU | `sku` | 单行文本 | 是 | - | `YN-BRA-001` | N8N 写 / 客户读 |
| 关联任务 | `task_id` | 单行文本 | 是 | - | `55555555-5555-5555-5555-555555555501` | N8N 写 / 客户读 |
| 关联候选 | `candidate_id` | 单行文本 | 是 | - | `c-7f8e...01` | N8N 写 / 客户读 |
| 媒介类型 | `media_type` | 单选 | 是 | - | 选项：image / video / storyboard / script / srt | N8N 写 / 客户读 |
| 最终成品 | `final_asset` | 附件 | 是 | - | 入库后的最终文件 | N8N 写 / 客户读 |
| 最终 OSS URL | `final_oss_url` | 链接 | 是 | - | `https://oss.example.com/archive/yini/YN-BRA-001/img-001.jpg` | N8N 写 / 客户读 |
| 交付路径 | `delivery_path` | 单行文本 | 否 | - | `/客户交付/YN-BRA-001/2026-05/` | N8N 写 / 客户读 |
| 是否已交付 | `is_delivered` | 单选 | 是 | `否` | 选项：是 / 否 | N8N 或 客户写 |
| 交付时间 | `delivered_at` | 日期 | 否 | - | `2026-05-06 10:00` | N8N 或 客户写 |
| 交付人 | `delivered_by` | 单行文本 | 否 | - | `飞飞` | N8N 或 客户写 |
| 客户验收 | `client_accepted` | 单选 | 否 | - | 选项：通过 / 不通过 / 待复核 | 客户写 / N8N 读 |
| 验收意见 | `acceptance_comment` | 多行文本 | 否 | - | `OK，可上架` | 客户写 / N8N 读 |
| 归档时间 | `archived_at` | 日期 | 是 | 当前时间 | `2026-05-05 17:00` | N8N 写 / 客户读 |
| 备注 | `remark` | 多行文本 | 否 | - | - | 双向 |

---

## 飞书侧建表注意事项

1. **创建顺序**：先建 `tbl_products_input` → 再建 `tbl_tasks_progress`（其 `sku` 单向关联指向产品输入表）→ 再建 `tbl_candidates_review`（其 `task_id` 单向关联指向任务进度表）→ 最后建 `tbl_archive`。
2. **单选选项**：所有 `状态/类型` 类字段在飞书界面"字段属性 → 选项"里逐项录入，名称必须与本文档一字不差，否则 N8N 写入会变"未知选项"。
3. **附件字段**：飞书附件存在 5 GB 单租户配额，视频候选优先用 `链接` 字段保留 OSS URL，附件字段只放缩略图。
4. **权限**：客户账号只给"产品输入表写、任务进度表读、候选审核表（仅审核相关 4 列）写、归档表（验收 2 列）写"权限，其余为 N8N Bot 写。
5. **视图**：每张表至少建 2 个视图——"全部" + "按 SKU 分组"。候选审核表额外建"我的待审核"（筛选 `status=new`）。
