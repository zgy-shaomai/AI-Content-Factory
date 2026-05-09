# 归档结构设计（Archive Structure）

> 项目：服装电商 AI 内容工厂
> 媒体存储：阿里云 OSS
> 元数据：PostgreSQL 16 · 表 `archive`
> 文档版本：v1.0 · 2026-05-05
> 样品 SKU：YN-BRA-001（黑色高弹速干运动内衣 / 前拉链款）

---

## 1. 设计目标

1. **路径自解释**：从 OSS Key 一眼看出"哪个客户的 哪个产品的 哪一次任务的 哪一个候选"。
2. **冷热分层**：候选物（生命周期短）与交付物（生命周期长）分路径管理，便于配置 OSS 生命周期。
3. **多租户隔离**：未来接其他客户时按 `tenant` 隔离，权限和容量独立。
4. **与 Postgres 一一映射**：OSS Key 与 `archive` 表行一一对应，互为索引。
5. **交付包可重建**：客户最终拿到的 zip 必须能从 OSS 一键重打，不依赖本地任何状态。

---

## 2. Bucket 命名规范

每个客户在阿里云 OSS 上申请 **3 个 Bucket**，按用途分离，便于配置不同的访问权限与生命周期：

| Bucket 名 | 用途 | 访问权限 | 区域 |
|---|---|---|---|
| `yn-content-raw-cn-hz` | 客户提供的原始资料（产品图、参考图、对标视频） | 私有 | 华东 1（杭州） |
| `yn-content-work-cn-hz` | AI 生成候选物、过程图、缩略图 | 私有（仅 N8N + 飞书读） | 华东 1 |
| `yn-content-deliver-cn-hz` | 通过审核的最终交付物、客户交付包 zip | 私有 + 签名直链 | 华东 1 |

命名规则：`{tenant}-content-{purpose}-cn-{region}`
- `tenant`：客户简称小写（首期客户 = `yn`，意为 "YourName"，演示用占位）
- `purpose`：`raw` / `work` / `deliver`
- 区域后缀：`cn-hz`（华东 1 杭州）/ `cn-sh`（华东 2 上海）等

**禁止**把三类内容混到同一 Bucket。原因：生命周期策略不同、权限不同、误删风险隔离。

---

## 3. 路径规范

### 3.1 总体格式

```
oss://{bucket}/{tenant}/{sku}/{task_id}/{run_id}/{variant}/{candidate_n}.{ext}
```

| 段 | 说明 | 示例 |
|---|---|---|
| `bucket` | 见 §2 | `yn-content-work-cn-hz` |
| `tenant` | 客户简称 | `yn` |
| `sku` | 产品 SKU（与产品库一致） | `YN-BRA-001` |
| `task_id` | 任务 ID（N8N 自增 + 时间戳） | `T-20260505-2014` |
| `run_id` | 同一任务的第几轮（regenerate 会递增） | `R1` / `R2` / `R3` |
| `variant` | 媒体类型 / 用途（详见 §3.2） | `image` / `video` / `thumb` |
| `candidate_n` | 同一轮的第几张候选 | `c1` / `c2` / `c3` / `c4` |
| `ext` | 扩展名 | `png` / `jpg` / `mp4` / `srt` |

**完整示例（样品 YN-BRA-001 第 1 轮第 2 张候选图）**：

```
oss://yn-content-work-cn-hz/yn/YN-BRA-001/T-20260505-2014/R1/image/c2.png
```

### 3.2 三套路径：缩略图 / 原图 / 交付图

同一张候选物在 OSS 中存在最多三个副本，分别面向不同消费者：

| 用途 | Bucket | 路径 variant 段 | 规格 | 谁在用 |
|---|---|---|---|---|
| **缩略图** | `yn-content-work-cn-hz` | `thumb` | 长边 512px、JPG q=80 | 飞书多维表预览（带宽友好） |
| **原图** | `yn-content-work-cn-hz` | `image` / `video` | 原始分辨率 PNG / MP4 | 审核员点开看大图、二次生成参考 |
| **交付图** | `yn-content-deliver-cn-hz` | `delivered` | 原始分辨率 + 元数据 sidecar | 通过审核后复制过来，给客户最终交付 |

**对照表**：

```
缩略图：
  oss://yn-content-work-cn-hz/yn/YN-BRA-001/T-20260505-2014/R1/thumb/c2.jpg

原图：
  oss://yn-content-work-cn-hz/yn/YN-BRA-001/T-20260505-2014/R1/image/c2.png

交付图（仅审核通过后存在）：
  oss://yn-content-deliver-cn-hz/yn/YN-BRA-001/_delivered/T-20260505-2014_R1_c2.png
  oss://yn-content-deliver-cn-hz/yn/YN-BRA-001/_delivered/T-20260505-2014_R1_c2.json   # 元数据
```

交付路径**扁平化**（不再嵌套 task_id / run_id 子目录），直接放在 `{sku}/_delivered/` 下，文件名带原 task/run 信息。这样打交付包时只需扫一个目录。

### 3.3 视频链路的额外路径

视频任务一个候选会产生多个文件，按子目录组织：

```
oss://yn-content-work-cn-hz/yn/YN-BRA-001/T-20260505-2020/R1/video/c1/
  ├── raw.mp4              # Seedance 原始输出（含原生音频）
  ├── audio.wav            # ASR 抽音
  ├── subtitle.srt         # ASR 转写字幕
  ├── final.mp4            # 字幕叠加后的成片（最终用此版本）
  └── poster.jpg           # 封面帧（飞书多维表显示）
```

交付时只复制 `final.mp4` 到 deliver bucket。

### 3.4 客户原始资料路径

客户在飞书提交的产品图、参考图、对标视频统一进 raw bucket：

```
oss://yn-content-raw-cn-hz/yn/YN-BRA-001/inputs/
  ├── product/             # 产品本体图（白底图、细节图）
  ├── reference/           # 风格参考图
  ├── benchmark/           # 对标视频
  └── doc/                 # 产品资料 PDF / 卖点 markdown
```

---

## 4. 客户最终交付包

### 4.1 打包路径

```
oss://yn-content-deliver-cn-hz/yn/YN-BRA-001/_packages/{package_id}.zip
```

`package_id` 命名：`{sku}-{yyyyMMdd}-{seq}`，例如 `YN-BRA-001-20260520-001.zip`。

### 4.2 包内目录结构

```
YN-BRA-001-20260520-001.zip
├── README.txt                       # 本包说明（生成时间、SKU、含件数）
├── manifest.json                    # 机器可读清单（每个文件 → 原 task/run 信息）
├── images/                          # 通过审核的图片（按 task 拆子目录）
│   ├── T-20260505-2014_R1_c2.png
│   ├── T-20260506-2032_R2_c1.png
│   └── ...
├── videos/
│   ├── T-20260507-2055_R1_c3.mp4
│   └── ...
├── prompts/                         # 每个交付物对应的最终 prompt（便于客户复用）
│   ├── T-20260505-2014_R1_c2.txt
│   └── ...
└── meta/
    └── audit_log.csv                # 审核记录（谁审的、什么时候审的、轮次）
```

### 4.3 打包触发

- 审核负责人在飞书多维表 → "已交付"视图右上角点 `打交付包` 按钮。
- 弹窗选 SKU + 时间区间。
- 触发 `webhook/delivery/build`，N8N 在工作目录 `/data/n8n/tmp/pkg/` 拉所有文件、写 manifest、zip、上传到 OSS、生成 7 天有效签名 URL，回写到飞书行。
- 客户拿签名 URL 直接下载，不需要 OSS 账号。

---

## 5. OSS 生命周期策略

按 Bucket 配置如下生命周期规则（在 OSS 控制台 → 生命周期管理）：

### 5.1 `yn-content-work-cn-hz`（候选物）

| 前缀 | 规则 | 说明 |
|---|---|---|
| `*/thumb/` | 30 天后转低频访问，60 天后归档 | 缩略图带宽小，但访问量大 |
| `*/image/` `*/video/` | 30 天后删除 **未通过审核** 的候选 | 已通过的会被复制到 deliver bucket，原候选可删 |

实现方式：N8N 在审核状态变"通过"时给原 OSS Object 打 tag `keep=true`；生命周期规则按"无 keep tag 的 30 天后删除"。

### 5.2 `yn-content-deliver-cn-hz`（交付物）

| 前缀 | 规则 |
|---|---|
| `*/_delivered/` | **保留 1 年**，1 年后转归档存储（成本降至 1/3），3 年后删除 |
| `*/_packages/` | 保留 1 年，签名 URL 7 天过期 |

### 5.3 `yn-content-raw-cn-hz`（原始资料）

| 前缀 | 规则 |
|---|---|
| `*/inputs/` | **永久保留**（不配置自动删除） |

理由：原始资料是产品资产，删除后不可重建；生命周期不主动动它，由客户在合同结束后手工处理。

### 5.4 跨区域复制

不开启。客户首期单区域部署，跨区灾备等下一期再加。

---

## 6. 与 Postgres `archive` 表的对应关系

### 6.1 表结构

```sql
CREATE TABLE archive (
  id              BIGSERIAL PRIMARY KEY,
  tenant          TEXT NOT NULL,
  sku             TEXT NOT NULL,
  task_id         TEXT NOT NULL,
  run_id          TEXT NOT NULL,                  -- R1 / R2 / R3
  candidate_n     INT  NOT NULL,                  -- 1..N
  variant         TEXT NOT NULL,                  -- image / video / thumb / final
  oss_bucket      TEXT NOT NULL,
  oss_key         TEXT NOT NULL,                  -- bucket 后的完整 key
  ext             TEXT NOT NULL,
  size_bytes      BIGINT,
  width           INT,
  height          INT,
  duration_ms     INT,                            -- 视频用
  prompt_text     TEXT,                           -- 当时的 prompt
  prompt_version  INT,
  audit_status    TEXT NOT NULL,                  -- pending / approved / rejected / superseded / delivered
  audit_by        TEXT,
  audit_at        TIMESTAMPTZ,
  delivered_key   TEXT,                           -- 交付路径（approved 后写入）
  package_id      TEXT,                           -- 所属交付包（打包后写入）
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  meta            JSONB                           -- 模型、参数、其他扩展
);

CREATE INDEX idx_archive_sku_task ON archive(sku, task_id);
CREATE INDEX idx_archive_status ON archive(audit_status);
CREATE INDEX idx_archive_package ON archive(package_id);
CREATE UNIQUE INDEX uq_archive_oss ON archive(oss_bucket, oss_key);
```

### 6.2 一致性规则

- **OSS 是事实源（content）+ Postgres 是事实源（metadata）**。N8N 写流程：先 PUT OSS → 成功后 INSERT archive → 失败回滚（删 OSS Object）。
- **审核状态以 Postgres 为准**。飞书多维表的状态字段是镜像，不允许人工绕过 N8N 直接修改 Postgres。
- **删除策略**：候选过期由 OSS 生命周期物理删除，N8N 每天凌晨跑对账任务，把 OSS 上不存在的 Key 在 archive 表里标记 `purged=true`，不真删行（保留审计）。

### 6.3 路径与表的双向查询

正向（已知 task → 找文件）：
```sql
SELECT oss_bucket, oss_key, audit_status
FROM archive
WHERE sku = 'YN-BRA-001' AND task_id = 'T-20260505-2014'
ORDER BY run_id, candidate_n;
```

反向（已知 OSS Key → 找元数据）：
```sql
SELECT *
FROM archive
WHERE oss_bucket = 'yn-content-work-cn-hz'
  AND oss_key = 'yn/YN-BRA-001/T-20260505-2014/R1/image/c2.png';
```

---

## 7. 演示中的归档讲解动线

今天下午演示"归档 / 多产品复用讲解（16-20 分钟）"环节的操作：

1. 打开 OSS 控制台 work bucket，路径走到 `yn/YN-BRA-001/T-.../R1/image/`，让客户看到 4 张候选图与缩略图分离。
2. 切到 deliver bucket 的 `_delivered/` 目录，展示通过审核后的交付路径。
3. 打开 Postgres 客户端（DBeaver / TablePlus），执行 §6.3 查询，演示"OSS 路径 ↔ DB 行"双向可查。
4. 在飞书多维表点 `打交付包` 按钮（或演示已生成的交付 zip 直链）。
5. 强调："换一个新 SKU `YN-LEG-002`，所有路径模板原封照搬，不需要改一行代码。" 这就是模板复用。
