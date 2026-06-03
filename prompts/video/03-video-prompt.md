# 03 — Seedance 2.0 视频 Prompt 生成

## 用途

视频链路 S6 步：基于分镜脚本（01）+ 已生成的首帧（02 的产物 `first_frame_url`）+（仅镜 2/3/4）前一镜的尾帧 URL，调用 Claude 生成 Seedance 2.0 的视频 prompt。Seedance 习惯接受**中英混合 + 控制参数尾巴**的 prompt：主体描述与运镜 / 动作走中文，专业镜头术语、风格关键词、控制参数走英文。口播台词以 `<dialogue>` 标签前置写入，让 Seedance 生成原生口播音频。

## System Prompt

```
你是 Seedance 2.0 视频 prompt 工程师。给你一个分镜 JSON、对应首帧图像 URL，以及（仅镜 2-4）前一镜的尾帧 URL。生成一段可直接投喂 Seedance 的视频 prompt。

硬性规则：

1. 单段输出，不要分行不要 markdown。
2. 长度 220–360 个字符（中英混合）。Seedance 长 prompt 容易稀释关键指令。
3. 结构（必须按这个顺序）：
   主体（模特、服装关键细节）→ 起始动作（与首帧无缝衔接的微动作）→ 全镜动作展开 → 运镜术语（中文，含速度修饰）→ 环境与光线 → 风格关键词（英文）→ 口播 dialogue → 控制参数尾巴。
4. 运镜术语统一用：推 / 拉 / 摇 / 跟拍 / 升降 / 环绕 / 固定。每个术语后跟"缓 / 中速 / 快"修饰。
5. 口播以 `<dialogue>...</dialogue>` 包裹，仅放该镜 voiceover 原文（中文）。Seedance 会据此生成原生中文口播。
6. 控制参数尾巴必须为：` --resolution 720p --ratio 9:16 --duration 3 --fps 24 --camera_fixed false --watermark false`
7. 不要写 negative prompt（Seedance 不接收）。不要写"high quality / masterpiece"等口水词。
8. 严禁在 prompt 中重复模特长相描述 — 那是首帧图片的工作；本 prompt 只描述"动作 + 运镜 + 环境光线变化"。

输出仅一段 prompt 字符串。
```

## User Prompt 模板

```
为 Seedance 2.0 生成镜 {{ scene_no }} 的视频 prompt。

[Scene JSON]
{{ scene_json }}

[首帧 URL（已通过 image_url 字段在 API 层传入，不要写进 prompt）]
{{ first_frame_url }}

{{#if scene_no > 1}}
[前一镜尾帧 URL（已通过 last_frame_image_url 在 API 层传入，不要写进 prompt）]
{{ prev_last_frame_url }}
{{/if}}

[衔接要点]
{{ transition_to_next_from_prev }}
```

## 期望输出

单行 prompt 字符串，含 dialogue 标签与控制参数尾巴。

## YN-BRA-001 — 4 镜完整 Seedance Prompt 成品

### 镜 1（hook · 3s）

```
画面中模特从背身静态站立微微启动，右手由侧腰位置缓慢上抬至头顶把高马尾向上拢起，肩胛骨随动作自然收紧，胸腔轻轻打开，整段动作 0.6 秒完成后保持轻呼吸状态。镜头同步执行 推（缓），从全身中景缓慢推近至腰胯以上，景深逐渐变浅。瑜伽馆暖白晨光从右后窗位斜射，木地板高光随推近愈发明显，背景沙幔轻飘。warm-white side rim 4200K, soft cool fill, slight film grain, editorial sportwear cinematic, Kodak Portra 400 grade. <dialogue>试过才懂</dialogue> --resolution 720p --ratio 9:16 --duration 3 --fps 24 --camera_fixed false --watermark false
```

### 镜 2（卖点 A · 前拉链特写 · 3s）

```
模特保持三四分侧脸不动，右手食指与拇指捏住胸口金属拉链拉头，从首帧位置开始向下做 8 厘米的微缓拉动，拉链齿轨被一帧帧带开，动作均匀不抖；嘴角轻扬，眼神向下望向拉链。镜头采取 固定（无位移）+ 极轻微对焦呼吸，景深极浅，焦点死锁在拉链头与锁骨之间。背景瑜伽馆完全虚化为暖色 bokeh。soft 4500K front fill, 6000K top kicker glinting on zipper teeth, ultra-sharp metallic detail, fine grain, editorial product close-up. <dialogue>前拉链 三秒上身</dialogue> --resolution 720p --ratio 9:16 --duration 3 --fps 24 --camera_fixed false --watermark false
```

### 镜 3（卖点 B · 开合跳 · 3s）

```
从首帧的跳跃顶点开始，模特双脚下落到地板回弹再完成第二次开合跳：手臂从斜上 V 字下收到体侧再上抬，双脚在 1.2 秒节拍内开合一次，胸口在落地瞬间完全无上下位移，腋下菱形网眼随动作微微开合露出透气结构。镜头采用 跟拍（中速）+ 微推，每跳推近 5 厘米，低位仰拍仰角约 15 度，手部与马尾梢有轻微动态模糊但躯干保持锐利。5000K 顶光，地面银色反光板补阴影，光线随跳跃节奏轻微脉动。dynamic cinematic motion frame, fine grain, ultra-sharp underarm mesh weave. <dialogue>跑跳不晃 一秒速干</dialogue> --resolution 720p --ratio 9:16 --duration 3 --fps 24 --camera_fixed false --watermark false
```

### 镜 4（CTA · 正面定格 · 3s）

```
承接上一镜落地后的稳定姿态，模特正面平视镜头，右手已握住拉链拉头，自胸口位置向上做最后 6 厘米的拉合动作，约 1.2 秒完成后手指停在拉头上保持定格 1.5 秒，嘴角轻扬眼神向镜头形成信任感落点。镜头执行 拉（缓）+ 终帧固定，从胸口特写缓慢拉远到上半身略宽景，背景瑜伽馆完全虚化为奶油 bokeh。clean 4300K front key, soft rim from behind, no harsh shadow, trustworthy CTA-grade lighting, editorial closer frame, fine grain, ultra-sharp fabric and zipper detail. <dialogue>黑色M码 主页下单</dialogue> --resolution 720p --ratio 9:16 --duration 3 --fps 24 --camera_fixed false --watermark false
```

## Few-shot

### Few-shot 1（瑜伽裤穿搭 hook）

Input：
- scene: 模特在落地镜前提膝穿瑜伽裤、镜头中景缓推、口播"穿对就赢"
- first_frame_url: https://oss.example.com/keyframes/yn-pnt-002-s1.png

Output：
```
模特从首帧的提膝半穿状态继续，右腿膝盖向胸口靠拢的同时左手将高腰宽边向上提合 3 厘米，腰部弹力面料自然回弹贴合腰线，整段动作 1.2 秒后立稳。镜头执行 推（缓），从全身镜面反射的中景推近至腰胯以上。晨光从左侧落地窗斜入，地板高光随推近收紧。warm 4500K window key, soft cool fill, fine film grain, editorial sportwear cinematic. <dialogue>穿对就赢</dialogue> --resolution 720p --ratio 9:16 --duration 3 --fps 24 --camera_fixed false --watermark false
```

### Few-shot 2（家纺产品 — 静物推镜 · 风格迁移参考）

```
画面从全景床品静态起始缓慢推近至枕角华夫格织物的特写，床单褶皱随推近一帧帧显出立体织纹，无人物。镜头执行 推（缓），保持水平不偏移。3200K 床头灯暖光为主，左侧晨光 5500K 透过纱帘补冷调，光比 4:1。home-textile editorial catalog, fine grain, ultra-sharp waffle weave detail. <dialogue>触感会说话</dialogue> --resolution 720p --ratio 9:16 --duration 3 --fps 24 --camera_fixed false --watermark false
```

## 调用示例

### 调 LLM 生成视频 prompt

```bash
curl -X POST https://5dock.com/v1/chat/completions \
  -H "Authorization: Bearer ${CLAUDE_5DOCK_KEY}" \
  -d '{
    "model": "claude-sonnet-4-6",
    "temperature": 0.5,
    "max_tokens": 700,
    "messages": [
      { "role": "system", "content": "<上文 System Prompt 全文>" },
      { "role": "user",   "content": "<上文 User Prompt 模板，注入 scene_json 等>" }
    ]
  }'
```

### 调 Seedance 2.0 提交视频任务

```bash
curl -X POST https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks \
  -H "Authorization: Bearer ${ARK_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "doubao-seedance-1-0-pro-250528",
    "content": [
      { "type": "text", "text": "<LLM 返回的 prompt 字符串（已含控制参数尾巴）>" },
      { "type": "image_url", "image_url": { "url": "<first_frame_url>" }, "role": "first_frame" },
      { "type": "image_url", "image_url": { "url": "<prev_last_frame_url>" }, "role": "last_frame" }
    ]
  }'
```

> 镜 1 不传 `last_frame` 项；镜 2-4 传上一镜成片的最后一帧（视频生成完成后用 FFmpeg `select='eq(n,N-1)'` 抽出来上传 OSS）。

### 轮询任务

```bash
curl -X GET https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks/${TASK_ID} \
  -H "Authorization: Bearer ${ARK_API_KEY}"
# status: queued | running | succeeded | failed
# succeeded 时返回 content[0].video_url
```

## 备用 prompt 策略（Seedance 失败时启用）

第一次失败 → 用以下"精简备用 prompt"模板，去掉一切修饰，只保留主体 + 运镜 + 口播：

```
模特保持首帧姿态启动，{{核心动作一句}}，镜头 {{运镜术语}}（中速）。瑜伽馆自然光。<dialogue>{{voiceover}}</dialogue> --resolution 720p --ratio 9:16 --duration 3 --fps 24 --camera_fixed false --watermark false
```

第二次失败 → 完全去掉 first_frame，转 text-to-video（保留主体描述与口播）。
第三次失败 → 不再调 Seedance，由 FFmpeg 用 first_frame 图加 zoompan Ken Burns 推拉 3 秒补帧（见 video-pipeline.md § 5）。

## N8N 节点占位符

```
{{ $json.scene_no }}
{{ $json.scene_json }}
{{ $json.first_frame_url }}                         ← S5 输出
{{ $json.prev_last_frame_url }}                     ← 镜 2-4 才有，来自上一轮 batch
{{ $node["LLM-Video-Prompt"].json.choices[0].message.content }}
```
