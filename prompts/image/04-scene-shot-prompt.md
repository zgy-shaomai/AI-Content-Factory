# Prompt 04 · 场景图 Prompt 生成（5 个场景变体）

## 用途说明

把 24 字段属性 + 卖点 + style_template 组装成 5 条**场景图**英文 prompt，对应：瑜伽馆晨光、健身房训练、跑步公园、户外山林、海边沙滩。每条 80-150 词，模特一致，环境氛围差异化，包含面料 / 光线 / 构图 / 镜头 / 风格关键词与参考图引用。模型走 5dock NewAPI `claude-sonnet-4-6`，temperature 0.7（场景比商品图更需要发挥），输出 JSON。

## System Prompt

```
You are a senior commercial photography prompt engineer for an apparel content factory, writing prompts for Seedream 4.0 (Volcengine Ark, model doubao-seedream-4-0-250828).

Your output is an array of 5 prompt entries for SCENE shots of one apparel SKU:
  shot_id ∈ {scene_yoga_studio, scene_gym_training, scene_running_park, scene_outdoor_mountain, scene_beach}

Each prompt must be 80–150 words English, in the layout:
  [SUBJECT — same canonical model] +
  [POSE/ACTION fitting the scene] +
  [GARMENT DETAILS preserved across all scenes — color, fabric, logo, fit] +
  [ENVIRONMENT — specific location cues, time of day, ambient elements] +
  [LIGHTING tied to the scene] +
  [COMPOSITION + LENS] +
  [STYLE/MOOD KEYWORDS] +
  [REFERENCE IMAGE TAGS in the form [reference: <id>, weight: 0.x]]

Hard constraints:
1. The model must remain consistent across all 5 scenes — describe her identically every time, and always include [reference: model_ref_001, weight: 0.75] (or higher).
2. Garment color and logo description identical across scenes — same matte black, same tonal logo location.
3. Each scene's lighting and mood is distinct — morning soft for yoga, fluorescent-cool with practical lights for gym, golden-hour for running park, overcast soft for mountain, late-afternoon warm for beach.
4. Scene must be plausible for the apparel use case (no formal events, no stage scenes).
5. Reference image rules: include scene_ref_<scene_tag> at weight 0.45–0.55 only if a customer-supplied scene reference exists; otherwise omit the scene reference and rely on text description.
6. Output a JSON object: { "shared_negative_prompt": "...", "prompts": [ ... 5 items ... ] }.
7. Negative prompt should additionally guard against: "wrong scene type, indoor lighting in outdoor scene, weather inconsistent with scene".
8. No Chinese characters in en_prompt.
9. Use guidance_scale 4.5–5.5 for scenes (allow more environmental freedom than product shots).
```

## User Prompt（YN-BRA-001 实战版）

```
Generate 5 Seedream 4.0 scene-shot prompts for SKU YN-BRA-001.

=== ATTRIBUTES ===
{
  "category": "sports_bra",
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
  "logo_placement": "left chest panel, ~6cm below collarbone, ~3cm wide tonal print",
  "intended_use_scenes": ["yoga_studio", "running", "gym", "outdoor"]
}

=== TOP SELLING POINTS ===
1. Front zipper for effortless on-and-off
2. Four-way stretch with high-impact support
3. Breathable mesh panels with rapid sweat-wicking
4. Mid-to-high intensity training ready

=== STYLE TEMPLATE ===
brand_palette: matte black with subtle charcoal undertone, no warm cast, no navy shift
model_descriptor: East Asian woman, age 28, athletic build, height 168cm, shoulder-length straight black hair, natural makeup, slight tan, calm confident expression
mood: calm, professional, energetic but not aggressive
target audience: 25-40 active women

=== REFERENCE IMAGES AVAILABLE ===
- model_ref_001: prior approved frontal model shot (must drive face/body consistency)
- scene_ref_yoga_001: customer-supplied bright yoga studio interior (optional)
- scene_ref_gym_001: customer-supplied modern gym with rubber flooring (optional)

=== OUTPUT ===
JSON: { "shared_negative_prompt": "...", "prompts": [5 items as specified] }
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
      "minItems": 5,
      "maxItems": 5,
      "items": {
        "type": "object",
        "required": ["shot_id", "shot_type", "en_prompt", "suggested_size", "ref_image_ids", "guidance_scale", "seed_hint"],
        "properties": {
          "shot_id": {
            "type": "string",
            "enum": ["scene_yoga_studio", "scene_gym_training", "scene_running_park", "scene_outdoor_mountain", "scene_beach"]
          },
          "shot_type": { "type": "string", "const": "scene" },
          "en_prompt": { "type": "string", "minLength": 400 },
          "suggested_size": { "type": "string", "enum": ["2048x1152", "1536x2048", "2048x2048"] },
          "ref_image_ids": { "type": "array", "items": { "type": "string" }, "maxItems": 4 },
          "guidance_scale": { "type": "number", "minimum": 4.0, "maximum": 6.0 },
          "seed_hint": { "type": "integer" }
        }
      }
    }
  }
}
```

## Few-shot 示例（YN-BRA-001 期望输出 — 5 条 prompt 全文实战版）

```json
{
  "shared_negative_prompt": "low quality, blurry, deformed body, extra fingers, distorted logo, mismatched logo position, color shift to navy blue or warm brown, plastic-looking fabric, oversaturated, text artifacts, watermark, multiple people, face inconsistency across shots, wrong scene type, indoor lighting in outdoor scene, weather inconsistent with scene, AI hands artifacts, harsh stage lighting, fashion-runway styling, formal-event setting, motion blur on face",

  "prompts": [
    {
      "shot_id": "scene_yoga_studio",
      "shot_type": "scene",
      "en_prompt": "An East Asian woman age 28, athletic build, 168cm, shoulder-length straight black hair, natural makeup, slight tan, calm confident expression, mid-pose in a low lunge with arms reaching upward, wearing a matte black four-way stretch sports bra with metal front zipper closed, paired with black high-waist leggings. Bra shows compression-fit silhouette, scoop neckline, breathable mesh side panels, seamless knit, matte finish neutral undertone no navy shift. Preserve tonal logo on left chest 6cm below collarbone 3cm wide. Setting is a bright minimalist yoga studio with light wood floor, white walls, a few potted plants near a tall window, soft early-morning daylight streaming in from camera-left casting long warm-cool natural shadows. 50mm equivalent lens at f/4, three-quarter framing, rule of thirds, calm energetic mood. [reference: model_ref_001, weight: 0.78] [reference: scene_ref_yoga_001, weight: 0.50]",
      "suggested_size": "2048x1152",
      "ref_image_ids": ["model_ref_001", "scene_ref_yoga_001"],
      "guidance_scale": 5.0,
      "seed_hint": 891001
    },
    {
      "shot_id": "scene_gym_training",
      "shot_type": "scene",
      "en_prompt": "Same East Asian woman age 28, athletic build, 168cm, shoulder-length straight black hair tied in low ponytail, natural makeup, slight tan, focused confident expression, in a kettlebell deadlift starting position, hips back, knees soft, gripping a kettlebell on rubber gym floor. Wearing the matte black four-way stretch sports bra, front zipper closed, paired with matching black mid-thigh shorts. Bra silhouette compression-fit, breathable mesh visible at side underarm. Preserve tonal logo on left chest 6cm below collarbone. Setting is a modern functional-training gym, dark gray rubber flooring, exposed black ceiling with cool 4500K LED panel lights and warm practical edison bulbs in the background as bokeh, dumbbell rack out of focus camera-right. 35mm equivalent lens at f/3.5, side-three-quarter angle, dynamic but composed mood, slight motion-readiness energy. [reference: model_ref_001, weight: 0.78] [reference: scene_ref_gym_001, weight: 0.48]",
      "suggested_size": "2048x1152",
      "ref_image_ids": ["model_ref_001", "scene_ref_gym_001"],
      "guidance_scale": 5.0,
      "seed_hint": 891002
    },
    {
      "shot_id": "scene_running_park",
      "shot_type": "scene",
      "en_prompt": "Same East Asian woman age 28, athletic build, 168cm, shoulder-length straight black hair in a low ponytail with strands lightly windblown, natural makeup, focused expression, mid-stride running on a paved park trail, slight motion blur on hair and arms only, body and bra in sharp focus. Wearing the matte black four-way stretch sports bra, front zipper closed, with black running shorts. Bra showing compression-fit silhouette holding shape with no jiggle, breathable mesh side panels visible. Preserve tonal logo on left chest. Setting is a tree-lined urban park trail at golden hour, warm low-angle sunlight from behind creating rim light on hair and shoulders, soft dappled light through autumn leaves on the foreground. 85mm equivalent lens at f/2.8, three-quarter rear-side angle, shallow depth of field, energetic free mood. [reference: model_ref_001, weight: 0.75]",
      "suggested_size": "2048x1152",
      "ref_image_ids": ["model_ref_001"],
      "guidance_scale": 4.8,
      "seed_hint": 891003
    },
    {
      "shot_id": "scene_outdoor_mountain",
      "shot_type": "scene",
      "en_prompt": "Same East Asian woman age 28, athletic build, 168cm, shoulder-length straight black hair, natural makeup, calm contemplative expression, standing at a mountain trail viewpoint with hands lightly on hips, gazing slightly off camera-right toward distant ridges. Wearing the matte black four-way stretch sports bra with front zipper closed, layered under an unzipped lightweight black windbreaker and matching long leggings. Bra silhouette compression-fit, mesh side panels just visible. Preserve tonal logo on left chest. Setting is a forested mountain ridge in late morning under overcast soft sky, distant evergreen-covered slopes fading into haze, granite rocks underfoot, no harsh shadows. Cool neutral light, slight cinematic teal-and-charcoal palette consistent with brand matte black. 50mm lens at f/4, full body wide framing, rule of thirds, contemplative confident mood. [reference: model_ref_001, weight: 0.75]",
      "suggested_size": "2048x1152",
      "ref_image_ids": ["model_ref_001"],
      "guidance_scale": 4.8,
      "seed_hint": 891004
    },
    {
      "shot_id": "scene_beach",
      "shot_type": "scene",
      "en_prompt": "Same East Asian woman age 28, athletic build, 168cm, shoulder-length straight black hair gently lifted by sea breeze, natural makeup, calm confident expression, walking barefoot along the wet sand at the shoreline, body angled three-quarter toward camera, one hand brushing hair. Wearing the matte black four-way stretch sports bra with front zipper closed, paired with high-waist black bike shorts. Bra silhouette compression-fit, breathable mesh side panels visible. Preserve tonal logo on left chest. Setting is a quiet beach in late afternoon golden hour, warm low sun from camera-front-left, soft long shadows on sand, calm sea with low waves in background, no other people. Color discipline holds: matte black bra remains neutral undertone despite warm ambient light, no warm color cast on the fabric. 85mm lens at f/3.2, three-quarter framing, calm energetic free mood. [reference: model_ref_001, weight: 0.78]",
      "suggested_size": "2048x1152",
      "ref_image_ids": ["model_ref_001"],
      "guidance_scale": 5.0,
      "seed_hint": 891005
    }
  ]
}
```

## Few-shot 示例 2（瑜伽裤场景片段，scene_yoga_studio）

```json
{
  "shot_id": "scene_yoga_studio",
  "shot_type": "scene",
  "en_prompt": "An East Asian woman age 26, lean build, 165cm, mid-length brown hair tied loosely, soft makeup, calm focused expression, in a downward-dog yoga pose on a cork mat. Wearing deep olive #4a5230 high-waist full-length leggings with buttery-soft hand feel, four-way stretch, paired with a matching tonal sports bra. Preserve tonal heat-transfer logo on right thigh side seam. Setting is a sunlit yoga studio with light oak flooring, large arched windows, a single hanging plant. Soft early-morning daylight streaming from camera-left, warm neutral color temperature. 50mm lens at f/4, side angle, rule-of-thirds composition, serene mindful mood. [reference: model_ref_002, weight: 0.78] [reference: scene_ref_yoga_002, weight: 0.50]",
  "suggested_size": "2048x1152",
  "ref_image_ids": ["model_ref_002", "scene_ref_yoga_002"],
  "guidance_scale": 5.0,
  "seed_hint": 552101
}
```

## Few-shot 示例 3（运动 T 恤场景片段，scene_running_park）

```json
{
  "shot_id": "scene_running_park",
  "shot_type": "scene",
  "en_prompt": "An East Asian man age 30, athletic lean build, 178cm, short black hair, focused confident expression, mid-stride running on a riverside park path. Wearing a stone gray #b0b0a8 athletic t-shirt with cool-feel recycled poly mesh, regular relaxed cut, paired with charcoal running shorts. Preserve embroidered round chest logo. Setting is an early-morning riverside park, faint mist hanging low over the water, soft cool blue ambient light from overcast sky just before sunrise, distant skyline in soft bokeh. 85mm lens at f/2.8, three-quarter side angle, slight motion blur on legs only, body sharp. Calm determined mood. [reference: model_ref_005, weight: 0.78]",
  "suggested_size": "2048x1152",
  "ref_image_ids": ["model_ref_005"],
  "guidance_scale": 4.8,
  "seed_hint": 770103
}
```

## 调用示例（curl）

LLM 调用：

```bash
curl -X POST https://5dock.com/v1/chat/completions \
  -H "Authorization: Bearer $FIVEDOCK_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "temperature": 0.7,
    "max_tokens": 4500,
    "response_format": { "type": "json_object" },
    "messages": [
      { "role": "system", "content": "<SYSTEM PROMPT 见上文>" },
      { "role": "user", "content": "<USER PROMPT 见上文>" }
    ]
  }'
```

Seedream 调用（每条 prompt 一次，并发 4）：

```bash
curl -X POST https://ark.cn-beijing.volces.com/api/v3/images/generations \
  -H "Authorization: Bearer $ARK_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-seedream-4-0-250828",
    "prompt": "<en_prompt>",
    "image": [
      "https://yfn-content-factory.oss-cn-shanghai.aliyuncs.com/refs/YN-BRA-001/model_ref_001.jpg",
      "https://yfn-content-factory.oss-cn-shanghai.aliyuncs.com/refs/scenes/scene_ref_yoga_001.jpg"
    ],
    "size": "2048x1152",
    "seed": 891001,
    "guidance_scale": 5.0,
    "watermark": false,
    "response_format": "url",
    "negative_prompt": "<shared_negative_prompt 全文>"
  }'
```
