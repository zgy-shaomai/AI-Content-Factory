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
3. 可选：改 deploy/.env.local 填 ARK_API_KEY 和 NEWAPI_KEY
"""
import json
import os
import sys
import urllib.request
import urllib.error
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
PG_PASSWORD = env.get("POSTGRES_PASSWORD", "")
ARK_API_KEY = env.get("ARK_API_KEY", "")
NEWAPI_KEY = env.get("NEWAPI_KEY", "")

if not PG_PASSWORD:
    print("❌ deploy/.env.local 里 POSTGRES_PASSWORD 必须填")
    sys.exit(1)

missing_api_keys = [name for name, value in {"ARK_API_KEY": ARK_API_KEY, "NEWAPI_KEY": NEWAPI_KEY}.items() if not value]
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
#  Step 1: 创建 6 个 credential
# ============================================================
print("=" * 60)
print("Step 1: 创建 6 个 credential")
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
    {"name": "cred-5dock-newapi", "type": "httpHeaderAuth",
     "data": {"name": "Authorization", "value": f"Bearer {NEWAPI_KEY or 'placeholder'}"},
     "secret_required": True,
     "secret_present": bool(NEWAPI_KEY),
     "secret_name": "NEWAPI_KEY"},
    {"name": "cred-volcengine-ark", "type": "httpHeaderAuth",
     "data": {"name": "Authorization", "value": f"Bearer {ARK_API_KEY or 'placeholder'}"},
     "secret_required": True,
     "secret_present": bool(ARK_API_KEY),
     "secret_name": "ARK_API_KEY"},
    {"name": "cred-volcengine-asr", "type": "httpHeaderAuth",
     "data": {"name": "Authorization", "value": "Bearer placeholder"},
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
    """根据节点 type+url 推断该用哪个 credential"""
    nt = node.get("type", "")
    params = node.get("parameters") or {}
    url = (params.get("url") or "").lower()
    if nt == "n8n-nodes-base.postgres":
        return ("postgres", "cred-pg-content-factory")
    if nt in ("n8n-nodes-base.httpRequest", "n8n-nodes-base.httpRequestTool"):
        if "5dock.com" in url: return ("httpHeaderAuth", "cred-5dock-newapi")
        if "ark.cn-beijing" in url or "ark." in url: return ("httpHeaderAuth", "cred-volcengine-ark")
        if "openspeech" in url or "/asr" in url: return ("httpHeaderAuth", "cred-volcengine-asr")
        if "aliyuncs" in url: return ("httpHeaderAuth", "cred-aliyun-oss-signer")
        if "feishu" in url or "lark" in url: return ("httpHeaderAuth", "cred-feishu-tenant-token")
    return None


def find_node(wf_data, name_part):
    for node in wf_data.get("nodes", []):
        if name_part in node.get("name", ""):
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


def patch_postgres_params_for_n8n_2_19(wf_data, filename):
    """n8n 2.19 Postgres executeQuery reads options.queryReplacement, not old queryParams."""
    if filename == "image-workflow.json":
        webhook = find_node(wf_data, "trigger/image")
        if webhook:
            webhook.setdefault("parameters", {})["responseMode"] = "onReceived"

        insert_run = find_node(wf_data, "Insert generation_run")
        insert_run_name = insert_run.get("name", "Postgres · Insert generation_run") if insert_run else "Postgres · Insert generation_run"

        set_pg_query_replacement(find_node(wf_data, "Load product+style"), "={{ [$json.body.task_id] }}")
        set_pg_query_replacement(
            insert_run,
            "={{ [$json.task_id, $json.product_id, JSON.stringify({ trigger: 'webhook', shot_set: 'full' })] }}",
        )
        set_pg_query_replacement(
            find_node(wf_data, "Insert candidate"),
            "={{ [$json.run_id, $json.product_id, $json.shot_id, $json.shot_type, $json.en_prompt, $json.negative_prompt, $json.seed, JSON.stringify($json.ref_image_ids), $json.guidance_scale, $json.suggested_size, $json.oss_key, $json.oss_thumb_key, $json.ark_image_url || $json.oss_url, $json.ark_image_url || $json.oss_thumb_url, $json.ark_request_id, $json.generation_cost_cny, JSON.stringify({ logo_preserved: true, fabric_keywords: ['breathable mesh','sweat-wicking nylon-spandex'], brand_palette_hash: 'sha1:matteblack-v1', image_bytes: $json.image_bytes })] }}",
        )
        set_pg_query_replacement(
            find_node(wf_data, "Mark run failed"),
            f"={{{{ [$('{insert_run_name}').item.json.id, 'upstream_failure', JSON.stringify($json.error || $json)] }}}}",
        )
        set_pg_query_replacement(
            find_node(wf_data, "Finalize run status"),
            f"={{{{ [$('{insert_run_name}').item.json.id] }}}}",
        )
        finalize = find_node(wf_data, "Finalize run status")
        if finalize:
            finalize.setdefault("parameters", {})["query"] = "WITH counts AS (SELECT gr.id AS run_id, gr.task_id, t.requested_count, COUNT(c.id) FILTER (WHERE c.status != 'failed') AS ok_count FROM generation_runs gr JOIN tasks t ON t.id = gr.task_id LEFT JOIN candidates c ON c.run_id = gr.id WHERE gr.id = $1::uuid GROUP BY gr.id, gr.task_id, t.requested_count), updated_run AS (UPDATE generation_runs gr SET status = (CASE WHEN counts.ok_count >= counts.requested_count THEN 'succeeded' WHEN counts.ok_count > 0 THEN 'partial' ELSE 'failed' END)::run_status, finished_at = now() FROM counts WHERE gr.id = counts.run_id RETURNING gr.task_id, gr.status), updated_task AS (UPDATE tasks t SET status = (CASE WHEN updated_run.status IN ('succeeded','partial') THEN 'candidates_ready' ELSE 'failed_recoverable' END)::task_status, finished_at = CASE WHEN updated_run.status = 'succeeded' THEN now() ELSE t.finished_at END, updated_at = now() FROM updated_run WHERE t.id = updated_run.task_id RETURNING t.status) SELECT status FROM updated_run;"

        compute = find_node(wf_data, "Compute OSS key")
        insert_candidate = find_node(wf_data, "Insert candidate")
        oss_upload = find_node(wf_data, "Upload PNG")
        split = find_node(wf_data, "Split In Batches")
        seedream = find_node(wf_data, "Generate image")
        if seedream:
            seedream.setdefault("parameters", {})["jsonBody"] = """={{ {
  "model": "doubao-seedream-4-0-250828",
  "prompt": $json.en_prompt || "",
  "size": (() => {
    const fallback = "1024x1024";
    const raw = String($json.suggested_size || fallback).trim().toLowerCase();
    const m = raw.match(/^(\\d+)\\s*x\\s*(\\d+)$/);
    if (!m) return fallback;
    const w = Number(m[1]);
    const h = Number(m[2]);
    return Number.isFinite(w) && Number.isFinite(h) && (w * h) >= 921600 ? `${w}x${h}` : fallback;
  })(),
  "seed": Number.isFinite(Number($json.seed)) ? Number($json.seed) : Math.floor(Math.random() * 2000000000),
  "guidance_scale": $json.guidance_scale || 5.5,
  "watermark": false,
  "response_format": "url",
  "negative_prompt": $json.negative_prompt || ""
} }}"""
        if split:
            split.setdefault("parameters", {})["batchSize"] = 1
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

        load_node = find_node(wf_data, "Load product+style")
        build_prompts = find_node(wf_data, "Build 11 prompts")
        if load_node and build_prompts:
            load_name = load_node.get("name", "Postgres · Load product+style")
            build_prompts.setdefault("parameters", {})["jsonBody"] = """={{ {
  "model": "claude-sonnet-4-5-20250929",
  "temperature": 0.6,
  "max_tokens": 6000,
  "response_format": { "type": "json_object" },
  "messages": [
    {
      "role": "system",
      "content": "You are a senior prompt engineer for Seedream 4.0. Generate 6 product-shot prompts (studio_front, studio_side, studio_back, fabric_macro, zipper_action, logo_closeup) AND 5 scene prompts (scene_yoga_studio, scene_gym_training, scene_running_park, scene_outdoor_mountain, scene_beach). Each en_prompt 80-150 words English. Output strict JSON: { shared_negative_prompt, prompts: [11 items each with shot_id, shot_type, en_prompt, suggested_size, ref_image_ids, guidance_scale, seed_hint] }."
    },
    {
      "role": "user",
      "content": "=== ATTRIBUTES ===\\n" + JSON.stringify($('__LOAD_NODE__').item.json.attributes_json) + "\\n\\n=== SELLING POINTS ===\\n" + $json.choices[0].message.content + "\\n\\n=== STYLE TEMPLATE ===\\nbrand_palette: " + JSON.stringify($('__LOAD_NODE__').item.json.brand_palette) + "\\nmodel_descriptor: " + JSON.stringify($('__LOAD_NODE__').item.json.model_descriptor) + "\\nlighting: " + ($('__LOAD_NODE__').item.json.lighting || "") + "\\ncomposition: " + ($('__LOAD_NODE__').item.json.composition || "") + "\\nlens: " + ($('__LOAD_NODE__').item.json.lens || "") + "\\nmood: " + ($('__LOAD_NODE__').item.json.mood || "") + "\\n\\nReturn JSON only."
    }
  ]
} }}""".replace("__LOAD_NODE__", load_name)

        explode = find_node(wf_data, "Explode prompts")
        if load_node and insert_run and explode:
            load_name = load_node.get("name", "Postgres · Load product+style")
            insert_run_name = insert_run.get("name", "Postgres · Insert generation_run")
            explode.setdefault("parameters", {})["jsCode"] = """// Parse the LLM JSON content and explode into 11 items, one per shot prompt.
const rawValue = $input.first().json.choices?.[0]?.message?.content ?? '';
let raw = typeof rawValue === 'string' ? rawValue.trim() : JSON.stringify(rawValue);
raw = raw.replace(/^```(?:json)?\\s*/i, '').replace(/```$/i, '').trim();
let parsed;
try {
  parsed = JSON.parse(raw);
} catch (e) {
  throw new Error('LLM did not return valid JSON: ' + e.message + ' | sample=' + raw.slice(0, 120));
}
if (!parsed.prompts || !Array.isArray(parsed.prompts) || parsed.prompts.length < 11) {
  throw new Error('Expected 11 prompts in LLM response, got ' + (parsed.prompts ? parsed.prompts.length : 0));
}
const sharedNeg = parsed.shared_negative_prompt || '';
const runId = $('__INSERT_RUN_NODE__').item.json.id;
const sku = $('__LOAD_NODE__').item.json.sku;
const productId = $('__LOAD_NODE__').item.json.product_id;
const taskId = $('__LOAD_NODE__').item.json.task_id;
function normalizeSize(value) {
  const fallback = '1024x1024';
  const raw = String(value || fallback).trim().toLowerCase();
  const m = raw.match(/^(\\d+)\\s*x\\s*(\\d+)$/);
  if (!m) return fallback;
  const w = Number(m[1]);
  const h = Number(m[2]);
  return Number.isFinite(w) && Number.isFinite(h) && (w * h) >= 921600 ? `${w}x${h}` : fallback;
}

return parsed.prompts.slice(0, 11).map((p, idx) => ({
  json: {
    run_id: runId,
    task_id: taskId,
    product_id: productId,
    sku,
    shot_id: p.shot_id || `shot_${idx + 1}`,
    shot_type: p.shot_type || (idx < 6 ? 'product' : 'scene'),
    en_prompt: p.en_prompt || p.prompt || '',
    negative_prompt: sharedNeg,
    suggested_size: normalizeSize(p.suggested_size),
    ref_image_ids: p.ref_image_ids || [],
    guidance_scale: p.guidance_scale || 5.5,
    seed: p.seed_hint || Math.floor(Math.random() * 2_000_000_000),
    idx,
    ref_image_urls: []
  }
}));""".replace("__LOAD_NODE__", load_name).replace("__INSERT_RUN_NODE__", insert_run_name)

    if filename == "video-workflow.json":
        set_pg_query_replacement(
            find_node(wf_data, "Read product + style"),
            "={{ [$('Webhook - /trigger/video').item.json.body.task_id] }}",
        )
        set_pg_query_replacement(
            find_node(wf_data, "INSERT video candidate") or find_node(wf_data, "INSERT video_candidates"),
            "={{ [$json.task_id, 'https://content-factory.oss-cn-shanghai.aliyuncs.com/videos/'+$now.format('yyyyMM')+'/'+$json.task_id+'/candidate_1.mp4', 'https://content-factory.oss-cn-shanghai.aliyuncs.com/videos/'+$now.format('yyyyMM')+'/'+$json.task_id+'/candidate_1_thumb.jpg', JSON.stringify($('Parse Storyboard').first().json.storyboard)] }}",
        )


WORKFLOWS = {
    "image-workflow.json": "ContentFactory · Image Pipeline (YN-BRA-001 baseline)",
    "video-workflow.json": "Content Factory - Video Pipeline (YN-BRA-001)",
}

def get_existing_workflows():
    code, body = req("GET", "/workflows")
    if code != 200: return {}
    return {w["name"]: w["id"] for w in list_data(body)}

existing = get_existing_workflows()

for filename, wf_name in WORKFLOWS.items():
    src = ROOT / "n8n" / filename
    print(f"\n  {filename}:")
    if not src.is_file():
        print(f"    SKIP {src} 不存在")
        continue
    wf_data = json.loads(src.read_text(encoding="utf-8"))

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

    settings = {k: v for k, v in (wf_data.get("settings") or {}).items() if k in ALLOWED_SETTINGS}
    if "executionOrder" not in settings:
        settings["executionOrder"] = "v1"

    body = {
        "name": wf_data.get("name", wf_name),
        "nodes": wf_data["nodes"],
        "connections": wf_data["connections"],
        "settings": settings,
    }
    if wf_name in existing:
        # 已存在 -> PUT
        code, resp = req("PUT", f"/workflows/{existing[wf_name]}", body)
        print(f"    PUT 更新 code={code}")
    else:
        code, resp = req("POST", "/workflows", body)
        if code in (200, 201):
            existing[wf_name] = resp["id"]
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

img_id = existing.get(WORKFLOWS["image-workflow.json"])
vid_id = existing.get(WORKFLOWS["video-workflow.json"])
if img_id:
    code, _ = req("POST", f"/workflows/{img_id}/activate")
    print(f"  image-workflow activate: {code}")
if vid_id:
    code, _ = req("POST", f"/workflows/{vid_id}/activate")
    print(f"  video-workflow activate: {code}")


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
