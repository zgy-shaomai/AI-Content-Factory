# Prompt 02 · 卖点提炼（5-7 条 + 视觉表达建议）

## 用途说明

把客户给的、可能掺杂功能 / 工艺 / 营销话术混在一起的卖点列表，蒸馏成 5-7 条**面向视觉表达**的核心卖点。每条卖点必须自带"视觉表达建议"——告诉下游 Prompt 03/04 这一条该怎么"拍"出来（拍什么镜头、镜头里要有什么细节）。这是图片链路从"产品语言"切换到"画面语言"的关键节点。模型走 5dock NewAPI `claude-sonnet-4-6`，temperature 0.4，输出严格 JSON。

## System Prompt

```
You are a senior creative director for an apparel e-commerce content factory.
You receive structured product attributes (24-field JSON from upstream) plus original Chinese selling-point copy.
Your job is to distill them into 5-7 ranked selling points, each with a concrete VISUAL EXECUTION HINT that tells a downstream image-prompt writer exactly what kind of shot best showcases that point.

Rules:
1. Output 5 to 7 items, sorted by importance (rank 1 = most important).
2. Each item has: rank, text_cn (≤ 18 chars, sharp marketing copy), text_en (English version for prompt injection), visual_hint (English, what shot demonstrates this point — be specific about subject, action, framing, lighting cue).
3. visual_hint MUST be actionable: "close-up of front zipper being half-pulled, fingers visible, soft natural light from left" — not "show the zipper".
4. If the original brief has redundant points (e.g. "speed dry" and "moisture wicking" both about sweat), merge them.
5. NEVER invent product features that aren't in the input.
6. The 5-7 points must collectively cover: at least one fabric/material point, at least one functional/wearability point, at least one fit/silhouette point. Style/scenario points are optional but encouraged.
7. Output strict JSON only.
```

## User Prompt（YN-BRA-001 实战版）

```
Distill the selling points for SKU YN-BRA-001 (Black High-Stretch Quick-Dry Sports Bra, Front Zip).

=== UPSTREAM ATTRIBUTES (from prompt 01) ===
{
  "category": "sports_bra",
  "sub_category": "zip_front",
  "primary_color": "matte black / #0a0a0a",
  "material_main": "78% nylon, 22% spandex blend, sweat-wicking",
  "material_secondary": "breathable mesh inserts on back and side underarm panels",
  "stretch_level": "four_way",
  "support_level": "high",
  "closure_type": "front_zip",
  "padding": "removable_cups",
  "logo_present": true,
  "logo_placement": "left chest panel, ~6cm below collarbone, ~3cm tonal print",
  "intended_use_scenes": ["yoga_studio", "running", "gym", "outdoor"],
  "target_audience": "active women aged 25-40, mid-to-high intensity training"
}

=== ORIGINAL CHINESE COPY ===
- 透气网眼面料（背部和侧腋下）
- 前置金属拉链穿脱方便
- 高弹力支撑，适合中高强度运动
- 速干面料，汗后 8 分钟挥发
- 一体织造无侧缝
- 哑光黑色，简约百搭

=== STYLE TEMPLATE CONTEXT ===
brand_palette: matte black, no warm cast
mood: calm, professional, energetic but not aggressive
target audience: 25-40 active women

=== EXPECTED OUTPUT ===
JSON object with key "selling_points", array of 5-7 entries as specified in system prompt.
```

## 期望输出格式（JSON Schema）

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["selling_points"],
  "properties": {
    "selling_points": {
      "type": "array",
      "minItems": 5,
      "maxItems": 7,
      "items": {
        "type": "object",
        "required": ["rank", "text_cn", "text_en", "visual_hint", "category"],
        "properties": {
          "rank": { "type": "integer", "minimum": 1, "maximum": 7 },
          "text_cn": { "type": "string", "maxLength": 18 },
          "text_en": { "type": "string", "maxLength": 80 },
          "visual_hint": { "type": "string", "maxLength": 240 },
          "category": {
            "type": "string",
            "enum": ["fabric", "function", "fit", "style", "scenario"]
          }
        }
      }
    }
  }
}
```

## Few-shot 示例

### 示例 1（YN-BRA-001 期望输出）

```json
{
  "selling_points": [
    {
      "rank": 1,
      "text_cn": "前置拉链 一秒穿脱",
      "text_en": "Front YKK-style zipper for effortless on-and-off",
      "visual_hint": "Three-quarter front shot of model, hand grasping the metal zipper pull at chest level mid-motion, zipper half-open, fingertips slightly bent, soft daylight rim-lighting the metallic zipper teeth",
      "category": "function"
    },
    {
      "rank": 2,
      "text_cn": "高弹力 强支撑",
      "text_en": "Four-way stretch with high-impact support",
      "visual_hint": "Side profile of model in active yoga pose (warrior II), bra contour following the body without bunching, no visible band rolling at the underbust",
      "category": "fit"
    },
    {
      "rank": 3,
      "text_cn": "网眼透气 速干不闷",
      "text_en": "Breathable mesh panels with rapid sweat-wicking",
      "visual_hint": "Macro back-detail shot showing the mesh inserts on the back and side underarm; light passing through the mesh weave; tonal black-on-black texture clearly visible",
      "category": "fabric"
    },
    {
      "rank": 4,
      "text_cn": "中高强度运动适配",
      "text_en": "Designed for mid-to-high-intensity training",
      "visual_hint": "Action shot of model running in soft morning light, mid-stride, bra holding shape with no jiggle, slight motion blur on hair and arms only",
      "category": "scenario"
    },
    {
      "rank": 5,
      "text_cn": "一体织造 无侧缝",
      "text_en": "Seamless one-piece knit, no side seam",
      "visual_hint": "Close-up of the side body where the seam would normally be, smooth fabric continuity, finger pinching gently to show no ridge",
      "category": "fabric"
    },
    {
      "rank": 6,
      "text_cn": "哑光黑 极简百搭",
      "text_en": "Matte black, minimalist, easy to layer",
      "visual_hint": "Studio shot on neutral light gray seamless backdrop, model in matte black bra paired with high-waist black leggings, minimalist styling, soft butterfly lighting",
      "category": "style"
    }
  ]
}
```

### 示例 2（瑜伽裤参考输出，6 条）

```json
{
  "selling_points": [
    {
      "rank": 1,
      "text_cn": "黄油手感 不起球",
      "text_en": "Buttery-soft handle, anti-pilling",
      "visual_hint": "Macro detail of fabric being lightly stroked by a hand, surface showing smooth uniform fibers, soft directional light",
      "category": "fabric"
    },
    {
      "rank": 2,
      "text_cn": "高腰收腹 显瘦显腿长",
      "text_en": "High-waist tummy control, leg-lengthening fit",
      "visual_hint": "Side full-body shot of model in profile, hand at hip, waistband sitting high above navel, smooth front panel without rolling",
      "category": "fit"
    },
    {
      "rank": 3,
      "text_cn": "四面弹 蹲起自如",
      "text_en": "Four-way stretch, full mobility for deep squats",
      "visual_hint": "Model in deep squat with hands on knees, side angle, no fabric pull lines at the back of the knee or thigh",
      "category": "function"
    },
    {
      "rank": 4,
      "text_cn": "暗袋设计 跑步装钥匙",
      "text_en": "Hidden waistband pocket fits a key or card",
      "visual_hint": "Close-up rear-waist shot, model's hand sliding a key into the hidden inner pocket, fabric bulge minimal",
      "category": "function"
    },
    {
      "rank": 5,
      "text_cn": "瑜伽到日常 一裤多场",
      "text_en": "From yoga studio to street, all-day versatility",
      "visual_hint": "Two side-by-side scene shots: yoga studio with model holding pose, then a coffee-shop street scene same model same outfit",
      "category": "scenario"
    },
    {
      "rank": 6,
      "text_cn": "深橄榄 高级耐看",
      "text_en": "Deep olive tone, refined and easy to style",
      "visual_hint": "Color-accurate flat-lay including swatch of fabric on wood table with morning light, neutral white-balance reference card in corner",
      "category": "style"
    }
  ]
}
```

### 示例 3（运动 T 恤参考输出，5 条）

```json
{
  "selling_points": [
    {
      "rank": 1,
      "text_cn": "再生面料 环保速干",
      "text_en": "Recycled poly mesh, eco-friendly and quick-dry",
      "visual_hint": "Detail of fabric weave with light passing through, small recycled-material care tag visible at hem",
      "category": "fabric"
    },
    {
      "rank": 2,
      "text_cn": "凉感降温 越动越爽",
      "text_en": "Cooling feel that intensifies during movement",
      "visual_hint": "Action shot, model wiping forehead in motion, fabric showing no sweat-darkening patches",
      "category": "function"
    },
    {
      "rank": 3,
      "text_cn": "宽松剪裁 不勒身",
      "text_en": "Relaxed cut that drapes without clinging",
      "visual_hint": "Three-quarter shot of model with arms slightly raised, hem hanging cleanly mid-hip with natural drape",
      "category": "fit"
    },
    {
      "rank": 4,
      "text_cn": "圆领刺绣 小细节高级感",
      "text_en": "Embroidered logo on chest, refined detailing",
      "visual_hint": "Close-up of the round embroidered chest logo, threads catching light, fabric clearly visible behind",
      "category": "style"
    },
    {
      "rank": 5,
      "text_cn": "训练通勤都能穿",
      "text_en": "Goes from gym to commute without missing a beat",
      "visual_hint": "Composite-style shot: same model, same shirt, gym scene on left half, subway-platform scene on right half, matched lighting",
      "category": "scenario"
    }
  ]
}
```

## 调用示例（curl）

```bash
curl -X POST https://5dock.com/v1/chat/completions \
  -H "Authorization: Bearer $FIVEDOCK_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "temperature": 0.4,
    "max_tokens": 2500,
    "response_format": { "type": "json_object" },
    "messages": [
      { "role": "system", "content": "<SYSTEM PROMPT 见上文>" },
      { "role": "user", "content": "<USER PROMPT 见上文，attributes 字段从上一节点动态注入>" }
    ]
  }'
```
