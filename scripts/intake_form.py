"""
内容工厂 v3 · SaaS 级 UI（演示用）
访问 http://localhost:5001
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.request, urllib.parse, urllib.error
import subprocess
import sys

import os, mimetypes
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(errors="replace")

PORT = 5001
PG_CONTAINER = "cf-postgres-local"
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
N8N_BASE = (_env.get("N8N_BASE") or os.environ.get("N8N_BASE", "http://localhost:5678")).rstrip("/")
N8N_TRIGGER = f"{N8N_BASE}/webhook/trigger/image"
N8N_EDITOR_URL = (_env.get("N8N_EDITOR_URL") or os.environ.get("N8N_EDITOR_URL") or f"{N8N_BASE}/home/workflows")
ARK_API_KEY = _env.get("ARK_API_KEY") or os.environ.get("ARK_API_KEY", "")
ARK_BASE = "https://ark.cn-beijing.volces.com/api/v3"
SEEDANCE_MODEL = "doubao-seedance-1-0-pro-250528"

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
  <div class="page-sub">填好下面字段，系统自动跑卖点拆解 → 11 张商品图 + 场景图，平均 2-3 分钟。</div>
  <div class="steps">
    <div class="step active"><span class="step-num">1</span>录入</div>
    <span class="step-arr">→</span>
    <div class="step"><span class="step-num">2</span>生成</div>
    <span class="step-arr">→</span>
    <div class="step"><span class="step-num">3</span>审核</div>
    <span class="step-arr">→</span>
    <div class="step"><span class="step-num">4</span>归档</div>
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

  <div class="submit-bar">
    <div class="submit-meta">提交后跳转到生成进度页 · 全程可观察 N8N 流程</div>
    <button type="submit" class="btn btn-primary">
      开始生成
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14M13 5l7 7-7 7"/></svg>
    </button>
  </div>
</div>

</form>

<aside class="aside">
  <div class="aside-card">
    <div class="aside-title">📊 单 SKU 产能</div>
    <div class="metric"><span class="metric-label">候选数量</span><span class="metric-value">11 张</span></div>
    <div class="metric"><span class="metric-label">耗时</span><span class="metric-value">~2.5 min</span></div>
    <div class="metric"><span class="metric-label">单图成本</span><span class="metric-value">¥0.30</span></div>
    <div class="metric"><span class="metric-label">总成本</span><span class="metric-value">¥3.30</span></div>
  </div>

  <div class="aside-card">
    <div class="tip-icon">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
    </div>
    <div class="tip">
      <strong style="color:var(--slate-900)">小技巧</strong><br>
      卖点写得越具体（如"前拉链穿脱"而不是"方便"），生成图越能突出特征。
    </div>
  </div>

  <div class="aside-card">
    <div class="aside-title">🔗 关联视图</div>
    <a href="{n8n_editor_url}" target="_blank" style="display:block;padding:6px 0;font-size:12px;color:var(--indigo)">→ N8N 流程画布</a>
    <a href="/list" target="_blank" style="display:block;padding:6px 0;font-size:12px;color:var(--indigo)">→ 历史候选库</a>
  </div>
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
  color:#fff;border-radius:14px;padding:24px 28px;margin-bottom:20px;
  position:relative;overflow:hidden;
}
.video-showcase::before{
  content:"";position:absolute;top:-80px;right:-80px;width:300px;height:300px;
  background:radial-gradient(circle,rgba(236,72,153,.3) 0%,transparent 70%);border-radius:50%;
}
.video-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;position:relative;z-index:1}
.video-title{font-size:15px;font-weight:600;margin-bottom:4px}
.video-sub{font-size:12px;color:var(--slate-400)}
.video-wrap{
  position:relative;z-index:1;
  background:#000;border-radius:10px;overflow:hidden;
  display:flex;align-items:center;justify-content:center;
  max-width:280px;margin:0 auto;
  aspect-ratio:9/16;
  box-shadow:0 20px 40px rgba(0,0,0,.4);
}
.video-wrap video{width:100%;height:100%;object-fit:cover}
.video-controls{
  position:absolute;bottom:8px;left:8px;right:8px;
  display:flex;justify-content:space-between;align-items:center;
  background:linear-gradient(to top,rgba(0,0,0,.85),transparent);
  padding:20px 12px 8px;
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
  <a href="{n8n_editor_url}" target="_blank" class="btn btn-secondary">
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
      <div class="video-sub">同一模特、同一服装、同一场景 · 12 秒 · Seedance 2.0 image-to-video</div>
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
      <div class="video-sub">候选图审核通过后，挑任意一张作为视频首帧 · Seedance 2.0 image-to-video · 单条约 90-180 秒</div>
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
    <button class="btn btn-primary vc-submit" onclick="genVideoMock()" id="genVideoBtn">
      🎬 提交生成视频成片
    </button>
    <div class="vc-cost">预计耗时 ~90 秒 · 成本约 ¥12（Seedance 1 元/秒）</div>
  </div>
</div>
"""


PROGRESS_BLOCK = """
<div class="progress-card">
  <div class="progress-top">
    <div>
      <div class="progress-num"><span id="count">0</span><span class="total"> / 11</span><span class="label">候选已生成</span></div>
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
    <div class="story-label">选第 7 张当视频首帧</div>
    <div class="story-desc"><a href="#slot-card-7" onclick="highlightSeven(event)">瑜伽馆场景 ↓</a></div>
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
    grid.innerHTML='<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--slate-400);font-size:13px">该分类下暂无候选</div>';
    return;
  }
  grid.innerHTML=filtered.map((c,i)=>imgCardHTML(c,allCands.indexOf(c))).join('');
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
        <div class="video-sub">用候选图 #${seq} 作为首帧 · ${duration}s · ${ratio} · Seedance 2.0</div>
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
        <div class="video-sub">${duration} 秒 · ${ratio} · Seedance 2.0 image-to-video · 刚刚生成</div>
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
  try{
    const res=await fetch(`/api/status?task_id=${TASK_ID}`);
    const data=await res.json();
    allCands=data.candidates||[];
    const status=data.status||'running';

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

    if(status==='succeeded'){
      statusPill.classList.replace('pill-running','pill-success');
      statusText.textContent='生成完成';
      actionBar.classList.add('visible');
      $('actionBar').querySelector('.action-summary').innerHTML=
        `<strong>${n} 张候选</strong>已生成 · 总耗时 ${Math.round(elapsedSec)}s · 总花费 ¥${(n*0.30).toFixed(2)}`;
    } else if(status==='failed'){
      statusPill.classList.replace('pill-running','pill-failed');
      statusText.textContent='失败';
    }

    rerender();

    if(status==='succeeded'||status==='failed')return;
  }catch(e){console.error(e)}
  setTimeout(poll,2000);
}

setInterval(()=>{
  const sec=Math.floor((Date.now()-t0)/1000);
  const m=Math.floor(sec/60),s=sec%60;
  elapsedEl.textContent=m>0?`${m}m ${s}s`:`${s}s`;
},1000);

poll();
</script>
"""


# ============================================================================
#  Backend logic
# ============================================================================
def pg(sql):
    r = subprocess.run(
        ["docker","exec",PG_CONTAINER,"psql","-U","postgres","-d","content_factory","-q","-tAc",sql],
        capture_output=True, text=True, encoding="utf-8")
    stdout = (r.stdout or "").strip()
    lines = [ln for ln in stdout.split("\n")
             if ln and not ln.startswith(("UPDATE ","INSERT ","DELETE ","SELECT "))]
    return (lines[0].strip() if lines else ""), (r.stderr or "").strip()


def pg_rows(sql):
    r = subprocess.run(
        ["docker","exec",PG_CONTAINER,"psql","-U","postgres","-d","content_factory","-q","-tAc",sql],
        capture_output=True, text=True, encoding="utf-8")
    stdout = (r.stdout or "").strip()
    return [ln for ln in stdout.split("\n") if ln and "|" in ln], (r.stderr or "").strip()


def upsert_product_and_task(form):
    """每次提交：upsert product + 新建 task（保留历史）"""
    sku = form.get("sku",["YN-BRA-001"])[0]
    name = form.get("name",[""])[0].replace("'","''")
    category = form.get("category",[""])[0].replace("'","''")
    selling_points = [s.strip() for s in form.get("selling_points",[""])[0].split("\n") if s.strip()]
    primary_color = form.get("primary_color",[""])[0].replace("'","''")
    target_audience = form.get("target_audience",[""])[0].replace("'","''")
    scenarios = [s.strip() for s in form.get("scenarios",[""])[0].split("\n") if s.strip()]

    sp_pg = "ARRAY[" + ",".join("'"+p.replace("'","''")+"'" for p in selling_points) + "]"
    sc_pg = "ARRAY[" + ",".join("'"+p.replace("'","''")+"'" for p in scenarios) + "]" if scenarios else "ARRAY[]::text[]"

    # 1. 拿 tenant + style_template（用第一个，简化）
    tenant_id, _ = pg("SELECT id FROM content_factory.tenants LIMIT 1;")
    style_id, _ = pg("SELECT id FROM content_factory.style_templates LIMIT 1;")
    if not tenant_id: return None, "没有 tenant，schema seed 缺失"

    style_clause = "NULL" if not style_id else "'" + style_id + "'::uuid"
    # 2. UPSERT product（按 sku 更新，没有则新建）
    upsert_sql = (
        f"INSERT INTO content_factory.products "
        f"(tenant_id, sku, name, category, selling_points, target_audience, use_scenarios, "
        f"primary_color, reference_image_urls, style_template_id) "
        f"VALUES ('{tenant_id}'::uuid, '{sku}', '{name}', '{category}', {sp_pg}, "
        f"'{target_audience}', {sc_pg}, '{primary_color}', ARRAY[]::text[], "
        f"{style_clause}) "
        f"ON CONFLICT (tenant_id, sku) DO UPDATE SET "
        f"name=EXCLUDED.name, category=EXCLUDED.category, selling_points=EXCLUDED.selling_points, "
        f"target_audience=EXCLUDED.target_audience, use_scenarios=EXCLUDED.use_scenarios, "
        f"primary_color=EXCLUDED.primary_color, updated_at=now() "
        f"RETURNING id;"
    )
    out, err = pg(upsert_sql)
    if err and "ERROR" in err: return None, f"PG UPSERT: {err[:300]}"
    if not out: return None, f"product upsert 失败"
    pid = out

    # 3. **新建** task（不复用旧的）
    task_title = name.replace("'", "''")[:60] + " - " + sku
    new_task_sql = (
        f"INSERT INTO content_factory.tasks "
        f"(tenant_id, product_id, pipeline, status, title, requested_count, parameters) "
        f"VALUES ('{tenant_id}'::uuid, '{pid}'::uuid, 'image', 'pending', '{task_title}', 11, '{{}}'::jsonb) "
        f"RETURNING id;"
    )
    tid, err = pg(new_task_sql)
    if err and "ERROR" in err: return None, f"PG task INSERT: {err[:300]}"
    if not tid: return None, "task 创建失败"
    return tid, None


def trigger_n8n(task_id):
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
    out, _ = pg(
        f"SELECT oss_url FROM content_factory.candidates "
        f"WHERE task_id='{task_id}'::uuid AND sequence_no={int(seq)} LIMIT 1;"
    )
    return out


def seedance_submit(image_url, text_prompt, duration=12, ratio="9:16"):
    """给 Seedance 投递 image-to-video 任务，返回 task_id"""
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
        return {"status": "succeeded", "video_url": url}
    if status == "failed":
        return {"status": "failed", "error": str(d.get("error", d))[:300]}
    return {"status": status or "running"}


def get_status(task_id):
    rows, _ = pg_rows(
        f"SELECT id::text, oss_url, COALESCE(parameters_snapshot->>'shot_type','') AS shot, sequence_no "
        f"FROM content_factory.candidates WHERE task_id='{task_id}'::uuid ORDER BY sequence_no;"
    )
    cands = []
    for ln in rows:
        parts = ln.split("|")
        if len(parts) >= 3:
            cands.append({"id":parts[0].strip()[:8],"url":parts[1].strip(),"shot":parts[2].strip()})
    run_status, _ = pg(
        f"SELECT status FROM content_factory.generation_runs "
        f"WHERE task_id='{task_id}'::uuid ORDER BY started_at DESC LIMIT 1;"
    )
    return {"status": run_status or "running", "candidates": cands}


# ============================================================================
#  HTTP handler
# ============================================================================
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ct="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode("utf-8") if isinstance(body, str) else body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self._send(200, FORM_HTML.replace("{n8n_editor_url}", N8N_EDITOR_URL))
        elif path == "/result":
            qs = urllib.parse.urlparse(self.path).query
            tid = (urllib.parse.parse_qs(qs).get("task_id") or [""])[0]
            if not tid: self._send(400, "missing task_id"); return
            # 只有"演示样品"task（55555555-...）有真实预生成视频；其他任务显示空状态 + 模拟生成 CTA
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
            data = get_status(tid) if tid else {"error":"missing task_id"}
            self._send(200, json.dumps(data, ensure_ascii=False), "application/json; charset=utf-8")
        elif path == "/api/gen-video-status":
            qs = urllib.parse.urlparse(self.path).query
            sid = (urllib.parse.parse_qs(qs).get("id") or [""])[0]
            data = seedance_poll(sid) if sid else {"error":"missing id"}
            self._send(200, json.dumps(data, ensure_ascii=False), "application/json; charset=utf-8")
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
                "(SELECT COUNT(*) FROM content_factory.candidates WHERE task_id=t.id), "
                "(SELECT oss_url FROM content_factory.candidates WHERE task_id=t.id ORDER BY sequence_no LIMIT 1) "
                "FROM content_factory.tasks t JOIN content_factory.products p ON p.id=t.product_id "
                "WHERE t.pipeline='image' ORDER BY t.created_at DESC LIMIT 100;"
            )
            cards_html = ""
            for r in rows:
                p = r.split("|")
                if len(p) >= 8:
                    tid, sku, name, cat, status, created, cnt, thumb = [x.strip() for x in p[:8]]
                    cnt = int(cnt) if cnt.isdigit() else 0
                    pct = min(int(cnt*100/11), 100)
                    pill = ('<span class="pill-status pill-success"><span class="dot"></span>已完成</span>' if status in ('approved','archived','delivered') or cnt>=11
                            else '<span class="pill-status pill-running"><span class="dot"></span>生成中</span>' if status in ('analyzing','prompting','generating','reviewing','candidates_ready')
                            else '<span class="pill-status pill-failed"><span class="dot"></span>失败</span>' if 'failed' in status
                            else f'<span class="pill-status" style="background:var(--slate-100);color:var(--slate-600)"><span class="dot"></span>{status}</span>')
                    thumb_html = f'<img src="{thumb}" alt="" />' if thumb and thumb.startswith('http') else '<div class="thumb-empty">尚未生成</div>'
                    cards_html += f'''
<a class="hist-card" href="/result?task_id={tid}">
  <div class="hist-thumb">{thumb_html}</div>
  <div class="hist-body">
    <div class="hist-row1">
      <span class="hist-sku">{sku}</span>
      {pill}
    </div>
    <div class="hist-name">{name}</div>
    <div class="hist-meta">
      <span>{cat}</span><span>·</span>
      <span>{cnt}/11 张</span><span>·</span>
      <span>{created[:16]}</span>
    </div>
    <div class="hist-bar"><div class="hist-bar-fill" style="width:{pct}%"></div></div>
  </div>
</a>'''
            empty_html = '<div class="empty"><div class="empty-icon">📭</div><div>暂无任务历史</div><a href="/" class="btn btn-primary" style="margin-top:14px">+ 录入第一个产品</a></div>' if not rows else ''

            html = """<!DOCTYPE html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>历史任务 · ContentFactory</title>
<style>""" + COMMON_CSS + """
.shell{max-width:1280px;margin:0 auto;padding:0 24px}
.page-header{padding:32px 0 24px;display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap}
.page-title{font-size:24px;font-weight:700;letter-spacing:-.02em;margin-bottom:4px}
.page-sub{font-size:13px;color:var(--slate-500)}

.hist-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:14px;padding-bottom:60px}
.hist-card{
  background:#fff;border:1px solid var(--slate-200);border-radius:12px;
  overflow:hidden;display:flex;flex-direction:column;
  transition:all .2s var(--ease);
  box-shadow:var(--shadow-sm);
}
.hist-card:hover{transform:translateY(-2px);box-shadow:var(--shadow-lg);border-color:var(--indigo)}
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

.empty{text-align:center;padding:80px 20px;color:var(--slate-500)}
.empty-icon{font-size:48px;margin-bottom:14px}
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
      <div class="page-sub">点任意卡片查看完整候选 + 视频成片 · 共 """ + str(len(rows)) + """ 个任务</div>
    </div>
  </header>
  """ + empty_html + """
  <div class="hist-grid">""" + cards_html + """</div>
</div>

</body></html>"""
            self._send(200, html)
        else:
            self._send(404, "not found")

    def do_POST(self):
        if self.path == "/api/gen-video":
            length = int(self.headers.get("Content-Length", 0))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception:
                self._send(400, json.dumps({"error":"bad json"}), "application/json"); return
            tid = payload.get("task_id", "")
            seq = int(payload.get("seq") or 7)
            prompt = payload.get("prompt") or ""
            duration = int(payload.get("duration") or 12)
            ratio = payload.get("ratio") or "9:16"
            img_url = get_candidate_url(tid, seq)
            if not img_url:
                self._send(404, json.dumps({"error":f"候选 #{seq} 未找到，可能还没生成"}), "application/json"); return
            if not prompt.strip():
                self._send(400, json.dumps({"error":"prompt 不能为空"}), "application/json"); return
            sd_tid, err = seedance_submit(img_url, prompt, duration=duration, ratio=ratio)
            if err:
                self._send(500, json.dumps({"error":err}), "application/json"); return
            self._send(200, json.dumps({"seedance_task_id": sd_tid, "image_url": img_url}, ensure_ascii=False), "application/json; charset=utf-8")
            return

        if self.path != "/submit":
            self._send(404, "not found"); return
        length = int(self.headers.get("Content-Length", 0))
        raw_bytes = self.rfile.read(length)

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
                              .replace("{error_block}", f'<div class="err-card"><div class="err-title">录入失败</div><div class="err-msg">{err}</div></div>') \
                              .replace("{progress_block}", "") \
                              .replace("{poll_script}", "")
            self._send(500, html); return

        code, body = trigger_n8n(tid)
        if code >= 400:
            html = RESULT_HTML.replace("{title}", "N8N 触发失败") \
                              .replace("{task_id_short}", tid[:8]) \
                              .replace("{task_id}", tid) \
                              .replace("{n8n_editor_url}", N8N_EDITOR_URL) \
                              .replace("{error_block}", f'<div class="err-card"><div class="err-title">N8N 触发失败</div><div class="err-msg">HTTP {code} - {body[:200]}</div></div>') \
                              .replace("{progress_block}", "") \
                              .replace("{poll_script}", "")
            self._send(500, html); return

        self.send_response(303)
        self.send_header("Location", f"/result?task_id={tid}")
        self.end_headers()

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    print(f"=== ContentFactory v3 · http://localhost:{PORT} ===")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
