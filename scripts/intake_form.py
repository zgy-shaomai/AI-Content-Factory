"""
内容工厂 v3 · 本地联调界面
访问 http://localhost:5001
"""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import io
import json
import urllib.request, urllib.parse, urllib.error
import subprocess
import sys
import html
import re
import time
import zipfile

import os, mimetypes
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(errors="replace")

PORT = 5001
PG_CONTAINER = "cf-postgres-local"
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
EXTERNAL_TASK_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
VIDEO_DIR = Path(__file__).parent.parent / "_seed_assets" / "videos"
AUDIO_DIR = Path(__file__).parent.parent / "_seed_assets" / "audio"
ROOT_DIR = Path(__file__).parent.parent
ENV_LOCAL_PATH = ROOT_DIR / "deploy" / ".env.local"
ENV_LOCAL_EXAMPLE_PATH = ROOT_DIR / "deploy" / ".env.local.example"

# 从 deploy/.env.local 读 ARK key（如果存在），fallback 到环境变量
def _load_env_local():
    out = {}
    if ENV_LOCAL_PATH.is_file():
        for line in ENV_LOCAL_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"): continue
            if "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out

_env = _load_env_local()
HOST = _env.get("INTAKE_HOST") or os.environ.get("INTAKE_HOST", "127.0.0.1")
POSTGRES_DB = _env.get("POSTGRES_DB") or os.environ.get("POSTGRES_DB", "content_factory")
POSTGRES_USER = _env.get("POSTGRES_USER") or os.environ.get("POSTGRES_USER", "postgres")
N8N_BASE = (_env.get("N8N_BASE") or os.environ.get("N8N_BASE", "http://127.0.0.1:5678")).rstrip("/")
N8N_TRIGGER = f"{N8N_BASE}/webhook/trigger/image"
N8N_EDITOR_URL = (_env.get("N8N_EDITOR_URL") or os.environ.get("N8N_EDITOR_URL") or N8N_BASE)
N8N_IMAGE_EDITOR_URL = (_env.get("N8N_IMAGE_EDITOR_URL") or os.environ.get("N8N_IMAGE_EDITOR_URL") or N8N_EDITOR_URL)
N8N_VIDEO_EDITOR_URL = (_env.get("N8N_VIDEO_EDITOR_URL") or os.environ.get("N8N_VIDEO_EDITOR_URL") or N8N_EDITOR_URL)
N8N_IMAGE_ENTRY_URL = "/open-n8n?pipeline=image"
N8N_VIDEO_ENTRY_URL = "/open-n8n?pipeline=video"
PAC_PROFILE = _env.get("PAC_PROFILE") or os.environ.get("PAC_PROFILE", "cn_ecommerce_default")
LLM_PROVIDER = _env.get("LLM_PROVIDER") or os.environ.get("LLM_PROVIDER", "5dock")
LLM_API_KEY = _env.get("LLM_API_KEY") or _env.get("NEWAPI_KEY") or os.environ.get("LLM_API_KEY") or os.environ.get("NEWAPI_KEY", "")
LLM_BASE_URL = (_env.get("LLM_BASE_URL") or _env.get("NEWAPI_BASE_URL") or os.environ.get("LLM_BASE_URL") or os.environ.get("NEWAPI_BASE_URL") or "https://5dock.com/v1").rstrip("/")
LLM_MODEL = _env.get("LLM_MODEL") or os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")
MEDIA_API_KEY = _env.get("MEDIA_API_KEY") or os.environ.get("MEDIA_API_KEY", "")
MEDIA_BASE_URL = (_env.get("MEDIA_BASE_URL") or os.environ.get("MEDIA_BASE_URL", "")).rstrip("/")
IMAGE_PROVIDER = _env.get("IMAGE_PROVIDER") or os.environ.get("IMAGE_PROVIDER", "volcengine_ark")
IMAGE_API_KEY = _env.get("IMAGE_API_KEY") or os.environ.get("IMAGE_API_KEY") or MEDIA_API_KEY or _env.get("ARK_API_KEY") or os.environ.get("ARK_API_KEY", "")
IMAGE_BASE_URL = (_env.get("IMAGE_BASE_URL") or os.environ.get("IMAGE_BASE_URL") or MEDIA_BASE_URL or _env.get("ARK_ENDPOINT") or os.environ.get("ARK_ENDPOINT") or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
IMAGE_MODEL = _env.get("IMAGE_MODEL") or _env.get("ARK_IMAGE_MODEL") or os.environ.get("IMAGE_MODEL") or os.environ.get("ARK_IMAGE_MODEL", "doubao-seedream-4-0-250828")
VIDEO_PROVIDER = _env.get("VIDEO_PROVIDER") or os.environ.get("VIDEO_PROVIDER", "volcengine_ark")
VIDEO_API_KEY = _env.get("VIDEO_API_KEY") or os.environ.get("VIDEO_API_KEY") or MEDIA_API_KEY or _env.get("ARK_API_KEY") or os.environ.get("ARK_API_KEY", "")
VIDEO_BASE_URL = (_env.get("VIDEO_BASE_URL") or os.environ.get("VIDEO_BASE_URL") or MEDIA_BASE_URL or _env.get("ARK_ENDPOINT") or os.environ.get("ARK_ENDPOINT") or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
VIDEO_MODEL = _env.get("VIDEO_MODEL") or _env.get("ARK_VIDEO_MODEL") or os.environ.get("VIDEO_MODEL") or os.environ.get("ARK_VIDEO_MODEL", "doubao-seedance-1-0-pro-250528")
ASR_PROVIDER = _env.get("ASR_PROVIDER") or os.environ.get("ASR_PROVIDER", "volcengine")
ASR_API_KEY = _env.get("ASR_API_KEY") or os.environ.get("ASR_API_KEY", "")
ASR_BASE_URL = (_env.get("ASR_BASE_URL") or os.environ.get("ASR_BASE_URL") or "https://openspeech.bytedance.com/api/v1/auc").rstrip("/")
ASR_MODEL = _env.get("ASR_MODEL") or os.environ.get("ASR_MODEL", "volc_auc_common")

# Backward-compatible aliases used by older scripts and local demo paths.
ARK_API_KEY = _env.get("ARK_API_KEY") or IMAGE_API_KEY or VIDEO_API_KEY
NEWAPI_KEY = _env.get("NEWAPI_KEY") or LLM_API_KEY
ARK_BASE = IMAGE_BASE_URL
NEWAPI_BASE_URL = LLM_BASE_URL
SEEDREAM_MODEL = IMAGE_MODEL
SEEDANCE_MODEL = VIDEO_MODEL
MAX_FORM_BODY_BYTES = 64 * 1024
MAX_JSON_BODY_BYTES = 32 * 1024
ALLOWED_VIDEO_DURATIONS = {6, 12, 24}
ALLOWED_VIDEO_RATIOS = {"9:16", "1:1", "16:9"}
VIDEO_RATIO_IMAGE_SIZES = {"9:16": "720x1280", "1:1": "1024x1024", "16:9": "1280x720"}
SEEDANCE_CONTROL_PARAM_RE = re.compile(r"\s+--(?:resolution|ratio|duration|fps|camera_fixed|watermark)\s+\S+", re.I)
RUNNING_TASK_STATUSES = {"pending", "analyzing", "prompting", "generating", "reviewing", "candidates_ready", "regenerating"}
DONE_TASK_STATUSES = {"approved", "archived", "delivered"}
VIDEO_STATUS_TEXT = "已配置视频生成，可直接提交成片" if VIDEO_API_KEY else "未配置 VIDEO_API_KEY/MEDIA_API_KEY，视频提交会被后端明确拦截"
VIDEO_STATUS_CLASS = "env-ready" if VIDEO_API_KEY else "env-warn"
CONFIG_KEYS = (
    "PAC_PROFILE",
    "LLM_PROVIDER",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "MEDIA_API_KEY",
    "MEDIA_BASE_URL",
    "IMAGE_PROVIDER",
    "IMAGE_API_KEY",
    "IMAGE_BASE_URL",
    "IMAGE_MODEL",
    "VIDEO_PROVIDER",
    "VIDEO_API_KEY",
    "VIDEO_BASE_URL",
    "VIDEO_MODEL",
    "ASR_PROVIDER",
    "ASR_API_KEY",
    "ASR_BASE_URL",
    "ASR_MODEL",
    "ARK_API_KEY",
    "NEWAPI_KEY",
    "ARK_ENDPOINT",
    "NEWAPI_BASE_URL",
    "N8N_BASE",
    "N8N_EDITOR_URL",
    "N8N_IMAGE_EDITOR_URL",
    "N8N_VIDEO_EDITOR_URL",
    "LLM_MODEL",
    "ARK_IMAGE_MODEL",
    "ARK_VIDEO_MODEL",
)
ALLOWED_PROMPT_PROFILES = {"auto", "product_detail", "lifestyle", "social_ad"}
ALLOWED_CREATIVE_LATITUDES = {"strict", "balanced", "exploratory"}
ALLOWED_PROMPT_DENSITIES = {"concise", "balanced", "rich"}
ALLOWED_LOGO_POLICIES = {"no_logo", "own_logo_only", "preserve_from_reference_only"}
DEFAULT_BLOCKED_BRAND_TERMS = (
    "Nike",
    "NIKE",
    "Nike Swoosh",
    "swoosh logo",
    "Li-Ning",
    "LI-NING",
    "李宁",
    "lining logo",
    "adidas",
    "ADIDAS",
    "three stripes",
    "trefoil logo",
    "Puma",
    "Under Armour",
    "Lululemon",
    "Anta",
    "安踏",
    "Jordan",
    "Jumpman",
    "New Balance",
    "Reebok",
    "ASICS",
    "Fila",
    "Decathlon",
)
BRAND_SAFE_NEGATIVE_PROMPT = (
    "third-party brand logo, unauthorized trademark, unauthorized wordmark, "
    "random letters, random numbers, slogan text, hangtag text, chest text, "
    "Nike, Nike Swoosh, Li-Ning, 李宁, adidas, three stripes, Puma, Under Armour, "
    "Lululemon, Anta, Jordan, New Balance, Reebok, ASICS, Fila, Decathlon, "
    "logo distortion, wrong color, deformed hands, duplicated body, text overlay, watermark"
)

if not VIDEO_API_KEY:
    print("⚠️  VIDEO_API_KEY / MEDIA_API_KEY 未配置！视频生成功能不可用。")
    print("   请在 Provider Access Center 或 deploy/.env.local 里配置后重启/刷新")


def mask_secret(value):
    value = (value or "").strip()
    if not value:
        return "未配置"
    if len(value) <= 10:
        return value[:2] + "***" + value[-2:]
    return value[:6] + "..." + value[-4:]


def compact_multiline(value, max_chars=1200):
    value = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return value[:max_chars]


def split_lines_limited(value, max_items=12, max_chars=120):
    lines = []
    for line in compact_multiline(value, max_items * max_chars).split("\n"):
        item = line.strip()
        if item:
            lines.append(item[:max_chars])
        if len(lines) >= max_items:
            break
    return lines


def split_terms_limited(value, max_items=32, max_chars=48):
    terms = []
    seen = set()
    for raw in re.split(r"[,，;；\n]+", compact_multiline(value, max_items * max_chars)):
        item = raw.strip()
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        terms.append(item[:max_chars])
        seen.add(key)
        if len(terms) >= max_items:
            break
    return terms


def merge_blocked_brand_terms(extra_terms):
    merged = []
    seen = set()
    for item in list(DEFAULT_BLOCKED_BRAND_TERMS) + list(extra_terms or []):
        item = str(item or "").strip()
        if not item:
            continue
        key = item.casefold()
        if key in seen:
            continue
        merged.append(item[:48])
        seen.add(key)
    return merged[:40]


def refresh_runtime_config():
    global _env, HOST, POSTGRES_DB, POSTGRES_USER, N8N_BASE, N8N_TRIGGER
    global N8N_EDITOR_URL, N8N_IMAGE_EDITOR_URL, N8N_VIDEO_EDITOR_URL
    global PAC_PROFILE, LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
    global MEDIA_API_KEY, MEDIA_BASE_URL
    global IMAGE_PROVIDER, IMAGE_API_KEY, IMAGE_BASE_URL, IMAGE_MODEL
    global VIDEO_PROVIDER, VIDEO_API_KEY, VIDEO_BASE_URL, VIDEO_MODEL
    global ASR_PROVIDER, ASR_API_KEY, ASR_BASE_URL, ASR_MODEL
    global ARK_API_KEY, NEWAPI_KEY, ARK_BASE, NEWAPI_BASE_URL, SEEDREAM_MODEL, SEEDANCE_MODEL
    global VIDEO_STATUS_TEXT, VIDEO_STATUS_CLASS
    _env = _load_env_local()
    HOST = _env.get("INTAKE_HOST") or os.environ.get("INTAKE_HOST", "127.0.0.1")
    POSTGRES_DB = _env.get("POSTGRES_DB") or os.environ.get("POSTGRES_DB", "content_factory")
    POSTGRES_USER = _env.get("POSTGRES_USER") or os.environ.get("POSTGRES_USER", "postgres")
    N8N_BASE = (_env.get("N8N_BASE") or os.environ.get("N8N_BASE", "http://127.0.0.1:5678")).rstrip("/")
    N8N_TRIGGER = f"{N8N_BASE}/webhook/trigger/image"
    N8N_EDITOR_URL = (_env.get("N8N_EDITOR_URL") or os.environ.get("N8N_EDITOR_URL") or N8N_BASE)
    N8N_IMAGE_EDITOR_URL = (_env.get("N8N_IMAGE_EDITOR_URL") or os.environ.get("N8N_IMAGE_EDITOR_URL") or N8N_EDITOR_URL)
    N8N_VIDEO_EDITOR_URL = (_env.get("N8N_VIDEO_EDITOR_URL") or os.environ.get("N8N_VIDEO_EDITOR_URL") or N8N_EDITOR_URL)
    PAC_PROFILE = _env.get("PAC_PROFILE") or os.environ.get("PAC_PROFILE", "cn_ecommerce_default")
    LLM_PROVIDER = _env.get("LLM_PROVIDER") or os.environ.get("LLM_PROVIDER", "5dock")
    LLM_API_KEY = _env.get("LLM_API_KEY") or _env.get("NEWAPI_KEY") or os.environ.get("LLM_API_KEY") or os.environ.get("NEWAPI_KEY", "")
    LLM_BASE_URL = (_env.get("LLM_BASE_URL") or _env.get("NEWAPI_BASE_URL") or os.environ.get("LLM_BASE_URL") or os.environ.get("NEWAPI_BASE_URL") or "https://5dock.com/v1").rstrip("/")
    LLM_MODEL = _env.get("LLM_MODEL") or os.environ.get("LLM_MODEL", "claude-sonnet-4-5-20250929")
    MEDIA_API_KEY = _env.get("MEDIA_API_KEY") or os.environ.get("MEDIA_API_KEY", "")
    MEDIA_BASE_URL = (_env.get("MEDIA_BASE_URL") or os.environ.get("MEDIA_BASE_URL", "")).rstrip("/")
    IMAGE_PROVIDER = _env.get("IMAGE_PROVIDER") or os.environ.get("IMAGE_PROVIDER", "volcengine_ark")
    IMAGE_API_KEY = _env.get("IMAGE_API_KEY") or os.environ.get("IMAGE_API_KEY") or MEDIA_API_KEY or _env.get("ARK_API_KEY") or os.environ.get("ARK_API_KEY", "")
    IMAGE_BASE_URL = (_env.get("IMAGE_BASE_URL") or os.environ.get("IMAGE_BASE_URL") or MEDIA_BASE_URL or _env.get("ARK_ENDPOINT") or os.environ.get("ARK_ENDPOINT") or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
    IMAGE_MODEL = _env.get("IMAGE_MODEL") or _env.get("ARK_IMAGE_MODEL") or os.environ.get("IMAGE_MODEL") or os.environ.get("ARK_IMAGE_MODEL", "doubao-seedream-4-0-250828")
    VIDEO_PROVIDER = _env.get("VIDEO_PROVIDER") or os.environ.get("VIDEO_PROVIDER", "volcengine_ark")
    VIDEO_API_KEY = _env.get("VIDEO_API_KEY") or os.environ.get("VIDEO_API_KEY") or MEDIA_API_KEY or _env.get("ARK_API_KEY") or os.environ.get("ARK_API_KEY", "")
    VIDEO_BASE_URL = (_env.get("VIDEO_BASE_URL") or os.environ.get("VIDEO_BASE_URL") or MEDIA_BASE_URL or _env.get("ARK_ENDPOINT") or os.environ.get("ARK_ENDPOINT") or "https://ark.cn-beijing.volces.com/api/v3").rstrip("/")
    VIDEO_MODEL = _env.get("VIDEO_MODEL") or _env.get("ARK_VIDEO_MODEL") or os.environ.get("VIDEO_MODEL") or os.environ.get("ARK_VIDEO_MODEL", "doubao-seedance-1-0-pro-250528")
    ASR_PROVIDER = _env.get("ASR_PROVIDER") or os.environ.get("ASR_PROVIDER", "volcengine")
    ASR_API_KEY = _env.get("ASR_API_KEY") or os.environ.get("ASR_API_KEY", "")
    ASR_BASE_URL = (_env.get("ASR_BASE_URL") or os.environ.get("ASR_BASE_URL") or "https://openspeech.bytedance.com/api/v1/auc").rstrip("/")
    ASR_MODEL = _env.get("ASR_MODEL") or os.environ.get("ASR_MODEL", "volc_auc_common")
    ARK_API_KEY = _env.get("ARK_API_KEY") or IMAGE_API_KEY or VIDEO_API_KEY
    NEWAPI_KEY = _env.get("NEWAPI_KEY") or LLM_API_KEY
    ARK_BASE = IMAGE_BASE_URL
    NEWAPI_BASE_URL = LLM_BASE_URL
    SEEDREAM_MODEL = IMAGE_MODEL
    SEEDANCE_MODEL = VIDEO_MODEL
    VIDEO_STATUS_TEXT = "已配置视频生成，可直接提交成片" if VIDEO_API_KEY else "未配置 VIDEO_API_KEY/MEDIA_API_KEY，视频提交会被后端明确拦截"
    VIDEO_STATUS_CLASS = "env-ready" if VIDEO_API_KEY else "env-warn"


def update_env_local(updates):
    source_path = ENV_LOCAL_PATH if ENV_LOCAL_PATH.exists() else ENV_LOCAL_EXAMPLE_PATH
    lines = source_path.read_text(encoding="utf-8").splitlines() if source_path.exists() else []
    seen = set()
    next_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            next_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in updates:
            next_lines.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            next_lines.append(line)
    append_items = [(key, value) for key, value in updates.items() if key not in seen]
    if append_items:
        if next_lines and next_lines[-1].strip():
            next_lines.append("")
        next_lines.append("# --- local UI saved settings ---")
        for key, value in append_items:
            next_lines.append(f"{key}={value}")
    ENV_LOCAL_PATH.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")


# ============================================================================
#  Common stylesheet (shared by form + result)
# ============================================================================
COMMON_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  background:#fafbfc;color:#0f172a;line-height:1.5;-webkit-font-smoothing:antialiased;
  font-feature-settings:"cv11","ss01";
}
a{color:inherit;text-decoration:none}
button{font-family:inherit;cursor:pointer;border:0;background:none}
button[disabled]{opacity:.65;cursor:not-allowed;transform:none!important;box-shadow:none!important}
:root{
  --indigo:#6366f1;--indigo-dark:#4f46e5;--pink:#ec4899;
  --slate-50:#f8fafc;--slate-100:#f1f5f9;--slate-200:#e2e8f0;--slate-300:#cbd5e1;
  --slate-400:#94a3b8;--slate-500:#64748b;--slate-600:#475569;--slate-700:#334155;
  --slate-800:#1e293b;--slate-900:#0f172a;
  --green:#10b981;--green-dark:#059669;--red:#ef4444;--amber:#f59e0b;
  --shadow-sm:0 1px 3px rgba(15,23,42,.06),0 1px 2px rgba(15,23,42,.04);
  --shadow-md:0 4px 12px rgba(15,23,42,.08),0 2px 4px rgba(15,23,42,.04);
  --shadow-lg:0 20px 40px -8px rgba(15,23,42,.12),0 4px 12px rgba(15,23,42,.06);
  --ease:cubic-bezier(.4,0,.2,1);
}

/* ---------- top nav ---------- */
.nav{
  position:sticky;top:0;z-index:50;
  background:rgba(255,255,255,.85);backdrop-filter:blur(12px);
  border-bottom:1px solid var(--slate-200);
  padding:0 24px;height:56px;
  display:flex;align-items:center;justify-content:space-between;
}
.nav-left{display:flex;align-items:center;gap:24px}
.logo{display:flex;align-items:center;gap:8px;font-weight:700;font-size:15px;letter-spacing:-.01em}
.logo-mark{
  width:28px;height:28px;border-radius:8px;
  background:linear-gradient(135deg,var(--indigo),var(--pink));
  display:flex;align-items:center;justify-content:center;color:#fff;font-size:13px;
  box-shadow:var(--shadow-sm);
}
.crumbs{display:flex;align-items:center;gap:6px;font-size:13px;color:var(--slate-500)}
.crumbs span{color:var(--slate-300)}
.crumbs strong{color:var(--slate-900);font-weight:500}
.nav-right{display:flex;align-items:center;gap:8px}
.workspace{
  display:flex;align-items:center;gap:8px;padding:6px 10px;
  background:var(--slate-50);border:1px solid var(--slate-200);border-radius:8px;
  font-size:12px;font-weight:500;color:var(--slate-700);cursor:pointer;
}
.avatar{
  width:28px;height:28px;border-radius:50%;
  background:linear-gradient(135deg,#a78bfa,#f472b6);
  color:#fff;font-size:12px;font-weight:600;
  display:flex;align-items:center;justify-content:center;
}
@media(max-width:640px){
  .nav{
    height:auto;padding:12px 16px;flex-direction:column;align-items:stretch;gap:10px;
  }
  .nav-left,.nav-right{
    width:100%;display:flex;align-items:center;justify-content:space-between;gap:10px;
  }
  .crumbs,.workspace{display:none}
}

/* ---------- buttons ---------- */
.btn{
  display:inline-flex;align-items:center;gap:6px;
  padding:9px 16px;border-radius:8px;font-size:13px;font-weight:500;
  transition:all .15s var(--ease);cursor:pointer;
  border:1.5px solid transparent;
}
.btn-primary{
  background:linear-gradient(135deg,var(--indigo),var(--indigo-dark));color:#fff;
  box-shadow:0 1px 2px rgba(99,102,241,.3),0 4px 12px rgba(99,102,241,.25);
}
.btn-primary:hover{transform:translateY(-1px);box-shadow:0 1px 2px rgba(99,102,241,.3),0 8px 20px rgba(99,102,241,.4)}
.btn-secondary{background:#fff;border-color:var(--slate-200);color:var(--slate-700)}
.btn-secondary:hover{border-color:var(--slate-300);background:var(--slate-50)}
.btn-ghost{color:var(--slate-600)}
.btn-ghost:hover{background:var(--slate-100);color:var(--slate-900)}
.btn-success{background:var(--green);color:#fff}
.btn-success:hover{background:var(--green-dark)}

/* ---------- chips / pills ---------- */
.chip{
  display:inline-flex;align-items:center;gap:6px;
  padding:5px 12px;border-radius:999px;
  font-size:12px;font-weight:500;
  border:1px solid var(--slate-200);background:#fff;color:var(--slate-700);
  cursor:pointer;transition:all .15s var(--ease);
}
.chip:hover{border-color:var(--indigo);color:var(--indigo);background:#f0f1fe}
.chip.active{background:var(--indigo);color:#fff;border-color:var(--indigo)}
.pill-status{
  display:inline-flex;align-items:center;gap:6px;
  padding:4px 10px;border-radius:999px;font-size:11px;font-weight:600;
  text-transform:uppercase;letter-spacing:.05em;
}
.pill-status .dot{width:6px;height:6px;border-radius:50%;background:currentColor}
.pill-running{background:rgba(99,102,241,.1);color:var(--indigo)}
.pill-running .dot{animation:pulse 1.5s ease-in-out infinite}
.pill-success{background:rgba(16,185,129,.1);color:var(--green-dark)}
.pill-failed{background:rgba(239,68,68,.1);color:var(--red)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
"""


# ============================================================================
#  Form page
# ============================================================================
FORM_HTML = """<!DOCTYPE html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>新建任务 · ContentFactory</title>
<style>""" + COMMON_CSS + """
.shell{max-width:1080px;margin:0 auto;padding:0 24px}
.page-header{padding:40px 0 24px}
.page-title{font-size:28px;font-weight:700;letter-spacing:-.02em;margin-bottom:6px}
.page-sub{font-size:14px;color:var(--slate-500)}
.steps{display:flex;align-items:center;gap:8px;margin-top:20px;font-size:12px;color:var(--slate-500)}
.steps .step{display:flex;align-items:center;gap:6px}
.step-num{
  width:22px;height:22px;border-radius:50%;background:var(--slate-200);color:var(--slate-500);
  display:flex;align-items:center;justify-content:center;font-weight:600;font-size:11px;
}
.step.active .step-num{background:var(--indigo);color:#fff}
.step.active{color:var(--slate-900);font-weight:500}
.step-arr{color:var(--slate-300)}
.flow-hint{
  display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:18px;
}
.flow-card{
  background:#fff;border:1px solid var(--slate-200);border-radius:12px;padding:14px 16px;
  box-shadow:var(--shadow-sm);
}
.flow-kicker{font-size:11px;font-weight:600;color:var(--indigo);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px}
.flow-title{font-size:14px;font-weight:600;color:var(--slate-900);margin-bottom:4px}
.flow-desc{font-size:12px;color:var(--slate-500);line-height:1.6}
@media(max-width:640px){.flow-hint{grid-template-columns:1fr}}

.layout{display:grid;grid-template-columns:1fr 280px;gap:24px;margin-bottom:60px}
@media(max-width:900px){.layout{grid-template-columns:1fr}}

.card{background:#fff;border:1px solid var(--slate-200);border-radius:12px;box-shadow:var(--shadow-sm)}
.card-section{padding:24px 28px;border-bottom:1px solid var(--slate-100)}
.card-section:last-child{border-bottom:0}
.card-title{font-size:13px;font-weight:600;color:var(--slate-900);margin-bottom:4px;display:flex;align-items:center;gap:8px}
.card-desc{font-size:12px;color:var(--slate-500);margin-bottom:18px}

.field{margin-bottom:14px}
.field-row{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:600px){.field-row{grid-template-columns:1fr}}
label{display:flex;align-items:center;gap:4px;font-size:12px;font-weight:500;color:var(--slate-700);margin-bottom:6px}
.req{color:var(--red);font-weight:600}
.help{font-size:11px;color:var(--slate-400);margin-top:4px}
.field-note{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.counter-pill{
  display:inline-flex;align-items:center;padding:4px 8px;border-radius:999px;
  font-size:11px;font-weight:600;background:var(--slate-100);color:var(--slate-600);
}
.counter-pill.good{background:rgba(16,185,129,.12);color:var(--green-dark)}
.counter-pill.warn{background:rgba(245,158,11,.14);color:#b45309}
.counter-pill.bad{background:rgba(239,68,68,.12);color:var(--red)}
input[type=text],textarea,select{
  width:100%;padding:9px 12px;
  border:1.5px solid var(--slate-200);border-radius:8px;
  font-family:inherit;font-size:13px;color:var(--slate-900);background:#fff;
  transition:all .15s var(--ease);
}
input:hover,textarea:hover,select:hover{border-color:var(--slate-300)}
input:focus,textarea:focus,select:focus{
  outline:0;border-color:var(--indigo);box-shadow:0 0 0 3px rgba(99,102,241,.12);
}
textarea{min-height:78px;resize:vertical;line-height:1.6}

.template-chips{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}

.submit-bar{
  padding:18px 28px;background:var(--slate-50);border-top:1px solid var(--slate-100);
  display:flex;justify-content:space-between;align-items:center;
  border-radius:0 0 12px 12px;
}
.submit-meta{font-size:11px;color:var(--slate-500)}
@media(max-width:640px){
  .submit-bar{flex-direction:column;align-items:stretch;gap:12px}
  .submit-bar .btn{width:100%;justify-content:center}
}

.aside{display:flex;flex-direction:column;gap:14px}
.aside-card{
  background:#fff;border:1px solid var(--slate-200);border-radius:10px;padding:16px;
}
.aside-title{font-size:11px;font-weight:600;color:var(--slate-500);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px}
.metric{display:flex;justify-content:space-between;align-items:baseline;padding:8px 0;border-bottom:1px solid var(--slate-100)}
.metric:last-child{border-bottom:0}
.metric-label{font-size:12px;color:var(--slate-500)}
.metric-value{font-size:14px;font-weight:600;color:var(--slate-900)}
.tip{font-size:12px;color:var(--slate-600);line-height:1.6}
.tip-icon{
  display:inline-flex;align-items:center;justify-content:center;
  width:24px;height:24px;border-radius:6px;
  background:rgba(99,102,241,.1);color:var(--indigo);margin-bottom:8px;
}
.env-note{
  margin-top:12px;padding:10px 12px;border-radius:8px;font-size:12px;font-weight:500;
  border:1px solid var(--slate-200);
}
.env-ready{background:rgba(16,185,129,.08);color:var(--green-dark);border-color:rgba(16,185,129,.18)}
.env-warn{background:rgba(245,158,11,.1);color:#b45309;border-color:rgba(245,158,11,.22)}
.recent-list{display:flex;flex-direction:column;gap:10px}
.recent-item{
  padding:12px;border:1px solid var(--slate-100);border-radius:10px;background:var(--slate-50);
}
.recent-row{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
.recent-name{font-size:13px;font-weight:600;color:var(--slate-900);line-height:1.5}
.recent-sub{font-size:11px;color:var(--slate-500);line-height:1.5;margin-top:4px}
.recent-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}
.recent-link{font-size:12px;font-weight:600;color:var(--indigo)}
.recent-link-muted{font-size:12px;font-weight:600;color:var(--slate-600)}
</style></head><body>

<nav class="nav">
  <div class="nav-left">
    <a class="logo" href="/"><span class="logo-mark">CF</span>ContentFactory</a>
    <div class="crumbs"><span>·</span> 新建任务 <span>·</span> <strong>录入产品</strong></div>
  </div>
  <div class="nav-right">
    <a href="/history" class="btn btn-ghost" style="font-size:12px">🕐 历史任务</a>
    <a href="/review" class="btn btn-ghost" style="font-size:12px">待审核</a>
    <a href="/settings" class="btn btn-ghost" style="font-size:12px">模型配置</a>
    <div class="workspace">
      <span style="width:6px;height:6px;border-radius:50%;background:var(--green)"></span>
      Yifeel · 服装电商
      <span style="color:var(--slate-400);font-size:10px">▾</span>
    </div>
    <div class="avatar">J</div>
  </div>
</nav>

<div class="shell">

<header class="page-header">
  <div class="page-title">录入产品</div>
  <div class="page-sub">填好 SKU、卖点和场景后，系统会先生成 11 张候选，其中 4 张用于重点审核展示，平均 2-3 分钟。</div>
  <div class="steps">
    <div class="step active"><span class="step-num">1</span>录入</div>
    <span class="step-arr">→</span>
    <div class="step"><span class="step-num">2</span>生成</div>
    <span class="step-arr">→</span>
    <div class="step"><span class="step-num">3</span>审核</div>
    <span class="step-arr">→</span>
    <div class="step"><span class="step-num">4</span>归档</div>
  </div>
  <div class="flow-hint">
    <div class="flow-card">
      <div class="flow-kicker">Step 1</div>
      <div class="flow-title">录入产品要点</div>
      <div class="flow-desc">填写 SKU、核心卖点、目标场景，系统会按同一模板生成本次任务。</div>
    </div>
    <div class="flow-card">
      <div class="flow-kicker">Step 2</div>
      <div class="flow-title">生成 11 张候选</div>
      <div class="flow-desc">默认产出 6 张商品图和 5 张场景图，先看全量，再挑 4 张做重点审核展示。</div>
    </div>
    <div class="flow-card">
      <div class="flow-kicker">Step 3</div>
      <div class="flow-title">审核后转视频</div>
      <div class="flow-desc">挑一张候选当首帧，继续走视频成片和归档，不需要重新录入同一 SKU。</div>
    </div>
  </div>
</header>

<div class="layout">

<form method="POST" action="/submit" id="form">

<div class="card">

  <div class="card-section">
    <div class="card-title">⚡ 快捷模板</div>
    <div class="card-desc">点一个模板自动填好下面字段，可继续编辑</div>
    <div class="template-chips">
      <button type="button" class="chip" onclick="applyTpl('bra', this)">运动内衣 · 黑</button>
      <button type="button" class="chip" onclick="applyTpl('pants', this)">瑜伽裤 · 高腰</button>
      <button type="button" class="chip" onclick="applyTpl('tee', this)">运动 T 恤 · 速干</button>
      <button type="button" class="chip" onclick="applyTpl('jacket', this)">户外冲锋衣 · 防风</button>
    </div>
  </div>

  <div class="card-section">
    <div class="card-title">📦 产品基本信息</div>

    <div class="field-row">
      <div class="field">
        <label>SKU 编号<span class="req">*</span></label>
        <input type="text" name="sku" required value="YN-BRA-001" id="f_sku" />
      </div>
      <div class="field">
        <label>类目<span class="req">*</span></label>
        <select name="category" id="f_cat">
          <option>运动内衣</option><option>运动服</option><option>瑜伽裤</option>
          <option>泳装</option><option>户外服饰</option><option>其他</option>
        </select>
      </div>
    </div>

    <div class="field">
      <label>产品名称<span class="req">*</span></label>
      <input type="text" name="name" required value="黑色高弹速干运动内衣（前拉链款）" id="f_name" />
    </div>

    <div class="field-row">
      <div class="field">
        <label>主色<span class="req">*</span></label>
        <input type="text" name="primary_color" required value="黑色" id="f_color" />
      </div>
      <div class="field">
        <label>目标受众</label>
        <input type="text" name="target_audience" value="25-40 岁运动女性" id="f_aud" />
      </div>
    </div>
  </div>

  <div class="card-section">
    <div class="card-title">✨ 卖点 与 场景</div>

    <div class="field">
      <label>核心卖点<span class="req">*</span></label>
      <textarea name="selling_points" required id="f_sp">透气网眼面料
前置拉链穿脱方便
高弹力支撑
速干面料</textarea>
      <div class="help">每行一条，5-7 条最佳。系统按重要性排序并生成视觉表达建议。</div>
    </div>

    <div class="field">
      <label>使用场景</label>
      <textarea name="scenarios" id="f_sc">瑜伽馆
跑步
健身房
户外</textarea>
      <div class="help">每行一个场景。系统按场景自动生成对应的场景图。</div>
    </div>
  </div>

  <div class="field-row">
    <div class="field">
      <label>图片生成偏好</label>
      <select name="image_goal" id="f_image_goal">
        <option value="balanced" selected>平衡探索：商品图与场景图均衡</option>
        <option value="detail_focus">细节优先：更强调面料、拉链、版型</option>
        <option value="scene_focus">场景优先：更强调动作、情绪、氛围</option>
      </select>
      <div class="help">该偏好会写入任务快照，供图片与视频提示词默认值参考。</div>
    </div>
    <div class="field">
      <label>视频运动风格</label>
      <select name="video_motion" id="f_video_motion">
        <option value="showcase" selected>稳态展示：适合详情页和成片演示</option>
        <option value="dynamic">动态短片：更强调镜头推进和动作</option>
        <option value="texture">质感特写：更强调材质、细节和近景</option>
      </select>
      <div class="help">结果页会自动带出对应的视频 prompt 默认草稿。</div>
    </div>
  </div>

  <div class="card-section">
    <div class="card-title">Prompt 策略</div>
    <div class="card-desc">把这次任务的表达方向写进任务快照，图片和视频链路会按它动态规划镜头，不再只套固定模板。</div>
    <div class="field-row">
      <div class="field">
        <label>提示词策略</label>
        <select name="prompt_profile" id="f_prompt_profile">
          <option value="auto" selected>自动：按商品、卖点和场景规划</option>
          <option value="product_detail">商品细节：面料、结构、功能优先</option>
          <option value="lifestyle">生活方式：人物状态和场景情绪优先</option>
          <option value="social_ad">社媒广告：前 2 秒视觉钩子优先</option>
        </select>
      </div>
      <div class="field">
        <label>创作自由度</label>
        <select name="creative_latitude" id="f_creative_latitude">
          <option value="strict">严格跟随商品资料</option>
          <option value="balanced" selected>平衡：允许轻度创意补全</option>
          <option value="exploratory">探索：允许更强场景变化</option>
        </select>
      </div>
    </div>
    <div class="field-row">
      <div class="field">
        <label>Prompt 详细度</label>
        <select name="prompt_density" id="f_prompt_density">
          <option value="concise">简洁：更短、更少限定</option>
          <option value="balanced" selected>标准：主体、镜头、光线完整</option>
          <option value="rich">丰富：加入更多材质、动作和风格细节</option>
        </select>
      </div>
      <div class="field">
        <label>负面约束</label>
        <input type="text" name="negative_prompt" id="f_negative_prompt" value="logo distortion, wrong color, deformed hands, duplicated body, text overlay, watermark" />
        <div class="help">会合并到图片负面提示词和视频首帧保护规则。</div>
      </div>
    </div>
    <div class="field">
      <label>自定义视觉约束</label>
      <textarea name="visual_guardrails" id="f_visual_guardrails" placeholder="每行一条，例如：Logo 必须保持原色；拉链必须在正中；不要把黑色偏成深蓝。">保持服装颜色和版型稳定
拉链、版型、面料纹理和主色在同一批图里保持一致
人物比例自然，避免夸张变形</textarea>
      <div class="help">适合填写品牌、模特、构图、色彩纪律等不可跑偏项。</div>
    </div>
    <div class="field">
      <label>自定义镜头计划</label>
      <textarea name="shot_plan" id="f_shot_plan" placeholder="可留空。每行一个想要的镜头，例如：正面棚拍 / 面料微距 / 瑜伽馆动作 / 户外晨跑。"></textarea>
      <div class="help">留空时系统会根据卖点和场景自动规划；填写后会优先按你的镜头计划生成。</div>
    </div>
  </div>

  <div class="submit-bar">
    <div class="submit-meta">提交后会创建任务并跳转到进度页；如果 N8N 或数据库异常，页面会显示可定位的状态提示。</div>
    <button type="submit" class="btn btn-primary" id="submitBtn">
      <span id="submitBtnLabel">开始生成</span>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
    </button>
  </div>
</div>

</form>

<aside class="aside">
  <div class="aside-card">
    <div class="aside-title">📊 本次预计产出</div>
    <div class="metric"><span class="metric-label">商品图</span><span class="metric-value">6 张</span></div>
    <div class="metric"><span class="metric-label">场景图</span><span class="metric-value">5 张</span></div>
    <div class="metric"><span class="metric-label">视频成片</span><span class="metric-value">1 条</span></div>
    <div class="metric"><span class="metric-label">重点审核</span><span class="metric-value">4 张</span></div>
    <div class="help">图片平均 2-3 分钟；视频单条约 90-180 秒，首帧从候选图直接选取。</div>
  </div>

  <div class="aside-card">
    <div class="tip-icon">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
    </div>
    <div class="tip">
      <strong style="color:var(--slate-900)">小技巧</strong><br>
      卖点写得越具体（如"前拉链穿脱"而不是"方便"），生成图越能突出特征。
    </div>
    <div class="env-note {video_status_class}">{video_status_text}</div>
  </div>

  <div class="aside-card">
    <div class="aside-title">🔗 关联视图</div>
    <a href="{n8n_editor_url}" style="display:block;padding:6px 0;font-size:12px;color:var(--indigo)">→ N8N 流程画布</a>
    <a href="/list" style="display:block;padding:6px 0;font-size:12px;color:var(--indigo)">→ 历史候选库</a>
  </div>
  {recent_tasks_block}
</aside>

</div>

</div>

<script>
const TEMPLATES = {
  bra:{sku:'YN-BRA-001',cat:'运动内衣',name:'黑色高弹速干运动内衣（前拉链款）',color:'黑色',aud:'25-40 岁运动女性',sp:'透气网眼面料\\n前置拉链穿脱方便\\n高弹力支撑\\n速干面料',sc:'瑜伽馆\\n跑步\\n健身房\\n户外'},
  pants:{sku:'YN-PNT-002',cat:'瑜伽裤',name:'高腰塑形瑜伽裤（裸感面料）',color:'深灰',aud:'22-38 岁瑜伽爱好者',sp:'裸感塑形面料\\n高腰收腹设计\\n无痕缝线\\n四向弹力',sc:'瑜伽馆\\n普拉提\\n日常通勤\\n户外散步'},
  tee:{sku:'YN-TEE-003',cat:'运动服',name:'速干透气运动 T 恤',color:'白色',aud:'25-45 岁健身人群',sp:'速干面料\\n透气网眼\\n抗菌防臭\\n轻量化',sc:'跑步\\n健身房\\n篮球场\\n户外徒步'},
  jacket:{sku:'YN-JKT-004',cat:'户外服饰',name:'防风防泼水冲锋衣',color:'军绿',aud:'30-50 岁户外爱好者',sp:'防风面料\\n防泼水涂层\\n反光条设计\\n多功能口袋',sc:'户外徒步\\n登山\\n骑行\\n通勤'}
};
function applyTpl(k, btn){
  const t=TEMPLATES[k];if(!t)return;
  const newline = String.fromCharCode(10);
  const expandLines = value => String(value || '').replace(/\\\\n/g, newline);
  const setField = (id, value)=>{
    const field = document.getElementById(id);
    if(!field) return;
    field.value = value || '';
    field.dispatchEvent(new Event('input', {bubbles:true}));
  };
  setField('f_sku', t.sku);
  setField('f_cat', t.cat);
  setField('f_name', t.name);
  setField('f_color', t.color);
  setField('f_aud', t.aud);
  setField('f_sp', expandLines(t.sp));
  setField('f_sc', expandLines(t.sc));
  // 高亮选中
  document.querySelectorAll('.template-chips .chip').forEach(c=>c.classList.remove('active'));
  if(btn) btn.classList.add('active');
}

function installCounterPill(fieldId, pillId, goodMin, goodMax, unitLabel){
  const field = document.getElementById(fieldId);
  if(!field) return;
  let pill = document.getElementById(pillId);
  if(!pill){
    pill = document.createElement('span');
    pill.id = pillId;
    pill.className = 'counter-pill';
    const host = document.createElement('div');
    host.className = 'field-note';
    host.appendChild(document.createElement('span'));
    host.appendChild(pill);
    field.insertAdjacentElement('afterend', host);
  }
  const render = ()=>{
    const count = field.value.split(/\\r?\\n/).map(v=>v.trim()).filter(Boolean).length;
    pill.textContent = `${count} ${unitLabel}`;
    pill.className = 'counter-pill';
    if(count >= goodMin && count <= goodMax){
      pill.classList.add('good');
    }else if(count === 0){
      pill.classList.add('bad');
    }else{
      pill.classList.add('warn');
    }
  };
  field.addEventListener('input', render);
  render();
}

const formEl = document.getElementById('form');
const submitBtn = document.getElementById('submitBtn');
const submitBtnLabel = document.getElementById('submitBtnLabel');
installCounterPill('f_sp', 'spCountPill', 5, 7, '条');
installCounterPill('f_sc', 'scCountPill', 2, 5, '个场景');
if(formEl && submitBtn && submitBtnLabel){
  formEl.addEventListener('submit', e=>{
    if(submitBtn.dataset.submitting === '1'){
      e.preventDefault();
      return;
    }
    submitBtn.dataset.submitting = '1';
    submitBtn.disabled = true;
    submitBtnLabel.textContent = '已提交，正在创建任务...';
  });
}
</script>
</body></html>"""


# ============================================================================
#  Result page
# ============================================================================
RESULT_HTML = """<!DOCTYPE html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · ContentFactory</title>
<style>""" + COMMON_CSS + """
.shell{max-width:1280px;margin:0 auto;padding:0 24px}
.page-header{padding:32px 0 20px;display:flex;justify-content:space-between;align-items:flex-end;gap:24px;flex-wrap:wrap}
.page-title{font-size:24px;font-weight:700;letter-spacing:-.02em;margin-bottom:4px}
.page-sub{font-size:13px;color:var(--slate-500);font-family:"JetBrains Mono",Consolas,monospace}

.progress-card{
  background:linear-gradient(135deg,#fff,#fafbfc);
  border:1px solid var(--slate-200);border-radius:14px;
  padding:24px 28px;margin-bottom:20px;box-shadow:var(--shadow-sm);
}
.progress-top{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:16px}
.progress-num{font-size:32px;font-weight:700;letter-spacing:-.02em;line-height:1}
.progress-num .total{color:var(--slate-300);font-weight:500}
.progress-num .label{font-size:12px;color:var(--slate-500);font-weight:500;margin-left:8px}
.bar-wrap{position:relative}
.bar{height:6px;background:var(--slate-100);border-radius:999px;overflow:hidden}
.bar-fill{
  height:100%;border-radius:999px;
  background:linear-gradient(90deg,var(--indigo) 0%,var(--pink) 100%);
  transition:width .5s var(--ease);
  position:relative;overflow:hidden;
}
.bar-fill::after{
  content:"";position:absolute;top:0;left:0;right:0;bottom:0;
  background:linear-gradient(90deg,transparent,rgba(255,255,255,.4),transparent);
  animation:shine 2s infinite;
}
@keyframes shine{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:20px}
.stat{padding:10px 0}
.stat-v{font-size:18px;font-weight:600;color:var(--slate-900);font-feature-settings:"tnum"}
.stat-l{font-size:11px;color:var(--slate-400);text-transform:uppercase;letter-spacing:.05em;margin-top:2px}
.poll-state{
  margin-top:16px;padding:14px 16px;border-radius:12px;border:1px solid var(--slate-200);
  background:#fff;display:flex;justify-content:space-between;gap:16px;align-items:flex-start;
}
.poll-copy{min-width:0}
.poll-title{font-size:13px;font-weight:600;color:var(--slate-900);margin-bottom:3px}
.poll-sub{font-size:12px;color:var(--slate-500);line-height:1.6}
.poll-state.poll-ok{border-color:rgba(16,185,129,.18);background:rgba(16,185,129,.05)}
.poll-state.poll-warn{border-color:rgba(245,158,11,.24);background:rgba(245,158,11,.08)}
.poll-state.poll-error{border-color:rgba(239,68,68,.24);background:rgba(239,68,68,.08)}
@media(max-width:640px){
  .stats{grid-template-columns:repeat(2,1fr)}
  .poll-state{flex-direction:column}
}

/* story strip — 视觉化"图视频如何串起来" */
.story-strip{
  display:flex;align-items:center;gap:10px;
  background:#fff;border:1px solid var(--slate-200);border-radius:14px;
  padding:18px 22px;margin-bottom:16px;box-shadow:var(--shadow-sm);
  overflow-x:auto;
}
.story-step{display:flex;flex-direction:column;align-items:center;text-align:center;min-width:130px;flex:1}
.story-step-key{position:relative}
.story-step-key::after{
  content:"关键";position:absolute;top:-8px;right:-2px;
  background:linear-gradient(135deg,var(--indigo),var(--pink));color:#fff;
  font-size:9px;font-weight:600;padding:2px 7px;border-radius:99px;
  letter-spacing:.05em;
}
.story-icon{
  width:42px;height:42px;border-radius:12px;
  display:flex;align-items:center;justify-content:center;font-size:20px;
  margin-bottom:8px;
}
.story-label{font-size:12px;font-weight:600;color:var(--slate-900);margin-bottom:2px}
.story-desc{font-size:11px;color:var(--slate-500);line-height:1.4}
.story-desc a{color:var(--indigo);font-weight:500}
.story-desc a:hover{text-decoration:underline}
.story-arr{color:var(--slate-300);font-size:18px;flex-shrink:0}
@media(max-width:700px){
  .story-strip{flex-direction:column;align-items:stretch}
  .story-arr{transform:rotate(90deg);margin:0 auto}
}

.link-img7{
  background:linear-gradient(135deg,rgba(99,102,241,.3),rgba(236,72,153,.3));
  padding:1px 8px;border-radius:6px;cursor:pointer;
  border-bottom:1px dashed rgba(255,255,255,.4);
}
.link-img7:hover{background:linear-gradient(135deg,rgba(99,102,241,.5),rgba(236,72,153,.5))}
.vc-link{margin-left:auto;background:linear-gradient(135deg,var(--indigo),var(--pink))!important;border:0!important}

/* 视频配置表单 */
.video-config{
  position:relative;z-index:1;
  background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);
  border-radius:12px;padding:22px;
  display:flex;flex-direction:column;gap:16px;
}
.vc-row{display:flex;flex-direction:column;gap:6px}
.vc-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.vc-grid .vc-row{margin:0}
@media(max-width:600px){.vc-grid{grid-template-columns:1fr}}
.vc-label{font-size:11px;font-weight:600;color:rgba(255,255,255,.7);text-transform:uppercase;letter-spacing:.05em}
.vc-input{
  width:100%;padding:9px 12px;
  background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.15);border-radius:8px;
  color:#fff;font-size:13px;font-family:inherit;
}
.vc-input:focus{outline:0;border-color:var(--indigo);box-shadow:0 0 0 3px rgba(99,102,241,.3)}
.vc-input option{background:#1e293b;color:#fff}
.vc-textarea{min-height:78px;resize:vertical;line-height:1.6;font-size:12px}
.vc-help{font-size:11px;color:rgba(255,255,255,.5);margin-top:2px}
.vc-submit{
  align-self:flex-start;font-size:14px;padding:12px 22px;
  box-shadow:0 4px 20px rgba(99,102,241,.5);
}
.vc-cost{font-size:11px;color:rgba(255,255,255,.5);text-align:left}
.vc-hint{font-size:11px;color:rgba(255,255,255,.75);line-height:1.6}
.vc-presets{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.vc-preset{
  display:flex;flex-direction:column;align-items:flex-start;justify-content:flex-start;
  width:100%;padding:10px 12px;border-radius:14px;
  border:1px solid rgba(255,255,255,.16);background:rgba(255,255,255,.08);
  color:#fff;font-size:11px;font-weight:600;transition:all .15s var(--ease);text-align:left;
}
.vc-preset:hover{background:rgba(255,255,255,.16);border-color:rgba(255,255,255,.26)}
.vc-preset.is-active{
  background:linear-gradient(135deg,var(--indigo),var(--pink));
  border-color:transparent;
  box-shadow:0 8px 20px rgba(99,102,241,.32);
}
.vc-preset:disabled{opacity:.45;cursor:not-allowed}
.vc-preset-title{font-size:12px;font-weight:700;line-height:1.25}
.vc-preset-sub{font-size:10px;line-height:1.45;color:rgba(255,255,255,.66)}
.vc-preset.is-active .vc-preset-sub{color:rgba(255,255,255,.92)}
@media(max-width:680px){.vc-presets{grid-template-columns:1fr}}

/* 模拟生成中 */
.video-generating{
  background:#000;border-radius:10px;
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:14px;padding:40px;color:#fff;
  max-width:280px;margin:0 auto;aspect-ratio:9/16;
  position:relative;overflow:hidden;
}
.video-generating::before{
  content:"";position:absolute;inset:0;
  background:linear-gradient(135deg,rgba(99,102,241,.3),rgba(236,72,153,.3));
  animation:pulse 2s ease-in-out infinite;
}
.gen-spinner{
  width:48px;height:48px;border:3px solid rgba(255,255,255,.2);border-top-color:#fff;
  border-radius:50%;animation:spin 1s linear infinite;z-index:1;
}
.gen-text{font-size:14px;font-weight:600;z-index:1}
.gen-sub{font-size:11px;color:rgba(255,255,255,.7);z-index:1;text-align:center;line-height:1.5}
.gen-progress-bar{
  width:80%;height:4px;background:rgba(255,255,255,.2);border-radius:99px;overflow:hidden;z-index:1;
}
.gen-progress-fill{height:100%;background:linear-gradient(90deg,var(--indigo),var(--pink));border-radius:99px;transition:width .3s}

/* 图片卡 #07 高亮 */
.img-card.is-keyframe{
  border:2px solid transparent;
  background:linear-gradient(#fff,#fff) padding-box,
             linear-gradient(135deg,var(--indigo),var(--pink)) border-box;
  box-shadow:0 0 0 4px rgba(99,102,241,.1),0 8px 24px rgba(236,72,153,.2);
}
.img-card.is-keyframe::before{
  content:"🎬 视频首帧";
  position:absolute;top:8px;left:8px;z-index:2;
  background:linear-gradient(135deg,var(--indigo),var(--pink));color:#fff;
  font-size:10px;font-weight:600;padding:4px 10px;border-radius:99px;
  box-shadow:0 4px 12px rgba(99,102,241,.4);
  letter-spacing:.02em;
}
.img-card.is-keyframe.flash{
  animation:flashPulse 1.2s ease-out;
}
@keyframes flashPulse{
  0%{box-shadow:0 0 0 0 rgba(99,102,241,.6),0 8px 24px rgba(236,72,153,.2)}
  70%{box-shadow:0 0 0 16px rgba(99,102,241,0),0 8px 24px rgba(236,72,153,.2)}
  100%{box-shadow:0 0 0 4px rgba(99,102,241,.1),0 8px 24px rgba(236,72,153,.2)}
}

/* video showcase */
.video-showcase{
  background:linear-gradient(135deg,#1e293b 0%,#0f172a 100%);
  color:#fff;border-radius:18px;padding:26px 28px 30px;margin-bottom:20px;
  position:relative;overflow:hidden;
}
.video-showcase::before{
  content:"";position:absolute;top:-80px;right:-80px;width:300px;height:300px;
  background:radial-gradient(circle,rgba(236,72,153,.3) 0%,transparent 70%);border-radius:50%;
}
.video-header{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:18px;position:relative;z-index:1}
.video-title{font-size:15px;font-weight:600;margin-bottom:4px}
.video-sub{font-size:12px;color:var(--slate-400)}
.video-stage{
  position:relative;z-index:1;
  display:grid;grid-template-columns:minmax(360px,1.32fr) minmax(280px,.68fr);
  gap:22px;align-items:stretch;
}
.video-stage-main,.video-stage-side{min-width:0}
.video-stage-side{display:flex;flex-direction:column;gap:14px}
.video-preview-panel{
  min-height:100%;
  background:rgba(255,255,255,.04);
  border:1px solid rgba(255,255,255,.08);
  border-radius:18px;
  padding:18px;
  display:flex;align-items:center;justify-content:center;
}
#videoPreviewWell{
  width:100%;
  min-height:100%;
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
}
.video-preview-shell{
  width:min(100%,460px);
  margin:0 auto;
  display:flex;flex-direction:column;gap:14px;
}
.video-preview-top{
  width:100%;
  display:flex;flex-direction:column;justify-content:center;align-items:center;gap:8px;
  text-align:center;
}
.video-preview-bottom{
  width:100%;
  display:flex;flex-direction:column;justify-content:center;align-items:center;gap:8px;
  text-align:center;
}
.video-preview-title{font-size:14px;font-weight:700;color:#fff;text-align:center}
.video-preview-meta{font-size:11px;line-height:1.6;color:rgba(255,255,255,.7);text-align:center}
.video-floating-tag{
  display:inline-flex;align-items:center;gap:6px;
  padding:6px 10px;border-radius:999px;
  background:linear-gradient(135deg,rgba(99,102,241,.28),rgba(236,72,153,.22));
  border:1px solid rgba(255,255,255,.12);
  color:#fff;font-size:11px;font-weight:600;
}
.video-floating-tag.ghost{
  background:rgba(255,255,255,.06);
  color:rgba(255,255,255,.72);
}
.video-poster-frame{
  position:relative;overflow:hidden;border-radius:16px;aspect-ratio:9/16;
  width:100%;
  background:#0b1120;
  margin:0 auto;
  box-shadow:0 20px 40px rgba(0,0,0,.32);
}
.video-poster-frame img{
  width:100%;height:100%;
  object-fit:contain;object-position:center center;
  display:block;background:#0b1120;
}
.video-preview-empty{
  width:min(100%,460px);aspect-ratio:9/16;border-radius:16px;
  background:linear-gradient(180deg,rgba(255,255,255,.08),rgba(255,255,255,.03));
  border:1px dashed rgba(255,255,255,.16);
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px;
  padding:26px;text-align:center;
  margin:0 auto;
}
.video-preview-empty-icon{
  width:54px;height:54px;border-radius:18px;
  display:flex;align-items:center;justify-content:center;
  background:linear-gradient(135deg,rgba(99,102,241,.28),rgba(236,72,153,.24));
  font-size:24px;
}
.video-preview-empty-title{font-size:15px;font-weight:700}
.video-preview-empty-sub{font-size:12px;line-height:1.7;color:rgba(255,255,255,.7)}
.video-side-card{
  background:rgba(255,255,255,.05);
  border:1px solid rgba(255,255,255,.1);
  border-radius:16px;
  padding:16px 18px;
}
.video-side-title{
  font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
  color:rgba(255,255,255,.58);margin-bottom:12px;
}
.video-strategy-current{
  padding:14px 16px;border-radius:14px;
  background:linear-gradient(135deg,rgba(99,102,241,.14),rgba(236,72,153,.1));
  border:1px solid rgba(255,255,255,.08);
  margin-bottom:12px;
}
.video-strategy-kicker{
  font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
  color:rgba(255,255,255,.52);margin-bottom:6px;
}
.video-strategy-name{font-size:16px;font-weight:700;color:#fff;margin-bottom:4px}
.video-strategy-desc{font-size:12px;line-height:1.6;color:rgba(255,255,255,.72)}
.video-mini-list{display:flex;flex-direction:column;gap:10px}
.video-mini-item{
  display:flex;align-items:flex-start;gap:10px;
  font-size:12px;line-height:1.58;color:rgba(255,255,255,.8);
}
.video-mini-bullet{
  flex:0 0 auto;
  width:20px;height:20px;border-radius:50%;
  display:flex;align-items:center;justify-content:center;
  background:rgba(255,255,255,.08);
  color:#fff;font-size:10px;font-weight:700;margin-top:1px;
}
.video-kpi-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.video-kpi{
  padding:12px;border-radius:12px;background:rgba(255,255,255,.05);
  border:1px solid rgba(255,255,255,.06);
}
.video-kpi-label{
  font-size:10px;letter-spacing:.06em;text-transform:uppercase;
  color:rgba(255,255,255,.5);margin-bottom:6px;
}
.video-kpi-value{font-size:15px;font-weight:700;color:#fff}
.video-kpi-sub{font-size:11px;line-height:1.45;color:rgba(255,255,255,.58);margin-top:4px}
.video-prompt-preview{
  margin-top:12px;padding:12px 14px;border-radius:12px;
  background:rgba(15,23,42,.46);border:1px solid rgba(255,255,255,.05);
  font-size:12px;line-height:1.58;color:rgba(255,255,255,.8);
  max-height:152px;overflow:auto;
}
.video-actions-stack{display:flex;flex-direction:column;gap:10px;margin-top:14px}
.video-actions-row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.video-actions-stack .btn{justify-content:center}
.video-input-compact{min-height:0}
.video-wrap{
  position:relative;z-index:1;
  background:#000;border-radius:10px;overflow:hidden;
  display:flex;align-items:center;justify-content:center;
  max-width:440px;width:100%;margin:0 auto;
  aspect-ratio:9/16;
  box-shadow:0 20px 40px rgba(0,0,0,.4);
}
.video-wrap video{
  width:100%;height:100%;
  object-fit:contain;object-position:center center;
  background:#0b1120;
}
.video-overlay-info{
  position:absolute;top:12px;left:12px;right:12px;z-index:4;
  display:flex;justify-content:space-between;align-items:flex-start;gap:8px;pointer-events:none;
}
.vc-btn{
  background:rgba(255,255,255,.2);backdrop-filter:blur(10px);
  color:#fff;padding:5px 12px;border-radius:99px;font-size:11px;font-weight:500;
  border:1px solid rgba(255,255,255,.2);
}
.vc-btn:hover{background:rgba(255,255,255,.3)}
.vc-meta{color:rgba(255,255,255,.7);font-size:10px;font-family:monospace}
select.vc-btn{appearance:none;-webkit-appearance:none;padding-right:18px;cursor:pointer}
select.vc-btn option{background:#1e293b;color:#fff}

/* 大 CTA：播放完整成片 */
.play-full-btn{
  position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
  z-index:5;
  background:rgba(255,255,255,.95);backdrop-filter:blur(12px);
  border-radius:99px;padding:14px 22px 14px 18px;
  display:flex;align-items:center;gap:12px;
  box-shadow:0 10px 30px rgba(0,0,0,.4),0 4px 8px rgba(0,0,0,.2);
  transition:all .2s var(--ease);
  cursor:pointer;
}
.play-full-btn:hover{transform:translate(-50%,-50%) scale(1.05);box-shadow:0 14px 40px rgba(0,0,0,.5)}
.play-full-btn .pf-icon{
  width:36px;height:36px;border-radius:50%;
  background:linear-gradient(135deg,var(--indigo),var(--pink));color:#fff;
  display:flex;align-items:center;justify-content:center;font-size:14px;
}
.play-full-btn .pf-label{font-size:13px;font-weight:600;color:var(--slate-900);line-height:1.2}
.play-full-btn .pf-sub{font-size:10px;color:var(--slate-500);line-height:1.2;display:block}
.play-full-btn .pf-label-wrap{display:flex;flex-direction:column}

/* 播放中变小 */
.play-full-btn.playing{
  top:auto;bottom:60px;left:50%;
  transform:translateX(-50%);
  padding:8px 16px 8px 12px;
}
.play-full-btn.playing:hover{transform:translateX(-50%) scale(1.05)}
.play-full-btn.playing .pf-icon{width:24px;height:24px;font-size:11px}
.play-full-btn.playing .pf-label{font-size:11px}
.play-full-btn.playing .pf-sub{display:none}
.video-generating-overlay{
  position:absolute;inset:0;z-index:3;
  background:linear-gradient(180deg,rgba(15,23,42,.2),rgba(15,23,42,.78));
  display:flex;align-items:center;justify-content:center;padding:24px;
}
.video-generating-card{
  width:min(100%,230px);
  background:rgba(255,255,255,.14);backdrop-filter:blur(14px);
  border:1px solid rgba(255,255,255,.16);
  border-radius:20px;padding:20px 18px;
  display:flex;flex-direction:column;align-items:center;gap:12px;text-align:center;
}
.video-generating-card .gen-progress-bar{width:100%}
@media(max-width:920px){
  .video-stage{grid-template-columns:1fr}
  .video-actions-row,.video-kpi-grid{grid-template-columns:1fr}
}

.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;gap:12px;flex-wrap:wrap}
.tabs{display:flex;gap:4px;background:var(--slate-100);padding:3px;border-radius:8px}
.tab{
  padding:6px 14px;border-radius:6px;font-size:12px;font-weight:500;
  color:var(--slate-600);cursor:pointer;transition:all .15s var(--ease);
  display:flex;align-items:center;gap:5px;
}
.tab .count{font-size:10px;color:var(--slate-400);background:#fff;padding:1px 5px;border-radius:99px}
.tab.active{background:#fff;color:var(--slate-900);box-shadow:var(--shadow-sm)}
.tab.active .count{color:var(--indigo)}

.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px;margin-bottom:80px}
.img-card,.img-ph{
  position:relative;aspect-ratio:1;
  background:#fff;border:1px solid var(--slate-200);border-radius:12px;
  overflow:hidden;
  transition:all .2s var(--ease);
  animation:slideUp .4s var(--ease) backwards;
}
.img-card:hover{transform:translateY(-3px);box-shadow:var(--shadow-lg);border-color:var(--indigo)}
.img-card img{width:100%;height:100%;object-fit:cover;display:block}
.img-card .ovr{
  position:absolute;inset:0;
  background:linear-gradient(180deg,transparent 50%,rgba(0,0,0,.85) 100%);
  display:flex;flex-direction:column;justify-content:flex-end;padding:14px;
  opacity:0;transition:opacity .2s var(--ease);
  pointer-events:none;
}
.img-card:hover .ovr{opacity:1;pointer-events:auto}
.img-card .meta{color:#fff;font-size:11px;margin-bottom:8px;display:flex;align-items:center;gap:6px}
.img-card .meta .badge{
  background:rgba(255,255,255,.2);padding:2px 8px;border-radius:99px;font-weight:500;
}
.img-card .actions{display:flex;gap:6px}
.img-card .actions button{
  flex:1;padding:6px 8px;border-radius:6px;font-size:11px;font-weight:500;
  background:rgba(255,255,255,.95);color:var(--slate-900);
  display:flex;align-items:center;justify-content:center;gap:4px;
}
.img-card .actions button:hover{background:#fff}
.img-card .actions .approve:hover{background:var(--green);color:#fff}
.img-card .actions .reject:hover{background:var(--red);color:#fff}
.img-card .actions .approve.is-active{background:var(--green);color:#fff}
.img-card .actions .reject.is-active{background:var(--red);color:#fff}

/* approved/rejected card states */
.img-card.approved{border:3px solid var(--green)!important;box-shadow:0 0 0 4px rgba(16,185,129,.15),0 8px 24px rgba(16,185,129,.2)}
.img-card.approved::after{
  content:"✓";
  position:absolute;top:8px;right:8px;z-index:3;
  width:28px;height:28px;border-radius:50%;
  background:var(--green);color:#fff;
  display:flex;align-items:center;justify-content:center;
  font-size:14px;font-weight:700;
  box-shadow:0 4px 12px rgba(16,185,129,.4);
  animation:popIn .25s var(--ease);
}
.img-card.rejected{border:3px solid var(--red)!important;opacity:.55;filter:grayscale(.4)}
.img-card.rejected::after{
  content:"✕";
  position:absolute;top:8px;right:8px;z-index:3;
  width:28px;height:28px;border-radius:50%;
  background:var(--red);color:#fff;
  display:flex;align-items:center;justify-content:center;
  font-size:14px;font-weight:700;
  box-shadow:0 4px 12px rgba(239,68,68,.4);
  animation:popIn .25s var(--ease);
}
@keyframes popIn{from{transform:scale(0);opacity:0}to{transform:scale(1);opacity:1}}

/* toast */
.toast{
  position:fixed;top:80px;left:50%;transform:translateX(-50%) translateY(-20px);
  padding:10px 20px;border-radius:99px;color:#fff;font-size:13px;font-weight:500;
  background:var(--slate-800);box-shadow:0 10px 30px rgba(0,0,0,.3);
  opacity:0;pointer-events:none;transition:all .2s var(--ease);z-index:200;
}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}

.img-ph{
  border:2px dashed var(--slate-200);background:var(--slate-50);
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  color:var(--slate-400);font-size:11px;gap:8px;
}
.img-ph .spin{
  width:18px;height:18px;border:2px solid var(--slate-200);border-top-color:var(--indigo);
  border-radius:50%;animation:spin 0.8s linear infinite;
}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes slideUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}

/* sticky bottom action bar */
.action-bar{
  position:fixed;bottom:0;left:0;right:0;
  background:rgba(255,255,255,.92);backdrop-filter:blur(12px);
  border-top:1px solid var(--slate-200);
  padding:14px 24px;display:none;justify-content:space-between;align-items:center;z-index:40;
}
.action-bar.visible{display:flex}
.action-summary{font-size:13px;color:var(--slate-700)}
.action-summary strong{color:var(--slate-900)}
.action-buttons{display:flex;gap:8px}
@media(max-width:640px){
  .action-bar{padding:12px 16px;flex-direction:column;align-items:stretch;gap:10px}
  .action-buttons{display:grid;grid-template-columns:1fr 1fr;gap:8px}
  .action-buttons .btn:last-child{grid-column:1/-1}
}

/* lightbox */
.lightbox{
  position:fixed;inset:0;background:rgba(15,23,42,.92);z-index:100;
  display:none;align-items:center;justify-content:center;
}
.lightbox.open{display:flex}
.lightbox img{max-width:80vw;max-height:72vh;object-fit:contain;border-radius:8px;box-shadow:0 30px 60px rgba(0,0,0,.5)}
.lightbox-close{position:absolute;top:24px;right:24px;color:#fff;font-size:24px;cursor:pointer;width:40px;height:40px;display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,.1);border-radius:50%}
.lightbox-info{position:absolute;top:24px;left:50%;transform:translateX(-50%);color:#fff;font-size:13px;background:rgba(0,0,0,.5);padding:8px 16px;border-radius:99px;backdrop-filter:blur(8px)}
.lightbox-nav{position:absolute;top:50%;transform:translateY(-50%);color:#fff;width:48px;height:48px;display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,.1);border-radius:50%;cursor:pointer;font-size:20px}
.lightbox-nav:hover{background:rgba(255,255,255,.2)}
.lightbox-prev{left:24px}.lightbox-next{right:24px}
/* lightbox 底部操作栏 */
.lightbox-actions{
  position:absolute;bottom:24px;left:50%;transform:translateX(-50%);
  display:flex;gap:8px;z-index:101;
}
.lb-btn{
  padding:10px 18px;border-radius:99px;font-size:13px;font-weight:500;
  background:rgba(255,255,255,.95);color:var(--slate-900);cursor:pointer;
  display:inline-flex;align-items:center;gap:6px;
  border:0;backdrop-filter:blur(10px);transition:all .15s var(--ease);
}
.lb-btn:hover{transform:translateY(-2px);box-shadow:0 8px 20px rgba(0,0,0,.4)}
.lb-approve:hover{background:var(--green);color:#fff}
.lb-reject:hover{background:var(--red);color:#fff}
.lb-approve.is-active{background:var(--green);color:#fff}
.lb-reject.is-active{background:var(--red);color:#fff}
.lb-key{background:linear-gradient(135deg,var(--indigo),var(--pink))!important;color:#fff!important}
.lb-key:hover{box-shadow:0 8px 24px rgba(99,102,241,.5)}

/* keyframe pick button on card */
.img-card .actions{gap:4px}
.img-card .actions button{
  flex:1;padding:6px 4px;font-size:11px;
}
.img-card .kf-pick{
  background:rgba(255,255,255,.95);color:var(--indigo)!important;font-size:13px!important;
  padding:6px 8px;
}
.img-card .kf-pick:hover{
  background:linear-gradient(135deg,var(--indigo),var(--pink))!important;
  color:#fff!important;
}

/* video config flash on keyframe pick */
.video-showcase.flash-yellow{
  animation:flashYellow 1.2s ease-out;
}
@keyframes flashYellow{
  0%{box-shadow:0 0 0 0 rgba(99,102,241,.6),0 0 0 6px rgba(236,72,153,.5)}
  70%{box-shadow:0 0 0 12px transparent,0 0 0 18px transparent}
  100%{box-shadow:0 0 0 0 transparent}
}

.err-card{background:#fef2f2;border-left:4px solid var(--red);padding:18px 22px;border-radius:10px;margin-bottom:20px}
.err-title{color:#991b1b;font-weight:600;font-size:14px;margin-bottom:4px}
.err-msg{color:#b91c1c;font-size:13px}
.err-help{margin-top:8px;font-size:12px;color:#7f1d1d;line-height:1.6}
.reject-dialog{position:fixed;inset:0;z-index:160;display:none;align-items:center;justify-content:center;background:rgba(15,23,42,.54);padding:20px}
.reject-dialog.open{display:flex}
.reject-panel{width:min(520px,100%);background:#fff;border-radius:16px;box-shadow:0 30px 80px rgba(15,23,42,.28);border:1px solid var(--slate-200);overflow:hidden}
.reject-head{padding:18px 20px;border-bottom:1px solid var(--slate-100);display:flex;justify-content:space-between;gap:12px;align-items:flex-start}
.reject-title{font-size:17px;font-weight:800;color:var(--slate-900)}
.reject-sub{font-size:12px;color:var(--slate-500);line-height:1.6;margin-top:4px}
.reject-close{border:0;background:var(--slate-100);color:var(--slate-600);width:30px;height:30px;border-radius:50%;cursor:pointer;font-size:18px;line-height:1}
.reject-body{padding:18px 20px;display:flex;flex-direction:column;gap:12px}
.reject-field{display:flex;flex-direction:column;gap:6px}
.reject-field span{font-size:12px;font-weight:700;color:var(--slate-600)}
.reject-field select,.reject-field textarea,.reject-field input{width:100%;border:1px solid var(--slate-200);border-radius:10px;padding:10px 12px;font:inherit;font-size:13px;color:var(--slate-900);outline:none;background:#fff}
.reject-field textarea{min-height:92px;resize:vertical;line-height:1.6}
.reject-foot{padding:14px 20px;border-top:1px solid var(--slate-100);display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap}
</style></head><body>

<nav class="nav">
  <div class="nav-left">
    <a class="logo" href="/"><span class="logo-mark">CF</span>ContentFactory</a>
    <div class="crumbs"><span>·</span> <a href="/history" style="color:var(--slate-500)">历史任务</a> <span>·</span> <strong>{task_id_short}</strong> <span>·</span> 候选审核</div>
  </div>
  <div class="nav-right">
    <a href="/history" class="btn btn-ghost" style="font-size:12px">🕐 历史任务</a>
    <a href="/review" class="btn btn-ghost" style="font-size:12px">待审核</a>
    <a href="/settings" class="btn btn-ghost" style="font-size:12px">模型配置</a>
    <a href="/" class="btn btn-ghost">+ 新建任务</a>
    <div class="avatar">J</div>
  </div>
</nav>

<div class="shell">

<header class="page-header">
  <div>
    <div class="page-title">{title}</div>
    <div class="page-sub">task_id: {task_id}</div>
  </div>
  <a href="{n8n_editor_url}" class="btn btn-secondary">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="6" cy="6" r="3"/><circle cx="18" cy="6" r="3"/><circle cx="12" cy="18" r="3"/><line x1="6" y1="9" x2="12" y2="15"/><line x1="18" y1="9" x2="12" y2="15"/></svg>
    看 N8N 画布
  </a>
</header>

{error_block}

{progress_block}

</div>

<!-- sticky action bar (shown after all done) -->
<div class="action-bar" id="actionBar">
  <div class="action-summary">11 张候选已生成 · <strong>0 通过 / 0 驳回</strong> · 平均 ¥0.30/张</div>
  <div class="action-buttons">
    <button class="btn btn-ghost" id="regenRejectedBtn" onclick="regenerateRejected()">⟲ 重新生成驳回的</button>
    <button class="btn btn-secondary" id="exportZipBtn" onclick="exportZip()">⤓ 导出 ZIP</button>
    <button class="btn btn-success" id="approveAllBtn" onclick="approveAllCandidates()">✓ 全部通过</button>
  </div>
</div>

<div class="reject-dialog" id="rejectDialog" aria-hidden="true">
  <div class="reject-panel" role="dialog" aria-modal="true" aria-labelledby="rejectDialogTitle">
    <div class="reject-head">
      <div>
        <div class="reject-title" id="rejectDialogTitle">驳回原因</div>
        <div class="reject-sub" id="rejectDialogSub">把需要修正的点写清楚，重新生成会自动带上这些约束。</div>
      </div>
      <button type="button" class="reject-close" onclick="closeRejectDialog()">×</button>
    </div>
    <div class="reject-body">
      <label class="reject-field">
        <span>问题分类</span>
        <select id="rejectReasonCategory">
          <option value="garment_identity">服装不一致</option>
          <option value="color_material">颜色 / 面料偏差</option>
          <option value="logo_text">出现品牌 / 文字</option>
          <option value="composition">构图或视角不合适</option>
          <option value="model_body">人物 / 身体异常</option>
          <option value="quality">质感或清晰度不足</option>
          <option value="other">其他</option>
        </select>
      </label>
      <label class="reject-field">
        <span>需要修正</span>
        <textarea id="rejectComment" maxlength="700" placeholder="例如：胸前出现了 Nike 标志；上衣颜色偏成亮蓝；裤腰结构和前几张不一致。"></textarea>
      </label>
      <label class="reject-field">
        <span>保持不变</span>
        <input id="rejectPreserve" maxlength="360" value="保持同一件服装：品类、版型、主色、面料、缝线、口袋、腰头/领口和无品牌标签策略都不要变。" />
      </label>
    </div>
    <div class="reject-foot">
      <button type="button" class="btn btn-secondary" onclick="closeRejectDialog()">取消</button>
      <button type="button" class="btn btn-primary" onclick="confirmRejectDialog()">确认驳回</button>
    </div>
  </div>
</div>

<!-- lightbox -->
<div class="lightbox" id="lightbox">
  <div class="lightbox-close" onclick="closeLightbox()">✕</div>
  <div class="lightbox-nav lightbox-prev" onclick="navLightbox(-1)">‹</div>
  <img id="lightboxImg" src="" alt="" />
  <div class="lightbox-nav lightbox-next" onclick="navLightbox(1)">›</div>
  <div class="lightbox-info" id="lightboxInfo"></div>
</div>

{poll_script}

</body></html>"""


VIDEO_HAS = """
<div class="video-showcase">
  <div class="video-header">
    <div>
      <div class="video-title">🎬 视频成片 · 由 <span class="link-img7" onclick="highlightSeven(event)">候选图 #7（瑜伽馆）</span> 动画化得到</div>
      <div class="video-sub">同一模特、同一服装、同一场景 · 12 秒 · Video Provider image-to-video</div>
    </div>
    <span class="pill-status pill-success"><span class="dot"></span>已就绪</span>
  </div>
  <div class="video-wrap">
    <video id="demoVideo" autoplay loop muted playsinline preload="auto">
      <source src="/video/yn-bra-001-12s-coherent.mp4" type="video/mp4">
    </video>
    <button class="play-full-btn" id="playFullBtn" onclick="playFullShowcase()">
      <span class="pf-icon">▶</span>
      <span class="pf-label">播放完整成片</span>
      <span class="pf-sub">视频 + 旁白同步</span>
    </button>
    <div class="video-controls">
      <button class="vc-btn" onclick="toggleVO()" id="voBtn">🔊 旁白</button>
      <select class="vc-btn" id="voicePicker" onchange="changeVoice()">
        <option value="zh-CN-XiaoxiaoNeural">晓晓（女）</option>
        <option value="zh-CN-XiaoyiNeural">晓伊（女）</option>
        <option value="zh-CN-YunxiNeural">云希（男）</option>
      </select>
      <span class="vc-meta" id="vcMeta">9:16 · 720p</span>
      <button class="vc-btn vc-link" onclick="highlightSeven(event)">↓ 看首帧图</button>
    </div>
  </div>
  <audio id="voAudio" preload="auto">
    <source id="voSource" src="/audio/voiceover_zh-CN-XiaoxiaoNeural.mp3" type="audio/mpeg">
  </audio>
</div>
"""

VIDEO_EMPTY = """
<div class="video-showcase video-empty">
  <div class="video-header">
    <div>
      <div class="video-title">🎬 视频成片</div>
      <div class="video-sub">候选图审核通过后，挑任意一张作为视频首帧 · Video Provider image-to-video · 单条约 90-180 秒</div>
    </div>
    <span class="pill-status" style="background:var(--slate-100);color:var(--slate-500)"><span class="dot"></span>等待配置</span>
  </div>
  <div class="video-config">
    <div class="vc-row">
      <label class="vc-label">📌 选首帧图</label>
      <select id="kfPicker" class="vc-input">
        <option value="1">第 1 张 · 商品正面（白底）</option>
        <option value="2">第 2 张 · 商品侧面</option>
        <option value="3">第 3 张 · 商品背面</option>
        <option value="4">第 4 张 · 面料特写</option>
        <option value="5">第 5 张 · 拉链动作</option>
        <option value="6">第 6 张 · Logo 特写</option>
        <option value="7" selected>第 7 张 · 瑜伽馆场景</option>
        <option value="8">第 8 张 · 健身房训练</option>
        <option value="9">第 9 张 · 跑步公园</option>
        <option value="10">第 10 张 · 户外山林</option>
        <option value="11">第 11 张 · 海边沙滩</option>
      </select>
    </div>
    <div class="vc-row">
      <label class="vc-label">📝 视频 Prompt（动作 / 镜头 / 节奏）</label>
      <textarea id="videoPrompt" class="vc-input vc-textarea" placeholder="描述视频的动作和镜头...">From the opening shot, slow camera push-in to medium shot. Model gracefully transitions to warrior pose with arms extended, then reverse warrior. Golden morning light streaming through arched window. Smooth fluid motion, end on calm centered pose facing camera with slight smile.</textarea>
      <div class="vc-presets">
        <button type="button" class="vc-preset" onclick="applyVideoPromptPreset('showcase')">稳态展示</button>
        <button type="button" class="vc-preset" onclick="applyVideoPromptPreset('dynamic')">动态短片</button>
        <button type="button" class="vc-preset" onclick="applyVideoPromptPreset('texture')">质感特写</button>
        <button type="button" class="vc-preset" onclick="applyVideoPromptPreset('social')">社媒广告</button>
      </div>
      <div class="vc-help">系统已根据您的产品资料预填，可直接编辑或重写</div>
    </div>
    <div class="vc-row vc-grid">
      <div>
        <label class="vc-label">⏱ 时长</label>
        <select id="videoDuration" class="vc-input">
          <option value="6">6 秒</option>
          <option value="12" selected>12 秒（推荐）</option>
          <option value="24">24 秒</option>
        </select>
      </div>
      <div>
        <label class="vc-label">📐 比例</label>
        <select id="videoRatio" class="vc-input">
          <option value="9:16" selected>9:16 竖屏（TikTok）</option>
          <option value="1:1">1:1 方形</option>
          <option value="16:9">16:9 横屏</option>
        </select>
      </div>
      <div>
        <label class="vc-label">🎤 旁白</label>
        <select id="videoVoice" class="vc-input">
          <option value="zh-CN-XiaoxiaoNeural" selected>晓晓（女）</option>
          <option value="zh-CN-XiaoyiNeural">晓伊（女）</option>
          <option value="zh-CN-YunxiNeural">云希（男）</option>
        </select>
      </div>
    </div>
    <button class="btn btn-primary vc-submit" onclick="genVideoMock()" id="genVideoBtn" disabled>
      🎬 提交生成视频成片
    </button>
    <div class="vc-cost">预计耗时 90-180 秒 · 按视频模型时长计费</div>
  </div>
</div>
"""


VIDEO_EMPTY = """
<div class="video-showcase video-empty">
  <div class="video-header">
    <div>
      <div class="video-title">🎞 视频成片</div>
      <div class="video-sub">候选图审核通过后，选择一张作为首帧，再提交 Video Provider image-to-video 生成 6 / 12 / 24 秒短视频。</div>
    </div>
    <span class="pill-status" style="background:var(--slate-100);color:var(--slate-500)"><span class="dot"></span>等待配置</span>
  </div>
  <div class="video-config">
    <div class="vc-row">
      <label class="vc-label">🎯 选首帧图</label>
      <select id="kfPicker" class="vc-input">
        <option value="">等待候选图生成后自动填充</option>
      </select>
      <div class="vc-hint" id="videoConfigHint">至少生成 1 张候选图后，系统会自动把可用首帧填到这里。</div>
    </div>
    <div class="vc-row">
      <label class="vc-label">📝 视频 Prompt（动作 / 镜头 / 节奏）</label>
      <textarea id="videoPrompt" class="vc-input vc-textarea" placeholder="系统会根据商品资料、首帧和视频风格自动预填 prompt，您也可以手动改写。"></textarea>
      <div class="vc-presets">
        <button type="button" class="vc-preset" data-preset="showcase" onclick="applyVideoPromptPreset('showcase')">稳态展示</button>
        <button type="button" class="vc-preset" data-preset="dynamic" onclick="applyVideoPromptPreset('dynamic')">动态短片</button>
        <button type="button" class="vc-preset" data-preset="texture" onclick="applyVideoPromptPreset('texture')">质感特写</button>
        <button type="button" class="vc-preset" data-preset="social" onclick="applyVideoPromptPreset('social')">社媒广告</button>
      </div>
      <div class="vc-help">系统会基于任务快照预填默认 prompt，您也可以一键切换成不同风格版本。</div>
    </div>
    <div class="vc-row vc-grid">
      <div>
        <label class="vc-label">⏱ 时长</label>
        <select id="videoDuration" class="vc-input">
          <option value="6">6 秒</option>
          <option value="12" selected>12 秒（推荐）</option>
          <option value="24">24 秒</option>
        </select>
      </div>
      <div>
        <label class="vc-label">📐 比例</label>
        <select id="videoRatio" class="vc-input">
          <option value="9:16" selected>9:16 竖屏（TikTok / Reels）</option>
          <option value="1:1">1:1 方形</option>
          <option value="16:9">16:9 横屏</option>
        </select>
      </div>
      <div>
        <label class="vc-label">🗣 旁白</label>
        <select id="videoVoice" class="vc-input">
          <option value="zh-CN-XiaoxiaoNeural" selected>晓晓（女）</option>
          <option value="zh-CN-XiaoyiNeural">晓伊（女）</option>
          <option value="zh-CN-YunxiNeural">云希（男）</option>
        </select>
      </div>
    </div>
    <button class="btn btn-primary vc-submit" onclick="genVideoMock()" id="genVideoBtn" disabled>
      🎞 提交生成视频成片
    </button>
    <div class="vc-cost">预计耗时 90-180 秒 · 页面会保存当前首帧、prompt、比例和时长，刷新后可继续。</div>
  </div>
</div>
"""

PROGRESS_BLOCK = """
<div class="progress-card">
  <div class="progress-top">
    <div>
      <div class="progress-num"><span id="count">0</span><span class="total"> / <span id="countTotal">11</span></span><span class="label">候选已生成</span></div>
    </div>
    <span class="pill-status pill-running" id="statusPill">
      <span class="dot"></span>
      <span id="statusText">正在生成</span>
    </span>
  </div>
  <div class="bar-wrap"><div class="bar"><div id="bar" class="bar-fill" style="width:0%"></div></div></div>
  <div class="stats">
    <div class="stat"><div class="stat-v" id="elapsed">0s</div><div class="stat-l">已用时</div></div>
    <div class="stat"><div class="stat-v" id="rate">-</div><div class="stat-l">平均出图速度</div></div>
    <div class="stat"><div class="stat-v" id="cost">¥0.00</div><div class="stat-l">已花费</div></div>
    <div class="stat"><div class="stat-v" id="eta">-</div><div class="stat-l">预计剩余</div></div>
  </div>
  <div class="poll-state poll-ok" id="pollState">
    <div class="poll-copy">
      <div class="poll-title" id="pollStateTitle">正在连接生成服务...</div>
      <div class="poll-sub" id="pollStateSub">页面会每 2 秒查询一次任务状态，并在异常时给出排查提示。</div>
    </div>
    <button type="button" class="btn btn-secondary" id="pollRetryBtn" onclick="retryPoll()" style="display:none">重新检查状态</button>
  </div>
</div>

<!-- Story strip：让客户一眼看明白图视频是同一套素材联动 -->
<div class="story-strip">
  <div class="story-step">
    <div class="story-icon" style="background:rgba(99,102,241,.15);color:var(--indigo)">📝</div>
    <div class="story-label">您的录入</div>
    <div class="story-desc">SKU 信息 + 卖点 + 场景</div>
  </div>
  <div class="story-arr">→</div>
  <div class="story-step">
    <div class="story-icon" style="background:rgba(236,72,153,.15);color:var(--pink)">🖼️</div>
    <div class="story-label">11 张候选图</div>
    <div class="story-desc">商品图 6 + 场景图 5</div>
  </div>
  <div class="story-arr">→</div>
  <div class="story-step story-step-key">
    <div class="story-icon" style="background:linear-gradient(135deg,var(--indigo),var(--pink));color:#fff;box-shadow:0 4px 12px rgba(99,102,241,.4)">🎯</div>
    <div class="story-label">4 张重点审核</div>
    <div class="story-desc">确认风格后，再从候选里选首帧做视频</div>
  </div>
  <div class="story-arr">→</div>
  <div class="story-step">
    <div class="story-icon" style="background:rgba(16,185,129,.15);color:var(--green)">🎬</div>
    <div class="story-label">12 秒成片视频</div>
    <div class="story-desc">人物 / 服装 / 场景 完全一致</div>
  </div>
</div>

{video_block}

<div class="toolbar">
  <div class="tabs">
    <div class="tab active" onclick="switchTab('all', event)">全部 <span class="count" id="cnt-all">0</span></div>
    <div class="tab" onclick="switchTab('product', event)">商品图 <span class="count" id="cnt-product">0</span></div>
    <div class="tab" onclick="switchTab('scene', event)">场景图 <span class="count" id="cnt-scene">0</span></div>
  </div>
</div>

<div class="grid" id="img-grid"></div>
"""


POLL_SCRIPT = """
<script>
const TASK_ID = "{task_id}";
const t0 = Date.now();
let allCands = [];
let curTab = 'all';

const $ = id => document.getElementById(id);
const grid = $('img-grid'), countEl = $('count'), barEl = $('bar');
const elapsedEl = $('elapsed'), rateEl = $('rate'), costEl = $('cost'), etaEl = $('eta');
const statusPill = $('statusPill'), statusText = $('statusText'), actionBar = $('actionBar');
const pollState = $('pollState'), pollStateTitle = $('pollStateTitle');
const pollStateSub = $('pollStateSub'), pollRetryBtn = $('pollRetryBtn');
let consecutivePollErrors = 0;
let pollFinished = false;
let pollTimer = null;

// 初始 11 个 placeholder
function renderPlaceholders(){
  grid.innerHTML='';
  for(let i=0;i<11;i++){
    const d=document.createElement('div');d.className='img-ph';
    d.innerHTML=`<div class="spin"></div><div>第 ${i+1} 张生成中</div>`;
    d.id='slot-'+(i+1);grid.appendChild(d);
  }
}
renderPlaceholders();

function switchTab(tab, ev){
  curTab=tab;
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  ev.currentTarget.classList.add('active');
  rerender();
}

function classify(c){
  const s=(c.shot||'').toLowerCase();
  if(s.includes('scene')||s.includes('yoga')||s.includes('park')||s.includes('mountain')||s.includes('beach')||s.includes('gym'))return 'scene';
  return 'product';
}

let currentKeyframe = 7;  // 默认第 7 张
function imgCardHTML(c, idx){
  const t=classify(c);
  const isKey = (idx+1)===currentKeyframe;
  const cls = 'img-card' + (isKey?' is-keyframe':'');
  return `<div class="${cls}" id="slot-card-${idx+1}" style="animation-delay:${idx*30}ms">
    <img src="${c.url}" loading="lazy" alt="候选 ${idx+1}" onclick="openLightbox(${idx})" />
    <div class="ovr">
      <div class="meta">
        <span class="badge">#${idx+1}</span>
        <span>${t==='scene'?'场景图':'商品图'}</span>
        ${c.shot?`<span style="opacity:.7">· ${c.shot}</span>`:''}
      </div>
      <div class="actions">
        <button class="approve" onclick="markApproval(${idx},'approve',event)" title="审核通过">✓</button>
        <button class="reject" onclick="markApproval(${idx},'reject',event)" title="驳回">✕</button>
        <button class="kf-pick" onclick="pickAsKeyframe(${idx+1},event)" title="用此图生成视频">🎬</button>
      </div>
    </div>
  </div>`;
}

function pickAsKeyframe(seqNo, ev){
  if(ev) ev.stopPropagation();
  currentKeyframe = seqNo;
  // 同步 dropdown
  const picker = document.getElementById('kfPicker');
  if(picker) picker.value = seqNo;
  // 重渲染图卡（让徽章移到新选的）
  rerender();
  // 关闭 lightbox（如果开着）
  if(document.getElementById('lightbox').classList.contains('open')) closeLightbox();
  // 滚到视频配置区 + 闪烁
  const showcase = document.querySelector('.video-showcase');
  if(showcase){
    showcase.scrollIntoView({behavior:'smooth', block:'start'});
    showcase.classList.remove('flash-yellow');
    void showcase.offsetWidth;
    showcase.classList.add('flash-yellow');
  }
  showToast(`🎬 已选第 ${seqNo} 张作为视频首帧`, 'indigo');
}

function highlightSeven(ev){
  if(ev) ev.preventDefault();
  const target = document.getElementById('slot-card-7');
  if(!target){ alert('图 #7 还没生成出来'); return; }
  // 切到"全部"或"场景"tab，确保图 7 显示
  const sceneTab = Array.from(document.querySelectorAll('.tab')).find(t=>t.textContent.includes('场景'));
  // 简单起见切到全部
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tab')[0].classList.add('active');
  curTab = 'all';
  rerender();
  // 等渲染完滚动 + 闪烁
  setTimeout(()=>{
    const fresh = document.getElementById('slot-card-7');
    if(!fresh) return;
    fresh.scrollIntoView({behavior:'smooth', block:'center'});
    fresh.classList.remove('flash');
    void fresh.offsetWidth;  // 强制 reflow 让动画重启
    fresh.classList.add('flash');
  }, 100);
}

function rerender(){
  const filtered=allCands.filter(c=>curTab==='all'||classify(c)===curTab);
  if(filtered.length===0){
    if(allCands.length===0){renderPlaceholders();return;}
    grid.innerHTML='<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--slate-400);font-size:13px">该分类下暂无候选，先回到“全部”查看，或继续等待更多候选生成。</div>';
    return;
  }
  grid.innerHTML=filtered.map((c,i)=>imgCardHTML(c,allCands.indexOf(c))).join('');
}

function setPollState(kind, title, sub, showRetry){
  pollState.className = `poll-state ${kind}`;
  pollStateTitle.textContent = title;
  pollStateSub.textContent = sub;
  pollRetryBtn.style.display = showRetry ? 'inline-flex' : 'none';
}

function retryPoll(){
  if(pollFinished){
    pollFinished = false;
  }
  if(pollTimer){
    clearTimeout(pollTimer);
    pollTimer = null;
  }
  consecutivePollErrors = 0;
  setPollState('poll-ok', '正在重新检查状态...', '会继续轮询任务和候选回写状态。', false);
  poll();
}

let approvals={approve:0,reject:0,marked:{}};  // marked: idx → 'approve'/'reject'
function markApproval(idx,act,ev){
  ev.stopPropagation();
  // 防重复点击：如果已经标记过同样动作，撤销
  const prev=approvals.marked[idx];
  if(prev===act){
    approvals[act]--;
    delete approvals.marked[idx];
  } else {
    if(prev) approvals[prev]--;  // 撤销之前的状态
    approvals[act]++;
    approvals.marked[idx]=act;
  }
  // 重新 render 视觉
  const card=document.getElementById('slot-card-'+(idx+1));
  if(card){
    card.classList.remove('approved','rejected');
    if(approvals.marked[idx]==='approve'){card.classList.add('approved')}
    if(approvals.marked[idx]==='reject'){card.classList.add('rejected')}
  }
  // 始终更新 action bar，并显示出来
  const ab=document.getElementById('actionBar');
  ab.classList.add('visible');
  ab.querySelector('.action-summary').innerHTML=
    `${allCands.length} 张候选 · <strong style="color:var(--green-dark)">✓ ${approvals.approve} 通过</strong> / <strong style="color:var(--red)">✕ ${approvals.reject} 驳回</strong> / ${allCands.length-approvals.approve-approvals.reject} 待审`;
  // toast
  showToast(act==='approve'?`✓ 候选 #${idx+1} 已通过`:`✕ 候选 #${idx+1} 已驳回`, act==='approve'?'green':'red');
}

function showToast(msg, color){
  let t = document.getElementById('toast');
  if(!t){
    t=document.createElement('div');t.id='toast';t.className='toast';
    document.body.appendChild(t);
  }
  t.textContent=msg;
  t.style.background = color==='green'?'var(--green)':color==='red'?'var(--red)':'var(--slate-800)';
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer=setTimeout(()=>t.classList.remove('show'),1800);
}

function openLightbox(idx){
  const c=allCands[idx];if(!c)return;
  $('lightboxImg').src=c.url;
  $('lightboxInfo').textContent=`#${idx+1} / ${allCands.length} · ${classify(c)==='scene'?'场景图':'商品图'} ${c.shot?'· '+c.shot:''}`;
  // 加 lightbox 操作栏
  let bar = document.getElementById('lightboxActions');
  if(!bar){
    bar = document.createElement('div');
    bar.id='lightboxActions';bar.className='lightbox-actions';
    document.getElementById('lightbox').appendChild(bar);
  }
  bar.innerHTML = `
    <button class="lb-btn lb-approve" onclick="markApproval(${idx},'approve',event);closeLightbox()">✓ 审核通过</button>
    <button class="lb-btn lb-reject" onclick="markApproval(${idx},'reject',event);closeLightbox()">✕ 驳回</button>
    <button class="lb-btn lb-key" onclick="pickAsKeyframe(${idx+1},event)">🎬 用此图生成视频</button>
  `;
  $('lightbox').classList.add('open');$('lightbox').dataset.idx=idx;
}
function closeLightbox(){$('lightbox').classList.remove('open')}
function navLightbox(dir){
  const cur=parseInt($('lightbox').dataset.idx||0);
  const next=(cur+dir+allCands.length)%allCands.length;
  openLightbox(next);
}
document.addEventListener('keydown',e=>{
  if(!$('lightbox').classList.contains('open'))return;
  if(e.key==='Escape')closeLightbox();
  if(e.key==='ArrowLeft')navLightbox(-1);
  if(e.key==='ArrowRight')navLightbox(1);
});
$('lightbox').addEventListener('click',e=>{if(e.target.id==='lightbox')closeLightbox()});

// Edge TTS 高质量神经声 - 预生成的 MP3
function toggleVO(){
  const a=document.getElementById('voAudio');
  const btn=document.getElementById('voBtn');
  if(a.paused){
    a.currentTime=0;
    a.play().then(()=>{btn.textContent='⏸ 旁白'}).catch(e=>console.error(e));
  } else {
    a.pause(); a.currentTime=0;
    btn.textContent='🔊 旁白';
  }
}
function changeVoice(){
  const sel=document.getElementById('voicePicker').value;
  const a=document.getElementById('voAudio');
  const src=document.getElementById('voSource');
  const wasPlay=!a.paused;
  src.src=`/audio/voiceover_${sel}.mp3`;
  a.load();
  if(wasPlay) a.play();
}

// "播放完整成片"：视频从头 + 旁白从头 + 音量渐入，完美同步
let isFullPlaying = false;
function playFullShowcase(){
  const v=document.getElementById('demoVideo');
  const a=document.getElementById('voAudio');
  const btn=document.getElementById('playFullBtn');
  const labelEl=btn.querySelector('.pf-label');
  const iconEl=btn.querySelector('.pf-icon');

  if(isFullPlaying){
    // 暂停
    v.pause();a.pause();
    isFullPlaying=false;
    btn.classList.remove('playing');
    iconEl.textContent='▶';labelEl.textContent='播放完整成片';
    return;
  }

  // 从头播
  v.currentTime=0;
  a.currentTime=0;
  a.volume=0;
  v.muted=true;  // 视频静音（它本来就没音轨）
  v.play();
  a.play().then(()=>{
    isFullPlaying=true;
    btn.classList.add('playing');
    iconEl.textContent='⏸';labelEl.textContent='暂停';

    // 音量渐入 0→1 over 300ms
    const t0=performance.now();
    function fadeIn(){
      const elapsed=performance.now()-t0;
      const v0=Math.min(elapsed/300,1);
      a.volume=v0;
      if(v0<1) requestAnimationFrame(fadeIn);
    }
    fadeIn();
  }).catch(e=>{
    console.error('播放失败：',e);
    alert('浏览器拦了自动播放，再点一次按钮');
  });
}

// 视频空状态：真调 Video Provider API 出片
let _genVideoVoice = 'zh-CN-XiaoxiaoNeural';
async function genVideoMock(){
  const showcase = document.querySelector('.video-showcase');
  if(!showcase) return;
  // 收集表单值
  const seq = parseInt(document.getElementById('kfPicker').value)||7;
  const prompt = (document.getElementById('videoPrompt').value||'').trim();
  const duration = parseInt(document.getElementById('videoDuration').value)||12;
  const ratio = document.getElementById('videoRatio').value||'9:16';
  _genVideoVoice = document.getElementById('videoVoice').value||'zh-CN-XiaoxiaoNeural';

  if(!prompt){ alert('请填写视频 prompt'); return; }

  // 切换到生成中 UI
  showcase.innerHTML = `
    <div class="video-header">
      <div>
        <div class="video-title">🎬 视频成片 · 生成中</div>
        <div class="video-sub">用候选图 #${seq} 作为首帧 · ${duration}s · ${ratio} · Video Provider image-to-video</div>
      </div>
      <span class="pill-status pill-running"><span class="dot"></span>生成中</span>
    </div>
    <div class="video-generating">
      <div class="gen-spinner"></div>
      <div class="gen-text" id="genText">生成比例匹配的视频首帧...</div>
      <div class="gen-sub" id="genSub">已用 0s</div>
      <div class="gen-progress-bar"><div class="gen-progress-fill" id="genFill" style="width:0%"></div></div>
    </div>
  `;

  // 1. 提交
  let seedanceTid = null;
  try{
    const sub = await fetch('/api/gen-video', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({task_id: TASK_ID, seq, prompt, duration, ratio})
    });
    const subData = await sub.json();
    if(subData.error){
      showGenError('提交失败: '+subData.error);return;
    }
    seedanceTid = subData.seedance_task_id;
    document.getElementById('genText').textContent = '已提交，视频 Provider 渲染中...';
    document.getElementById('genSub').textContent = `video task: ${seedanceTid.slice(0,16)}...`;
  }catch(e){
    showGenError('提交异常: '+e.message);return;
  }

  // 2. 轮询
  const t0 = Date.now();
  const pollInterval = 5000;  // 5s 一次
  const maxWait = 240000;     // 最长 4 分钟
  let lastPct = 5;
  const poll = async ()=>{
    const elapsed = (Date.now()-t0)/1000;
    if(elapsed*1000 > maxWait){
      showGenError('生成超时（>4min），请重试'); return;
    }
    // 更新进度（部分视频 provider 没有真实进度，按 elapsed 估算）
    const estPct = Math.min(8 + elapsed/180*85, 95);
    if(estPct > lastPct){
      lastPct = estPct;
      const fill = document.getElementById('genFill');
      if(fill) fill.style.width = estPct+'%';
    }
    const sub = document.getElementById('genSub');
    if(sub) sub.textContent = `已用 ${Math.round(elapsed)}s · 预计总时长 90-180s`;

    try{
      const r = await fetch(`/api/gen-video-status?id=${seedanceTid}`);
      const d = await r.json();
      if(d.status === 'succeeded' && d.video_url){
        document.getElementById('genFill').style.width = '100%';
        document.getElementById('genText').textContent = '✓ 完成';
        setTimeout(()=>showVideoFromReal(d.video_url, seq, prompt, duration, ratio), 400);
        return;
      }
      if(d.status === 'failed'){
        showGenError('视频生成失败: '+(d.error||'unknown'));return;
      }
      // 状态仍在 running / queued, 继续轮询
    }catch(e){
      // 网络抖动忽略，继续
    }
    setTimeout(poll, pollInterval);
  };
  poll();
}

function showGenError(msg){
  const showcase = document.querySelector('.video-showcase');
  if(!showcase) return;
  showcase.innerHTML = `
    <div class="video-header">
      <div>
        <div class="video-title">🎬 视频成片 · 失败</div>
        <div class="video-sub">${msg}</div>
      </div>
      <span class="pill-status pill-failed"><span class="dot"></span>失败</span>
    </div>
    <div class="video-empty-state" style="padding:24px">
      <button class="btn btn-primary" onclick="location.reload()">↻ 重试</button>
    </div>
  `;
}

function showVideoFromReal(videoUrl, seq, prompt, duration, ratio){
  const showcase = document.querySelector('.video-showcase');
  if(!showcase) return;
  showcase.classList.remove('video-empty');
  showcase.innerHTML = `
    <div class="video-header">
      <div>
        <div class="video-title">🎬 视频成片 · 由 <span class="link-img7" onclick="pickAsKeyframe(${seq},event)">候选图 #${seq}</span> 动画化得到</div>
        <div class="video-sub">${duration} 秒 · ${ratio} · Video Provider image-to-video · 刚刚生成</div>
      </div>
      <span class="pill-status pill-success"><span class="dot"></span>刚刚完成</span>
    </div>
    <div class="video-wrap">
      <video id="demoVideo" autoplay loop muted playsinline preload="auto">
        <source src="${videoUrl}" type="video/mp4">
      </video>
      <button class="play-full-btn" id="playFullBtn" onclick="playFullShowcase()">
        <span class="pf-icon">▶</span>
        <span class="pf-label">播放完整成片</span>
        <span class="pf-sub">视频 + 旁白同步</span>
      </button>
      <div class="video-controls">
        <button class="vc-btn" onclick="toggleVO()" id="voBtn">🔊 旁白</button>
        <select class="vc-btn" id="voicePicker" onchange="changeVoice()">
          <option value="zh-CN-XiaoxiaoNeural">晓晓（女）</option>
          <option value="zh-CN-XiaoyiNeural">晓伊（女）</option>
          <option value="zh-CN-YunxiNeural">云希（男）</option>
        </select>
        <span class="vc-meta">${ratio} · 720p</span>
        <button class="vc-btn vc-link" onclick="pickAsKeyframe(${seq},event)">↓ 看首帧图</button>
      </div>
    </div>
    <audio id="voAudio" preload="auto">
      <source id="voSource" src="/audio/voiceover_${_genVideoVoice}.mp3" type="audio/mpeg">
    </audio>
  `;
  // 设 voice picker 默认值
  const vp = document.getElementById('voicePicker');
  if(vp){ vp.value = _genVideoVoice; }
}

// 旁白结束：UI 复位 + dropdown 监听同步首帧
document.addEventListener('DOMContentLoaded',()=>{
  const a=document.getElementById('voAudio');
  if(a){
    a.addEventListener('ended',()=>{
      if(isFullPlaying){
        isFullPlaying=false;
        const btn=document.getElementById('playFullBtn');
        btn.classList.remove('playing');
        btn.querySelector('.pf-icon').textContent='▶';
        btn.querySelector('.pf-label').textContent='重播完整成片';
      }
    });
  }
  const picker=document.getElementById('kfPicker');
  if(picker){
    picker.addEventListener('change',()=>{
      currentKeyframe = parseInt(picker.value)||7;
      rerender();
      showToast(`🎬 已选第 ${currentKeyframe} 张作为视频首帧`, 'indigo');
    });
  }
});

async function poll(){
  if(pollFinished)return;
  try{
    const res=await fetch(`/api/status?task_id=${TASK_ID}`);
    if(!res.ok){
      throw new Error(`HTTP ${res.status}`);
    }
    const data=await res.json();
    if(data.error){
      throw new Error(data.error);
    }
    consecutivePollErrors = 0;
    allCands=data.candidates||[];
    const status=data.status||'pending';

    const n=allCands.length;
    countEl.textContent=n;
    barEl.style.width=(n/11*100)+'%';
    costEl.textContent='¥'+(n*0.30).toFixed(2);

    const cntProd=allCands.filter(c=>classify(c)==='product').length;
    const cntScene=allCands.filter(c=>classify(c)==='scene').length;
    $('cnt-all').textContent=n;$('cnt-product').textContent=cntProd;$('cnt-scene').textContent=cntScene;

    const elapsedSec=(Date.now()-t0)/1000;
    if(n>0)rateEl.textContent=(elapsedSec/n).toFixed(1)+'s/张';
    if(n>0&&n<11){
      const remaining=(11-n)*(elapsedSec/n);
      etaEl.textContent=remaining<60?Math.round(remaining)+'s':Math.round(remaining/60)+'m'+Math.round(remaining%60)+'s';
    } else if(n===11){etaEl.textContent='✓ 完成'}

    if(n===0 && elapsedSec >= 60 && status !== 'failed'){
      setPollState('poll-warn', '超过 60 秒仍未返回候选', '请检查 N8N 最近执行、数据库连接和外部 API 凭据。', true);
    } else if(n===0){
      setPollState('poll-ok', '生成服务已连接，等待第一张候选', '任务已创建后，首批候选通常会在 10-30 秒内开始回写。', false);
    } else if(n < 11){
      setPollState('poll-ok', '候选持续回写中', `当前已回写 ${n}/11 张；页面会继续自动刷新。`, false);
    } else {
      setPollState('poll-ok', '候选已全部回写', '可以继续重点审核，或直接从候选中挑一张转视频。', false);
    }

    if(status==='succeeded'){
      statusPill.classList.replace('pill-running','pill-success');
      statusText.textContent='生成完成';
      actionBar.classList.add('visible');
      $('actionBar').querySelector('.action-summary').innerHTML=
        `<strong>${n} 张候选</strong>已生成 · 总耗时 ${Math.round(elapsedSec)}s · 总花费 ¥${(n*0.30).toFixed(2)}`;
      setPollState('poll-ok', '任务已完成', '候选回写已经结束，可以开始审核或继续生成视频。', false);
      pollFinished = true;
    } else if(status==='failed'){
      statusPill.classList.replace('pill-running','pill-failed');
      statusText.textContent='失败';
      setPollState('poll-error', '任务执行失败', '请打开 N8N 画布查看失败节点；修复后可重新触发本任务。', true);
      pollFinished = true;
    } else if(status==='pending'){
      statusText.textContent='等待执行';
    } else {
      statusText.textContent='正在生成';
    }

    rerender();

    if(status==='succeeded'||status==='failed')return;
  }catch(e){
    consecutivePollErrors += 1;
    const severe = consecutivePollErrors >= 3;
    setPollState(
      severe ? 'poll-error' : 'poll-warn',
      severe ? '生成服务连接异常' : '状态查询暂时波动',
      `${e.message || e}。${severe ? '请检查 N8N、数据库或容器状态。' : '系统会自动继续重试。'}`,
      severe,
    );
  }
  pollTimer = setTimeout(poll,2000);
}

setInterval(()=>{
  const sec=Math.floor((Date.now()-t0)/1000);
  const m=Math.floor(sec/60),s=sec%60;
  elapsedEl.textContent=m>0?`${m}m ${s}s`:`${s}s`;
},1000);

poll();
</script>
"""


POLL_SCRIPT = """
<script>
const TASK_ID = "{task_id}";
const t0 = Date.now();
let allCands = [];
let curTab = 'all';
let requestedCount = 11;
let taskMeta = {parameters:{}};
let currentKeyframe = 0;
let videoDraftHydrated = false;
let consecutivePollErrors = 0;
let pollFinished = false;
let pollTimer = null;
let videoJobTimer = null;
let _genVideoVoice = 'zh-CN-XiaoxiaoNeural';
let approvals = {approve:0,reject:0,marked:{}};
let reviewBusy = new Set();
let pendingRejectReview = null;
let frozenElapsedSec = null;

const VIDEO_DRAFT_KEY = `cf_video_draft:${TASK_ID}`;
const VIDEO_JOB_KEY = `cf_video_job:${TASK_ID}`;

const $ = id => document.getElementById(id);
const grid = $('img-grid'), countEl = $('count'), countTotalEl = $('countTotal'), barEl = $('bar');
const elapsedEl = $('elapsed'), rateEl = $('rate'), costEl = $('cost'), etaEl = $('eta');
const statusPill = $('statusPill'), statusText = $('statusText'), actionBar = $('actionBar');
const pollState = $('pollState'), pollStateTitle = $('pollStateTitle');
const pollStateSub = $('pollStateSub'), pollRetryBtn = $('pollRetryBtn');

function readStorage(key){
  try{return JSON.parse(localStorage.getItem(key) || 'null')}catch(_){return null}
}

function writeStorage(key, value){
  try{localStorage.setItem(key, JSON.stringify(value))}catch(_){}
}

function removeStorage(key){
  try{localStorage.removeItem(key)}catch(_){}
}

function renderElapsed(secValue){
  if(!elapsedEl)return;
  const sec = Math.max(0, Math.floor(secValue || 0));
  const m = Math.floor(sec / 60), s = sec % 60;
  elapsedEl.textContent = m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function getRequestedCount(){
  return Math.max(1, parseInt(requestedCount, 10) || 11);
}

function getVideoDefaults(){
  return (taskMeta.parameters && taskMeta.parameters.video_defaults) || {};
}

function getInputSnapshot(){
  return (taskMeta.parameters && taskMeta.parameters.input_snapshot) || {};
}

function getVideoMotionDefault(){
  return (taskMeta.parameters && taskMeta.parameters.video_motion) || 'showcase';
}

function getVideoMotionLabel(){
  return (taskMeta.parameters && taskMeta.parameters.video_motion_label) || '稳态展示';
}

function getVideoPromptSeed(){
  return getVideoDefaults().prompt_seed || '';
}

function seqNoOf(c, fallbackIndex){
  const seq = parseInt(c && c.sequence_no, 10);
  return Number.isFinite(seq) && seq > 0 ? seq : fallbackIndex + 1;
}

function currentKeyframeCandidate(){
  return allCands.find((c, idx) => seqNoOf(c, idx) === currentKeyframe) || null;
}

function pickDefaultKeyframe(){
  const preferred = [currentKeyframe, 7].find(seq => allCands.some((c, idx) => seqNoOf(c, idx) === seq));
  if(preferred)return preferred;
  const sceneCand = allCands.find(c => classify(c) === 'scene');
  if(sceneCand)return seqNoOf(sceneCand, allCands.indexOf(sceneCand));
  return allCands.length ? seqNoOf(allCands[0], 0) : 0;
}

function renderPlaceholderCard(seqNo){
  return `<div class="img-ph" id="slot-${seqNo}"><div class="spin"></div><div>第 ${seqNo} 张生成中</div></div>`;
}

function renderPlaceholders(){
  if(!grid)return;
  const total = getRequestedCount();
  grid.innerHTML = Array.from({length: total}, (_, idx) => renderPlaceholderCard(idx + 1)).join('');
}
renderPlaceholders();

function switchTab(tab, ev){
  curTab = tab;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  if(ev && ev.currentTarget)ev.currentTarget.classList.add('active');
  rerender();
}

function classify(c){
  const s = ((c && c.shot) || '').toLowerCase();
  if(s.includes('scene') || s.includes('yoga') || s.includes('park') || s.includes('mountain') || s.includes('beach') || s.includes('gym') || s.includes('outdoor'))return 'scene';
  return 'product';
}

function cardStateClass(idx){
  const state = approvals.marked[idx];
  if(state === 'approve')return ' approved';
  if(state === 'reject')return ' rejected';
  return '';
}

function syncApprovalsFromCandidates(){
  approvals = {approve:0,reject:0,marked:{}};
  allCands.forEach((candidate, idx)=>{
    if(candidate.status === 'approved'){
      approvals.approve += 1;
      approvals.marked[idx] = 'approve';
    } else if(candidate.status === 'rejected'){
      approvals.reject += 1;
      approvals.marked[idx] = 'reject';
    }
  });
}

function imgCardHTML(c, idx){
  const seq = seqNoOf(c, idx);
  const t = classify(c);
  const isKey = seq === currentKeyframe;
  const state = approvals.marked[idx] || '';
  const approveText = state === 'approve' ? '取消' : '通过';
  const rejectText = state === 'reject' ? '取消' : '驳回';
  const approveCls = state === 'approve' ? 'approve is-active' : 'approve';
  const rejectCls = state === 'reject' ? 'reject is-active' : 'reject';
  const cls = `img-card${isKey ? ' is-keyframe' : ''}${cardStateClass(idx)}`;
  return `<div class="${cls}" id="slot-card-${seq}" style="animation-delay:${idx * 30}ms">
    <img src="${c.url}" loading="lazy" alt="候选图 ${seq}" onclick="openLightbox(${idx})" />
    <div class="ovr">
      <div class="meta">
        <span class="badge">#${seq}</span>
        <span>${t === 'scene' ? '场景图' : '商品图'}</span>
        ${c.shot ? `<span style="opacity:.7">· ${c.shot}</span>` : ''}
      </div>
      <div class="actions">
        <button class="${approveCls}" onclick="markApproval(${idx},'approve',event)" title="${state === 'approve' ? '取消通过' : '审核通过'}">${approveText}</button>
        <button class="${rejectCls}" onclick="markApproval(${idx},'reject',event)" title="${state === 'reject' ? '取消驳回' : '驳回'}">${rejectText}</button>
        <button class="kf-pick" onclick="pickAsKeyframe(${seq},event)" title="用此图生成视频">首帧</button>
      </div>
    </div>
  </div>`;
}

function pickAsKeyframe(seqNo, ev){
  if(ev)ev.stopPropagation();
  currentKeyframe = seqNo;
  const picker = $('kfPicker');
  if(picker)picker.value = String(seqNo);
  rerender();
  saveVideoDraft();
  syncVideoControls();
  const lightbox = $('lightbox');
  if(lightbox && lightbox.classList.contains('open'))closeLightbox();
  const showcase = document.querySelector('.video-showcase');
  if(showcase){
    showcase.scrollIntoView({behavior:'smooth', block:'start'});
    showcase.classList.remove('flash-yellow');
    void showcase.offsetWidth;
    showcase.classList.add('flash-yellow');
  }
  showToast(`已将候选图 #${seqNo} 设为视频首帧`, 'indigo');
}

function highlightSeven(ev){
  if(ev)ev.preventDefault();
  const seqNo = currentKeyframe || 7;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  const firstTab = document.querySelectorAll('.tab')[0];
  if(firstTab)firstTab.classList.add('active');
  curTab = 'all';
  rerender();
  setTimeout(()=>{
    const fresh = document.getElementById(`slot-card-${seqNo}`);
    if(!fresh){ alert(`候选图 #${seqNo} 还没有生成出来`); return; }
    fresh.scrollIntoView({behavior:'smooth', block:'center'});
    fresh.classList.remove('flash');
    void fresh.offsetWidth;
    fresh.classList.add('flash');
  }, 100);
}

function rerender(){
  if(!grid)return;
  if(allCands.length === 0){ renderPlaceholders(); return; }
  const filtered = allCands.filter(c => curTab === 'all' || classify(c) === curTab);
  if(filtered.length === 0){
    grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--slate-400);font-size:13px">这个分类下暂时还没有候选图，先回到“全部”查看，或继续等待更多结果。</div>';
    return;
  }
  let html = filtered.map(c => imgCardHTML(c, allCands.indexOf(c))).join('');
  if(curTab === 'all' && allCands.length < getRequestedCount()){
    for(let seq = allCands.length + 1; seq <= getRequestedCount(); seq += 1){
      html += renderPlaceholderCard(seq);
    }
  }
  grid.innerHTML = html;
}

function createNodeFromHTML(html){
  const tpl = document.createElement('template');
  tpl.innerHTML = html.trim();
  return tpl.content.firstElementChild;
}

function candidateRenderSignature(c, idx){
  return JSON.stringify({
    seq: seqNoOf(c, idx),
    url: (c && c.url) || '',
    shot: (c && c.shot) || '',
    status: (c && c.status) || '',
    kind: classify(c),
    isKeyframe: seqNoOf(c, idx) === currentKeyframe,
    approval: approvals.marked[idx] || '',
  });
}

function ensurePlaceholderNode(seqNo){
  const existing = document.getElementById(`slot-${seqNo}`);
  if(existing)return existing;
  return createNodeFromHTML(renderPlaceholderCard(seqNo));
}

function ensureCandidateNode(c, idx){
  const seq = seqNoOf(c, idx);
  const current = document.getElementById(`slot-card-${seq}`);
  const signature = candidateRenderSignature(c, idx);
  if(current && current.dataset.signature === signature){
    return current;
  }
  const next = createNodeFromHTML(imgCardHTML(c, idx));
  next.dataset.signature = signature;
  if(current){
    current.replaceWith(next);
    return next;
  }
  const placeholder = document.getElementById(`slot-${seq}`);
  if(placeholder){
    placeholder.replaceWith(next);
    return next;
  }
  return next;
}

function syncGridChildren(nodes){
  const keepIds = new Set(nodes.map(node => node.id));
  Array.from(grid.children).forEach(child=>{
    if(!keepIds.has(child.id))child.remove();
  });
  nodes.forEach((node, idx)=>{
    const current = grid.children[idx];
    if(current !== node){
      grid.insertBefore(node, current || null);
    }
  });
}

function rerender(){
  if(!grid)return;
  if(allCands.length === 0){ renderPlaceholders(); return; }
  const filtered = allCands.filter(c => curTab === 'all' || classify(c) === curTab);
  if(filtered.length === 0){
    grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--slate-400);font-size:13px">杩欎釜鍒嗙被涓嬫殏鏃惰繕娌℃湁鍊欓€夊浘锛屽厛鍥炲埌鈥滃叏閮ㄢ€濇煡鐪嬶紝鎴栫户缁瓑寰呮洿澶氱粨鏋溿€?/div>';
    return;
  }
  if(curTab === 'all'){
    const bySeq = new Map(allCands.map((c, idx) => [seqNoOf(c, idx), {c, idx}]));
    const maxSeq = Math.max(getRequestedCount(), ...allCands.map((c, idx) => seqNoOf(c, idx)));
    const nodes = [];
    for(let seq = 1; seq <= maxSeq; seq += 1){
      const item = bySeq.get(seq);
      nodes.push(item ? ensureCandidateNode(item.c, item.idx) : ensurePlaceholderNode(seq));
    }
    syncGridChildren(nodes);
    return;
  }
  const nodes = filtered.map(c => ensureCandidateNode(c, allCands.indexOf(c)));
  syncGridChildren(nodes);
}

function setPollState(kind, title, sub, showRetry){
  if(!pollState)return;
  pollState.className = `poll-state ${kind}`;
  if(pollStateTitle)pollStateTitle.textContent = title;
  if(pollStateSub)pollStateSub.textContent = sub;
  if(pollRetryBtn)pollRetryBtn.style.display = showRetry ? 'inline-flex' : 'none';
}

function setStatusPill(bucket, label){
  if(!statusPill || !statusText)return;
  statusPill.classList.remove('pill-running','pill-success','pill-failed');
  if(bucket === 'success')statusPill.classList.add('pill-success');
  else if(bucket === 'failed')statusPill.classList.add('pill-failed');
  else statusPill.classList.add('pill-running');
  statusText.textContent = label;
}

function retryPoll(){
  pollFinished = false;
  if(pollTimer){
    clearTimeout(pollTimer);
    pollTimer = null;
  }
  consecutivePollErrors = 0;
  setPollState('poll-ok', '正在重新检查状态...', '会继续轮询任务与候选图回写情况。', false);
  poll();
}

function updateActionSummary(){
  if(!actionBar)return;
  const summary = actionBar.querySelector('.action-summary');
  if(!summary)return;
  const total = getRequestedCount();
  const pending = Math.max(allCands.length - approvals.approve - approvals.reject, 0);
  summary.innerHTML = `${allCands.length}/${total} 张候选图 · <strong style="color:var(--green-dark)">通过 ${approvals.approve}</strong> / <strong style="color:var(--red)">驳回 ${approvals.reject}</strong> / 待看 ${pending}`;
  const regenBtn = $('regenRejectedBtn');
  const exportBtn = $('exportZipBtn');
  const approveAllBtn = $('approveAllBtn');
  const approvableCount = allCands.filter(candidate => candidate.status !== 'rejected').length;
  if(regenBtn)regenBtn.disabled = approvals.reject === 0;
  if(exportBtn)exportBtn.disabled = allCands.length === 0;
  if(approveAllBtn)approveAllBtn.disabled = approvableCount === 0 || approvals.approve >= approvableCount;
  if(allCands.length > 0 || approvals.approve > 0 || approvals.reject > 0 || pollFinished){
    actionBar.classList.add('visible');
  }
}

function applyReviewResult(data){
  if(data && data.candidate){
    const candidate = data.candidate;
    const idx = allCands.findIndex(c => (c.id && c.id === candidate.id) || seqNoOf(c, 0) === Number(candidate.sequence_no));
    if(idx >= 0){
      allCands[idx] = {...allCands[idx], status: candidate.status};
    }
  }
  syncApprovalsFromCandidates();
  rerender();
  syncVideoControls();
  updateActionSummary();
  if(data && data.summary && data.summary.task_status){
    if(data.summary.task_status === 'approved')setStatusPill('success', '已全部通过');
    else if(data.summary.task_status === 'rejected')setStatusPill('failed', '已驳回');
    else if(data.summary.task_status === 'reviewing')setStatusPill('running', '审核中');
  }
}

function openRejectDialog(idx, ev){
  if(ev)ev.stopPropagation();
  const candidate = allCands[idx];
  if(!candidate)return;
  pendingRejectReview = {idx, candidate};
  const seq = seqNoOf(candidate, idx);
  const dialog = $('rejectDialog');
  const sub = $('rejectDialogSub');
  const comment = $('rejectComment');
  if(sub)sub.textContent = `候选图 #${seq} 将被标记为驳回，并把原因写入下一次重新生成。`;
  if(comment)comment.value = '';
  if(dialog){
    dialog.classList.add('open');
    dialog.setAttribute('aria-hidden', 'false');
    setTimeout(()=>comment && comment.focus(), 30);
  }
}

function closeRejectDialog(){
  const dialog = $('rejectDialog');
  if(dialog){
    dialog.classList.remove('open');
    dialog.setAttribute('aria-hidden', 'true');
  }
  pendingRejectReview = null;
}

async function confirmRejectDialog(){
  if(!pendingRejectReview)return;
  const idx = pendingRejectReview.idx;
  const reviewFeedback = {
    reason_category: ($('rejectReasonCategory') && $('rejectReasonCategory').value) || 'other',
    comment: (($('rejectComment') && $('rejectComment').value) || '').trim(),
    preserve: (($('rejectPreserve') && $('rejectPreserve').value) || '').trim(),
  };
  closeRejectDialog();
  await sendReviewAction(idx, 'reject', null, reviewFeedback);
}

async function markApproval(idx, act, ev){
  if(ev)ev.stopPropagation();
  if(act === 'reject' && approvals.marked[idx] !== 'reject'){
    openRejectDialog(idx, ev);
    return;
  }
  await sendReviewAction(idx, act, ev, {});
}

async function sendReviewAction(idx, act, ev, reviewFeedback){
  if(ev)ev.stopPropagation();
  const candidate = allCands[idx];
  if(!candidate)return;
  const seq = seqNoOf(candidate, idx);
  const busyKey = candidate.id || String(seq);
  if(reviewBusy.has(busyKey))return;
  reviewBusy.add(busyKey);
  try{
    const payload = {task_id: TASK_ID, candidate_id: candidate.id || '', seq, action: act, ...(reviewFeedback || {})};
    const res = await fetch('/api/review-candidate', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(()=>({}));
    if(!res.ok || data.error){
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    applyReviewResult(data);
    const status = data.candidate ? data.candidate.status : '';
    const color = status === 'approved' ? 'green' : status === 'rejected' ? 'red' : 'slate';
    showToast(data.message || `候选图 #${seq} 状态已更新`, color);
  }catch(err){
    alert(`审核更新失败：${err.message || err}`);
  }finally{
    reviewBusy.delete(busyKey);
  }
}

async function approveAllCandidates(){
  if(allCands.length === 0)return;
  const btn = $('approveAllBtn');
  if(btn)btn.disabled = true;
  try{
    const res = await fetch('/api/approve-all', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({task_id: TASK_ID}),
    });
    const data = await res.json().catch(()=>({}));
    if(!res.ok || data.error){
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    allCands = allCands.map(c => c.status === 'rejected' ? c : ({...c, status:'approved'}));
    syncApprovalsFromCandidates();
    rerender();
    syncVideoControls();
    updateActionSummary();
    if(data.summary && data.summary.task_status === 'approved'){
      setStatusPill('success', '已全部通过');
      setPollState('poll-ok', '候选图已全部通过', '审核决策已写入数据库，已通过素材可以导出或继续生成视频。', false);
    }else{
      setStatusPill('failed', '仍有驳回');
      setPollState('poll-warn', '未驳回候选已通过', '已驳回素材会保留驳回状态，请点击“重新生成驳回的”补齐。', false);
    }
    showToast(data.message || '已全部通过', 'green');
  }catch(err){
    alert(`全部通过失败：${err.message || err}`);
  }finally{
    updateActionSummary();
  }
}

async function regenerateRejected(){
  const rejectedIds = allCands
    .filter((candidate, idx) => approvals.marked[idx] === 'reject')
    .map(candidate => candidate.id)
    .filter(Boolean);
  if(rejectedIds.length === 0){
    showToast('没有驳回的候选图需要重新生成', 'slate');
    return;
  }
  const btn = $('regenRejectedBtn');
  if(btn)btn.disabled = true;
  try{
    const res = await fetch('/api/regenerate-rejected', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({task_id: TASK_ID, candidate_ids: rejectedIds}),
    });
    const data = await res.json().catch(()=>({}));
    if(!res.ok || data.error){
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    pollFinished = false;
    frozenElapsedSec = null;
    setStatusPill('running', '重新生成');
    setPollState('poll-ok', '驳回图已重新生成', `本轮已补 ${data.generated_count || data.rejected_count || rejectedIds.length} 张对应候选图，页面会自动刷新。`, false);
    showToast(data.message || '驳回图已重新生成', 'indigo');
    if(pollTimer){
      clearTimeout(pollTimer);
      pollTimer = null;
    }
    poll();
  }catch(err){
    alert(`重新生成失败：${err.message || err}`);
  }finally{
    updateActionSummary();
  }
}

function exportZip(){
  if(allCands.length === 0){
    showToast('还没有可导出的候选图', 'slate');
    return;
  }
  showToast(approvals.approve > 0 ? '正在导出交付包：已通过素材 + prompt + 参数 + 审核日志' : '还没有通过素材，将导出当前可审核交付包', 'indigo');
  window.location.href = `/api/export-zip?task_id=${encodeURIComponent(TASK_ID)}`;
}

function showToast(msg, color){
  let t = $('toast');
  if(!t){
    t = document.createElement('div');
    t.id = 'toast';
    t.className = 'toast';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  if(color === 'green')t.style.background = 'var(--green)';
  else if(color === 'red')t.style.background = 'var(--red)';
  else if(color === 'indigo')t.style.background = 'linear-gradient(135deg,var(--indigo),var(--pink))';
  else t.style.background = 'var(--slate-800)';
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(()=>t.classList.remove('show'), 1800);
}

function openLightbox(idx){
  const c = allCands[idx];
  if(!c)return;
  const seq = seqNoOf(c, idx);
  $('lightboxImg').src = c.url;
  $('lightboxInfo').textContent = `#${seq} / ${allCands.length} · ${classify(c) === 'scene' ? '场景图' : '商品图'}${c.shot ? ` · ${c.shot}` : ''}`;
  let bar = $('lightboxActions');
  if(!bar){
    bar = document.createElement('div');
    bar.id = 'lightboxActions';
    bar.className = 'lightbox-actions';
    $('lightbox').appendChild(bar);
  }
  const state = approvals.marked[idx] || '';
  const approveText = state === 'approve' ? '取消通过' : '审核通过';
  const rejectText = state === 'reject' ? '取消驳回' : '驳回';
  const approveCls = state === 'approve' ? 'lb-btn lb-approve is-active' : 'lb-btn lb-approve';
  const rejectCls = state === 'reject' ? 'lb-btn lb-reject is-active' : 'lb-btn lb-reject';
  bar.innerHTML = `
    <button class="${approveCls}" onclick="markApproval(${idx},'approve',event);closeLightbox()">${approveText}</button>
    <button class="${rejectCls}" onclick="markApproval(${idx},'reject',event);closeLightbox()">${rejectText}</button>
    <button class="lb-btn lb-key" onclick="pickAsKeyframe(${seq},event)">设为首帧</button>
  `;
  $('lightbox').classList.add('open');
  $('lightbox').dataset.idx = idx;
}

function closeLightbox(){ $('lightbox').classList.remove('open') }

function navLightbox(dir){
  const cur = parseInt($('lightbox').dataset.idx || 0, 10);
  const next = (cur + dir + allCands.length) % allCands.length;
  openLightbox(next);
}

document.addEventListener('keydown', e=>{
  const rejectDialog = $('rejectDialog');
  if(rejectDialog && rejectDialog.classList.contains('open')){
    if(e.key === 'Escape')closeRejectDialog();
    return;
  }
  if(!$('lightbox').classList.contains('open'))return;
  if(e.key === 'Escape')closeLightbox();
  if(e.key === 'ArrowLeft')navLightbox(-1);
  if(e.key === 'ArrowRight')navLightbox(1);
});

$('lightbox').addEventListener('click', e=>{ if(e.target.id === 'lightbox')closeLightbox() });
const rejectDialogEl = $('rejectDialog');
if(rejectDialogEl){
  rejectDialogEl.addEventListener('click', e=>{ if(e.target.id === 'rejectDialog')closeRejectDialog() });
}

function toggleVO(){
  const a = $('voAudio');
  const btn = $('voBtn');
  if(!a || !btn)return;
  if(a.paused){
    a.currentTime = 0;
    a.play().then(()=>{ btn.textContent = '停止旁白'; }).catch(e=>console.error(e));
  } else {
    a.pause();
    a.currentTime = 0;
    btn.textContent = '播放旁白';
  }
}

function changeVoice(){
  const picker = $('voicePicker');
  const a = $('voAudio');
  const src = $('voSource');
  if(!picker || !a || !src)return;
  const sel = picker.value;
  const wasPlay = !a.paused;
  src.src = `/audio/voiceover_${sel}.mp3`;
  a.load();
  if(wasPlay)a.play();
}

let isFullPlaying = false;
function playFullShowcase(){
  const v = $('demoVideo');
  const a = $('voAudio');
  const btn = $('playFullBtn');
  if(!v || !a || !btn)return;
  const labelEl = btn.querySelector('.pf-label');
  const iconEl = btn.querySelector('.pf-icon');
  if(isFullPlaying){
    v.pause();
    a.pause();
    isFullPlaying = false;
    btn.classList.remove('playing');
    if(iconEl)iconEl.textContent = '▶';
    if(labelEl)labelEl.textContent = '播放完整成片';
    return;
  }
  v.currentTime = 0;
  a.currentTime = 0;
  a.volume = 0;
  v.muted = true;
  v.play();
  a.play().then(()=>{
    isFullPlaying = true;
    btn.classList.add('playing');
    if(iconEl)iconEl.textContent = '⏸';
    if(labelEl)labelEl.textContent = '暂停';
    const fadeT0 = performance.now();
    function fadeIn(){
      const elapsed = performance.now() - fadeT0;
      const nextVolume = Math.min(elapsed / 300, 1);
      a.volume = nextVolume;
      if(nextVolume < 1)requestAnimationFrame(fadeIn);
    }
    fadeIn();
  }).catch(e=>{
    console.error('playFullShowcase failed:', e);
    alert('浏览器拦截了自动播放，请再点一次按钮。');
  });
}

function attachVideoPlaybackEvents(){
  const a = $('voAudio');
  if(!a || a.dataset.bound === '1')return;
  a.dataset.bound = '1';
  a.addEventListener('ended', ()=>{
    const playBtn = $('playFullBtn');
    if(isFullPlaying && playBtn){
      isFullPlaying = false;
      playBtn.classList.remove('playing');
      const icon = playBtn.querySelector('.pf-icon');
      const label = playBtn.querySelector('.pf-label');
      if(icon)icon.textContent = '▶';
      if(label)label.textContent = '重播完整成片';
    }
    const voBtn = $('voBtn');
    if(voBtn)voBtn.textContent = '播放旁白';
  });
}

function loadVideoDraft(){
  return readStorage(VIDEO_DRAFT_KEY) || {};
}

function saveVideoDraft(){
  const picker = $('kfPicker');
  const promptField = $('videoPrompt');
  if(!picker || !promptField)return;
  const activePreset = document.querySelector('.vc-preset.is-active');
  writeStorage(VIDEO_DRAFT_KEY, {
    seq: currentKeyframe || parseInt(picker.value || '0', 10) || 0,
    prompt: promptField.value || '',
    duration: $('videoDuration') ? $('videoDuration').value : String(getVideoDefaults().duration || 12),
    ratio: $('videoRatio') ? $('videoRatio').value : (getVideoDefaults().ratio || '9:16'),
    voice: $('videoVoice') ? $('videoVoice').value : (getVideoDefaults().voice || 'zh-CN-XiaoxiaoNeural'),
    preset: activePreset ? activePreset.dataset.preset : getVideoMotionDefault(),
    updated_at: Date.now(),
  });
}

function setActivePreset(kind){
  document.querySelectorAll('.vc-preset').forEach(btn=>{
    btn.classList.toggle('is-active', btn.dataset.preset === kind);
  });
}

const VIDEO_PRESET_META = {
  showcase: {
    label: '转化主视觉',
    angle: '用户视角',
    desc: '先把商品看清，再给动作节奏，适合详情页和高转化素材。',
    hint: '适合详情页、商城首屏和品牌主视觉视频。',
  },
  dynamic: {
    label: '平台爆点',
    angle: '增长视角',
    desc: '前两秒直接抓人，镜头推进更快，更像短视频投流素材。',
    hint: '适合抖音、Reels、投流短视频和快节奏内容分发。',
  },
  texture: {
    label: '面料质感',
    angle: '品牌视角',
    desc: '强化面料、拉链、支撑结构和近景细节，适合高客单展示。',
    hint: '适合质感表达、面料卖点和高客单产品展示。',
  },
  social: {
    label: '场景情绪',
    angle: '内容视角',
    desc: '强调人物状态、场景氛围和情绪连贯，更适合种草素材。',
    hint: '适合生活方式内容、社媒种草和场景叙事素材。',
  },
};

const VOICE_LABELS = {
  'zh-CN-XiaoxiaoNeural': '晓晓（女）',
  'zh-CN-XiaoyiNeural': '晓伊（女）',
  'zh-CN-YunxiNeural': '云希（男）',
};

function escapeHTML(value){
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[ch]));
}

function getVideoPresetMeta(kind){
  return VIDEO_PRESET_META[kind] || VIDEO_PRESET_META.showcase;
}

function getActiveVideoPresetKind(){
  const active = document.querySelector('.vc-preset.is-active');
  return active ? active.dataset.preset : getVideoMotionDefault();
}

function getVoiceLabel(value){
  return VOICE_LABELS[value] || value || '默认旁白';
}

function findCandidateBySeq(seqNo){
  return allCands.find((c, idx) => seqNoOf(c, idx) === seqNo) || null;
}

function getCandidateDescriptor(candidate, seqNo){
  if(!candidate)return `候选图 #${seqNo || '-'}`;
  const kind = classify(candidate) === 'scene' ? '场景图' : '商品图';
  return `${kind}${candidate.shot ? ` · ${candidate.shot}` : ''}`;
}

function getVideoPlatformHint(ratio){
  if(ratio === '9:16')return '适合抖音 / Reels / TikTok，建议开场 1 秒内进入主体。';
  if(ratio === '1:1')return '适合商品详情与信息流封面，建议主体构图更居中。';
  return '适合官网横版、投放 KV 或落地页首屏，建议保留左右空间。';
}

function getPromptPreviewText(prompt, fallback){
  const text = (prompt || fallback || '').replace(/\s+/g, ' ').trim();
  if(text.length <= 220)return text || '系统会根据当前策略自动生成视频 prompt。';
  return `${text.slice(0, 220)}...`;
}

function renderVoiceOptions(selectedVoice){
  return Object.entries(VOICE_LABELS).map(([value, label]) =>
    `<option value="${value}" ${value === selectedVoice ? 'selected' : ''}>${label}</option>`
  ).join('');
}

function buildVideoInsightItems(kind, candidate, ratio){
  const snap = getInputSnapshot();
  return [
    `用户视角：${candidate ? `当前首帧是候选图 #${currentKeyframe}` : '先选一张首帧图'}，建议前 1-1.5 秒先交代 ${snap.category || '商品'} 主体，再进入动作。`,
    `品牌视角：保持 ${snap.primary_color || '主色'} 服装识别、Logo 位置和人物比例稳定，避免动作过快导致服装失真。`,
    `内容视角：${getVideoPresetMeta(kind).hint}`,
    `投放视角：${getVideoPlatformHint(ratio)}`,
  ];
}

function ensureVideoConfigShell(){
  const showcase = document.querySelector('.video-showcase.video-empty');
  if(!showcase || showcase.dataset.enhanced === '1')return;
  const header = showcase.querySelector('.video-header');
  const config = showcase.querySelector('.video-config');
  if(!header || !config)return;
  const stage = document.createElement('div');
  stage.className = 'video-stage';
  stage.innerHTML = `
    <div class="video-stage-main">
      <div class="video-preview-panel">
        <div id="videoPreviewWell"></div>
      </div>
    </div>
    <div class="video-stage-side"></div>
  `;
  const side = stage.querySelector('.video-stage-side');
  side.appendChild(config);
  const support = document.createElement('div');
  support.className = 'video-side-card';
  support.innerHTML = `
    <div class="video-side-title">系统建议</div>
    <div class="video-strategy-current" id="videoStrategySummary"></div>
    <div class="video-mini-list" id="videoGuidanceList"></div>
  `;
  side.appendChild(support);
  header.insertAdjacentElement('afterend', stage);
  showcase.dataset.enhanced = '1';
}

function upgradeVideoPresetButtons(){
  document.querySelectorAll('.vc-preset').forEach(btn=>{
    const meta = getVideoPresetMeta(btn.dataset.preset);
    btn.innerHTML = `
      <span class="vc-preset-title">${meta.label}</span>
      <span class="vc-preset-sub">${meta.angle}</span>
    `;
  });
}

function renderVideoConfigSupport(){
  ensureVideoConfigShell();
  upgradeVideoPresetButtons();
  const previewWell = $('videoPreviewWell');
  const strategySummary = $('videoStrategySummary');
  const guidanceList = $('videoGuidanceList');
  const kind = getActiveVideoPresetKind();
  const preset = getVideoPresetMeta(kind);
  const ratio = (($('videoRatio') || {}).value || getVideoDefaults().ratio || '9:16');
  const duration = parseInt((($('videoDuration') || {}).value || getVideoDefaults().duration || '12'), 10) || 12;
  const voice = getVoiceLabel((($('videoVoice') || {}).value || getVideoDefaults().voice || 'zh-CN-XiaoxiaoNeural'));
  const candidate = currentKeyframeCandidate();
  if(previewWell){
    if(candidate){
      previewWell.innerHTML = `
        <div class="video-preview-shell">
          <div class="video-preview-top">
            <span class="video-floating-tag">首帧 · 候选图 #${currentKeyframe}</span>
            <span class="video-floating-tag ghost">${escapeHTML(getCandidateDescriptor(candidate, currentKeyframe))}</span>
          </div>
          <div class="video-poster-frame">
            <img src="${candidate.url}" alt="候选图 #${currentKeyframe}" />
          </div>
          <div class="video-preview-bottom">
            <div>
              <div class="video-preview-title">预计输出 ${duration} 秒成片</div>
              <div class="video-preview-meta">Video Provider image-to-video · ${ratio} · ${voice}</div>
            </div>
            <span class="video-floating-tag ghost">${preset.label}</span>
          </div>
        </div>
      `;
    } else {
      previewWell.innerHTML = `
        <div class="video-preview-empty">
          <div class="video-preview-empty-icon">🎬</div>
          <div class="video-preview-empty-title">先选一张候选图做视频首帧</div>
          <div class="video-preview-empty-sub">系统会自动从商品信息、候选图、时长、比例和风格策略生成更稳的视频 prompt。</div>
        </div>
      `;
    }
  }
  if(strategySummary){
    strategySummary.innerHTML = `
      <div class="video-strategy-kicker">${preset.angle}</div>
      <div class="video-strategy-name">${preset.label}</div>
      <div class="video-strategy-desc">${preset.desc}</div>
    `;
  }
  if(guidanceList){
    guidanceList.innerHTML = buildVideoInsightItems(kind, candidate, ratio).map((item, idx) => `
      <div class="video-mini-item">
        <span class="video-mini-bullet">${idx + 1}</span>
        <span>${escapeHTML(item)}</span>
      </div>
    `).join('');
  }
}

function buildVideoPromptPreset(kind){
  const seed = getVideoPromptSeed();
  const snap = getInputSnapshot();
  const candidate = currentKeyframeCandidate();
  const productName = snap.name || taskMeta.product_name || 'the product';
  const category = snap.category || 'apparel';
  const audience = snap.target_audience || 'active users';
  const color = snap.primary_color || 'hero';
  const scenario = (snap.scenarios && snap.scenarios[0]) || 'brand studio';
  const highlight = (snap.selling_points || []).slice(0, 3).join(', ');
  const opener = candidate
    ? `Use candidate image #${currentKeyframe}${candidate.shot ? ` with ${candidate.shot}` : ''} as the opening frame.`
    : 'Use the selected candidate image as the opening frame.';
  const base = seed || `Create a 12-second commercial video for a ${color} ${category} product named ${productName}. Target audience: ${audience}. Primary scene: ${scenario}. Key selling points: ${highlight || 'fit, texture, silhouette'}.`;
  const presetMap = {
    showcase: 'Keep camera movement deliberate and trustworthy. Start with a locked hero frame for the first 1-1.5 seconds, then use one slow push-in and one clean body transition. Prioritize product legibility, zipper line, underbust support, and silhouette continuity. End on a centered hold that feels premium and conversion-oriented.',
    dynamic: 'Open with a strong visual hook in the first second. Use quicker pacing but keep it to one forward push, one side follow, and one decisive pose change while keeping outfit identity, anatomy, and lighting continuity stable. The result should feel social-ready, energetic, and clean enough for paid distribution.',
    texture: 'Lead with tactile detail before widening back out. Emphasize zipper pull motion, mesh texture, fabric stretch recovery, seam cleanliness, and support structure through close-up framing and soft specular light sweeps. Keep motion subtle, refined, and materially rich.',
    social: 'Build a lifestyle narrative around confidence and movement in the primary scenario. Use the opening frame as a mood anchor, transition through one expressive action beat and one emotional beat, then end on an aspirational stop frame. Keep the tone warm, believable, and shareable without losing commerce clarity.',
  };
  const stability = 'Hard constraints: one continuous shot, no jump cuts, no scene swap, no shape morphing, no melting fabric, no duplicated body, no extra limbs, no face drift, no new text, no watermark, no unauthorized logo.';
  return `${base} ${opener} ${presetMap[kind] || presetMap.showcase} ${stability}`.replace(/\s+/g, ' ').trim();
}

function applyVideoPromptPreset(kind){
  const promptField = $('videoPrompt');
  if(!promptField)return;
  promptField.value = buildVideoPromptPreset(kind);
  setActivePreset(kind);
  syncVideoControls();
}

function populateKeyframeOptions(){
  const picker = $('kfPicker');
  if(!picker)return;
  if(allCands.length === 0){
    picker.innerHTML = '<option value="">等待候选图生成后自动填充</option>';
    picker.value = '';
    currentKeyframe = 0;
    return;
  }
  const saved = loadVideoDraft();
  const savedSeq = parseInt(saved.seq, 10);
  const selected = [currentKeyframe, savedSeq, 7].find(seq => Number.isFinite(seq) && allCands.some((c, idx) => seqNoOf(c, idx) === seq));
  currentKeyframe = selected || pickDefaultKeyframe();
  picker.innerHTML = allCands.map((c, idx)=>{
    const seq = seqNoOf(c, idx);
    const kind = classify(c) === 'scene' ? '场景图' : '商品图';
    const shot = c.shot ? ` · ${c.shot}` : '';
    return `<option value="${seq}">候选图 #${seq} · ${kind}${shot}</option>`;
  }).join('');
  picker.value = String(currentKeyframe);
}

function hydrateVideoDraft(force){
  const picker = $('kfPicker');
  const promptField = $('videoPrompt');
  const durationField = $('videoDuration');
  const ratioField = $('videoRatio');
  const voiceField = $('videoVoice');
  if(!picker || !promptField)return;
  const saved = loadVideoDraft();
  const defaults = getVideoDefaults();
  if(durationField)durationField.value = String(saved.duration || defaults.duration || '12');
  if(ratioField)ratioField.value = saved.ratio || defaults.ratio || '9:16';
  if(voiceField){
    const nextVoice = saved.voice || defaults.voice || 'zh-CN-XiaoxiaoNeural';
    voiceField.value = nextVoice;
    _genVideoVoice = nextVoice;
  }
  if(force || !promptField.value.trim()){
    promptField.value = saved.prompt || getVideoPromptSeed() || buildVideoPromptPreset(saved.preset || getVideoMotionDefault());
  }
  setActivePreset(saved.preset || getVideoMotionDefault());
  videoDraftHydrated = true;
  syncVideoControls();
}

function syncVideoControls(){
  ensureVideoConfigShell();
  const picker = $('kfPicker');
  const promptField = $('videoPrompt');
  const btn = $('genVideoBtn');
  const hint = $('videoConfigHint');
  if(!picker || !promptField || !btn)return;
  const selectedSeq = parseInt(picker.value || '0', 10);
  if(Number.isFinite(selectedSeq) && selectedSeq > 0){
    currentKeyframe = selectedSeq;
  }
  const current = currentKeyframeCandidate();
  const hasCandidates = allCands.length > 0;
  const hasPrompt = Boolean(promptField.value.trim());
  const keyframeApproved = current && current.status === 'approved';
  btn.disabled = !(hasCandidates && current && keyframeApproved && hasPrompt);
  if(hint){
    if(!hasCandidates){
      hint.textContent = '图片至少生成 1 张后，才能选择首帧并提交视频。';
    }else if(!current){
      hint.textContent = `当前已返回 ${allCands.length}/${getRequestedCount()} 张候选图，请先选一张作为视频首帧。`;
    }else if(!keyframeApproved){
      const shot = current.shot ? ` · ${current.shot}` : '';
      hint.textContent = `当前首帧：候选图 #${currentKeyframe}${shot}，需要先审核通过后才能提交视频。`;
    }else{
      const shot = current.shot ? ` · ${current.shot}` : '';
      hint.textContent = `当前首帧：候选图 #${currentKeyframe}${shot}。默认视频风格：${getVideoMotionLabel()}。`;
    }
  }
  saveVideoDraft();
  renderVideoConfigSupport();
}

function saveVideoJob(job){
  writeStorage(VIDEO_JOB_KEY, {...job, updated_at: Date.now()});
}

function loadVideoJob(){
  return readStorage(VIDEO_JOB_KEY) || null;
}

function clearVideoJob(){
  removeStorage(VIDEO_JOB_KEY);
  if(videoJobTimer){
    clearTimeout(videoJobTimer);
    videoJobTimer = null;
  }
}

function restartVideoConfig(){
  clearVideoJob();
  location.reload();
}

function renderVideoGeneratingState(seq, duration, ratio){
  const showcase = document.querySelector('.video-showcase');
  if(!showcase)return;
  showcase.classList.remove('video-empty');
  showcase.innerHTML = `
    <div class="video-header">
      <div>
        <div class="video-title">🎞 视频成片 · 生成中</div>
        <div class="video-sub">用候选图 #${seq} 作为首帧 · ${duration}s · ${ratio} · Video Provider image-to-video</div>
      </div>
      <span class="pill-status pill-running"><span class="dot"></span>生成中</span>
    </div>
    <div class="video-generating">
      <div class="gen-spinner"></div>
      <div class="gen-text" id="genText">生成比例匹配的视频首帧...</div>
      <div class="gen-sub" id="genSub">已用 0s</div>
      <div class="gen-progress-bar"><div class="gen-progress-fill" id="genFill" style="width:0%"></div></div>
    </div>
  `;
}

async function pollVideoTask(job){
  clearTimeout(videoJobTimer);
  const startedAt = job.startedAt || Date.now();
  const pollInterval = 5000;
  const maxWait = 240000;
  const tick = async ()=>{
    const elapsedMs = Date.now() - startedAt;
    const elapsedSec = elapsedMs / 1000;
    if(elapsedMs > maxWait){
      clearVideoJob();
      showGenError('视频生成超时（超过 4 分钟），请重新提交。');
      return;
    }
    const estPct = Math.min(8 + elapsedSec / 180 * 85, 95);
    const fill = $('genFill');
    if(fill)fill.style.width = `${estPct}%`;
    const sub = $('genSub');
    if(sub)sub.textContent = `已用 ${Math.round(elapsedSec)}s · 预计总时长 90-180s`;
    try{
      const res = await fetch(`/api/gen-video-status?id=${encodeURIComponent(job.seedanceTaskId)}`);
      const data = await res.json();
      if(!res.ok && data.status !== 'failed'){
        throw new Error(data.error || `HTTP ${res.status}`);
      }
      if(data.status === 'succeeded' && data.video_url){
        const fillDone = $('genFill');
        const textDone = $('genText');
        if(fillDone)fillDone.style.width = '100%';
        if(textDone)textDone.textContent = '视频生成完成';
        clearVideoJob();
        setTimeout(()=>showVideoFromReal(data.video_url, job.seq, job.prompt, job.duration, job.ratio, job.voice), 300);
        return;
      }
      if(data.status === 'failed'){
        clearVideoJob();
        showGenError(`视频生成失败：${data.error || 'unknown'}`);
        return;
      }
    }catch(_){}
    saveVideoJob({...job, startedAt});
    videoJobTimer = setTimeout(tick, pollInterval);
  };
  saveVideoJob({...job, startedAt});
  tick();
}

function resumePendingVideoJob(){
  if($('demoVideo'))return;
  const job = loadVideoJob();
  if(!job || !job.seedanceTaskId)return;
  if(job.updated_at && Date.now() - job.updated_at > 30 * 60 * 1000){
    clearVideoJob();
    return;
  }
  _genVideoVoice = job.voice || _genVideoVoice;
  renderVideoGeneratingState(job.seq, job.duration, job.ratio);
  pollVideoTask(job);
}

async function genVideoMock(){
  const candidate = currentKeyframeCandidate();
  const prompt = (($('videoPrompt') || {}).value || '').trim();
  const duration = parseInt((($('videoDuration') || {}).value || '12'), 10) || 12;
  const ratio = (($('videoRatio') || {}).value || '9:16');
  _genVideoVoice = (($('videoVoice') || {}).value || 'zh-CN-XiaoxiaoNeural');
  if(!candidate){ alert('请先选择一张已生成的候选图作为视频首帧。'); return; }
  if(candidate.status !== 'approved'){ alert('当前首帧还没有审核通过，请先点“通过”再提交视频。'); return; }
  if(!prompt){ alert('请先填写视频 prompt。'); return; }
  saveVideoDraft();
  renderVideoGeneratingState(currentKeyframe, duration, ratio);
  try{
    const sub = await fetch('/api/gen-video', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({task_id: TASK_ID, seq: currentKeyframe, prompt, duration, ratio})
    });
    const subData = await sub.json().catch(()=>({}));
    if(!sub.ok){
      throw new Error(subData.error || `HTTP ${sub.status}`);
    }
    if(!subData.seedance_task_id){
      throw new Error(subData.error || '缺少 seedance_task_id');
    }
    const job = {
      seedanceTaskId: subData.seedance_task_id,
      seq: currentKeyframe,
      prompt,
      duration,
      ratio,
      voice: _genVideoVoice,
      startedAt: Date.now(),
    };
    const genText = $('genText');
    const genSub = $('genSub');
    if(genText)genText.textContent = '已提交给视频 Provider，正在轮询结果...';
    if(genSub)genSub.textContent = `任务 ID: ${subData.seedance_task_id.slice(0,16)}...`;
    pollVideoTask(job);
  }catch(err){
    clearVideoJob();
    showGenError(`提交失败：${err.message || err}`);
  }
}

function showGenError(msg){
  clearVideoJob();
  const showcase = document.querySelector('.video-showcase');
  if(!showcase)return;
  showcase.innerHTML = `
    <div class="video-header">
      <div>
        <div class="video-title">🎞 视频成片 · 失败</div>
        <div class="video-sub">${msg}</div>
      </div>
      <span class="pill-status pill-failed"><span class="dot"></span>失败</span>
    </div>
    <div class="video-empty-state" style="padding:24px">
      <button class="btn btn-primary" onclick="restartVideoConfig()">返回配置</button>
    </div>
  `;
}

function showVideoFromReal(videoUrl, seq, prompt, duration, ratio, voice){
  clearVideoJob();
  const showcase = document.querySelector('.video-showcase');
  if(!showcase)return;
  _genVideoVoice = voice || _genVideoVoice;
  showcase.classList.remove('video-empty');
  showcase.innerHTML = `
    <div class="video-header">
      <div>
        <div class="video-title">🎞 视频成片 · 由 <span class="link-img7" onclick="pickAsKeyframe(${seq},event)">候选图 #${seq}</span> 动画化得到</div>
        <div class="video-sub">${duration} 秒 · ${ratio} · Video Provider image-to-video · 刚刚生成</div>
      </div>
      <span class="pill-status pill-success"><span class="dot"></span>刚刚完成</span>
    </div>
    <div class="video-wrap">
      <video id="demoVideo" autoplay loop muted playsinline preload="auto">
        <source src="${videoUrl}" type="video/mp4">
      </video>
      <button class="play-full-btn" id="playFullBtn" onclick="playFullShowcase()">
        <span class="pf-icon">▶</span>
        <span class="pf-label">播放完整成片</span>
        <span class="pf-sub">视频 + 旁白同步</span>
      </button>
      <div class="video-controls">
        <button class="vc-btn" onclick="toggleVO()" id="voBtn">播放旁白</button>
        <select class="vc-btn" id="voicePicker" onchange="changeVoice()">
          <option value="zh-CN-XiaoxiaoNeural">晓晓（女）</option>
          <option value="zh-CN-XiaoyiNeural">晓伊（女）</option>
          <option value="zh-CN-YunxiNeural">云希（男）</option>
        </select>
        <span class="vc-meta">${ratio} · 720p</span>
        <button class="vc-btn vc-link" onclick="pickAsKeyframe(${seq},event)">→ 看首帧图</button>
        <button class="vc-btn vc-link" onclick="restartVideoConfig()">重新生成</button>
      </div>
    </div>
    <audio id="voAudio" preload="auto">
      <source id="voSource" src="/audio/voiceover_${_genVideoVoice}.mp3" type="audio/mpeg">
    </audio>
  `;
  const vp = $('voicePicker');
  if(vp)vp.value = _genVideoVoice;
  attachVideoPlaybackEvents();
}

document.addEventListener('DOMContentLoaded', ()=>{
  attachVideoPlaybackEvents();
  const picker = $('kfPicker');
  if(picker){
    picker.addEventListener('change', ()=>{
      currentKeyframe = parseInt(picker.value || '0', 10) || 0;
      rerender();
      syncVideoControls();
      if(currentKeyframe){
        showToast(`已将候选图 #${currentKeyframe} 设为视频首帧`, 'indigo');
      }
    });
  }
  const promptField = $('videoPrompt');
  if(promptField)promptField.addEventListener('input', syncVideoControls);
  const durationField = $('videoDuration');
  if(durationField)durationField.addEventListener('change', syncVideoControls);
  const ratioField = $('videoRatio');
  if(ratioField)ratioField.addEventListener('change', syncVideoControls);
  const voiceField = $('videoVoice');
  if(voiceField)voiceField.addEventListener('change', syncVideoControls);
  setActivePreset(loadVideoDraft().preset || getVideoMotionDefault());
  syncVideoControls();
  resumePendingVideoJob();
});

function finishPollAsFailed(title, detail){
  consecutivePollErrors = 0;
  pollFinished = true;
  frozenElapsedSec = Math.floor((Date.now() - t0) / 1000);
  setStatusPill('failed', title);
  setPollState('poll-error', title, detail || title, true);
  renderElapsed(frozenElapsedSec);
}

async function poll(){
  if(pollFinished)return;
  try{
    const res = await fetch(`/api/status?task_id=${TASK_ID}`);
    let data = null;
    try{
      data = await res.json();
    }catch(_){
      data = null;
    }
    if(!res.ok){
      if(data && data.error_code === 'task_not_found'){
        finishPollAsFailed(
          '\u4efb\u52a1\u4e0d\u5b58\u5728',
          data.error || '\u8bf7\u8fd4\u56de\u9996\u9875\u91cd\u65b0\u63d0\u4ea4\u751f\u6210\u4efb\u52a1\u3002'
        );
        return;
      }
      throw new Error((data && data.error) || `HTTP ${res.status}`);
    }
    if(!data){
      throw new Error('empty status response');
    }
    if(data.error){
      if(data.error_code === 'task_not_found'){
        finishPollAsFailed(
          '\u4efb\u52a1\u4e0d\u5b58\u5728',
          data.error || '\u8bf7\u8fd4\u56de\u9996\u9875\u91cd\u65b0\u63d0\u4ea4\u751f\u6210\u4efb\u52a1\u3002'
        );
        return;
      }
      throw new Error(data.error);
    }
    consecutivePollErrors = 0;
    requestedCount = parseInt(data.requested_count, 10) || 11;
    taskMeta = {
      parameters: data.parameters || {},
      title: data.title || '',
      product_name: data.product_name || '',
      sku: data.sku || '',
      task_status: data.task_status || '',
      run_status: data.run_status || '',
    };
    allCands = (data.candidates || []).slice().sort((a, b) => seqNoOf(a, 0) - seqNoOf(b, 0));
    syncApprovalsFromCandidates();
    populateKeyframeOptions();
    if(!videoDraftHydrated)hydrateVideoDraft(false);

    const n = allCands.length;
    if(countEl)countEl.textContent = String(n);
    if(countTotalEl)countTotalEl.textContent = String(getRequestedCount());
    if(barEl)barEl.style.width = `${Math.min(100, n / getRequestedCount() * 100)}%`;
    if(costEl)costEl.textContent = '¥' + (n * 0.30).toFixed(2);

    const cntProd = allCands.filter(c => classify(c) === 'product').length;
    const cntScene = allCands.filter(c => classify(c) === 'scene').length;
    $('cnt-all').textContent = n;
    $('cnt-product').textContent = cntProd;
    $('cnt-scene').textContent = cntScene;

    const elapsedSec = (Date.now() - t0) / 1000;
    if(rateEl)rateEl.textContent = n > 0 ? (elapsedSec / n).toFixed(1) + 's/张' : '-';

    const rawStatus = (data.status || 'pending').toLowerCase();
    const runStatus = (data.run_status || '').toLowerCase();
    const taskStatus = (data.task_status || '').toLowerCase();
    const isFailed = rawStatus.includes('failed') || runStatus === 'failed' || taskStatus.includes('failed');
    const isSucceeded =
      rawStatus === 'succeeded' ||
      runStatus === 'succeeded' ||
      ['candidates_ready','reviewing','approved','archived','delivered'].includes(taskStatus) ||
      (getRequestedCount() > 0 && n >= getRequestedCount());
    const isPartial =
      rawStatus === 'partial' ||
      runStatus === 'partial' ||
      (!isSucceeded && taskStatus === 'candidates_ready' && n > 0 && n < getRequestedCount());

    if(n > 0 && !isFailed && !isSucceeded && !isPartial){
      const remaining = (getRequestedCount() - n) * (elapsedSec / n);
      if(etaEl)etaEl.textContent = remaining < 60 ? Math.round(remaining) + 's' : Math.floor(remaining / 60) + 'm ' + Math.round(remaining % 60) + 's';
    } else if(isPartial){
      if(etaEl)etaEl.textContent = '部分完成';
    } else if(isFailed || isSucceeded){
      if(etaEl)etaEl.textContent = '已完成';
    } else {
      if(etaEl)etaEl.textContent = '-';
    }

    if(n === 0 && elapsedSec >= 60 && !isFailed){
      setPollState('poll-warn', '超过 60 秒仍未返回候选图', '请检查 N8N 最近执行、数据库连接和外部 API 凭据。', true);
    } else if(n === 0){
      setPollState('poll-ok', '任务已创建，正在等待首批候选图', '通常会在 10-30 秒内看到第一张候选图。', false);
    } else if(isFailed){
      setPollState('poll-error', '任务执行失败', '请打开 N8N 画布检查失败节点；修复后可重新触发。', true);
    } else if(isPartial){
      setPollState('poll-warn', '候选图已部分完成', `当前已返回 ${n}/${getRequestedCount()} 张候选图，可先审图，也可决定是否重跑。`, true);
    } else if(isSucceeded){
      setPollState('poll-ok', '候选图已准备完成', '可以开始审核，也可以直接选择一张作为视频首帧。', false);
    } else {
      setPollState('poll-ok', '候选图持续回写中', `当前已回写 ${n}/${getRequestedCount()} 张，页面会继续自动刷新。`, false);
    }

    if(isFailed){
      setStatusPill('failed', '失败');
      frozenElapsedSec = Math.floor(elapsedSec);
      pollFinished = true;
    } else if(isPartial){
      setStatusPill('success', '部分完成');
      frozenElapsedSec = Math.floor(elapsedSec);
      pollFinished = true;
    } else if(isSucceeded){
      setStatusPill('success', '生成完成');
      frozenElapsedSec = Math.floor(elapsedSec);
      pollFinished = true;
    } else if(rawStatus === 'pending' && n === 0){
      setStatusPill('running', '等待执行');
    } else {
      setStatusPill('running', '正在生成');
    }

    rerender();
    syncVideoControls();
    updateActionSummary();

    if(pollFinished){
      renderElapsed(frozenElapsedSec);
      return;
    }
  }catch(e){
    consecutivePollErrors += 1;
    const severe = consecutivePollErrors >= 3;
    setPollState(
      severe ? 'poll-error' : 'poll-warn',
      severe ? '生成服务连接异常' : '状态查询暂时波动',
      `${e.message || e}。${severe ? '请检查 N8N、数据库或容器状态。' : '系统会自动继续重试。'}`,
      severe,
    );
  }
  pollTimer = setTimeout(poll, 2000);
}

setInterval(()=>{
  renderElapsed(frozenElapsedSec ?? ((Date.now() - t0) / 1000));
}, 1000);

poll();
</script>
"""

# ============================================================================
#  Backend logic
# ============================================================================
def pg(sql):
    return pg_vars(sql)


def pg_rows(sql):
    return pg_rows_vars(sql)


def _run_psql(sql, vars=None):
    args = [
        "docker", "exec", "-i", PG_CONTAINER,
        "psql", "-U", POSTGRES_USER, "-d", POSTGRES_DB,
        "-qAtX", "-F", "\t", "-v", "ON_ERROR_STOP=1"
    ]
    for key, value in (vars or {}).items():
        args.extend(["-v", f"{key}={value}"])
    r = subprocess.run(args, input=sql, capture_output=True, text=True, encoding="utf-8")
    stdout = (r.stdout or "").strip()
    stderr = (r.stderr or "").strip()
    if r.returncode != 0 and not stderr:
        stderr = f"psql exited with code {r.returncode}"
    return stdout, stderr


def pg_vars(sql, vars=None):
    stdout, stderr = _run_psql(sql, vars)
    lines = [ln for ln in stdout.split("\n") if ln and not ln.startswith(("UPDATE ", "INSERT ", "DELETE ", "SELECT "))]
    return (lines[0].strip() if lines else ""), stderr


def pg_rows_vars(sql, vars=None):
    stdout, stderr = _run_psql(sql, vars)
    return [ln for ln in stdout.split("\n") if ln and "\t" in ln], stderr


def validate_uuid(value, field_name):
    if not value or not UUID_RE.match(value):
        raise ValueError(f"{field_name} 必须是 UUID")
    return value.lower()


def sanitize_task_token(value, field_name):
    if not value or not EXTERNAL_TASK_RE.match(value):
        raise ValueError(f"{field_name} 含有非法字符")
    return value


def h(value):
    return html.escape(str(value or ""), quote=True)


def safe_http_url(value):
    try:
        parsed = urllib.parse.urlparse(value or "")
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return value
    except Exception:
        pass
    return ""


def load_json_text(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def clean_review_text(value, max_len=500):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_len]


def build_regeneration_feedback(feedback):
    feedback = feedback or {}
    if isinstance(feedback, str):
        feedback = {"comment": feedback}
    reason_category = clean_review_text(feedback.get("reason_category"), 80)
    comment = clean_review_text(feedback.get("comment"), 700)
    preserve = clean_review_text(feedback.get("preserve"), 360)
    lines = []
    if reason_category:
        lines.append(f"Rejection category: {reason_category}.")
    if comment:
        lines.append(f"Fix request: {comment}.")
    if preserve:
        lines.append(f"Preserve: {preserve}.")
    return "\n".join(lines)


def render_external_redirect_page(title, target_url, button_label):
    safe_target = safe_http_url(target_url) or N8N_BASE
    return f"""<!DOCTYPE html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="0;url={h(safe_target)}">
<title>{h(title)}</title>
<style>{COMMON_CSS}
body{{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}}
.redirect-card{{width:min(100%,520px);background:#fff;border:1px solid var(--slate-200);border-radius:18px;box-shadow:var(--shadow-lg);padding:28px}}
.redirect-kicker{{font-size:11px;font-weight:700;color:var(--indigo);text-transform:uppercase;letter-spacing:.08em;margin-bottom:10px}}
.redirect-title{{font-size:24px;font-weight:800;color:var(--slate-900);letter-spacing:-.03em;margin-bottom:10px}}
.redirect-copy{{font-size:14px;line-height:1.8;color:var(--slate-600);margin-bottom:18px}}
.redirect-actions{{display:flex;gap:10px;flex-wrap:wrap}}
.redirect-url{{margin-top:16px;font-size:12px;color:var(--slate-400);word-break:break-all}}
</style>
<script>
window.addEventListener('DOMContentLoaded', ()=>{{
  window.location.replace({json.dumps(safe_target)});
}});
</script>
</head><body>
  <div class="redirect-card">
    <div class="redirect-kicker">N8N</div>
    <div class="redirect-title">正在打开 N8N 画布</div>
    <div class="redirect-copy">如果当前浏览器没有自动跳转，请点击下面的按钮继续进入 N8N。</div>
    <div class="redirect-actions">
      <a href="{h(safe_target)}" class="btn btn-primary">{h(button_label)}</a>
      <a href="/" class="btn btn-secondary">返回首页</a>
    </div>
    <div class="redirect-url">{h(safe_target)}</div>
  </div>
</body></html>"""


LEGACY_CONFIG_ALIASES = {
    "LLM_API_KEY": ("NEWAPI_KEY",),
    "LLM_BASE_URL": ("NEWAPI_BASE_URL",),
    "IMAGE_API_KEY": ("ARK_API_KEY",),
    "IMAGE_BASE_URL": ("ARK_ENDPOINT",),
    "IMAGE_MODEL": ("ARK_IMAGE_MODEL",),
    "VIDEO_API_KEY": ("ARK_API_KEY",),
    "VIDEO_BASE_URL": ("ARK_ENDPOINT",),
    "VIDEO_MODEL": ("ARK_VIDEO_MODEL",),
}

SECRET_CONFIG_KEYS = {
    "LLM_API_KEY",
    "MEDIA_API_KEY",
    "IMAGE_API_KEY",
    "VIDEO_API_KEY",
    "ASR_API_KEY",
    "ARK_API_KEY",
    "NEWAPI_KEY",
}

MODEL_CONFIG_KEYS = {"LLM_MODEL", "IMAGE_MODEL", "VIDEO_MODEL", "ASR_MODEL", "ARK_IMAGE_MODEL", "ARK_VIDEO_MODEL"}

PROVIDER_OPTIONS = {
    "LLM_PROVIDER": [
        ("5dock", "5dock NewAPI"),
        ("openai", "OpenAI"),
        ("deepseek", "DeepSeek"),
        ("qwen", "Qwen / DashScope"),
        ("moonshot", "Moonshot / Kimi"),
        ("zhipu", "Zhipu GLM"),
        ("openrouter", "OpenRouter"),
        ("litellm", "LiteLLM / NewAPI"),
        ("custom_openai", "自定义 OpenAI 兼容"),
    ],
    "IMAGE_PROVIDER": [
        ("volcengine_ark", "Volcengine Ark / Seedream"),
        ("runway_gateway", "Runway via media gateway"),
        ("kling_gateway", "Kling via media gateway"),
        ("minimax_gateway", "MiniMax via media gateway"),
        ("veo_gateway", "Google Veo via media gateway"),
        ("custom_media_gateway", "自定义媒体网关"),
    ],
    "VIDEO_PROVIDER": [
        ("volcengine_ark", "Volcengine Ark / Seedance"),
        ("runway_gateway", "Runway via media gateway"),
        ("kling_gateway", "Kling via media gateway"),
        ("minimax_gateway", "MiniMax via media gateway"),
        ("veo_gateway", "Google Veo via media gateway"),
        ("custom_media_gateway", "自定义媒体网关"),
    ],
    "ASR_PROVIDER": [
        ("volcengine", "Volcengine ASR"),
        ("openai", "OpenAI Audio"),
        ("azure", "Azure Speech"),
        ("custom_gateway", "自定义语音网关"),
        ("disabled", "暂不启用"),
    ],
    "PAC_PROFILE": [
        ("cn_ecommerce_default", "国内电商稳定"),
        ("quality_first", "效果优先"),
        ("cost_first", "成本优先"),
        ("enterprise_gateway", "企业统一网关"),
    ],
}


def config_value(name, default=""):
    for key in (name, *LEGACY_CONFIG_ALIASES.get(name, ())):
        value = _env.get(key) or os.environ.get(key, "")
        if value:
            return value
    return default


def provider_select(name, current):
    current = current or ""
    options = []
    for value, label in PROVIDER_OPTIONS.get(name, []):
        selected = " selected" if value == current else ""
        options.append(f'<option value="{h(value)}"{selected}>{h(label)}</option>')
    if current and all(value != current for value, _ in PROVIDER_OPTIONS.get(name, [])):
        options.append(f'<option value="{h(current)}" selected>{h(current)}</option>')
    return f'<select name="{h(name)}">{"".join(options)}</select>'


def profile_label(value):
    for item_value, label in PROVIDER_OPTIONS["PAC_PROFILE"]:
        if item_value == value:
            return label
    return value or "未设置"


def render_provider_access_center(message="", error=""):
    profile = config_value("PAC_PROFILE", PAC_PROFILE)
    provider_specs = [
        {
            "capability": "Text LLM",
            "title": "文本 / Agent",
            "provider_key": "LLM_PROVIDER",
            "secret_key": "LLM_API_KEY",
            "base_key": "LLM_BASE_URL",
            "model_key": "LLM_MODEL",
            "provider": config_value("LLM_PROVIDER", LLM_PROVIDER),
            "secret": config_value("LLM_API_KEY", LLM_API_KEY),
            "base_url": config_value("LLM_BASE_URL", LLM_BASE_URL),
            "model": config_value("LLM_MODEL", LLM_MODEL),
            "purpose": "卖点拆解、分镜、图片提示词、视频提示词、审核摘要。推荐 OpenAI-compatible 网关，方便接 OpenAI、DeepSeek、Qwen、Kimi、GLM、OpenRouter、LiteLLM。",
            "scope": "OpenAI-compatible / gateway",
            "placeholder": "sk-... 留空保留当前 key",
        },
        {
            "capability": "Image",
            "title": "图片生成",
            "provider_key": "IMAGE_PROVIDER",
            "secret_key": "IMAGE_API_KEY",
            "base_key": "IMAGE_BASE_URL",
            "model_key": "IMAGE_MODEL",
            "provider": config_value("IMAGE_PROVIDER", IMAGE_PROVIDER),
            "secret": config_value("IMAGE_API_KEY", IMAGE_API_KEY),
            "base_url": config_value("IMAGE_BASE_URL", IMAGE_BASE_URL),
            "model": config_value("IMAGE_MODEL", IMAGE_MODEL),
            "purpose": "商品图、场景图、视频首帧。默认走 Ark-compatible adapter；Runway、Kling、MiniMax、Veo 等图片模型建议通过媒体网关统一请求格式。",
            "scope": "Ark-compatible media API",
            "placeholder": "media key / ark-... 留空保留当前 key",
        },
        {
            "capability": "Video",
            "title": "视频生成",
            "provider_key": "VIDEO_PROVIDER",
            "secret_key": "VIDEO_API_KEY",
            "base_key": "VIDEO_BASE_URL",
            "model_key": "VIDEO_MODEL",
            "provider": config_value("VIDEO_PROVIDER", VIDEO_PROVIDER),
            "secret": config_value("VIDEO_API_KEY", VIDEO_API_KEY),
            "base_url": config_value("VIDEO_BASE_URL", VIDEO_BASE_URL),
            "model": config_value("VIDEO_MODEL", VIDEO_MODEL),
            "purpose": "image-to-video、任务轮询、视频候选。默认走 Ark-compatible adapter；Runway、MiniMax、Kling、Veo 建议通过统一媒体网关接入。",
            "scope": "Ark-compatible async video API",
            "placeholder": "video key / ark-... 留空保留当前 key",
        },
        {
            "capability": "ASR",
            "title": "语音 / 字幕",
            "provider_key": "ASR_PROVIDER",
            "secret_key": "ASR_API_KEY",
            "base_key": "ASR_BASE_URL",
            "model_key": "ASR_MODEL",
            "provider": config_value("ASR_PROVIDER", ASR_PROVIDER),
            "secret": config_value("ASR_API_KEY", ASR_API_KEY),
            "base_url": config_value("ASR_BASE_URL", ASR_BASE_URL),
            "model": config_value("ASR_MODEL", ASR_MODEL),
            "purpose": "ASR 转字幕、口播对齐和字幕兜底。非必填；没有 ASR 时走 storyboard 字幕。",
            "scope": "optional",
            "placeholder": "optional key，留空保留当前 key",
        },
    ]
    core_specs = [spec for spec in provider_specs if spec["capability"] in {"Text LLM", "Image", "Video"}]
    configured_core = sum(1 for spec in core_specs if spec["secret"])
    configured_all = sum(1 for spec in provider_specs if spec["secret"] or spec["provider"] == "disabled")
    media_secret = config_value("MEDIA_API_KEY", MEDIA_API_KEY)
    media_base_url = config_value("MEDIA_BASE_URL", MEDIA_BASE_URL)
    media_gateway_html = f"""<section class="gateway-card">
        <div>
          <div class="provider-eyebrow">Shared Media Gateway</div>
          <div class="provider-title">图片 / 视频共用入口</div>
          <div class="provider-purpose">如果图片和视频走同一个网关，只填这里即可；IMAGE / VIDEO 未单独填写时会继承该 key 和 endpoint。直连 Ark、Runway、Kling、MiniMax、Veo 都建议在网关侧做 provider adapter。</div>
          <div class="provider-meta"><span>{h(media_base_url or '可留空')}</span><span>{h(mask_secret(media_secret))}</span></div>
        </div>
        <div class="provider-controls">
          <label>MEDIA_API_KEY</label>
          <input type="password" name="MEDIA_API_KEY" autocomplete="off" placeholder="共享媒体 key，留空保留当前值" />
          <label>MEDIA_BASE_URL</label>
          <input type="text" name="MEDIA_BASE_URL" value="{h(media_base_url)}" placeholder="https://media-gateway.example.com/v1" />
        </div>
      </section>"""

    def provider_card(spec):
        configured = bool(spec["secret"]) or spec["provider"] == "disabled"
        status_text = "Connected" if configured else "Missing"
        return f"""<section class="provider-card {'is-ready' if configured else 'is-missing'}">
          <div class="provider-main">
            <div class="provider-row">
              <div>
                <div class="provider-eyebrow">{h(spec['capability'])}</div>
                <div class="provider-title">{h(spec['title'])}</div>
              </div>
              <span class="status-badge {'status-ready' if configured else 'status-missing'}">{status_text}</span>
            </div>
            <div class="provider-purpose">{h(spec['purpose'])}</div>
            <div class="provider-meta">
              <span>{h(spec['scope'])}</span>
              <span>{h(spec['model'])}</span>
              <span>{h(mask_secret(spec['secret']))}</span>
            </div>
          </div>
          <div class="provider-controls">
            <label>Provider</label>
            {provider_select(spec['provider_key'], spec['provider'])}
            <label>API Key</label>
            <input type="password" name="{h(spec['secret_key'])}" autocomplete="off" placeholder="{h(spec['placeholder'])}" />
            <details class="provider-advanced">
              <summary>Endpoint</summary>
              <div class="settings-field">
                <label>{h(spec['base_key'])}</label>
                <input type="text" name="{h(spec['base_key'])}" value="{h(spec['base_url'])}" />
              </div>
            </details>
          </div>
        </section>"""

    route_fields = [
        ("PAC_PROFILE", profile, "Route Profile", "select"),
        ("LLM_MODEL", config_value("LLM_MODEL", LLM_MODEL), "Text LLM Model", "input"),
        ("IMAGE_MODEL", config_value("IMAGE_MODEL", IMAGE_MODEL), "Image Model", "input"),
        ("VIDEO_MODEL", config_value("VIDEO_MODEL", VIDEO_MODEL), "Video Model", "input"),
        ("ASR_MODEL", config_value("ASR_MODEL", ASR_MODEL), "ASR Model", "input"),
    ]
    route_html = "".join(
        f"""<div class="settings-field">
          <label>{h(label)}</label>
          {provider_select(name, value) if kind == 'select' else f'<input type="text" name="{h(name)}" value="{h(value)}" />'}
        </div>"""
        for name, value, label, kind in route_fields
    )
    provider_html = "".join(provider_card(spec) for spec in provider_specs)
    message_html = f'<div class="settings-alert ok">{h(message)}</div>' if message else ""
    error_html = f'<div class="settings-alert err">{h(error)}</div>' if error else ""

    return f"""<!DOCTYPE html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>模型配置 · ContentFactory</title>
<style>{COMMON_CSS}
.settings-shell{{max-width:1180px;margin:0 auto;padding:30px 24px 70px}}
.settings-head{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:18px;align-items:start;margin-bottom:22px}}
.settings-title{{font-size:28px;font-weight:800;color:var(--slate-900);letter-spacing:-.02em;margin-bottom:6px}}
.settings-sub{{font-size:14px;color:var(--slate-500);line-height:1.75;max-width:800px}}
.settings-kpis{{display:grid;grid-template-columns:repeat(4,minmax(140px,1fr));gap:10px;margin:18px 0 22px}}
.kpi{{background:#fff;border:1px solid var(--slate-200);border-radius:8px;padding:14px 16px}}
.kpi-label{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--slate-400);margin-bottom:6px}}
.kpi-value{{font-size:22px;font-weight:800;color:var(--slate-900)}}
.kpi-sub{{font-size:12px;color:var(--slate-500);margin-top:4px;word-break:break-all}}
.settings-grid{{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:18px;align-items:start}}
@media(max-width:940px){{.settings-grid,.settings-head{{grid-template-columns:1fr}}.settings-kpis{{grid-template-columns:1fr}}}}
.settings-stack{{display:flex;flex-direction:column;gap:14px}}
.section-head{{display:flex;justify-content:space-between;gap:12px;align-items:flex-end;margin:8px 0 10px}}
.section-title{{font-size:15px;font-weight:800;color:var(--slate-900)}}
.section-sub{{font-size:12px;color:var(--slate-500);line-height:1.6;max-width:720px}}
.provider-card,.gateway-card{{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:18px;background:#fff;border:1px solid var(--slate-200);border-radius:8px;padding:18px;box-shadow:var(--shadow-sm)}}
.gateway-card{{border-left:4px solid var(--indigo)}}
@media(max-width:760px){{.provider-card,.gateway-card{{grid-template-columns:1fr}}}}
.provider-card.is-ready{{border-left:4px solid var(--green)}}
.provider-card.is-missing{{border-left:4px solid var(--amber)}}
.provider-row{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}}
.provider-eyebrow{{font-size:11px;font-weight:700;color:var(--slate-400);letter-spacing:.05em;text-transform:uppercase}}
.provider-title{{font-size:17px;font-weight:800;color:var(--slate-900);margin-top:3px}}
.provider-purpose{{font-size:13px;color:var(--slate-600);line-height:1.7;margin:12px 0}}
.provider-meta{{display:flex;flex-wrap:wrap;gap:8px}}
.provider-meta span{{font-size:12px;color:var(--slate-600);background:var(--slate-50);border:1px solid var(--slate-200);border-radius:999px;padding:5px 8px}}
.status-badge{{display:inline-flex;align-items:center;height:24px;padding:0 9px;border-radius:999px;font-size:11px;font-weight:800;letter-spacing:.04em;text-transform:uppercase}}
.status-ready{{background:rgba(16,185,129,.1);color:var(--green-dark)}}
.status-missing{{background:rgba(245,158,11,.12);color:#b45309}}
.provider-controls{{display:grid;grid-template-columns:1fr;gap:8px;align-content:start}}
.provider-controls label,.settings-field label{{font-size:11px;font-weight:700;color:var(--slate-500);text-transform:uppercase;letter-spacing:.04em;margin:0}}
.provider-controls input,.provider-controls select,.settings-field input,.settings-field select{{width:100%;padding:10px 11px;border:1.5px solid var(--slate-200);border-radius:8px;background:#fff;color:var(--slate-900);font-size:13px;font-family:inherit}}
.provider-controls input:focus,.provider-controls select:focus,.settings-field input:focus,.settings-field select:focus{{outline:0;border-color:var(--indigo);box-shadow:0 0 0 3px rgba(99,102,241,.12)}}
.provider-advanced{{margin-top:2px}}
.provider-advanced summary{{cursor:pointer;font-size:12px;font-weight:700;color:var(--slate-500);padding:6px 0}}
.model-grid{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;background:#fff;border:1px solid var(--slate-200);border-radius:8px;padding:18px}}
@media(max-width:980px){{.model-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
@media(max-width:640px){{.model-grid{{grid-template-columns:1fr}}}}
.settings-field{{display:flex;flex-direction:column;gap:7px}}
.advanced-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;background:#fff;border:1px solid var(--slate-200);border-radius:8px;padding:18px}}
@media(max-width:760px){{.advanced-grid{{grid-template-columns:1fr}}}}
.settings-actions{{position:sticky;bottom:0;display:flex;gap:10px;flex-wrap:wrap;align-items:center;justify-content:space-between;background:rgba(248,250,252,.94);backdrop-filter:blur(10px);border:1px solid var(--slate-200);border-radius:8px;padding:12px 14px;margin-top:14px}}
.settings-actions-left{{display:flex;gap:10px;flex-wrap:wrap}}
.settings-actions-note{{font-size:12px;color:var(--slate-500)}}
.side-card{{background:#fff;border:1px solid var(--slate-200);border-radius:8px;padding:16px;box-shadow:var(--shadow-sm)}}
.side-title{{font-size:13px;font-weight:800;color:var(--slate-900);margin-bottom:9px}}
.side-copy{{font-size:12px;color:var(--slate-600);line-height:1.75}}
.check-list{{display:flex;flex-direction:column;gap:8px;margin-top:10px}}
.check-item{{display:grid;grid-template-columns:18px 1fr;gap:8px;font-size:12px;color:var(--slate-600);line-height:1.55}}
.check-dot{{width:18px;height:18px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:var(--slate-100);color:var(--slate-500);font-size:11px;font-weight:800}}
.check-dot.ok{{background:rgba(16,185,129,.12);color:var(--green-dark)}}
.code-line{{margin-top:9px;padding:9px 10px;background:var(--slate-50);border:1px solid var(--slate-200);border-radius:8px;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;color:var(--slate-700);word-break:break-all}}
.settings-alert{{padding:12px 14px;border-radius:10px;font-size:13px;font-weight:600;margin-bottom:14px}}
.settings-alert.ok{{background:rgba(16,185,129,.1);color:var(--green-dark);border:1px solid rgba(16,185,129,.18)}}
.settings-alert.err{{background:rgba(239,68,68,.1);color:var(--red);border:1px solid rgba(239,68,68,.18)}}
code{{background:var(--slate-100);padding:2px 5px;border-radius:5px;font-size:12px}}
</style></head><body>
<nav class="nav">
  <div class="nav-left">
    <a class="logo" href="/"><span class="logo-mark">CF</span>ContentFactory</a>
    <div class="crumbs"><span>·</span> <strong>模型配置</strong></div>
  </div>
  <div class="nav-right">
    <a href="/" class="btn btn-ghost" style="font-size:12px">新建任务</a>
    <a href="/history" class="btn btn-ghost" style="font-size:12px">历史任务</a>
    <a href="/review" class="btn btn-ghost" style="font-size:12px">待审核</a>
  </div>
</nav>
<div class="settings-shell">
  <div class="settings-head">
    <div>
      <div class="settings-title">Provider Access Center</div>
      <div class="settings-sub">这里不是模型市场，而是能力路由中心。默认保持国内电商稳定链路；高级用户可以把文本 LLM 切到任意 OpenAI-compatible provider，把图片/视频切到统一媒体网关。密钥只写入 <code>deploy/.env.local</code>，页面不回填明文。</div>
    </div>
    <div class="settings-actions-left">
      <a class="btn btn-secondary" href="/health">健康 JSON</a>
      <a class="btn btn-secondary" href="/open-n8n?pipeline=image">打开 N8N</a>
    </div>
  </div>
  {message_html}{error_html}
  <section class="settings-kpis">
    <div class="kpi"><div class="kpi-label">Core Routes</div><div class="kpi-value">{configured_core}/3</div><div class="kpi-sub">文本 / 图片 / 视频</div></div>
    <div class="kpi"><div class="kpi-label">Profile</div><div class="kpi-value">{h(profile_label(profile))}</div><div class="kpi-sub">{h(profile)}</div></div>
    <div class="kpi"><div class="kpi-label">Providers</div><div class="kpi-value">{configured_all}/4</div><div class="kpi-sub">ASR 可选</div></div>
    <div class="kpi"><div class="kpi-label">Workflow Sync</div><div class="kpi-value">Manual</div><div class="kpi-sub">保存后重跑 n8n_setup.py</div></div>
  </section>
  <div class="settings-grid">
    <form method="POST" action="/settings" class="settings-stack">
      <div class="section-head">
        <div>
          <div class="section-title">Credentials</div>
          <div class="section-sub">最少只需要填文本 LLM key 和一个共享媒体网关 key；图片/视频也可以按能力单独覆盖。空 password 表示保留当前 secret。</div>
        </div>
      </div>
      {media_gateway_html}
      {provider_html}
      <div class="section-head">
        <div>
          <div class="section-title">Model Routing</div>
          <div class="section-sub">Provider 负责鉴权和 endpoint，模型 ID 负责实际路由。后续换模型不需要改业务代码。</div>
        </div>
      </div>
      <section class="model-grid">{route_html}</section>
      <div class="section-head">
        <div>
          <div class="section-title">Advanced Endpoints</div>
          <div class="section-sub">只有端口、代理或远程 N8N 改动时才需要调整。</div>
        </div>
      </div>
      <section class="advanced-grid">
        <div class="settings-field">
          <label>N8N_BASE</label>
          <input type="text" name="N8N_BASE" value="{h(config_value('N8N_BASE', N8N_BASE))}" />
        </div>
        <div class="settings-field">
          <label>N8N_EDITOR_URL</label>
          <input type="text" name="N8N_EDITOR_URL" value="{h(config_value('N8N_EDITOR_URL', N8N_EDITOR_URL))}" />
        </div>
        <div class="settings-field">
          <label>N8N_IMAGE_EDITOR_URL</label>
          <input type="text" name="N8N_IMAGE_EDITOR_URL" value="{h(config_value('N8N_IMAGE_EDITOR_URL', N8N_IMAGE_EDITOR_URL))}" />
        </div>
        <div class="settings-field">
          <label>N8N_VIDEO_EDITOR_URL</label>
          <input type="text" name="N8N_VIDEO_EDITOR_URL" value="{h(config_value('N8N_VIDEO_EDITOR_URL', N8N_VIDEO_EDITOR_URL))}" />
        </div>
      </section>
      <div class="settings-actions">
        <div class="settings-actions-left">
          <button type="submit" class="btn btn-primary">保存配置</button>
          <a href="/" class="btn btn-secondary">返回首页</a>
        </div>
        <div class="settings-actions-note">当前 5001 服务会立即刷新；/health 会提示 N8N 是否还需要同步。</div>
      </div>
    </form>
    <aside class="settings-stack">
      <section class="side-card">
        <div class="side-title">Connection Check</div>
        <div class="side-copy" id="healthText">读取本地健康状态中...</div>
        <div class="check-list">
          <div class="check-item"><span class="check-dot" id="dbDot">·</span><span id="dbText">Postgres</span></div>
          <div class="check-item"><span class="check-dot" id="llmDot">·</span><span id="llmText">LLM route</span></div>
          <div class="check-item"><span class="check-dot" id="imageDot">·</span><span id="imageText">Image route</span></div>
          <div class="check-item"><span class="check-dot" id="videoDot">·</span><span id="videoText">Video route</span></div>
          <div class="check-item"><span class="check-dot" id="n8nDot">·</span><span id="n8nText">N8N trigger</span></div>
          <div class="check-item"><span class="check-dot" id="syncDot">·</span><span id="syncText">N8N credential sync</span></div>
        </div>
      </section>
      <section class="side-card">
        <div class="side-title">Recommended Setup</div>
        <div class="side-copy">交付默认：LLM 走 OpenAI-compatible 网关，图片/视频走 Ark 或内部媒体网关。这样客户只需要维护 2-3 个 key，同时可以在网关侧切 OpenAI、DeepSeek、Qwen、Kimi、GLM、Claude 等模型。</div>
      </section>
      <section class="side-card">
        <div class="side-title">Sync Runbook</div>
        <div class="side-copy">保存 key 后，当前表单服务已经生效；N8N 画布中的 credential 和容器 env 需要同步。</div>
        <div class="code-line">python scripts/n8n_setup.py --token=&lt;N8N_API_TOKEN&gt;</div>
        <div class="code-line">docker compose -f deploy/docker-compose.local.yml --env-file deploy/.env.local up -d --force-recreate n8n</div>
      </section>
      <section class="side-card">
        <div class="side-title">Security Baseline</div>
        <div class="check-list">
          <div class="check-item"><span class="check-dot ok">✓</span><span>不在页面回填明文 secret</span></div>
          <div class="check-item"><span class="check-dot ok">✓</span><span>空 password 表示保留当前值</span></div>
          <div class="check-item"><span class="check-dot ok">✓</span><span>新字段与旧 ARK/NEWAPI 字段双向兼容</span></div>
          <div class="check-item"><span class="check-dot ok">✓</span><span>Provider 按能力拆分，方便后续接入更多 adapter</span></div>
        </div>
      </section>
    </aside>
  </div>
</div>
<script>
fetch('/health').then(r=>r.json()).then(data=>{{
  const set = (id, ok, text) => {{
    const dot = document.getElementById(id + 'Dot');
    const label = document.getElementById(id + 'Text');
    if(dot){{ dot.textContent = ok ? '✓' : '!'; dot.classList.toggle('ok', !!ok); }}
    if(label) label.textContent = text;
  }};
  set('db', data.postgres_ok, data.postgres_ok ? 'Postgres connected' : 'Postgres degraded');
  set('llm', data.providers && data.providers.llm && data.providers.llm.configured, data.providers && data.providers.llm ? data.providers.llm.label : 'LLM route');
  set('image', data.providers && data.providers.image && data.providers.image.configured, data.providers && data.providers.image ? data.providers.image.label : 'Image route');
  set('video', data.providers && data.providers.video && data.providers.video.configured, data.providers && data.providers.video ? data.providers.video.label : 'Video route');
  set('n8n', !!data.n8n_trigger, data.n8n_trigger || 'N8N trigger missing');
  set('sync', data.sync && data.sync.n8n_status === 'synced', data.sync ? data.sync.n8n_text : 'N8N credential sync');
  const health = document.getElementById('healthText');
  if(health) health.textContent = data.status === 'ok' ? '本地服务健康，配置可以用于新任务。' : '本地服务存在异常，请先看 /health 详情。';
}}).catch(err=>{{
  const health = document.getElementById('healthText');
  if(health) health.textContent = '健康状态读取失败：' + (err.message || err);
}});
</script>
</body></html>"""


def render_minimal_provider_settings(message="", error=""):
    llm_provider = config_value("LLM_PROVIDER", LLM_PROVIDER)
    llm_key = config_value("LLM_API_KEY", LLM_API_KEY)
    llm_base = config_value("LLM_BASE_URL", LLM_BASE_URL)
    llm_model = config_value("LLM_MODEL", LLM_MODEL)
    media_key = config_value("MEDIA_API_KEY", MEDIA_API_KEY)
    media_base = config_value("MEDIA_BASE_URL", MEDIA_BASE_URL)
    media_provider = config_value("IMAGE_PROVIDER", IMAGE_PROVIDER)
    image_model = config_value("IMAGE_MODEL", IMAGE_MODEL)
    video_model = config_value("VIDEO_MODEL", VIDEO_MODEL)
    llm_ok = bool(llm_key)
    media_ok = bool(media_key or IMAGE_API_KEY or VIDEO_API_KEY)
    setup_count = int(llm_ok) + int(media_ok)
    message_html = f'<div class="settings-alert ok">{h(message)}</div>' if message else ""
    error_html = f'<div class="settings-alert err">{h(error)}</div>' if error else ""

    return f"""<!DOCTYPE html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>API Key 设置 · ContentFactory</title>
<style>{COMMON_CSS}
.settings-shell{{max-width:920px;margin:0 auto;padding:30px 22px 74px}}
.settings-head{{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:18px}}
@media(max-width:760px){{.settings-head{{flex-direction:column}}}}
.settings-title{{font-size:28px;font-weight:850;color:var(--slate-900);margin-bottom:6px}}
.settings-sub{{font-size:14px;color:var(--slate-500);line-height:1.75;max-width:680px}}
.settings-topline{{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0 20px}}
.mini-pill{{display:inline-flex;align-items:center;gap:6px;height:28px;padding:0 10px;border:1px solid var(--slate-200);border-radius:999px;background:#fff;color:var(--slate-600);font-size:12px;font-weight:700}}
.mini-dot{{width:8px;height:8px;border-radius:999px;background:var(--amber)}}
.mini-dot.ok{{background:var(--green)}}
.settings-card{{background:#fff;border:1px solid var(--slate-200);border-radius:8px;box-shadow:var(--shadow-sm);padding:22px;margin-bottom:14px}}
.settings-card.is-ready{{border-left:4px solid var(--green)}}
.settings-card.is-missing{{border-left:4px solid var(--amber)}}
.card-head{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:18px}}
.card-kicker{{font-size:11px;font-weight:800;color:var(--slate-400);letter-spacing:.06em;text-transform:uppercase;margin-bottom:4px}}
.card-title{{font-size:18px;font-weight:850;color:var(--slate-900)}}
.card-copy{{font-size:13px;color:var(--slate-600);line-height:1.7;margin-top:8px;max-width:620px}}
.status-badge{{display:inline-flex;align-items:center;height:26px;padding:0 10px;border-radius:999px;font-size:11px;font-weight:850;text-transform:uppercase;letter-spacing:.04em}}
.status-ready{{background:rgba(16,185,129,.1);color:var(--green-dark)}}
.status-missing{{background:rgba(245,158,11,.12);color:#b45309}}
.form-grid{{display:grid;grid-template-columns:220px minmax(0,1fr);gap:12px}}
@media(max-width:760px){{.form-grid{{grid-template-columns:1fr}}}}
.settings-field{{display:flex;flex-direction:column;gap:7px}}
.settings-field label{{font-size:11px;font-weight:800;color:var(--slate-500);text-transform:uppercase;letter-spacing:.04em}}
.settings-field input,.settings-field select{{width:100%;padding:11px 12px;border:1.5px solid var(--slate-200);border-radius:8px;background:#fff;color:var(--slate-900);font-size:14px;font-family:inherit}}
.settings-field input:focus,.settings-field select:focus{{outline:0;border-color:var(--indigo);box-shadow:0 0 0 3px rgba(99,102,241,.12)}}
.secret-row{{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px}}
@media(max-width:560px){{.secret-row{{grid-template-columns:1fr}}}}
.ghost-note{{font-size:12px;color:var(--slate-500);line-height:1.6;margin-top:8px}}
.advanced{{margin-top:16px;border-top:1px solid var(--slate-100);padding-top:12px}}
.advanced summary{{cursor:pointer;color:var(--slate-600);font-size:13px;font-weight:800}}
.advanced-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}}
@media(max-width:760px){{.advanced-grid{{grid-template-columns:1fr}}}}
.settings-actions{{position:sticky;bottom:0;margin-top:18px;display:flex;justify-content:space-between;gap:12px;align-items:center;background:rgba(248,250,252,.94);backdrop-filter:blur(10px);border:1px solid var(--slate-200);border-radius:8px;padding:12px 14px}}
@media(max-width:760px){{.settings-actions{{align-items:stretch;flex-direction:column}}}}
.settings-actions-left{{display:flex;gap:10px;flex-wrap:wrap}}
.sync-panel{{margin-top:14px;background:#fff;border:1px solid var(--slate-200);border-radius:8px;padding:16px}}
.sync-title{{font-size:13px;font-weight:850;color:var(--slate-900);margin-bottom:10px}}
.check-list{{display:grid;gap:8px}}
.check-item{{display:grid;grid-template-columns:18px 1fr;gap:8px;font-size:12px;color:var(--slate-600);line-height:1.55}}
.check-dot{{width:18px;height:18px;border-radius:999px;display:flex;align-items:center;justify-content:center;background:var(--slate-100);color:var(--slate-500);font-size:11px;font-weight:850}}
.check-dot.ok{{background:rgba(16,185,129,.12);color:var(--green-dark)}}
.settings-alert{{padding:12px 14px;border-radius:8px;font-size:13px;font-weight:650;margin-bottom:14px}}
.settings-alert.ok{{background:rgba(16,185,129,.1);color:var(--green-dark);border:1px solid rgba(16,185,129,.18)}}
.settings-alert.err{{background:rgba(239,68,68,.1);color:var(--red);border:1px solid rgba(239,68,68,.18)}}
code{{background:var(--slate-100);padding:2px 5px;border-radius:5px;font-size:12px}}
</style></head><body>
<nav class="nav">
  <div class="nav-left">
    <a class="logo" href="/"><span class="logo-mark">CF</span>ContentFactory</a>
    <div class="crumbs"><span>·</span> <strong>API Key 设置</strong></div>
  </div>
  <div class="nav-right">
    <a href="/" class="btn btn-ghost" style="font-size:12px">新建任务</a>
    <a href="/history" class="btn btn-ghost" style="font-size:12px">历史任务</a>
    <a href="/review" class="btn btn-ghost" style="font-size:12px">待审核</a>
  </div>
</nav>
<main class="settings-shell">
  <div class="settings-head">
    <div>
      <div class="settings-title">API Key 设置</div>
      <div class="settings-sub">只需要两组连接：文本模型负责提示词和分析，图片/视频模型负责生成素材。模型 ID 和 endpoint 已放进高级设置，默认不用动。</div>
    </div>
    <div class="settings-actions-left">
      <a class="btn btn-secondary" href="/health">健康状态</a>
      <a class="btn btn-secondary" href="/open-n8n?pipeline=image">打开 N8N</a>
    </div>
  </div>
  {message_html}{error_html}
  <div class="settings-topline">
    <span class="mini-pill"><span class="mini-dot {'ok' if llm_ok else ''}"></span>文本模型 {mask_secret(llm_key)}</span>
    <span class="mini-pill"><span class="mini-dot {'ok' if media_ok else ''}"></span>图片/视频 {mask_secret(media_key or IMAGE_API_KEY or VIDEO_API_KEY)}</span>
    <span class="mini-pill">{setup_count}/2 已配置</span>
  </div>
  <form method="POST" action="/settings">
    <section class="settings-card {'is-ready' if llm_ok else 'is-missing'}">
      <div class="card-head">
        <div>
          <div class="card-kicker">Required</div>
          <div class="card-title">文本模型</div>
          <div class="card-copy">用于卖点拆解、分镜、图片提示词、视频提示词和审核摘要。兼容 OpenAI-compatible 网关。</div>
        </div>
        <span class="status-badge {'status-ready' if llm_ok else 'status-missing'}">{'Connected' if llm_ok else 'Missing'}</span>
      </div>
      <div class="form-grid">
        <div class="settings-field">
          <label>Provider</label>
          {provider_select('LLM_PROVIDER', llm_provider)}
        </div>
        <div class="settings-field">
          <label>API Key</label>
          <input type="password" name="LLM_API_KEY" autocomplete="off" placeholder="sk-... 空着表示保留当前 key" />
          <div class="ghost-note">当前：{h(mask_secret(llm_key))}</div>
        </div>
      </div>
      <details class="advanced">
        <summary>高级设置</summary>
        <div class="advanced-grid">
          <div class="settings-field">
            <label>Base URL</label>
            <input type="text" name="LLM_BASE_URL" value="{h(llm_base)}" />
          </div>
          <div class="settings-field">
            <label>Model</label>
            <input type="text" name="LLM_MODEL" value="{h(llm_model)}" />
          </div>
        </div>
      </details>
    </section>
    <section class="settings-card {'is-ready' if media_ok else 'is-missing'}">
      <div class="card-head">
        <div>
          <div class="card-kicker">Required</div>
          <div class="card-title">图片 / 视频模型</div>
          <div class="card-copy">用于商品图、场景图、视频首帧和 image-to-video。建议接一个媒体网关，网关内部再切即梦、火山、Runway、Kling、MiniMax、Veo 等模型。</div>
        </div>
        <span class="status-badge {'status-ready' if media_ok else 'status-missing'}">{'Connected' if media_ok else 'Missing'}</span>
      </div>
      <input type="hidden" name="VIDEO_PROVIDER" id="videoProviderMirror" value="{h(config_value('VIDEO_PROVIDER', VIDEO_PROVIDER))}" />
      <div class="form-grid">
        <div class="settings-field">
          <label>Provider</label>
          {provider_select('IMAGE_PROVIDER', media_provider)}
        </div>
        <div class="settings-field">
          <label>API Key</label>
          <input type="password" name="MEDIA_API_KEY" autocomplete="off" placeholder="media / ark / jimeng key，空着表示保留当前 key" />
          <div class="ghost-note">当前：{h(mask_secret(media_key or IMAGE_API_KEY or VIDEO_API_KEY))}</div>
        </div>
      </div>
      <details class="advanced">
        <summary>高级设置</summary>
        <div class="advanced-grid">
          <div class="settings-field">
            <label>Media Base URL</label>
            <input type="text" name="MEDIA_BASE_URL" value="{h(media_base)}" placeholder="https://media-gateway.example.com/v1" />
          </div>
          <div class="settings-field">
            <label>Image Model</label>
            <input type="text" name="IMAGE_MODEL" value="{h(image_model)}" />
          </div>
          <div class="settings-field">
            <label>Video Model</label>
            <input type="text" name="VIDEO_MODEL" value="{h(video_model)}" />
          </div>
          <div class="settings-field">
            <label>Route Profile</label>
            {provider_select('PAC_PROFILE', config_value('PAC_PROFILE', PAC_PROFILE))}
          </div>
        </div>
      </details>
    </section>
    <details class="sync-panel">
      <summary class="sync-title">部署同步</summary>
      <div class="check-list">
        <div class="check-item"><span class="check-dot" id="dbDot">·</span><span id="dbText">Postgres</span></div>
        <div class="check-item"><span class="check-dot" id="llmDot">·</span><span id="llmText">Text route</span></div>
        <div class="check-item"><span class="check-dot" id="mediaDot">·</span><span id="mediaText">Media route</span></div>
        <div class="check-item"><span class="check-dot" id="syncDot">·</span><span id="syncText">N8N credential sync</span></div>
      </div>
      <div class="ghost-note">保存会立即刷新本地 5001 服务配置；N8N credential 需要运行 <code>python scripts/n8n_setup.py --token=&lt;N8N_API_TOKEN&gt;</code> 同步。</div>
    </details>
    <div class="settings-actions">
      <div class="settings-actions-left">
        <button type="submit" class="btn btn-primary">保存 API Key</button>
        <a href="/" class="btn btn-secondary">返回首页</a>
      </div>
      <div class="ghost-note">空 password 表示保留当前 secret，页面不回显明文。</div>
    </div>
  </form>
</main>
<script>
const imageProvider = document.querySelector('select[name="IMAGE_PROVIDER"]');
const videoProviderMirror = document.getElementById('videoProviderMirror');
if(imageProvider && videoProviderMirror){{
  const sync = () => {{ videoProviderMirror.value = imageProvider.value; }};
  imageProvider.addEventListener('change', sync);
  sync();
}}
fetch('/health').then(r=>r.json()).then(data=>{{
  const set = (id, ok, text) => {{
    const dot = document.getElementById(id + 'Dot');
    const label = document.getElementById(id + 'Text');
    if(dot){{ dot.textContent = ok ? '✓' : '!'; dot.classList.toggle('ok', !!ok); }}
    if(label) label.textContent = text;
  }};
  set('db', data.postgres_ok, data.postgres_ok ? 'Postgres connected' : 'Postgres degraded');
  set('llm', data.providers && data.providers.llm && data.providers.llm.configured, data.providers && data.providers.llm ? data.providers.llm.label : 'Text route');
  const mediaOk = !!(data.media_configured || (data.providers && data.providers.image && data.providers.image.configured && data.providers.video && data.providers.video.configured));
  const mediaText = data.media_gateway && data.media_gateway.configured ? data.media_gateway.label : 'Media route';
  set('media', mediaOk, mediaText);
  set('sync', data.sync && data.sync.n8n_status === 'synced', data.sync ? data.sync.n8n_text : 'N8N credential sync');
}}).catch(()=>{{}});
</script>
</body></html>"""


def render_settings_page(message="", error=""):
    return render_minimal_provider_settings(message=message, error=error)

def save_settings_form(form):
    updates = {}
    for key in CONFIG_KEYS:
        raw = (form.get(key, [""])[0] or "").strip()
        if key in SECRET_CONFIG_KEYS and not raw:
            continue
        if key not in SECRET_CONFIG_KEYS:
            if not raw:
                continue
            if key.endswith("_URL") or key.endswith("_BASE") or key.endswith("_ENDPOINT"):
                if not safe_http_url(raw):
                    return f"{key} 必须是 http 或 https URL"
                raw = raw.rstrip("/")
            if key in MODEL_CONFIG_KEYS:
                if len(raw) > 160 or any(ch.isspace() for ch in raw) or any(ch in raw for ch in "\"'`$"):
                    return f"{key} 只能填写不含空格和引号的模型 ID"
            if key.endswith("_PROVIDER") or key == "PAC_PROFILE":
                if len(raw) > 80 or any(ch.isspace() for ch in raw) or any(ch in raw for ch in "\"'`$"):
                    return f"{key} 只能填写不含空格和引号的标识"
        updates[key] = raw
    # Keep legacy names synchronized so old scripts and existing N8N env refs keep working.
    if "LLM_API_KEY" in updates:
        updates["NEWAPI_KEY"] = updates["LLM_API_KEY"]
    if "LLM_BASE_URL" in updates:
        updates["NEWAPI_BASE_URL"] = updates["LLM_BASE_URL"]
    if "IMAGE_PROVIDER" in updates and "VIDEO_PROVIDER" not in updates:
        updates["VIDEO_PROVIDER"] = updates["IMAGE_PROVIDER"]
    if "IMAGE_API_KEY" in updates and "VIDEO_API_KEY" in updates and updates["IMAGE_API_KEY"] == updates["VIDEO_API_KEY"]:
        updates["ARK_API_KEY"] = updates["IMAGE_API_KEY"]
    if "IMAGE_BASE_URL" in updates and "VIDEO_BASE_URL" in updates and updates["IMAGE_BASE_URL"] == updates["VIDEO_BASE_URL"]:
        updates["ARK_ENDPOINT"] = updates["IMAGE_BASE_URL"]
    if "IMAGE_MODEL" in updates:
        updates["ARK_IMAGE_MODEL"] = updates["IMAGE_MODEL"]
    if "VIDEO_MODEL" in updates:
        updates["ARK_VIDEO_MODEL"] = updates["VIDEO_MODEL"]
    if not updates:
        return "没有检测到需要保存的配置"
    updates["PAC_LAST_SAVED_AT"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    update_env_local(updates)
    refresh_runtime_config()
    return ""


def normalize_choice(value, allowed_values, default_value):
    value = (value or "").strip()
    return value if value in allowed_values else default_value


def build_video_prompt_seed(
    name,
    category,
    primary_color,
    audience,
    selling_points,
    scenarios,
    video_motion,
    prompt_profile="auto",
    creative_latitude="balanced",
    prompt_density="balanced",
    authorized_brand_text="",
    logo_policy="no_logo",
    blocked_brand_terms=None,
    visual_guardrails=None,
    negative_prompt="",
):
    hero_scene = scenarios[0] if scenarios else "brand studio"
    highlights = ", ".join(selling_points[:3]) if selling_points else "fit, fabric texture, silhouette"
    audience_text = audience or "active women"
    color_text = primary_color or "black"
    motion_templates = {
        "showcase": (
            "Open with a steady hero frame, then use a slow push-in and clean half-body transitions. "
            "Keep the garment silhouette stable, emphasize product clarity, zipper line, and fabric support."
        ),
        "dynamic": (
            "Start with confident forward motion, then add rhythm through body turns, camera push, and a brief side follow shot. "
            "Keep motion energetic but controlled, suitable for short-form social content."
        ),
        "texture": (
            "Begin with a close-up fabric detail shot, transition to zipper and contour macro movement, then widen to a calm hero pose. "
            "Prioritize tactile texture, stitching, and light sweep across the garment surface."
        ),
    }
    motion_text = motion_templates.get(video_motion, motion_templates["showcase"])
    profile_text = {
        "auto": "Let the shot language follow the product evidence, selling points, and selected first frame.",
        "product_detail": "Prioritize product proof: material, construction, fit, support, closures, and close-up readability.",
        "lifestyle": "Prioritize believable lifestyle context, body movement, mood, and continuity with the selected scenario.",
        "social_ad": "Prioritize a strong first-second hook, clean pacing, and direct ecommerce readability for short-form ads.",
    }.get(prompt_profile, "Let the shot language follow the product evidence, selling points, and selected first frame.")
    latitude_text = {
        "strict": "Stay conservative: do not invent product features, colors, logos, or major scene elements.",
        "balanced": "Allow small creative completions only when they support the provided product facts.",
        "exploratory": "Allow broader scene and camera variation, while preserving product identity and factual constraints.",
    }.get(creative_latitude, "Allow small creative completions only when they support the provided product facts.")
    density_text = {
        "concise": "Use concise prompt language with only the highest-impact visual constraints.",
        "balanced": "Use complete prompt language covering subject, action, camera, lighting, material, and continuity.",
        "rich": "Use rich prompt language with detailed material cues, motion beats, lens choices, and transition rhythm.",
    }.get(prompt_density, "Use complete prompt language covering subject, action, camera, lighting, material, and continuity.")
    guardrail_text = "; ".join((visual_guardrails or [])[:5])
    brand_rule = (
        f"Brand/logo rule: only the authorized brand may appear ({authorized_brand_text}); no third-party brand marks."
        if authorized_brand_text and logo_policy != "no_logo"
        else "Brand/logo rule: plain unbranded apparel, no visible logo, no text label, no slogan, no badge, no hangtag text."
    )
    blocked_brand_text = ", ".join((blocked_brand_terms or [])[:16])
    negative_text = (negative_prompt or "").strip()
    return (
        f"Create a 12-second fashion video for a {color_text} {category or 'sportswear'} product named {name or 'hero item'}. "
        f"Target audience: {audience_text}. Primary scene: {hero_scene}. Key selling points: {highlights}. "
        f"{profile_text} {latitude_text} {density_text} {motion_text} {brand_rule} Preserve outfit identity, body proportions, and scene continuity. "
        f"{'Hard visual guardrails: ' + guardrail_text + '. ' if guardrail_text else ''}"
        f"{'Avoid: ' + negative_text + '. ' if negative_text else ''}"
        f"{'Forbidden brand terms: ' + blocked_brand_text + '. ' if blocked_brand_text else ''}"
        "Use premium commercial lighting, smooth camera movement, and end on a strong centered closing pose."
    )


def build_task_parameters_snapshot(
    sku,
    name,
    category,
    primary_color,
    target_audience,
    selling_points,
    scenarios,
    image_goal,
    video_motion,
    prompt_profile,
    creative_latitude,
    prompt_density,
    authorized_brand_text,
    logo_policy,
    blocked_brand_terms,
    visual_guardrails,
    shot_plan,
    negative_prompt,
):
    image_goal_labels = {
        "balanced": "平衡探索",
        "detail_focus": "细节优先",
        "scene_focus": "场景优先",
    }
    video_motion_labels = {
        "showcase": "稳态展示",
        "dynamic": "动态短片",
        "texture": "质感特写",
    }
    prompt_profile_labels = {
        "auto": "自动规划",
        "product_detail": "商品细节",
        "lifestyle": "生活方式",
        "social_ad": "社媒广告",
    }
    brand_negative_text = ", ".join(
        part for part in [
            negative_prompt,
            "third-party brand logo, unauthorized trademark, unauthorized wordmark, random garment text",
            ", ".join(blocked_brand_terms[:24]),
        ] if part
    )[:1000]
    garment_identity_hint = ", ".join(
        part for part in [
            f"SKU {sku}" if sku else "",
            name,
            category,
            f"primary color {primary_color}" if primary_color else "",
            "selling points: " + "; ".join(selling_points[:5]) if selling_points else "",
        ] if part
    )[:900]
    return {
        "source": "intake_form_v2",
        "requested_count": 11,
        "image_goal": image_goal,
        "image_goal_label": image_goal_labels.get(image_goal, image_goal),
        "video_motion": video_motion,
        "video_motion_label": video_motion_labels.get(video_motion, video_motion),
        "prompt_strategy": {
            "profile": prompt_profile,
            "profile_label": prompt_profile_labels.get(prompt_profile, prompt_profile),
            "creative_latitude": creative_latitude,
            "prompt_density": prompt_density,
            "authorized_brand_text": authorized_brand_text,
            "logo_policy": logo_policy,
            "blocked_brand_terms": blocked_brand_terms,
            "brand_safety": {
                "mode": "authorized_brand_only" if authorized_brand_text else "plain_unbranded_by_default",
                "positive_prompt_rule": (
                    f"Only the authorized brand/logo may appear: {authorized_brand_text}."
                    if authorized_brand_text else
                    "Plain unbranded apparel: no visible logo, no text label, no slogan, no badge, no hangtag text."
                ),
                "forbidden_brands": blocked_brand_terms,
            },
            "consistency": {
                "mode": "batch_garment_identity_lock",
                "garment_identity_hint": garment_identity_hint,
                "apply_when_user_prompt_is_sparse": True,
                "same_across_all_images": [
                    "product category",
                    "primary color and undertone",
                    "silhouette and fit",
                    "fabric/material finish",
                    "closure, seams, panels, neckline, waistband, pockets",
                    "logo/label policy",
                ],
                "allowed_to_change": ["pose", "camera angle", "crop", "lighting", "background scene"],
            },
            "visual_guardrails": visual_guardrails,
            "shot_plan": shot_plan,
            "negative_prompt": brand_negative_text,
            "user_negative_prompt": negative_prompt,
        },
        "input_snapshot": {
            "sku": sku,
            "name": name,
            "category": category,
            "primary_color": primary_color,
            "target_audience": target_audience,
            "selling_points": selling_points,
            "scenarios": scenarios,
        },
        "video_defaults": {
            "duration": 12,
            "ratio": "9:16",
            "voice": "zh-CN-XiaoxiaoNeural",
            "prompt_seed": build_video_prompt_seed(
                name,
                category,
                primary_color,
                target_audience,
                selling_points,
                scenarios,
                video_motion,
                prompt_profile,
                creative_latitude,
                prompt_density,
                authorized_brand_text,
                logo_policy,
                blocked_brand_terms,
                visual_guardrails,
                brand_negative_text,
            ),
        },
    }


def format_task_status(status, candidate_count=0, requested_count=11):
    status = (status or "").strip()
    if status in DONE_TASK_STATUSES or (requested_count > 0 and candidate_count >= requested_count):
        return "done"
    if "failed" in status:
        return "failed"
    if status in RUNNING_TASK_STATUSES:
        return "running"
    return "other"


def render_task_status_pill(status, candidate_count=0, requested_count=11):
    bucket = format_task_status(status, candidate_count=candidate_count, requested_count=requested_count)
    label_map = {
        "done": "已完成",
        "failed": "失败",
        "running": "生成中",
        "other": status or "未知",
    }
    cls_map = {
        "done": "pill-status pill-success",
        "failed": "pill-status pill-failed",
        "running": "pill-status pill-running",
        "other": "pill-status",
    }
    style = ' style="background:var(--slate-100);color:var(--slate-600)"' if bucket == "other" else ""
    return f'<span class="{cls_map[bucket]}"{style}><span class="dot"></span>{h(label_map[bucket])}</span>'


def purpose_label(value):
    mapping = {
        "selling_point_extract": "卖点拆解",
        "image_product": "商品图",
        "image_scene": "场景图",
        "video_storyboard": "分镜脚本",
        "video_shot": "单镜头",
        "video_prompt": "视频 Prompt",
        "tts_script": "口播文案",
        "style_guard": "风格守护",
    }
    return mapping.get((value or "").strip(), value or "-")


def pipeline_label(value):
    return {"image": "图片链路", "video": "视频链路"}.get((value or "").strip(), value or "-")


def priority_label(value):
    return {"low": "低", "normal": "普通", "high": "高", "urgent": "紧急"}.get((value or "").strip(), value or "-")


def shot_bucket(shot_type):
    shot = (shot_type or "").lower()
    if any(key in shot for key in ("scene", "yoga", "park", "mountain", "beach", "gym", "outdoor")):
        return "场景图"
    return "商品图"


def read_request_body(handler, max_bytes, body_name):
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except ValueError as exc:
        raise ValueError("Content-Length 非法") from exc
    if length <= 0:
        raise ValueError(f"{body_name} 不能为空")
    if length > max_bytes:
        raise ValueError(f"{body_name} 过大，超过 {max_bytes // 1024} KB")
    return handler.rfile.read(length)


def parse_int_field(value, field_name):
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 必须是整数") from exc


def upsert_product_and_task(form):
    """每次提交：upsert product + 新建 task（保留历史）"""
    sku = form.get("sku", ["YN-BRA-001"])[0].strip()[:64]
    name = form.get("name", [""])[0].strip()[:160]
    category = form.get("category", [""])[0].strip()[:64]
    selling_points = [s.strip()[:120] for s in form.get("selling_points", [""])[0].split("\n") if s.strip()]
    primary_color = form.get("primary_color", [""])[0].strip()[:32]
    target_audience = form.get("target_audience", [""])[0].strip()[:120]
    scenarios = [s.strip()[:80] for s in form.get("scenarios", [""])[0].split("\n") if s.strip()]
    image_goal = normalize_choice(form.get("image_goal", ["balanced"])[0], {"balanced", "detail_focus", "scene_focus"}, "balanced")
    video_motion = normalize_choice(form.get("video_motion", ["showcase"])[0], {"showcase", "dynamic", "texture"}, "showcase")
    prompt_profile = normalize_choice(form.get("prompt_profile", ["auto"])[0], ALLOWED_PROMPT_PROFILES, "auto")
    creative_latitude = normalize_choice(form.get("creative_latitude", ["balanced"])[0], ALLOWED_CREATIVE_LATITUDES, "balanced")
    prompt_density = normalize_choice(form.get("prompt_density", ["balanced"])[0], ALLOWED_PROMPT_DENSITIES, "balanced")
    authorized_brand_text = compact_multiline(form.get("authorized_brand_text", [""])[0], max_chars=120)
    logo_policy = normalize_choice(form.get("logo_policy", ["no_logo"])[0], ALLOWED_LOGO_POLICIES, "no_logo")
    raw_blocked_brand_terms = split_terms_limited(form.get("blocked_brand_terms", [""])[0], max_items=30, max_chars=48)
    blocked_brand_terms = merge_blocked_brand_terms(raw_blocked_brand_terms)
    if not authorized_brand_text and logo_policy == "own_logo_only":
        logo_policy = "no_logo"
    visual_guardrails = split_lines_limited(form.get("visual_guardrails", [""])[0], max_items=12, max_chars=160)
    shot_plan = split_lines_limited(form.get("shot_plan", [""])[0], max_items=16, max_chars=120)
    negative_prompt = compact_multiline(form.get("negative_prompt", [""])[0], max_chars=700)
    if not sku or not name:
        return None, "SKU 和产品名称必填"

    if len(selling_points) < 3:
        return None, "核心卖点至少填写 3 条，图片生成会更稳定"

    task_parameters_json = json.dumps(
        build_task_parameters_snapshot(
            sku,
            name,
            category,
            primary_color,
            target_audience,
            selling_points,
            scenarios,
            image_goal,
            video_motion,
            prompt_profile,
            creative_latitude,
            prompt_density,
            authorized_brand_text,
            logo_policy,
            blocked_brand_terms,
            visual_guardrails,
            shot_plan,
            negative_prompt,
        ),
        ensure_ascii=False,
    )

    # psql :'var' performs SQL literal quoting; arrays are passed as JSON then expanded in SQL.
    vars = {
        "sku": sku,
        "name": name,
        "category": category,
        "selling_points_json": json.dumps(selling_points, ensure_ascii=False),
        "primary_color": primary_color,
        "target_audience": target_audience,
        "scenarios_json": json.dumps(scenarios, ensure_ascii=False),
        "task_parameters_json": task_parameters_json,
    }
    upsert_sql = """
WITH defaults AS (
  SELECT
    (SELECT id FROM content_factory.tenants ORDER BY created_at LIMIT 1) AS tenant_id,
    (SELECT id FROM content_factory.style_templates ORDER BY created_at LIMIT 1) AS style_template_id,
    COALESCE((SELECT array_agg(value) FROM jsonb_array_elements_text(:'selling_points_json'::jsonb)), ARRAY[]::text[]) AS selling_points,
    COALESCE((SELECT array_agg(value) FROM jsonb_array_elements_text(:'scenarios_json'::jsonb)), ARRAY[]::text[]) AS scenarios
),
upserted AS (
  INSERT INTO content_factory.products (
    tenant_id, sku, name, category, selling_points, target_audience, use_scenarios,
    primary_color, reference_image_urls, style_template_id
  )
  SELECT
    tenant_id, :'sku', :'name', :'category', selling_points, :'target_audience', scenarios,
    :'primary_color', ARRAY[]::text[], style_template_id
  FROM defaults
  WHERE tenant_id IS NOT NULL
  ON CONFLICT (tenant_id, sku) DO UPDATE SET
    name = EXCLUDED.name,
    category = EXCLUDED.category,
    selling_points = EXCLUDED.selling_points,
    target_audience = EXCLUDED.target_audience,
    use_scenarios = EXCLUDED.use_scenarios,
    primary_color = EXCLUDED.primary_color,
    updated_at = now()
  RETURNING id
)
SELECT id FROM upserted;
"""
    out, err = pg_vars(upsert_sql, vars)
    if err and "ERROR" in err: return None, f"PG UPSERT: {err[:300]}"
    if not out: return None, "product upsert 失败：没有 tenant seed 数据"
    pid = out

    # 3. **新建** task（不复用旧的）
    task_title = f"{name[:60]} - {sku}"
    new_task_sql = """
INSERT INTO content_factory.tasks
  (tenant_id, product_id, pipeline, status, title, requested_count, parameters)
SELECT tenant_id, id, 'image', 'pending', :'task_title', 11, :'task_parameters_json'::jsonb
FROM content_factory.products
WHERE id = :'product_id'::uuid
RETURNING id;
"""
    tid, err = pg_vars(new_task_sql, {"product_id": pid, "task_title": task_title, "task_parameters_json": task_parameters_json})
    if err and "ERROR" in err: return None, f"PG task INSERT: {err[:300]}"
    if not tid: return None, "task 创建失败"
    return tid, None


def trigger_n8n(task_id):
    try:
        task_id = validate_uuid(task_id, "task_id")
    except ValueError as e:
        return 400, str(e)
    body = json.dumps({"task_id":task_id}).encode()
    req = urllib.request.Request(N8N_TRIGGER, data=body,
        headers={"Content-Type":"application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, r.read().decode()
    except urllib.error.URLError as e: return 500, str(e)
    except Exception as e: return 500, str(e)


def get_candidate_url(task_id, seq):
    """拿这个 task 的第 N 张候选图 URL"""
    task_id = validate_uuid(task_id, "task_id")
    seq = max(1, min(int(seq), 99))
    out, _ = pg_vars(
        "SELECT oss_url FROM content_factory.candidates WHERE task_id = :'task_id'::uuid AND media_type = 'image' AND sequence_no = :'seq'::int LIMIT 1;",
        {"task_id": task_id, "seq": str(seq)}
    )
    return out


def strip_seedance_control_params(text_prompt):
    """Remove inline Seedance flags so the backend owns ratio/duration consistently."""
    return SEEDANCE_CONTROL_PARAM_RE.sub("", text_prompt or "").strip()


def build_stable_i2v_prompt(text_prompt, duration=12, ratio="9:16"):
    prompt_core = strip_seedance_control_params(text_prompt)
    stability_rules = (
        "Use the provided first frame as the exact visual truth. "
        "Create one continuous commercial product shot, not a montage. "
        "Keep the same person, garment, color, logo policy, fabric texture, scene, and lighting from frame 0.0s to the end. "
        "Use only small natural body motion and a slow controlled camera move; avoid fast rotation, heavy zoom, whip pan, scene cut, object morphing, melting fabric, duplicated body, extra limbs, face drift, text overlay, watermark, and new logos. "
        "The product must stay readable and anatomically realistic throughout. "
        "End on a clean frame where the same product is still clearly visible."
    )
    return (
        f"{stability_rules} "
        f"User direction: {prompt_core[:900]} "
        f"--resolution 720p --ratio {ratio} --duration {int(duration)} --fps 24 --camera_fixed false --watermark false"
    ).strip()


def seedream_video_keyframe(reference_image_url, text_prompt, ratio="9:16"):
    """Create a ratio-correct first frame before image-to-video generation."""
    if not IMAGE_API_KEY:
        return None, "视频首帧功能未配置 IMAGE_API_KEY/MEDIA_API_KEY"
    size = VIDEO_RATIO_IMAGE_SIZES.get(ratio)
    if not size:
        return None, f"不支持的视频比例: {ratio}"
    prompt_core = strip_seedance_control_params(text_prompt)
    prompt = (
        f"Create a clean {ratio} first frame for an ecommerce short video, using the reference image as the visual anchor. "
        "Preserve the same model identity, outfit, product color, fabric texture, scene mood, and lighting. "
        "Create exactly one subject and one coherent garment; keep anatomy realistic and the product structure unchanged. "
        "Recompose to fully fill the target frame, centered subject with safe margins, no black bars, no letterboxing, "
        "no split screen, no duplicated body, no extra limbs, no text overlay, no watermark, no new logo. "
        f"Video direction: {prompt_core[:700]}"
    ).strip()
    body = {
        "model": SEEDREAM_MODEL,
        "prompt": prompt,
        "size": size,
        "guidance_scale": 3,
        "watermark": False,
        "response_format": "url",
        "reference_images": [reference_image_url],
    }
    req = urllib.request.Request(
        f"{IMAGE_BASE_URL}/images/generations",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {IMAGE_API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
        data = d.get("data") or []
        image_url = data[0].get("url") if data and isinstance(data[0], dict) else ""
        if not image_url:
            return None, f"Seedream 未返回视频首帧 URL: {str(d)[:240]}"
        return image_url, None
    except urllib.error.HTTPError as e:
        return None, f"Seedream HTTP {e.code}: {e.read().decode(errors='replace')[:240]}"
    except Exception as e:
        return None, str(e)


def prepare_seedance_first_frame(image_url, text_prompt, ratio="9:16"):
    """Seedance i2v is most stable when the first frame matches the output ratio."""
    if ratio == "1:1":
        return image_url, None
    keyframe_url, err = seedream_video_keyframe(image_url, text_prompt, ratio=ratio)
    if err:
        return None, err
    return keyframe_url, None


def seedance_submit(image_url, text_prompt, duration=12, ratio="9:16"):
    """给 Seedance 投递 image-to-video 任务，返回 task_id"""
    if not VIDEO_API_KEY:
        return None, "视频功能未配置 VIDEO_API_KEY/MEDIA_API_KEY"
    full_prompt = build_stable_i2v_prompt(text_prompt, duration=duration, ratio=ratio)
    body = {
        "model": SEEDANCE_MODEL,
        "content": [
            {"type": "text", "text": full_prompt},
            {"type": "image_url", "image_url": {"url": image_url}, "role": "first_frame"},
        ],
    }
    req = urllib.request.Request(
        f"{VIDEO_BASE_URL}/contents/generations/tasks",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {VIDEO_API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read())
        return d.get("id"), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, str(e)


def seedance_poll(seedance_task_id):
    """查 Seedance 任务状态。返回 {status, video_url?, error?}"""
    try:
        seedance_task_id = sanitize_task_token(seedance_task_id, "seedance_task_id")
    except ValueError as e:
        return {"status": "error", "error": str(e)}
    req = urllib.request.Request(
        f"{VIDEO_BASE_URL}/contents/generations/tasks/{seedance_task_id}",
        headers={"Authorization": f"Bearer {VIDEO_API_KEY}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
    except Exception as e:
        return {"status": "error", "error": str(e)}
    status = d.get("status")
    if status == "succeeded":
        # 找 video_url（可能在 content / output / data 等不同字段）
        url = ""
        for path in [("content", "video_url"), ("output", "video_url"), ("data", "video_url")]:
            obj = d
            for k in path:
                if isinstance(obj, dict):
                    obj = obj.get(k)
                else:
                    obj = None
                    break
            if isinstance(obj, str) and obj.startswith("http"):
                url = obj
                break
        # 也可能直接在顶层
        if not url:
            url = d.get("video_url", "") or ""
        if not url:
            return {"status": "failed", "error": "Seedance succeeded but video_url was empty"}
        return {"status": "succeeded", "video_url": url}
    if status == "failed":
        return {"status": "failed", "error": str(d.get("error", d))[:300]}
    return {"status": status or "running"}


def get_status(task_id):
    task_id = validate_uuid(task_id, "task_id")
    rows, rows_err = pg_rows_vars(
        "SELECT id::text, oss_url, COALESCE(parameters_snapshot->>'shot_type','') AS shot, sequence_no, status::text "
        "FROM content_factory.candidates "
        "WHERE task_id = :'task_id'::uuid AND media_type = 'image' AND status <> 'discarded' "
        "ORDER BY sequence_no, created_at;",
        {"task_id": task_id}
    )
    if rows_err:
        return {"status": "error", "error": f"数据库读取候选失败: {rows_err[:200]}"}
    cands = []
    for ln in rows:
        parts = ln.split("\t")
        if len(parts) >= 3:
            cands.append({
                "id": parts[0].strip(),
                "url": parts[1].strip(),
                "shot": parts[2].strip(),
                "sequence_no": int(parts[3].strip()) if len(parts) > 3 and parts[3].strip().isdigit() else len(cands) + 1,
                "status": parts[4].strip() if len(parts) > 4 else "pending_review",
            })
    run_rows, run_err = pg_rows_vars(
        "SELECT status::text, COALESCE(model_provider,''), COALESCE(model_name,''), COALESCE(purpose::text,''), "
        "COALESCE(duration_ms::text,''), COALESCE(cost_cny::text,''), COALESCE(error_message,''), "
        "COALESCE(started_at::text,''), COALESCE(finished_at::text,'') "
        "FROM content_factory.generation_runs WHERE task_id = :'task_id'::uuid "
        "ORDER BY COALESCE(started_at, created_at) DESC LIMIT 1;",
        {"task_id": task_id}
    )
    if run_err:
        return {"status": "error", "error": f"数据库读取任务状态失败: {run_err[:200]}"}
    latest_run = {}
    run_status = ""
    if run_rows:
        run_parts = run_rows[0].split("\t")
        latest_run = {
            "status": run_parts[0].strip() if len(run_parts) > 0 else "",
            "provider": run_parts[1].strip() if len(run_parts) > 1 else "",
            "model": run_parts[2].strip() if len(run_parts) > 2 else "",
            "purpose": run_parts[3].strip() if len(run_parts) > 3 else "",
            "duration_ms": run_parts[4].strip() if len(run_parts) > 4 else "",
            "cost_cny": run_parts[5].strip() if len(run_parts) > 5 else "",
            "error_message": run_parts[6].strip() if len(run_parts) > 6 else "",
            "started_at": run_parts[7].strip() if len(run_parts) > 7 else "",
            "finished_at": run_parts[8].strip() if len(run_parts) > 8 else "",
        }
        run_status = latest_run.get("status", "")
    task_rows, task_err = pg_rows_vars(
        "SELECT t.status::text, t.requested_count::text, COALESCE(t.parameters::text, '{}'), "
        "COALESCE(t.title, ''), COALESCE(p.name, ''), COALESCE(p.sku, '') "
        "FROM content_factory.tasks t "
        "JOIN content_factory.products p ON p.id = t.product_id "
        "WHERE t.id = :'task_id'::uuid LIMIT 1;",
        {"task_id": task_id}
    )
    if task_err:
        return {"status": "error", "error": f"读取任务元数据失败: {task_err[:200]}"}
    if not task_rows:
        return {
            "error": f"任务 {task_id[:8]} 不存在或已被删除",
            "error_code": "task_not_found",
            "task_id": task_id,
        }
    task_status = ""
    requested_count = 11
    parameters = {}
    title = ""
    product_name = ""
    sku = ""
    if task_rows:
        parts = task_rows[0].split("\t")
        if len(parts) >= 6:
            task_status = parts[0].strip()
            requested_count = int(parts[1].strip()) if parts[1].strip().isdigit() else 11
            parameters = load_json_text(parts[2].strip(), {})
            title = parts[3].strip()
            product_name = parts[4].strip()
            sku = parts[5].strip()
    normalized_status = task_status or run_status or "pending"
    if run_status in {"running", "queued", "pending"}:
        normalized_status = "pending"
    elif "failed" in (task_status or "") or run_status == "failed":
        normalized_status = "failed"
    elif run_status == "succeeded":
        normalized_status = "succeeded"
    elif run_status == "partial":
        normalized_status = "partial"
    elif task_status in DONE_TASK_STATUSES or task_status in {"candidates_ready", "reviewing"}:
        normalized_status = "succeeded"
    elif requested_count > 0 and len(cands) >= requested_count:
        normalized_status = "succeeded"
    if (
        len(cands) > 0
        and normalized_status in {"succeeded", "partial"}
        and task_status in {"pending", "analyzing", "prompting", "generating", "regenerating"}
    ):
        promoted_status, promote_err = pg_vars(
            """
UPDATE content_factory.tasks
SET status = 'candidates_ready',
    started_at = COALESCE(started_at, created_at),
    updated_at = now()
WHERE id = :'task_id'::uuid
  AND status IN ('pending','analyzing','prompting','generating','regenerating')
RETURNING status::text;
""",
            {"task_id": task_id},
        )
        if not promote_err and promoted_status:
            task_status = promoted_status
    candidate_counts = {
        "total": len(cands),
        "approved": sum(1 for item in cands if item.get("status") == "approved"),
        "rejected": sum(1 for item in cands if item.get("status") == "rejected"),
        "pending": sum(1 for item in cands if item.get("status") in {"new", "pending_review", "in_review"}),
        "missing": max(requested_count - len(cands), 0),
    }
    return {
        "status": normalized_status,
        "task_status": task_status,
        "run_status": run_status or "",
        "latest_run": latest_run,
        "requested_count": requested_count,
        "candidate_counts": candidate_counts,
        "parameters": parameters,
        "title": title,
        "product_name": product_name,
        "sku": sku,
        "candidates": cands,
    }


def parse_review_summary_row(row):
    parts = row.split("\t") if row else []
    return {
        "task_status": parts[0].strip() if len(parts) > 0 else "",
        "requested_count": int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0,
        "total": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0,
        "approved": int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0,
        "rejected": int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0,
        "pending": int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 0,
    }


def recompute_task_review_state(task_id):
    task_id = validate_uuid(task_id, "task_id")
    rows, err = pg_rows_vars(
        """
WITH counts AS (
  SELECT
    t.id AS task_id,
    t.status AS current_status,
    t.requested_count,
    COUNT(c.id) FILTER (
      WHERE c.media_type = 'image'
        AND c.status IN ('new','pending_review','in_review','approved','rejected')
    ) AS reviewable_total,
    COUNT(c.id) FILTER (WHERE c.media_type = 'image' AND c.status = 'approved') AS approved_count,
    COUNT(c.id) FILTER (WHERE c.media_type = 'image' AND c.status = 'rejected') AS rejected_count,
    COUNT(c.id) FILTER (WHERE c.media_type = 'image' AND c.status IN ('new','pending_review','in_review')) AS pending_count
  FROM content_factory.tasks t
  LEFT JOIN content_factory.candidates c ON c.task_id = t.id
  WHERE t.id = :'task_id'::uuid
  GROUP BY t.id
),
next_state AS (
  SELECT
    *,
    CASE
      WHEN reviewable_total > 0 AND pending_count = 0 AND approved_count = reviewable_total THEN 'approved'
      WHEN requested_count > 0 AND approved_count >= requested_count THEN 'approved'
      WHEN reviewable_total > 0 AND pending_count = 0 AND rejected_count > 0 THEN 'rejected'
      WHEN reviewable_total > 0 AND (approved_count + rejected_count) > 0 THEN 'reviewing'
      WHEN reviewable_total > 0 THEN 'candidates_ready'
      ELSE current_status::text
    END AS next_status
  FROM counts
),
updated AS (
  UPDATE content_factory.tasks t
  SET
    status = next_state.next_status::content_factory.task_status,
    finished_at = CASE
      WHEN next_state.next_status = 'approved' THEN COALESCE(t.finished_at, now())
      ELSE t.finished_at
    END,
    updated_at = now()
  FROM next_state
  WHERE t.id = next_state.task_id
  RETURNING
    t.status::text,
    next_state.requested_count::text,
    next_state.reviewable_total::text,
    next_state.approved_count::text,
    next_state.rejected_count::text,
    next_state.pending_count::text
)
SELECT * FROM updated;
""",
        {"task_id": task_id},
    )
    if err:
        return None, f"重算任务审核状态失败: {err[:240]}"
    if not rows:
        return None, "任务不存在"
    return parse_review_summary_row(rows[0]), None


def archive_approved_candidate(candidate_id, reviewer):
    candidate_id = validate_uuid(candidate_id, "candidate_id")
    reviewer = (reviewer or "local-ui").strip()[:80] or "local-ui"
    _, err = pg_vars(
        """
INSERT INTO content_factory.archive (
  tenant_id, product_id, task_id, candidate_id, media_type,
  final_oss_url, delivery_path, is_delivered, delivered_by, delivery_metadata
)
SELECT
  t.tenant_id,
  t.product_id,
  t.id,
  c.id,
  c.media_type,
  c.oss_url,
  'approved/' || regexp_replace(p.sku, '[^A-Za-z0-9_.-]+', '_', 'g') || '/' ||
    lpad(c.sequence_no::text, 2, '0') || '_' || replace(c.id::text, '-', ''),
  false,
  :'reviewer',
  jsonb_build_object(
    'source', 'local-ui',
    'sequence_no', c.sequence_no,
    'candidate_status', c.status::text,
    'archived_reason', 'candidate_approved'
  )
FROM content_factory.candidates c
JOIN content_factory.tasks t ON t.id = c.task_id
JOIN content_factory.products p ON p.id = t.product_id
WHERE c.id = :'candidate_id'::uuid AND c.status = 'approved'
ON CONFLICT (candidate_id) DO UPDATE SET
  final_oss_url = EXCLUDED.final_oss_url,
  delivery_path = EXCLUDED.delivery_path,
  delivered_by = EXCLUDED.delivered_by,
  delivery_metadata = archive.delivery_metadata || EXCLUDED.delivery_metadata,
  updated_at = now();
""",
        {"candidate_id": candidate_id, "reviewer": reviewer},
    )
    return err


def archive_approved_candidates(task_id, reviewer):
    task_id = validate_uuid(task_id, "task_id")
    reviewer = (reviewer or "local-ui").strip()[:80] or "local-ui"
    _, err = pg_vars(
        """
INSERT INTO content_factory.archive (
  tenant_id, product_id, task_id, candidate_id, media_type,
  final_oss_url, delivery_path, is_delivered, delivered_by, delivery_metadata
)
SELECT
  t.tenant_id,
  t.product_id,
  t.id,
  c.id,
  c.media_type,
  c.oss_url,
  'approved/' || regexp_replace(p.sku, '[^A-Za-z0-9_.-]+', '_', 'g') || '/' ||
    lpad(c.sequence_no::text, 2, '0') || '_' || replace(c.id::text, '-', ''),
  false,
  :'reviewer',
  jsonb_build_object(
    'source', 'local-ui',
    'sequence_no', c.sequence_no,
    'candidate_status', c.status::text,
    'archived_reason', 'bulk_or_task_approved'
  )
FROM content_factory.candidates c
JOIN content_factory.tasks t ON t.id = c.task_id
JOIN content_factory.products p ON p.id = t.product_id
WHERE c.task_id = :'task_id'::uuid
  AND c.media_type = 'image'
  AND c.status = 'approved'
ON CONFLICT (candidate_id) DO UPDATE SET
  final_oss_url = EXCLUDED.final_oss_url,
  delivery_path = EXCLUDED.delivery_path,
  delivered_by = EXCLUDED.delivered_by,
  delivery_metadata = archive.delivery_metadata || EXCLUDED.delivery_metadata,
  updated_at = now();
""",
        {"task_id": task_id, "reviewer": reviewer},
    )
    return err


def delete_candidate_archive(candidate_id):
    candidate_id = validate_uuid(candidate_id, "candidate_id")
    _, err = pg_vars(
        "DELETE FROM content_factory.archive WHERE candidate_id = :'candidate_id'::uuid;",
        {"candidate_id": candidate_id},
    )
    return err


def normalize_seedream_size(value):
    raw = str(value or "1024x1024").strip().lower()
    m = re.match(r"^(\d{3,4})\s*x\s*(\d{3,4})$", raw)
    if not m:
        return "1024x1024"
    w, hgt = int(m.group(1)), int(m.group(2))
    if w < 512 or hgt < 512 or w > 4096 or hgt > 4096:
        return "1024x1024"
    return f"{w}x{hgt}"


def numeric_seed(value):
    try:
        seed = int(value)
    except (TypeError, ValueError):
        seed = int(time.time() * 1000) % 2_000_000_000
    return max(1, min(seed, 2_000_000_000))


def seedream_regenerate_image(prompt, params, feedback=None):
    if not IMAGE_API_KEY:
        return None, None, "未配置 IMAGE_API_KEY/MEDIA_API_KEY，无法直接重新生成图片"
    prompt = (prompt or "").strip()
    if not prompt:
        return None, None, "候选图缺少 prompt_snapshot，无法按原图重生成"
    params = params or {}
    feedback_text = build_regeneration_feedback(feedback)
    regen_prompt = (
        f"{prompt}\n\n"
        "Regenerate a fresh alternative for this rejected candidate. Keep the same product, shot type, "
        "garment identity, composition intent, and brand color discipline. Keep the same clothing category, "
        "cut, fit, primary color, fabric finish, seams, panels, neckline, waistband, pockets, and logo/label "
        "policy across the batch. Do not invent third-party brand marks, logos, labels, slogans, random text, "
        "or mixed brand identities. Vary only micro-pose, framing, lighting detail, background nuance, and "
        "texture fidelity enough that it is a new candidate."
    )
    if feedback_text:
        regen_prompt += "\n\nApply the human rejection feedback precisely. Fix only the rejected issue; do not change the locked garment identity.\n" + feedback_text
    try:
        guidance_scale = float(params.get("guidance_scale") or 5.5)
    except (TypeError, ValueError):
        guidance_scale = 5.5
    body = {
        "model": SEEDREAM_MODEL,
        "prompt": regen_prompt,
        "size": normalize_seedream_size(params.get("image_size") or params.get("suggested_size")),
        "seed": (numeric_seed(params.get("seed")) + 17) % 2_000_000_000 or 1,
        "guidance_scale": guidance_scale,
        "watermark": False,
        "response_format": "url",
    }
    negative_prompt = params.get("negative_prompt")
    if negative_prompt:
        body["negative_prompt"] = str(negative_prompt)
    req = urllib.request.Request(
        f"{IMAGE_BASE_URL}/images/generations",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {IMAGE_API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:300]
        return None, None, f"Seedream HTTP {e.code}: {err_body}"
    except Exception as e:
        return None, None, f"Seedream 调用失败: {e}"
    image_url = ""
    if isinstance(data.get("data"), list) and data["data"]:
        image_url = data["data"][0].get("url") or ""
    if not image_url:
        return None, data.get("id") or "", f"Seedream 返回中没有图片 URL: {json.dumps(data, ensure_ascii=False)[:300]}"
    return image_url, data.get("id") or data.get("request_id") or "", None


def review_candidate(payload):
    if not isinstance(payload, dict):
        raise ValueError("请求体必须是 JSON 对象")
    task_id = validate_uuid(payload.get("task_id", ""), "task_id")
    action = (payload.get("action") or "").strip()
    if action not in {"approve", "reject", "clear"}:
        raise ValueError("action 仅支持 approve / reject / clear")
    reviewer = (payload.get("reviewer") or "local-ui").strip()[:80] or "local-ui"
    candidate_id = (payload.get("candidate_id") or "").strip()
    seq = payload.get("seq")
    reason_category = clean_review_text(payload.get("reason_category"), 80)
    review_comment = clean_review_text(payload.get("comment"), 700)
    preserve_note = clean_review_text(payload.get("preserve"), 360)

    if candidate_id:
        candidate_id = validate_uuid(candidate_id, "candidate_id")
        rows, err = pg_rows_vars(
            """
SELECT c.id::text, c.status::text, c.sequence_no::text, c.task_id::text
FROM content_factory.candidates c
WHERE c.task_id = :'task_id'::uuid
  AND c.id = :'candidate_id'::uuid
  AND c.media_type = 'image'
LIMIT 1;
""",
            {"task_id": task_id, "candidate_id": candidate_id},
        )
    else:
        seq = parse_int_field(seq, "seq")
        if seq <= 0 or seq > 999:
            raise ValueError("seq 超出范围")
        rows, err = pg_rows_vars(
            """
SELECT c.id::text, c.status::text, c.sequence_no::text, c.task_id::text
FROM content_factory.candidates c
WHERE c.task_id = :'task_id'::uuid
  AND c.sequence_no = :'seq'::int
  AND c.media_type = 'image'
LIMIT 1;
""",
            {"task_id": task_id, "seq": str(seq)},
        )
    if err:
        return None, f"读取候选失败: {err[:200]}"
    if not rows:
        return None, "候选图不存在或不属于当前任务"

    current_id, current_status, sequence_no, _ = [p.strip() for p in rows[0].split("\t")[:4]]
    if action == "approve":
        new_status = "pending_review" if current_status == "approved" else "approved"
        audit_action = "comment" if current_status == "approved" else "approve"
        message = f"已取消候选图 #{sequence_no} 的通过" if current_status == "approved" else f"候选图 #{sequence_no} 已通过"
    elif action == "reject":
        new_status = "pending_review" if current_status == "rejected" else "rejected"
        audit_action = "comment" if current_status == "rejected" else "reject"
        message = f"已取消候选图 #{sequence_no} 的驳回" if current_status == "rejected" else f"候选图 #{sequence_no} 已驳回"
        if current_status != "rejected" and (reason_category or review_comment):
            message += f"（{reason_category or '需要修改'}"
            if review_comment:
                message += f": {review_comment[:80]}"
            message += "）"
    else:
        new_status = "pending_review"
        audit_action = "comment"
        message = f"候选图 #{sequence_no} 已恢复为待审"

    rows, update_err = pg_rows_vars(
        """
UPDATE content_factory.candidates
SET status = :'new_status'::content_factory.candidate_status,
    updated_at = now()
WHERE id = :'candidate_id'::uuid
RETURNING id::text, status::text, sequence_no::text;
""",
        {"candidate_id": current_id, "new_status": new_status},
    )
    if update_err:
        return None, f"更新候选状态失败: {update_err[:240]}"
    if not rows:
        return None, "候选状态未更新"

    metadata_obj = {
        "source": "local-ui",
        "ui_action": action,
        "previous_status": current_status,
        "new_status": new_status,
    }
    if action == "reject" and current_status != "rejected":
        metadata_obj["reason_category"] = reason_category or "unspecified"
        metadata_obj["comment"] = review_comment
        metadata_obj["preserve"] = preserve_note
        metadata_obj["regeneration_hint"] = build_regeneration_feedback(metadata_obj)
    metadata = json.dumps(metadata_obj, ensure_ascii=False)
    _, audit_err = pg_vars(
        """
INSERT INTO content_factory.audit_log (candidate_id, task_id, reviewer, action, comment, metadata)
VALUES (
  :'candidate_id'::uuid,
  :'task_id'::uuid,
  :'reviewer',
  :'audit_action'::content_factory.audit_action,
  :'comment',
  :'metadata'::jsonb
);
""",
        {
            "candidate_id": current_id,
            "task_id": task_id,
            "reviewer": reviewer,
            "audit_action": audit_action,
            "comment": message,
            "metadata": metadata,
        },
    )
    if audit_err:
        return None, f"写入审核日志失败: {audit_err[:240]}"

    if new_status == "approved":
        archive_err = archive_approved_candidate(current_id, reviewer)
        if archive_err:
            return None, f"写入归档记录失败: {archive_err[:240]}"
    elif current_status == "approved":
        archive_err = delete_candidate_archive(current_id)
        if archive_err:
            return None, f"撤销归档记录失败: {archive_err[:240]}"

    summary, summary_err = recompute_task_review_state(task_id)
    if summary_err:
        return None, summary_err
    if summary and summary.get("task_status") == "approved":
        archive_err = archive_approved_candidates(task_id, reviewer)
        if archive_err:
            return None, f"批量归档已通过候选失败: {archive_err[:240]}"

    updated_parts = rows[0].split("\t")
    return {
        "candidate": {
            "id": updated_parts[0].strip(),
            "status": updated_parts[1].strip(),
            "sequence_no": int(updated_parts[2]) if len(updated_parts) > 2 and updated_parts[2].isdigit() else int(sequence_no),
        },
        "summary": summary,
        "message": message,
    }, None


def approve_all_candidates(task_id, reviewer="local-ui"):
    task_id = validate_uuid(task_id, "task_id")
    reviewer = (reviewer or "local-ui").strip()[:80] or "local-ui"
    rows, err = pg_rows_vars(
        """
WITH target AS (
  SELECT id, task_id, status, sequence_no
  FROM content_factory.candidates
  WHERE task_id = :'task_id'::uuid
    AND media_type = 'image'
    AND status IN ('new','pending_review','in_review','approved')
),
changed AS (
  UPDATE content_factory.candidates c
  SET status = 'approved',
      updated_at = now()
  FROM target
  WHERE c.id = target.id
    AND c.status <> 'approved'
  RETURNING c.id, c.task_id, target.status AS previous_status, c.sequence_no
),
audit AS (
  INSERT INTO content_factory.audit_log (candidate_id, task_id, reviewer, action, comment, metadata)
  SELECT
    id,
    task_id,
    :'reviewer',
    'approve'::content_factory.audit_action,
    '批量全部通过',
    jsonb_build_object('source', 'local-ui', 'ui_action', 'approve_all', 'previous_status', previous_status::text)
  FROM changed
  RETURNING id
)
SELECT
  (SELECT COUNT(*)::text FROM target),
  (SELECT COUNT(*)::text FROM changed);
""",
        {"task_id": task_id, "reviewer": reviewer},
    )
    if err:
        return None, f"批量通过失败: {err[:240]}"
    if not rows:
        return None, "当前任务没有可审核候选图"
    total, changed = rows[0].split("\t")[:2]
    total_count = int(total) if total.isdigit() else 0
    changed_count = int(changed) if changed.isdigit() else 0
    if total_count == 0:
        return None, "当前任务没有可审核候选图"

    archive_err = archive_approved_candidates(task_id, reviewer)
    if archive_err:
        return None, f"批量归档失败: {archive_err[:240]}"
    summary, summary_err = recompute_task_review_state(task_id)
    if summary_err:
        return None, summary_err
    return {
        "summary": summary,
        "total": total_count,
        "changed": changed_count,
        "message": f"已将 {total_count} 张未驳回候选图标记为通过",
    }, None


def regenerate_rejected_candidates(task_id, reviewer="local-ui", candidate_ids=None):
    task_id = validate_uuid(task_id, "task_id")
    reviewer = (reviewer or "local-ui").strip()[:80] or "local-ui"
    candidate_ids = candidate_ids or []
    if not isinstance(candidate_ids, list):
        raise ValueError("candidate_ids 必须是数组")
    validated_candidate_ids = []
    seen_candidate_ids = set()
    for raw_id in candidate_ids:
        candidate_id = validate_uuid(raw_id, "candidate_id")
        if candidate_id not in seen_candidate_ids:
            seen_candidate_ids.add(candidate_id)
            validated_candidate_ids.append(candidate_id)
    candidate_ids_json = json.dumps(validated_candidate_ids)

    rows, err = pg_rows_vars(
        """
SELECT
  t.status::text,
  t.retry_count::text,
  t.max_retries::text,
  COUNT(c.id) FILTER (
    WHERE c.media_type = 'image'
      AND c.status = 'rejected'
      AND (
        jsonb_array_length(:'candidate_ids_json'::jsonb) = 0
        OR c.id::text IN (SELECT value FROM jsonb_array_elements_text(:'candidate_ids_json'::jsonb))
      )
  )::text
FROM content_factory.tasks t
LEFT JOIN content_factory.candidates c ON c.task_id = t.id
WHERE t.id = :'task_id'::uuid
GROUP BY t.id
LIMIT 1;
""",
        {"task_id": task_id, "candidate_ids_json": candidate_ids_json},
    )
    if err:
        return None, f"读取驳回候选失败: {err[:200]}"
    if not rows:
        return None, "任务不存在"
    parts = rows[0].split("\t")
    retry_count = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    max_retries = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 3
    rejected_count = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
    if rejected_count <= 0:
        return None, "没有驳回的候选图需要重新生成"
    if max_retries > 0 and retry_count >= max_retries:
        return None, f"已达到最大重试次数 {retry_count}/{max_retries}，请先调整提示词或任务参数后再重新生成"

    _, audit_err = pg_vars(
        """
INSERT INTO content_factory.audit_log (candidate_id, task_id, reviewer, action, comment, metadata)
SELECT
  c.id,
  c.task_id,
  :'reviewer',
  'request_revision'::content_factory.audit_action,
  '重新生成驳回候选',
  jsonb_build_object('source', 'local-ui', 'ui_action', 'regenerate_rejected', 'retry_from', :'retry_count'::int)
FROM content_factory.candidates c
WHERE c.task_id = :'task_id'::uuid
  AND c.media_type = 'image'
  AND c.status = 'rejected'
  AND (
    jsonb_array_length(:'candidate_ids_json'::jsonb) = 0
    OR c.id::text IN (SELECT value FROM jsonb_array_elements_text(:'candidate_ids_json'::jsonb))
  );
""",
        {"task_id": task_id, "reviewer": reviewer, "retry_count": str(retry_count), "candidate_ids_json": candidate_ids_json},
    )
    if audit_err:
        return None, f"写入重新生成审核日志失败: {audit_err[:240]}"

    next_retry, update_err = pg_vars(
        """
UPDATE content_factory.tasks
SET status = 'regenerating',
    retry_count = retry_count + 1,
    error_message = NULL,
    updated_at = now()
WHERE id = :'task_id'::uuid
  AND (max_retries <= 0 OR retry_count < max_retries)
RETURNING retry_count::text;
""",
        {"task_id": task_id},
    )
    if update_err:
        return None, f"更新任务重生成状态失败: {update_err[:240]}"
    if not next_retry:
        return None, f"已达到最大重试次数 {retry_count}/{max_retries}，请先调整提示词或任务参数后再重新生成"

    target_rows, target_err = pg_rows_vars(
        """
SELECT
  c.id::text,
  c.sequence_no::text,
  COALESCE(c.prompt_snapshot, ''),
  c.parameters_snapshot::text,
  COALESCE(c.run_id::text, ''),
  c.status::text,
  COALESCE(latest_reject.metadata::text, '{}'::text),
  COALESCE(latest_reject.comment, '')
FROM content_factory.candidates c
LEFT JOIN LATERAL (
  SELECT al.metadata, al.comment
  FROM content_factory.audit_log al
  WHERE al.candidate_id = c.id
    AND al.action = 'reject'
  ORDER BY al.created_at DESC
  LIMIT 1
) latest_reject ON TRUE
WHERE c.task_id = :'task_id'::uuid
  AND c.media_type = 'image'
  AND c.status = 'rejected'
  AND (
    jsonb_array_length(:'candidate_ids_json'::jsonb) = 0
    OR c.id::text IN (SELECT value FROM jsonb_array_elements_text(:'candidate_ids_json'::jsonb))
  )
ORDER BY c.sequence_no, c.created_at
LIMIT 20;
""",
        {"task_id": task_id, "candidate_ids_json": candidate_ids_json},
    )
    if target_err:
        return None, f"读取重生成目标失败: {target_err[:240]}"
    if not target_rows:
        return None, "没有找到可重生成的驳回候选"

    run_id, run_err = pg_vars(
        """
INSERT INTO content_factory.generation_runs (
  task_id, sequence_no, model_provider, model_name, purpose, status, started_at, input_payload
)
VALUES (
  :'task_id'::uuid,
  COALESCE((SELECT MAX(sequence_no)+1 FROM content_factory.generation_runs WHERE task_id = :'task_id'::uuid), 1),
  :'model_provider',
  :'model_name',
  'image_product',
  'running',
  now(),
  jsonb_build_object(
    'source', 'local-ui',
    'mode', 'regenerate_rejected_only',
    'candidate_ids', :'candidate_ids_json'::jsonb,
    'retry_count', :'next_retry'::int
  )
)
RETURNING id::text;
""",
        {
            "task_id": task_id,
            "candidate_ids_json": candidate_ids_json,
            "next_retry": str(next_retry or retry_count + 1),
            "model_provider": IMAGE_PROVIDER,
            "model_name": SEEDREAM_MODEL,
        },
    )
    if run_err:
        return None, f"创建重生成批次失败: {run_err[:240]}"

    generated = []
    failures = []
    for row in target_rows:
        parts = row.split("\t")
        if len(parts) < 8:
            continue
        old_id, seq, prompt, params_raw, _, old_status, feedback_raw, feedback_comment = [part.strip() for part in parts[:8]]
        params = load_json_text(params_raw, {})
        feedback = load_json_text(feedback_raw, {})
        if feedback_comment and not feedback.get("comment"):
            feedback["comment"] = feedback_comment
        image_url, ark_request_id, gen_err = seedream_regenerate_image(prompt, params, feedback)
        if gen_err:
            failures.append({"candidate_id": old_id, "sequence_no": seq, "error": gen_err})
            continue

        params["regenerated_from_candidate_id"] = old_id
        params["regenerated_from_status"] = old_status
        params["regeneration_feedback"] = feedback
        params["regenerated_by"] = reviewer
        params["regenerated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        params["ark_request_id"] = ark_request_id
        params["regeneration_mode"] = "direct_seedream_rejected_only"
        params["generation_cost_cny"] = params.get("generation_cost_cny", 0.3)
        insert_rows, insert_err = pg_rows_vars(
            """
WITH inserted AS (
  INSERT INTO content_factory.candidates (
    task_id, run_id, media_type, oss_url, thumbnail_url, prompt_snapshot,
    parameters_snapshot, status, sequence_no, created_at
  )
  VALUES (
    :'task_id'::uuid,
    :'run_id'::uuid,
    'image',
    :'image_url',
    :'image_url',
    :'prompt',
    :'parameters'::jsonb,
    'pending_review',
    :'sequence_no'::int,
    now()
  )
  RETURNING id::text, sequence_no::text
),
discarded AS (
  UPDATE content_factory.candidates
  SET status = 'discarded',
      updated_at = now()
  WHERE id = :'old_id'::uuid
  RETURNING id
)
SELECT id, sequence_no FROM inserted;
""",
            {
                "task_id": task_id,
                "run_id": run_id,
                "image_url": image_url,
                "prompt": prompt,
                "parameters": json.dumps(params, ensure_ascii=False),
                "sequence_no": seq,
                "old_id": old_id,
            },
        )
        if insert_err:
            failures.append({"candidate_id": old_id, "sequence_no": seq, "error": f"写入新候选失败: {insert_err[:220]}"})
            continue
        new_id = insert_rows[0].split("\t")[0].strip() if insert_rows else ""
        generated.append({"old_candidate_id": old_id, "candidate_id": new_id, "sequence_no": int(seq) if seq.isdigit() else seq, "url": image_url})

    run_status = "succeeded" if generated and not failures else "partial" if generated else "failed"
    pg_vars(
        """
UPDATE content_factory.generation_runs
SET status = :'run_status'::content_factory.run_status,
    output_payload = :'output_payload'::jsonb,
    error_message = :'error_message',
    finished_at = now(),
    updated_at = now()
WHERE id = :'run_id'::uuid;
""",
        {
            "run_id": run_id,
            "run_status": run_status,
            "output_payload": json.dumps({"generated": generated, "failures": failures}, ensure_ascii=False),
            "error_message": "; ".join(item["error"] for item in failures)[:1000],
        },
    )
    if not generated:
        pg_vars(
            """
UPDATE content_factory.tasks
SET status = 'failed_recoverable',
    error_message = :'error_message',
    updated_at = now()
WHERE id = :'task_id'::uuid;
""",
            {"task_id": task_id, "error_message": "; ".join(item["error"] for item in failures)[:1000]},
        )
        return None, failures[0]["error"] if failures else "重生成失败"

    if failures:
        pg_vars(
            """
UPDATE content_factory.tasks
SET status = 'failed_recoverable',
    error_message = :'error_message',
    updated_at = now()
WHERE id = :'task_id'::uuid;
""",
            {"task_id": task_id, "error_message": ("部分驳回候选重生成失败: " + "; ".join(item["error"] for item in failures))[:1000]},
        )
    else:
        pg_vars(
            """
UPDATE content_factory.tasks
SET status = 'candidates_ready',
    error_message = NULL,
    updated_at = now()
WHERE id = :'task_id'::uuid;
""",
            {"task_id": task_id},
        )
    return {
        "task_id": task_id,
        "rejected_count": rejected_count,
        "generated_count": len(generated),
        "failures": failures,
        "retry_count": int(next_retry) if str(next_retry).isdigit() else retry_count + 1,
        "message": f"已重新生成 {len(generated)} 张驳回候选",
    }, None


def safe_zip_name(value, fallback):
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "").strip("._")
    return cleaned[:80] or fallback


def build_candidates_zip(task_id):
    task_id = validate_uuid(task_id, "task_id")
    raw, err = pg_vars(
        """
WITH approved_exists AS (
  SELECT EXISTS (
    SELECT 1 FROM content_factory.candidates
    WHERE task_id = :'task_id'::uuid
      AND media_type IN ('image','video')
      AND status = 'approved'
  ) AS has_approved
),
selected_candidates AS (
  SELECT
    c.id,
    c.sequence_no,
    c.media_type,
    c.oss_url,
    c.thumbnail_url,
    c.status,
    COALESCE(c.parameters_snapshot, '{}'::jsonb) AS parameters_snapshot,
    COALESCE(c.prompt_snapshot, '') AS prompt_snapshot,
    c.created_at,
    p.sku,
    p.name AS product_name,
    COALESCE(p.category, '') AS category,
    t.title,
    t.status AS task_status,
    t.pipeline,
    t.requested_count,
    COALESCE(t.parameters, '{}'::jsonb) AS task_parameters,
    COALESCE(gr.model_provider, '') AS model_provider,
    COALESCE(gr.model_name, '') AS model_name,
    COALESCE(gr.purpose::text, '') AS run_purpose,
    COALESCE(gr.status::text, '') AS run_status,
    COALESCE(gr.cost_cny::text, '') AS run_cost_cny,
    COALESCE(gr.duration_ms::text, '') AS run_duration_ms,
    COALESCE(gr.started_at::text, '') AS run_started_at,
    COALESCE(gr.finished_at::text, '') AS run_finished_at,
    COALESCE((
      SELECT json_agg(json_build_object(
        'created_at', al.created_at::text,
        'reviewer', al.reviewer,
        'action', al.action::text,
        'comment', COALESCE(al.comment, ''),
        'metadata', al.metadata
      ) ORDER BY al.created_at ASC)
      FROM content_factory.audit_log al
      WHERE al.candidate_id = c.id
    ), '[]'::json) AS audit_entries
  FROM content_factory.candidates c
  JOIN content_factory.tasks t ON t.id = c.task_id
  JOIN content_factory.products p ON p.id = t.product_id
  LEFT JOIN content_factory.generation_runs gr ON gr.id = c.run_id
  CROSS JOIN approved_exists ae
  WHERE c.task_id = :'task_id'::uuid
    AND c.media_type IN ('image','video')
    AND (
      (ae.has_approved AND c.status = 'approved')
      OR
      (NOT ae.has_approved AND c.status IN ('new','pending_review','in_review','approved','rejected'))
    )
)
SELECT COALESCE(json_agg(json_build_object(
  'candidate_id', id::text,
  'sequence_no', sequence_no,
  'media_type', media_type::text,
  'url', oss_url,
  'thumbnail_url', COALESCE(thumbnail_url, ''),
  'status', status::text,
  'shot_type', COALESCE(parameters_snapshot->>'shot_type', ''),
  'parameters_snapshot', parameters_snapshot,
  'prompt_snapshot', prompt_snapshot,
  'created_at', created_at::text,
  'sku', sku,
  'product_name', product_name,
  'category', category,
  'task_title', title,
  'task_status', task_status::text,
  'pipeline', pipeline::text,
  'requested_count', requested_count,
  'task_parameters', task_parameters,
  'run', json_build_object(
    'provider', model_provider,
    'model', model_name,
    'purpose', run_purpose,
    'status', run_status,
    'cost_cny', run_cost_cny,
    'duration_ms', run_duration_ms,
    'started_at', run_started_at,
    'finished_at', run_finished_at
  ),
  'audit_log', audit_entries
) ORDER BY sequence_no ASC, created_at ASC), '[]'::json)::text
FROM selected_candidates;
""",
        {"task_id": task_id},
    )
    if err:
        return None, None, f"读取导出候选失败: {err[:240]}"
    counts_raw, _ = pg_vars(
        """
SELECT json_build_object(
  'total', COUNT(*) FILTER (WHERE status <> 'discarded'),
  'approved', COUNT(*) FILTER (WHERE status = 'approved'),
  'rejected', COUNT(*) FILTER (WHERE status = 'rejected'),
  'pending', COUNT(*) FILTER (WHERE status IN ('new','pending_review','in_review')),
  'discarded', COUNT(*) FILTER (WHERE status = 'discarded')
)::text
FROM content_factory.candidates
WHERE task_id = :'task_id'::uuid
  AND media_type IN ('image','video');
""",
        {"task_id": task_id},
    )
    status_counts = load_json_text(counts_raw, {})
    items = load_json_text(raw, [])
    if not items:
        return None, None, "没有可导出的候选图"

    manifest = []
    first_sku = "content-factory"
    task_title = ""
    audit_log = []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item_data in items:
            seq = str(item_data.get("sequence_no") or len(manifest) + 1)
            cid = str(item_data.get("candidate_id") or "")
            url = str(item_data.get("url") or "")
            status = str(item_data.get("status") or "")
            shot = str(item_data.get("shot_type") or "")
            media_type = str(item_data.get("media_type") or "image")
            sku = str(item_data.get("sku") or "")
            title = str(item_data.get("task_title") or "")
            task_title = task_title or title
            first_sku = safe_zip_name(sku, first_sku)
            parsed = urllib.parse.urlparse(url)
            ext = Path(parsed.path).suffix.lower()
            allowed_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"} if media_type == "image" else {".mp4", ".mov", ".webm", ".m4v"}
            if ext not in allowed_exts:
                ext = ".jpg" if media_type == "image" else ".mp4"
            seq_label = int(seq) if str(seq).isdigit() else len(manifest) + 1
            base = f"{seq_label:02d}_{safe_zip_name(shot or media_type, 'candidate')}_{status}"
            media_dir = "images" if media_type == "image" else "videos"
            item = {
                "sequence_no": seq,
                "candidate_id": cid,
                "media_type": media_type,
                "status": status,
                "shot_type": shot,
                "url": url,
                "prompt_file": f"prompts/{base}.txt",
                "parameters_file": f"parameters/{base}.json",
                "exported_file": f"{media_dir}/{base}{ext}",
                "run": item_data.get("run") or {},
            }
            zf.writestr(item["prompt_file"], (item_data.get("prompt_snapshot") or "").strip() + "\n")
            zf.writestr(
                item["parameters_file"],
                json.dumps(item_data.get("parameters_snapshot") or {}, ensure_ascii=False, indent=2),
            )
            for audit_item in item_data.get("audit_log") or []:
                audit_log.append({"candidate_id": cid, "sequence_no": seq, **audit_item})
            try:
                safe_url = safe_http_url(url)
                if not safe_url:
                    raise ValueError("不是有效 HTTP/HTTPS 素材 URL")
                req = urllib.request.Request(safe_url, headers={"User-Agent": "ContentFactoryLocalExport/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = resp.read(50 * 1024 * 1024 + 1)
                if len(data) > 50 * 1024 * 1024:
                    raise ValueError("素材超过 50MB，已跳过下载")
                zf.writestr(f"{media_dir}/{base}{ext}", data)
                item["downloaded"] = True
            except Exception as exc:
                item["downloaded"] = False
                item["error"] = str(exc)[:240]
                item["exported_file"] = f"links/{base}.url.txt"
                zf.writestr(f"links/{base}.url.txt", f"{url}\n\n下载失败: {item['error']}\n")
            manifest.append(item)
        zf.writestr("audit-log.json", json.dumps(audit_log, ensure_ascii=False, indent=2))
        zf.writestr(
            "delivery-summary.md",
            "\n".join([
                f"# ContentFactory Delivery Package",
                "",
                f"- Task: {task_title or task_id}",
                f"- Task ID: {task_id}",
                f"- SKU: {first_sku}",
                f"- Exported items: {len(manifest)}",
                f"- Candidate status: approved {status_counts.get('approved', 0)}, rejected {status_counts.get('rejected', 0)}, pending {status_counts.get('pending', 0)}",
                f"- Export rule: approved candidates first; if nothing is approved, current reviewable candidates are included.",
                "",
                "See `manifest.json`, `prompts/`, `parameters/`, and `audit-log.json` for reproduction and review context.",
                "",
            ]),
        )
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "task_id": task_id,
                    "sku": first_sku,
                    "task_title": task_title,
                    "package_version": 2,
                    "candidate_status_counts": status_counts,
                    "export_rule": "优先导出已通过候选；如果还没有通过素材，则导出当前可审核候选。",
                    "items": manifest,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    buf.seek(0)
    filename = f"{first_sku}-{task_id[:8]}-candidates.zip"
    return filename, buf.getvalue(), None


def delete_task(task_id):
    task_id = validate_uuid(task_id, "task_id")
    rows, meta_err = pg_rows_vars(
        "SELECT t.id::text, COALESCE(p.name, ''), "
        "(SELECT COUNT(*)::text FROM content_factory.candidates WHERE task_id = t.id), "
        "(SELECT COUNT(*)::text FROM content_factory.generation_runs WHERE task_id = t.id) "
        "FROM content_factory.tasks t "
        "JOIN content_factory.products p ON p.id = t.product_id "
        "WHERE t.id = :'task_id'::uuid LIMIT 1;",
        {"task_id": task_id},
    )
    if meta_err:
        return None, f"删除前读取任务失败: {meta_err[:200]}"
    if not rows:
        return None, "任务不存在或已删除"

    parts = rows[0].split("\t")
    title = parts[1].strip() if len(parts) > 1 else ""
    candidate_count = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    run_count = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0

    deleted_id, delete_err = pg_vars(
        "DELETE FROM content_factory.tasks WHERE id = :'task_id'::uuid RETURNING id::text;",
        {"task_id": task_id},
    )
    if delete_err:
        return None, f"删除任务失败: {delete_err[:200]}"
    if not deleted_id:
        return None, "任务不存在或已删除"

    return {
        "task_id": deleted_id,
        "title": title,
        "candidate_count": candidate_count,
        "run_count": run_count,
    }, None


def delete_tasks(task_ids):
    if not isinstance(task_ids, list):
        raise ValueError("task_ids 必须是数组")

    validated = []
    seen = set()
    for raw in task_ids:
        task_id = validate_uuid(raw, "task_id")
        if task_id not in seen:
            seen.add(task_id)
            validated.append(task_id)

    if not validated:
        raise ValueError("至少选择一个任务")
    if len(validated) > 100:
        raise ValueError("单次最多删除 100 个任务")

    deleted = []
    errors = []
    for task_id in validated:
        result, err = delete_task(task_id)
        if err:
            errors.append({"task_id": task_id, "error": err})
        else:
            deleted.append(result)

    return {
        "requested": len(validated),
        "deleted": deleted,
        "errors": errors,
    }


def get_task_detail(task_id):
    task_id = validate_uuid(task_id, "task_id")
    raw, detail_err = pg_vars(
        """
SELECT json_build_object(
  'task_id', t.id::text,
  'title', t.title,
  'status', t.status::text,
  'pipeline', t.pipeline::text,
  'priority', t.priority::text,
  'requested_count', t.requested_count,
  'retry_count', t.retry_count,
  'max_retries', t.max_retries,
  'error_message', COALESCE(t.error_message, ''),
  'created_by', COALESCE(t.created_by, ''),
  'feishu_record_id', COALESCE(t.feishu_record_id, ''),
  'created_at', COALESCE(t.created_at::text, ''),
  'started_at', COALESCE(t.started_at::text, ''),
  'finished_at', COALESCE(t.finished_at::text, ''),
  'parameters', COALESCE(t.parameters, '{}'::jsonb),
  'sku', p.sku,
  'product_name', p.name,
  'category', COALESCE(p.category, ''),
  'target_audience', COALESCE(p.target_audience, ''),
  'primary_color', COALESCE(p.primary_color, ''),
  'selling_points', COALESCE(to_jsonb(p.selling_points), '[]'::jsonb),
  'scenarios', COALESCE(to_jsonb(p.use_scenarios), '[]'::jsonb),
  'candidate_total', COALESCE((SELECT COUNT(*) FROM content_factory.candidates c WHERE c.task_id = t.id), 0),
  'candidate_approved', COALESCE((SELECT COUNT(*) FROM content_factory.candidates c WHERE c.task_id = t.id AND c.status = 'approved'), 0),
  'candidate_rejected', COALESCE((SELECT COUNT(*) FROM content_factory.candidates c WHERE c.task_id = t.id AND c.status = 'rejected'), 0),
  'candidate_pending_review', COALESCE((SELECT COUNT(*) FROM content_factory.candidates c WHERE c.task_id = t.id AND c.status IN ('new','pending_review','in_review')), 0),
  'run_total', COALESCE((SELECT COUNT(*) FROM content_factory.generation_runs gr WHERE gr.task_id = t.id), 0),
  'latest_run_status', COALESCE((SELECT gr.status::text FROM content_factory.generation_runs gr WHERE gr.task_id = t.id ORDER BY gr.sequence_no DESC LIMIT 1), ''),
  'latest_run_model', COALESCE((SELECT gr.model_name FROM content_factory.generation_runs gr WHERE gr.task_id = t.id ORDER BY gr.sequence_no DESC LIMIT 1), '')
)
FROM content_factory.tasks t
JOIN content_factory.products p ON p.id = t.product_id
WHERE t.id = :'task_id'::uuid
LIMIT 1;
""",
        {"task_id": task_id},
    )
    if detail_err:
        return None, f"读取任务详情失败: {detail_err[:200]}"
    if not raw:
        return None, "任务不存在"

    detail = load_json_text(raw, {})
    if not detail:
        return None, "任务详情解析失败"

    run_rows, run_err = pg_rows_vars(
        """
SELECT
  sequence_no::text,
  COALESCE(model_provider, ''),
  COALESCE(model_name, ''),
  COALESCE(purpose::text, ''),
  COALESCE(status::text, ''),
  COALESCE(duration_ms::text, ''),
  COALESCE(cost_cny::text, ''),
  COALESCE(external_job_id, ''),
  COALESCE(started_at::text, '-')
FROM content_factory.generation_runs
WHERE task_id = :'task_id'::uuid
ORDER BY sequence_no DESC
LIMIT 8;
""",
        {"task_id": task_id},
    )
    if run_err:
        return None, f"读取调用记录失败: {run_err[:200]}"

    runs = []
    for row in run_rows:
        parts = row.split("\t")
        if len(parts) >= 9:
            runs.append({
                "sequence_no": parts[0].strip(),
                "model_provider": parts[1].strip(),
                "model_name": parts[2].strip(),
                "purpose": parts[3].strip(),
                "status": parts[4].strip(),
                "duration_ms": parts[5].strip(),
                "cost_cny": parts[6].strip(),
                "external_job_id": parts[7].strip(),
                "started_at": parts[8].strip(),
            })

    candidate_rows, candidate_err = pg_rows_vars(
        """
SELECT
  sequence_no::text,
  COALESCE(oss_url, ''),
  COALESCE(status::text, ''),
  COALESCE(media_type::text, ''),
  COALESCE(parameters_snapshot->>'shot_type', ''),
  COALESCE(prompt_snapshot, '-')
FROM content_factory.candidates
WHERE task_id = :'task_id'::uuid
  AND status <> 'discarded'
ORDER BY sequence_no ASC
LIMIT 12;
""",
        {"task_id": task_id},
    )
    if candidate_err:
        return None, f"读取候选列表失败: {candidate_err[:200]}"

    candidates = []
    for row in candidate_rows:
        parts = row.split("\t")
        if len(parts) >= 6:
            candidates.append({
                "sequence_no": parts[0].strip(),
                "oss_url": parts[1].strip(),
                "status": parts[2].strip(),
                "media_type": parts[3].strip(),
                "shot_type": parts[4].strip(),
                "prompt_snapshot": parts[5].strip(),
            })

    detail["runs"] = runs
    detail["candidates"] = candidates
    detail["selling_points"] = detail.get("selling_points") or []
    detail["scenarios"] = detail.get("scenarios") or []
    detail["parameters"] = detail.get("parameters") or {}
    return detail, None


def render_home_recent_tasks(limit=3):
    limit = max(1, min(int(limit), 6))
    rows, err = pg_rows(
        "SELECT t.id::text, p.sku, p.name, t.status::text, t.created_at::text, "
        "t.requested_count::text, "
        "(SELECT COUNT(*)::text FROM content_factory.candidates WHERE task_id = t.id) "
        "FROM content_factory.tasks t "
        "JOIN content_factory.products p ON p.id = t.product_id "
        f"WHERE t.pipeline = 'image' ORDER BY t.created_at DESC LIMIT {limit};"
    )
    if err:
        return (
            '<div class="aside-card"><div class="aside-title">最近任务</div>'
            '<div class="tip">最近任务读取失败，可先前往历史任务页继续处理。</div>'
            '<a href="/history" class="recent-link" style="display:inline-block;margin-top:10px">→ 打开历史任务</a></div>'
        )

    items = []
    for row in rows:
        parts = [x.strip() for x in row.split("\t")]
        if len(parts) < 7:
            continue
        tid, sku, name, status, created_at, requested_count, candidate_count = parts[:7]
        requested = int(requested_count) if requested_count.isdigit() else 11
        generated = int(candidate_count) if candidate_count.isdigit() else 0
        created_label = (created_at or "").replace("T", " ")[:16] or "-"
        pill = render_task_status_pill(status, candidate_count=generated, requested_count=requested)
        items.append(f"""
<div class="recent-item">
  <div class="recent-row">
    <div>
      <div class="recent-name">{h(name)}</div>
      <div class="recent-sub">{h(sku)} · {h(created_label)} · {h(str(generated))}/{h(str(requested))} 张</div>
    </div>
    {pill}
  </div>
  <div class="recent-actions">
    <a class="recent-link" href="/task?task_id={h(tid)}">任务详情</a>
    <a class="recent-link-muted" href="/result?task_id={h(tid)}">候选审核</a>
  </div>
</div>""")

    content = '<div class="tip">还没有历史任务，先提交一个产品试跑完整链路。</div>'
    if items:
        content = '<div class="recent-list">' + "".join(items) + '</div>'

    return (
        '<div class="aside-card"><div class="aside-title">最近任务</div>'
        '<div class="tip" style="margin-bottom:12px">提交后不用回表单页找入口，可以直接从这里继续看进度、审核候选或进入详情。</div>'
        + content +
        '<a href="/history" class="recent-link" style="display:inline-block;margin-top:12px">→ 查看全部历史任务</a></div>'
    )


def get_pending_review_items(limit=80):
    limit = max(1, min(int(limit or 80), 200))
    raw, err = pg_vars(
        f"""
SELECT COALESCE(json_agg(item ORDER BY priority_rank DESC, candidate_created_at ASC), '[]'::json)::text
FROM (
  SELECT
    CASE v.priority::text
      WHEN 'urgent' THEN 4
      WHEN 'high' THEN 3
      WHEN 'normal' THEN 2
      ELSE 1
    END AS priority_rank,
    v.candidate_created_at,
    json_build_object(
      'candidate_id', v.candidate_id::text,
      'media_type', v.media_type::text,
      'url', COALESCE(v.thumbnail_url, v.oss_url, ''),
      'sequence_no', v.sequence_no,
      'candidate_created_at', v.candidate_created_at::text,
      'task_id', v.task_id::text,
      'task_title', v.task_title,
      'pipeline', v.pipeline::text,
      'priority', v.priority::text,
      'sku', v.sku,
      'product_name', v.product_name,
      'shot_type', COALESCE(c.parameters_snapshot->>'shot_type', '')
    ) AS item
  FROM content_factory.v_pending_review v
  JOIN content_factory.candidates c ON c.id = v.candidate_id
  ORDER BY priority_rank DESC, v.candidate_created_at ASC
  LIMIT {limit}
) q;
"""
    )
    if err:
        return [], err
    return load_json_text(raw, []), None


def render_review_queue_page():
    items, err = get_pending_review_items()
    if err:
        items = []
    cards_html = ""
    for item in items:
        tid = item.get("task_id", "")
        safe_url = safe_http_url(item.get("url", ""))
        seq = str(item.get("sequence_no") or "-")
        shot = item.get("shot_type") or item.get("media_type") or "candidate"
        created = (item.get("candidate_created_at") or "").replace("T", " ")[:16] or "-"
        priority_text = priority_label(item.get("priority", ""))
        pipeline_text = pipeline_label(item.get("pipeline", ""))
        thumb_html = f'<img src="{h(safe_url)}" alt="候选 #{h(seq)}" />' if safe_url else '<div class="queue-thumb-empty">暂无预览</div>'
        cards_html += f"""
<article class="queue-card">
  <a class="queue-thumb" href="/result?task_id={h(tid)}">{thumb_html}</a>
  <div class="queue-body">
    <div class="queue-top">
      <span class="queue-seq">#{h(seq)}</span>
      <span class="queue-priority">{h(priority_text)}</span>
    </div>
    <div class="queue-title">{h(item.get("product_name") or item.get("task_title") or "待审核素材")}</div>
    <div class="queue-meta">{h(item.get("sku", "-"))} · {h(pipeline_text)} · {h(shot)} · {h(created)}</div>
    <div class="queue-actions">
      <a class="btn btn-primary" href="/result?task_id={h(tid)}">进入审核</a>
      <a class="btn btn-secondary" href="/task?task_id={h(tid)}">任务详情</a>
    </div>
  </div>
</article>"""
    if not cards_html:
        message = "待审核队列读取失败，请检查数据库连接。" if err else "当前没有待审核素材。"
        cards_html = f'<div class="queue-empty">{h(message)}<br><a href="/" class="btn btn-primary" style="margin-top:14px">新建任务</a></div>'

    return """<!DOCTYPE html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>待审核队列 · ContentFactory</title>
<style>""" + COMMON_CSS + """
.shell{max-width:1280px;margin:0 auto;padding:28px 24px 56px}
.page-head{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:18px}
.page-title{font-size:26px;font-weight:800;letter-spacing:-.02em;color:var(--slate-900)}
.page-sub{font-size:13px;color:var(--slate-500);line-height:1.6;margin-top:4px}
.queue-count{padding:10px 12px;border:1px solid var(--slate-200);border-radius:999px;background:#fff;color:var(--slate-700);font-size:12px;font-weight:700}
.queue-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.queue-card{display:flex;flex-direction:column;background:#fff;border:1px solid var(--slate-200);border-radius:14px;overflow:hidden;box-shadow:var(--shadow-sm);transition:all .18s var(--ease)}
.queue-card:hover{transform:translateY(-2px);box-shadow:var(--shadow-lg);border-color:rgba(99,102,241,.38)}
.queue-thumb{aspect-ratio:4/3;background:linear-gradient(135deg,#f8fafc,#e2e8f0);display:flex;align-items:center;justify-content:center;overflow:hidden}
.queue-thumb img{width:100%;height:100%;object-fit:contain;padding:10px}
.queue-thumb-empty{font-size:12px;color:var(--slate-400)}
.queue-body{padding:14px 16px 16px;display:flex;flex-direction:column;gap:8px;min-width:0}
.queue-top{display:flex;justify-content:space-between;align-items:center;gap:10px}
.queue-seq{font-size:12px;font-weight:800;color:var(--indigo)}
.queue-priority{font-size:11px;font-weight:700;color:var(--slate-500);background:var(--slate-100);border-radius:999px;padding:5px 8px}
.queue-title{font-size:15px;font-weight:700;color:var(--slate-900);line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.queue-meta{font-size:12px;color:var(--slate-500);line-height:1.6}
.queue-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:4px}
.queue-actions .btn{font-size:12px;min-height:34px}
.queue-empty{grid-column:1/-1;text-align:center;background:#fff;border:1px dashed var(--slate-200);border-radius:14px;padding:42px;color:var(--slate-500)}
@media(max-width:640px){.shell{padding:20px 16px 40px}.queue-grid{grid-template-columns:1fr}.queue-actions .btn{flex:1;justify-content:center}}
</style></head><body>
<nav class="nav">
  <div class="nav-left">
    <a class="logo" href="/"><span class="logo-mark">CF</span>ContentFactory</a>
    <div class="crumbs"><span>·</span> <strong>待审核队列</strong></div>
  </div>
  <div class="nav-right">
    <a href="/history" class="btn btn-ghost" style="font-size:12px">历史任务</a>
    <a href="/review" class="btn btn-ghost" style="font-size:12px">待审核</a>
    <a href="/settings" class="btn btn-ghost" style="font-size:12px">模型配置</a>
    <a href="/" class="btn btn-primary">+ 新建任务</a>
    <div class="avatar">J</div>
  </div>
</nav>
<main class="shell">
  <header class="page-head">
    <div>
      <div class="page-title">待审核队列</div>
      <div class="page-sub">集中处理所有未通过/未驳回的候选素材，优先级高的任务会排在前面。</div>
    </div>
    <div class="queue-count">""" + h(str(len(items))) + """ 个待处理</div>
  </header>
  <section class="queue-grid">""" + cards_html + """</section>
</main>
</body></html>"""


def render_task_detail_page_legacy(detail):
    candidate_total = int(detail.get("candidate_total") or 0)
    requested_count = int(detail.get("requested_count") or 0)
    n8n_entry_url = N8N_VIDEO_ENTRY_URL if str(detail.get("pipeline", "")).lower() == "video" else N8N_IMAGE_ENTRY_URL
    status_pill = render_task_status_pill(detail.get("status", ""), candidate_count=candidate_total, requested_count=requested_count)
    status_bucket = format_task_status(detail.get("status", ""), candidate_count=candidate_total, requested_count=requested_count)
    status_label = {
        "done": "已完成",
        "failed": "失败",
        "running": "生成中",
        "other": detail.get("status", "") or "-",
    }.get(status_bucket, detail.get("status", "") or "-")

    selling_points_html = "".join(f"<li>{h(item)}</li>" for item in detail.get("selling_points", [])) or "<li>暂无卖点</li>"
    scenarios_html = "".join(f"<li>{h(item)}</li>" for item in detail.get("scenarios", [])) or "<li>暂无场景</li>"

    run_rows_html = ""
    for run in detail.get("runs", []):
        duration_label = "-"
        if run.get("duration_ms", "").isdigit():
            duration_value = int(run["duration_ms"])
            duration_label = f"{duration_value / 1000:.1f}s" if duration_value >= 1000 else f"{duration_value}ms"
        cost_label = run.get("cost_cny", "").strip() or "-"
        started_label = run.get("started_at", "").replace("T", " ")[:19] if run.get("started_at") else "-"
        run_rows_html += f"""
<tr>
  <td>#{h(run.get("sequence_no", "-"))}</td>
  <td>{h(run.get("model_provider", "-"))}</td>
  <td>{h(run.get("model_name", "-"))}</td>
  <td>{h(purpose_label(run.get("purpose", "")))}</td>
  <td>{h(run.get("status", "-"))}</td>
  <td>{h(duration_label)}</td>
  <td>{h(cost_label)}</td>
  <td>{h(started_label)}</td>
</tr>"""
    if not run_rows_html:
        run_rows_html = '<tr><td colspan="8" class="table-empty">暂无模型调用记录</td></tr>'

    candidate_cards_html = ""
    lightbox_items = []
    for cand in detail.get("candidates", []):
        safe_url = safe_http_url(cand.get("oss_url", ""))
        seq_label = str(cand.get("sequence_no", "-"))
        status_label = cand.get("status", "-")
        shot_label = cand.get("shot_type", "") or "未标注 shot_type"
        bucket_label = shot_bucket(cand.get("shot_type", ""))
        media_label = cand.get("media_type", "-")
        lightbox_index = len(lightbox_items)
        if safe_url:
            lightbox_items.append({
                "url": safe_url,
                "sequence_no": seq_label,
                "status": status_label,
                "bucket": bucket_label,
                "shot": shot_label,
            })
            thumb = f"""
<button type="button" class="cand-thumb cand-thumb-btn" onclick="openTaskLightbox({lightbox_index})" title="点击放大预览">
  <img src="{h(safe_url)}" alt="候选 {h(seq_label)}" />
  <span class="cand-zoom-chip">放大</span>
</button>"""
        else:
            thumb = '<div class="cand-thumb"><div class="detail-thumb-empty">暂无预览</div></div>'
        candidate_cards_html += f"""
<div class="cand-card">
  {thumb}
  <div class="cand-body">
    <div class="cand-row">
      <span class="cand-seq">#{h(seq_label)}</span>
      <span class="cand-status">{h(status_label)}</span>
    </div>
    <div class="cand-meta">{h(bucket_label)} · {h(media_label)}</div>
    <div class="cand-shot">{h(shot_label)}</div>
  </div>
</div>"""
    if not candidate_cards_html:
        candidate_cards_html = '<div class="table-empty" style="padding:24px;border:1px dashed var(--slate-200);border-radius:12px">暂无候选，先去候选页查看生成进度或重试任务。</div>'

    error_block = ""
    if detail.get("error_message"):
        error_block = f"""
<div class="detail-alert">
  <div class="detail-alert-title">任务异常</div>
  <div class="detail-alert-body">{h(detail.get("error_message", ""))}</div>
</div>"""

    task_lightbox_script = """
<div class="task-lightbox" id="taskLightbox">
  <div class="task-lightbox-close" onclick="closeTaskLightbox()">×</div>
  <div class="task-lightbox-nav task-lightbox-prev" onclick="navTaskLightbox(-1)">‹</div>
  <img id="taskLightboxImg" src="" alt="" />
  <div class="task-lightbox-nav task-lightbox-next" onclick="navTaskLightbox(1)">›</div>
  <div class="task-lightbox-info" id="taskLightboxInfo"></div>
  <div class="task-lightbox-hint">Esc 关闭 · ← → 切换</div>
</div>
<script>
const TASK_LIGHTBOX_ITEMS = """ + json.dumps(lightbox_items, ensure_ascii=False) + """;
function openTaskLightbox(idx){
  const item = TASK_LIGHTBOX_ITEMS[idx];
  if(!item)return;
  const root = document.getElementById('taskLightbox');
  document.getElementById('taskLightboxImg').src = item.url;
  document.getElementById('taskLightboxInfo').textContent = `#${item.sequence_no} · ${item.bucket} · ${item.shot} · ${item.status}`;
  root.dataset.idx = String(idx);
  root.classList.add('open');
}
function closeTaskLightbox(){
  const root = document.getElementById('taskLightbox');
  if(root)root.classList.remove('open');
}
function navTaskLightbox(dir){
  if(!TASK_LIGHTBOX_ITEMS.length)return;
  const root = document.getElementById('taskLightbox');
  const cur = parseInt(root.dataset.idx || '0', 10);
  const next = (cur + dir + TASK_LIGHTBOX_ITEMS.length) % TASK_LIGHTBOX_ITEMS.length;
  openTaskLightbox(next);
}
document.addEventListener('keydown', event=>{
  const root = document.getElementById('taskLightbox');
  if(!root || !root.classList.contains('open'))return;
  if(event.key === 'Escape')closeTaskLightbox();
  if(event.key === 'ArrowLeft')navTaskLightbox(-1);
  if(event.key === 'ArrowRight')navTaskLightbox(1);
});
document.addEventListener('click', event=>{
  if(event.target && event.target.id === 'taskLightbox'){
    closeTaskLightbox();
  }
});
</script>"""

    return """<!DOCTYPE html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>任务详情 · ContentFactory</title>
<style>""" + COMMON_CSS + """
.shell{max-width:1280px;margin:0 auto;padding:0 24px 48px}
.page-header{padding:32px 0 20px;display:flex;justify-content:space-between;align-items:flex-end;gap:20px;flex-wrap:wrap}
.page-title{font-size:28px;font-weight:700;letter-spacing:-.02em;margin-bottom:6px}
.page-sub{font-size:13px;color:var(--slate-500);font-family:"JetBrains Mono",Consolas,monospace}
.header-actions{display:flex;gap:8px;flex-wrap:wrap}
.summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:18px}
.summary-card,.detail-card{
  background:#fff;border:1px solid var(--slate-200);border-radius:14px;
  box-shadow:var(--shadow-sm);
}
.summary-card{padding:18px 20px}
.summary-kicker{font-size:11px;color:var(--slate-400);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px}
.summary-value{font-size:24px;font-weight:700;color:var(--slate-900);letter-spacing:-.02em}
.summary-sub{font-size:12px;color:var(--slate-500);margin-top:4px}
.detail-grid{display:grid;grid-template-columns:1.2fr .8fr;gap:18px;margin-bottom:18px}
.detail-card{padding:20px}
.detail-title{font-size:16px;font-weight:700;color:var(--slate-900);margin-bottom:14px}
.detail-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 18px}
.detail-item-label{font-size:11px;color:var(--slate-400);text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px}
.detail-item-value{font-size:14px;color:var(--slate-900);line-height:1.6;word-break:break-word}
.token-list{margin:0;padding-left:18px;color:var(--slate-700);font-size:13px;line-height:1.8}
.detail-stack{display:flex;flex-direction:column;gap:18px}
.detail-alert{background:#fef2f2;border-left:4px solid var(--red);padding:16px 18px;border-radius:12px;margin-bottom:18px}
.detail-alert-title{font-size:13px;font-weight:700;color:#991b1b;margin-bottom:4px}
.detail-alert-body{font-size:13px;color:#b91c1c;line-height:1.6}
.detail-pre{
  background:var(--slate-900);color:#e2e8f0;padding:16px;border-radius:12px;
  font-size:12px;line-height:1.6;overflow:auto;
}
.table-wrap{overflow:auto}
.detail-table{width:100%;border-collapse:collapse;font-size:13px}
.detail-table th,.detail-table td{padding:10px 12px;border-bottom:1px solid var(--slate-100);text-align:left;white-space:nowrap}
.detail-table th{font-size:11px;color:var(--slate-400);text-transform:uppercase;letter-spacing:.05em}
.table-empty{text-align:center;color:var(--slate-400);padding:18px}
.cand-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px}
.cand-card{background:#fff;border:1px solid var(--slate-200);border-radius:12px;overflow:hidden;transition:all .18s var(--ease)}
.cand-card:hover{transform:translateY(-2px);box-shadow:var(--shadow-lg);border-color:var(--indigo)}
.cand-thumb{position:relative;aspect-ratio:1;background:linear-gradient(135deg,#f8fafc,#e2e8f0);display:flex;align-items:center;justify-content:center}
.cand-thumb img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .2s var(--ease)}
.cand-thumb-btn{width:100%;padding:0;border:0;cursor:zoom-in}
.cand-thumb-btn:hover img{transform:scale(1.03)}
.cand-zoom-chip{
  position:absolute;top:10px;right:10px;
  padding:5px 9px;border-radius:999px;
  background:rgba(15,23,42,.72);color:#fff;
  font-size:11px;font-weight:600;backdrop-filter:blur(8px);
}
.detail-thumb-empty{font-size:12px;color:var(--slate-400)}
.cand-body{padding:12px}
.cand-row{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px}
.cand-seq{font-size:12px;font-weight:700;color:var(--indigo)}
.cand-status{font-size:11px;color:var(--slate-500)}
.cand-meta{font-size:12px;font-weight:600;color:var(--slate-900);margin-bottom:4px}
.cand-shot{font-size:11px;color:var(--slate-500);line-height:1.5}
.task-lightbox{
  position:fixed;inset:0;z-index:120;
  background:rgba(15,23,42,.92);
  display:none;align-items:center;justify-content:center;
}
.task-lightbox.open{display:flex}
.task-lightbox img{
  max-width:82vw;max-height:74vh;object-fit:contain;border-radius:10px;
  box-shadow:0 30px 60px rgba(0,0,0,.45);
}
.task-lightbox-close,.task-lightbox-nav{
  position:absolute;display:flex;align-items:center;justify-content:center;
  background:rgba(255,255,255,.12);color:#fff;backdrop-filter:blur(8px);
}
.task-lightbox-close{
  top:22px;right:22px;width:42px;height:42px;border-radius:50%;
  font-size:22px;cursor:pointer;
}
.task-lightbox-nav{
  top:50%;transform:translateY(-50%);
  width:50px;height:50px;border-radius:50%;
  font-size:24px;cursor:pointer;
}
.task-lightbox-prev{left:22px}
.task-lightbox-next{right:22px}
.task-lightbox-info{
  position:absolute;top:22px;left:50%;transform:translateX(-50%);
  padding:8px 14px;border-radius:999px;
  background:rgba(0,0,0,.42);color:#fff;font-size:13px;
  backdrop-filter:blur(8px);max-width:calc(100vw - 120px);text-align:center;
}
.task-lightbox-hint{
  position:absolute;bottom:22px;left:50%;transform:translateX(-50%);
  padding:8px 14px;border-radius:999px;
  background:rgba(0,0,0,.36);color:rgba(255,255,255,.8);font-size:12px;
}
@media(max-width:980px){
  .summary-grid{grid-template-columns:repeat(2,1fr)}
  .detail-grid{grid-template-columns:1fr}
}
@media(max-width:640px){
  .shell{padding:0 16px 32px}
  .summary-grid{grid-template-columns:1fr}
  .detail-list{grid-template-columns:1fr}
  .header-actions{width:100%}
  .header-actions .btn{flex:1;justify-content:center}
}
</style></head><body>
<nav class="nav">
  <div class="nav-left">
    <a class="logo" href="/"><span class="logo-mark">CF</span>ContentFactory</a>
    <div class="crumbs"><span>·</span> <a href="/history" style="color:var(--slate-500)">历史任务</a> <span>·</span> <strong>任务详情</strong></div>
  </div>
  <div class="nav-right">
    <a href="/history" class="btn btn-ghost" style="font-size:12px">🕐 历史任务</a>
    <a href="/" class="btn btn-ghost">+ 新建任务</a>
    <div class="avatar">J</div>
  </div>
</nav>
<div class="shell">
  <header class="page-header">
    <div>
      <div class="page-title">""" + h(detail.get("title", "任务详情")) + """</div>
      <div class="page-sub">task_id: """ + h(detail.get("task_id", "")) + """</div>
    </div>
    <div class="header-actions">
      """ + status_pill + """
      <a href="/result?task_id=""" + h(detail.get("task_id", "")) + """" class="btn btn-secondary">查看候选页</a>
      <a href="/history" class="btn btn-secondary">回到历史</a>
      <a href=\"""" + h(n8n_entry_url) + """\" class="btn btn-secondary">打开 N8N 画布</a>
    </div>
  </header>
  """ + error_block + """
  <section class="summary-grid">
    <div class="summary-card">
      <div class="summary-kicker">任务状态</div>
      <div class="summary-value">""" + h(status_label) + """</div>
      <div class="summary-sub">链路：""" + h(pipeline_label(detail.get("pipeline", ""))) + """</div>
    </div>
    <div class="summary-card">
      <div class="summary-kicker">候选进度</div>
      <div class="summary-value">""" + h(f"{candidate_total}/{requested_count or 0}") + """</div>
      <div class="summary-sub">通过 """ + h(str(detail.get("candidate_approved", 0))) + """ · 驳回 """ + h(str(detail.get("candidate_rejected", 0))) + """</div>
    </div>
    <div class="summary-card">
      <div class="summary-kicker">调用次数</div>
      <div class="summary-value">""" + h(str(detail.get("run_total", 0))) + """</div>
      <div class="summary-sub">最近模型：""" + h(detail.get("latest_run_model", "") or "-") + """</div>
    </div>
    <div class="summary-card">
      <div class="summary-kicker">重试信息</div>
      <div class="summary-value">""" + h(f"{detail.get('retry_count', 0)}/{detail.get('max_retries', 0)}") + """</div>
      <div class="summary-sub">最近 run：""" + h(detail.get("latest_run_status", "") or "-") + """</div>
    </div>
  </section>
  <section class="detail-grid">
    <div class="detail-stack">
      <div class="detail-card">
        <div class="detail-title">产品与任务信息</div>
        <div class="detail-list">
          <div><div class="detail-item-label">SKU</div><div class="detail-item-value">""" + h(detail.get("sku", "-")) + """</div></div>
          <div><div class="detail-item-label">产品名称</div><div class="detail-item-value">""" + h(detail.get("product_name", "-")) + """</div></div>
          <div><div class="detail-item-label">类目</div><div class="detail-item-value">""" + h(detail.get("category", "-")) + """</div></div>
          <div><div class="detail-item-label">主色</div><div class="detail-item-value">""" + h(detail.get("primary_color", "-")) + """</div></div>
          <div><div class="detail-item-label">目标受众</div><div class="detail-item-value">""" + h(detail.get("target_audience", "-")) + """</div></div>
          <div><div class="detail-item-label">优先级</div><div class="detail-item-value">""" + h(priority_label(detail.get("priority", ""))) + """</div></div>
          <div><div class="detail-item-label">创建人</div><div class="detail-item-value">""" + h(detail.get("created_by", "-")) + """</div></div>
          <div><div class="detail-item-label">飞书记录</div><div class="detail-item-value">""" + h(detail.get("feishu_record_id", "-") or "-") + """</div></div>
          <div><div class="detail-item-label">创建时间</div><div class="detail-item-value">""" + h((detail.get("created_at", "") or "-").replace("T", " ")[:19]) + """</div></div>
          <div><div class="detail-item-label">完成时间</div><div class="detail-item-value">""" + h((detail.get("finished_at", "") or "-").replace("T", " ")[:19]) + """</div></div>
        </div>
      </div>
      <div class="detail-card">
        <div class="detail-title">最近模型调用</div>
        <div class="table-wrap">
          <table class="detail-table">
            <thead>
              <tr><th>轮次</th><th>提供方</th><th>模型</th><th>用途</th><th>状态</th><th>耗时</th><th>成本</th><th>开始时间</th></tr>
            </thead>
            <tbody>""" + run_rows_html + """</tbody>
          </table>
        </div>
      </div>
    </div>
    <div class="detail-stack">
      <div class="detail-card">
        <div class="detail-title">卖点与场景</div>
        <div class="detail-item-label">核心卖点</div>
        <ul class="token-list">""" + selling_points_html + """</ul>
        <div class="detail-item-label" style="margin-top:12px">使用场景</div>
        <ul class="token-list">""" + scenarios_html + """</ul>
      </div>
      <div class="detail-card">
        <div class="detail-title">任务参数快照</div>
        <pre class="detail-pre">""" + h(json.dumps(detail.get("parameters", {}), ensure_ascii=False, indent=2)) + """</pre>
      </div>
    </div>
  </section>
  <section class="detail-card">
    <div class="detail-title">候选预览（前 12 条）</div>
    <div class="cand-grid">""" + candidate_cards_html + """</div>
  </section>
</div>
""" + task_lightbox_script + """
</body></html>"""


render_task_detail_page = render_task_detail_page_legacy


def render_task_detail_page(detail):
    candidate_total = int(detail.get("candidate_total") or 0)
    requested_count = int(detail.get("requested_count") or 0)
    n8n_entry_url = N8N_VIDEO_ENTRY_URL if str(detail.get("pipeline", "")).lower() == "video" else N8N_IMAGE_ENTRY_URL
    approved_count = int(detail.get("candidate_approved") or 0)
    rejected_count = int(detail.get("candidate_rejected") or 0)
    pending_review_count = int(detail.get("candidate_pending_review") or 0)
    run_total = int(detail.get("run_total") or 0)
    retry_count = int(detail.get("retry_count") or 0)
    max_retries = int(detail.get("max_retries") or 0)
    status_pill = render_task_status_pill(detail.get("status", ""), candidate_count=candidate_total, requested_count=requested_count)
    status_bucket = format_task_status(detail.get("status", ""), candidate_count=candidate_total, requested_count=requested_count)
    task_status_label = {
        "done": "已完成",
        "failed": "失败",
        "running": "生成中",
        "other": detail.get("status", "") or "-",
    }.get(status_bucket, detail.get("status", "") or "-")
    pipeline_text = pipeline_label(detail.get("pipeline", ""))
    priority_text = priority_label(detail.get("priority", ""))
    created_label = (detail.get("created_at", "") or "-").replace("T", " ")[:19]
    started_label = (detail.get("started_at", "") or "").replace("T", " ")[:19] or "未开始"
    finished_label = (detail.get("finished_at", "") or "").replace("T", " ")[:19] or "进行中"
    created_by_label = detail.get("created_by", "") or "系统"
    latest_model = detail.get("latest_run_model", "") or "-"
    latest_run_status = detail.get("latest_run_status", "") or "-"
    progress_percent = 0
    if requested_count > 0:
        progress_percent = max(0, min(100, int(round(candidate_total * 100 / requested_count))))

    guidance_tone = "success"
    guidance_title = "下一步建议"
    guidance_body = "候选素材已经准备好，建议继续进入候选页做审核、放大查看，或进入视频生成环节。"
    if detail.get("error_message"):
        guidance_tone = "danger"
        guidance_title = "优先处理异常"
        guidance_body = "当前任务已经记录异常信息，建议先查看错误提示和最近模型调用，再决定是否重试。"
    elif status_bucket == "failed":
        guidance_tone = "danger"
        guidance_title = "需要重试或排查链路"
        guidance_body = "任务当前处于失败状态，先核对参数快照和最近一次模型调用，再回到候选页或 N8N 画布继续排查。"
    elif status_bucket == "running":
        guidance_tone = "warn"
        guidance_title = "继续观察生成进度"
        guidance_body = f"当前已生成 {candidate_total} / {requested_count or 0} 张候选图。详情页更适合看总览，候选页更适合做实时审核。"
    elif pending_review_count > 0:
        guidance_tone = "success"
        guidance_title = "优先处理待审核候选"
        guidance_body = f"当前有 {pending_review_count} 张候选图待审核。先筛出通过图，再进入视频生成，可以减少后续返工。"
    elif candidate_total == 0:
        guidance_tone = "warn"
        guidance_title = "等待首张素材产出"
        guidance_body = "当前还没有候选图，建议先核对任务参数、卖点信息和模型调用状态，确认链路是否正常。"

    selling_points_html = "".join(f"<li>{h(item)}</li>" for item in detail.get("selling_points", [])) or "<li>暂无卖点</li>"
    scenarios_html = "".join(f"<li>{h(item)}</li>" for item in detail.get("scenarios", [])) or "<li>暂无场景</li>"

    run_rows_html = ""
    for run in detail.get("runs", []):
        duration_label = "-"
        if run.get("duration_ms", "").isdigit():
            duration_value = int(run["duration_ms"])
            duration_label = f"{duration_value / 1000:.1f}s" if duration_value >= 1000 else f"{duration_value}ms"
        cost_label = run.get("cost_cny", "").strip() or "-"
        started_at_label = run.get("started_at", "").replace("T", " ")[:19] if run.get("started_at") else "-"
        run_rows_html += f"""
<tr>
  <td>#{h(run.get("sequence_no", "-"))}</td>
  <td>{h(run.get("model_provider", "-"))}</td>
  <td>{h(run.get("model_name", "-"))}</td>
  <td>{h(purpose_label(run.get("purpose", "")))}</td>
  <td>{h(run.get("status", "-"))}</td>
  <td>{h(duration_label)}</td>
  <td>{h(cost_label)}</td>
  <td>{h(started_at_label)}</td>
</tr>"""
    if not run_rows_html:
        run_rows_html = '<tr><td colspan="8" class="table-empty">暂无模型调用记录</td></tr>'

    candidate_cards_html = ""
    lightbox_items = []
    hero_preview_index = None
    hero_preview_seq = "-"
    hero_preview_url = ""
    for cand in detail.get("candidates", []):
        safe_url = safe_http_url(cand.get("oss_url", ""))
        seq_label = str(cand.get("sequence_no", "-"))
        candidate_status_label = cand.get("status", "-")
        shot_label = cand.get("shot_type", "") or "未标注 shot_type"
        bucket_label = shot_bucket(cand.get("shot_type", ""))
        media_label = cand.get("media_type", "-")
        prompt_snapshot = re.sub(r"\s+", " ", cand.get("prompt_snapshot", "") or "").strip()
        prompt_snippet = prompt_snapshot[:180] + "..." if len(prompt_snapshot) > 180 else prompt_snapshot
        prompt_html = '<div class="cand-prompt cand-prompt-empty">暂无 prompt 快照</div>'
        if prompt_snapshot and prompt_snapshot != "-":
            prompt_html = f'<div class="cand-prompt" title="{h(prompt_snapshot)}">{h(prompt_snippet)}</div>'
        lightbox_index = len(lightbox_items)
        if safe_url:
            lightbox_items.append({
                "url": safe_url,
                "sequence_no": seq_label,
                "status": candidate_status_label,
                "bucket": bucket_label,
                "shot": shot_label,
            })
            if hero_preview_index is None:
                hero_preview_index = lightbox_index
                hero_preview_seq = seq_label
                hero_preview_url = safe_url
            thumb = f"""
<button type="button" class="cand-thumb cand-thumb-btn" onclick="openTaskLightbox({lightbox_index})" title="点击放大预览">
  <img src="{h(safe_url)}" alt="候选 {h(seq_label)}" />
  <span class="cand-zoom-chip">查看大图</span>
</button>"""
        else:
            thumb = '<div class="cand-thumb"><div class="detail-thumb-empty">暂无预览</div></div>'
        candidate_cards_html += f"""
<div class="cand-card">
  {thumb}
  <div class="cand-body">
    <div class="cand-row">
      <span class="cand-seq">#{h(seq_label)}</span>
      <span class="cand-status">{h(candidate_status_label)}</span>
    </div>
    <div class="cand-meta">{h(bucket_label)} / {h(media_label)}</div>
    <div class="cand-shot">{h(shot_label)}</div>
    {prompt_html}
  </div>
</div>"""
    if not candidate_cards_html:
        candidate_cards_html = '<div class="table-empty" style="padding:24px;border:1px dashed var(--slate-200);border-radius:14px">暂时还没有候选素材，先去候选页查看生成进度或重试任务。</div>'

    hero_preview_html = """
<div class="hero-preview-empty">
  <div class="hero-preview-empty-title">当前还没有候选图</div>
  <div class="hero-preview-empty-sub">生成完成后，这里会优先展示首张素材，方便你快速判断是否值得继续往下走。</div>
</div>"""
    if hero_preview_url:
        hero_preview_html = f"""
<button type="button" class="hero-preview-button" onclick="openTaskLightbox({hero_preview_index})" title="点击查看候选 #{h(hero_preview_seq)} 大图">
  <div class="hero-preview-frame">
    <img src="{h(hero_preview_url)}" alt="候选 #{h(hero_preview_seq)}" />
    <span class="hero-preview-badge">候选 #{h(hero_preview_seq)}</span>
  </div>
</button>"""

    error_block = ""
    if detail.get("error_message"):
        error_block = f"""
<div class="detail-alert">
  <div class="detail-alert-title">任务异常</div>
  <div class="detail-alert-body">{h(detail.get("error_message", ""))}</div>
</div>"""

    task_lightbox_script = """
<div class="task-lightbox" id="taskLightbox">
  <div class="task-lightbox-close" onclick="closeTaskLightbox()">&times;</div>
  <div class="task-lightbox-nav task-lightbox-prev" onclick="navTaskLightbox(-1)">&lsaquo;</div>
  <img id="taskLightboxImg" src="" alt="" />
  <div class="task-lightbox-nav task-lightbox-next" onclick="navTaskLightbox(1)">&rsaquo;</div>
  <div class="task-lightbox-info" id="taskLightboxInfo"></div>
  <div class="task-lightbox-hint">Esc 关闭 / 左右方向键切换</div>
</div>
<script>
const TASK_LIGHTBOX_ITEMS = """ + json.dumps(lightbox_items, ensure_ascii=False) + """;
function openTaskLightbox(idx){
  const item = TASK_LIGHTBOX_ITEMS[idx];
  if(!item)return;
  const root = document.getElementById('taskLightbox');
  document.getElementById('taskLightboxImg').src = item.url;
  document.getElementById('taskLightboxInfo').textContent = `#${item.sequence_no} / ${item.bucket} / ${item.shot} / ${item.status}`;
  root.dataset.idx = String(idx);
  root.classList.add('open');
}
function closeTaskLightbox(){
  const root = document.getElementById('taskLightbox');
  if(root)root.classList.remove('open');
}
function navTaskLightbox(dir){
  if(!TASK_LIGHTBOX_ITEMS.length)return;
  const root = document.getElementById('taskLightbox');
  const cur = parseInt(root.dataset.idx || '0', 10);
  const next = (cur + dir + TASK_LIGHTBOX_ITEMS.length) % TASK_LIGHTBOX_ITEMS.length;
  openTaskLightbox(next);
}
document.addEventListener('keydown', event=>{
  const root = document.getElementById('taskLightbox');
  if(!root || !root.classList.contains('open'))return;
  if(event.key === 'Escape')closeTaskLightbox();
  if(event.key === 'ArrowLeft')navTaskLightbox(-1);
  if(event.key === 'ArrowRight')navTaskLightbox(1);
});
document.addEventListener('click', event=>{
  if(event.target && event.target.id === 'taskLightbox'){
    closeTaskLightbox();
  }
});
</script>"""

    return """<!DOCTYPE html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>任务详情 / ContentFactory</title>
<style>""" + COMMON_CSS + """
.shell{max-width:1500px;margin:0 auto;padding:20px 24px 56px}
.task-shell{display:flex;flex-direction:column;gap:18px}
.hero-card,.summary-card,.detail-card,.candidate-section{
  background:#fff;border:1px solid var(--slate-200);border-radius:18px;
  box-shadow:var(--shadow-sm);
}
.hero-card{
  position:relative;overflow:hidden;padding:28px;
  background:linear-gradient(135deg,rgba(99,102,241,.08),rgba(236,72,153,.05) 34%,#fff 72%);
}
.hero-card::before{
  content:"";position:absolute;left:-72px;top:-118px;width:280px;height:280px;border-radius:50%;
  background:radial-gradient(circle,rgba(99,102,241,.18),rgba(99,102,241,0) 70%);
  pointer-events:none;
}
.hero-layout{position:relative;display:grid;grid-template-columns:minmax(0,1.14fr) minmax(320px,.86fr);gap:24px;align-items:stretch}
.hero-main,.hero-side{min-width:0}
.hero-main{display:flex;flex-direction:column;gap:18px}
.hero-kicker{
  font-size:11px;font-weight:700;color:var(--indigo);
  text-transform:uppercase;letter-spacing:.12em;
}
.page-title{font-size:34px;font-weight:800;letter-spacing:-.03em;line-height:1.12;color:var(--slate-900)}
.page-sub{
  font-size:13px;color:var(--slate-500);
  font-family:"JetBrains Mono",Consolas,monospace;
  word-break:break-all;
}
.hero-meta{display:flex;flex-wrap:wrap;gap:10px}
.meta-pill{
  display:inline-flex;align-items:center;gap:8px;padding:10px 12px;
  border-radius:999px;border:1px solid rgba(226,232,240,.94);
  background:rgba(255,255,255,.88);color:var(--slate-700);font-size:12px;
}
.meta-pill strong{
  font-size:10px;font-weight:700;color:var(--slate-400);
  text-transform:uppercase;letter-spacing:.08em;
}
.hero-guidance{
  padding:16px 18px;border-radius:16px;border:1px solid transparent;
  background:rgba(248,250,252,.9);
}
.hero-guidance-title{font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;margin-bottom:6px}
.hero-guidance-body{font-size:14px;line-height:1.75;color:var(--slate-700)}
.hero-guidance.success{border-color:rgba(16,185,129,.18);background:rgba(16,185,129,.08)}
.hero-guidance.success .hero-guidance-title{color:var(--green-dark)}
.hero-guidance.warn{border-color:rgba(245,158,11,.2);background:rgba(245,158,11,.1)}
.hero-guidance.warn .hero-guidance-title{color:#b45309}
.hero-guidance.danger{border-color:rgba(239,68,68,.18);background:rgba(254,242,242,.96)}
.hero-guidance.danger .hero-guidance-title{color:#b91c1c}
.hero-actions{display:flex;gap:10px;flex-wrap:wrap}
.hero-actions .btn{min-height:40px}
.hero-preview-card{
  height:100%;display:flex;flex-direction:column;gap:14px;padding:16px;
  border-radius:18px;border:1px solid rgba(226,232,240,.9);
  background:rgba(255,255,255,.92);box-shadow:var(--shadow-md);
}
.panel-kicker{
  font-size:11px;font-weight:700;color:var(--slate-400);
  text-transform:uppercase;letter-spacing:.08em;
}
.panel-title{font-size:18px;font-weight:700;color:var(--slate-900)}
.panel-sub{font-size:13px;color:var(--slate-500);line-height:1.6}
.hero-preview-button{width:100%;padding:0;border:0;background:none;cursor:zoom-in}
.hero-preview-frame{
  position:relative;aspect-ratio:4/5;border-radius:16px;overflow:hidden;
  display:flex;align-items:center;justify-content:center;
  background:linear-gradient(135deg,#f8fafc,#e2e8f0);
}
.hero-preview-frame img{
  width:100%;height:100%;display:block;object-fit:contain;padding:14px;
}
.hero-preview-badge{
  position:absolute;top:12px;right:12px;padding:6px 10px;border-radius:999px;
  background:rgba(15,23,42,.78);color:#fff;font-size:11px;font-weight:700;
}
.hero-preview-empty{
  min-height:280px;padding:22px;border-radius:16px;border:1px dashed var(--slate-200);
  background:linear-gradient(135deg,#fff,#f8fafc);display:flex;flex-direction:column;
  align-items:center;justify-content:center;text-align:center;
}
.hero-preview-empty-title{font-size:16px;font-weight:700;color:var(--slate-800);margin-bottom:8px}
.hero-preview-empty-sub{font-size:13px;color:var(--slate-500);line-height:1.7;max-width:320px}
.hero-mini-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.hero-mini-card{
  padding:12px;border-radius:14px;border:1px solid var(--slate-100);
  background:linear-gradient(180deg,#fff,rgba(248,250,252,.96));
}
.hero-mini-label{
  font-size:11px;color:var(--slate-400);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px;
}
.hero-mini-value{font-size:20px;font-weight:800;letter-spacing:-.02em;color:var(--slate-900)}
.hero-mini-sub{font-size:12px;color:var(--slate-500);margin-top:4px}
.summary-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}
.summary-card{padding:18px 20px}
.summary-top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:10px}
.summary-kicker{font-size:11px;color:var(--slate-400);text-transform:uppercase;letter-spacing:.08em}
.summary-value{font-size:28px;font-weight:800;color:var(--slate-900);letter-spacing:-.03em;line-height:1.1;margin-top:8px}
.summary-sub{font-size:13px;color:var(--slate-500);line-height:1.6}
.summary-badge{
  padding:6px 10px;border-radius:999px;background:var(--slate-50);
  color:var(--slate-600);font-size:11px;font-weight:700;
}
.summary-bar{height:8px;border-radius:999px;background:var(--slate-100);overflow:hidden;margin-top:14px}
.summary-bar span{
  display:block;height:100%;border-radius:999px;background:linear-gradient(135deg,var(--indigo),var(--pink));
}
.workbench-grid{display:grid;grid-template-columns:minmax(0,1.24fr) minmax(320px,.76fr);gap:18px;align-items:start}
.detail-stack{display:flex;flex-direction:column;gap:18px;min-width:0}
.detail-card{padding:22px}
.section-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;flex-wrap:wrap;margin-bottom:18px}
.section-title-wrap{display:flex;flex-direction:column;gap:4px}
.section-kicker{
  font-size:11px;font-weight:700;color:var(--slate-400);
  text-transform:uppercase;letter-spacing:.08em;
}
.detail-title{font-size:18px;font-weight:700;color:var(--slate-900);margin:0}
.section-sub{font-size:13px;color:var(--slate-500);line-height:1.6;max-width:560px}
.detail-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.detail-item{
  padding:14px 16px;border:1px solid var(--slate-100);border-radius:15px;
  background:linear-gradient(180deg,#fff,rgba(248,250,252,.96));
}
.detail-item-label{
  font-size:11px;color:var(--slate-400);text-transform:uppercase;letter-spacing:.07em;margin-bottom:6px;
}
.detail-item-value{font-size:14px;font-weight:600;color:var(--slate-900);line-height:1.7;word-break:break-word}
.detail-alert{
  background:#fef2f2;border:1px solid rgba(239,68,68,.18);border-left:4px solid var(--red);
  padding:16px 18px;border-radius:16px;
}
.detail-alert-title{font-size:13px;font-weight:700;color:#991b1b;margin-bottom:4px}
.detail-alert-body{font-size:13px;color:#b91c1c;line-height:1.7}
.insight-card{
  padding:18px;border:1px solid var(--slate-100);border-radius:16px;
  background:linear-gradient(180deg,#fff,#f8fafc);
}
.insight-card + .insight-card{margin-top:12px}
.insight-title{
  font-size:12px;font-weight:700;color:var(--slate-400);
  text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px;
}
.insight-copy{font-size:14px;color:var(--slate-700);line-height:1.75}
.token-group{
  padding:16px;border:1px solid var(--slate-100);border-radius:16px;
  background:linear-gradient(180deg,#fff,#f8fafc);
}
.token-group + .token-group{margin-top:12px}
.token-group-title{
  font-size:12px;font-weight:700;color:var(--slate-500);
  text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px;
}
.token-list{margin:0;padding-left:18px;color:var(--slate-700);font-size:13px;line-height:1.85}
.token-list li + li{margin-top:4px}
.detail-pre-shell{
  border:1px solid rgba(30,41,59,.08);border-radius:16px;overflow:hidden;background:var(--slate-900);
}
.detail-pre-head{
  display:flex;justify-content:space-between;align-items:center;gap:10px;
  padding:12px 16px;border-bottom:1px solid rgba(255,255,255,.08);color:#cbd5e1;
  font-size:12px;background:rgba(15,23,42,.72);
}
.detail-pre{
  margin:0;padding:16px;background:transparent;color:#e2e8f0;
  font-size:12px;line-height:1.7;overflow:auto;max-height:360px;
}
.table-wrap{overflow:auto;border:1px solid var(--slate-100);border-radius:16px}
.detail-table{width:100%;min-width:760px;border-collapse:collapse;font-size:13px;background:#fff}
.detail-table th,.detail-table td{
  padding:12px 14px;border-bottom:1px solid var(--slate-100);text-align:left;white-space:nowrap;
}
.detail-table thead{background:var(--slate-50)}
.detail-table th{
  font-size:11px;font-weight:700;color:var(--slate-400);text-transform:uppercase;letter-spacing:.08em;
}
.table-empty{text-align:center;color:var(--slate-400);padding:18px}
.candidate-section{padding:22px}
.cand-toolbar{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;flex-wrap:wrap;margin-bottom:18px}
.cand-toolbar-meta{display:flex;gap:10px;flex-wrap:wrap}
.cand-stat-pill{
  display:inline-flex;align-items:center;gap:8px;padding:10px 12px;
  border-radius:999px;border:1px solid var(--slate-200);background:var(--slate-50);
  color:var(--slate-700);font-size:12px;font-weight:600;
}
.cand-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px}
.cand-card{
  background:#fff;border:1px solid var(--slate-200);border-radius:16px;
  overflow:hidden;transition:all .18s var(--ease);box-shadow:var(--shadow-sm);
}
.cand-card:hover{transform:translateY(-2px);box-shadow:var(--shadow-lg);border-color:rgba(99,102,241,.36)}
.cand-thumb{
  position:relative;aspect-ratio:4/5;padding:14px;background:linear-gradient(135deg,#f8fafc,#e2e8f0);
  display:flex;align-items:center;justify-content:center;
}
.cand-thumb img{
  width:100%;height:100%;object-fit:contain;display:block;transition:transform .2s var(--ease);
}
.cand-thumb-btn{width:100%;padding:0;border:0;cursor:zoom-in}
.cand-thumb-btn:hover img{transform:scale(1.02)}
.cand-zoom-chip{
  position:absolute;top:12px;right:12px;padding:6px 10px;border-radius:999px;
  background:rgba(15,23,42,.76);color:#fff;font-size:11px;font-weight:700;
}
.detail-thumb-empty{font-size:12px;color:var(--slate-400);text-align:center;line-height:1.7}
.cand-body{padding:14px 14px 16px;display:flex;flex-direction:column;gap:8px}
.cand-row{display:flex;justify-content:space-between;align-items:center;gap:8px}
.cand-seq{font-size:12px;font-weight:800;color:var(--indigo)}
.cand-status{
  padding:4px 8px;border-radius:999px;background:var(--slate-100);
  font-size:11px;font-weight:700;color:var(--slate-600);
}
.cand-meta{font-size:13px;font-weight:700;color:var(--slate-900)}
.cand-shot{font-size:12px;color:var(--slate-500);line-height:1.65;min-height:38px}
.cand-prompt{
  font-size:12px;color:var(--slate-600);line-height:1.65;max-height:3.3em;overflow:hidden;word-break:break-word;
}
.cand-prompt-empty{color:var(--slate-400)}
.task-lightbox{
  position:fixed;inset:0;z-index:120;background:rgba(15,23,42,.92);
  display:none;align-items:center;justify-content:center;
}
.task-lightbox.open{display:flex}
.task-lightbox img{
  max-width:82vw;max-height:74vh;object-fit:contain;border-radius:10px;
  box-shadow:0 30px 60px rgba(0,0,0,.45);
}
.task-lightbox-close,.task-lightbox-nav{
  position:absolute;display:flex;align-items:center;justify-content:center;
  background:rgba(255,255,255,.12);color:#fff;backdrop-filter:blur(8px);
}
.task-lightbox-close{
  top:22px;right:22px;width:42px;height:42px;border-radius:50%;
  font-size:22px;cursor:pointer;
}
.task-lightbox-nav{
  top:50%;transform:translateY(-50%);
  width:50px;height:50px;border-radius:50%;font-size:24px;cursor:pointer;
}
.task-lightbox-prev{left:22px}
.task-lightbox-next{right:22px}
.task-lightbox-info{
  position:absolute;top:22px;left:50%;transform:translateX(-50%);
  padding:8px 14px;border-radius:999px;background:rgba(0,0,0,.42);color:#fff;
  font-size:13px;backdrop-filter:blur(8px);max-width:calc(100vw - 120px);text-align:center;
}
.task-lightbox-hint{
  position:absolute;bottom:22px;left:50%;transform:translateX(-50%);
  padding:8px 14px;border-radius:999px;background:rgba(0,0,0,.36);color:rgba(255,255,255,.8);font-size:12px;
}
@media(max-width:1180px){
  .hero-layout,.workbench-grid{grid-template-columns:1fr}
}
@media(max-width:760px){
  .shell{padding:0 16px 32px}
  .hero-card,.summary-card,.detail-card,.candidate-section{border-radius:16px}
  .hero-card{padding:20px}
  .page-title{font-size:28px}
  .hero-mini-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .detail-list{grid-template-columns:1fr}
  .cand-grid{grid-template-columns:repeat(auto-fit,minmax(180px,1fr))}
  .task-lightbox img{max-width:92vw;max-height:70vh}
}
@media(max-width:560px){
  .shell{padding:0 14px 28px}
  .hero-actions .btn,.cand-toolbar .btn{width:100%;justify-content:center}
  .hero-mini-grid{grid-template-columns:1fr}
  .cand-grid{grid-template-columns:1fr}
  .task-lightbox-info{top:auto;bottom:82px;max-width:calc(100vw - 28px)}
  .task-lightbox-prev{left:12px}
  .task-lightbox-next{right:12px}
}
</style></head><body>
<nav class="nav">
  <div class="nav-left">
    <a class="logo" href="/"><span class="logo-mark">CF</span>ContentFactory</a>
    <div class="crumbs"><span>路</span> <a href="/history" style="color:var(--slate-500)">历史任务</a> <span>路</span> <strong>任务详情</strong></div>
  </div>
  <div class="nav-right">
    <a href="/history" class="btn btn-ghost" style="font-size:12px">历史任务</a>
    <a href="/review" class="btn btn-ghost" style="font-size:12px">待审核</a>
    <a href="/settings" class="btn btn-ghost" style="font-size:12px">模型配置</a>
    <a href="/" class="btn btn-ghost">+ 新建任务</a>
    <div class="avatar">J</div>
  </div>
</nav>
<div class="shell">
  <div class="task-shell">
    <section class="hero-card">
      <div class="hero-layout">
        <div class="hero-main">
          <div>
            <div class="hero-kicker">Task Workbench</div>
            <div class="page-title">""" + h(detail.get("title", "任务详情")) + """</div>
            <div class="page-sub">task_id: """ + h(detail.get("task_id", "")) + """</div>
          </div>
          <div class="hero-meta">
            <div class="meta-pill"><strong>SKU</strong><span>""" + h(detail.get("sku", "-")) + """</span></div>
            <div class="meta-pill"><strong>流程</strong><span>""" + h(pipeline_text) + """</span></div>
            <div class="meta-pill"><strong>优先级</strong><span>""" + h(priority_text) + """</span></div>
            <div class="meta-pill"><strong>创建时间</strong><span>""" + h(created_label) + """</span></div>
            <div class="meta-pill"><strong>启动时间</strong><span>""" + h(started_label) + """</span></div>
          </div>
          <div class="hero-guidance """ + h(guidance_tone) + """">
            <div class="hero-guidance-title">""" + h(guidance_title) + """</div>
            <div class="hero-guidance-body">""" + h(guidance_body) + """</div>
          </div>
          <div class="hero-actions">
            """ + status_pill + """
            <a href="/result?task_id=""" + h(detail.get("task_id", "")) + """" class="btn btn-primary">查看候选页</a>
            <a href="/history" class="btn btn-secondary">返回历史任务</a>
            <a href=\"""" + h(n8n_entry_url) + """\" class="btn btn-secondary">打开 N8N 画布</a>
          </div>
        </div>
        <div class="hero-side">
          <div class="hero-preview-card">
            <div>
              <div class="panel-kicker">Output Snapshot</div>
              <div class="panel-title">当前素材视窗</div>
              <div class="panel-sub">首屏直接展示任务当前最有代表性的候选图，方便快速判断继续审核还是回查链路。</div>
            </div>
            """ + hero_preview_html + """
            <div class="hero-mini-grid">
              <div class="hero-mini-card">
                <div class="hero-mini-label">已生成</div>
                <div class="hero-mini-value">""" + h(str(candidate_total)) + """</div>
                <div class="hero-mini-sub">目标 """ + h(str(requested_count or 0)) + """ 张</div>
              </div>
              <div class="hero-mini-card">
                <div class="hero-mini-label">待审核</div>
                <div class="hero-mini-value">""" + h(str(pending_review_count)) + """</div>
                <div class="hero-mini-sub">通过 """ + h(str(approved_count)) + """ / 驳回 """ + h(str(rejected_count)) + """</div>
              </div>
              <div class="hero-mini-card">
                <div class="hero-mini-label">模型调用</div>
                <div class="hero-mini-value">""" + h(str(run_total)) + """</div>
                <div class="hero-mini-sub">""" + h(latest_model) + """</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
    """ + error_block + """
    <section class="summary-grid">
      <div class="summary-card">
        <div class="summary-top">
          <div>
            <div class="summary-kicker">任务状态</div>
            <div class="summary-value">""" + h(task_status_label) + """</div>
          </div>
          <div class="summary-badge">""" + h(pipeline_text) + """</div>
        </div>
        <div class="summary-sub">当前详情页先回答三个问题：任务是否正常、候选是否够用、下一步应不应该继续往下走。</div>
      </div>
      <div class="summary-card">
        <div class="summary-top">
          <div>
            <div class="summary-kicker">候选进度</div>
            <div class="summary-value">""" + h(f"{candidate_total}/{requested_count or 0}") + """</div>
          </div>
          <div class="summary-badge">完成 """ + h(str(progress_percent)) + """%</div>
        </div>
        <div class="summary-sub">通过 """ + h(str(approved_count)) + """ / 驳回 """ + h(str(rejected_count)) + """ / 待审核 """ + h(str(pending_review_count)) + """</div>
        <div class="summary-bar"><span style="width:""" + h(str(progress_percent)) + """%"></span></div>
      </div>
      <div class="summary-card">
        <div class="summary-top">
          <div>
            <div class="summary-kicker">模型调用</div>
            <div class="summary-value">""" + h(str(run_total)) + """</div>
          </div>
          <div class="summary-badge">最近状态</div>
        </div>
        <div class="summary-sub">最近模型：""" + h(latest_model) + """ / 最近 run：""" + h(latest_run_status) + """</div>
      </div>
      <div class="summary-card">
        <div class="summary-top">
          <div>
            <div class="summary-kicker">重试信息</div>
            <div class="summary-value">""" + h(f"{retry_count}/{max_retries}") + """</div>
          </div>
          <div class="summary-badge">完成时间</div>
        </div>
        <div class="summary-sub">任务完成时间：""" + h(finished_label) + """</div>
      </div>
    </section>
    <section class="workbench-grid">
      <div class="detail-stack">
        <div class="detail-card">
          <div class="section-head">
            <div class="section-title-wrap">
              <div class="section-kicker">Business Context</div>
              <div class="detail-title">商品与任务信息</div>
              <div class="section-sub">把商品属性、任务配置和上下游标识集中在一个区块，方便业务侧回看任务输入是否准确。</div>
            </div>
          </div>
          <div class="detail-list">
            <div class="detail-item"><div class="detail-item-label">SKU</div><div class="detail-item-value">""" + h(detail.get("sku", "-")) + """</div></div>
            <div class="detail-item"><div class="detail-item-label">商品名称</div><div class="detail-item-value">""" + h(detail.get("product_name", "-")) + """</div></div>
            <div class="detail-item"><div class="detail-item-label">类目</div><div class="detail-item-value">""" + h(detail.get("category", "-")) + """</div></div>
            <div class="detail-item"><div class="detail-item-label">主色</div><div class="detail-item-value">""" + h(detail.get("primary_color", "-")) + """</div></div>
            <div class="detail-item"><div class="detail-item-label">目标人群</div><div class="detail-item-value">""" + h(detail.get("target_audience", "-")) + """</div></div>
            <div class="detail-item"><div class="detail-item-label">优先级</div><div class="detail-item-value">""" + h(priority_text) + """</div></div>
            <div class="detail-item"><div class="detail-item-label">创建人</div><div class="detail-item-value">""" + h(created_by_label) + """</div></div>
            <div class="detail-item"><div class="detail-item-label">飞书记录</div><div class="detail-item-value">""" + h(detail.get("feishu_record_id", "-") or "-") + """</div></div>
            <div class="detail-item"><div class="detail-item-label">创建时间</div><div class="detail-item-value">""" + h(created_label) + """</div></div>
            <div class="detail-item"><div class="detail-item-label">完成时间</div><div class="detail-item-value">""" + h(finished_label) + """</div></div>
          </div>
        </div>
        <div class="detail-card">
          <div class="section-head">
            <div class="section-title-wrap">
              <div class="section-kicker">Execution Log</div>
              <div class="detail-title">最近模型调用</div>
              <div class="section-sub">按最近 8 次调用回看本次任务的生成链路，方便快速定位模型、用途、耗时和状态变化。</div>
            </div>
          </div>
          <div class="table-wrap">
            <table class="detail-table">
              <thead>
                <tr><th>轮次</th><th>提供方</th><th>模型</th><th>用途</th><th>状态</th><th>耗时</th><th>成本</th><th>开始时间</th></tr>
              </thead>
              <tbody>""" + run_rows_html + """</tbody>
            </table>
          </div>
        </div>
      </div>
      <div class="detail-stack">
        <div class="detail-card">
          <div class="section-head">
            <div class="section-title-wrap">
              <div class="section-kicker">Decision Support</div>
              <div class="detail-title">业务判断</div>
              <div class="section-sub">站在业务运营视角，把当前任务最值得关注的结论和提醒固定在右侧区域。</div>
            </div>
          </div>
          <div class="insight-card">
            <div class="insight-title">当前建议</div>
            <div class="insight-copy">""" + h(guidance_body) + """</div>
          </div>
          <div class="insight-card">
            <div class="insight-title">交付信号</div>
            <div class="insight-copy">任务状态：""" + h(task_status_label) + """ / 候选审核：""" + h(str(pending_review_count)) + """ 张待处理 / 最近模型状态：""" + h(latest_run_status) + """</div>
          </div>
        </div>
        <div class="detail-card">
          <div class="section-head">
            <div class="section-title-wrap">
              <div class="section-kicker">Prompt Inputs</div>
              <div class="detail-title">卖点与场景</div>
              <div class="section-sub">这里保留任务生成前最关键的商品表达，方便核对后续图像是否跑偏。</div>
            </div>
          </div>
          <div class="token-group">
            <div class="token-group-title">核心卖点</div>
            <ul class="token-list">""" + selling_points_html + """</ul>
          </div>
          <div class="token-group">
            <div class="token-group-title">使用场景</div>
            <ul class="token-list">""" + scenarios_html + """</ul>
          </div>
        </div>
        <div class="detail-card">
          <div class="section-head">
            <div class="section-title-wrap">
              <div class="section-kicker">Snapshot</div>
              <div class="detail-title">任务参数快照</div>
              <div class="section-sub">保留完整参数原文，便于开发和运营在排查时直接对照接口输入。</div>
            </div>
          </div>
          <div class="detail-pre-shell">
            <div class="detail-pre-head">
              <span>parameters.json</span>
              <span>只读快照</span>
            </div>
            <pre class="detail-pre">""" + h(json.dumps(detail.get("parameters", {}), ensure_ascii=False, indent=2)) + """</pre>
          </div>
        </div>
      </div>
    </section>
    <section class="candidate-section">
      <div class="cand-toolbar">
        <div class="section-title-wrap">
          <div class="section-kicker">Creative Outputs</div>
          <div class="detail-title">候选素材预览</div>
          <div class="section-sub">最多展示 12 张候选素材。点击缩略图可直接放大查看，不需要再跳到别的页面确认细节。</div>
        </div>
        <div class="cand-toolbar-meta">
          <div class="cand-stat-pill">已生成 """ + h(str(candidate_total)) + """ 张</div>
          <div class="cand-stat-pill">待审核 """ + h(str(pending_review_count)) + """ 张</div>
          <div class="cand-stat-pill">通过 """ + h(str(approved_count)) + """ 张</div>
        </div>
      </div>
      <div class="cand-grid">""" + candidate_cards_html + """</div>
    </section>
  </div>
</div>
""" + task_lightbox_script + """
</body></html>"""


# ============================================================================
#  HTTP handler
# ============================================================================
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ct="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.end_headers()
        self.wfile.write(body.encode("utf-8") if isinstance(body, str) else body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            html = FORM_HTML.replace("{n8n_editor_url}", N8N_IMAGE_ENTRY_URL) \
                            .replace("{video_status_text}", VIDEO_STATUS_TEXT) \
                            .replace("{video_status_class}", VIDEO_STATUS_CLASS) \
                            .replace("{recent_tasks_block}", render_home_recent_tasks())
            self._send(200, html)
        elif path == "/review":
            self._send(200, render_review_queue_page())
        elif path == "/task":
            qs = urllib.parse.urlparse(self.path).query
            tid = (urllib.parse.parse_qs(qs).get("task_id") or [""])[0]
            if not tid:
                self._send(400, "missing task_id"); return
            try:
                detail, err = get_task_detail(tid)
            except ValueError as e:
                self._send(400, str(e)); return
            if err:
                self._send(404 if "不存在" in err else 500, err); return
            self._send(200, render_task_detail_page(detail))
        elif path == "/result":
            qs = urllib.parse.urlparse(self.path).query
            tid = (urllib.parse.parse_qs(qs).get("task_id") or [""])[0]
            if not tid: self._send(400, "missing task_id"); return
            try:
                tid = validate_uuid(tid, "task_id")
            except ValueError as e:
                self._send(400, str(e)); return
            # 只有"演示样品"task（55555555-...）有真实预生成视频；其他任务显示空状态 + 模拟生成 CTA
            status_snapshot = get_status(tid)
            if status_snapshot.get("error_code") == "task_not_found":
                html = RESULT_HTML.replace("{title}", "任务不存在") \
                                  .replace("{task_id_short}", tid[:8]) \
                                  .replace("{task_id}", tid) \
                                  .replace("{n8n_editor_url}", N8N_IMAGE_ENTRY_URL) \
                                  .replace("{error_block}", f'<div class="err-card"><div class="err-title">任务不存在或已被删除</div><div class="err-msg">当前 task_id 为 {h(tid)}，数据库中已经没有这条任务记录。</div><div class="err-help">这不是图片生成慢，而是结果页正在查看一个失效任务。请返回首页重新提交，或去历史任务页确认是否被删除。</div></div>') \
                                  .replace("{progress_block}", "") \
                                  .replace("{poll_script}", "")
                self._send(404, html); return
            has_video = tid.startswith("55555555-5555")
            video_block = VIDEO_HAS if has_video else VIDEO_EMPTY
            html = RESULT_HTML.replace("{title}", "候选审核") \
                              .replace("{task_id_short}", tid[:8]) \
                              .replace("{task_id}", tid) \
                              .replace("{n8n_editor_url}", N8N_IMAGE_ENTRY_URL) \
                              .replace("{error_block}", "") \
                              .replace("{progress_block}", PROGRESS_BLOCK.replace("{video_block}", video_block)) \
                              .replace("{poll_script}", POLL_SCRIPT.replace("{task_id}", tid))
            self._send(200, html)
        elif path == "/api/status":
            qs = urllib.parse.urlparse(self.path).query
            tid = (urllib.parse.parse_qs(qs).get("task_id") or [""])[0]
            try:
                data = get_status(tid) if tid else {"error":"missing task_id"}
            except ValueError as e:
                data = {"error": str(e)}
            status_code = 200 if "error" not in data else 503
            if data.get("error") == "missing task_id" or "UUID" in data.get("error", ""):
                status_code = 400
            elif data.get("error_code") == "task_not_found":
                status_code = 404
            self._send(status_code, json.dumps(data, ensure_ascii=False), "application/json; charset=utf-8")
        elif path == "/api/export-zip":
            qs = urllib.parse.urlparse(self.path).query
            tid = (urllib.parse.parse_qs(qs).get("task_id") or [""])[0]
            try:
                filename, data, err = build_candidates_zip(tid)
            except ValueError as e:
                self._send(400, json.dumps({"error": str(e)}, ensure_ascii=False), "application/json; charset=utf-8"); return
            if err:
                self._send(404 if "没有可导出" in err else 500, json.dumps({"error": err}, ensure_ascii=False), "application/json; charset=utf-8"); return
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif path == "/api/gen-video-status":
            qs = urllib.parse.urlparse(self.path).query
            sid = (urllib.parse.parse_qs(qs).get("id") or [""])[0]
            data = seedance_poll(sid) if sid else {"error":"missing id"}
            status_code = 200
            if data.get("status") == "error" or ("error" in data and data.get("status") != "failed"):
                status_code = 503
            if data.get("error") == "missing id":
                status_code = 400
            self._send(status_code, json.dumps(data, ensure_ascii=False), "application/json; charset=utf-8")
        elif path == "/open-n8n":
            qs = urllib.parse.urlparse(self.path).query
            pipeline = ((urllib.parse.parse_qs(qs).get("pipeline") or ["image"])[0] or "image").strip().lower()
            if pipeline == "video":
                target_url = N8N_VIDEO_EDITOR_URL
            elif pipeline == "image":
                target_url = N8N_IMAGE_EDITOR_URL
            else:
                target_url = N8N_EDITOR_URL
            self._send(200, render_external_redirect_page("打开 N8N 画布", target_url, "继续打开 N8N"))
        elif path == "/settings":
            self._send(200, render_settings_page())
        elif path == "/health":
            db_ok = False
            db_err = ""
            _, db_err = pg_vars("SELECT 1;")
            db_ok = not db_err
            review_count_raw, review_count_err = pg_vars("SELECT COUNT(*)::text FROM content_factory.v_pending_review;")
            review_queue_count = int(review_count_raw) if review_count_raw.isdigit() else 0
            pac_saved_at = _env.get("PAC_LAST_SAVED_AT", "")
            n8n_synced_at = _env.get("PAC_N8N_SYNCED_AT", "")
            if pac_saved_at and n8n_synced_at and n8n_synced_at >= pac_saved_at:
                n8n_sync_status = "synced"
                n8n_sync_text = f"N8N credentials synced at {n8n_synced_at}"
            elif pac_saved_at:
                n8n_sync_status = "needs_sync"
                n8n_sync_text = "N8N credentials need sync after latest PAC save"
            else:
                n8n_sync_status = "unknown"
                n8n_sync_text = "N8N sync has not been recorded"
            health = {
                "status": "ok" if db_ok else "degraded",
                "host": HOST,
                "port": PORT,
                "postgres_ok": db_ok,
                "postgres_error": db_err[:160],
                "review_queue_count": review_queue_count,
                "review_queue_error": review_count_err[:160],
                "ark_configured": bool(IMAGE_API_KEY or VIDEO_API_KEY),
                "media_configured": bool(IMAGE_API_KEY or VIDEO_API_KEY),
                "media_gateway": {
                    "configured": bool(MEDIA_API_KEY),
                    "base_url": MEDIA_BASE_URL,
                    "label": f"media gateway · {mask_secret(MEDIA_API_KEY)}" if MEDIA_API_KEY else "media gateway · 未配置",
                },
                "providers": {
                    "llm": {
                        "provider": LLM_PROVIDER,
                        "model": LLM_MODEL,
                        "configured": bool(LLM_API_KEY),
                        "label": f"{LLM_PROVIDER} · {LLM_MODEL}",
                    },
                    "image": {
                        "provider": IMAGE_PROVIDER,
                        "model": IMAGE_MODEL,
                        "configured": bool(IMAGE_API_KEY),
                        "label": f"{IMAGE_PROVIDER} · {IMAGE_MODEL}",
                    },
                    "video": {
                        "provider": VIDEO_PROVIDER,
                        "model": VIDEO_MODEL,
                        "configured": bool(VIDEO_API_KEY),
                        "label": f"{VIDEO_PROVIDER} · {VIDEO_MODEL}",
                    },
                    "asr": {
                        "provider": ASR_PROVIDER,
                        "model": ASR_MODEL,
                        "configured": bool(ASR_API_KEY) or ASR_PROVIDER == "disabled",
                        "label": f"{ASR_PROVIDER} · {ASR_MODEL}",
                    },
                },
                "sync": {
                    "pac_last_saved_at": pac_saved_at,
                    "n8n_synced_at": n8n_synced_at,
                    "n8n_status": n8n_sync_status,
                    "n8n_text": n8n_sync_text,
                    "credential_names": ["cred-llm-provider", "cred-image-provider", "cred-video-provider", "cred-volcengine-asr"],
                },
                "n8n_trigger": N8N_TRIGGER,
                "status_api_shape_version": 3,
                "export_package_version": 2,
                "ui_script_has_video_draft": "cf_video_draft" in POLL_SCRIPT,
                "video_config_dynamic": 'data-preset="showcase"' in VIDEO_EMPTY,
            }
            self._send(200 if db_ok else 503, json.dumps(health, ensure_ascii=False), "application/json; charset=utf-8")
        elif path.startswith("/video/") or path.startswith("/audio/"):
            is_audio = path.startswith("/audio/")
            fname = path[len("/audio/" if is_audio else "/video/"):]
            if "/" in fname or "\\" in fname or ".." in fname:
                self._send(400, "bad path"); return
            fpath = (AUDIO_DIR if is_audio else VIDEO_DIR) / fname
            if not fpath.is_file():
                self._send(404, f"video not found: {fname}"); return
            ct, _ = mimetypes.guess_type(str(fpath))
            ct = ct or "video/mp4"
            data = fpath.read_bytes()
            # 支持 Range 请求（视频随机播放/seek 必需）
            range_h = self.headers.get("Range")
            total = len(data)
            if range_h and range_h.startswith("bytes="):
                try:
                    rng = range_h[6:].split("-")
                    start = int(rng[0]) if rng[0] else 0
                    end = int(rng[1]) if rng[1] else total - 1
                    end = min(end, total - 1)
                    chunk = data[start:end+1]
                    self.send_response(206)
                    self.send_header("Content-Type", ct)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(len(chunk)))
                    self.end_headers()
                    self.wfile.write(chunk)
                    return
                except Exception:
                    pass
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(total))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(data)
        elif path == "/history" or path == "/list":
            rows, _ = pg_rows(
                "SELECT t.id::text, p.sku, p.name, p.category, t.status::text, t.created_at::text, "
                "t.requested_count::text, "
                "(SELECT COUNT(*) FROM content_factory.candidates WHERE task_id=t.id), "
                "COALESCE((SELECT oss_url FROM content_factory.candidates WHERE task_id=t.id ORDER BY sequence_no LIMIT 1), '-') "
                "FROM content_factory.tasks t JOIN content_factory.products p ON p.id=t.product_id "
                "WHERE t.pipeline='image' ORDER BY t.created_at DESC;"
            )
            cards_html = ""
            for r in rows:
                p = r.split("\t")
                if len(p) >= 9:
                    tid, sku, name, cat, status, created, requested_count, cnt, thumb = [x.strip() for x in p[:9]]
                    requested_count = int(requested_count) if requested_count.isdigit() else 11
                    cnt = int(cnt) if cnt.isdigit() else 0
                    pct = min(int(cnt * 100 / max(requested_count, 1)), 100)
                    pill = render_task_status_pill(status, candidate_count=cnt, requested_count=requested_count)
                    filter_status = format_task_status(status, candidate_count=cnt, requested_count=requested_count)
                    search_blob = " ".join([tid[:8], tid, sku, name, cat, status]).lower()
                    safe_thumb = safe_http_url(thumb)
                    thumb_html = f'<img src="{h(safe_thumb)}" alt="" />' if safe_thumb else '<div class="thumb-empty">尚未生成</div>'
                    cards_html += f'''
<div class="hist-card" id="hist-card-{h(tid)}" data-task-id="{h(tid)}" data-task-name="{h(name)}" data-search="{h(search_blob)}" data-filter-status="{h(filter_status)}">
  <button type="button" class="hist-select" data-task-id="{h(tid)}" data-task-name="{h(name)}" aria-pressed="false" onclick="toggleSelection(event, this)">□</button>
  <button type="button" class="hist-delete" data-task-id="{h(tid)}" data-task-name="{h(name)}" onclick="deleteTask(event, this)">删除</button>
  <a class="hist-link" href="/task?task_id={h(tid)}">
    <div class="hist-thumb">{thumb_html}</div>
    <div class="hist-body">
      <div class="hist-row1">
        <span class="hist-sku">{h(sku)}</span>
        {pill}
      </div>
      <div class="hist-name">{h(name)}</div>
      <div class="hist-meta">
        <span>{h(cat)}</span><span>·</span>
        <span>{cnt}/{requested_count} 张</span><span>·</span>
        <span>{h(created[:16])}</span>
      </div>
      <div class="hist-bar"><div class="hist-bar-fill" style="width:{pct}%"></div></div>
    </div>
  </a>
  <div class="hist-foot">
    <a class="hist-mini" href="/task?task_id={h(tid)}">任务详情</a>
    <a class="hist-mini hist-mini-primary" href="/result?task_id={h(tid)}">候选审核</a>
  </div>
</div>'''
            empty_html = '<div class="empty"><div class="empty-icon">📭</div><div>暂无任务历史</div><a href="/" class="btn btn-primary" style="margin-top:14px">+ 录入第一个产品</a></div>' if not rows else ''

            html = """<!DOCTYPE html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>历史任务 · ContentFactory</title>
<style>""" + COMMON_CSS + """
.shell{max-width:1280px;margin:0 auto;padding:0 24px}
.page-header{padding:32px 0 24px;display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap}
.page-title{font-size:24px;font-weight:700;letter-spacing:-.02em;margin-bottom:4px}
.page-sub{font-size:13px;color:var(--slate-500)}
.page-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.filters{
  display:grid;grid-template-columns:minmax(260px,1fr) auto;gap:12px;margin-bottom:16px;align-items:center;
}
.search-box{
  display:flex;align-items:center;gap:8px;background:#fff;border:1px solid var(--slate-200);
  border-radius:12px;padding:0 14px;box-shadow:var(--shadow-sm);
}
.search-box input{
  flex:1;border:0;outline:0;background:transparent;font:inherit;color:var(--slate-900);padding:12px 0;
}
.search-box span{font-size:13px;color:var(--slate-400)}
.filter-tabs{display:flex;gap:8px;flex-wrap:wrap}
.filter-tab{
  padding:9px 12px;border-radius:999px;border:1px solid var(--slate-200);background:#fff;color:var(--slate-600);
  font-size:12px;font-weight:600;transition:all .15s var(--ease);
}
.filter-tab.active{background:var(--indigo);border-color:var(--indigo);color:#fff}
.batch-btn-danger{background:var(--red);color:#fff}
.batch-btn-danger:hover{background:#dc2626}
.batch-btn-danger[disabled]{background:var(--slate-300);color:#fff}

.hist-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:14px}
.hist-card{
  background:#fff;border:1px solid var(--slate-200);border-radius:12px;
  overflow:hidden;display:flex;flex-direction:column;position:relative;
  transition:all .2s var(--ease);
  box-shadow:var(--shadow-sm);
}
.hist-card:hover{transform:translateY(-2px);box-shadow:var(--shadow-lg);border-color:var(--indigo)}
.hist-card.selected{
  border-color:var(--indigo);
  box-shadow:0 0 0 3px rgba(99,102,241,.14), var(--shadow-lg);
}
.hist-link{display:flex;flex-direction:column;flex:1}
.hist-foot{
  display:flex;justify-content:space-between;gap:8px;padding:0 16px 16px;
}
.hist-mini{
  display:inline-flex;align-items:center;justify-content:center;flex:1;
  padding:8px 10px;border-radius:8px;border:1px solid var(--slate-200);font-size:12px;font-weight:600;color:var(--slate-700);
  transition:all .15s var(--ease);
}
.hist-mini:hover{border-color:var(--slate-300);background:var(--slate-50)}
.hist-mini-primary{border-color:rgba(99,102,241,.22);color:var(--indigo);background:rgba(99,102,241,.06)}
.hist-mini-primary:hover{background:rgba(99,102,241,.12);border-color:rgba(99,102,241,.3)}
.hist-thumb{
  aspect-ratio:16/10;background:linear-gradient(135deg,#f1f5f9,#e2e8f0);
  position:relative;overflow:hidden;
}
.hist-thumb img{width:100%;height:100%;object-fit:cover;display:block}
.thumb-empty{
  position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  color:var(--slate-400);font-size:12px;
}
.hist-body{padding:14px 16px;flex:1;display:flex;flex-direction:column;gap:6px}
.hist-row1{display:flex;justify-content:space-between;align-items:center;gap:8px}
.hist-sku{
  font-size:11px;font-weight:600;color:var(--indigo);
  background:rgba(99,102,241,.1);padding:2px 8px;border-radius:4px;font-family:monospace;
}
.hist-name{font-size:14px;font-weight:600;color:var(--slate-900);line-height:1.4;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.hist-meta{font-size:11px;color:var(--slate-500);display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.hist-meta span{white-space:nowrap}
.hist-bar{height:3px;background:var(--slate-100);border-radius:99px;margin-top:6px;overflow:hidden}
.hist-bar-fill{height:100%;background:linear-gradient(90deg,var(--indigo),var(--pink));border-radius:99px;transition:width .4s}
.hist-select{
  position:absolute;top:10px;left:10px;z-index:2;
  width:30px;height:30px;border-radius:50%;
  background:rgba(255,255,255,.95);color:var(--slate-500);font-size:16px;font-weight:700;
  border:1px solid var(--slate-200);display:flex;align-items:center;justify-content:center;
  opacity:0;transform:translateY(-4px);transition:all .15s var(--ease);
}
.hist-select:hover{border-color:var(--indigo);color:var(--indigo)}
.hist-select.selected{
  opacity:1;transform:translateY(0);
  background:var(--indigo);border-color:var(--indigo);color:#fff;
}
.hist-delete{
  position:absolute;top:10px;right:10px;z-index:2;
  padding:6px 10px;border-radius:999px;
  background:rgba(15,23,42,.78);color:#fff;font-size:11px;font-weight:600;
  opacity:0;transform:translateY(-4px);transition:all .15s var(--ease);
}
.hist-delete:hover{background:var(--red)}
.hist-card:hover .hist-select,
.hist-card:focus-within .hist-select,
.hist-card.selected .hist-select,
.hist-card:hover .hist-delete,
.hist-card:focus-within .hist-delete{opacity:1;transform:translateY(0)}
.hist-card.deleting{opacity:.55;pointer-events:none}
.hist-pagination{
  display:flex;justify-content:space-between;align-items:center;gap:12px;
  padding:18px 0 60px;flex-wrap:wrap;
}
.hist-page-meta{font-size:12px;color:var(--slate-500)}
.hist-page-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.page-btn{
  min-width:38px;height:38px;padding:0 12px;border-radius:10px;
  border:1px solid var(--slate-200);background:#fff;color:var(--slate-700);
  font-size:12px;font-weight:600;transition:all .15s var(--ease);
}
.page-btn:hover{border-color:var(--slate-300);background:var(--slate-50)}
.page-btn.active{background:var(--indigo);border-color:var(--indigo);color:#fff}
.page-btn[disabled]{background:var(--slate-100);color:var(--slate-400)}
.hist-filter-empty{
  display:none;text-align:center;padding:48px 20px;margin-top:14px;
  border:1px dashed var(--slate-200);border-radius:14px;background:#fff;color:var(--slate-500);
}

.empty{text-align:center;padding:80px 20px;color:var(--slate-500)}
.empty-icon{font-size:48px;margin-bottom:14px}
@media(max-width:720px){
  .filters{grid-template-columns:1fr}
  .page-actions{width:100%}
  .page-actions .btn{flex:1;justify-content:center}
  .filter-tabs{width:100%}
  .hist-pagination{flex-direction:column;align-items:stretch}
  .hist-page-actions{justify-content:flex-start}
}
</style></head><body>

<nav class="nav">
  <div class="nav-left">
    <a class="logo" href="/"><span class="logo-mark">CF</span>ContentFactory</a>
    <div class="crumbs"><span>·</span> <strong>历史任务</strong></div>
  </div>
  <div class="nav-right">
    <a href="/review" class="btn btn-ghost" style="font-size:12px">待审核</a>
    <a href="/settings" class="btn btn-ghost" style="font-size:12px">模型配置</a>
    <a href="/" class="btn btn-primary">+ 新建任务</a>
    <div class="avatar">J</div>
  </div>
</nav>

<div class="shell">
  <header class="page-header">
    <div>
      <div class="page-title">历史任务</div>
      <div class="page-sub" id="histSummary">共 """ + str(len(rows)) + """ 个任务 · 点卡片查看详情，点“候选审核”进入生成结果页</div>
    </div>
    <div class="page-actions">
      <button type="button" class="btn btn-secondary" onclick="selectAllTasks()">全选当前页</button>
      <button type="button" class="btn btn-ghost" id="clearSelectionBtn" onclick="clearSelection()" disabled>取消选择</button>
      <button type="button" class="btn batch-btn-danger" id="batchDeleteBtn" onclick="deleteSelectedTasks()" disabled>删除所选</button>
    </div>
  </header>
  <section class="filters">
    <label class="search-box">
      <span>搜索</span>
      <input id="histSearchInput" type="text" placeholder="按 SKU / 名称 / 类目 / task_id 搜索" oninput="applyHistoryFilters()" />
    </label>
    <div class="filter-tabs">
      <button type="button" class="filter-tab active" data-filter="all" onclick="setStatusFilter('all', this)">全部</button>
      <button type="button" class="filter-tab" data-filter="running" onclick="setStatusFilter('running', this)">生成中</button>
      <button type="button" class="filter-tab" data-filter="done" onclick="setStatusFilter('done', this)">已完成</button>
      <button type="button" class="filter-tab" data-filter="failed" onclick="setStatusFilter('failed', this)">失败</button>
    </div>
  </section>
  """ + empty_html + """
  <div class="hist-grid">""" + cards_html + """</div>
  <div class="hist-filter-empty" id="histFilteredEmpty">当前筛选下没有任务，试试换个关键词或状态。</div>
  <div class="hist-pagination" id="histPagination" hidden>
    <div class="hist-page-meta" id="histPageMeta"></div>
    <div class="hist-page-actions" id="histPageActions"></div>
  </div>
</div>

<script>
const TOTAL_HISTORY_TASKS = """ + str(len(rows)) + """;
const HISTORY_PAGE_SIZE = 10;
const selectedTaskMap = new Map();
const histSummaryEl = document.getElementById('histSummary');
const histSearchInputEl = document.getElementById('histSearchInput');
const batchDeleteBtnEl = document.getElementById('batchDeleteBtn');
const clearSelectionBtnEl = document.getElementById('clearSelectionBtn');
const histPaginationEl = document.getElementById('histPagination');
const histPageMetaEl = document.getElementById('histPageMeta');
const histPageActionsEl = document.getElementById('histPageActions');
const histFilteredEmptyEl = document.getElementById('histFilteredEmpty');
let activeStatusFilter = 'all';
let activeHistoryPage = 1;
let filteredTaskCount = TOTAL_HISTORY_TASKS;
let totalHistoryPages = Math.max(1, Math.ceil(Math.max(TOTAL_HISTORY_TASKS, 1) / HISTORY_PAGE_SIZE));

function getVisibleTaskCount(){
  return Array.from(document.querySelectorAll('.hist-card')).filter(card => card.style.display !== 'none').length;
}

function getFilteredCards(){
  const keyword = (histSearchInputEl?.value || '').trim().toLowerCase();
  return Array.from(document.querySelectorAll('.hist-card')).filter(card => {
    const searchText = (card.dataset.search || '').toLowerCase();
    const statusBucket = card.dataset.filterStatus || 'other';
    const hitKeyword = !keyword || searchText.includes(keyword);
    const hitStatus = activeStatusFilter === 'all' || statusBucket === activeStatusFilter;
    return hitKeyword && hitStatus;
  });
}

function updateHistorySummary(){
  if(!histSummaryEl) return;
  const selectedCount = selectedTaskMap.size;
  if(selectedCount > 0){
    histSummaryEl.textContent = `已选 ${selectedCount} 个任务，可一键删除`;
    return;
  }
  const visibleCount = getVisibleTaskCount();
  const suffix = activeStatusFilter === 'all' ? '全部状态' : `状态：${activeStatusFilter}`;
  histSummaryEl.textContent = `显示 ${visibleCount} / ${TOTAL_HISTORY_TASKS} 个任务 · ${suffix} · 点卡片查看详情`;
}

function updateSelectionUI(){
  const count = selectedTaskMap.size;
  if(batchDeleteBtnEl){
    batchDeleteBtnEl.disabled = count === 0;
    batchDeleteBtnEl.textContent = count > 0 ? `删除所选 (${count})` : '删除所选';
  }
  if(clearSelectionBtnEl){ clearSelectionBtnEl.disabled = count === 0; }
  updateHistorySummary();
}

function setTaskSelected(taskId, taskName, selected){
  const card = document.getElementById(`hist-card-${taskId}`);
  if(!card) return;
  const btn = card.querySelector('.hist-select');
  if(selected){
    selectedTaskMap.set(taskId, taskName || taskId.slice(0, 8));
    card.classList.add('selected');
    if(btn){
      btn.classList.add('selected');
      btn.setAttribute('aria-pressed', 'true');
      btn.textContent = '✓';
    }
  }else{
    selectedTaskMap.delete(taskId);
    card.classList.remove('selected');
    if(btn){
      btn.classList.remove('selected');
      btn.setAttribute('aria-pressed', 'false');
      btn.textContent = '□';
    }
  }
}

function toggleSelection(ev, btn){
  ev.preventDefault();
  ev.stopPropagation();
  const taskId = btn.dataset.taskId || '';
  const taskName = btn.dataset.taskName || '';
  const shouldSelect = !selectedTaskMap.has(taskId);
  setTaskSelected(taskId, taskName, shouldSelect);
  updateSelectionUI();
}

function selectAllTasks(){
  document.querySelectorAll('.hist-card').forEach(card => {
    if(card.style.display === 'none') return;
    const btn = card.querySelector('.hist-select');
    if(btn){
      setTaskSelected(btn.dataset.taskId || '', btn.dataset.taskName || '', true);
    }
  });
  updateSelectionUI();
}

function clearSelection(){
  Array.from(selectedTaskMap.entries()).forEach(([taskId, taskName]) => {
    setTaskSelected(taskId, taskName, false);
  });
  updateSelectionUI();
}

function setStatusFilter(filter, btn){
  activeStatusFilter = filter;
  document.querySelectorAll('.filter-tab').forEach(node => node.classList.remove('active'));
  if(btn){ btn.classList.add('active'); }
  applyHistoryFilters();
}

function applyHistoryFilters(){
  const keyword = (histSearchInputEl?.value || '').trim().toLowerCase();
  document.querySelectorAll('.hist-card').forEach(card => {
    const searchText = (card.dataset.search || '').toLowerCase();
    const statusBucket = card.dataset.filterStatus || 'other';
    const hitKeyword = !keyword || searchText.includes(keyword);
    const hitStatus = activeStatusFilter === 'all' || statusBucket === activeStatusFilter;
    card.style.display = (hitKeyword && hitStatus) ? '' : 'none';
  });
  updateHistorySummary();
}

function renderHistoryPagination(filteredCards){
  filteredTaskCount = filteredCards.length;
  totalHistoryPages = Math.max(1, Math.ceil(Math.max(filteredTaskCount, 1) / HISTORY_PAGE_SIZE));
  if(activeHistoryPage > totalHistoryPages){
    activeHistoryPage = totalHistoryPages;
  }
  const startIndex = (activeHistoryPage - 1) * HISTORY_PAGE_SIZE;
  const pageCards = filteredCards.slice(startIndex, startIndex + HISTORY_PAGE_SIZE);
  const visibleCards = new Set(pageCards);

  document.querySelectorAll('.hist-card').forEach(card => {
    card.style.display = visibleCards.has(card) ? '' : 'none';
  });

  if(histFilteredEmptyEl){
    histFilteredEmptyEl.style.display = (filteredTaskCount === 0 && TOTAL_HISTORY_TASKS > 0) ? 'block' : 'none';
  }
  if(histPaginationEl){
    histPaginationEl.hidden = filteredTaskCount <= HISTORY_PAGE_SIZE;
  }
  if(histPageMetaEl){
    histPageMetaEl.textContent = filteredTaskCount > 0
      ? `每页 ${HISTORY_PAGE_SIZE} 条 · 第 ${activeHistoryPage} / ${totalHistoryPages} 页`
      : '当前没有匹配的任务';
  }
  if(histPageActionsEl){
    if(filteredTaskCount <= HISTORY_PAGE_SIZE){
      histPageActionsEl.innerHTML = '';
      return;
    }
    const pageButtons = [];
    const startPage = Math.max(1, activeHistoryPage - 2);
    const endPage = Math.min(totalHistoryPages, startPage + 4);
    pageButtons.push(`<button type="button" class="page-btn" onclick="goToHistoryPage(${activeHistoryPage - 1})" ${activeHistoryPage === 1 ? 'disabled' : ''}>上一页</button>`);
    for(let page = startPage; page <= endPage; page += 1){
      pageButtons.push(`<button type="button" class="page-btn ${page === activeHistoryPage ? 'active' : ''}" onclick="goToHistoryPage(${page})">${page}</button>`);
    }
    pageButtons.push(`<button type="button" class="page-btn" onclick="goToHistoryPage(${activeHistoryPage + 1})" ${activeHistoryPage === totalHistoryPages ? 'disabled' : ''}>下一页</button>`);
    histPageActionsEl.innerHTML = pageButtons.join('');
  }
}

function goToHistoryPage(page){
  const nextPage = Math.max(1, Math.min(page, totalHistoryPages));
  if(nextPage === activeHistoryPage){
    return;
  }
  activeHistoryPage = nextPage;
  renderHistoryPagination(getFilteredCards());
  updateHistorySummary();
}

function updateHistorySummary(){
  if(!histSummaryEl) return;
  const selectedCount = selectedTaskMap.size;
  if(selectedCount > 0){
    histSummaryEl.textContent = `已选 ${selectedCount} 个任务，可一键删除`;
    return;
  }
  const visibleCount = getVisibleTaskCount();
  const suffix = activeStatusFilter === 'all' ? '全部状态' : `状态：${activeStatusFilter}`;
  const pageLabel = filteredTaskCount > 0 ? ` · 第 ${activeHistoryPage}/${totalHistoryPages} 页` : '';
  histSummaryEl.textContent = `显示 ${visibleCount} / ${filteredTaskCount} 个任务 · 共 ${TOTAL_HISTORY_TASKS} 条记录${pageLabel} · ${suffix}`;
}

function applyHistoryFilters(resetPage = true){
  if(resetPage){
    activeHistoryPage = 1;
  }
  renderHistoryPagination(getFilteredCards());
  updateHistorySummary();
}

async function deleteTask(ev, btn){
  ev.preventDefault();
  ev.stopPropagation();
  const taskId = btn.dataset.taskId || '';
  const taskName = btn.dataset.taskName || '';
  const label = taskName || taskId.slice(0, 8);
  if(!confirm(`确认删除任务“${label}”吗？\\n这会同时删除该任务下的候选、运行记录和审核日志。`)){
    return;
  }
  const card = document.getElementById(`hist-card-${taskId}`);
  if(card){ card.classList.add('deleting'); }
  try{
    const res = await fetch('/api/delete-task', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({task_id: taskId}),
    });
    const data = await res.json();
    if(!res.ok || data.error){
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    location.reload();
  }catch(err){
    if(card){ card.classList.remove('deleting'); }
    alert(`删除失败：${err.message || err}`);
  }
}

async function deleteSelectedTasks(){
  const taskIds = Array.from(selectedTaskMap.keys());
  if(taskIds.length === 0){
    return;
  }
  if(!confirm(`确认一键删除已选的 ${taskIds.length} 个任务吗？\\n这会同时删除对应候选、运行记录和审核日志。`)){
    return;
  }
  taskIds.forEach(taskId => {
    const card = document.getElementById(`hist-card-${taskId}`);
    if(card){ card.classList.add('deleting'); }
  });
  try{
    const res = await fetch('/api/delete-tasks', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({task_ids: taskIds}),
    });
    const data = await res.json();
    if(!res.ok){
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    if(data.errors && data.errors.length){
      alert(`已删除 ${data.deleted.length} 个任务，${data.errors.length} 个失败。页面将刷新到最新状态。`);
    }
    location.reload();
  }catch(err){
    taskIds.forEach(taskId => {
      const card = document.getElementById(`hist-card-${taskId}`);
      if(card){ card.classList.remove('deleting'); }
    });
    alert(`批量删除失败：${err.message || err}`);
  }
}

applyHistoryFilters();
</script>

</body></html>"""
            self._send(200, html)
        else:
            self._send(404, "not found")

    def do_POST(self):
        if self.path == "/settings":
            try:
                raw_bytes = read_request_body(self, MAX_FORM_BODY_BYTES, "配置表单")
            except ValueError as e:
                self._send(400, render_settings_page(error=str(e))); return

            def _safe_decode_settings(b):
                for enc in ("utf-8", "gbk"):
                    try: return b.decode(enc)
                    except UnicodeDecodeError: continue
                return b.decode("utf-8", errors="replace")

            try:
                form_b = urllib.parse.parse_qs(raw_bytes, keep_blank_values=True)
                form = {_safe_decode_settings(k):[_safe_decode_settings(v) for v in vs] for k, vs in form_b.items()}
            except Exception:
                form = urllib.parse.parse_qs(_safe_decode_settings(raw_bytes), keep_blank_values=True)
            err = save_settings_form(form)
            if err:
                self._send(400, render_settings_page(error=err)); return
            self._send(200, render_settings_page(message="配置已保存到 deploy/.env.local。当前 5001 服务已刷新，N8N 如需同步请重启容器并重跑 n8n_setup.py。"))
            return

        if self.path == "/api/review-candidate":
            try:
                raw = read_request_body(self, MAX_JSON_BODY_BYTES, "JSON 请求体")
                payload = json.loads(raw.decode("utf-8"))
                result, err = review_candidate(payload)
            except ValueError as e:
                self._send(400, json.dumps({"error": str(e)}, ensure_ascii=False), "application/json; charset=utf-8"); return
            except Exception as e:
                self._send(400, json.dumps({"error": f"bad json: {e}"}, ensure_ascii=False), "application/json; charset=utf-8"); return
            if err:
                self._send(400, json.dumps({"error": err}, ensure_ascii=False), "application/json; charset=utf-8"); return
            self._send(200, json.dumps(result, ensure_ascii=False), "application/json; charset=utf-8")
            return

        if self.path == "/api/approve-all":
            try:
                raw = read_request_body(self, MAX_JSON_BODY_BYTES, "JSON 请求体")
                payload = json.loads(raw.decode("utf-8"))
                result, err = approve_all_candidates(payload.get("task_id", ""), payload.get("reviewer") or "local-ui")
            except ValueError as e:
                self._send(400, json.dumps({"error": str(e)}, ensure_ascii=False), "application/json; charset=utf-8"); return
            except Exception as e:
                self._send(400, json.dumps({"error": f"bad json: {e}"}, ensure_ascii=False), "application/json; charset=utf-8"); return
            if err:
                self._send(400, json.dumps({"error": err}, ensure_ascii=False), "application/json; charset=utf-8"); return
            self._send(200, json.dumps(result, ensure_ascii=False), "application/json; charset=utf-8")
            return

        if self.path == "/api/regenerate-rejected":
            try:
                raw = read_request_body(self, MAX_JSON_BODY_BYTES, "JSON 请求体")
                payload = json.loads(raw.decode("utf-8"))
                result, err = regenerate_rejected_candidates(
                    payload.get("task_id", ""),
                    payload.get("reviewer") or "local-ui",
                    payload.get("candidate_ids") or [],
                )
            except ValueError as e:
                self._send(400, json.dumps({"error": str(e)}, ensure_ascii=False), "application/json; charset=utf-8"); return
            except Exception as e:
                self._send(400, json.dumps({"error": f"bad json: {e}"}, ensure_ascii=False), "application/json; charset=utf-8"); return
            if err:
                self._send(400, json.dumps({"error": err}, ensure_ascii=False), "application/json; charset=utf-8"); return
            self._send(200, json.dumps(result, ensure_ascii=False), "application/json; charset=utf-8")
            return

        if self.path == "/api/delete-tasks":
            try:
                raw = read_request_body(self, MAX_JSON_BODY_BYTES, "JSON 请求体")
                payload = json.loads(raw.decode("utf-8"))
                result = delete_tasks(payload.get("task_ids", []))
            except ValueError as e:
                self._send(400, json.dumps({"error": str(e)}, ensure_ascii=False), "application/json; charset=utf-8"); return
            except Exception as e:
                self._send(400, json.dumps({"error": f"bad json: {e}"}), "application/json"); return
            status_code = 200 if not result["errors"] else 207
            self._send(status_code, json.dumps(result, ensure_ascii=False), "application/json; charset=utf-8")
            return

        if self.path == "/api/delete-task":
            try:
                raw = read_request_body(self, MAX_JSON_BODY_BYTES, "JSON 请求体")
                payload = json.loads(raw.decode("utf-8"))
                result, err = delete_task(payload.get("task_id", ""))
            except ValueError as e:
                self._send(400, json.dumps({"error": str(e)}, ensure_ascii=False), "application/json; charset=utf-8"); return
            except Exception as e:
                self._send(400, json.dumps({"error": f"bad json: {e}"}), "application/json"); return
            if err:
                code = 404 if "不存在" in err else 500
                self._send(code, json.dumps({"error": err}, ensure_ascii=False), "application/json; charset=utf-8"); return
            self._send(200, json.dumps(result, ensure_ascii=False), "application/json; charset=utf-8")
            return

        if self.path == "/api/gen-video":
            try:
                raw = read_request_body(self, MAX_JSON_BODY_BYTES, "JSON 请求体")
                payload = json.loads(raw.decode("utf-8"))
            except ValueError as e:
                self._send(400, json.dumps({"error": str(e)}, ensure_ascii=False), "application/json; charset=utf-8"); return
            except Exception:
                self._send(400, json.dumps({"error":"bad json"}), "application/json"); return
            tid = payload.get("task_id", "")
            prompt = payload.get("prompt") or ""
            ratio = payload.get("ratio") or "9:16"
            try:
                seq = parse_int_field(payload.get("seq") or 7, "seq")
                duration = parse_int_field(payload.get("duration") or 12, "duration")
            except ValueError as e:
                self._send(400, json.dumps({"error": str(e)}, ensure_ascii=False), "application/json; charset=utf-8"); return
            if duration not in ALLOWED_VIDEO_DURATIONS:
                self._send(400, json.dumps({"error":"duration 仅支持 6 / 12 / 24 秒"}, ensure_ascii=False), "application/json; charset=utf-8"); return
            if ratio not in ALLOWED_VIDEO_RATIOS:
                self._send(400, json.dumps({"error":"ratio 仅支持 9:16 / 1:1 / 16:9"}, ensure_ascii=False), "application/json; charset=utf-8"); return
            if not VIDEO_API_KEY:
                self._send(400, json.dumps({"error":"视频功能未配置 VIDEO_API_KEY/MEDIA_API_KEY"}, ensure_ascii=False), "application/json; charset=utf-8"); return
            try:
                img_url = get_candidate_url(tid, seq)
            except ValueError as e:
                self._send(400, json.dumps({"error": str(e)}, ensure_ascii=False), "application/json; charset=utf-8"); return
            if not img_url:
                self._send(404, json.dumps({"error":f"候选 #{seq} 未找到，可能还没生成"}), "application/json"); return
            if not prompt.strip():
                self._send(400, json.dumps({"error":"prompt 不能为空"}), "application/json"); return
            if len(prompt) > 2000:
                self._send(400, json.dumps({"error":"prompt 过长，最多 2000 字符"}), "application/json"); return
            first_frame_url, err = prepare_seedance_first_frame(img_url, prompt, ratio=ratio)
            if err:
                self._send(500, json.dumps({"error":"视频首帧生成失败: "+err}, ensure_ascii=False), "application/json; charset=utf-8"); return
            sd_tid, err = seedance_submit(first_frame_url, prompt, duration=duration, ratio=ratio)
            if err:
                self._send(500, json.dumps({"error":err}), "application/json"); return
            self._send(200, json.dumps({"seedance_task_id": sd_tid, "image_url": first_frame_url, "source_image_url": img_url}, ensure_ascii=False), "application/json; charset=utf-8")
            return

        if self.path != "/submit":
            self._send(404, "not found"); return
        try:
            raw_bytes = read_request_body(self, MAX_FORM_BODY_BYTES, "表单请求体")
        except ValueError as e:
            self._send(400, str(e)); return

        def _safe_decode(b):
            for enc in ("utf-8", "gbk"):
                try: return b.decode(enc)
                except UnicodeDecodeError: continue
            return b.decode("utf-8", errors="replace")

        try:
            form_b = urllib.parse.parse_qs(raw_bytes, keep_blank_values=True)
            form = {_safe_decode(k):[_safe_decode(v) for v in vs] for k, vs in form_b.items()}
        except Exception:
            form = urllib.parse.parse_qs(_safe_decode(raw_bytes), keep_blank_values=True)

        tid, err = upsert_product_and_task(form)
        if err:
            html = RESULT_HTML.replace("{title}", "录入失败") \
                              .replace("{task_id_short}", "ERROR") \
                              .replace("{task_id}", "-") \
                              .replace("{n8n_editor_url}", N8N_IMAGE_ENTRY_URL) \
                              .replace("{error_block}", f'<div class="err-card"><div class="err-title">录入失败</div><div class="err-msg">{h(err)}</div></div>') \
                              .replace("{progress_block}", "") \
                              .replace("{poll_script}", "")
            self._send(500, html); return

        code, body = trigger_n8n(tid)
        if code >= 400:
            html = RESULT_HTML.replace("{title}", "N8N 触发失败") \
                              .replace("{task_id_short}", tid[:8]) \
                              .replace("{task_id}", tid) \
                              .replace("{n8n_editor_url}", N8N_IMAGE_ENTRY_URL) \
                              .replace("{error_block}", f'<div class="err-card"><div class="err-title">N8N 触发失败</div><div class="err-msg">HTTP {code} - {h(body[:200])}</div><div class="err-help">任务已经创建，后续可通过该 task_id 重新检查状态，或在 N8N 画布中手动重试 webhook。</div></div>') \
                              .replace("{progress_block}", "") \
                              .replace("{poll_script}", "")
            self._send(500, html); return

        self.send_response(303)
        self.send_header("Location", f"/result?task_id={tid}")
        self.end_headers()

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    print(f"=== ContentFactory v3 · http://{HOST}:{PORT} ===")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
