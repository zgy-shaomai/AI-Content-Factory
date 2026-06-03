# 本地部署说明

本文档用于说明如何在本地把 `AI-Content-Factory` 跑起来，并理解本地模式与服务器模式之间的差异。

如果你只是想先把项目跑通，请完整看完本文档再执行命令。很多问题不是“代码坏了”，而是本地依赖、凭据或 n8n 初始化步骤漏了。

## 1. 本地模式的目标

本地模式主要是为了做以下事情：

1. 验证 Docker、Postgres、Redis、n8n 能否正常启动
2. 验证 workflow 能否导入并触发
3. 验证本地表单、数据库与 n8n 的联通
4. 在不接完整线上环境的情况下先完成基础联调

本地模式默认不追求 100% 复刻正式生产环境，因此会做一些简化：

- 使用 `localhost` 访问
- 不强依赖 HTTPS
- 不强依赖域名
- 可先不接飞书与 OSS
- 允许保留一部分样例素材做回显

## 2. 前置依赖

在开始前，请确保本机具备以下条件：

- Docker Desktop
- Python 3.10+
- Git Bash 或 WSL
- 能访问外部模型 API 的网络环境
- 可用的 Volcengine Ark API Key
- 可用的 NewAPI Key

推荐额外准备：

- 一个可用的终端环境
- 一个可访问 `http://localhost:5678` 的浏览器
- `openssl`，用于快速生成 `N8N_ENCRYPTION_KEY`

## 3. 你会用到的主要文件

本地启动时最关键的是这几个文件：

| 文件 | 作用 |
|---|---|
| `deploy/.env.local.example` | 本地环境变量模板 |
| `deploy/bootstrap-local.sh` | 本地一键起栈 |
| `deploy/docker-compose.local.yml` | 本地 Docker 编排 |
| `scripts/n8n_setup.py` | 初始化 n8n |
| `scripts/intake_form.py` | 启动本地表单页 |
| `scripts/dry-run.sh` | 验证图片链路是否跑通 |

## 4. 第一步：配置环境变量

先从模板复制一份本地环境变量文件：

```bash
cp deploy/.env.local.example deploy/.env.local
```

然后编辑 `deploy/.env.local`。

至少要确认下面这些字段：

```env
POSTGRES_PASSWORD=
N8N_ENCRYPTION_KEY=
REDIS_PASSWORD=
ARK_API_KEY=
NEWAPI_KEY=
```

### 4.1 这几个变量分别干什么

| 变量 | 作用 | 是否必须 |
|---|---|---|
| `POSTGRES_PASSWORD` | 本地 Postgres 密码 | 必须 |
| `N8N_ENCRYPTION_KEY` | n8n 凭据加密密钥 | 必须 |
| `REDIS_PASSWORD` | 本地 Redis 密码 | 必须 |
| `ARK_API_KEY` | 图片/视频相关外部能力调用 | 建议填写 |
| `NEWAPI_KEY` | LLM 或中转服务调用 | 建议填写 |

### 4.2 如何生成 `N8N_ENCRYPTION_KEY`

推荐直接使用：

```bash
openssl rand -hex 32
```

注意：

- 这个值一旦用于 n8n，就不要随便改
- 如果你改了它，已有 credentials 可能失效

## 5. 第二步：启动本地依赖

执行：

```bash
bash deploy/bootstrap-local.sh
```

这个脚本会做几件事：

1. 检查 `.env.local` 是否存在
2. 检查关键变量是否已填写
3. 检查 Docker 是否已启动
4. 把数据库初始化脚本放到 `deploy/initdb/`
5. 启动 Postgres、Redis、n8n
6. 等待数据库和 n8n 健康检查通过

如果脚本顺利完成，说明本地容器基础环境已经正常。

## 6. 第三步：打开 n8n 并创建 API Key

启动后打开：

`http://localhost:5678`

第一次进入时需要：

1. 注册 owner 账号
2. 进入头像菜单
3. 打开 `Settings`
4. 找到 `n8n API`
5. 创建一个 API Key

这个 token 稍后会给 `scripts/n8n_setup.py` 使用。

## 7. 第四步：自动导入 workflow 和 credentials

执行：

```bash
python scripts/n8n_setup.py --token=<your_n8n_api_token>
```

这个脚本会自动：

1. 读取 `deploy/.env.local`
2. 创建本地使用的 credential
3. 导入 `n8n/image-workflow.json`
4. 导入 `n8n/video-workflow.json`
5. patch 一部分 credential 引用
6. 激活图片工作流

### 7.1 这个脚本为什么重要

如果你跳过这一步，常见结果会是：

- workflow 虽然存在，但节点凭据全是空的
- HTTP 请求节点报红
- Postgres 节点无法连接
- 本地触发后 workflow 根本跑不起来

## 8. 第五步：启动本地表单页面

执行：

```bash
python scripts/intake_form.py
```

然后访问：

`http://localhost:5001`

这个页面主要提供三类能力：

1. 录入样例商品信息
2. 触发任务
3. 查看候选结果和样例视频

它不是一个正式后台，而是一个方便联调的轻量入口。

## 9. 第六步：验证整条链路

如果页面能打开，不代表链路就一定完整可用。建议再跑一遍 dry-run：

```bash
bash scripts/dry-run.sh
```

这个脚本会：

1. 检查 n8n 和 Postgres 容器是否在跑
2. 找一个可用图片任务
3. 触发 image webhook
4. 轮询数据库里的 candidates 变化
5. 输出最终是否达到预期数量

这是判断“系统到底通没通”的最快方式之一。

## 10. 本地常用地址

- `http://localhost:5678`：n8n 控制台
- `http://localhost:5001`：本地录入表单
- `localhost:55432`：Postgres 映射端口
- `localhost:56379`：Redis 映射端口

## 11. 本地常用命令

### 11.1 启动本地环境

```bash
bash deploy/bootstrap-local.sh
```

### 11.2 重新初始化 n8n

```bash
python scripts/n8n_setup.py --token=<your_n8n_api_token>
```

### 11.3 启动本地表单

```bash
python scripts/intake_form.py
```

### 11.4 验证 API

```bash
bash scripts/verify-apis.sh
```

### 11.5 跑 dry-run

```bash
bash scripts/dry-run.sh
```

## 12. 常见问题排查

### 12.1 `http://localhost:5678` 打不开

优先检查：

- Docker Desktop 是否已启动
- `cf-n8n-local` 是否在运行
- `docker ps` 是否能看到相关容器
- `http://localhost:5678/healthz` 是否返回成功

### 12.2 n8n 节点全部发红

高概率原因：

- 没执行 `scripts/n8n_setup.py`
- API token 错误
- `.env.local` 没填完整
- credential 没创建成功

先重新执行：

```bash
python scripts/n8n_setup.py --token=<your_n8n_api_token>
```

### 12.3 表单能打开，但点提交没有反应

排查顺序建议：

1. 看 `intake_form.py` 所在终端有没有报错
2. 看 n8n 最近一次执行有没有触发
3. 看 PostgreSQL 里是否有新任务
4. 看 webhook 地址是否正确

### 12.4 图片或视频不生成

优先检查：

- `ARK_API_KEY` 是否正确
- `NEWAPI_KEY` 是否正确
- 网络是否能访问外部 API
- `scripts/verify-apis.sh` 是否通过

### 12.5 5001 端口被占用

Windows 下可以先查占用：

```bash
netstat -ano | findstr 5001
```

找到 PID 后再决定是否释放对应进程。

### 12.6 数据库初始化异常

优先检查：

- `deploy/initdb/01-postgres-init.sql` 是否存在
- PostgreSQL 日志是否有 SQL 错误
- 数据库名、用户、密码是否与 compose 配置一致

## 13. 本地模式与服务器模式的区别

很多同学会在本地能跑通后，直接拿同样的理解去部署服务器，结果踩坑。主要差异在这里：

| 项目 | 本地模式 | 服务器模式 |
|---|---|---|
| compose 文件 | `docker-compose.local.yml` | `docker-compose.yml` |
| 域名 | 不需要 | 需要 |
| HTTPS | 通常不配 | 通常要配 |
| 反向代理 | 不需要 | 使用 Caddy |
| 外部依赖 | 可部分留空 | 应完整接入 |
| 用途 | 联调和验证 | 正式运行 |

如果你已经完成本地联调，下一步建议去看：

- `deploy/.env.example`
- `deploy/docker-compose.yml`
- `docs/architecture.md`

## 14. 什么时候算本地环境“真的跑通了”

建议同时满足下面几个条件：

1. Docker 容器正常启动
2. `http://localhost:5678` 可访问
3. `scripts/n8n_setup.py` 执行成功
4. `http://localhost:5001` 可访问
5. `scripts/dry-run.sh` 返回成功

只有“页面能打开”或者“容器能起来”都还不算真正跑通。

## 15. 推荐的本地调试顺序

如果你后面要继续改这个项目，建议按这个顺序调试：

1. 先看 `README.md` 理解全貌
2. 再按本文件把环境起起来
3. 用 `n8n_setup.py` 恢复 workflow
4. 用 `intake_form.py` 验证入口
5. 用 `dry-run.sh` 验证图片链路
6. 再根据需要深入看 `docs/` 和 `schemas/`

---

本地环境跑通后，建议继续看 [docs/README.md](docs/README.md) 和 [schemas/README.md](schemas/README.md)。
