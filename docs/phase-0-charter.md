# Phase 0 Charter

> 目标：把项目从“能讲方案”推进到“可演示、可验收、可进入实现阶段”的工程化基线。

## 1. Scope

Phase 0 只交付可验证的工程设计与演示闭环，不承诺生产量产稳定性。

**In scope**
- 1 个锁定 SKU：`YN-BRA-001`，客户如替换 SKU，需同步替换素材包与验收样本。
- 图片链路：生成 11 张候选图（6 张商品/细节图 + 5 张场景图），进入审核状态。
- 视频链路：演示 1 条 10-15 秒成片路径；真实渲染可用预生成 fallback，但必须标注 `PRE-GENERATED`。
- 数据闭环：PostgreSQL 记录任务、模型调用、候选物、审核与归档元数据。
- 部署闭环：本地 Docker demo + 生产 docker-compose 骨架 + n8n workflow import。
- 治理闭环：验收评分表、风险登记表、模型矩阵、回滚口径。

**Out of scope**
- 大规模并发量产 SLA。
- 无限返工或人工 PS。
- 自定义前端后台。
- 跨品类泛化效果承诺。
- 第三方 API 成本兜底。

## 2. DRI

| Area | DRI | Backup | Decision |
|---|---|---|---|
| Product scope / SOW | Joshua | 客户业务负责人 | 验收边界、返工轮数 |
| Architecture / workflow | 工程负责人 | N8N owner | 数据流、失败处理、部署 |
| Demo operation | 演示负责人 | SRE | live run / fallback 切换 |
| Customer acceptance | 客户指定审核人 | 客户老板 | 评分与签收 |
| Legal / rights | 客户 | 我方项目负责人 | 素材版权、肖像授权 |

## 3. Success Metrics

| Metric | Phase 0 target |
|---|---|
| Workflow import | `n8n/image-workflow.json` 和 `n8n/video-workflow.json` JSON 可解析，节点引用无断链 |
| Local stack | `deploy/bootstrap-local.*` 可启动 Postgres / Redis / N8N |
| DB contract | schema 可初始化，enum / view / seed 数据与 workflow 状态一致 |
| Image output | 11 张候选进入 DB，至少 4 张可进入客户审核 |
| Video demo | 1 条 10-15 秒成片可展示，live/fallback 标签透明 |
| Audit path | 通过 / 驳回 / 归档路径有明确状态与表字段 |
| Risk closure | 客户书面确认素材权利、验收人、返工轮数、第三方费用 |

## 4. Exit Criteria

Phase 0 结束必须同时满足：

1. `scripts/quality_gate.py` 通过。
2. `python -m py_compile scripts/*.py` 通过。
3. `schemas/smoke-test.sh` 在有 Docker 的环境中通过。
4. 客户确认 `docs/acceptance-rubric.md`。
5. 演示脚本不使用不透明模拟口径，所有 live/fallback 路径必须标注。
