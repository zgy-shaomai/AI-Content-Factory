# 内容工厂项目（服装电商版）

> 客户：服装电商（运动内衣 / 运动服 / 瑜伽裤）
> 工期：20-30 个工作日
> 目标：搭建可复用的图片链路 + 视频链路内容生产系统，单产品打样后可复用到多产品
> 验收口径：以 `docs/acceptance-rubric.md` 的评分表为准，不再使用不可量化的“同样或更高”单句口径。

---

## 一、这个项目在做什么

把客户日常**做电商上新内容**这件事，从"美工 + 摄影 + 剪辑师 1 周出 1 个 SKU"变成"录入产品资料 → 系统自动出图 + 出视频 → 人工审核 → 归档交付"。

整个系统跑在客户自己的 VPS 上，**客户老板能在 N8N 画布看到每一步流程**，**审核员只需要在飞书多维表里打勾驳回**，**新 SKU 上来时只录一份资料**就能跑完整条链路。

---

## 二、技术栈一览

| 层 | 选型 | 备注 |
|---|---|---|
| 工作流引擎 | N8N（自托管 docker） | 老板看节点 / 员工看封装 |
| 图片生成 | Seedream 4.0（火山引擎方舟） | 服装类对参考图驱动支持好 |
| 视频生成 | Seedance 2.0（火山引擎方舟） | 与视频项目方案 4 复用 |
| LLM | Claude Sonnet 4.5 model id via 5dock NewAPI | 走公司统一中转；以 `docs/model-matrix.md` 为唯一模型真源 |
| 任务输入 / 审核 | 飞书多维表 | 不写自定义前端 |
| 媒体存储 | 阿里云 OSS | CDN 现成 |
| 任务库 | PostgreSQL 16 | 同 VPS docker |
| 反向代理 | Caddy | 自动 HTTPS |
| 队列 | Redis | N8N queue mode |

---

## 三、核心样品（演示围绕它走）

| 字段 | 值 |
|---|---|
| SKU | `YN-BRA-001` |
| 名称 | 黑色高弹速干运动内衣（前拉链款）|
| 卖点 | 透气网眼面料、前置拉链穿脱方便、高弹力支撑、速干 |
| 场景 | 瑜伽馆、跑步、健身房、户外 |
| 受众 | 25-40 岁运动女性 |
| 颜色 | 黑色为主，备选深灰 |
| 尺码 | S / M / L / XL |
| 视频时长 | 12 秒（4 镜，每镜 3 秒）|

---

## 四、文件结构索引

```
01-内容工厂项目/
├── README.md                        ← 你正在看的文件
├── docs/                            ← 所有设计文档
│   ├── phase-0-charter.md           （Phase 0 目标 / 非目标 / 退出条件）
│   ├── acceptance-rubric.md         （客户验收评分表）
│   ├── model-matrix.md              （模型 ID / endpoint / fallback 真源）
│   ├── risk-register.md             （风险、owner、trigger、fallback）
│   ├── architecture.md              （总架构 + 演示讲稿）
│   ├── image-pipeline.md            （图片链路完整说明）
│   ├── video-pipeline.md            （视频链路完整说明）
│   ├── audit-workflow.md            （审核工作台设计）
│   ├── archive-structure.md         （归档结构与 OSS 路径）
│   ├── delivery-package.md          （给客户的 SOW，可直接发）
│   └── demo-script.md               （下午演示走台脚本 ⭐）
├── schemas/                         ← 数据层
│   ├── postgres-init.sql            （含 YN-BRA-001 seed 数据）
│   ├── feishu-fields.md             （飞书 4 张多维表字段表）
│   ├── state-machine.md             （任务状态机 + mermaid 图）
│   └── README.md                    （schema 部署与扩展指南）
├── prompts/                         ← LLM prompt 模板库
│   ├── image/
│   │   ├── 01-product-attribute-extraction.md
│   │   ├── 02-selling-points.md
│   │   ├── 03-product-shot-prompt.md
│   │   └── 04-scene-shot-prompt.md
│   └── video/
│       ├── 01-storyboard.md         （含 YN-BRA-001 完整 4 镜脚本）
│       ├── 02-keyframe-prompt.md    （4 镜对应 4 个首帧 prompt）
│       └── 03-video-prompt.md       （4 镜对应 4 个 Seedance prompt）
├── n8n/                             ← N8N 工作流（可 import）
│   ├── image-workflow.json
│   └── video-workflow.json
└── deploy/                          ← 部署
    ├── docker-compose.yml           （n8n + postgres + caddy + redis）
    ├── .env.example                 （所有需填变量）
    └── bootstrap.sh                 （一键起栈脚本）
```

---

## 五、已有环境下 5 分钟触发 demo

> 注意：Docker、N8N owner 账号、API key、workflow import、飞书表结构首次配置不计入这 5 分钟。完整本地搭建看 `SETUP.md`。

```bash
# 1. 进入部署目录
cd 01-内容工厂项目/deploy

# 2. 复制环境变量模板，填入凭据
cp .env.example .env
vim .env                # 填火山方舟 / 5dock / OSS / 飞书 / Caddy 域名

# 3. 一键起栈
bash bootstrap.sh

# 4. 等服务起来后访问
# - N8N 画布: https://n8n.<你的域名>
# - PostgreSQL: 内网 5432

# 5. import N8N workflow
# 在 N8N 画布点 Workflows → Import from File → 选 n8n/image-workflow.json
# 同样 import n8n/video-workflow.json

# 6. 录入飞书多维表
# 按 schemas/feishu-fields.md 建 4 张表，把 YN-BRA-001 填进"产品输入表"

# 7. 触发流程
curl -X POST https://api.<你的域名>/webhook/trigger/image \
    -H "Content-Type: application/json" \
    -d '{"task_id": "task-yn-bra-001-image-001"}'
```

---

## 六、演示当天用什么

按这个顺序点：

1. **`docs/architecture.md`** — 开场 5 分钟讲架构图
2. **N8N 画布**（浏览器）— 中段 7 分钟现场跑流程
3. **飞书多维表** — 演示审核 4 分钟
4. **`docs/demo-script.md`** — 全程参考的走台脚本，含 12 个客户常见问题预演 ⭐

如果 demo 当场翻车（API 超时 / 生成质量差 / 网络卡），翻 `docs/demo-script.md` 末尾的"应急预案"。

演示必须透明标注：

- `LIVE`：现场真实触发的任务。
- `PRE-GENERATED`：预生成兜底资产，只证明目标效果，不伪装成现场刚生成。

---

## 七、客户必须确认的事（演示后立刻问）

- [ ] 是否已有阿里云 OSS / 火山引擎账号？没有的话谁去开？
- [ ] 是否接受飞书作为输入和审核入口？还是要换企微 / 钉钉？
- [ ] 参考图怎么提供？图床 URL / 飞书附件 / OSS 上传？
- [ ] 模特是否用真人脸？是否有版权 / 肖像授权问题？
- [ ] 首期核心产品确定是什么？（YN-BRA-001 是我们假设的，要换成客户真实 SKU）
- [ ] 验收标准里"一样或更高"是谁说了算？需不需要客户指定 1-3 名审核人？
- [ ] 是否认可 `docs/acceptance-rubric.md` 的评分维度、权重和通过线？
- [ ] VPS 谁出？我方代部署还是客户自部署？
- [ ] 内容版权归属（生成图 / 生成视频）默认归甲方，需要写进合同吗？

完整版见 `docs/architecture.md` 末尾的"风险与未决项"。

---

## 八、本项目不包含什么（默认排除）

按需求原文复述（也写在 `docs/delivery-package.md` 里）：

- 跨品类大规模批量稳定化
- 长期代运营
- 无限次返工或无限制效果调优
- 人工 PS 服务
- 大量定制前端系统开发

如有以上需求，**另行评估**。

---

## 九、保修与扩展

- **交付后 1 个月免费保修**（见 `docs/delivery-package.md`）
- 后续同类（服装类）SKU 可基于本次模板复用
- 跨品类 / 大规模稳定量产 / 新增复杂要求需另行评估

---

## 十、变更记录

| 日期 | 变更 | 经手 |
|---|---|---|
| 2026-05-08 | Phase 0 工程设计完成（架构 / schema / prompt / N8N / 部署 / 演示）| Joshua |
| 2026-05-08 | 跨 agent 一致性修复：N8N workflow 7 处 SQL query 改写到对齐 schema、enum 扩 3 个值、credential ID 统一为 kebab-case；演示当天 Postgres 节点不需要禁掉 | Joshua |
