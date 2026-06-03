# AI 内容工厂

`AI-Content-Factory` 是一个面向服装电商场景的内容生产工程项目，目标是把“录入商品资料 -> 生成图片与视频候选 -> 审核 -> 归档”这一套流程标准化、可复用化，便于在本地或 VPS 环境中部署与扩展。

当前仓库主要包含：

- 图片生成链路的工作流定义
- 视频生成链路的工作流定义
- 本地联调用的表单界面
- PostgreSQL 初始化脚本与数据契约
- 提示词模板、归档规范、审核流程说明
- 本地与服务器部署配置

本项目不是传统的前后端 Web 应用，而是一个“工作流 + 数据库 + 资产管理 + 辅助脚本”的工程仓库。核心编排由 n8n 承担，数据库使用 PostgreSQL，预置样例素材保存在 `_seed_assets/`。

## 1. 项目目标

这个项目要解决的问题是：

1. 让运营侧只需要录入一份 SKU 资料，就能触发整条内容生成链路。
2. 让图片和视频共用同一套商品资料、风格信息和审核机制，避免两条链路互相割裂。
3. 让审核过程结构化，而不是靠聊天记录或零散备注推进。
4. 让最终素材可以归档、可追溯、可复用，而不是生成后散落在各个平台。
5. 让整套流程可以在本地先跑通，再迁移到服务器部署。

## 2. 适用范围

当前仓库的基础数据和文档以服装电商场景为基线，尤其适合以下类型的内容生产：

- 白底商品图
- 场景商品图
- 商品卖点短视频
- 审核后二次生成
- SKU 级素材归档

虽然基础样例围绕 `YN-BRA-001` 展开，但整体结构并不只适用于这一个商品。文档中的很多设计，比如状态机、归档路径、审核回写、提示词拆分，都可以迁移到其他服饰类 SKU。

## 3. 技术栈

仓库当前的核心组成如下：

| 模块 | 选型 | 作用 |
|---|---|---|
| 工作流编排 | n8n | 串联图片、视频、审核、回写等流程 |
| 数据库 | PostgreSQL 16 | 保存任务、候选、运行记录、归档元数据 |
| 本地运行环境 | Docker Compose | 启动 n8n、Postgres、Redis |
| 提示词模板 | Markdown | 组织图片链路、视频链路各阶段 prompt |
| 本地交互界面 | Python `http.server` | 提供一个轻量录入和结果查看页面 |
| 媒体模型接入 | Volcengine Ark / NewAPI | 调用图片、视频、LLM 相关能力 |
| 素材归档 | OSS 方案文档 + 工作流约定 | 约束候选、交付、原始素材路径 |

## 4. 模型介入总览

这个项目里，模型不是“一次调用做完整条链路”，而是分段介入。更准确地说，系统把任务拆成多个子步骤，每一步只让对应模型处理它最擅长的部分。

可以先把整体理解成下面这张表：

| 模型 / 服务 | 介入环节 | 输入 | 输出 | 不负责什么 |
|---|---|---|---|---|
| Claude Sonnet 4.6（经 5dock / NewAPI） | 文本理解与提示词生成 | 商品资料、卖点、风格模板、审核反馈 | 结构化属性、卖点摘要、图片 prompt、视频分镜、视频 prompt | 不直接生成图片或视频 |
| Seedream 4.0（经 Volcengine Ark） | 图片生成 | 英文图片 prompt、参考图、尺寸、seed 等 | 商品图、场景图、关键帧图 | 不做商品资料理解，不做审核决策 |
| Seedance 2.0（经 Volcengine Ark） | 视频生成 | 视频 prompt、首帧图、尾帧图、时长等 | 分镜视频片段 | 不负责写脚本，不负责字幕定稿 |
| ASR 服务 | 字幕转写 | 视频音轨 | 字幕时间戳 / SRT | 不负责内容创作 |
| n8n / PostgreSQL / OSS | 编排、存储、审核回写 | 任务、状态、模型结果 | 工作流状态推进、结果归档 | 不生成内容 |

可以把它理解成：

1. LLM 负责“想清楚怎么生成”
2. 图像模型负责“把图做出来”
3. 视频模型负责“把镜头动起来”
4. ASR 负责“把音频转成字幕”
5. n8n 和数据库负责“把这些步骤串起来并记录下来”

### 4.1 图片链路里的模型分工

图片链路不是“把商品资料扔给 Seedream 就结束”，而是通常分为四段：

1. LLM-A 先把商品资料解析成结构化属性
2. LLM-B 再把商品卖点整理成适合视觉表达的卖点集合
3. LLM-C 基于属性、卖点、风格模板和镜头计划，组装出多条英文图片 prompt
4. Seedream 根据每条 prompt 和参考图真正生成图片

所以图片链路里，LLM 的职责是“理解需求并生成 prompt”，Seedream 的职责是“执行生成”。

### 4.2 视频链路里的模型分工

视频链路也不是“一次模型调用出成片”，而是至少拆成四段：

1. LLM 先生成 4 镜分镜脚本
2. LLM 再为每一镜生成关键帧 prompt
3. Seedream 生成每一镜的首帧图
4. LLM 再根据分镜和首帧生成视频 prompt
5. Seedance 按镜头逐段生成视频
6. ASR 或规则化字幕逻辑生成字幕
7. FFmpeg 把片段拼成最终成片

所以视频链路里，真正“产出视频像素”的是 Seedance；真正“决定镜头怎么写”的是 LLM；真正“负责合成文件”的则是本地工作流和 FFmpeg。

## 5. 仓库结构

```text
.
├── _seed_assets/
│   ├── audio/                     # 样例音频素材
│   ├── images/                    # 样例图片素材
│   └── videos/                    # 样例视频素材
├── deploy/
│   ├── .env.example               # 服务器部署环境变量模板
│   ├── .env.local.example         # 本地运行环境变量模板
│   ├── bootstrap-local.sh         # 本地一键起栈脚本
│   ├── bootstrap.sh               # 服务器部署辅助脚本
│   ├── docker-compose.local.yml   # 本地 compose
│   ├── docker-compose.yml         # 服务器 compose
│   ├── Caddyfile                  # 反向代理配置
│   └── initdb/                    # 数据库初始化脚本挂载目录
├── docs/
│   ├── README.md                  # 文档导航
│   ├── architecture.md            # 系统架构总览
│   ├── archive-structure.md       # 归档路径与交付包规范
│   ├── audit-workflow.md          # 审核工作台设计
│   ├── image-pipeline.md          # 图片链路设计
│   └── video-pipeline.md          # 视频链路设计
├── n8n/
│   ├── image-workflow.json        # 图片工作流
│   └── video-workflow.json        # 视频工作流
├── prompts/
│   ├── image/                     # 图片链路 prompt 模板
│   └── video/                     # 视频链路 prompt 模板
├── schemas/
│   ├── README.md                  # 数据层说明
│   ├── feishu-fields.md           # 飞书字段规范
│   ├── postgres-init.sql          # 初始化 SQL
│   ├── smoke-test.sh              # 冒烟脚本
│   └── state-machine.md           # 状态机说明
├── scripts/
│   ├── dry-run.sh                 # 端到端 dry-run
│   ├── generate-fallback-assets.sh# 生成兜底素材
│   ├── generate_seedance_video.py # 单独生成样例视频
│   ├── generate_seedream_images.py# 单独生成样例图片
│   ├── intake_form.py             # 本地表单与结果页
│   ├── n8n_setup.py               # 自动创建 n8n 凭据与导入 workflow
│   └── verify-apis.sh             # API 连通性验证
├── .gitignore
├── README.md
└── SETUP.md
```

## 6. 目录职责说明

### 6.1 `deploy/`

这个目录负责“环境怎么启动”。

- 如果你是在自己电脑上跑本地联调，重点看 `docker-compose.local.yml` 和 `bootstrap-local.sh`
- 如果你是在 VPS 上部署完整环境，重点看 `docker-compose.yml`、`.env.example` 和 `Caddyfile`
- `initdb/01-postgres-init.sql` 会在容器首次启动 PostgreSQL 时自动执行

### 6.2 `docs/`

这个目录负责“设计怎么解释”。

- `architecture.md`：从全局角度讲清系统组件、数据流和部署方式
- `image-pipeline.md`：只看图片链路
- `video-pipeline.md`：只看视频链路
- `audit-workflow.md`：只看审核过程、回写和 SLA
- `archive-structure.md`：只看 OSS 路径、交付包、生命周期

如果你第一次接手这个项目，建议阅读顺序是：

1. `README.md`
2. `SETUP.md`
3. `docs/README.md`
4. `docs/architecture.md`
5. 按需继续看 image / video / audit / archive

### 6.3 `n8n/`

这个目录存的是可导入的 workflow JSON。

- `image-workflow.json`：图片任务链路
- `video-workflow.json`：视频任务链路

这两个文件是仓库里最接近“业务流程定义”的内容。只要 n8n 凭据准备好，就可以通过导入它们来复现流程骨架。

### 6.4 `prompts/`

这里存的是文本模板，不是代码逻辑。

图片链路里通常会经过：

- 商品属性提取
- 卖点提炼
- 商品图 prompt 组装
- 场景图 prompt 组装

视频链路里通常会经过：

- 分镜脚本生成
- 关键帧 prompt 生成
- 视频 prompt 生成

如果你想优化生成效果，通常优先改这里，而不是先动 workflow。

### 6.5 `schemas/`

这里定义数据契约。

你可以把它理解成“所有模块之间的共识层”：

- PostgreSQL 表结构长什么样
- 飞书字段如何对应
- 状态机有哪些状态和迁移

如果后续要改字段、加表、加状态，最好先改 `schemas/`，再回头改 workflow 和脚本。

### 6.6 `scripts/`

这个目录存放日常联调和本地辅助脚本。

常用脚本说明：

| 脚本 | 作用 |
|---|---|
| `n8n_setup.py` | 自动创建本地 n8n 所需 credential，并导入两个 workflow |
| `intake_form.py` | 启动本地表单页和结果页，便于从浏览器触发任务 |
| `dry-run.sh` | 跑一轮图片链路 dry-run，验证数据库、n8n、workflow 是否联通 |
| `verify-apis.sh` | 验证外部 API 是否可访问 |
| `generate-fallback-assets.sh` | 生成或拉取本地兜底素材 |
| `generate_seedream_images.py` | 单独测试图片生成 |
| `generate_seedance_video.py` | 单独测试视频生成 |

## 7. 系统整体流程

从高层看，这个项目的流程可以概括成下面几步：

1. 录入商品资料
2. 读取商品信息和风格信息
3. 生成图片 prompt 与视频 prompt
4. 调外部模型生成图片或视频
5. 将候选结果写入数据库
6. 回写审核台或结果页
7. 根据审核结果决定通过、打回或二次生成
8. 审核通过后做归档和交付

其中有三个特别关键的工程点：

- 统一商品资料来源：避免图片和视频各自维护一套输入
- 统一状态流转：避免审核状态和生成状态互相打架
- 统一归档结构：避免最后资产无法追溯

## 8. 快速开始

如果你只是想最快把本地版本跑起来，可以按下面步骤执行：

```bash
cp deploy/.env.local.example deploy/.env.local
bash deploy/bootstrap-local.sh
python scripts/n8n_setup.py --token=<your_n8n_api_token>
python scripts/intake_form.py
```

启动后访问：

- `http://localhost:5678`：n8n 控制台
- `http://localhost:5001`：本地录入表单

更详细的本地说明见 [SETUP.md](SETUP.md)。

## 9. 本地运行方式

本地运行的目标不是完全复刻线上环境，而是优先满足这几件事：

1. 能导入 workflow
2. 能把 PostgreSQL 跑起来
3. 能触发并观察任务流程
4. 能在没有完整飞书、OSS、线上域名的情况下先完成联调

因此本地模式有一些默认约定：

- 使用 `docker-compose.local.yml`
- 不强制要求 Caddy、HTTPS、域名
- PostgreSQL 和 Redis 端口直接映射到本机
- 某些外部依赖可以先留空，后续再补

## 10. 生产部署方式

服务器部署与本地部署的主要区别是：

| 项目 | 本地 | 服务器 |
|---|---|---|
| 启动文件 | `docker-compose.local.yml` | `docker-compose.yml` |
| 访问方式 | `localhost` | 域名 + HTTPS |
| 反向代理 | 无 | Caddy |
| 适合用途 | 联调 / 测试 | 正式部署 |
| 外部服务依赖 | 可部分留空 | 需要完整配置 |

如果你要部署到 VPS，建议先完成下面这些前置条件：

1. 域名和子域名准备好
2. VPS 上安装 Docker 和 Docker Compose
3. 外部服务 API Key 准备齐全
4. `.env` 基于 `deploy/.env.example` 正确填写
5. OSS、飞书、ASR 等依赖已经有对应账号和权限

## 11. 环境变量说明

项目里有两套环境变量模板：

### 11.1 `deploy/.env.local.example`

用于本地环境，字段较少，重点是先把容器和基础流程跑起来。

通常最少要关心：

- `POSTGRES_PASSWORD`
- `N8N_ENCRYPTION_KEY`
- `REDIS_PASSWORD`
- `ARK_API_KEY`
- `NEWAPI_KEY`

### 11.2 `deploy/.env.example`

用于服务器环境，字段更完整，覆盖：

- PostgreSQL
- Redis
- n8n
- 域名与证书
- NewAPI
- Volcengine Ark
- OSS
- 飞书
- ASR
- 租户标识

如果你不确定某个变量的来源，建议直接打开模板文件逐条看注释，里面已经写了“从哪里拿”和“是否必填”。

## 12. 核心脚本使用说明

### 12.1 `scripts/n8n_setup.py`

这个脚本用于自动配置本地 n8n。

它会做几件事：

1. 读取 `deploy/.env.local`
2. 使用 n8n API Token 调用 n8n API
3. 创建本地测试用 credential
4. 导入 `n8n/` 下的 workflow
5. 按规则 patch workflow 中的 credential 引用
6. 激活图片工作流

适合场景：

- 刚启动一套新的本地环境
- 想快速恢复 workflow 和凭据

### 12.2 `scripts/intake_form.py`

这是一个本地浏览器入口。

它不是完整业务后台，而是一个轻量的联调页面，用来：

- 录入样例 SKU 数据
- 触发本地 workflow
- 轮询任务进度
- 展示候选结果和样例视频

如果你只想快速验证“从页面点一下到 n8n 开始跑”这个闭环，这个脚本非常有用。

### 12.3 `scripts/dry-run.sh`

这个脚本适合在你怀疑“系统是不是断了”的时候使用。

它会：

1. 检查 Docker 容器是否在跑
2. 自动找一个可用任务
3. 触发图片链路 webhook
4. 轮询数据库，查看 candidates 是否增长
5. 输出最终结果与异常信息

### 12.4 `scripts/verify-apis.sh`

这个脚本适合在外部模型调用失败时使用。

它的作用是尽量把问题前置到“API 是否通”这个层面，而不是等 workflow 跑到一半才发现凭据错了。

## 13. 数据库与数据契约

项目的数据契约主要集中在 `schemas/`。

推荐阅读：

- [schemas/README.md](schemas/README.md)
- [schemas/state-machine.md](schemas/state-machine.md)
- [schemas/feishu-fields.md](schemas/feishu-fields.md)

如果你要加字段、改状态或扩表，建议遵循这个顺序：

1. 先改 schema 设计
2. 再改 workflow 里读写数据库的节点
3. 再改飞书字段或本地表单
4. 最后补文档

## 14. 文档索引

详细文档导航见 [docs/README.md](docs/README.md)。

你也可以按主题直接查阅：

- 总体架构：[docs/architecture.md](docs/architecture.md)
- 图片链路：[docs/image-pipeline.md](docs/image-pipeline.md)
- 视频链路：[docs/video-pipeline.md](docs/video-pipeline.md)
- 审核流程：[docs/audit-workflow.md](docs/audit-workflow.md)
- 归档规范：[docs/archive-structure.md](docs/archive-structure.md)

## 15. 常见排查路径

如果你遇到问题，可以按下面顺序排查：

### 15.1 n8n 打不开

先检查：

- Docker Desktop 是否启动
- `cf-n8n-local` 容器是否存在
- `http://localhost:5678/healthz` 是否可访问

### 15.2 workflow 已导入但节点报红

优先检查：

- `scripts/n8n_setup.py` 是否成功执行
- credential 是否创建成功
- API key 是否已写入 `deploy/.env.local`

### 15.3 页面可以打开，但不出图

优先检查：

- webhook 是否真正触发
- `generation_runs` 是否新增
- 外部 API 是否返回 401 / 429 / 5xx
- n8n 最近一次执行是否有红色节点

### 15.4 数据库初始化失败

优先检查：

- `deploy/initdb/01-postgres-init.sql` 是否已挂载
- PostgreSQL 容器日志里是否有 SQL 报错
- 数据库名和用户名是否与 compose 配置一致

## 16. 当前仓库保留了什么

当前仓库保留的是“工程运行必需内容”和“理解项目必需文档”，包括：

- 工作流定义
- 部署脚本
- 数据库脚本
- 提示词模板
- 样例素材
- 架构与链路说明

已经移除的是：

- 销售话术类文档
- 口播脚本类文档
- 冗余运维操作手册
- 与正式工程无关的重复说明

## 17. 建议的阅读顺序

如果你是第一次接手这个仓库，建议按照下面顺序看：

1. 本文件 `README.md`
2. [SETUP.md](SETUP.md)
3. [docs/README.md](docs/README.md)
4. [schemas/README.md](schemas/README.md)
5. [docs/architecture.md](docs/architecture.md)
6. 按需继续看图片、视频、审核、归档文档

## 18. 后续可以继续优化的方向

如果后面还要继续打磨，我建议下一轮可以做这些事情：

1. 给 `n8n/` 两个 workflow 增加版本说明和变更记录
2. 把 `scripts/` 每个脚本单独补 usage 文档
3. 为本地表单补一份页面字段说明
4. 给数据库表增加一份 ER 图
5. 把本地模式和服务器模式的差异整理成单独文档

---

如需直接上手，请从 [SETUP.md](SETUP.md) 开始。
