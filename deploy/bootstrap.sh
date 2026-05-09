#!/usr/bin/env bash
# =============================================================================
# 服装电商 AI 内容工厂 - 一键部署脚本
# 目标：Ubuntu 22.04 LTS · 4C8G · 已安装 Docker 24+ / Compose v2
# 用法：bash bootstrap.sh
# =============================================================================

set -euo pipefail

# ---------- 颜色输出 ----------
RED=$(printf '\033[31m'); GREEN=$(printf '\033[32m'); YELLOW=$(printf '\033[33m')
BLUE=$(printf '\033[34m'); BOLD=$(printf '\033[1m'); RESET=$(printf '\033[0m')

info()    { echo "${BLUE}[INFO]${RESET}  $*"; }
ok()      { echo "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo "${YELLOW}[WARN]${RESET}  $*"; }
err()     { echo "${RED}[ERR]${RESET}   $*" 1>&2; }
section() { echo; echo "${BOLD}>>> $* <<<${RESET}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ---------- Step 1: 检查 docker / docker compose ----------
section "Step 1/7  检查依赖"

if ! command -v docker >/dev/null 2>&1; then
  err "未检测到 docker。请先安装 Docker 24+：https://docs.docker.com/engine/install/ubuntu/"
  exit 1
fi
ok "docker: $(docker --version)"

if ! docker compose version >/dev/null 2>&1; then
  err "未检测到 docker compose v2 插件。请安装 docker-compose-plugin。"
  exit 1
fi
ok "compose: $(docker compose version --short 2>/dev/null || docker compose version)"

if [ "$(id -u)" -ne 0 ] && ! groups | grep -qw docker; then
  warn "当前用户不在 docker 组，后续命令可能需要 sudo。建议：sudo usermod -aG docker \$USER && newgrp docker"
fi

# ---------- Step 2: 检查 .env ----------
section "Step 2/7  检查 .env 配置"

cd "${SCRIPT_DIR}"

if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    err ".env 不存在。请先 cp .env.example .env 并填写所有 [必填] 项。"
    exit 1
  else
    err ".env 与 .env.example 都不存在，仓库不完整。"
    exit 1
  fi
fi
chmod 600 .env
ok ".env 存在且权限已设为 600"

# 加载 .env，校验关键变量
set -a
# shellcheck disable=SC1091
source .env
set +a

REQUIRED_VARS=(
  POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD
  REDIS_PASSWORD
  N8N_ENCRYPTION_KEY N8N_HOST API_HOST ACME_EMAIL
  TZ TENANT
)
MISSING=()
for v in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!v:-}" ] || [[ "${!v}" == *CHANGE_ME* ]]; then
    MISSING+=("$v")
  fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
  err "以下变量未配置或仍是占位符：${MISSING[*]}"
  err "请编辑 ${SCRIPT_DIR}/.env 后重试。"
  exit 1
fi
ok "关键环境变量校验通过"

# ---------- Step 3: 准备 init SQL ----------
section "Step 3/7  准备 Postgres 初始化脚本"

mkdir -p "${SCRIPT_DIR}/initdb"

INIT_SQL_SOURCE="${PROJECT_DIR}/schemas/postgres-init.sql"
INIT_SQL_TARGET="${SCRIPT_DIR}/initdb/01-init.sql"

if [ -f "${INIT_SQL_SOURCE}" ]; then
  cp -f "${INIT_SQL_SOURCE}" "${INIT_SQL_TARGET}"
  ok "已复制 ${INIT_SQL_SOURCE} → ${INIT_SQL_TARGET}"
else
  warn "未找到 ${INIT_SQL_SOURCE}。将写入一个最小占位 init SQL，后续请从 schemas/ 同步真正的建表语句。"
  cat > "${INIT_SQL_TARGET}" <<'SQL'
-- placeholder: 由 bootstrap.sh 在 schemas/postgres-init.sql 缺失时生成
-- 真正的建表语句应放在仓库 schemas/postgres-init.sql
CREATE TABLE IF NOT EXISTS bootstrap_marker (
  id SERIAL PRIMARY KEY,
  note TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO bootstrap_marker (note) VALUES ('placeholder init from bootstrap.sh');
SQL
fi

# ---------- Step 4: 拉镜像 ----------
section "Step 4/7  拉取 Docker 镜像"
docker compose pull
ok "镜像就绪"

# ---------- Step 5: 启动服务 ----------
section "Step 5/7  启动服务（docker compose up -d）"
docker compose up -d
ok "服务已发起启动"

# ---------- Step 6: 等 Postgres 健康 ----------
section "Step 6/7  等待 Postgres 健康"

MAX_WAIT=120
WAITED=0
while true; do
  STATUS=$(docker inspect -f '{{.State.Health.Status}}' cf-postgres 2>/dev/null || echo "starting")
  if [ "${STATUS}" = "healthy" ]; then
    ok "Postgres healthy"
    break
  fi
  if [ ${WAITED} -ge ${MAX_WAIT} ]; then
    err "Postgres 在 ${MAX_WAIT}s 内未变为 healthy，请查看 docker compose logs postgres"
    docker compose logs --tail=50 postgres
    exit 1
  fi
  printf "."
  sleep 3
  WAITED=$((WAITED + 3))
done

# 顺手检查 N8N 是否能 healthcheck
WAITED=0
while [ ${WAITED} -lt 90 ]; do
  STATUS=$(docker inspect -f '{{.State.Health.Status}}' cf-n8n 2>/dev/null || echo "starting")
  if [ "${STATUS}" = "healthy" ]; then
    ok "N8N healthy"
    break
  fi
  printf "."
  sleep 3
  WAITED=$((WAITED + 3))
done
[ "${STATUS:-x}" = "healthy" ] || warn "N8N 尚未 healthy（首次启动可能要 1-2 分钟），可继续等待或查看 docker compose logs n8n"

# ---------- Step 7: 输出后续操作指南 ----------
section "Step 7/7  部署完成"

cat <<EOF

${BOLD}=================== 部署摘要 ===================${RESET}

${BOLD}N8N 控制台:${RESET}
  https://${N8N_HOST}/

${BOLD}首次登录:${RESET}
  打开上方链接 → 创建 Owner 账号（邮箱 + 密码自定）
  ${YELLOW}重要:${RESET} 第一个注册的账号即超级管理员，请妥善保管。

${BOLD}API webhook 入口（飞书自动化指向这里）:${RESET}
  https://${API_HOST}/webhook/...

${BOLD}Caddy 自动 HTTPS:${RESET}
  首次签发证书需 30-60 秒，过程中如访问报 SSL 错请稍候重试。
  确认 ${N8N_HOST} 与 ${API_HOST} 的 DNS 已解析到本机公网 IP。

${BOLD}导入 N8N 工作流（在仓库 n8n/workflows/ 下放好 *.json 后执行）:${RESET}
  docker compose exec n8n n8n import:workflow --separate --input=/workflows
  导入后再执行 activate：
  docker compose exec n8n n8n update:workflow --all --active=true

${BOLD}查看运行日志:${RESET}
  docker compose logs -f n8n
  docker compose logs -f postgres

${BOLD}停服 / 重启:${RESET}
  docker compose stop
  docker compose restart

${BOLD}备份 Postgres:${RESET}
  docker compose exec postgres pg_dump -U ${POSTGRES_USER} ${POSTGRES_DB} | gzip > backup-\$(date +%F).sql.gz

${BOLD}=============================================${RESET}

EOF
