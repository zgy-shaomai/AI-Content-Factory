# Prompt 03 · 商品图 Prompt 生成（6 个视角变体）

## 用途说明

把"24 字段属性 + 5-7 条卖点 + style_template"组装成 6 条**可直接喂给 Seedream 4.0** 的英文 prompt，对应 6 个商品图镜头：正面、侧面、背面、面料微距、拉链动作、左胸 logo 特写。每条 prompt 80-150 词，包含面料、光线、构图、镜头、风格关键词，以及参考图引用语法 `[reference: xxx, weight: 0.x]`。LLM 走 5dock NewAPI `claude-sonnet-4-6`，temperature 0.6，输出 JSON。

## System Prompt

```
You are a senior prompt engineer specialized in commerce-grade apparel image generation, writing prompts for Seedream 4.0 (Volcengine Ark, model doubao-seedream-4-0-250828).

Your output is an array of 6 prompt entries for studio/product-shot variants of one apparel SKU:
  shot_id ∈ {studio_front, studio_side, studio_back, fabric_macro, zipper_action, logo_closeup}

Each prompt must be 80–150 words English, dense with concrete cues, in this layout:
  [SUBJECT + POSE/ACTION] +
  [GARMENT DETAILS — color, fabric finish, fit, logo placement, closure] +
  [LIGHTING] + [COMPOSITION + LENS] + [BACKGROUND/SETTING] +
  [STYLE KEYWORDS] +
  [REFERENCE IMAGE TAGS in the form [reference: <id>, weight: 0.x]]

Hard constraints:
1. Inject brand_palette, model_descriptor, lighting from style_template VERBATIM where applicable.
2. Always include fabric language: "breathable mesh fabric", "sweat-wicking nylon-spandex blend", "subtle matte sheen on fabric", whichever apply.
3. If logo_present=true, every shot that shows the chest must say "preserve original tonal logo placement on left chest, ~6cm below collarbone, ~3cm wide". Do not let the model invent or move the logo.
4. Color discipline: say "matte black, neutral undertone, no color shift to navy or warm brown" — this is critical for sports apparel.
5. Reference image syntax: append [reference: model_ref_001, weight: 0.75] for any model shot, [reference: product_ref_001, weight: 0.85] for any garment shot. Both for shots showing both.
6. Output a JSON object with key "prompts", each entry having: shot_id, shot_type='product', en_prompt, negative_prompt, suggested_size, ref_image_ids, guidance_scale, seed_hint.
7. Negative prompt is shared across the 6 shots — output once at top level under "shared_negative_prompt".
8. Never include Chinese characters in the en_prompt.
```

## User Prompt（YN-BRA-001 实战版）

```
Generate 6 Seedream 4.0 product-shot prompts for SKU YN-BRA-001.

=== ATTRIBUTES ===
{
  "category": "sports_bra",
  "sub_category": "zip_front",
  "primary_color": "matte black / #0a0a0a",
  "color_undertone": "neutral",
  "material_main": "78% nylon, 22% spandex, sweat-wicking",
  "material_secondary": "breathable mesh inserts on back and side underarm",
  "fabric_finish": "matte",
  "stretch_level": "four_way",
  "silhouette": "compression_fit",
  "neckline": "scoop",
  "closure_type": "front_zip (matte-black metal pull)",
  "support_level": "high",
  "logo_present": true,
  "logo_placement": "left chest panel, ~6cm below collarbone, ~3cm wide tonal print"
}

=== TOP SELLING POINTS ===
1. Front zipper for effortless on-and-off
2. Four-way stretch with high-impact support
3. Breathable mesh panels with rapid sweat-wicking
4. Seamless one-piece knit, no side seam

=== STYLE TEMPLATE ===
brand_palette: matte black with subtle charcoal undertone, no warm color cast, no shift to navy
model_descriptor: East Asian woman, age 28, athletic build, height 168cm, shoulder-length straight black hair, natural makeup, slight tan, calm confident expression
lighting: soft natural daylight from large studio window, slight rim light from behind
composition: centered subject, rule of thirds for cropped shots
lens: 85mm equivalent, f/2.8, shallow depth of field for detail shots
mood: calm, professional, energetic but not aggressive

=== REFERENCE IMAGES AVAILABLE ===
- model_ref_001: prior approved frontal model shot for this SKU
- product_ref_001: customer flat-lay of the actual bra
- product_ref_002: customer back-detail showing mesh panel

=== OUTPUT ===
JSON object: { "shared_negative_prompt": "...", "prompts": [ ... 6 items ... ] }
```

## 期望输出格式（JSON Schema）

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["shared_negative_prompt", "prompts"],
  "properties": {
    "shared_negative_prompt": { "type": "string" },
    "prompts": {
      "type": "array",
      "minItems": 6,
      "maxItems": 6,
      "items": {
        "type": "object",
        "required": ["shot_id", "shot_type", "en_prompt", "suggested_size", "ref_image_ids", "guidance_scale", "seed_hint"],
        "properties": {
          "shot_id": {
            "type": "string",
            "enum": ["studio_front", "studio_side", "studio_back", "fabric_macro", "zipper_action", "logo_closeup"]
          },
          "shot_type": { "type": "string", "const": "product" },
          "en_prompt": { "type": "string", "minLength": 400 },
          "suggested_size": { "type": "string", "enum": ["2048x2048", "1536x2048", "2048x1536"] },
          "ref_image_ids": { "type": "array", "items": { "type": "string" }, "maxItems": 4 },
          "guidance_scale": { "type": "number", "minimum": 4.0, "maximum": 8.5 },
          "seed_hint": { "type": "integer" }
        }
      }
    }
  }
}
```

## Few-shot 示例（YN-BRA-001 期望输出 — 6 条 prompt 全文实战版）

```json
{
  "shared_negative_prompt": "low quality, blurry, deformed body, extra fingers, distorted logo, mismatched logo position, color shift to navy blue or warm brown, plastic-looking fabric, oversaturated, text artifacts, watermark, multiple people, face inconsistency, see-through fabric where not intended, visible bra straps misaligned, AI hands artifacts, harsh shadows, dramatic studio lighting",

  "prompts": [
    {
      "shot_id": "studio_front",
      "shot_type": "product",
      "en_prompt": "Front-facing studio portrait of an East Asian woman age 28, athletic build, 168cm, shoulder-length straight black hair, natural makeup, slight tan, calm confident expression, wearing a matte black high-stretch sports bra with a metal front zipper fully closed at the chest. The bra is a four-way stretch nylon-spandex compression-fit silhouette with a scoop neckline, breathable mesh panels visible at side underarm, seamless one-piece knit body, fabric showing a subtle matte sheen with no warm color cast. Preserve original tonal logo placement on left chest approximately 6cm below collarbone, around 3cm wide, same tonal black-on-black print. Soft natural daylight from large studio window camera-left, gentle rim light from behind. Centered composition, head and shoulders to mid-thigh framing, 85mm equivalent lens at f/2.8, shallow depth of field, clean light-gray seamless paper backdrop. Calm professional energetic mood, commerce-grade clarity. [reference: model_ref_001, weight: 0.78] [reference: product_ref_001, weight: 0.85]",
      "suggested_size": "1536x2048",
      "ref_image_ids": ["model_ref_001", "product_ref_001"],
      "guidance_scale": 7.0,
      "seed_hint": 884213
    },
    {
      "shot_id": "studio_side",
      "shot_type": "product",
      "en_prompt": "Side profile studio shot of the same East Asian woman age 28, athletic build, 168cm, shoulder-length straight black hair, natural makeup, calm confident expression, standing in a relaxed athletic posture with one arm slightly raised, wearing the matte black four-way stretch sports bra, front zipper closed. Side view emphasizes the compression-fit silhouette contour following the underbust band cleanly with no rolling or bunching, visible mesh panel at side underarm letting subtle highlight pass through. Matte black fabric with neutral undertone, no shift to navy or brown, subtle matte sheen. Seamless one-piece knit emphasized — no side seam visible. Preserve tonal logo on left chest just visible in profile angle. Soft natural daylight from camera-front-left, slight rim light from behind. 85mm lens at f/2.8, shallow depth of field, light-gray seamless backdrop. Centered subject, full torso framing. [reference: model_ref_001, weight: 0.75] [reference: product_ref_001, weight: 0.80]",
      "suggested_size": "1536x2048",
      "ref_image_ids": ["model_ref_001", "product_ref_001"],
      "guidance_scale": 7.0,
      "seed_hint": 884214
    },
    {
      "shot_id": "studio_back",
      "shot_type": "product",
      "en_prompt": "Back-view studio shot of the same East Asian woman age 28, athletic build, 168cm, shoulder-length straight black hair pulled slightly to one side, wearing the matte black sports bra. Camera focuses on the full back panel showing the wide breathable mesh insert running from the upper back down to between the shoulder blades, fabric weave clearly visible with light passing through the mesh weave revealing tonal black-on-black texture. Compression-fit straps lying flat across the upper back without twist. Seamless one-piece knit, no center back seam, no clasp. Matte finish, neutral black undertone, no warm color cast. Soft natural daylight from camera-left, slight rim light defining shoulder blade contours. 85mm lens at f/2.8, shallow depth of field on the model's hair, fabric in sharp focus. Light-gray seamless paper backdrop, centered subject. [reference: model_ref_001, weight: 0.72] [reference: product_ref_002, weight: 0.85]",
      "suggested_size": "1536x2048",
      "ref_image_ids": ["model_ref_001", "product_ref_002"],
      "guidance_scale": 7.2,
      "seed_hint": 884215
    },
    {
      "shot_id": "fabric_macro",
      "shot_type": "product",
      "en_prompt": "Macro close-up detail of the breathable mesh panel of the matte black sports bra, focal point on the side underarm mesh insert about 8cm wide. Fabric weave is sharply resolved showing the open hexagonal mesh structure with sweat-wicking nylon-spandex yarns clearly visible, subtle matte sheen on the threads, light passing through the holes hinting at the model's skin behind in soft blur. Color discipline: matte black with neutral undertone, charcoal where light catches, absolutely no shift to navy blue or warm brown. Soft directional natural daylight from upper-left grazing across the weave to reveal three-dimensional texture. 100mm macro lens equivalent at f/4, very shallow depth of field, focus stack feel. Composition fills 80 percent of frame, slight diagonal weave direction. Background fabric of the bra body visible at edges as out-of-focus matte black. [reference: product_ref_002, weight: 0.90]",
      "suggested_size": "2048x2048",
      "ref_image_ids": ["product_ref_002"],
      "guidance_scale": 6.5,
      "seed_hint": 884216
    },
    {
      "shot_id": "zipper_action",
      "shot_type": "product",
      "en_prompt": "Three-quarter front close-up of the same East Asian woman age 28, framing chest to lower face, mid-action of grasping the matte black metal front zipper pull and drawing it half-open. Fingers natural and slightly bent, pinky relaxed, fingernails short and unpainted, no AI hand distortion. The zipper is half-down at sternum height, exposing the inner placket and a hint of the matte black fabric underneath, metal teeth catching subtle light. Bra is matte black four-way stretch, compression-fit, scoop neckline, breathable mesh hint at upper chest. Preserve tonal logo on left chest. Soft natural daylight from camera-left rim-lighting the metallic zipper teeth and the fingertips. 85mm lens at f/2.5, shallow depth of field with face slightly soft, hand and zipper sharp. Light-gray seamless backdrop. Calm energetic mood. [reference: model_ref_001, weight: 0.70] [reference: product_ref_001, weight: 0.85]",
      "suggested_size": "2048x2048",
      "ref_image_ids": ["model_ref_001", "product_ref_001"],
      "guidance_scale": 6.8,
      "seed_hint": 884217
    },
    {
      "shot_id": "logo_closeup",
      "shot_type": "product",
      "en_prompt": "Tight macro close-up centered on the left chest panel of the matte black sports bra, framing only the logo area roughly 8cm by 8cm. Preserve original tonal logo placement, approximately 6cm below collarbone, around 3cm wide, tonal black-on-black print where the logo is a slightly deeper charcoal hue against matte black fabric. Logo edges crisp, no smearing, no replacement of brand mark. Surrounding fabric shows the seamless one-piece knit weave with sweat-wicking nylon-spandex blend, subtle matte sheen, neutral undertone, no warm color cast, no shift to navy. Skin partially visible at top edge of frame as soft out-of-focus tonal background. Soft natural daylight from camera-left grazing the logo print to reveal its slight raised texture. 100mm macro at f/4, very shallow depth of field. [reference: product_ref_001, weight: 0.92]",
      "suggested_size": "2048x2048",
      "ref_image_ids": ["product_ref_001"],
      "guidance_scale": 7.5,
      "seed_hint": 884218
    }
  ]
}
```

## Few-shot 示例 2（瑜伽裤参考片段，仅展示 studio_front）

```json
{
  "shot_id": "studio_front",
  "shot_type": "product",
  "en_prompt": "Front-facing studio shot of an East Asian woman age 26, lean build, 165cm, mid-length brown hair, soft makeup, calm focused expression, wearing deep olive high-waist full-length leggings with a buttery-soft hand feel, four-way stretch nylon-spandex compression silhouette, waistband sitting just above navel without rolling, smooth front panel without front rise creasing. Color is deep olive #4a5230 with warm undertone, no shift to khaki or brown, subtle matte finish. Preserve tonal heat-transfer logo on right thigh side seam approximately 12cm below hip, small reflective mark. Soft natural daylight from large studio window camera-left, gentle rim light. Full body framing from head to toe, centered composition, 85mm lens at f/3.2, light-gray seamless backdrop. Calm refined athletic mood. [reference: model_ref_002, weight: 0.78] [reference: product_ref_010, weight: 0.85]",
  "suggested_size": "1536x2048",
  "ref_image_ids": ["model_ref_002", "product_ref_010"],
  "guidance_scale": 7.0,
  "seed_hint": 552001
}
```

## Few-shot 示例 3（运动 T 恤参考片段，仅展示 fabric_macro）

```json
{
  "shot_id": "fabric_macro",
  "shot_type": "product",
  "en_prompt": "Macro close-up of the recycled polyester mesh weave of the stone-gray athletic t-shirt, focal area on the chest panel about 10cm wide. Fabric structure shows clean honeycomb-style mesh with cool-feel polyester yarns, subtle matte finish, no satin sheen. Color discipline: stone gray #b0b0a8 with cool undertone, no shift to beige or yellow. Soft directional natural daylight from upper-right grazing across the weave revealing three-dimensional honeycomb depth. 100mm macro lens at f/4, very shallow depth of field, weave fills 85 percent of frame, embroidered chest logo just visible at lower-left of frame as soft out-of-focus textured circle. Background body fabric out-of-focus stone gray. [reference: product_ref_021, weight: 0.90]",
  "suggested_size": "2048x2048",
  "ref_image_ids": ["product_ref_021"],
  "guidance_scale": 6.5,
  "seed_hint": 770044
}
```

## 调用示例（curl）

LLM-C 调用 5dock 把上面 user prompt 丢进去：

```bash
curl -X POST https://5dock.com/v1/chat/completions \
  -H "Authorization: Bearer $FIVEDOCK_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "temperature": 0.6,
    "max_tokens": 4500,
    "response_format": { "type": "json_object" },
    "messages": [
      { "role": "system", "content": "<SYSTEM PROMPT 见上文>" },
      { "role": "user", "content": "<USER PROMPT 见上文，attributes 与 selling_points 由上一节点动态注入>" }
    ]
  }'
```

LLM 输出后由 N8N 拆 6 条，每条调用 Seedream 4.0：

```bash
curl -X POST https://ark.cn-beijing.volces.com/api/v3/images/generations \
  -H "Authorization: Bearer $ARK_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-seedream-4-0-250828",
    "prompt": "<en_prompt 字段全文>",
    "image": [
      "https://yfn-content-factory.oss-cn-shanghai.aliyuncs.com/refs/YN-BRA-001/model_ref_001.jpg",
      "https://yfn-content-factory.oss-cn-shanghai.aliyuncs.com/refs/YN-BRA-001/product_ref_001.jpg"
    ],
    "size": "1536x2048",
    "seed": 884213,
    "guidance_scale": 7.0,
    "watermark": false,
    "response_format": "url",
    "negative_prompt": "<shared_negative_prompt 全文>"
  }'
```
