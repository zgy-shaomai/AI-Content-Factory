# 内容工厂 · 本地一键搭建（同事版）

> 这份文档让你 30 分钟内在自己电脑上跑起来同款演示，体验"客户填表 → AI 出 11 张图 + 视频成片"完整流程。

---

## 你需要准备的东西（5 分钟）

| 物料 | 哪里拿 | 必填 |
|---|---|---|
| **Docker Desktop** | https://www.docker.com/products/docker-desktop/ 装好启动 | ✅ |
| **Python 3.10+** | https://www.python.org/ （Windows 装时勾 "Add to PATH"）| ✅ |
| **火山引擎方舟 API Key** | https://console.volcengine.com/ark → 控制台 → API Key 管理 | ✅ |
| **5dock NewAPI Key** | 找 Joshua 要 vip 分组的 sk-xxx | ✅ |
| **PowerShell** | Windows 自带；本地启动可直接用新增 `.ps1` 脚本 | ✅ |
| **WSL 或 Git Bash** | 只在你想继续跑旧版 `.sh` 脚本时需要 | 可选 |

> ⚠️ **火山方舟需要充值** —— 演示一次约 ¥3-5（图）+ ¥12（视频/条），充 50 元够你测三五轮

---

## 5 步起栈

### 1. 解压 + 进项目

```bash
# 把这个文件夹放任意路径（中文路径也行）
cd /path/to/01-内容工厂项目
```

### 2. 配环境变量

```bash
cp deploy/.env.local.example deploy/.env.local
```

打开 `deploy/.env.local`：

```env
POSTGRES_PASSWORD=随便定一个，比如 cf_local_pwd
N8N_ENCRYPTION_KEY=用下面命令生成 64 位 hex
REDIS_PASSWORD=随便定，比如 cf_redis_pwd
ARK_API_KEY=ark-你的火山方舟 key
NEWAPI_KEY=sk-Joshua 给你的 5dock vip key
```

说明：
- `POSTGRES_PASSWORD` / `REDIS_PASSWORD` 可以先用示例默认值
- 真正必填的是 `N8N_ENCRYPTION_KEY`
- 想让图片/视频真跑起来，再填 `ARK_API_KEY` 和 `NEWAPI_KEY`

生成 N8N 加密 key：
```bash
# Linux/Mac/WSL/Git Bash:
openssl rand -hex 32
# 或 Python:
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. 启 Docker Desktop（手动）

任务栏右下角小鲸鲸图标变绿。

### 4. 一键起栈

PowerShell：
```powershell
.\deploy\bootstrap-local.ps1
```

如果你还保留 bash 环境，也可以继续用：
```bash
bash deploy/bootstrap-local.sh
```

期望看到：
```
✅ .env.local 必填项都齐了
✅ Docker 已启动
✅ Postgres ready
✅ schema 已部署，9 张表
✅ run_status / candidate_status enum 都扩好了
✅ N8N ready
```

### 5. 配 N8N（一次性，约 5 分钟）

打开浏览器 http://localhost:5678

**5.1** 注册 owner 账号（邮箱随便填，密码自定，不会发验证邮件）

**5.2** 左下角头像 → Settings → n8n API → **Create an API key**（不要过期或 30 天都行）→ 复制 token

**5.3** 跑配置脚本（任选一种方式传 token）：

```bash
# 方式 1: 命令行参数
python scripts/n8n_setup.py --token=eyJhbG...你刚复制的token

# 方式 2: 环境变量
export N8N_API_TOKEN=eyJhbG...你刚复制的token   # Linux/Mac/WSL
set N8N_API_TOKEN=eyJhbG...你刚复制的token       # Windows cmd
$env:N8N_API_TOKEN="eyJhbG...你刚复制的token"    # PowerShell
python scripts/n8n_setup.py
```

它会自动：
- 创建 6 个 credential（postgres / 5dock / ARK / OSS / 飞书 / ASR）
- import 两个 workflow（image + video）
- 绑定 credential 到节点
- 激活 image-workflow

期望末尾输出：`🟢 Active  ContentFactory · Image Pipeline (YN-BRA-001 baseline)`

### 6. 启录入表单（演示主入口）

新开一个终端：
```bash
python scripts/intake_form.py
```

浏览器打开 **http://localhost:5001** —— 看到深色 hero + 录入表单就 OK 了。

---

## 完整演示流程（验证步骤）

1. http://localhost:5001 → 点 [运动内衣 · 黑] 模板 chip → [开始生成]
2. 跳到进度页，2-3 分钟看 11 张图涨出来（每张 10-15 秒）
3. **新任务**视频区是空状态 + 配置表单：
   - 选首帧图（dropdown 或直接 hover 图卡点 [🎬]）
   - 改 prompt
   - 点 [🎬 提交生成视频成片]
4. 等 90-180 秒（真调 Seedance）
5. 看真新视频出来 + 点 [🔊 旁白] 听神经声口播
6. 浏览器开 http://localhost:5001/history 看历史卡片，点任意一张回看

---

## 常见问题

### Docker Desktop 启动报错 "filename, directory name, or volume label syntax is incorrect"
这是 Docker Desktop 4.5x+ 的 zombie socket bug：
1. 点 Quit
2. 重命名文件夹：`mv ~/AppData/Local/Docker/run ~/AppData/Local/Docker/run.broken`
3. 重启 Docker Desktop
4. 还不行 → 重启 Windows

### N8N 节点全部红色 ⚠️
Credential ID 没绑上。重跑 `python scripts/n8n_setup.py`。

### 想先验 API 是否可用
PowerShell 直接跑：`.\scripts\verify-apis.ps1`

### 候选图 0/11 一直涨不起来
查 N8N 画布最近一次执行的红色节点。常见原因：
- ARK_API_KEY 错 → curl 验证：`bash scripts/verify-apis.sh`
- 5dock vip 分组没 claude-sonnet-4-5-20250929 → 找 Joshua 加
- N8N 没 Active → 浏览器 N8N → 右上角开关

### 视频生成 4 分钟还没好
火山方舟高峰期常见。重新点 [🎬 提交生成视频成片] 重试。

### 表单服务 5001 端口起不来
端口被占。Windows: `netstat -ano | findstr 5001` 找 PID 然后 `taskkill /F /PID <pid>`

---

## 文件说明

| 文件 / 目录 | 用途 |
|---|---|
| `deploy/docker-compose.local.yml` | 本地版 docker-compose（无 Caddy）|
| `deploy/.env.local.example` | 环境变量模板 |
| `deploy/bootstrap-local.ps1` | Windows 原生本地起栈 |
| `deploy/bootstrap-local.sh` | 一键起栈 |
| `schemas/postgres-init.sql` | 数据库 schema + seed 数据 |
| `n8n/image-workflow.json` | 图片链路 workflow（19 节点）|
| `n8n/video-workflow.json` | 视频链路 workflow（27 节点）|
| `prompts/` | LLM prompt 模板 |
| `scripts/intake_form.py` | 录入表单 + 视频实时生成（端口 5001）|
| `scripts/n8n_setup.py` | N8N credentials + workflow 自动配置 |
| `scripts/verify-apis.ps1` | Windows 原生验证 ARK / NewAPI key |
| `scripts/verify-apis.sh` | 验证 ARK / NewAPI key 通不通 |
| `scripts/generate_seedream_images.py` | 单独生成 11 张兜底图 |
| `scripts/generate_seedance_video.py` | 单独生成兜底视频 |
| `_demo_seed/` | 预生成的兜底素材（图 + 视频 + 旁白音频）|
| `docs/` | 架构 / SOW / 演示讲稿等设计文档 |

---

## 卡住找谁

Joshua（项目 owner）—— 微信问。
