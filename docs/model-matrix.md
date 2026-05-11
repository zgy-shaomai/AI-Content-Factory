# Model Matrix

> 单一模型真源。Provider Access Center 以“能力路由”为主，不再把业务流程绑死在 5dock 或火山上。

## 1. Capability Routes

| Capability | Canonical env | Default provider | Default model | API shape | Notes |
|---|---|---|---|---|---|
| Text LLM / agents | `LLM_*` | `5dock` | `claude-sonnet-4-5-20250929` | OpenAI-compatible `chat/completions` | 可换 OpenAI、DeepSeek、Qwen、Kimi、GLM、OpenRouter、LiteLLM / NewAPI |
| Shared media gateway | `MEDIA_*` | optional | n/a | Ark-compatible media adapter | 最短配置路径：图片和视频共用一个 key / endpoint |
| Image generation | `IMAGE_*` | `volcengine_ark` | `doubao-seedream-4-0-250828` | `images/generations` through adapter | 可单独覆盖 `MEDIA_*`；Runway、MiniMax、Kling、Veo 走媒体网关 adapter |
| Video generation | `VIDEO_*` | `volcengine_ark` | `doubao-seedance-1-0-pro-250528` | async video tasks through adapter | 可单独覆盖 `MEDIA_*`；轮询、错误码、URL 解析由 adapter 归一化 |
| ASR / subtitle | `ASR_*` | `volcengine` | `volc_auc_common` | Provider-specific | 可禁用；失败时使用 storyboard 字幕兜底 |

## 2. Env Contract

```env
PAC_PROFILE=cn_ecommerce_default

LLM_PROVIDER=5dock
LLM_API_KEY=
LLM_BASE_URL=https://5dock.com/v1
LLM_MODEL=claude-sonnet-4-5-20250929

MEDIA_API_KEY=
MEDIA_BASE_URL=

IMAGE_PROVIDER=volcengine_ark
IMAGE_API_KEY=
IMAGE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
IMAGE_MODEL=doubao-seedream-4-0-250828

VIDEO_PROVIDER=volcengine_ark
VIDEO_API_KEY=
VIDEO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
VIDEO_MODEL=doubao-seedance-1-0-pro-250528

ASR_PROVIDER=volcengine
ASR_API_KEY=
ASR_BASE_URL=https://openspeech.bytedance.com/api/v1/auc
ASR_MODEL=volc_auc_common
```

Legacy aliases are still read and synchronized:

| Legacy | New route |
|---|---|
| `NEWAPI_KEY` | `LLM_API_KEY` |
| `NEWAPI_BASE_URL` | `LLM_BASE_URL` |
| `ARK_API_KEY` | `IMAGE_API_KEY` / `VIDEO_API_KEY` |
| `ARK_ENDPOINT` | `IMAGE_BASE_URL` / `VIDEO_BASE_URL` |
| `ARK_IMAGE_MODEL` | `IMAGE_MODEL` |
| `ARK_VIDEO_MODEL` | `VIDEO_MODEL` |

## 3. Credential Names

| Credential | n8n type | Source |
|---|---|---|
| `cred-pg-content-factory` | postgres | `deploy/.env*` |
| `cred-llm-provider` | httpHeaderAuth | `LLM_API_KEY` |
| `cred-image-provider` | httpHeaderAuth | `IMAGE_API_KEY` fallback `MEDIA_API_KEY` |
| `cred-video-provider` | httpHeaderAuth | `VIDEO_API_KEY` fallback `MEDIA_API_KEY` |
| `cred-volcengine-asr` | httpHeaderAuth | `ASR_API_KEY` |
| `cred-aliyun-oss-signer` | httpHeaderAuth | OSS signing service or temporary signed header |
| `cred-feishu-tenant-token` | httpHeaderAuth | Feishu tenant token |

## 4. Agent Split

| Agent | Responsibility | Route |
|---|---|---|
| Intake Normalizer | Normalize raw SKU fields into product JSON | `LLM_*` |
| Product Analyst | Extract locked facts, soft inferences, forbidden inventions | `LLM_*` |
| Claim Guard | Check overclaim, trademark, medical/absolute wording | `LLM_*` |
| Image Prompt Builder | Build product / lifestyle / detail prompts | `LLM_*` |
| Image Generator | Generate and regenerate candidate images | `IMAGE_*` |
| Image QC | Score product accuracy, consistency, realism, compliance | `LLM_*` multimodal route when available |
| Storyboard Agent | Build scene JSON for short videos | `LLM_*` |
| Keyframe Agent | Convert scenes into first-frame image prompts | `LLM_*` + `IMAGE_*` |
| Video Prompt Agent | Convert scenes into video-provider prompt format | `LLM_*` |
| Video Generator | Submit and poll image-to-video tasks | `VIDEO_*` |
| Subtitle Agent | ASR to SRT, fallback to storyboard captions | `ASR_*` |
| Router | Select provider based on profile, quota, failures, cost | Rule-based, not LLM |

## 5. Media Adapter Contract

业务流程只依赖这三个能力，不直接依赖某一家模型的原始 API：

| Adapter method | Request contract | Response contract |
|---|---|---|
| `image_generation` | `model`, `prompt`, `negative_prompt`, `size`, `seed`, `reference_images` | `{ id, image_url, provider, model, raw }` |
| `image_to_video_submit` | `model`, `prompt`, `first_frame_url`, `last_frame_url`, `duration`, `ratio` | `{ task_id, provider, model, raw }` |
| `video_poll` | `task_id` | `{ status, video_url, error_code, error_message, raw }` |

Ark / Seedream / Seedance 是默认 adapter。Runway、Kling、MiniMax、Veo、ComfyUI 或企业内部网关都应先映射到以上 contract，再接入 N8N 和本地 UI。

## 6. Claim Guardrails

LLM 输出不得编造以下内容，除非客户素材或检测报告明确提供：

- 医疗、塑形、减脂、治疗效果。
- “跑跳不位移”“5 分钟蒸发”“适合 B-D 杯”等具体性能承诺。
- 绝对化措辞：最强、100%、永久、无风险。
- 未授权真人脸、竞品 Logo、第三方 IP。

所有画面文案和口播必须来自客户资料、审核意见或人工确认的卖点表。
