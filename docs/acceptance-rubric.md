# Acceptance Rubric

> 用这个评分表替代“和样本一样或更高”。没有评分表，就没有可签的验收。

## 1. Acceptance Window

| Item | Rule |
|---|---|
| SKU | 只评估客户确认的 1 个 SKU 与固定素材包 |
| Reviewer | 客户指定 1-3 名审核人，验收以书面结论为准 |
| Attempt | Phase 0 默认最多 2 轮自动重生成 |
| Evidence | 保留图片/视频 URL、prompt、seed、run metadata、审核记录 |
| Dispute | 评分维度逐项复核，不使用主观总评替代 |

## 2. Image Rubric

满分 100，Phase 0 通过线：总分 >= 80，且任何 P0 事实错误为不通过。

| Dimension | Weight | Pass condition |
|---|---:|---|
| Product identity | 25 | SKU、颜色、版型、核心结构与客户素材一致 |
| Key selling points | 20 | 至少 2 个核心卖点可在画面中被识别 |
| Commercial quality | 20 | 清晰、构图可用、无明显畸形、无水印 |
| Brand consistency | 15 | 色调、模特气质、场景符合风格模板 |
| Compliance | 10 | 不生成未授权商标、低俗/夸大/侵权内容 |
| Traceability | 10 | 每张候选有 prompt、参数、模型、run_id |

## 3. Video Rubric

满分 100，Phase 0 通过线：总分 >= 80。若使用预生成视频，必须标注 `PRE-GENERATED`，不能伪装成 live run。

| Dimension | Weight | Pass condition |
|---|---:|---|
| Duration / format | 15 | 10-15 秒，9:16，能正常播放 |
| Story coherence | 20 | 有开场、卖点展示、场景动作、收尾 |
| Product consistency | 25 | 服装颜色、结构、模特/风格与图片链路一致 |
| Visual quality | 20 | 无严重脸崩、肢体异常、服装漂移 |
| Caption / voiceover | 10 | 字幕或口播不含未经证实的功效承诺 |
| Traceability | 10 | 有首帧、prompt、模型、run metadata |

## 4. P0 Failure Examples

- 把黑色运动内衣生成成蓝色、白色或其他品类。
- 生成未经客户授权的真人脸、品牌 Logo 或竞品商标。
- 视频无法播放或文件损坏。
- 工作流无法导入或任务不能落库。
- 把预生成 fallback 伪装成 live run。

## 5. Sign-off Template

```text
SKU:
Reviewer:
Sample pack version:
Image score:
Video score:
Approved assets:
Known issues accepted:
Rework rounds used:
Sign-off date:
```
