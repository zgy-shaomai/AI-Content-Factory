# 内容工厂数据层 - schemas

本目录存放 PostgreSQL DDL、飞书多维表字段规范、任务状态机文档，是整个内容工厂的数据契约层。

文件清单：
- `postgres-init.sql` — 完整建库脚本（含枚举、表、索引、触发器、视图、seed）
- `feishu-fields.md` — 飞书 4 张多维表字段规格
- `state-machine.md` — 任务全生命周期状态机

---

## 1. 怎么部署 schema

前提：PostgreSQL 16+ 可达，账号有 `CREATE SCHEMA / CREATE EXTENSION` 权限。

```bash
# 1. 在 PG 上创建数据库（首次部署）
createdb -h <host> -U <admin> content_factory

# 2. 执行初始化脚本
psql -h <host> -U <admin> -d content_factory -f postgres-init.sql

# 3. 看一眼输出，应有若干 CREATE / INSERT 行，无 ERROR
```

脚本是幂等的：所有 `CREATE TYPE` 用 `DO $$ ... duplicate_object ...`、所有 `CREATE TABLE` 用 `IF NOT EXISTS`、所有 `INSERT` 用 `ON CONFLICT DO NOTHING`，重复执行不会报错也不会重复插。

飞书侧建表参照 `feishu-fields.md`，按 4 张表的字段顺序与类型逐项创建；建表完成后把每张表的 `app_token / table_id` 填入 N8N 的飞书凭证节点。

---

## 2. 怎么验证 seed 数据

执行完 SQL 后，在 psql 里跑下面三条查询，三条全部返回行即代表 seed 成功：

```sql
-- 行计数检查（期望: tenants=1, style=1, products=1, prompt=5, tasks=2）
SELECT 'tenants' AS t, COUNT(*) FROM content_factory.tenants
UNION ALL SELECT 'style_templates', COUNT(*) FROM content_factory.style_templates
UNION ALL SELECT 'products', COUNT(*) FROM content_factory.products
UNION ALL SELECT 'prompt_templates', COUNT(*) FROM content_factory.prompt_templates
UNION ALL SELECT 'tasks', COUNT(*) FROM content_factory.tasks;

-- 任务总览视图：应能看到 YN-BRA-001 的两条任务（image + video）
SELECT id, sku, product_name, pipeline, status, requested_count
FROM content_factory.v_task_overview;

-- 产品 + 风格联表：检查外键正确
SELECT p.sku, p.name, p.selling_points, s.code AS style_code, s.brand_colors
FROM content_factory.products p
JOIN content_factory.style_templates s ON s.id = p.style_template_id
WHERE p.sku = 'YN-BRA-001';
```

飞书侧验证：在 `tbl_products_input` 手动添一行 `YN-BRA-001` 即可触发 N8N 回写流程，去 `tbl_tasks_progress` 看是否出现一行 `pending` 任务。

---

## 3. 怎么扩展加新表

1. 在 `postgres-init.sql` 末尾（`COMMIT;` 之前）新增 `CREATE TABLE IF NOT EXISTS xxx (...)`，按现有约定补：UUID 主键、`tenant_id` 外键、`created_at/updated_at` 默认值、`updated_at` 触发器、必要 INDEX、关键字段 COMMENT；
2. 若涉及新状态枚举，先 `CREATE TYPE` 再用，并在 `state-machine.md` 转移表中补充对应行；
3. 若该表需要客户在飞书侧也能看到，去 `feishu-fields.md` 加一节，列出字段规格表，并在 N8N 里加 `[node] feishu-sync-xxx`；
4. 实战重大变更（删列、改类型、改外键）请用单独的迁移脚本 `migrations/NNNN_<change>.sql` 而不是改本文件，保持本文件始终是"从零拉起完整库"的入口；
5. 改完后在本地起一个干净 PG，跑一次 `psql -f postgres-init.sql` 验证幂等，再跑第 2 节的验证查询。
