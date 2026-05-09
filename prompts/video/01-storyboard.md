# 01 — 分镜脚本生成 Prompt

## 用途

在视频链路 S2 步调用 Claude Sonnet 4.6（走 5dock NewAPI），从产品资料（SKU 卖点、目标受众、风格模板）生成 12 秒 4 镜的 TikTok 风格分镜脚本。脚本是后续 Seedream 首帧 prompt（02）与 Seedance 视频 prompt（03）的唯一上游真源。

## System Prompt

```
你是一名专为 TikTok / 抖音电商短视频设计分镜的资深导演兼广告文案。
你的输出必须严格遵循以下硬约束：

1. 总时长 = 12.0 秒，分 4 镜，每镜 3.0 秒。
2. 节奏：镜 1 为 hook（开场吸睛 1-2 秒钩子），镜 2-3 为卖点展示（核心 6-8 秒），镜 4 为 CTA（行动召唤 2-3 秒）。
3. 口播文案：每镜 6-9 个汉字，4 镜累计不超过 36 字（按中文播音 4 字/秒）。语气贴近女性运动场景、口语化、不要用书面语。
4. 画面描述要可拍：明确场景、人物姿态、服装细节、镜头取景、光线、色调。禁止抽象形容词（如"高级感""氛围感"）独立成句。
5. 运镜指令使用电影术语（推 / 拉 / 摇 / 跟拍 / 升降 / 环绕 / 固定），并标注速度（缓 / 中速 / 快）。
6. 镜与镜之间必须设计一个明确的"转场锚点"，让上一镜尾帧能和下一镜首帧自然衔接（同一模特、同一服装、空间或动作连续）。
7. 字幕文案 = 口播文案，但允许做简短的视觉化删减（保留最有力的关键词）。
8. 配乐建议给 BPM 数值与情绪关键词，灯光建议给色温（K）和方向。

输出必须是合法 JSON，结构如下：

{
  "sku": "YN-BRA-001",
  "total_duration_sec": 12.0,
  "scenes": [
    {
      "scene_no": 1,
      "duration_sec": 3.0,
      "role_in_pacing": "hook",
      "scene_description": "...",
      "actor_action": "...",
      "wardrobe_focus": "...",
      "camera": { "shot_type": "...", "movement": "...", "speed": "..." },
      "lighting": { "color_temp_k": 4500, "direction": "...", "mood": "..." },
      "voiceover": "...",
      "subtitle": "...",
      "music": { "bpm": 120, "mood": "...", "reference": "..." },
      "transition_to_next": "..."
    },
    ...
  ]
}

不要输出任何 JSON 之外的文字，不要包 markdown 代码块。
```

## User Prompt（YN-BRA-001 实战版）

```
请为下面这款产品生成 4 镜分镜脚本。

【产品信息】
SKU: YN-BRA-001
名称: 黑色高弹速干运动内衣（前拉链款）
核心卖点:
  - 透气网眼面料（侧腋下、背部菱形拼接）
  - 前置金属拉链，单手 0.5 秒穿脱
  - 高弹力支撑（适配 B-D 罩杯，跑跳不位移）
  - 速干（汗水 5 分钟蒸发，不闷不黏）
场景: 瑜伽馆、跑步、健身房、户外晨跑
目标受众: 25-40 岁运动女性，已稳定健身 6 个月以上，对舒适度敏感

【风格模板】
style_id: sportwear_dynamic
视觉关键词: 暖白光、高对比、轻颗粒感、电影级宽容度、人物皮肤偏冷调饱和
机位偏好: 低位仰拍 + 中位平视混用，强调身体线条
节奏偏好: 前快后稳，CTA 镜稳定收尾

【硬性要求】
- 模特：亚洲女性、26-30 岁、长发马尾、肤色自然、身高 168、运动体型。
- 必须出现"前拉链"特写一次（建议在镜 2 或镜 3）。
- 必须出现"透气网眼"近景一次。
- CTA 镜（镜 4）画面包含拉链镜头落点 + 商品色号一致的产品。
- 字幕颜色统一白字黑描边，底部居中。
```

## 期望输出格式（JSON Schema 摘录）

```json
{
  "type": "object",
  "required": ["sku", "total_duration_sec", "scenes"],
  "properties": {
    "scenes": {
      "type": "array",
      "minItems": 4,
      "maxItems": 4,
      "items": { "$ref": "#/$defs/scene" }
    }
  }
}
```

## YN-BRA-001 完整 4 镜脚本（成品 — 这是 LLM 该返回的样子）

```json
{
  "sku": "YN-BRA-001",
  "total_duration_sec": 12.0,
  "style_id": "sportwear_dynamic",
  "scenes": [
    {
      "scene_no": 1,
      "duration_sec": 3.0,
      "role_in_pacing": "hook",
      "scene_description": "清晨瑜伽馆，落地窗透进暖白光，木地板反光。亚洲女模特长发马尾，背对镜头站立，身穿黑色前拉链运动内衣，露出后背菱形网眼拼接。她抬手把头发向上拢起，手腕自然向后甩，肩胛骨线条收紧。",
      "actor_action": "右手向上拢头发，0.6 秒完成；同时左肩微沉、胸廓打开。",
      "wardrobe_focus": "后背菱形透气网眼拼接（占画面中央 40%）",
      "camera": {
        "shot_type": "中景",
        "movement": "缓慢推近（push-in），从全身推到腰胯以上",
        "speed": "缓"
      },
      "lighting": {
        "color_temp_k": 4200,
        "direction": "侧逆光（窗户在画面右后方）",
        "mood": "通透、克制、有呼吸感"
      },
      "voiceover": "试过才懂",
      "subtitle": "试过才懂",
      "music": {
        "bpm": 96,
        "mood": "深呼吸、电子氛围 pad",
        "reference": "类 ODESZA 早晨 instrumental"
      },
      "transition_to_next": "模特正要转身（脸尚未入镜），动作的 80% 留给下一镜接住。"
    },
    {
      "scene_no": 2,
      "duration_sec": 3.0,
      "role_in_pacing": "selling_point_a",
      "scene_description": "无缝接镜 1：模特已转向 3/4 侧脸，右手食指与拇指捏住胸前金属拉链拉头。镜头特写到锁骨与上胸口位置，金属拉链反光被暖光命中，黑色面料上的细密纹理清晰可见。",
      "actor_action": "右手捏住拉链，向下拉 8 厘米的微小动作，眼神向下看着拉链，嘴角微扬。",
      "wardrobe_focus": "前置金属拉链（特写，占画面 35%），网眼面料肌理（特写，占 25%）",
      "camera": {
        "shot_type": "胸口特写",
        "movement": "固定 + 极轻微对焦呼吸",
        "speed": "—"
      },
      "lighting": {
        "color_temp_k": 4500,
        "direction": "正面柔光 + 顶光打高光",
        "mood": "聚焦、商品质感"
      },
      "voiceover": "前拉链 三秒上身",
      "subtitle": "前拉链 · 三秒上身",
      "music": {
        "bpm": 100,
        "mood": "节拍渐入，加入轻 hi-hat",
        "reference": "类 Tycho 中段"
      },
      "transition_to_next": "模特拉链停在中位，镜头快速 cut，下一镜衔接她已穿好开始动作。"
    },
    {
      "scene_no": 3,
      "duration_sec": 3.0,
      "role_in_pacing": "selling_point_b",
      "scene_description": "切到瑜伽馆地面跟拍：模特正在做开合跳（jumping jack），低位仰拍捕捉胸口与腋下的网眼拼接。她每跳一次，胸部支撑稳定不上下晃动；落地一刻能看到腋下网眼透气区随动作微张。背景轻微动态模糊。",
      "actor_action": "完成 2 次完整开合跳，第二次落地后轻轻喘气，胸口起伏自然。",
      "wardrobe_focus": "腋下网眼透气拼接 + 高弹支撑（无晃动）",
      "camera": {
        "shot_type": "全身 + 低位仰拍",
        "movement": "跟拍跳跃节奏的微推（每跳推 5cm）",
        "speed": "中速"
      },
      "lighting": {
        "color_temp_k": 5000,
        "direction": "顶光 + 地面反光板补阴影",
        "mood": "动感、有力量"
      },
      "voiceover": "跑跳不晃 一秒速干",
      "subtitle": "跑跳不晃 · 一秒速干",
      "music": {
        "bpm": 120,
        "mood": "鼓组进入，节拍重击",
        "reference": "类 RY X remix beat drop"
      },
      "transition_to_next": "模特落地后停住，镜头从全身快速回拉到她平视镜头的胸口位置。"
    },
    {
      "scene_no": 4,
      "duration_sec": 3.0,
      "role_in_pacing": "cta",
      "scene_description": "模特正面平视镜头，胸口居中，右手再次握住拉链拉头，做出向上拉合的动作并定格。她面带轻松微笑，眼神坚定。画面右下角浮现轻量品牌文字水印（不抢主体），左上角弹出商品色号标签'Black M'。背景虚化的瑜伽馆。",
      "actor_action": "右手把拉链向上拉到顶，手指停在拉头上，2 秒定格；同时嘴角上扬、眼神向镜头。",
      "wardrobe_focus": "拉链顶部 + 完整胸口轮廓 + 商品全貌",
      "camera": {
        "shot_type": "胸口特写微拉远到上半身",
        "movement": "缓慢拉远（pull-out）+ 最后一帧固定",
        "speed": "缓"
      },
      "lighting": {
        "color_temp_k": 4300,
        "direction": "正面柔光，去除阴影",
        "mood": "干净、信赖、收口"
      },
      "voiceover": "黑色M码 主页下单",
      "subtitle": "黑色 M 码 · 主页下单",
      "music": {
        "bpm": 100,
        "mood": "鼓组撤回，pad 收尾，留 0.5 秒静音让 CTA 落定",
        "reference": "—"
      },
      "transition_to_next": "—（结束）"
    }
  ]
}
```

字数核验：4 镜口播 = 4 + 7 + 8 + 8 = 27 字（约束 ≤ 36）。

## Few-shot

### Few-shot 1（瑜伽裤示例 — 缩略）

```json
{
  "sku": "YN-PNT-002",
  "scenes": [
    { "scene_no": 1, "duration_sec": 3.0, "role_in_pacing": "hook",
      "voiceover": "穿对就赢",
      "scene_description": "全身镜前模特单腿提膝穿瑜伽裤，腰部弹性翻折一下，镜头中景。" },
    "..."
  ]
}
```

### Few-shot 2（运动夹克 — 缩略，演示节奏）

```json
{
  "sku": "YN-JKT-003",
  "scenes": [
    { "scene_no": 1, "voiceover": "晨跑必备", "role_in_pacing": "hook" },
    { "scene_no": 2, "voiceover": "三层防风", "role_in_pacing": "selling_point_a" },
    { "scene_no": 3, "voiceover": "速干透气", "role_in_pacing": "selling_point_b" },
    { "scene_no": 4, "voiceover": "限时 9 折", "role_in_pacing": "cta" }
  ]
}
```

## 调用示例（cURL）

```bash
curl -X POST https://5dock.com/v1/chat/completions \
  -H "Authorization: Bearer ${CLAUDE_5DOCK_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "temperature": 0.6,
    "max_tokens": 4096,
    "response_format": { "type": "json_object" },
    "messages": [
      { "role": "system", "content": "<上文 System Prompt 全文>" },
      { "role": "user",   "content": "<上文 User Prompt 全文（已注入 product 与 style 字段）>" }
    ]
  }'
```

## N8N 节点中的占位符（与 workflow JSON 对齐）

```
{{ $json.system_prompt }}        ← System Prompt 常量
{{ $json.user_prompt_filled }}   ← 用 $node["Postgres - Read"].json 渲染好的 User Prompt
```
