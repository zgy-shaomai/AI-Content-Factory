#!/usr/bin/env bash
# =============================================================================
# 端到端 dry-run 脚本：演示前 30 分钟跑一次，确认全链路通
# =============================================================================
# 做什么：
#   1. 检查 docker 容器在跑（postgres + n8n）
#   2. 从 PG 自动捞一个 pending 的 image 任务（或用传入的 task_id）
#   3. 记录基线：candidates 数、generation_runs 数
#   4. curl 触发 image webhook
#   5. 每 5 秒轮询一次，看 candidates 表新增了几行
#   6. 最多等 8 分钟。期望：11 个新 candidate
#   7. 报告：耗时、产出、抽 1 个 candidate URL 给你点开看
#
# 用法：
#   bash scripts/dry-run.sh              # 自动挑一个任务
#   bash scripts/dry-run.sh <task_uuid>  # 指定任务
# =============================================================================
set -uo pipefail

RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; CYN=$'\033[36m'; NC=$'\033[0m'

PG="docker exec -i cf-postgres-local psql -U postgres -d content_factory -tAc"
WEBHOOK="http://localhost:5678/webhook/trigger/image"
EXPECTED_CANDIDATES=11
TIMEOUT_SEC=480   # 8 分钟

# ---------- 0. preflight ----------
echo "${CYN}━━━━━━━━ 0. Preflight 检查 ━━━━━━━━${NC}"

if ! docker ps --format '{{.Names}}' | grep -q '^cf-postgres-local$'; then
    echo "${RED}❌ cf-postgres-local 容器没在跑${NC}"
    echo "   先 bash deploy/bootstrap-local.sh"
    exit 1
fi
echo "${GRN}  ✅ Postgres 容器在跑${NC}"

if ! docker ps --format '{{.Names}}' | grep -q '^cf-n8n-local$'; then
    echo "${RED}❌ cf-n8n-local 容器没在跑${NC}"
    exit 1
fi
echo "${GRN}  ✅ N8N 容器在跑${NC}"

if ! curl -sf http://localhost:5678/healthz >/dev/null 2>&1; then
    echo "${RED}❌ N8N healthcheck 没通${NC}"
    echo "   docker logs cf-n8n-local --tail 30"
    exit 1
fi
echo "${GRN}  ✅ N8N healthcheck OK${NC}"

# ---------- 1. 选 task ----------
echo
echo "${CYN}━━━━━━━━ 1. 选定 task ━━━━━━━━${NC}"
TASK_ID="${1:-}"
if [[ -z "$TASK_ID" ]]; then
    TASK_ID=$($PG "SELECT id FROM tasks WHERE pipeline='image' ORDER BY created_at LIMIT 1;" 2>/dev/null | tr -d '[:space:]')
    if [[ -z "$TASK_ID" ]]; then
        echo "${RED}❌ PG 里没有 image 类型 task。检查 schemas/postgres-init.sql 的 seed 数据是否部署${NC}"
        exit 1
    fi
    echo "${YLW}  没传 task_id，自动挑了:${NC} $TASK_ID"
else
    EXISTS=$($PG "SELECT count(*) FROM tasks WHERE id = '$TASK_ID'::uuid;" 2>/dev/null | tr -d '[:space:]')
    if [[ "$EXISTS" != "1" ]]; then
        echo "${RED}❌ task_id 不存在: $TASK_ID${NC}"
        exit 1
    fi
    echo "${GRN}  ✅ 用指定的 task:${NC} $TASK_ID"
fi

TASK_INFO=$($PG "SELECT title || ' | sku=' || (SELECT sku FROM products WHERE id = t.product_id) || ' | status=' || status FROM tasks t WHERE id = '$TASK_ID'::uuid;")
echo "${CYN}  task 详情:${NC} $TASK_INFO"

# ---------- 2. 基线 ----------
echo
echo "${CYN}━━━━━━━━ 2. 记录基线 ━━━━━━━━${NC}"
BASELINE_CANDIDATES=$($PG "SELECT count(*) FROM candidates WHERE task_id = '$TASK_ID'::uuid;" | tr -d '[:space:]')
BASELINE_RUNS=$($PG "SELECT count(*) FROM generation_runs WHERE task_id = '$TASK_ID'::uuid;" | tr -d '[:space:]')
echo "  candidates 基线: $BASELINE_CANDIDATES"
echo "  generation_runs 基线: $BASELINE_RUNS"

# ---------- 3. 触发 ----------
echo
echo "${CYN}━━━━━━━━ 3. 触发 image webhook ━━━━━━━━${NC}"
START_EPOCH=$(date +%s)
START_TS=$(date +%H:%M:%S)
echo "  POST $WEBHOOK"
echo "  body: {\"task_id\":\"$TASK_ID\"}"
echo "  起始时间: $START_TS"

HTTP_RESP=$(curl -sS -w "\n%{http_code}" -X POST "$WEBHOOK" \
    -H "Content-Type: application/json" \
    -d "{\"task_id\":\"$TASK_ID\"}" 2>&1 || echo $'\n000')
HTTP_BODY=$(echo "$HTTP_RESP" | head -n -1)
HTTP_CODE=$(echo "$HTTP_RESP" | tail -n 1)

if [[ "$HTTP_CODE" =~ ^2 ]]; then
    echo "${GRN}  ✅ webhook 返回 $HTTP_CODE${NC}"
elif [[ "$HTTP_CODE" == "404" ]]; then
    echo "${RED}❌ webhook 404 → workflow 没 Activate。${NC}"
    echo "   去 N8N (http://localhost:5678) 把 image-workflow 右上角开关打开。"
    exit 1
else
    echo "${RED}❌ webhook 返回 $HTTP_CODE${NC}"
    echo "  body: $HTTP_BODY"
    exit 1
fi

# ---------- 4. 轮询 ----------
echo
echo "${CYN}━━━━━━━━ 4. 轮询进度（最多 ${TIMEOUT_SEC}s）━━━━━━━━${NC}"
LAST_CAND=$BASELINE_CANDIDATES
LAST_RUN_STATUS=""
SUCCESS=0
while :; do
    NOW=$(date +%s)
    ELAPSED=$((NOW - START_EPOCH))
    if [[ $ELAPSED -gt $TIMEOUT_SEC ]]; then
        echo "${RED}  ❌ 超时 ${TIMEOUT_SEC}s${NC}"
        break
    fi

    NEW_CAND=$($PG "SELECT count(*) FROM candidates WHERE task_id = '$TASK_ID'::uuid;" | tr -d '[:space:]')
    DELTA=$((NEW_CAND - BASELINE_CANDIDATES))
    LATEST_RUN=$($PG "SELECT status FROM generation_runs WHERE task_id = '$TASK_ID'::uuid ORDER BY started_at DESC NULLS LAST LIMIT 1;" 2>/dev/null | tr -d '[:space:]')

    # 输出有变化才打
    if [[ "$NEW_CAND" != "$LAST_CAND" || "$LATEST_RUN" != "$LAST_RUN_STATUS" ]]; then
        printf "  [%3ds] candidates +%-2d (共 %d)  | latest run: %s\n" \
            "$ELAPSED" "$DELTA" "$NEW_CAND" "${LATEST_RUN:-?}"
        LAST_CAND=$NEW_CAND
        LAST_RUN_STATUS="$LATEST_RUN"
    fi

    # 成功条件：新增达到期望 + 最近一个 run 成功/部分成功
    if [[ $DELTA -ge $EXPECTED_CANDIDATES ]] && [[ "$LATEST_RUN" == "succeeded" || "$LATEST_RUN" == "partial" ]]; then
        SUCCESS=1
        break
    fi
    # 失败条件：run 失败
    if [[ "$LATEST_RUN" == "failed" ]]; then
        echo "${RED}  ❌ generation_runs 显示 failed${NC}"
        break
    fi

    sleep 5
done

ELAPSED_TOTAL=$(($(date +%s) - START_EPOCH))

# ---------- 5. 验收 ----------
echo
echo "${CYN}━━━━━━━━ 5. 验收报告 ━━━━━━━━${NC}"

FINAL_CAND=$($PG "SELECT count(*) FROM candidates WHERE task_id = '$TASK_ID'::uuid;" | tr -d '[:space:]')
DELTA_CAND=$((FINAL_CAND - BASELINE_CANDIDATES))
FINAL_RUNS=$($PG "SELECT count(*) FROM generation_runs WHERE task_id = '$TASK_ID'::uuid;" | tr -d '[:space:]')
DELTA_RUNS=$((FINAL_RUNS - BASELINE_RUNS))

# 检查内容质量
NULL_OSS=$($PG "SELECT count(*) FROM candidates WHERE task_id = '$TASK_ID'::uuid AND (oss_url IS NULL OR oss_url = '');" | tr -d '[:space:]')
NULL_PROMPT=$($PG "SELECT count(*) FROM candidates WHERE task_id = '$TASK_ID'::uuid AND (prompt_snapshot IS NULL OR prompt_snapshot = '');" | tr -d '[:space:]')

echo "  耗时: ${ELAPSED_TOTAL}s"
echo "  candidates 新增: $DELTA_CAND（期望 ≥ $EXPECTED_CANDIDATES）"
echo "  generation_runs 新增: $DELTA_RUNS（期望 ≥ 1）"
echo "  candidate.oss_url 空值数: $NULL_OSS（期望 0）"
echo "  candidate.prompt_snapshot 空值数: $NULL_PROMPT（期望 0）"

# 列最近 3 个 candidate
echo
echo "  最近 3 个 candidate（点 oss_url 看效果）："
docker exec -i cf-postgres-local psql -U postgres -d content_factory -c \
    "SELECT substring(id::text,1,8) AS id, media_type, status, substring(oss_url,1,60) AS url, sequence_no, created_at::time AS t FROM candidates WHERE task_id = '$TASK_ID'::uuid ORDER BY created_at DESC LIMIT 3;"

# generation_runs 状态汇总
echo "  generation_runs 状态汇总："
docker exec -i cf-postgres-local psql -U postgres -d content_factory -c \
    "SELECT status, count(*), avg(coalesce(duration_ms,0))::int AS avg_dur_ms, sum(coalesce(cost_cny,0))::numeric(10,2) AS total_cny FROM generation_runs WHERE task_id = '$TASK_ID'::uuid GROUP BY status;"

# 飞书侧抽查（如果 FEISHU_APP_ID 设了才看）
if [[ -n "${FEISHU_APP_ID:-}" ]] && [[ "$FEISHU_APP_ID" != "" ]]; then
    echo "  飞书侧抽查: 候选审核表（feishu_record_id 非空数）"
    FEISHU_OK=$($PG "SELECT count(*) FROM candidates WHERE task_id = '$TASK_ID'::uuid AND feishu_record_id IS NOT NULL;" | tr -d '[:space:]')
    echo "    $FEISHU_OK / $DELTA_CAND（期望相等，不等说明飞书回写漏了）"
fi

# ---------- 6. 结论 ----------
echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ $SUCCESS -eq 1 ]] && [[ $NULL_OSS -eq 0 ]] && [[ $NULL_PROMPT -eq 0 ]]; then
    echo "${GRN}✅ 端到端通了。可以正式演示。${NC}"
    echo "   建议：现在打开 http://localhost:5678 看 image-workflow 画布的最近一次执行，确认所有节点都绿。"
    exit 0
else
    echo "${RED}❌ dry-run 有问题，演示前必须排查：${NC}"
    [[ $DELTA_CAND -lt $EXPECTED_CANDIDATES ]] && echo "   - candidates 新增不够（$DELTA_CAND < $EXPECTED_CANDIDATES）"
    [[ $NULL_OSS -gt 0 ]]    && echo "   - 有 $NULL_OSS 个 candidate 的 oss_url 是空（OSS 节点失败？演示走本地可以接受，关掉那个节点）"
    [[ $NULL_PROMPT -gt 0 ]] && echo "   - 有 $NULL_PROMPT 个 candidate 的 prompt_snapshot 是空"
    [[ "$LAST_RUN_STATUS" == "failed" ]] && echo "   - generation_runs 失败 → 看 N8N 画布上的红色节点"
    echo
    echo "   N8N 画布查执行历史: http://localhost:5678/executions"
    echo "   PG 查 generation_runs 错误: docker exec -it cf-postgres-local psql -U postgres -d content_factory \\"
    echo "     -c \"SELECT error_message FROM generation_runs WHERE task_id='$TASK_ID' ORDER BY started_at DESC LIMIT 1;\""
    exit 2
fi
