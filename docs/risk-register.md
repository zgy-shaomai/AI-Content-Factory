# Risk Register

> Phase 0 风险登记表。每个风险必须有 owner、触发条件和兜底动作。

| ID | Risk | Probability | Impact | Owner | Trigger | Mitigation | Fallback |
|---|---|---|---|---|---|---|---|
| R1 | 验收口径主观 | High | High | Joshua | 客户说“不像样本”但无评分依据 | 使用 `acceptance-rubric.md` 逐项评分 | 只重跑低分维度 |
| R2 | 客户素材版权/肖像权不清 | Medium | High | 客户 | 使用真人脸或第三方图 | 演示前书面确认授权 | 改 AI 模特或无脸方案 |
| R3 | 火山/5dock API 超时或限流 | Medium | High | SRE | 429/5xx/timeout | 演示前跑 `verify-apis.*` | 切 `PRE-GENERATED` 资产 |
| R4 | N8N workflow 导入后节点红 | Medium | High | 工程负责人 | credential 断链或节点版本不兼容 | 跑 `scripts/quality_gate.py` 和 `n8n_setup.py` | 展示录屏 + DB 数据 |
| R5 | 生成质量不稳定 | High | Medium | Prompt owner | 模特脸崩、服装漂移 | 人工审核 + 最多 2 轮重生成 | 人工挑选可用候选 |
| R6 | 成本失控 | Low | High | 项目负责人 | 单 run 调用数超预算 | run metadata 记录成本，限制重试轮数 | 人工暂停任务 |
| R7 | 生产 queue 无 worker | Low | High | SRE | Redis 有任务但无执行 | docker-compose 固定 `n8n-worker` | 回切 regular 本地演示 |
| R8 | 演示真实性风险 | Medium | High | 演示负责人 | 需要手动触发/预生成资产 | 屏幕标注 `LIVE` / `PRE-GENERATED` | 明确说明这是 fallback |

## Decision Deadlines

| Decision | Deadline | If not decided |
|---|---|---|
| 是否接受飞书作为输入/审核入口 | 演示后 1 个工作日 | Phase 1 不启动 |
| OSS / 火山 / 5dock 账号归属 | 演示后 2 个工作日 | 使用我方临时账号仅做 demo |
| 验收人和评分表 | 合同前 | 不签“同样或更高”口径 |
| 真人模特授权 | 生成真人脸前 | 改为无脸或 AI 模特 |
| 生产 VPS 规格 | 部署前 | Phase 0 仅保留本地 demo |

