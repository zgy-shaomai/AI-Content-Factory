#!/usr/bin/env bash
# =============================================================================
# 备份素材生成器：演示前 1 小时跑一次，万一现场 API 翻车就用这堆
# =============================================================================
# 产物：
#   _demo_seed/
#     ├── images/
#     │    ├── 01-studio-front.png      （白底正面）
#     │    ├── 02-studio-side.png       （白底侧面）
#     │    ├── 03-studio-back.png       （白底背面）
#     │    ├── 04-fabric-macro.png      （面料特写）
#     │    ├── 05-zipper-action.png     （拉链开合）
#     │    ├── 06-logo-closeup.png      （Logo 特写）
#     │    ├── 07-yoga-studio.png       （瑜伽馆）
#     │    ├── 08-gym-training.png      （健身房）
#     │    ├── 09-park-running.png      （跑步公园）
#     │    ├── 10-mountain-outdoor.png  （户外山林）
#     │    └── 11-beach-coast.png       （海边沙滩）
#     ├── videos/
#     │    └── yn-bra-001-12s.mp4
#     └── manifest.json                 （所有素材的 prompt + URL + 时间戳）
# =============================================================================
set -uo pipefail

RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; NC=$'\033[0m'

# 兜底从 deploy/.env.local 读
if [[ -f "deploy/.env.local" ]] && [[ -z "${IMAGE_API_KEY:-}" || -z "${VIDEO_API_KEY:-}" ]]; then
    set -o allexport
    # shellcheck source=/dev/null
    source deploy/.env.local
    set +o allexport
fi

IMAGE_API_KEY="${IMAGE_API_KEY:-${MEDIA_API_KEY:-${ARK_API_KEY:-}}}"
VIDEO_API_KEY="${VIDEO_API_KEY:-${MEDIA_API_KEY:-${ARK_API_KEY:-}}}"
IMAGE_BASE_URL="${IMAGE_BASE_URL:-${MEDIA_BASE_URL:-${ARK_ENDPOINT:-https://ark.cn-beijing.volces.com/api/v3}}}"
VIDEO_BASE_URL="${VIDEO_BASE_URL:-${MEDIA_BASE_URL:-${ARK_ENDPOINT:-https://ark.cn-beijing.volces.com/api/v3}}}"
IMAGE_MODEL="${IMAGE_MODEL:-${ARK_IMAGE_MODEL:-doubao-seedream-4-0-250828}}"
VIDEO_MODEL="${VIDEO_MODEL:-${ARK_VIDEO_MODEL:-doubao-seedance-1-0-pro-250528}}"
export IMAGE_MODEL VIDEO_MODEL

if [[ -z "${IMAGE_API_KEY:-}" ]] || [[ "$IMAGE_API_KEY" == CHANGE_ME* ]]; then
    echo "${RED}❌ IMAGE_API_KEY/MEDIA_API_KEY 没设${NC}"
    exit 1
fi
if [[ -z "${VIDEO_API_KEY:-}" ]] || [[ "$VIDEO_API_KEY" == CHANGE_ME* ]]; then
    echo "${RED}❌ VIDEO_API_KEY/MEDIA_API_KEY 没设${NC}"
    exit 1
fi

mkdir -p _demo_seed/images _demo_seed/videos

# ---------- 11 张图的 prompt（YN-BRA-001 实战版，从 prompts/image/03/04 抽）----------
declare -a IMAGE_PROMPTS=(
"01-studio-front|studio shot of a 28-year-old asian woman wearing matte black sports bra with chrome front zipper on minimalist light gray background, frontal view, eye level, soft diffused natural light from camera left, breathable mesh fabric texture visible at sides, sweat-wicking nylon-spandex blend with subtle matte sheen, preserve original tonal logo placement on left chest 6cm below collarbone 3cm wide, neutral undertone, no color shift to navy blue or warm brown, professional fashion photography, ultra detailed, 1024x1024"
"02-studio-side|studio profile shot of same 28-year-old asian woman wearing matte black sports bra with front zipper, side view facing camera-right, minimalist light gray seamless background, soft natural light from front-left at 45 degrees, breathable mesh side panels visible, high elasticity fabric showing natural drape, sweat-wicking nylon-spandex blend, brand color matte black with neutral undertone, professional fashion editorial style, sharp focus on fabric texture, 1024x1024"
"03-studio-back|studio back shot of same 28-year-old asian woman wearing matte black sports bra, viewed from behind, minimalist light gray background, even soft lighting, racerback design clearly visible, breathable mesh fabric across upper back, high-elasticity strap support visible, no logo on back, matte black brand color, ultra detailed editorial photography, 1024x1024"
"04-fabric-macro|extreme close-up macro photograph of breathable mesh fabric surface on a matte black sports bra, sweat-wicking nylon-spandex blend showing fine weave pattern, subtle matte sheen, fiber detail at 1:1 magnification, soft directional lighting from upper-left to reveal texture depth, neutral undertone, professional product photography, no model, white seamless background blur, 1024x1024"
"05-zipper-action|cinematic close-up of asian woman's hand pulling chrome front zipper of matte black sports bra, fingers gripping zipper pull with subtle motion blur on the pull, natural skin tone, soft directional light from window left, breathable mesh fabric texture visible around zipper area, preserve logo placement on left chest just below frame, lifestyle editorial style, shallow depth of field, 1024x1024"
"06-logo-closeup|extreme close-up of branded logo on matte black sports bra fabric on left chest area, tonal embroidery or heat-transfer print, breathable mesh fabric texture surrounding logo, sweat-wicking nylon-spandex blend, soft natural lighting from top-left to highlight logo subtle dimensionality, no human face in frame, neutral matte black color with no color shift, professional product detail photography, 1024x1024"
"07-yoga-studio|wide lifestyle shot of same 28-year-old asian woman in matte black sports bra and matching black yoga pants doing warrior pose in a sun-drenched yoga studio at golden morning hour, wooden floor, large arched window with soft warm sunlight streaming in, minimalist scandinavian decor, plants in background, breathable mesh fabric visible, professional photography in editorial fashion style, ultra detailed, 1024x1024"
"08-gym-training|dynamic action shot of same asian woman wearing matte black sports bra performing battle rope exercises in modern minimalist gym with concrete floors, controlled motion blur on the ropes, focused expression, sweat sheen on skin showing effort, dramatic side lighting from large industrial windows, breathable mesh fabric and matte sheen visible, sweat-wicking performance shown, editorial sports photography, 1024x1024"
"09-park-running|lifestyle shot of same asian woman jogging through a green urban park at golden hour, wearing matte black sports bra and running shorts, motion blur in legs and trees, focused forward gaze, warm late afternoon sunlight casting long shadows, breathable mesh fabric visible, sweat-wicking performance demonstrated, athletic editorial style with cinematic color grading, 1024x1024"
"10-mountain-outdoor|cinematic outdoor shot of same asian woman in matte black sports bra and hiking shorts standing on a rocky mountain ridge with sweeping vista in background, dramatic golden hour lighting, slight wind in hair, confident pose looking toward distant peaks, breathable mesh fabric subtly visible, lifestyle adventure photography editorial, ultra detailed, 1024x1024"
"11-beach-coast|coastal lifestyle shot of same asian woman in matte black sports bra walking along wet sand at sunset, ocean waves and distant horizon, warm orange-pink sky, footprints in sand behind her, soft sea breeze in hair, breathable mesh fabric visible, peaceful confident expression, fashion editorial photography, ultra detailed, 1024x1024"
)

echo "${YLW}━━━━━━━━ 1/2: Seedream 4.0 出 11 张图 ━━━━━━━━${NC}"
MANIFEST="["
FAIL_IMG=0
for i in "${!IMAGE_PROMPTS[@]}"; do
    line="${IMAGE_PROMPTS[$i]}"
    name="${line%%|*}"
    prompt="${line#*|}"
    out="_demo_seed/images/${name}.png"

    echo -ne "${YLW}  [$((i+1))/11] ${name}...${NC} "

    RESP=$(curl -sS -X POST "${IMAGE_BASE_URL%/}/images/generations" \
        -H "Authorization: Bearer ${IMAGE_API_KEY}" \
        -H "Content-Type: application/json" \
        -d "$(python3 -c "import json,sys,os; print(json.dumps({'model':os.environ.get('IMAGE_MODEL'),'prompt':sys.argv[1],'size':'1024x1024','watermark':False}))" "$prompt")" 2>&1)

    URL=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',[{}])[0].get('url',''))" 2>/dev/null || echo "")

    if [[ -n "$URL" && "$URL" == http* ]]; then
        if curl -sSL "$URL" -o "$out" --max-time 30; then
            SIZE=$(wc -c < "$out")
            echo "${GRN}✅ ${SIZE}B${NC}"
            MANIFEST+="{\"name\":\"$name\",\"prompt\":$(echo "$prompt" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip()))"),\"url\":\"$URL\",\"file\":\"images/${name}.png\",\"size\":$SIZE},"
        else
            echo "${RED}❌ 下载失败${NC}"
            ((FAIL_IMG++))
        fi
    else
        echo "${RED}❌ 出图失败${NC}"
        echo "  $(echo "$RESP" | head -c 200)"
        ((FAIL_IMG++))
    fi
done

# ---------- 视频 ----------
echo
echo "${YLW}━━━━━━━━ 2/2: Seedance 2.0 出 1 条 12 秒视频 ━━━━━━━━${NC}"
echo "${YLW}  ⓘ 视频通常要 90-180 秒生成，请耐心等${NC}"

VIDEO_PROMPT='4-shot edit (3 seconds each) of a 28-year-old asian woman wearing matte black sports bra with front zipper. Shot 1: she pulls back her hair confidently, soft window light. Shot 2: close-up of her hand pulling the chrome zipper down 3cm to reveal breathable mesh inner. Shot 3: she does jumping jacks in slow motion at low angle, fabric showing high elasticity, no breast bounce. Shot 4: she faces camera, zips up, smiles slightly, end frame on a clean centered product reveal. Cinematic professional fashion photography aesthetic. Voiceover: "试过才懂. 前拉链, 三秒上身. 跑跳不晃, 一秒速干. 黑色M码, 主页下单." --resolution 720p --ratio 9:16 --duration 12 --fps 24 --watermark false'

VR=$(curl -sS -X POST "${VIDEO_BASE_URL%/}/contents/generations/tasks" \
    -H "Authorization: Bearer ${VIDEO_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "$(python3 -c "import json,sys,os; print(json.dumps({'model':os.environ.get('VIDEO_MODEL'),'content':[{'type':'text','text':sys.argv[1]}]}))" "$VIDEO_PROMPT")" 2>&1)

VTASK=$(echo "$VR" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id',''))" 2>/dev/null || echo "")

if [[ -z "$VTASK" ]]; then
    echo "${RED}  ❌ 视频任务下单失败:${NC} $(echo "$VR" | head -c 200)"
else
    echo "${GRN}  ✅ 任务已下单:${NC} $VTASK"
    echo -ne "${YLW}  轮询任务状态...${NC}"
    for i in $(seq 1 60); do
        sleep 5
        VR2=$(curl -sS -H "Authorization: Bearer ${VIDEO_API_KEY}" \
            "${VIDEO_BASE_URL%/}/contents/generations/tasks/$VTASK" 2>&1)
        ST=$(echo "$VR2" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null || echo "")
        echo -ne "."
        if [[ "$ST" == "succeeded" ]]; then
            VURL=$(echo "$VR2" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('content',{}).get('video_url','') or d.get('output',{}).get('video_url',''))" 2>/dev/null || echo "")
            if [[ -n "$VURL" ]]; then
                echo
                echo -ne "${YLW}  下载视频...${NC} "
                if curl -sSL "$VURL" -o "_demo_seed/videos/yn-bra-001-12s.mp4" --max-time 120; then
                    SZ=$(wc -c < "_demo_seed/videos/yn-bra-001-12s.mp4")
                    echo "${GRN}✅ ${SZ}B${NC}"
                    MANIFEST+="{\"name\":\"yn-bra-001-12s\",\"task_id\":\"$VTASK\",\"url\":\"$VURL\",\"file\":\"videos/yn-bra-001-12s.mp4\",\"size\":$SZ}"
                fi
            fi
            break
        elif [[ "$ST" == "failed" ]]; then
            echo
            echo "${RED}  ❌ 视频生成失败${NC}"
            break
        fi
    done
fi

# ---------- manifest ----------
MANIFEST="${MANIFEST%,}"
MANIFEST+="]"
echo "$MANIFEST" | python3 -c "import sys,json; print(json.dumps(json.loads(sys.stdin.read()), ensure_ascii=False, indent=2))" > _demo_seed/manifest.json 2>/dev/null || echo "$MANIFEST" > _demo_seed/manifest.json

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
IMG_OK=$(ls _demo_seed/images/*.png 2>/dev/null | wc -l)
VID_OK=$(ls _demo_seed/videos/*.mp4 2>/dev/null | wc -l)
echo "${GRN}图片: ${IMG_OK}/11${NC}  ${GRN}视频: ${VID_OK}/1${NC}"
echo "manifest: _demo_seed/manifest.json"
[[ $IMG_OK -ge 8 && $VID_OK -ge 1 ]] && echo "${GRN}✅ 备份素材足够撑过演示翻车${NC}" || echo "${RED}⚠️  备份不够，建议重跑${NC}"
