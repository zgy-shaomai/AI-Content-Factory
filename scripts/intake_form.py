"""
内容工厂 v3 · SaaS 级 UI（演示用）
访问 http://localhost:5001
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.request, urllib.parse, urllib.error
import subprocess
import sys
import html
import re

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
VIDEO_DIR = Path(__file__).parent.parent / "_demo_seed" / "videos"
AUDIO_DIR = Path(__file__).parent.parent / "_demo_seed" / "audio"

# 从 deploy/.env.local 读 ARK key（如果存在），fallback 到环境变量
def _load_env_local():
    env_path = Path(__file__).parent.parent / "deploy" / ".env.local"
    out = {}
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
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
ARK_API_KEY = _env.get("ARK_API_KEY") or os.environ.get("ARK_API_KEY", "")
ARK_BASE = "https://ark.cn-beijing.volces.com/api/v3"
SEEDANCE_MODEL = "doubao-seedance-1-0-pro-250528"
MAX_FORM_BODY_BYTES = 64 * 1024
MAX_JSON_BODY_BYTES = 32 * 1024
ALLOWED_VIDEO_DURATIONS = {6, 12, 24}
ALLOWED_VIDEO_RATIOS = {"9:16", "1:1", "16:9"}
RUNNING_TASK_STATUSES = {"pending", "analyzing", "prompting", "generating", "reviewing", "candidates_ready", "regenerating"}
DONE_TASK_STATUSES = {"approved", "archived", "delivered"}
VIDEO_STATUS_TEXT = "已配置视频生成，可直接提交成片" if ARK_API_KEY else "未配置 ARK_API_KEY，视频提交会被后端明确拦截"
VIDEO_STATUS_CLASS = "env-ready" if ARK_API_KEY else "env-warn"

if not ARK_API_KEY:
    print("⚠️  ARK_API_KEY 未配置！视频生成功能不可用。")
    print("   请在 deploy/.env.local 里填 ARK_API_KEY=... 后重启")


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
  document.getElementById('f_sku').value=t.sku;
  document.getElementById('f_cat').value=t.cat;
  document.getElementById('f_name').value=t.name;
  document.getElementById('f_color').value=t.color;
  document.getElementById('f_aud').value=t.aud;
  document.getElementById('f_sp').value=t.sp.replace(/\\\\n/g,'\\n');
  document.getElementById('f_sc').value=t.sc.replace(/\\\\n/g,'\\n');
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
    const count = field.value.split('\n').map(v=>v.trim()).filter(Boolean).length;
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
.video-preview-shell{
  width:min(100%,460px);
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
  background:#0b1120;
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
</style></head><body>

<nav class="nav">
  <div class="nav-left">
    <a class="logo" href="/"><span class="logo-mark">CF</span>ContentFactory</a>
    <div class="crumbs"><span>·</span> <a href="/history" style="color:var(--slate-500)">历史任务</a> <span>·</span> <strong>{task_id_short}</strong> <span>·</span> 候选审核</div>
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
    <button class="btn btn-ghost">⟲ 重新生成驳回的</button>
    <button class="btn btn-secondary">⤓ 导出 ZIP</button>
    <button class="btn btn-success">✓ 全部通过</button>
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
      <div class="video-sub">同一模特、同一服装、同一场景 · 12 秒 · Seedance image-to-video</div>
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
      <div class="video-sub">候选图审核通过后，挑任意一张作为视频首帧 · Seedance image-to-video · 单条约 90-180 秒</div>
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
    <div class="vc-cost">预计耗时 90-180 秒 · 按 Seedance 视频时长计费</div>
  </div>
</div>
"""


VIDEO_EMPTY = """
<div class="video-showcase video-empty">
  <div class="video-header">
    <div>
      <div class="video-title">🎞 视频成片</div>
      <div class="video-sub">候选图审核通过后，选择一张作为首帧，再提交 Seedance image-to-video 生成 6 / 12 / 24 秒短视频。</div>
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

// 视频空状态：真调 Seedance API 出片
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
        <div class="video-sub">用候选图 #${seq} 作为首帧 · ${duration}s · ${ratio} · Seedance image-to-video</div>
      </div>
      <span class="pill-status pill-running"><span class="dot"></span>生成中</span>
    </div>
    <div class="video-generating">
      <div class="gen-spinner"></div>
      <div class="gen-text" id="genText">提交 Seedance 任务...</div>
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
    document.getElementById('genText').textContent = '已提交，Seedance 渲染中...';
    document.getElementById('genSub').textContent = `Seedance task: ${seedanceTid.slice(0,16)}...`;
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
    // 更新进度（Seedance 没有真实进度，按 elapsed 估算）
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
        showGenError('Seedance 生成失败: '+(d.error||'unknown'));return;
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
        <div class="video-sub">${duration} 秒 · ${ratio} · Seedance image-to-video · 刚刚生成</div>
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

function imgCardHTML(c, idx){
  const seq = seqNoOf(c, idx);
  const t = classify(c);
  const isKey = seq === currentKeyframe;
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
        <button class="approve" onclick="markApproval(${idx},'approve',event)" title="审核通过">通过</button>
        <button class="reject" onclick="markApproval(${idx},'reject',event)" title="驳回">驳回</button>
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
    const nodes = [];
    for(let seq = 1; seq <= getRequestedCount(); seq += 1){
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
  if(allCands.length > 0 || approvals.approve > 0 || approvals.reject > 0 || pollFinished){
    actionBar.classList.add('visible');
  }
}

function markApproval(idx, act, ev){
  if(ev)ev.stopPropagation();
  const prev = approvals.marked[idx];
  if(prev === act){
    approvals[act] = Math.max(approvals[act] - 1, 0);
    delete approvals.marked[idx];
  } else {
    if(prev)approvals[prev] = Math.max(approvals[prev] - 1, 0);
    approvals[act] += 1;
    approvals.marked[idx] = act;
  }
  rerender();
  updateActionSummary();
  const seq = seqNoOf(allCands[idx] || {}, idx);
  showToast(act === 'approve' ? `候选图 #${seq} 已通过` : `候选图 #${seq} 已驳回`, act === 'approve' ? 'green' : 'red');
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
  bar.innerHTML = `
    <button class="lb-btn lb-approve" onclick="markApproval(${idx},'approve',event);closeLightbox()">审核通过</button>
    <button class="lb-btn lb-reject" onclick="markApproval(${idx},'reject',event);closeLightbox()">驳回</button>
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
  if(!$('lightbox').classList.contains('open'))return;
  if(e.key === 'Escape')closeLightbox();
  if(e.key === 'ArrowLeft')navLightbox(-1);
  if(e.key === 'ArrowRight')navLightbox(1);
});

$('lightbox').addEventListener('click', e=>{ if(e.target.id === 'lightbox')closeLightbox() });

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
              <div class="video-preview-meta">Seedance image-to-video · ${ratio} · ${voice}</div>
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
    dynamic: 'Open with a strong visual hook in the first second. Use quicker pacing, one forward push, one side follow, and one decisive pose change while keeping outfit identity, anatomy, and lighting continuity stable. The result should feel social-ready, energetic, and clean enough for paid distribution.',
    texture: 'Lead with tactile detail before widening back out. Emphasize zipper pull motion, mesh texture, fabric stretch recovery, seam cleanliness, and support structure through close-up framing and soft specular light sweeps. Keep motion subtle, refined, and materially rich.',
    social: 'Build a lifestyle narrative around confidence and movement in the primary scenario. Use the opening frame as a mood anchor, transition through one expressive action beat and one emotional beat, then end on an aspirational stop frame. Keep the tone warm, believable, and shareable without losing commerce clarity.',
  };
  return `${base} ${opener} ${presetMap[kind] || presetMap.showcase}`.replace(/\s+/g, ' ').trim();
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
  btn.disabled = !(hasCandidates && current && hasPrompt);
  if(hint){
    if(!hasCandidates){
      hint.textContent = '图片至少生成 1 张后，才能选择首帧并提交视频。';
    }else if(!current){
      hint.textContent = `当前已返回 ${allCands.length}/${getRequestedCount()} 张候选图，请先选一张作为视频首帧。`;
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
        <div class="video-sub">用候选图 #${seq} 作为首帧 · ${duration}s · ${ratio} · Seedance image-to-video</div>
      </div>
      <span class="pill-status pill-running"><span class="dot"></span>生成中</span>
    </div>
    <div class="video-generating">
      <div class="gen-spinner"></div>
      <div class="gen-text" id="genText">提交 Seedance 任务...</div>
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
        showGenError(`Seedance 生成失败：${data.error || 'unknown'}`);
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
    if(genText)genText.textContent = '已提交给 Seedance，正在轮询结果...';
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
        <div class="video-sub">${duration} 秒 · ${ratio} · Seedance image-to-video · 刚刚生成</div>
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

async function poll(){
  if(pollFinished)return;
  try{
    const res = await fetch(`/api/status?task_id=${TASK_ID}`);
    if(!res.ok){
      throw new Error(`HTTP ${res.status}`);
    }
    const data = await res.json();
    if(data.error){
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


def normalize_choice(value, allowed_values, default_value):
    value = (value or "").strip()
    return value if value in allowed_values else default_value


def build_video_prompt_seed(name, category, primary_color, audience, selling_points, scenarios, video_motion):
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
    return (
        f"Create a 12-second fashion video for a {color_text} {category or 'sportswear'} product named {name or 'hero item'}. "
        f"Target audience: {audience_text}. Primary scene: {hero_scene}. Key selling points: {highlights}. "
        f"{motion_text} Preserve outfit identity, body proportions, and scene continuity. "
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
    return {
        "source": "intake_form_v2",
        "requested_count": 11,
        "image_goal": image_goal,
        "image_goal_label": image_goal_labels.get(image_goal, image_goal),
        "video_motion": video_motion,
        "video_motion_label": video_motion_labels.get(video_motion, video_motion),
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
                name, category, primary_color, target_audience, selling_points, scenarios, video_motion
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


def seedance_submit(image_url, text_prompt, duration=12, ratio="9:16"):
    """给 Seedance 投递 image-to-video 任务，返回 task_id"""
    if not ARK_API_KEY:
        return None, "视频功能未配置 ARK_API_KEY"
    full_prompt = f"{text_prompt} --resolution 720p --ratio {ratio} --duration {int(duration)} --fps 24 --watermark false"
    body = {
        "model": SEEDANCE_MODEL,
        "content": [
            {"type": "text", "text": full_prompt},
            {"type": "image_url", "image_url": {"url": image_url}},
        ],
    }
    req = urllib.request.Request(
        f"{ARK_BASE}/contents/generations/tasks",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {ARK_API_KEY}", "Content-Type": "application/json"},
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
        f"{ARK_BASE}/contents/generations/tasks/{seedance_task_id}",
        headers={"Authorization": f"Bearer {ARK_API_KEY}"},
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
        "SELECT id::text, oss_url, COALESCE(parameters_snapshot->>'shot_type','') AS shot, sequence_no "
        "FROM content_factory.candidates WHERE task_id = :'task_id'::uuid AND media_type = 'image' ORDER BY sequence_no;",
        {"task_id": task_id}
    )
    if rows_err:
        return {"status": "error", "error": f"数据库读取候选失败: {rows_err[:200]}"}
    cands = []
    for ln in rows:
        parts = ln.split("\t")
        if len(parts) >= 3:
            cands.append({
                "id": parts[0].strip()[:8],
                "url": parts[1].strip(),
                "shot": parts[2].strip(),
                "sequence_no": int(parts[3].strip()) if len(parts) > 3 and parts[3].strip().isdigit() else len(cands) + 1,
            })
    run_status, run_err = pg_vars(
        "SELECT status FROM content_factory.generation_runs WHERE task_id = :'task_id'::uuid ORDER BY started_at DESC LIMIT 1;",
        {"task_id": task_id}
    )
    if run_err:
        return {"status": "error", "error": f"数据库读取任务状态失败: {run_err[:200]}"}
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
    if "failed" in (task_status or "") or run_status == "failed":
        normalized_status = "failed"
    elif run_status == "succeeded":
        normalized_status = "succeeded"
    elif run_status == "partial":
        normalized_status = "partial"
    elif task_status in DONE_TASK_STATUSES or task_status in {"candidates_ready", "reviewing"}:
        normalized_status = "succeeded"
    elif requested_count > 0 and len(cands) >= requested_count:
        normalized_status = "succeeded"
    return {
        "status": normalized_status,
        "task_status": task_status,
        "run_status": run_status or "",
        "requested_count": requested_count,
        "parameters": parameters,
        "title": title,
        "product_name": product_name,
        "sku": sku,
        "candidates": cands,
    }


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


def render_task_detail_page_legacy(detail):
    candidate_total = int(detail.get("candidate_total") or 0)
    requested_count = int(detail.get("requested_count") or 0)
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
      <a href=\"""" + h(N8N_EDITOR_URL) + """\" class="btn btn-secondary">看 N8N 画布</a>
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
            html = FORM_HTML.replace("{n8n_editor_url}", N8N_EDITOR_URL) \
                            .replace("{video_status_text}", VIDEO_STATUS_TEXT) \
                            .replace("{video_status_class}", VIDEO_STATUS_CLASS) \
                            .replace("{recent_tasks_block}", render_home_recent_tasks())
            self._send(200, html)
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
                                  .replace("{n8n_editor_url}", N8N_EDITOR_URL) \
                                  .replace("{error_block}", f'<div class="err-card"><div class="err-title">任务不存在或已被删除</div><div class="err-msg">当前 task_id 为 {h(tid)}，数据库中已经没有这条任务记录。</div><div class="err-help">这不是图片生成慢，而是结果页正在查看一个失效任务。请返回首页重新提交，或去历史任务页确认是否被删除。</div></div>') \
                                  .replace("{progress_block}", "") \
                                  .replace("{poll_script}", "")
                self._send(404, html); return
            has_video = tid.startswith("55555555-5555")
            video_block = VIDEO_HAS if has_video else VIDEO_EMPTY
            html = RESULT_HTML.replace("{title}", "候选审核") \
                              .replace("{task_id_short}", tid[:8]) \
                              .replace("{task_id}", tid) \
                              .replace("{n8n_editor_url}", N8N_EDITOR_URL) \
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
        elif path == "/health":
            db_ok = False
            db_err = ""
            _, db_err = pg_vars("SELECT 1;")
            db_ok = not db_err
            health = {
                "status": "ok" if db_ok else "degraded",
                "host": HOST,
                "port": PORT,
                "postgres_ok": db_ok,
                "postgres_error": db_err[:160],
                "ark_configured": bool(ARK_API_KEY),
                "n8n_trigger": N8N_TRIGGER,
                "status_api_shape_version": 2,
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
            if not ARK_API_KEY:
                self._send(400, json.dumps({"error":"视频功能未配置 ARK_API_KEY"}, ensure_ascii=False), "application/json; charset=utf-8"); return
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
            sd_tid, err = seedance_submit(img_url, prompt, duration=duration, ratio=ratio)
            if err:
                self._send(500, json.dumps({"error":err}), "application/json"); return
            self._send(200, json.dumps({"seedance_task_id": sd_tid, "image_url": img_url}, ensure_ascii=False), "application/json; charset=utf-8")
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
                              .replace("{n8n_editor_url}", N8N_EDITOR_URL) \
                              .replace("{error_block}", f'<div class="err-card"><div class="err-title">录入失败</div><div class="err-msg">{h(err)}</div></div>') \
                              .replace("{progress_block}", "") \
                              .replace("{poll_script}", "")
            self._send(500, html); return

        code, body = trigger_n8n(tid)
        if code >= 400:
            html = RESULT_HTML.replace("{title}", "N8N 触发失败") \
                              .replace("{task_id_short}", tid[:8]) \
                              .replace("{task_id}", tid) \
                              .replace("{n8n_editor_url}", N8N_EDITOR_URL) \
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
    HTTPServer((HOST, PORT), Handler).serve_forever()
