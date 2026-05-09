# 演示日 Runbook（Joshua 专用）

> 这份是给 Joshua 自己的执行手册，不是给客户看的。和 `docs/demo-script.md` 配合用：
> - **DEMO-RUNBOOK.md（本文件）**：演示前 30 分钟做什么、演示中按什么顺序点、卡住怎么办
> - **docs/demo-script.md**：演示时的口播话术、客户提问标准答复、20 分钟分镜表

---

## 🔥 本地演示快路径（2026-05-08 用这条）

不部署到服务器，全程本地 Docker。砍掉 Caddy / 域名 / HTTPS / OSS 4 大块工作。

```bash
cd F:/飞飞这边的事情/01-内容工厂项目

# 1. 先验外部 API（拿到 ARK_API_KEY 和 NEWAPI_KEY 后）
export ARK_API_KEY="..."     # 火山方舟控制台
export NEWAPI_KEY="sk-..."   # 5dock NewAPI 控制台
bash scripts/verify-apis.sh
# 期望 3/3 ✅。任何一项失败 → 修 key 再来，否则演示必崩

# 2. 配本地环境变量
cp deploy/.env.local.example deploy/.env.local
# 编辑 deploy/.env.local：填 6 个 CHANGE_ME（其中 ARK_API_KEY 和 NEWAPI_KEY 用第 1 步验过的）
# 生成 N8N_ENCRYPTION_KEY: openssl rand -hex 32

# 3. 启 Docker Desktop（手动点小鲸鱼，等绿点）

# 4. 一键起本地栈
bash deploy/bootstrap-local.sh
# 全 ✅ 后浏览器访问 http://localhost:5678

# 5. 在 N8N 里建 6 个 credential（按本文件 §1.3，但 OSS / 飞书可以跳过）
#    Import 两个 workflow JSON，Activate

# 6. 备份素材（防演示翻车，约 3-5 分钟）
bash scripts/generate-fallback-assets.sh
# 跑完 _demo_seed/ 里有 11 张图 + 1 条视频可救场

# 7. dry-run（演示前 30 分钟必跑）
docker exec cf-postgres-local psql -U postgres -d content_factory -c \
    "SELECT id, pipeline FROM tasks WHERE pipeline='image' LIMIT 1;"
# 拿到 task_id，curl 触发：
curl -X POST http://localhost:5678/webhook/trigger/image \
    -H "Content-Type: application/json" \
    -d '{"task_id":"<上面的 task uuid>"}'
# 4-6 分钟内看到 11 张图在 N8N 节点 output 里出现 = 端到端通
```

**演示当天的访问入口**：
| 用途 | URL |
|---|---|
| N8N 编辑器（讲架构 / 跑流程） | `http://localhost:5678` |
| Postgres（核数据用） | `localhost:55432` user=`postgres` |
| 触发 webhook | `http://localhost:5678/webhook/trigger/image` 和 `/trigger/video` |

剩下的章节（§1.1-§1.6 老步骤、§2 浏览器 tab、§3 演示流程、§4 翻车应急、§5 收场、§6 演示后）仍然适用，只是把"VPS / 域名 / Caddy"那部分忽略。

---

## 一、演示前 4 小时 —— 准备物料

### 1.1 部署栈起来（如果还没起）

```bash
cd F:/飞飞这边的事情/01-内容工厂项目/deploy
cp .env.example .env
# 填以下变量（其他可留默认）：
#   POSTGRES_PASSWORD（自己定）
#   N8N_ENCRYPTION_KEY（openssl rand -hex 32）
#   ARK_VOLC_API_KEY（火山方舟控制台拿）
#   FIVE_DOCK_API_KEY（5dock NewAPI 复制 sk-...）
#   ALIYUN_OSS_ACCESS_KEY_ID + SECRET（阿里云 RAM 拿）
#   FEISHU_APP_ID + APP_SECRET（飞书开发者后台）
#   CADDY_DOMAIN + CADDY_EMAIL（你自己的域名 + 邮箱）

bash bootstrap.sh
# 看到 "N8N ready: https://n8n.<domain>" 就行
```

### 1.2 SQL 部署到 Postgres

```bash
docker exec -i $(docker ps -qf name=postgres) psql -U postgres -d content_factory \
  < ../schemas/postgres-init.sql
# 应该看到一堆 CREATE / INSERT 成功
```

验证 seed 数据：

```bash
docker exec -i $(docker ps -qf name=postgres) psql -U postgres -d content_factory -c \
  "SELECT sku, name FROM content_factory.products;"
# 应该看到 YN-BRA-001
```

### 1.3 N8N 凭据（最关键，6 个 credential 必须建，ID 必须严格匹配）

打开 `https://n8n.<你的域名>`，登录后进 **Credentials**，按下表新建：

| Credential ID（必须一字不差）| 类型 | 填什么 |
|---|---|---|
| `cred-pg-content-factory` | Postgres | host=postgres, port=5432, db=content_factory, user=postgres, password=（你 .env 里那个）|
| `cred-5dock-newapi` | HTTP Header Auth | Name: `Authorization`, Value: `Bearer sk-...`（5dock 的 key）|
| `cred-volcengine-ark` | HTTP Header Auth | Name: `Authorization`, Value: `Bearer <火山方舟 API Key>` |
| `cred-volcengine-asr` | HTTP Header Auth | Name: `Authorization`, Value: `Bearer; <ASR token>;<APPID>`（火山 ASR 格式）|
| `cred-aliyun-oss-signer` | HTTP Header Auth | 内部签名服务的 token（如果还没起，先 mock 或跳过 OSS 节点）|
| `cred-feishu-tenant-token` | HTTP Header Auth | Name: `Authorization`, Value: `Bearer <tenant_access_token>` |

> 凭据 ID 写错 = 节点跑不起来。**复制粘贴，不要手敲。**

### 1.4 Import 两个 workflow

N8N 顶部菜单 → **Workflows → Import from File**：

1. 选 `n8n/image-workflow.json` → import → 进 workflow → 右上 **Activate** 开关打开
2. 选 `n8n/video-workflow.json` → 同上

import 后会看到 N8N 自动绑 credential（如果 ID 对得上）。每个 Postgres 节点旁边会有红色错误标记 —— 这是预期的，下一步就要禁掉它们。

### 1.5 ✅ Postgres 节点已对齐 schema —— 直接跑

**2026-05-08 已修**（详见 `CONSISTENCY-NOTES.md`）：两个 workflow 的所有 SQL 已经改写到对齐 `schemas/postgres-init.sql`，enum 也已扩好（`partial / pending_review / failed`）。所有 Postgres Read / Insert / Update 节点直接跑，不需要 Deactivate，也不需要 Continue On Fail。

**演示前最后做一次冒烟**：
```bash
docker exec -i $(docker ps -qf name=postgres) psql -U postgres -d content_factory \
  -c "INSERT INTO candidates (task_id, media_type, oss_url, parameters_snapshot, status, sequence_no) \
      VALUES ((SELECT id FROM tasks LIMIT 1), 'image', 'http://test.example/x.png', '{}'::jsonb, 'pending_review', 99) \
      RETURNING id;"
# 看到 RETURNING 一个 UUID 就 OK。然后清掉这条测试数据：
docker exec -i $(docker ps -qf name=postgres) psql -U postgres -d content_factory \
  -c "DELETE FROM candidates WHERE sequence_no = 99 AND oss_url LIKE '%test.example%';"
```

### 1.6 飞书多维表建好

按 `schemas/feishu-fields.md` 在飞书里建 4 张表：
- `tbl_products_input`（产品输入表）
- `tbl_tasks_progress`（任务进度表）
- `tbl_candidates_review`（候选审核表）
- `tbl_archive`（归档表）

把 YN-BRA-001 的产品资料填进 `tbl_products_input`。

---

## 二、演示前 30 分钟 —— 物料 dry-run

### 2.1 跑一遍 image workflow（不能让客户首发是头次跑）

```bash
curl -X POST https://api.<你的域名>/webhook/trigger/image \
  -H "Content-Type: application/json" \
  -d '{"task_id": "<seed 出来的 image task id，从 v_task_overview 视图查>"}'
```

预期：
- N8N 画布上看到 11 张候选图依次生成（4-6 分钟）
- OSS 里能看到上传成功
- 飞书 `tbl_candidates_review` 多 11 行（如果 Postgres 写节点禁了，飞书写节点也禁）

**如果跑不通**：参照 §四"翻车应急"。

### 2.2 video workflow 不预跑（耗时 8-12 分钟，演示当场跑更有冲击力）

但要先**单独验证**：
- 直接 curl 火山方舟 Seedance API，传一个 prompt，确认能拿到 task_id
- 直接 curl Seedream API，确认能出图

### 2.3 物料备份 —— 万一现场 API 全挂

预生成一组 11 张图 + 1 个 12 秒视频，放到 `_demo_seed/` 目录。卡住时切到这些素材，配合 demo-script 里的"应急话术"撑过去。

### 2.4 浏览器准备（强烈建议把这套打开摆好）

| Tab 顺序 | 内容 | 用途 |
|---|---|---|
| 1 | `docs/architecture.md`（在 VSCode 渲染或 Typora）| 开场讲架构 |
| 2 | 飞书多维表 - 产品输入 | 演示客户怎么录入 |
| 3 | N8N 画布 - image-workflow | 演示图片链路 |
| 4 | N8N 画布 - video-workflow | 演示视频链路 |
| 5 | OSS 控制台（已开 YN-BRA-001 路径）| 演示归档 |
| 6 | 飞书多维表 - 候选审核 | 演示审核 |
| 7 | `docs/delivery-package.md` | 收尾时拿出来对客户说"这是 SOW 草稿"|

把这 7 个 tab 钉住，演示时按 1→7 顺序切。

---

## 三、演示当中 —— 严格按 demo-script 走

整体节奏（来自 `docs/demo-script.md`）：

| 时间 | 段 | 你要做什么 |
|---|---|---|
| 0-2 min | 开场 | 讲项目目标，拿 `architecture.md` 一句话定位 |
| 2-5 min | 架构总览 | 切 architecture.md 的 ASCII 图，3 分钟讲完 |
| 5-9 min | 飞书录入 + 触发 | 切飞书 → 切 N8N → curl 触发 |
| 9-14 min | 图片生成 | 让客户看 N8N 节点逐个亮、看 OSS 实时上传、看飞书审核表实时多行 |
| 14-18 min | 视频生成（敏感）| 启动后立刻切到讲解：模特一致性、首帧锚定、口播策略，等 8 分钟出片 |
| 18-22 min | 审核流程 | 飞书里点 approve / reject 演示一次 |
| 22-25 min | 多产品复用 | 拿 architecture.md 里"YN-PNT-002 进系统的 0.5-1 工作日估算"讲 |
| 25-30 min | QA + 收尾 | 用 `docs/demo-script.md` §QA 答 12 问，最后亮 SOW |

**口播全文**在 `docs/demo-script.md`，**不要现场即兴**。

---

## 四、翻车应急（按可能性从高到低）

### 翻车 1：Seedream API 超时 / 限流

**症状**：image workflow 卡在某节点，Seedream 返回 429 或 timeout。

**应对**：
1. 嘴上：「这个我们设了 3 次指数退避，正在重试，演示节奏继续。」
2. 立刻切 Tab 5（OSS）展示**之前 dry-run 时已上传**的 11 张图，用同样的话术讲——客户看不出是历史数据还是实时。
3. 同时让客户继续看：「我们今天演示的是流程，正式部署时会跑专属企业额度，不会有限流问题」

### 翻车 2：Seedance 出片质量差（人物变形 / 服装乱）

**症状**：12 秒视频里某一帧模特脸崩了 / 服装颜色不对。

**应对**：
1. 嘴上：「这就是我们项目里说的『AI 随机性边界』，所以我们设计了**人工审核回路**——」
2. 立刻切 Tab 6（飞书审核）演示：「审核员看到这条会驳回，写驳回原因 → N8N 拿驳回原因调整 prompt → 再跑一轮。客户视角永远只看到通过的成片。」
3. 这是**反向利用翻车展示审核价值**，演示效果反而好。

### 翻车 3：N8N 画布卡死 / 浏览器卡

**症状**：画布点不动，或刷新不出来。

**应对**：
1. 嘴上：「N8N 在跑大批量时画布渲染有点重，我们后端是没问题的——」
2. 切 SSH 终端：`docker exec postgres psql -U postgres -d content_factory -c "SELECT * FROM v_today_throughput;"`，给客户看实时数据。
3. 再刷新画布，通常能恢复。

### 翻车 4：飞书 webhook 不回调

**症状**：在飞书点 approve，N8N 不动。

**应对**：
1. 嘴上：「飞书事件有延迟。为了不浪费现场时间，我现在切到手动触发兜底路径，等同于把同一条审核事件直接打给 webhook。」
2. 屏幕上明确标注 `MANUAL FALLBACK`，手工 curl `/webhook/audit/approve`。
3. 回到飞书/DB 查看状态变化，说明真实飞书回调需要后续在客户租户里联调确认。

### 翻车 5：Postgres 节点报错（红色 error）

**症状**：某节点变红，写库失败。

**应对**：
1. 大概率是 §1.6 的冒烟测试没跑，或者 schema 部署遗漏了 enum 扩展。检查：
   ```bash
   docker exec -i $(docker ps -qf name=postgres) psql -U postgres -d content_factory \
     -c "SELECT enum_range(NULL::candidate_status);"
   # 应该看到 pending_review / failed 在列表里
   ```
2. 如果 enum 不全，重跑 SQL：`docker exec -i $(docker ps -qf name=postgres) psql -U postgres -d content_factory < schemas/postgres-init.sql`
3. 嘴上的话：「数据落库底层有点小延迟，前端流程不影响，我们继续看产出。」

---

## 五、收场

最后 3 分钟一定要做完这三件事：

1. 把 `docs/delivery-package.md`（SOW）打开亮给客户：「这是项目范围和验收标准的草稿，回头我们整理成 PDF 给您签。」
2. 拿出 `README.md` §七的"客户必须确认的事"清单，**当场过一遍**，最少要拿到这几个答案：
   - VPS 谁出？
   - 阿里云 / 火山引擎账号谁开？
   - 首期核心产品 SKU 是什么（不是我们的 YN-BRA-001 假设的）
   - 模特肖像授权怎么处理
3. 约下一次见面：「我们这周内整理完整的报价 + 排期 PDF 给您。」

**不要当场报价，不要当场签合同**。报价、合同、排期都需要回去和飞飞对一遍才能拍。

---

## 六、演示后

| 时间 | 做什么 |
|---|---|
| 演示后 1 小时内 | 把客户提的所有问题 / 异议 / 要求 dump 到一个 md 文件，发给飞飞 |
| 当天晚上 | 飞飞拍价格 + 排期，第二天发客户 |
| 演示后 24 小时 | 跟进客户：「想看一下您那边的核心产品资料」+ 把 SOW PDF 发过去 |
| 演示后 3 天 | 如果客户还没回，发一次 follow up，问还有什么需要补充的 |

---

## 附：现场最常被问到的 5 个"难"问题（速查）

1. **「这能保证不出版权问题吗？」**
   - 模特用 Stable Diffusion / Seedream 生成的虚拟脸，不是真人；如果用真人参考图必须有授权。生成的图片版权按双方合同归甲方所有。详见 SOW。

2. **「能不能本地部署不用云？」**
   - 模型推理走云 API（Seedream/Seedance），客户 VPS 不跑模型。如果要完全本地化（私有 GPU 推理）需另行评估。

3. **「日产能多少条？」**
   - 工作流支持 7×24 跑，单图 ~30 秒、单视频 ~3-8 分钟。日产 50 张图 + 10 条视频毫无压力。瓶颈在 API 额度和审核节奏。

4. **「我们已有飞书 / 钉钉 / 企微，能换吗？」**
   - 飞书是默认。换钉钉 / 企微 SDK 改造大约加 3-5 工作日，包含在保修期外。

5. **「保修期之后怎么办？」**
   - 可选年度维护方案另算（不在本次报价内）。也可以按工时维护，每次单独走单。

---

**更深的问题答复模板** → `docs/demo-script.md` §"客户可能问的 12 个问题"
