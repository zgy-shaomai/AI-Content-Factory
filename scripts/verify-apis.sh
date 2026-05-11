#!/usr/bin/env bash
# =============================================================================
# 演示前 API 验证脚本：3 条真实 API 各 curl 一次，验证 key 有效 + 服务可达
# =============================================================================
# 用法：
#   先 export 3 个环境变量，再跑：
#
#   export IMAGE_API_KEY="..."        # 图片 provider key（可 fallback ARK_API_KEY）
#   export VIDEO_API_KEY="..."        # 视频 provider key（可 fallback ARK_API_KEY）
#   export LLM_API_KEY="sk-..."       # OpenAI-compatible LLM provider key（可 fallback NEWAPI_KEY）
#   bash scripts/verify-apis.sh
# =============================================================================
set -uo pipefail

RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; NC=$'\033[0m'
PASS=0; FAIL=0

# 兜底从 deploy/.env.local 读
if [[ -f "deploy/.env.local" ]] && [[ -z "${IMAGE_API_KEY:-}" || -z "${VIDEO_API_KEY:-}" || -z "${LLM_API_KEY:-}" ]]; then
    set -o allexport
    # shellcheck source=/dev/null
    source deploy/.env.local
    set +o allexport
fi

IMAGE_API_KEY="${IMAGE_API_KEY:-${MEDIA_API_KEY:-${ARK_API_KEY:-}}}"
VIDEO_API_KEY="${VIDEO_API_KEY:-${MEDIA_API_KEY:-${ARK_API_KEY:-}}}"
LLM_API_KEY="${LLM_API_KEY:-${NEWAPI_KEY:-}}"
IMAGE_BASE_URL="${IMAGE_BASE_URL:-${MEDIA_BASE_URL:-${ARK_ENDPOINT:-https://ark.cn-beijing.volces.com/api/v3}}}"
VIDEO_BASE_URL="${VIDEO_BASE_URL:-${MEDIA_BASE_URL:-${ARK_ENDPOINT:-https://ark.cn-beijing.volces.com/api/v3}}}"
LLM_BASE_URL="${LLM_BASE_URL:-${NEWAPI_BASE_URL:-https://5dock.com/v1}}"
IMAGE_MODEL="${IMAGE_MODEL:-${ARK_IMAGE_MODEL:-doubao-seedream-4-0-250828}}"
VIDEO_MODEL="${VIDEO_MODEL:-${ARK_VIDEO_MODEL:-doubao-seedance-1-0-pro-250528}}"
LLM_MODEL="${LLM_MODEL:-claude-sonnet-4-5-20250929}"

if [[ -z "${IMAGE_API_KEY:-}" ]] || [[ "$IMAGE_API_KEY" == CHANGE_ME* ]]; then
    echo "${RED}❌ IMAGE_API_KEY/MEDIA_API_KEY 没设。先 export 或填 deploy/.env.local${NC}"
    exit 1
fi
if [[ -z "${VIDEO_API_KEY:-}" ]] || [[ "$VIDEO_API_KEY" == CHANGE_ME* ]]; then
    echo "${RED}❌ VIDEO_API_KEY/MEDIA_API_KEY 没设${NC}"
    exit 1
fi
if [[ -z "${LLM_API_KEY:-}" ]] || [[ "$LLM_API_KEY" == CHANGE_ME* ]]; then
    echo "${RED}❌ LLM_API_KEY/NEWAPI_KEY 没设${NC}"
    exit 1
fi

# -----------------------------------------------------------------------------
# 1. Seedream 4.0 - 出图
# -----------------------------------------------------------------------------
echo "${YLW}▶ [1/3] Seedream 4.0 出图测试...${NC}"
SD_RESP=$(curl -sS --connect-timeout 10 --max-time 60 -X POST "${IMAGE_BASE_URL%/}/images/generations" \
    -H "Authorization: Bearer ${IMAGE_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{
        \"model\": \"${IMAGE_MODEL}\",
        \"prompt\": \"studio shot of a black sports bra with front zipper, on minimalist gray background, soft natural light, fashion photography, ultra detailed\",
        \"size\": \"1024x1024\",
        \"watermark\": false
    }" 2>&1)
SD_URL=$(echo "$SD_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',[{}])[0].get('url',''))" 2>/dev/null || echo "")
if [[ -n "$SD_URL" && "$SD_URL" == http* ]]; then
    echo "${GRN}  ✅ 出图成功:${NC} $SD_URL"
    ((PASS++))
else
    echo "${RED}  ❌ 出图失败${NC}"
    echo "  Response: $SD_RESP" | head -c 500
    echo
    ((FAIL++))
fi

# -----------------------------------------------------------------------------
# 2. Seedance 2.0 - 出视频任务（不等任务跑完，只验证能下单）
# -----------------------------------------------------------------------------
echo "${YLW}▶ [2/3] Seedance 2.0 视频任务下单测试...${NC}"
SD2_RESP=$(curl -sS --connect-timeout 10 --max-time 60 -X POST "${VIDEO_BASE_URL%/}/contents/generations/tasks" \
    -H "Authorization: Bearer ${VIDEO_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{
        \"model\": \"${VIDEO_MODEL}\",
        \"content\": [
            {\"type\":\"text\",\"text\":\"a woman jogging in a green park at golden hour, wearing black sports bra, cinematic shot --resolution 720p --duration 5 --ratio 9:16\"}
        ]
    }" 2>&1)
SD2_TASKID=$(echo "$SD2_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id',''))" 2>/dev/null || echo "")
if [[ -n "$SD2_TASKID" ]]; then
    echo "${GRN}  ✅ 视频任务已下单:${NC} task_id=$SD2_TASKID"
    echo "${YLW}  ⓘ 实际视频生成需要 1-3 分钟，这里只验证下单接口通${NC}"
    ((PASS++))
else
    echo "${RED}  ❌ 视频任务下单失败${NC}"
    echo "  Response: $SD2_RESP" | head -c 500
    echo
    ((FAIL++))
fi

# -----------------------------------------------------------------------------
# 3. LLM provider - chat/completions
# -----------------------------------------------------------------------------
echo "${YLW}▶ [3/3] LLM provider chat/completions 测试...${NC}"
CL_RESP=$(curl -sS --connect-timeout 10 --max-time 60 "${LLM_BASE_URL%/}/chat/completions" \
    -H "Authorization: Bearer ${LLM_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{
        \"model\": \"${LLM_MODEL}\",
        \"messages\": [{\"role\":\"user\",\"content\":\"reply with exactly the word: OK\"}],
        \"max_tokens\": 10
    }" 2>&1)
CL_TEXT=$(echo "$CL_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('choices',[{}])[0].get('message',{}).get('content',''))" 2>/dev/null || echo "")
if [[ -n "$CL_TEXT" ]]; then
    echo "${GRN}  ✅ Claude 响应:${NC} $CL_TEXT"
    ((PASS++))
else
    echo "${RED}  ❌ Claude 调用失败${NC}"
    echo "  Response: $CL_RESP" | head -c 500
    echo
    ((FAIL++))
fi

# -----------------------------------------------------------------------------
# 收尾
# -----------------------------------------------------------------------------
echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ $FAIL -eq 0 ]]; then
    echo "${GRN}✅ 全部 3/3 通过。可以正式演示。${NC}"
    exit 0
else
    echo "${RED}❌ 失败 ${FAIL}/3，演示前必须修。${NC}"
    echo "${YLW}  Seedream/Seedance 失败 → 查火山方舟控制台 API Key 是否启用、配额够不够，以及 Seedance 模型服务是否已开通${NC}"
    echo "${YLW}  LLM 失败 → 查 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 是否匹配当前 provider${NC}"
    exit 1
fi
