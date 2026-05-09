-- ============================================================================
-- 服装电商内容工厂 - PostgreSQL 16 初始化脚本
-- ============================================================================
-- 用途：完整建库脚本，包含 schema、枚举、表、索引、触发器、视图、seed 数据
-- 部署：psql -h <host> -U <user> -d <db> -f postgres-init.sql
-- 版本：v1.0  日期：2026-05-05
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 0. Schema 与扩展
-- ----------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS content_factory;
SET search_path TO content_factory, public;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- 模糊检索

-- ----------------------------------------------------------------------------
-- 1. 枚举类型
-- ----------------------------------------------------------------------------

-- 任务链路类型
DO $$ BEGIN
    CREATE TYPE task_pipeline AS ENUM ('image', 'video');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 任务状态（与 state-machine.md 严格一致）
DO $$ BEGIN
    CREATE TYPE task_status AS ENUM (
        'pending',           -- 待启动
        'analyzing',         -- 卖点拆解中
        'prompting',         -- prompt 生成中
        'generating',        -- 模型调用中
        'candidates_ready',  -- 候选已产出，待审核
        'reviewing',         -- 审核中
        'approved',          -- 已通过
        'rejected',          -- 已驳回（终态前的中转）
        'regenerating',      -- 重新生成
        'archived',          -- 已归档
        'delivered',         -- 已交付
        'failed_recoverable',-- 可恢复失败（自动重试）
        'failed_terminal'    -- 终态失败（人工介入）
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 任务优先级
DO $$ BEGIN
    CREATE TYPE task_priority AS ENUM ('low', 'normal', 'high', 'urgent');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 单次模型调用记录状态
DO $$ BEGIN
    CREATE TYPE run_status AS ENUM (
        'queued',     -- 入队
        'running',    -- 调用中
        'succeeded',  -- 成功
        'failed',     -- 失败
        'timeout',    -- 超时
        'cancelled'   -- 取消
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 候选物状态
DO $$ BEGIN
    CREATE TYPE candidate_status AS ENUM (
        'new',        -- 新生成
        'in_review',  -- 审核中
        'approved',   -- 通过
        'rejected',   -- 驳回
        'archived',   -- 已归档
        'discarded'   -- 已废弃
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 审核动作
DO $$ BEGIN
    CREATE TYPE audit_action AS ENUM (
        'approve',         -- 通过
        'reject',          -- 驳回
        'request_revision',-- 要求修改
        'comment'          -- 仅评论
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 候选物媒介类型
DO $$ BEGIN
    CREATE TYPE asset_media_type AS ENUM ('image', 'video', 'storyboard', 'script', 'srt');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- prompt 模板用途
DO $$ BEGIN
    CREATE TYPE prompt_purpose AS ENUM (
        'selling_point_extract', -- 卖点拆解
        'image_product',         -- 商品图
        'image_scene',           -- 场景图
        'video_storyboard',      -- 分镜脚本
        'video_shot',            -- 单分镜描述
        'video_prompt',          -- 视频生成 prompt
        'tts_script',            -- 口播文案
        'style_guard'            -- 风格一致性守护
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ----------------------------------------------------------------------------
-- 2. 触发器：自动维护 updated_at
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ----------------------------------------------------------------------------
-- 3. tenants - 租户表
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tenants (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code         TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    contact_name TEXT,
    contact_phone TEXT,
    feishu_app_token TEXT,             -- 飞书多维表 app_token
    oss_bucket   TEXT,                 -- 该租户专属 OSS bucket
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    settings     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE tenants IS '租户主表，单客户场景预留多租户能力';
COMMENT ON COLUMN tenants.code IS '租户短码，N8N 链路标识用';
COMMENT ON COLUMN tenants.feishu_app_token IS '飞书多维表 app_token，用于 OpenAPI 回写';

CREATE INDEX IF NOT EXISTS idx_tenants_active ON tenants(is_active) WHERE is_active = TRUE;

DROP TRIGGER IF EXISTS trg_tenants_updated_at ON tenants;
CREATE TRIGGER trg_tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- ----------------------------------------------------------------------------
-- 4. style_templates - 全局风格模板
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS style_templates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    code            TEXT NOT NULL,
    name            TEXT NOT NULL,
    brand_colors    TEXT[] NOT NULL DEFAULT '{}',          -- 品牌色 hex 数组
    model_features  JSONB NOT NULL DEFAULT '{}'::jsonb,    -- 模特特征：年龄、肤色、身高、发型等
    tone            TEXT,                                   -- 调性描述
    mood_keywords   TEXT[] NOT NULL DEFAULT '{}',          -- 情绪关键词
    forbidden_words TEXT[] NOT NULL DEFAULT '{}',          -- 禁用词
    reference_image_urls TEXT[] NOT NULL DEFAULT '{}',     -- 参考图 URL
    extra           JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, code)
);
COMMENT ON TABLE style_templates IS '全局风格模板：品牌色、模特特征、调性，供产品引用';
COMMENT ON COLUMN style_templates.model_features IS 'JSON 结构: {age_range, skin_tone, height_cm, hair, body_type}';

CREATE INDEX IF NOT EXISTS idx_style_templates_tenant ON style_templates(tenant_id);
CREATE INDEX IF NOT EXISTS idx_style_templates_active ON style_templates(tenant_id, is_active) WHERE is_active = TRUE;

DROP TRIGGER IF EXISTS trg_style_templates_updated_at ON style_templates;
CREATE TRIGGER trg_style_templates_updated_at
    BEFORE UPDATE ON style_templates
    FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- ----------------------------------------------------------------------------
-- 5. products - 产品 SKU 主数据
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    sku                 TEXT NOT NULL,
    name                TEXT NOT NULL,
    category            TEXT,                              -- 内衣 / 运动服 / 瑜伽裤
    selling_points      TEXT[] NOT NULL DEFAULT '{}',     -- 卖点
    target_audience     TEXT,                              -- 目标受众
    use_scenarios       TEXT[] NOT NULL DEFAULT '{}',     -- 使用场景
    primary_color       TEXT,
    alt_colors          TEXT[] NOT NULL DEFAULT '{}',
    sizes               TEXT[] NOT NULL DEFAULT '{}',
    reference_image_urls TEXT[] NOT NULL DEFAULT '{}',    -- 参考图 URL 数组（必填）
    style_template_id   UUID REFERENCES style_templates(id) ON DELETE SET NULL,
    spec                JSONB NOT NULL DEFAULT '{}'::jsonb,-- 物理规格
    extra               JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, sku)
);
COMMENT ON TABLE products IS '产品 SKU 主数据，所有任务和候选物都关联到产品';
COMMENT ON COLUMN products.reference_image_urls IS '客户提供的参考图，至少 1 张';
COMMENT ON COLUMN products.style_template_id IS '该产品默认使用的风格模板';

CREATE INDEX IF NOT EXISTS idx_products_tenant ON products(tenant_id);
CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);
CREATE INDEX IF NOT EXISTS idx_products_style ON products(style_template_id);
CREATE INDEX IF NOT EXISTS idx_products_name_trgm ON products USING gin (name gin_trgm_ops);

DROP TRIGGER IF EXISTS trg_products_updated_at ON products;
CREATE TRIGGER trg_products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- ----------------------------------------------------------------------------
-- 6. prompt_templates - prompt 模板库
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prompt_templates (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    code        TEXT NOT NULL,
    purpose     prompt_purpose NOT NULL,
    name        TEXT NOT NULL,
    body        TEXT NOT NULL,                       -- 模板正文，支持 {{variable}} 占位
    variables   JSONB NOT NULL DEFAULT '[]'::jsonb,  -- 可用变量定义
    model_hint  TEXT,                                 -- 推荐模型（gpt-4o / claude / seedance 等）
    version     INT NOT NULL DEFAULT 1,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, code, version)
);
COMMENT ON TABLE prompt_templates IS 'Prompt 模板库，按 purpose 分类，可版本化';

CREATE INDEX IF NOT EXISTS idx_prompts_tenant_purpose ON prompt_templates(tenant_id, purpose) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_prompts_code ON prompt_templates(code);

DROP TRIGGER IF EXISTS trg_prompt_templates_updated_at ON prompt_templates;
CREATE TRIGGER trg_prompt_templates_updated_at
    BEFORE UPDATE ON prompt_templates
    FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- ----------------------------------------------------------------------------
-- 7. tasks - 生成任务
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    product_id      UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    pipeline        task_pipeline NOT NULL,
    status          task_status NOT NULL DEFAULT 'pending',
    priority        task_priority NOT NULL DEFAULT 'normal',
    title           TEXT NOT NULL,
    requested_count INT NOT NULL DEFAULT 1 CHECK (requested_count > 0),  -- 期望候选数
    parameters      JSONB NOT NULL DEFAULT '{}'::jsonb,                  -- 任务级参数（分辨率、时长、模型等）
    feishu_record_id TEXT,                                                -- 关联飞书任务表的 record_id
    retry_count     INT NOT NULL DEFAULT 0,
    max_retries     INT NOT NULL DEFAULT 3,
    error_message   TEXT,
    created_by      TEXT,                                                 -- 创建人（飞书用户 / 系统）
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE tasks IS '生成任务主表，每条对应一次完整的生成流程';
COMMENT ON COLUMN tasks.pipeline IS 'image=图片链路，video=视频链路';
COMMENT ON COLUMN tasks.feishu_record_id IS '飞书任务进度表 record_id，便于回写';
COMMENT ON COLUMN tasks.parameters IS '示例: {"resolution":"1024x1024","duration_sec":12,"model":"seedance-2.0"}';

CREATE INDEX IF NOT EXISTS idx_tasks_tenant ON tasks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tasks_product ON tasks(product_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_pipeline_status ON tasks(pipeline, status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority_created ON tasks(priority DESC, created_at ASC) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_tasks_feishu_record ON tasks(feishu_record_id) WHERE feishu_record_id IS NOT NULL;

DROP TRIGGER IF EXISTS trg_tasks_updated_at ON tasks;
CREATE TRIGGER trg_tasks_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- ----------------------------------------------------------------------------
-- 8. generation_runs - 每次模型调用记录
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS generation_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    sequence_no     INT NOT NULL,                          -- 同一任务内的第几次调用
    model_provider  TEXT NOT NULL,                         -- volcengine / openai / seedance
    model_name      TEXT NOT NULL,                         -- gpt-4o / seedance-2.0 / sd-xl
    purpose         prompt_purpose,                        -- 这次调用做什么
    prompt_template_id UUID REFERENCES prompt_templates(id) ON DELETE SET NULL,
    input_payload   JSONB NOT NULL,                        -- 入参快照
    output_payload  JSONB,                                 -- 出参（OSS URL、token 数等）
    status          run_status NOT NULL DEFAULT 'queued',
    cost_usd        NUMERIC(10,4) NOT NULL DEFAULT 0,
    cost_cny        NUMERIC(10,4) NOT NULL DEFAULT 0,
    duration_ms     INT,
    error_message   TEXT,
    external_job_id TEXT,                                  -- 第三方平台任务 ID（如 Seedance task_id）
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (task_id, sequence_no)
);
COMMENT ON TABLE generation_runs IS '每次模型调用的入参/出参/成本/耗时记录，便于复盘和成本核算';

CREATE INDEX IF NOT EXISTS idx_runs_task ON generation_runs(task_id);
CREATE INDEX IF NOT EXISTS idx_runs_status ON generation_runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_external_job ON generation_runs(external_job_id) WHERE external_job_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_runs_created ON generation_runs(created_at DESC);

DROP TRIGGER IF EXISTS trg_runs_updated_at ON generation_runs;
CREATE TRIGGER trg_runs_updated_at
    BEFORE UPDATE ON generation_runs
    FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- ----------------------------------------------------------------------------
-- 9. candidates - 候选产物
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS candidates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    run_id          UUID REFERENCES generation_runs(id) ON DELETE SET NULL,
    media_type      asset_media_type NOT NULL,
    oss_url         TEXT NOT NULL,                         -- 主资源 URL
    thumbnail_url   TEXT,                                   -- 缩略图 URL
    file_size_bytes BIGINT,
    width           INT,
    height          INT,
    duration_ms     INT,                                    -- 视频时长
    parameters_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb, -- 参数快照
    prompt_snapshot TEXT,                                    -- 实际使用的 prompt
    status          candidate_status NOT NULL DEFAULT 'new',
    score           NUMERIC(4,2),                            -- 自动评分（可选）
    sequence_no     INT NOT NULL DEFAULT 1,                  -- 同一任务内的第几个候选
    feishu_record_id TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE candidates IS '候选产物：图片/视频/分镜/字幕，是审核与归档的基本单位';
COMMENT ON COLUMN candidates.parameters_snapshot IS '完整复现该产物所需的全部参数';

CREATE INDEX IF NOT EXISTS idx_candidates_task ON candidates(task_id);
CREATE INDEX IF NOT EXISTS idx_candidates_run ON candidates(run_id);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status);
CREATE INDEX IF NOT EXISTS idx_candidates_media_type ON candidates(media_type);
CREATE INDEX IF NOT EXISTS idx_candidates_feishu ON candidates(feishu_record_id) WHERE feishu_record_id IS NOT NULL;

DROP TRIGGER IF EXISTS trg_candidates_updated_at ON candidates;
CREATE TRIGGER trg_candidates_updated_at
    BEFORE UPDATE ON candidates
    FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- ----------------------------------------------------------------------------
-- 10. audit_log - 审核记录
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id  UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    task_id       UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    reviewer      TEXT NOT NULL,                          -- 审核员（飞书 user_id 或姓名）
    action        audit_action NOT NULL,
    comment       TEXT,
    score         NUMERIC(4,2),
    metadata      JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE audit_log IS '所有审核动作流水，append-only，不更新';

CREATE INDEX IF NOT EXISTS idx_audit_candidate ON audit_log(candidate_id);
CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_log(task_id);
CREATE INDEX IF NOT EXISTS idx_audit_reviewer ON audit_log(reviewer);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);

-- ----------------------------------------------------------------------------
-- 11. archive - 归档表
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS archive (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    product_id          UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    task_id             UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    candidate_id        UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    media_type          asset_media_type NOT NULL,
    final_oss_url       TEXT NOT NULL,                    -- 归档地址（独立于候选 OSS，长期存储）
    delivery_path       TEXT,                              -- 客户交付路径（OSS / 飞书 / 本地）
    is_delivered        BOOLEAN NOT NULL DEFAULT FALSE,
    delivered_at        TIMESTAMPTZ,
    delivered_by        TEXT,
    delivery_metadata   JSONB NOT NULL DEFAULT '{}'::jsonb,
    feishu_record_id    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (candidate_id)
);
COMMENT ON TABLE archive IS '最终归档表，1 候选 = 1 归档记录';

CREATE INDEX IF NOT EXISTS idx_archive_tenant ON archive(tenant_id);
CREATE INDEX IF NOT EXISTS idx_archive_product ON archive(product_id);
CREATE INDEX IF NOT EXISTS idx_archive_delivered ON archive(is_delivered);
CREATE INDEX IF NOT EXISTS idx_archive_created ON archive(created_at DESC);

DROP TRIGGER IF EXISTS trg_archive_updated_at ON archive;
CREATE TRIGGER trg_archive_updated_at
    BEFORE UPDATE ON archive
    FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- ----------------------------------------------------------------------------
-- 12. 视图
-- ----------------------------------------------------------------------------

-- 待审核候选物视图
CREATE OR REPLACE VIEW v_pending_review AS
SELECT
    c.id              AS candidate_id,
    c.media_type,
    c.oss_url,
    c.thumbnail_url,
    c.sequence_no,
    c.created_at      AS candidate_created_at,
    t.id              AS task_id,
    t.title           AS task_title,
    t.pipeline,
    t.priority,
    p.sku,
    p.name            AS product_name,
    p.tenant_id
FROM candidates c
JOIN tasks t      ON t.id = c.task_id
JOIN products p   ON p.id = t.product_id
WHERE c.status IN ('new', 'in_review')
  AND t.status IN ('candidates_ready', 'reviewing')
ORDER BY t.priority DESC, c.created_at ASC;

COMMENT ON VIEW v_pending_review IS '所有待审核的候选物，含产品和任务上下文';

-- 当日产能视图
CREATE OR REPLACE VIEW v_today_throughput AS
SELECT
    p.tenant_id,
    t.pipeline,
    COUNT(DISTINCT t.id)  FILTER (WHERE t.status IN ('approved','archived','delivered'))   AS approved_tasks,
    COUNT(DISTINCT t.id)  FILTER (WHERE t.status = 'failed_terminal')                       AS failed_tasks,
    COUNT(DISTINCT c.id)                                                                    AS candidates_generated,
    COUNT(DISTINCT c.id)  FILTER (WHERE c.status = 'approved')                              AS candidates_approved,
    COALESCE(SUM(r.cost_cny), 0)                                                            AS total_cost_cny,
    COALESCE(SUM(r.duration_ms), 0)                                                         AS total_duration_ms
FROM tasks t
JOIN products p           ON p.id = t.product_id
LEFT JOIN candidates c    ON c.task_id = t.id AND c.created_at >= date_trunc('day', now())
LEFT JOIN generation_runs r ON r.task_id = t.id AND r.created_at >= date_trunc('day', now())
WHERE t.created_at >= date_trunc('day', now())
GROUP BY p.tenant_id, t.pipeline;

COMMENT ON VIEW v_today_throughput IS '当日按租户+链路汇总：完成任务数、产出候选数、总成本';

-- 任务完整状态视图（含最新候选数）
CREATE OR REPLACE VIEW v_task_overview AS
SELECT
    t.id,
    t.tenant_id,
    t.title,
    t.pipeline,
    t.status,
    t.priority,
    p.sku,
    p.name AS product_name,
    t.requested_count,
    (SELECT COUNT(*) FROM candidates c WHERE c.task_id = t.id) AS candidates_total,
    (SELECT COUNT(*) FROM candidates c WHERE c.task_id = t.id AND c.status = 'approved') AS candidates_approved,
    t.retry_count,
    t.created_at,
    t.updated_at
FROM tasks t
JOIN products p ON p.id = t.product_id;

COMMENT ON VIEW v_task_overview IS '任务总览，飞书任务进度表的数据源视图';

-- ----------------------------------------------------------------------------
-- 13. SEED DATA - YN-BRA-001 完整样品
-- ----------------------------------------------------------------------------

-- 13.1 租户
INSERT INTO tenants (id, code, name, contact_name, oss_bucket, settings)
VALUES (
    '11111111-1111-1111-1111-111111111111',
    'YINI',
    '伊妮运动服饰',
    '飞飞',
    'yini-content-factory',
    '{"timezone":"Asia/Shanghai","default_locale":"zh-CN"}'::jsonb
) ON CONFLICT (code) DO NOTHING;

-- 13.2 风格模板
INSERT INTO style_templates (
    id, tenant_id, code, name, brand_colors, model_features, tone, mood_keywords,
    forbidden_words, reference_image_urls, extra
)
VALUES (
    '22222222-2222-2222-2222-222222222222',
    '11111111-1111-1111-1111-111111111111',
    'YINI-SPORT-V1',
    '伊妮运动主调-V1',
    ARRAY['#000000', '#3A3A3A', '#FFFFFF', '#FF3366'],
    '{"age_range":"25-35","skin_tone":"亚洲健康肤色","height_cm":"168-175","body_type":"匀称运动型","hair":"中长马尾或低马尾"}'::jsonb,
    '专业、清爽、力量感、不过度性感',
    ARRAY['active','energetic','confident','minimal','clean'],
    ARRAY['性感','低俗','blur','low quality'],
    ARRAY['https://oss.example.com/refs/yini/style_v1_01.jpg','https://oss.example.com/refs/yini/style_v1_02.jpg'],
    '{"lighting":"自然光为主，柔和侧光","background":"健身房/瑜伽馆/户外街道"}'::jsonb
) ON CONFLICT (tenant_id, code) DO NOTHING;

-- 13.3 产品
INSERT INTO products (
    id, tenant_id, sku, name, category, selling_points, target_audience,
    use_scenarios, primary_color, alt_colors, sizes, reference_image_urls,
    style_template_id, spec, extra
)
VALUES (
    '33333333-3333-3333-3333-333333333333',
    '11111111-1111-1111-1111-111111111111',
    'YN-BRA-001',
    '黑色高弹速干运动内衣（前拉链款）',
    '运动内衣',
    ARRAY['透气网眼面料','前置拉链穿脱方便','高弹力支撑','速干'],
    '25-40 岁运动女性',
    ARRAY['瑜伽馆','跑步','健身房','户外'],
    '黑色',
    ARRAY['深灰'],
    ARRAY['S','M','L','XL'],
    ARRAY[
        'https://oss.example.com/refs/YN-BRA-001/front.jpg',
        'https://oss.example.com/refs/YN-BRA-001/back.jpg',
        'https://oss.example.com/refs/YN-BRA-001/detail_zip.jpg'
    ],
    '22222222-2222-2222-2222-222222222222',
    '{"fabric":"聚酯纤维 88% 氨纶 12%","support_level":"中高强度","cup":"无钢圈一体","care":"机洗冷水"}'::jsonb,
    '{"price_cny":159,"weight_g":130}'::jsonb
) ON CONFLICT (tenant_id, sku) DO NOTHING;

-- 13.4 Prompt 模板（5 条覆盖核心 purpose）
INSERT INTO prompt_templates (id, tenant_id, code, purpose, name, body, variables, model_hint, version)
VALUES
(
    '44444444-4444-4444-4444-444444444401',
    '11111111-1111-1111-1111-111111111111',
    'TPL-SP-EXTRACT',
    'selling_point_extract',
    '卖点拆解-标准版',
    '你是服装电商内容策划。请基于以下产品信息，拆解出 3-5 个最有传播力的卖点，每个卖点需指出对应的【场景】和【目标人群感受】。\n产品名称：{{product_name}}\n产品规格：{{spec}}\n原始卖点：{{selling_points}}\n输出 JSON：{"points":[{"point":"","scene":"","feeling":""}]}',
    '[{"name":"product_name","required":true},{"name":"spec","required":true},{"name":"selling_points","required":true}]'::jsonb,
    'gpt-4o',
    1
),
(
    '44444444-4444-4444-4444-444444444402',
    '11111111-1111-1111-1111-111111111111',
    'TPL-IMG-PRODUCT',
    'image_product',
    '商品图-白底高保真',
    'A high-fidelity studio product photo of {{product_name}}. Pure white background, soft even studio lighting, sharp focus, true-to-life {{primary_color}} fabric color, no model. Show {{view}} view. Ultra detail on {{detail_focus}}. 1024x1024, photorealistic, e-commerce quality.',
    '[{"name":"product_name","required":true},{"name":"primary_color","required":true},{"name":"view","required":true,"default":"front"},{"name":"detail_focus","required":true}]'::jsonb,
    'sd-xl-1.0',
    1
),
(
    '44444444-4444-4444-4444-444444444403',
    '11111111-1111-1111-1111-111111111111',
    'TPL-IMG-SCENE',
    'image_scene',
    '场景图-运动情境',
    'A {{age_range}} Asian fit female model wearing {{product_name}} in a {{scene}} scene. {{tone}}. Brand colors {{brand_colors}}. Natural lighting, candid composition, focus on athletic confidence, no oversexualization. 1024x1280.',
    '[{"name":"product_name","required":true},{"name":"scene","required":true},{"name":"age_range","required":true},{"name":"tone","required":true},{"name":"brand_colors","required":true}]'::jsonb,
    'sd-xl-1.0',
    1
),
(
    '44444444-4444-4444-4444-444444444404',
    '11111111-1111-1111-1111-111111111111',
    'TPL-VID-STORYBOARD',
    'video_storyboard',
    '视频分镜脚本-12秒',
    '为 {{product_name}} 生成 12 秒短视频分镜脚本，目标平台 TikTok。要求 3-4 个分镜，每镜 3-4 秒，按"痛点-解决-场景展示-行动召唤"结构推进。卖点：{{selling_points}}。场景候选：{{scenarios}}。\n输出 JSON：{"shots":[{"index":1,"duration_s":3,"description":"","camera":"","action":"","caption":""}]}',
    '[{"name":"product_name","required":true},{"name":"selling_points","required":true},{"name":"scenarios","required":true}]'::jsonb,
    'gpt-4o',
    1
),
(
    '44444444-4444-4444-4444-444444444405',
    '11111111-1111-1111-1111-111111111111',
    'TPL-VID-PROMPT',
    'video_prompt',
    'Seedance 视频生成-单镜',
    'Subject: {{subject}}. Action: {{action}}. Camera: {{camera}}. Setting: {{setting}}. Style: photorealistic, soft natural light, e-commerce-grade. Duration: {{duration_s}}s. Aspect 9:16. Audio: native ambient.',
    '[{"name":"subject","required":true},{"name":"action","required":true},{"name":"camera","required":true},{"name":"setting","required":true},{"name":"duration_s","required":true,"default":3}]'::jsonb,
    'seedance-2.0',
    1
)
ON CONFLICT (tenant_id, code, version) DO NOTHING;

-- 13.5 任务：image 链路
INSERT INTO tasks (
    id, tenant_id, product_id, pipeline, status, priority, title,
    requested_count, parameters, feishu_record_id, created_by
)
VALUES (
    '55555555-5555-5555-5555-555555555501',
    '11111111-1111-1111-1111-111111111111',
    '33333333-3333-3333-3333-333333333333',
    'image',
    'pending',
    'high',
    'YN-BRA-001 首期图片打样：白底图 + 4 场景图',
    8,
    '{"resolution":"1024x1280","views":["front","back","detail"],"scenes":["yoga_studio","running_outdoor","gym","outdoor_street"],"model_image":"sd-xl-1.0","model_text":"gpt-4o"}'::jsonb,
    'recXXXIMG001',
    '飞飞'
) ON CONFLICT (id) DO NOTHING;

-- 13.6 任务：video 链路
INSERT INTO tasks (
    id, tenant_id, product_id, pipeline, status, priority, title,
    requested_count, parameters, feishu_record_id, created_by
)
VALUES (
    '55555555-5555-5555-5555-555555555502',
    '11111111-1111-1111-1111-111111111111',
    '33333333-3333-3333-3333-333333333333',
    'video',
    'pending',
    'high',
    'YN-BRA-001 首期视频打样：12 秒 TikTok 短视频',
    3,
    '{"duration_sec":12,"aspect":"9:16","model":"seedance-2.0","with_subtitle":true,"audio":"native","fallback_tts":"volcengine_tts"}'::jsonb,
    'recXXXVID001',
    '飞飞'
) ON CONFLICT (id) DO NOTHING;

COMMIT;

-- ----------------------------------------------------------------------------
-- 14. 验证查询（可选，部署后手动执行）
-- ----------------------------------------------------------------------------
-- SELECT 'tenants' AS t, COUNT(*) FROM tenants
-- UNION ALL SELECT 'style_templates', COUNT(*) FROM style_templates
-- UNION ALL SELECT 'products', COUNT(*) FROM products
-- UNION ALL SELECT 'prompt_templates', COUNT(*) FROM prompt_templates
-- UNION ALL SELECT 'tasks', COUNT(*) FROM tasks;
--
-- SELECT * FROM v_task_overview;
-- SELECT * FROM v_pending_review;
-- SELECT * FROM v_today_throughput;

-- ============================================================================
-- 自动给当前数据库设默认 search_path，这样后续任何连接（含 N8N Postgres 节点）
-- 都默认在 content_factory schema 找表，不需要每条 query 都加 schema 前缀。
-- 注意：DDL 不会立即影响已建立的连接，需新连接生效。
-- ============================================================================
DO $$
BEGIN
    EXECUTE format('ALTER DATABASE %I SET search_path TO content_factory, public',
                   current_database());
END $$;

-- ============================================================================
-- 兼容层：补 enum 值，让 N8N workflow 用到的状态字面量都合法
-- workflow 用的 'partial'（run_status）和 'pending_review'/'failed'（candidate_status）
-- 都不在原始 enum 里，这里补全（必须在重写 query 之前先扩 enum）
-- 注意：ALTER TYPE ADD VALUE 不能在 transaction 块里跑，所以必须独立语句
-- ============================================================================
DO $$ BEGIN
    ALTER TYPE run_status ADD VALUE IF NOT EXISTS 'partial';
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TYPE candidate_status ADD VALUE IF NOT EXISTS 'pending_review';
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TYPE candidate_status ADD VALUE IF NOT EXISTS 'failed';
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
