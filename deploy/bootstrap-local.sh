#!/usr/bin/env bash
# =============================================================================
# 本地演示一键起栈脚本
# =============================================================================
# 跑这个之前：
#   1. Docker Desktop 已启动（右下角小鲸鱼变绿）
#   2. cp .env.local.example .env.local，填 6 个 CHANGE_ME
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$SCRIPT_DIR"

RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; NC=$'\033[0m'

# ---------- step 1: 检查 .env.local ----------
echo "${YLW}▶ 检查 .env.local...${NC}"
if [[ ! -f .env.local ]]; then
    echo "${RED}❌ .env.local 不存在。先 cp .env.local.example .env.local，填好 3 个必填项再来。${NC}"
    exit 1
fi

# 只强制 3 个关键变量（基础设施起栈必须）
# API key 可以留空，stack 能起来，等拿到 key 后填进去重启 n8n 即可
set -o allexport
# shellcheck source=/dev/null
source .env.local
set +o allexport
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-content_factory}"

MISSING=0
for v in POSTGRES_PASSWORD N8N_ENCRYPTION_KEY REDIS_PASSWORD; do
    val="${!v:-}"
    if [[ -z "$val" || "$val" == CHANGE_ME* ]]; then
        echo "${RED}  ❌ $v 必填且不能保留 CHANGE_ME${NC}"
        MISSING=1
    fi
done
[[ $MISSING -eq 1 ]] && exit 1

# 软警告：API key 没填仍可起栈，但 N8N workflow 跑不通
for v in LLM_API_KEY IMAGE_API_KEY VIDEO_API_KEY; do
    val="${!v:-}"
    [[ -z "$val" && "$v" == "LLM_API_KEY" ]] && val="${NEWAPI_KEY:-}"
    [[ -z "$val" && "$v" == "IMAGE_API_KEY" ]] && val="${MEDIA_API_KEY:-${ARK_API_KEY:-}}"
    [[ -z "$val" && "$v" == "VIDEO_API_KEY" ]] && val="${MEDIA_API_KEY:-${ARK_API_KEY:-}}"
    if [[ -z "$val" || "$val" == CHANGE_ME* ]]; then
        echo "${YLW}  ⚠ $v 没填 → 栈能起，但 workflow 调用会 401。等拿到 key 后填进去，重启: docker restart cf-n8n-local${NC}"
    fi
done
echo "${GRN}  ✅ .env.local 必填项都齐了${NC}"

# ---------- step 2: 检查 Docker ----------
echo "${YLW}▶ 检查 Docker daemon...${NC}"
if ! docker ps >/dev/null 2>&1; then
    echo "${RED}❌ Docker daemon 没启。打开 Docker Desktop 再来。${NC}"
    exit 1
fi
echo "${GRN}  ✅ Docker 已启动${NC}"

# ---------- step 3: 把 schema 复制到 initdb 目录 ----------
echo "${YLW}▶ 准备 initdb...${NC}"
mkdir -p initdb
cp "$ROOT_DIR/schemas/postgres-init.sql" initdb/01-postgres-init.sql
echo "${GRN}  ✅ initdb/01-postgres-init.sql 就位${NC}"

# ---------- step 4: 起栈 ----------
echo "${YLW}▶ 起 postgres + redis + n8n（首次约 60-90 秒）...${NC}"
docker compose -f docker-compose.local.yml --env-file .env.local up -d
echo "${GRN}  ✅ 容器已启动${NC}"

# ---------- step 5: 等 postgres ready ----------
echo "${YLW}▶ 等 Postgres ready...${NC}"
for i in $(seq 1 30); do
    if docker exec cf-postgres-local pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
        echo "${GRN}  ✅ Postgres ready (${i}s)${NC}"
        break
    fi
    sleep 1
done

# ---------- step 6: 验证 schema 部署 ----------
echo "${YLW}▶ 验证 schema...${NC}"
COUNT=$(docker exec cf-postgres-local psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema='content_factory';" || echo "0")
if [[ "$COUNT" -lt 9 ]]; then
    echo "${RED}❌ schema 部署不完整（只有 $COUNT 张表，期望 9+）${NC}"
    echo "  查看日志: docker logs cf-postgres-local | tail -50"
    exit 1
fi
echo "${GRN}  ✅ schema 已部署，${COUNT} 张表${NC}"

# ---------- step 7: 验证 enum 已扩 ----------
echo "${YLW}▶ 验证 enum 扩展...${NC}"
ENUM_OK=$(docker exec cf-postgres-local psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT (enum_range(NULL::run_status)::text[]) @> ARRAY['partial']::text[] AND (enum_range(NULL::candidate_status)::text[]) @> ARRAY['pending_review','failed']::text[];")
if [[ "$ENUM_OK" != "t" ]]; then
    echo "${RED}❌ enum 没扩到位${NC}"
    exit 1
fi
echo "${GRN}  ✅ run_status / candidate_status enum 都扩好了${NC}"

# ---------- step 8: 等 N8N ready ----------
echo "${YLW}▶ 等 N8N ready（最长 90 秒）...${NC}"
for i in $(seq 1 90); do
    if curl -sf http://localhost:5678/healthz >/dev/null 2>&1; then
        echo "${GRN}  ✅ N8N ready (${i}s)${NC}"
        break
    fi
    sleep 1
done

# ---------- 完工 ----------
cat <<EOF

${GRN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}
${GRN}✅ 本地栈起完了${NC}

  N8N 编辑器:   http://localhost:5678
  Postgres:    localhost:55432  user=$POSTGRES_USER  db=$POSTGRES_DB
  Redis:       localhost:56379

下一步：
  1. 浏览器打开 http://localhost:5678
  2. 注册第一个 owner 账号
  3. Credentials → 建 6 个凭据（ID 严格匹配 DEMO-RUNBOOK §1.3 表格）
  4. Workflows → Import from File →
       n8n/image-workflow.json
       n8n/video-workflow.json
  5. 两个 workflow 都 Activate
  6. 看一下 N8N OSS 节点：本地 demo 没起 OSS，把这些节点 Deactivate
     （或者 Continue On Fail 也行，反正不挡演示流程）

测试触发：
  curl -X POST http://localhost:5678/webhook/trigger/image \\
    -H "Content-Type: application/json" \\
    -d '{"task_id":"<seed 出来的 task uuid>"}'

  从 PG 查 task uuid:
  docker exec cf-postgres-local psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \\
    -c "SELECT id, pipeline, status FROM tasks LIMIT 5;"

停服：
  docker compose -f docker-compose.local.yml --env-file .env.local down
彻底清空（包括数据）：
  docker compose -f docker-compose.local.yml --env-file .env.local down -v

${GRN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}

EOF
