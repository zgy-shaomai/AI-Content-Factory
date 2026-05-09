# Model Matrix

> 单一模型真源。文档、脚本、workflow 出现模型名冲突时，以本表为准。

## 1. Canonical Models

| Purpose | Provider | Canonical model id | Used by | Timeout | Fallback |
|---|---|---|---|---:|---|
| Image generation | Volcengine Ark | `doubao-seedream-4-0-250828` | image workflow, keyframes, fallback assets | 90s | pre-generated image seed |
| Video generation | Volcengine Ark | `doubao-seedance-1-0-pro-250528` | video workflow, form i2v | 20m polling cap | pre-generated mp4 |
| Copy / prompt generation | 5dock NewAPI | `claude-sonnet-4-5-20250929` | selling points, storyboard, prompt rewrite | 90s | cached prompt template |
| ASR | Volcengine ASR | `volc_auc_common` | subtitle extraction | 2m | storyboard subtitle fallback |

## 2. Credential Names

| Credential | n8n type | Source |
|---|---|---|
| `cred-pg-content-factory` | postgres | `deploy/.env*` |
| `cred-5dock-newapi` | httpHeaderAuth | `NEWAPI_KEY` |
| `cred-volcengine-ark` | httpHeaderAuth | `ARK_API_KEY` |
| `cred-volcengine-asr` | httpHeaderAuth | ASR token / app token |
| `cred-aliyun-oss-signer` | httpHeaderAuth | OSS signing service or temporary signed header |
| `cred-feishu-tenant-token` | httpHeaderAuth | Feishu tenant token |

## 3. Claim Guardrails

LLM 输出不得编造以下内容，除非客户素材或检测报告明确提供：

- 医疗、塑形、减脂、治疗效果。
- “跑跳不位移”“5 分钟蒸发”“适合 B-D 杯”等具体性能承诺。
- 绝对化措辞：最强、100%、永久、无风险。
- 未授权真人脸、竞品 Logo、第三方 IP。

所有画面文案和口播必须来自客户资料、审核意见或人工确认的卖点表。

## 4. Change Control

模型 ID、endpoint、base URL、超时或成本估算变更时，需要同时更新：

- `docs/model-matrix.md`
- `deploy/.env.example`
- `scripts/verify-apis.*`
- `n8n/*.json`
- `scripts/quality_gate.py` 规则（如有）

