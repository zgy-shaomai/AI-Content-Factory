#!/usr/bin/env bash
# 真 Postgres 端到端冒烟测试。
# 前提：Docker Desktop 已开（看右下角小鲸鱼图标）。
# 用途：起一个临时 postgres:16-alpine，跑完整 schema，逐条执行 N8N workflow 里的所有 SQL，
#       验证不只是语法对、列名对、enum 值对、JOIN 走得通。
# 跑完自动清理容器。
#
# 用法：
#   bash schemas/smoke-test.sh
#
# 期望输出：所有 query EXPLAIN 不报错 → ✅。任意一条报错 → ❌ 并 dump 错误。

set -euo pipefail

CONTAINER_NAME="cf-smoke-pg-$$"
PG_PASSWORD="smoke_test_$$"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
export CONTAINER_NAME ROOT_DIR

cleanup() {
    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "▶ 起临时 Postgres 容器 ($CONTAINER_NAME)..."
docker run -d --rm --name "$CONTAINER_NAME" \
    -e POSTGRES_PASSWORD="$PG_PASSWORD" \
    -e POSTGRES_DB=content_factory \
    postgres:16-alpine >/dev/null

echo "▶ 等 Postgres ready..."
for i in $(seq 1 30); do
    if docker exec "$CONTAINER_NAME" pg_isready -U postgres >/dev/null 2>&1; then
        echo "  ready (waited ${i}s)"
        break
    fi
    sleep 1
done

echo "▶ 部署 schema..."
docker exec -i "$CONTAINER_NAME" psql -U postgres -d content_factory -v ON_ERROR_STOP=1 \
    < "$SCRIPT_DIR/postgres-init.sql" 2>&1 | tail -20

echo "▶ 验证 enum 已扩..."
docker exec "$CONTAINER_NAME" psql -U postgres -d content_factory -t -c "
    SELECT 'run_status: ' || array_to_string(enum_range(NULL::run_status)::text[], ',');
    SELECT 'candidate_status: ' || array_to_string(enum_range(NULL::candidate_status)::text[], ',');
"

echo "▶ 抽 N8N workflow query 逐条 EXPLAIN..."
python3 - <<'PYEOF'
import json, subprocess, sys
from pathlib import Path
import os

ROOT = Path(os.environ["ROOT_DIR"])
container = os.environ["CONTAINER_NAME"]

queries = []
for wf in ("image-workflow.json", "video-workflow.json"):
    obj = json.loads((ROOT / "n8n" / wf).read_text(encoding="utf-8"))
    def walk(n):
        if isinstance(n, dict):
            for k, v in n.items():
                if k == "query" and isinstance(v, str):
                    queries.append((wf, v))
                walk(v)
        elif isinstance(n, list):
            for v in n: walk(v)
    walk(obj)

# 用 PREPARE + EXPLAIN 验证：让 PG 解析+绑定参数+做 plan，但不执行
fails = 0
for i, (wf, q) in enumerate(queries, 1):
    # PREPARE 需要参数类型注解。我们用一个 trick：包成 EXPLAIN 子句 + 假参数
    n_params = max([int(x) for x in __import__("re").findall(r"\$(\d+)", q)] or [0])
    if n_params == 0:
        prep = f"EXPLAIN {q.rstrip(';')}"
    else:
        # 用 generic types 让 PG 推断
        types = ",".join(["unknown"] * n_params)
        prep = f"PREPARE p_{i} ({types}) AS {q.rstrip(';')}"
    full = prep + ";"
    r = subprocess.run(
        ["docker", "exec", "-i", container, "psql", "-U", "postgres", "-d", "content_factory",
         "-v", "ON_ERROR_STOP=1", "-c", full],
        capture_output=True, text=True
    )
    if r.returncode == 0:
        print(f"  ✅ {wf} Q{i}")
    else:
        fails += 1
        print(f"  ❌ {wf} Q{i}")
        print("     " + r.stderr.strip().replace("\n", "\n     ")[:500])

print()
print(f"总计 {len(queries)} 条，通过 {len(queries)-fails}，失败 {fails}")
sys.exit(0 if fails == 0 else 1)
PYEOF

echo ""
echo "✅ 全部通过。"
