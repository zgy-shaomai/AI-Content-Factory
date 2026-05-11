"""
N8N 一键配置脚本（同事在新机器上跑）

功能：
1. 用 N8N API token 调 /api/v1/credentials 建 6 个 credential
2. 拉硬盘上的 workflow JSON，patch credential UUID + 模型名 + 必要字段
3. PUT 到 N8N
4. 激活 image-workflow

跑前先：
1. 浏览器进 http://localhost:5678 注册 owner
2. 头像 → Settings → n8n API → Create API key → 复制粘到下面 TOKEN
3. 可选：改 deploy/.env.local 填 LLM_API_KEY / IMAGE_API_KEY / VIDEO_API_KEY
"""
import json
import os
import sys
import urllib.request
import urllib.error
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(errors="replace")

# ============================================================
#  配置
# ============================================================
N8N_BASE = os.environ.get("N8N_BASE", "http://localhost:5678")
TOKEN = os.environ.get("N8N_API_TOKEN", "")  # 也可从命令行 --token 传

# 默认 token 占位 — 替换成你自己的
if len(sys.argv) > 1 and sys.argv[1].startswith("--token="):
    TOKEN = sys.argv[1].split("=", 1)[1]

if not TOKEN:
    print("❌ 缺 N8N API token")
    print("   方法 1: export N8N_API_TOKEN=eyJ...")
    print("   方法 2: python n8n_setup.py --token=eyJ...")
    print("   去哪拿: 浏览器 http://localhost:5678 → 头像 → Settings → n8n API → Create")
    sys.exit(1)

# 从 deploy/.env.local 读 secrets
def load_env():
    env_path = Path(__file__).parent.parent / "deploy" / ".env.local"
    if not env_path.is_file():
        print(f"❌ {env_path} 不存在，先 cp deploy/.env.local.example deploy/.env.local 并填值")
        sys.exit(1)
    out = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out

env = load_env()
ENV_LOCAL_PATH = Path(__file__).parent.parent / "deploy" / ".env.local"


def write_env_value(key, value):
    lines = ENV_LOCAL_PATH.read_text(encoding="utf-8").splitlines() if ENV_LOCAL_PATH.exists() else []
    found = False
    next_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            next_lines.append(f"{key}={value}")
            found = True
        else:
            next_lines.append(line)
    if not found:
        if next_lines and next_lines[-1].strip():
            next_lines.append("")
        next_lines.append(f"{key}={value}")
    ENV_LOCAL_PATH.write_text("\n".join(next_lines) + "\n", encoding="utf-8")

N8N_BASE = (os.environ.get("N8N_BASE") or env.get("N8N_BASE") or N8N_BASE).rstrip("/")
PG_PASSWORD = env.get("POSTGRES_PASSWORD", "")
PAC_PROFILE = env.get("PAC_PROFILE", "cn_ecommerce_default")
LLM_PROVIDER = env.get("LLM_PROVIDER", "5dock")
LLM_API_KEY = env.get("LLM_API_KEY") or env.get("NEWAPI_KEY", "")
LLM_BASE_URL = (env.get("LLM_BASE_URL") or env.get("NEWAPI_BASE_URL") or "https://5dock.com/v1").rstrip("/")
LLM_MODEL = env.get("LLM_MODEL", "claude-sonnet-4-5-20250929") or "claude-sonnet-4-5-20250929"
MEDIA_API_KEY = env.get("MEDIA_API_KEY", "")
MEDIA_BASE_URL = (env.get("MEDIA_BASE_URL") or "").rstrip("/")
IMAGE_PROVIDER = env.get("IMAGE_PROVIDER", "volcengine_ark")
IMAGE_API_KEY = env.get("IMAGE_API_KEY") or MEDIA_API_KEY or env.get("ARK_API_KEY", "")
IMAGE_BASE_URL = (env.get("IMAGE_BASE_URL") or MEDIA_BASE_URL or env.get("ARK_ENDPOINT") or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
IMAGE_MODEL = env.get("IMAGE_MODEL") or env.get("ARK_IMAGE_MODEL") or "doubao-seedream-4-0-250828"
VIDEO_PROVIDER = env.get("VIDEO_PROVIDER", "volcengine_ark")
VIDEO_API_KEY = env.get("VIDEO_API_KEY") or MEDIA_API_KEY or env.get("ARK_API_KEY", "")
VIDEO_BASE_URL = (env.get("VIDEO_BASE_URL") or MEDIA_BASE_URL or env.get("ARK_ENDPOINT") or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
VIDEO_MODEL = env.get("VIDEO_MODEL") or env.get("ARK_VIDEO_MODEL") or "doubao-seedance-1-0-pro-250528"
ASR_PROVIDER = env.get("ASR_PROVIDER", "volcengine")
ASR_API_KEY = env.get("ASR_API_KEY", "")

# Legacy aliases retained for old workflow expressions.
ARK_API_KEY = env.get("ARK_API_KEY") or IMAGE_API_KEY or VIDEO_API_KEY
NEWAPI_KEY = env.get("NEWAPI_KEY") or LLM_API_KEY
ARK_IMAGE_MODEL = IMAGE_MODEL
ARK_VIDEO_MODEL = VIDEO_MODEL

if not PG_PASSWORD:
    print("❌ deploy/.env.local 里 POSTGRES_PASSWORD 必须填")
    sys.exit(1)

missing_api_keys = [
    name for name, value in {
        "LLM_API_KEY": LLM_API_KEY,
        "IMAGE_API_KEY": IMAGE_API_KEY,
        "VIDEO_API_KEY": VIDEO_API_KEY,
    }.items() if not value
]
if missing_api_keys:
    print(f"⚠️  未配置 {', '.join(missing_api_keys)}：会为缺失 key 的新 credential 使用 placeholder。")
    print("   已存在的真实 credential 不会被 placeholder 覆盖；填 key 后重跑本脚本即可。")


def req(method, path, body=None):
    headers = {"X-N8N-API-KEY": TOKEN, "Content-Type": "application/json", "Accept": "application/json"}
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(f"{N8N_BASE}/api/v1{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except: return e.code, e.read().decode()


def list_data(body):
    if isinstance(body, dict) and isinstance(body.get("data"), list):
        return body["data"]
    if isinstance(body, list):
        return body
    return []


def js_single(value):
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def apply_model_defaults(obj):
    replacements = {
        json.dumps("claude-sonnet-4-5-20250929"): json.dumps(LLM_MODEL),
        "'claude-sonnet-4-5-20250929'": js_single(LLM_MODEL),
        json.dumps("doubao-seedream-4-0-250828"): json.dumps(IMAGE_MODEL),
        "'doubao-seedream-4-0-250828'": js_single(IMAGE_MODEL),
        json.dumps("doubao-seedance-1-0-pro-250528"): json.dumps(VIDEO_MODEL),
        "'doubao-seedance-1-0-pro-250528'": js_single(VIDEO_MODEL),
    }
    if isinstance(obj, dict):
        for key, value in list(obj.items()):
            obj[key] = apply_model_defaults(value)
        return obj
    if isinstance(obj, list):
        return [apply_model_defaults(value) for value in obj]
    if isinstance(obj, str):
        for old, new in replacements.items():
            obj = obj.replace(old, new)
        return obj
    return obj


def get_existing_credentials():
    code, body = req("GET", "/credentials?limit=250")
    if code != 200:
        return {}
    by_name = {}
    for c in list_data(body):
        if not c.get("name") or not c.get("id"):
            continue
        prev = by_name.get(c["name"])
        if not prev or (c.get("createdAt") or "") > (prev.get("createdAt") or ""):
            by_name[c["name"]] = c
    return {name: c["id"] for name, c in by_name.items()}


# ============================================================
#  Step 1: 创建 provider credentials
# ============================================================
print("=" * 60)
print("Step 1: 创建 provider credentials")
print("=" * 60)

CREDS = [
    {
        "name": "cred-pg-content-factory", "type": "postgres",
        "data": {
            "host": "postgres", "database": "content_factory", "user": "postgres",
            "password": PG_PASSWORD, "port": 5432,
            "allowUnauthorizedCerts": False, "ssl": "disable", "sshTunnel": False,
        },
        "secret_required": False,
    },
    {"name": "cred-llm-provider", "type": "httpHeaderAuth",
     "data": {"name": "Authorization", "value": f"Bearer {LLM_API_KEY or 'placeholder'}"},
     "secret_required": True,
     "secret_present": bool(LLM_API_KEY),
     "secret_name": "LLM_API_KEY"},
    {"name": "cred-image-provider", "type": "httpHeaderAuth",
     "data": {"name": "Authorization", "value": f"Bearer {IMAGE_API_KEY or 'placeholder'}"},
     "secret_required": True,
     "secret_present": bool(IMAGE_API_KEY),
     "secret_name": "IMAGE_API_KEY"},
    {"name": "cred-video-provider", "type": "httpHeaderAuth",
     "data": {"name": "Authorization", "value": f"Bearer {VIDEO_API_KEY or 'placeholder'}"},
     "secret_required": True,
     "secret_present": bool(VIDEO_API_KEY),
     "secret_name": "VIDEO_API_KEY"},
    {"name": "cred-volcengine-asr", "type": "httpHeaderAuth",
     "data": {"name": "Authorization", "value": f"Bearer {ASR_API_KEY or 'placeholder'}"},
     "secret_required": False},
    {"name": "cred-aliyun-oss-signer", "type": "httpHeaderAuth",
     "data": {"name": "Authorization", "value": "Bearer placeholder"},
     "secret_required": False},
    {"name": "cred-feishu-tenant-token", "type": "httpHeaderAuth",
     "data": {"name": "Authorization", "value": "Bearer placeholder"},
     "secret_required": False},
]

existing_cred_ids = get_existing_credentials()
cred_id_by_name = dict(existing_cred_ids)
for c in CREDS:
    payload = {"name": c["name"], "type": c["type"], "data": c["data"]}
    existing_id = existing_cred_ids.get(c["name"])
    missing_secret = c.get("secret_required") and not c.get("secret_present")
    if existing_id:
        if missing_secret:
            cred_id_by_name[c["name"]] = existing_id
            print(f"  SKIP update {c['name']} -> {existing_id} ({c['secret_name']} 未配置，保留现有 credential)")
            continue
        patch_code, patch_body = req("PATCH", f"/credentials/{existing_id}", payload)
        if patch_code not in (200, 201):
            print(f"  FAIL update {c['name']} id={existing_id} code={patch_code} body={str(patch_body)[:200]}")
            sys.exit(1)
        cred_id_by_name[c["name"]] = existing_id
        print(f"  OK update {c['name']} -> {existing_id}")
        continue

    code, body = req("POST", "/credentials", payload)
    if code in (200, 201):
        cred_id_by_name[c["name"]] = body["id"]
        print(f"  OK create {c['name']} -> {body['id']}")
    elif code == 400 and "already exists" in str(body).lower():
        existing_id = existing_cred_ids.get(c["name"])
        if not existing_id:
            print(f"  FAIL {c['name']} 已存在，但脚本没拿到它的 id，无法绑定到 workflow")
            sys.exit(1)
        patch_code, patch_body = req("PATCH", f"/credentials/{existing_id}", payload)
        if patch_code not in (200, 201):
            print(f"  FAIL update {c['name']} id={existing_id} code={patch_code} body={str(patch_body)[:200]}")
            sys.exit(1)
        cred_id_by_name[c["name"]] = existing_id
        print(f"  -- {c['name']} 已存在，复用 id={existing_id}")
    else:
        print(f"  FAIL {c['name']} code={code} body={str(body)[:200]}")
        sys.exit(1)


# ============================================================
#  Step 2: import 2 个 workflow JSON 到 N8N
# ============================================================
print()
print("=" * 60)
print("Step 2: import workflow")
print("=" * 60)

ROOT = Path(__file__).parent.parent
ALLOWED_SETTINGS = {"executionOrder", "saveDataErrorExecution", "saveDataSuccessExecution", "saveExecutionProgress", "saveManualExecutions"}

def derive_cred(node):
    """根据节点 type/name/url 推断该用哪个 credential"""
    nt = node.get("type", "")
    name = (node.get("name") or "").lower()
    params = node.get("parameters") or {}
    url = (params.get("url") or "").lower()
    if nt == "n8n-nodes-base.postgres":
        return ("postgres", "cred-pg-content-factory")
    if nt in ("n8n-nodes-base.httpRequest", "n8n-nodes-base.httpRequestTool"):
        if any(token in name for token in ("提炼卖点", "提示词", "分镜", "claude", "llm")) or "chat/completions" in url or "5dock.com" in url:
            return ("httpHeaderAuth", "cred-llm-provider")
        if any(token in name for token in ("seedream", "生图", "首帧")) or "/images/generations" in url:
            return ("httpHeaderAuth", "cred-image-provider")
        if any(token in name for token in ("seedance", "视频任务", "轮询视频")) or "/contents/generations/tasks" in url:
            return ("httpHeaderAuth", "cred-video-provider")
        if "openspeech" in url or "/asr" in url: return ("httpHeaderAuth", "cred-volcengine-asr")
        if "aliyuncs" in url: return ("httpHeaderAuth", "cred-aliyun-oss-signer")
        if "feishu" in url or "lark" in url: return ("httpHeaderAuth", "cred-feishu-tenant-token")
    return None


def find_node(wf_data, name_part):
    parts = name_part if isinstance(name_part, (list, tuple, set)) else [name_part]
    for node in wf_data.get("nodes", []):
        node_name = node.get("name", "")
        if any(part and part in node_name for part in parts):
            return node
    return None


def set_pg_query_replacement(node, expression):
    if not node:
        return
    node["typeVersion"] = 2.5
    params = node.setdefault("parameters", {})
    params.pop("additionalFields", None)
    options = params.setdefault("options", {})
    options.pop("queryParams", None)
    options["queryReplacement"] = expression


def patch_provider_routes(wf_data):
    """Make HTTP model calls read provider endpoints from env instead of hardcoded vendors."""
    llm_url = "={{(($env.LLM_BASE_URL || $env.NEWAPI_BASE_URL || 'https://5dock.com/v1').replace(/\\/$/, '')) + '/chat/completions'}}"
    image_url = "={{(($env.IMAGE_BASE_URL || $env.MEDIA_BASE_URL || $env.ARK_ENDPOINT || 'https://ark.cn-beijing.volces.com/api/v3').replace(/\\/$/, '')) + '/images/generations'}}"
    video_submit_url = "={{(($env.VIDEO_BASE_URL || $env.MEDIA_BASE_URL || $env.ARK_ENDPOINT || 'https://ark.cn-beijing.volces.com/api/v3').replace(/\\/$/, '')) + '/contents/generations/tasks'}}"
    video_poll_url = "={{(($env.VIDEO_BASE_URL || $env.MEDIA_BASE_URL || $env.ARK_ENDPOINT || 'https://ark.cn-beijing.volces.com/api/v3').replace(/\\/$/, '')) + '/contents/generations/tasks/' + $('提交视频任务（Video Provider）').item.json.id}}"
    for node in wf_data.get("nodes", []):
        if node.get("type") not in ("n8n-nodes-base.httpRequest", "n8n-nodes-base.httpRequestTool"):
            continue
        name = node.get("name", "")
        params = node.setdefault("parameters", {})
        if any(part in name for part in ("提炼卖点", "生成 11 条提示词", "生成分镜脚本", "生成首帧提示词", "生成视频提示词")):
            params["url"] = llm_url
        elif any(part in name for part in ("调用图片 Provider 生图", "调用 Seedream 生图", "生成首帧（Image Provider）", "生成首帧（Seedream）")):
            params["url"] = image_url
        elif "提交视频任务" in name:
            params["url"] = video_submit_url
        elif "轮询视频任务" in name:
            params["url"] = video_poll_url


def patch_postgres_params_for_n8n_2_19(wf_data, filename):
    """n8n 2.19 Postgres executeQuery reads options.queryReplacement, not old queryParams."""
    if filename == "image-workflow.json":
        webhook = find_node(wf_data, ("触发器 /trigger/image", "Webhook · /trigger/image", "trigger/image"))
        if webhook:
            webhook.setdefault("parameters", {})["responseMode"] = "onReceived"

        insert_run = find_node(wf_data, ("写入生成批次", "Insert generation_run"))
        insert_run_name = insert_run.get("name", "写入生成批次") if insert_run else "写入生成批次"
        if insert_run:
            insert_run.setdefault("parameters", {})["query"] = (
                "INSERT INTO generation_runs (id, task_id, sequence_no, model_provider, model_name, purpose, status, started_at, input_payload) "
                "VALUES (gen_random_uuid(), $1::uuid, COALESCE((SELECT MAX(sequence_no)+1 FROM generation_runs WHERE task_id = $1::uuid), 1), "
                "$4, $5, 'image_product', 'running', now(), ($3::jsonb) || jsonb_build_object('product_id', $2, 'model_provider', $4, 'model_name', $5)) RETURNING id;"
            )

        set_pg_query_replacement(find_node(wf_data, ("读取商品与风格", "Load product+style")), "={{ [$json.body.task_id] }}")
        set_pg_query_replacement(
            insert_run,
            "={{ [$json.task_id, $json.product_id, JSON.stringify({ trigger: 'webhook', shot_set: 'full' }), $env.IMAGE_PROVIDER || 'volcengine_ark', $env.IMAGE_MODEL || $env.ARK_IMAGE_MODEL || 'doubao-seedream-4-0-250828'] }}",
        )
        set_pg_query_replacement(
            find_node(wf_data, ("写入候选图记录", "Insert candidate")),
            "={{ [$json.run_id, $json.product_id, $json.shot_id, $json.shot_type, $json.en_prompt, $json.negative_prompt, $json.seed, JSON.stringify($json.ref_image_ids), $json.guidance_scale, $json.suggested_size, $json.oss_key, $json.oss_thumb_key, $json.ark_image_url || $json.oss_url, $json.ark_image_url || $json.oss_thumb_url, $json.ark_request_id, $json.generation_cost_cny, JSON.stringify({ model_name: $env.IMAGE_MODEL || $env.ARK_IMAGE_MODEL || 'doubao-seedream-4-0-250828', model_provider: $env.IMAGE_PROVIDER || 'volcengine_ark', fact_refs: $json.fact_refs || [], must_show: $json.must_show || [], must_not_change: $json.must_not_change || [], quality_check: $json.quality_check || {}, garment_identity: $json.garment_identity || '', logo_policy: $json.logo_policy || 'no_logo', authorized_brand_text: $json.authorized_brand_text || '', forbidden_brand_terms: $json.forbidden_brand_terms || [], forbidden_inventions: $json.forbidden_inventions || [], image_bytes: $json.image_bytes })] }}",
        )
        set_pg_query_replacement(
            find_node(wf_data, ("标记批次失败", "Mark run failed")),
            f"={{{{ [$('{insert_run_name}').item.json.id, 'upstream_failure', JSON.stringify($json.error || $json)] }}}}",
        )
        set_pg_query_replacement(
            find_node(wf_data, ("汇总批次状态", "Finalize run status")),
            f"={{{{ [$('{insert_run_name}').item.json.id] }}}}",
        )
        finalize = find_node(wf_data, ("汇总批次状态", "Finalize run status"))
        if finalize:
            finalize.setdefault("parameters", {})["query"] = "WITH counts AS (SELECT gr.id AS run_id, gr.task_id, t.requested_count, COUNT(c.id) FILTER (WHERE c.status != 'failed') AS ok_count FROM generation_runs gr JOIN tasks t ON t.id = gr.task_id LEFT JOIN candidates c ON c.run_id = gr.id WHERE gr.id = $1::uuid GROUP BY gr.id, gr.task_id, t.requested_count), updated_run AS (UPDATE generation_runs gr SET status = (CASE WHEN counts.ok_count >= counts.requested_count THEN 'succeeded' WHEN counts.ok_count > 0 THEN 'partial' ELSE 'failed' END)::run_status, finished_at = now() FROM counts WHERE gr.id = counts.run_id RETURNING gr.task_id, gr.status), updated_task AS (UPDATE tasks t SET status = (CASE WHEN updated_run.status IN ('succeeded','partial') THEN 'candidates_ready' ELSE 'failed_recoverable' END)::task_status, finished_at = CASE WHEN updated_run.status = 'succeeded' THEN now() ELSE t.finished_at END, updated_at = now() FROM updated_run WHERE t.id = updated_run.task_id RETURNING t.status) SELECT status FROM updated_run;"

        compute = find_node(wf_data, ("生成 OSS 路径与元数据", "Compute OSS key"))
        insert_candidate = find_node(wf_data, ("写入候选图记录", "Insert candidate"))
        oss_upload = find_node(wf_data, ("上传 PNG 到 OSS", "Upload PNG"))
        split = find_node(wf_data, ("分批并发", "Split In Batches"))
        seedream = find_node(wf_data, ("调用图片 Provider 生图", "调用 Seedream 生图", "Generate image"))
        # Keep the authored image-provider body so reference images, negative prompts,
        # and model routing from n8n/image-workflow.json survive sync.
        if split:
            split.setdefault("parameters", {})["batchSize"] = 4
        if compute and insert_candidate:
            wf_data.setdefault("connections", {})[compute["name"]] = {
                "main": [[{"node": insert_candidate["name"], "type": "main", "index": 0}]]
            }
        if insert_candidate and finalize:
            insert_conn = wf_data.setdefault("connections", {}).setdefault(insert_candidate["name"], {})
            insert_main = insert_conn.setdefault("main", [[]])
            if not insert_main:
                insert_main.append([])
            if not any(c.get("node") == finalize["name"] for c in insert_main[0]):
                insert_main[0].append({"node": finalize["name"], "type": "main", "index": 0})
            wf_data.setdefault("connections", {})[finalize["name"]] = {"main": [[]]}
        if split and seedream and finalize:
            wf_data.setdefault("connections", {})[split["name"]] = {
                "main": [
                    [{"node": finalize["name"], "type": "main", "index": 0}],
                    [{"node": seedream["name"], "type": "main", "index": 0}],
                ]
            }
        if oss_upload:
            oss_upload["disabled"] = True

        # Keep prompt-generation node bodies as authored in n8n/*.json. They now read
        # tasks.parameters.prompt_strategy, so this setup script should not overwrite
        # them with old fixed YN-BRA-001 prompt templates.

    if filename == "video-workflow.json":
        webhook_node = find_node(wf_data, ("触发器 /trigger/video", "Webhook - /trigger/video"))
        read_node = find_node(wf_data, ("读取商品、风格与图池", "Read product + style"))
        parse_storyboard = find_node(wf_data, ("解析分镜脚本", "Parse Storyboard"))
        insert_video_candidate = find_node(wf_data, ("写入视频候选记录", "INSERT video candidate", "INSERT video_candidates"))
        webhook_name = webhook_node.get("name", "触发器 /trigger/video") if webhook_node else "触发器 /trigger/video"
        parse_name = parse_storyboard.get("name", "解析分镜脚本") if parse_storyboard else "解析分镜脚本"
        set_pg_query_replacement(
            read_node,
            f"={{{{ [$('{webhook_name}').item.json.body.task_id] }}}}",
        )
        set_pg_query_replacement(
            insert_video_candidate,
            f"={{{{ [$json.task_id, 'https://content-factory.oss-cn-shanghai.aliyuncs.com/videos/'+$now.format('yyyyMM')+'/'+$json.task_id+'/candidate_1.mp4', 'https://content-factory.oss-cn-shanghai.aliyuncs.com/videos/'+$now.format('yyyyMM')+'/'+$json.task_id+'/candidate_1_thumb.jpg', JSON.stringify($('{parse_name}').first().json.storyboard)] }}}}",
        )


WORKFLOWS = {
    "image-workflow.json": {
        "name": "ContentFactory Image Pipeline",
        "aliases": [
            "内容工厂·图片生成流程（YN-BRA-001 基线）",
            "ContentFactory · Image Pipeline (YN-BRA-001 baseline)",
            "ContentFactory ? Image Pipeline (YN-BRA-001 baseline)",
            "ContentFactory ?? Image Pipeline (YN-BRA-001 baseline)",
        ],
    },
    "video-workflow.json": {
        "name": "ContentFactory Video Pipeline",
        "aliases": [
            "内容工厂·视频生成流程（YN-BRA-001）",
            "Content Factory - Video Pipeline (YN-BRA-001)",
        ],
    },
}


def resolve_existing_workflow_id(existing_map, wf_conf):
    for name in [wf_conf["name"], *wf_conf.get("aliases", [])]:
        if name in existing_map:
            return existing_map[name]
    return None


def get_existing_workflows():
    code, body = req("GET", "/workflows")
    if code != 200: return {}
    return {w["name"]: w["id"] for w in list_data(body)}

existing = get_existing_workflows()
workflow_ids = {}

for filename, wf_conf in WORKFLOWS.items():
    wf_name = wf_conf["name"]
    src = ROOT / "n8n" / filename
    print(f"\n  {filename}:")
    if not src.is_file():
        print(f"    SKIP {src} 不存在")
        continue
    wf_data = json.loads(src.read_text(encoding="utf-8"))
    patch_provider_routes(wf_data)

    # patch 节点 credential
    for node in wf_data.get("nodes", []):
        derived = derive_cred(node)
        if derived:
            ct, cn = derived
            cuuid = cred_id_by_name.get(cn)
            if cuuid:
                node["credentials"] = {ct: {"id": cuuid, "name": cn}}

        # 视频 workflow: executeCommand 节点改成空 Code（新版 N8N 禁了 executeCommand）
        if node.get("type") == "n8n-nodes-base.executeCommand":
            old_name = node["name"]
            node["type"] = "n8n-nodes-base.code"
            node["typeVersion"] = 2
            node["parameters"] = {"jsCode": f"// {old_name}\nreturn $input.all();"}
            node["disabled"] = True

    # 禁飞书节点（colleague 默认没飞书 token）
    for node in wf_data.get("nodes", []):
        if "Feishu" in node.get("name", "") or "飞书" in node.get("name", ""):
            node["disabled"] = True

    patch_postgres_params_for_n8n_2_19(wf_data, filename)
    apply_model_defaults(wf_data)

    settings = {k: v for k, v in (wf_data.get("settings") or {}).items() if k in ALLOWED_SETTINGS}
    if "executionOrder" not in settings:
        settings["executionOrder"] = "v1"

    body = {
        "name": wf_name,
        "nodes": wf_data["nodes"],
        "connections": wf_data["connections"],
        "settings": settings,
    }
    existing_id = resolve_existing_workflow_id(existing, wf_conf)
    if existing_id:
        # 已存在 -> PUT
        code, resp = req("PUT", f"/workflows/{existing_id}", body)
        workflow_ids[filename] = existing_id
        existing[wf_name] = existing_id
        print(f"    PUT 更新 code={code}")
    else:
        code, resp = req("POST", "/workflows", body)
        if code in (200, 201):
            existing[wf_name] = resp["id"]
            workflow_ids[filename] = resp["id"]
            print(f"    POST 新建 code={code} id={resp['id']}")
        else:
            print(f"    FAIL POST code={code} body={str(resp)[:200]}")


# ============================================================
#  Step 3: 激活 image-workflow
# ============================================================
print()
print("=" * 60)
print("Step 3: 激活 workflow")
print("=" * 60)

img_id = workflow_ids.get("image-workflow.json") or resolve_existing_workflow_id(existing, WORKFLOWS["image-workflow.json"])
vid_id = workflow_ids.get("video-workflow.json") or resolve_existing_workflow_id(existing, WORKFLOWS["video-workflow.json"])
if img_id:
    code, _ = req("POST", f"/workflows/{img_id}/activate")
    print(f"  image-workflow activate: {code}")
if vid_id:
    code, _ = req("POST", f"/workflows/{vid_id}/activate")
    print(f"  video-workflow activate: {code}")

try:
    write_env_value("PAC_N8N_SYNCED_AT", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
except Exception as exc:
    print(f"  WARN: PAC_N8N_SYNCED_AT 写入失败: {exc}")


# ============================================================
#  Step 4: 最终状态
# ============================================================
print()
print("=" * 60)
print("done. 当前 workflow 状态:")
print("=" * 60)
code, body = req("GET", "/workflows")
for w in body.get("data", []):
    s = "🟢 Active" if w["active"] else "🔴 Inactive"
    print(f"  {s}  {w['name']}")

print()
print("现在去:")
print(f"  N8N 画布: {N8N_BASE}/workflow/{img_id or '<id>'}")
print("  开录入表单: python scripts/intake_form.py")
print("  浏览器: http://localhost:5001")
