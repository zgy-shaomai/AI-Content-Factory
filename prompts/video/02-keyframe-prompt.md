# 02 — 首帧（Seedream 4.0）Prompt 生成

## 用途

视频链路 S4 步：把分镜脚本（01 输出）的每一镜转成一段英文 Seedream 4.0 prompt，用于生成 720×1280（9:16）的视频首帧静态图。该首帧将作为 S6 步 Seedance 的 `image_url`（first_frame）传入。

## System Prompt

```
You are a senior fashion-product photographer turned AI prompt engineer. Your job is to convert a single scene description from a Chinese TikTok storyboard into one well-structured Seedream 4.0 image prompt.

Hard rules:
1. Output English only. No Chinese characters in the final prompt.
2. Length: 80–150 words.
3. Structure (in order, separated by commas, no headings):
   subject (model description, age, ethnicity, hair, body type) →
   wardrobe (garment SKU, fabric, structural detail in close focus) →
   action / pose (frozen at the first frame moment) →
   environment (location, props, background depth) →
   camera (focal length, framing, angle) →
   lighting (color temp, direction, mood) →
   color grading & film stock keywords →
   negative cues at the very end as "--no <terms>".
4. Use cinematic / fashion editorial vocabulary (e.g. "soft window light", "85mm portrait lens", "shallow depth of field", "Kodak Portra 400 grade").
5. Do not invent product details that are not in the storyboard.
6. The first frame must be the *exact* moment the scene starts — not the middle, not the end. The model in the image should be one micro-frame before motion begins.
7. Maintain a single consistent model identity across all 4 scenes by re-using the same descriptor block ("Asian female model, 27 years old, long ponytail, natural tan skin, athletic 168cm build, defined shoulders, soft confident expression").
8. End with style anchors: "shot on Sony FX3, 9:16 vertical, 720x1280, ultra-sharp fabric texture, advertising grade".
9. Append: "--no extra fingers, deformed hands, watermark, text overlay, plastic skin, oversaturated, multiple subjects".

Output ONLY the prompt string, no JSON, no markdown, no explanation.
```

## User Prompt 模板

```
Convert the following storyboard scene into one Seedream 4.0 prompt.

[Scene JSON]
{{ scene_json }}

[Style anchors]
- style_id: sportwear_dynamic
- look: warm-white key + cool fill, high contrast, slight film grain, editorial sportwear
- camera prefs: 85mm lens, low-angle hero shots mixed with eye-level mids
- model identity (must reuse verbatim): Asian female model, 27 years old, long ponytail, natural tan skin, athletic 168cm build, defined shoulders, soft confident expression
- garment ground truth: black sports bra YN-BRA-001, front metallic zipper down the center, diamond-cut breathable mesh panels at the back and underarms, matte performance jersey main body, no logo
- reference image url (will be passed via API as reference_images): {{ reference_image_url }}
```

## 期望输出格式

纯文本字符串，单段，逗号分隔。不带引号、不带 markdown 围栏。

## YN-BRA-001 — 4 镜完整 Prompt 成品

### 镜 1（hook — 瑜伽馆背身拢发）

```
Asian female model, 27 years old, long ponytail just gathered above her head with her right hand mid-motion, natural tan skin, athletic 168cm build, defined shoulders, soft confident expression, wearing the black sports bra YN-BRA-001 with a centered front metallic zipper and diamond-cut breathable mesh panels across the upper back and shoulder blades, standing with her back three-quarters to the camera in a sun-lit yoga studio, blonde oak floorboards, large floor-to-ceiling window on the right rear, sheer linen curtain softly diffusing morning light, distant rolled yoga mat on the floor, medium shot framed from mid-thigh to head, slow push-in beginning, 85mm portrait lens, eye-level rising slightly to meet the shoulder line, warm side-rim 4200K key from the right window, cool 5600K fill from left, deep shadows on the spine, editorial sportwear cinematography, Kodak Portra 400 grade, fine film grain, ultra-sharp diamond mesh fabric texture, shot on Sony FX3, 9:16 vertical, 720x1280, advertising grade --no extra fingers, deformed hands, watermark, text overlay, plastic skin, oversaturated, multiple subjects, logos
```

### 镜 2（卖点 A — 前拉链特写）

```
Asian female model, 27 years old, long ponytail, natural tan skin, athletic 168cm build, defined shoulders, soft confident expression with a faint downward smile, wearing the black sports bra YN-BRA-001, right hand pinches the polished metallic zipper pull just below the collarbone with thumb and index finger frozen at the very start of a gentle downward tug, three-quarter front angle, chest-up close-up showing the entire vertical zipper line and the matte performance jersey weave, decorative shallow seam stitching parallel to the zipper, indoor yoga studio softly blurred behind her with bokeh window light, tight chest-level close-up, 50mm macro feel, eye-level slightly tilted down toward the zipper hardware, soft 4500K front fill plus a 6000K top kicker hitting the metal zipper teeth to glint, very shallow depth of field, ultra-sharp metallic teeth and fabric weft, editorial product detail style, slight film grain, shot on Sony FX3 with 50mm macro, 9:16 vertical, 720x1280, advertising grade --no extra fingers, deformed hands, watermark, text overlay, plastic skin, oversaturated, multiple subjects, logos
```

### 镜 3（卖点 B — 开合跳腋下网眼）

```
Asian female model, 27 years old, long ponytail mid-flight, natural tan skin, athletic 168cm build, defined shoulders, soft confident expression with slight athletic exertion, wearing the black sports bra YN-BRA-001 with diamond-cut breathable mesh panels clearly visible under both arms, captured at the precise apex of a jumping-jack — both arms extended diagonally upward, both feet just leaving the wooden floor by 5cm, hips squared, chest stays supported with no bounce, full-body framing in a bright yoga studio with soft floor reflection, low-angle hero shot looking up from floor level, 35mm wide-ish vertical framing, slight motion blur on the hands and ponytail tip, sharp on the torso and the underarm mesh weave, 5000K overhead key plus a silver bounce filling the underside of the chin and chest, dynamic cinematic lighting, mild handheld feel, editorial sportwear motion frame, fine grain, ultra-sharp mesh and fabric detail, shot on Sony FX3, 9:16 vertical, 720x1280, advertising grade --no extra fingers, deformed hands, watermark, text overlay, plastic skin, oversaturated, multiple subjects, logos, blurred face
```

### 镜 4（CTA — 正面拉合定格）

```
Asian female model, 27 years old, long ponytail, natural tan skin, athletic 168cm build, defined shoulders, soft confident closed-mouth smile with direct eye contact to the lens, wearing the black sports bra YN-BRA-001, right hand grasping the metallic zipper pull at chest center frozen at the moment the zipper has just been pulled fully up to the top, hand still resting on the zipper head, body squared frontally to camera, weight evenly balanced, indoor yoga studio strongly out of focus behind her with creamy 4300K bokeh, chest-up framed slightly wider than scene 2 to show the complete bra silhouette and zipper end, 85mm portrait lens, eye-level, soft even front key plus very subtle rim from behind, no harsh shadows, clean trustworthy CTA-grade lighting, editorial sportwear closer frame, slight film grain, ultra-sharp fabric and zipper detail, shot on Sony FX3, 9:16 vertical, 720x1280, advertising grade --no extra fingers, deformed hands, watermark, text overlay, plastic skin, oversaturated, multiple subjects, logos
```

## Few-shot

### Few-shot 1（瑜伽裤镜 1）

Input scene → Output prompt:

> Asian female model, 27 years old, long ponytail, natural tan skin, athletic 168cm, wearing high-waist black yoga pants with hidden pocket on the right thigh, standing in front of a full-length mirror lifting her right knee at 90 degrees while pulling the waistband higher with her left hand, modern minimalist bedroom in soft morning light, full-body framing reflected in the mirror, 35mm lens, eye-level, 4500K window key from the left, editorial sportwear style, slight film grain, ultra-sharp fabric texture, shot on Sony FX3, 9:16 vertical, 720x1280, advertising grade --no extra fingers, deformed hands, watermark, text overlay, multiple subjects

### Few-shot 2（家纺示例 — 演示风格转移）

> Cozy bedroom corner at golden hour, neatly made bed with waffle-weave duvet cover in oat color folded down to reveal the texture, ceramic table lamp on a walnut nightstand, single hardback book, no model, medium-wide static frame, 50mm lens, eye-level, 3200K warm tungsten lamp plus low-key 5500K window fill from the left, slight haze, editorial home-textile catalog, fine film grain, ultra-sharp waffle weave detail, shot on Sony FX3, 9:16 vertical, 720x1280, advertising grade --no people, watermark, text overlay, plastic textures

## 调用示例

### 调 LLM 生成 prompt

```bash
curl -X POST https://5dock.com/v1/chat/completions \
  -H "Authorization: Bearer ${CLAUDE_5DOCK_KEY}" \
  -d '{
    "model": "claude-sonnet-4-6",
    "temperature": 0.4,
    "max_tokens": 600,
    "messages": [
      { "role": "system", "content": "<上文 System Prompt 全文>" },
      { "role": "user",   "content": "<上文 User Prompt 模板，注入 scene_json 与 reference_image_url>" }
    ]
  }'
```

### 调 Seedream 提交首帧任务

```bash
curl -X POST https://ark.cn-beijing.volces.com/api/v3/images/generations \
  -H "Authorization: Bearer ${ARK_API_KEY}" \
  -d '{
    "model": "doubao-seedream-4-0-250828",
    "prompt": "<上一步 LLM 返回的 prompt 字符串>",
    "size": "720x1280",
    "guidance_scale": 3,
    "watermark": false,
    "response_format": "url",
    "reference_images": ["<image_pool 中第一张白底图 URL>"]
  }'
```

## N8N 节点占位符

```
{{ $json.scene.scene_no }}                      ← 1..4
{{ $json.scene_json }}                          ← 单镜 JSON 字符串
{{ $json.reference_image_url }}                 ← 来自 image_candidates(approved)
{{ $node["LLM-Keyframe-Prompt"].json.choices[0].message.content }}  ← LLM 返回
```
