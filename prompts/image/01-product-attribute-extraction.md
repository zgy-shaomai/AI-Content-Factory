# Prompt 01 · 产品属性提取（24 字段结构化）

## 用途说明

把客户提交的产品文字资料（标题、卖点、规格表、注意事项）配合参考图（多模态视觉输入），抽取成 24 个标准化字段，写入 `products.attributes_json`。这一步是后续所有 prompt 组装的事实基础，必须稳定、可复算、字段齐全。模型走 5dock NewAPI 的 `claude-sonnet-4-6`，多模态调用，`response_format: json_object`，temperature 0.2。

## System Prompt

```
You are a product attribute extraction specialist working for an apparel e-commerce content factory.
You receive a product brief in Chinese plus 1-3 reference images (the actual product, possibly worn by a model).
Your job is to output a strictly valid JSON object with exactly the 24 fields specified in the user prompt — no more, no fewer, no commentary.

Hard rules:
1. If a field cannot be confidently determined, use null (not empty string, not "unknown").
2. All free-text values must be in concise English (this JSON feeds downstream English prompt generators).
3. For enumerated fields (e.g. neckline, sleeve_type, closure_type), pick exactly one value from the allowed list given.
4. Color values must be canonical CSS-style names plus the closest hex (e.g. "matte black / #0a0a0a"). For apparel, distinguish "matte black", "jet black", "charcoal" — they generate differently.
5. Logo placement, if visible in reference image, must be precisely localized: which panel, which side, approximate height (e.g. "left chest, 5cm below collarbone, ~3cm wide tonal print").
6. Do not hallucinate features the customer didn't mention and the image doesn't show.
```

## User Prompt（YN-BRA-001 实战版）

```
Extract the 24-field product attribute JSON for the following item.

=== PRODUCT BRIEF (CN) ===
SKU: YN-BRA-001
名称: 黑色高弹速干运动内衣（前拉链款）
品类: 运动内衣 / sports bra
卖点:
  - 透气网眼面料（背部和侧腋下）
  - 前置金属拉链穿脱方便
  - 高弹力支撑，适合中高强度运动
  - 速干面料，汗后 8 分钟挥发
  - 一体织造无侧缝
适用场景: 瑜伽馆、跑步、健身房、户外
受众: 25-40 岁运动女性
风格倾向: 自然光、清爽极简、年轻活力但专业
品牌色: 黑色为主调（哑光黑），避免色偏到深蓝或深棕
Logo: 左胸位置丝印小 logo，与面料同色调（哑光黑底 + 略深的炭黑色 logo）
材质成分: 78% 锦纶 + 22% 氨纶
胸垫: 一体式 8 字胸垫，可拆
洗护: 30°C 手洗或机洗轻柔，不可漂白，不可烘干

=== REFERENCE IMAGES ===
[image 1] 平铺正面图，可见前拉链全貌、左胸 logo
[image 2] 模特上身正面图，瑜伽馆背景
[image 3] 背部细节，可见网眼区域

=== REQUIRED 24 FIELDS ===
Return JSON with exactly these keys:

{
  "category": "sports_bra",
  "sub_category": "<zip_front | pullover | racerback | strappy>",
  "primary_color": "<canonical name + hex>",
  "secondary_colors": [<list or empty>],
  "color_undertone": "<warm | cool | neutral>",
  "pattern": "<solid | print | colorblock | mesh_panel | other>",
  "material_main": "<fabric composition phrase>",
  "material_secondary": "<for mesh panels etc., or null>",
  "fabric_finish": "<matte | satin_sheen | high_gloss>",
  "fabric_weight": "<lightweight | midweight | heavyweight>",
  "stretch_level": "<low | medium | high | four_way>",
  "silhouette": "<compression_fit | regular | relaxed>",
  "neckline": "<scoop | v_neck | high_neck | racerback | other>",
  "sleeve_type": "<sleeveless | tank | short_sleeve | long_sleeve>",
  "closure_type": "<pullover | front_zip | back_zip | hook_eye | none>",
  "support_level": "<low | medium | high>",
  "padding": "<removable_cups | sewn_in | none>",
  "logo_present": true,
  "logo_placement": "<precise location description>",
  "logo_style": "<tonal_print | embroidered | reflective | metallic | rubber_patch>",
  "size_range": "<list>",
  "target_audience": "<short phrase>",
  "intended_use_scenes": [<list>],
  "care_instructions": "<phrase>"
}

Output ONLY the JSON object.
```

## 期望输出格式（JSON Schema）

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": [
    "category", "sub_category", "primary_color", "secondary_colors",
    "color_undertone", "pattern", "material_main", "material_secondary",
    "fabric_finish", "fabric_weight", "stretch_level", "silhouette",
    "neckline", "sleeve_type", "closure_type", "support_level",
    "padding", "logo_present", "logo_placement", "logo_style",
    "size_range", "target_audience", "intended_use_scenes", "care_instructions"
  ],
  "properties": {
    "category": { "type": "string" },
    "sub_category": { "type": "string", "enum": ["zip_front", "pullover", "racerback", "strappy"] },
    "primary_color": { "type": "string" },
    "secondary_colors": { "type": "array", "items": { "type": "string" } },
    "color_undertone": { "type": "string", "enum": ["warm", "cool", "neutral"] },
    "pattern": { "type": "string" },
    "material_main": { "type": "string" },
    "material_secondary": { "type": ["string", "null"] },
    "fabric_finish": { "type": "string", "enum": ["matte", "satin_sheen", "high_gloss"] },
    "fabric_weight": { "type": "string", "enum": ["lightweight", "midweight", "heavyweight"] },
    "stretch_level": { "type": "string", "enum": ["low", "medium", "high", "four_way"] },
    "silhouette": { "type": "string" },
    "neckline": { "type": "string" },
    "sleeve_type": { "type": "string" },
    "closure_type": { "type": "string" },
    "support_level": { "type": "string", "enum": ["low", "medium", "high"] },
    "padding": { "type": "string" },
    "logo_present": { "type": "boolean" },
    "logo_placement": { "type": ["string", "null"] },
    "logo_style": { "type": ["string", "null"] },
    "size_range": { "type": "array" },
    "target_audience": { "type": "string" },
    "intended_use_scenes": { "type": "array", "items": { "type": "string" } },
    "care_instructions": { "type": "string" }
  }
}
```

## Few-shot 示例

### 示例 1（YN-BRA-001 期望输出）

```json
{
  "category": "sports_bra",
  "sub_category": "zip_front",
  "primary_color": "matte black / #0a0a0a",
  "secondary_colors": ["charcoal accent / #1a1a1a"],
  "color_undertone": "neutral",
  "pattern": "solid_with_mesh_panel",
  "material_main": "78% nylon, 22% spandex blend, sweat-wicking",
  "material_secondary": "breathable mesh inserts on back and side underarm panels",
  "fabric_finish": "matte",
  "fabric_weight": "midweight",
  "stretch_level": "four_way",
  "silhouette": "compression_fit",
  "neckline": "scoop",
  "sleeve_type": "sleeveless",
  "closure_type": "front_zip",
  "support_level": "high",
  "padding": "removable_cups",
  "logo_present": true,
  "logo_placement": "left chest panel, approximately 6cm below collarbone, ~3cm wide tonal logo",
  "logo_style": "tonal_print",
  "size_range": ["XS", "S", "M", "L", "XL"],
  "target_audience": "active women aged 25-40, mid-to-high intensity training",
  "intended_use_scenes": ["yoga_studio", "running", "gym", "outdoor"],
  "care_instructions": "machine wash gentle 30C, no bleach, no tumble dry"
}
```

### 示例 2（瑜伽裤参考）

```json
{
  "category": "leggings",
  "sub_category": "high_waist_full_length",
  "primary_color": "deep olive / #4a5230",
  "secondary_colors": [],
  "color_undertone": "warm",
  "pattern": "solid",
  "material_main": "75% nylon, 25% spandex, buttery-soft hand feel",
  "material_secondary": null,
  "fabric_finish": "matte",
  "fabric_weight": "midweight",
  "stretch_level": "four_way",
  "silhouette": "compression_fit",
  "neckline": "n/a",
  "sleeve_type": "n/a",
  "closure_type": "pullover",
  "support_level": "medium",
  "padding": "none",
  "logo_present": true,
  "logo_placement": "right thigh side seam, 12cm below hip, small tonal heat-transfer",
  "logo_style": "reflective",
  "size_range": ["XS", "S", "M", "L"],
  "target_audience": "yoga and pilates practitioners, ages 22-38",
  "intended_use_scenes": ["yoga_studio", "pilates", "casual_wear"],
  "care_instructions": "cold wash, line dry"
}
```

### 示例 3（运动 T 恤参考）

```json
{
  "category": "athletic_tshirt",
  "sub_category": "regular_crew",
  "primary_color": "stone gray / #b0b0a8",
  "secondary_colors": ["white piping / #ffffff"],
  "color_undertone": "cool",
  "pattern": "solid_with_contrast_trim",
  "material_main": "100% recycled polyester, mesh weave",
  "material_secondary": null,
  "fabric_finish": "matte",
  "fabric_weight": "lightweight",
  "stretch_level": "medium",
  "silhouette": "regular",
  "neckline": "crew",
  "sleeve_type": "short_sleeve",
  "closure_type": "pullover",
  "support_level": "n/a",
  "padding": "none",
  "logo_present": true,
  "logo_placement": "center chest, 10cm below collar, embroidered 4cm circular logo",
  "logo_style": "embroidered",
  "size_range": ["S", "M", "L", "XL", "XXL"],
  "target_audience": "men and women, casual training, 20-45",
  "intended_use_scenes": ["gym", "running", "casual_wear"],
  "care_instructions": "machine wash 40C, low tumble dry"
}
```

## 调用示例（curl）

```bash
curl -X POST https://5dock.com/v1/chat/completions \
  -H "Authorization: Bearer $FIVEDOCK_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "temperature": 0.2,
    "max_tokens": 2000,
    "response_format": { "type": "json_object" },
    "messages": [
      { "role": "system", "content": "<SYSTEM PROMPT 见上文>" },
      { "role": "user", "content": [
          { "type": "text", "text": "<USER PROMPT 见上文>" },
          { "type": "image_url", "image_url": { "url": "https://yfn-content-factory.oss-cn-shanghai.aliyuncs.com/refs/YN-BRA-001/customer_ref_001.jpg" } },
          { "type": "image_url", "image_url": { "url": "https://yfn-content-factory.oss-cn-shanghai.aliyuncs.com/refs/YN-BRA-001/customer_ref_002.jpg" } },
          { "type": "image_url", "image_url": { "url": "https://yfn-content-factory.oss-cn-shanghai.aliyuncs.com/refs/YN-BRA-001/customer_ref_003.jpg" } }
        ]
      }
    ]
  }'
```
