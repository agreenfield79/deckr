-- init_schema.sql — PostgreSQL DDL for cloud / Docker mode.
-- For local SQLite: schema is created by Base.metadata.create_all() on startup (D-2).
-- Run once: psql -U deckr -d deckr_db -f migrations/init_schema.sql
--
-- Execution order matters: ENUMs first, then parent tables, then child tables.

-- ──────────────────────────────────────────────────────────
-- Named ENUM types (Convention 2)
-- ──────────────────────────────────────────────────────────
CREATE TYPE deal_status AS ENUM ('draft', 'review', 'approved', 'declined');
CREATE TYPE extraction_status AS ENUM ('pending', 'running', 'complete', 'partial', 'failed');
CREATE TYPE pipeline_status AS ENUM ('pending', 'running', 'complete', 'failed', 'partial');
CREATE TYPE covenant_status AS ENUM ('compliant', 'tight', 'breach', 'waived');
CREATE TYPE source_agent_type AS ENUM ('risk', 'review');

-- pgvector extension (required for embeddings table)
CREATE EXTENSION IF NOT EXISTS vector;

-- ──────────────────────────────────────────────────────────
-- Tier 1 — Root tables (no FK dependencies)
-- ──────────────────────────────────────────────────────────
CREATE TABLE workspaces (
    workspace_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_path    TEXT NOT NULL UNIQUE,
    borrower_name   VARCHAR(255),
    deal_id         UUID,           -- FK set after deals table exists (ALTER below)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ
);

CREATE TABLE deals (
    deal_id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id            UUID NOT NULL REFERENCES workspaces(workspace_id),
    borrower_entity_name    VARCHAR(255) NOT NULL,
    entity_structure        VARCHAR(50),
    requested_loan_amount   NUMERIC(18,2),
    loan_purpose            TEXT,
    naics_code              VARCHAR(10),
    status                  deal_status DEFAULT 'draft',
    created_at              TIMESTAMPTZ NOT NULL,
    updated_at              TIMESTAMPTZ
);

ALTER TABLE workspaces
    ADD CONSTRAINT fk_workspace_deal
    FOREIGN KEY (deal_id) REFERENCES deals(deal_id) ON DELETE SET NULL;

-- ──────────────────────────────────────────────────────────
-- Tier 2 — Deal-scoped tables (FK → deals, Pattern A cascade)
-- ──────────────────────────────────────────────────────────
CREATE TABLE entities (
    entity_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id                 UUID NOT NULL REFERENCES deals(deal_id) ON DELETE CASCADE,
    entity_type             VARCHAR(30) NOT NULL,
    legal_name              VARCHAR(255) NOT NULL,
    tax_id_masked           VARCHAR(20),
    state_of_incorporation  CHAR(2),
    years_in_business       INT,
    created_at              TIMESTAMPTZ
);

CREATE TABLE documents (
    document_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id        UUID REFERENCES workspaces(workspace_id),
    deal_id             UUID REFERENCES deals(deal_id) ON DELETE CASCADE,
    entity_id           UUID REFERENCES entities(entity_id),
    file_name           TEXT NOT NULL,
    file_path           TEXT NOT NULL,
    document_type       VARCHAR(30) NOT NULL,
    upload_timestamp    TIMESTAMPTZ NOT NULL,
    extraction_status   extraction_status DEFAULT 'pending',
    extracted_at        TIMESTAMPTZ,
    content_hash        CHAR(64),
    page_count          INT,
    file_size_bytes     BIGINT
);

CREATE TABLE pipeline_runs (
    pipeline_run_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id                 UUID REFERENCES deals(deal_id) ON DELETE CASCADE,
    workspace_id            UUID REFERENCES workspaces(workspace_id),
    started_at              TIMESTAMPTZ NOT NULL,
    completed_at            TIMESTAMPTZ,
    status                  pipeline_status,
    stages_completed        JSONB,
    total_duration_seconds  INT
);

CREATE TABLE loan_terms (
    loan_terms_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id                     UUID NOT NULL REFERENCES deals(deal_id) ON DELETE CASCADE,
    loan_amount                 NUMERIC(18,2) NOT NULL,
    interest_rate               NUMERIC(8,6),
    rate_type                   VARCHAR(20),
    amortization_years          INT,
    term_months                 INT,
    proposed_annual_debt_service NUMERIC(18,2),
    covenant_definitions        JSONB,
    revolver_availability       NUMERIC(18,2),
    created_at                  TIMESTAMPTZ,
    UNIQUE (deal_id)
);

CREATE TABLE collateral (
    collateral_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id         UUID REFERENCES deals(deal_id) ON DELETE CASCADE,
    document_id     UUID REFERENCES documents(document_id),
    collateral_type VARCHAR(30),
    description     TEXT,
    appraised_value NUMERIC(18,2),
    appraisal_date  DATE,
    ltv_ratio       NUMERIC(5,4),
    lien_position   INT,
    address         TEXT
);

CREATE TABLE slacr_scores (
    score_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id             UUID REFERENCES deals(deal_id) ON DELETE CASCADE,
    pipeline_run_id     UUID REFERENCES pipeline_runs(pipeline_run_id),
    sponsor_score       NUMERIC(5,2),
    leverage_score      NUMERIC(5,2),
    asset_quality_score NUMERIC(5,2),
    cash_flow_score     NUMERIC(5,2),
    risk_score          NUMERIC(5,2),
    composite_score     NUMERIC(5,2),
    internal_rating     VARCHAR(20) NOT NULL,
    occ_classification  VARCHAR(30) NOT NULL,
    model_version       VARCHAR(20),
    shap_values         JSONB,
    lime_values         JSONB,
    computed_at         TIMESTAMPTZ
);

CREATE TABLE covenants (
    covenant_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id         UUID REFERENCES deals(deal_id) ON DELETE CASCADE,
    pipeline_run_id UUID REFERENCES pipeline_runs(pipeline_run_id),
    covenant_type   VARCHAR(20),
    description     TEXT,
    metric          VARCHAR(50),
    threshold_value NUMERIC(10,4),
    actual_value    NUMERIC(10,4),
    unit            VARCHAR(20),
    pass_fail       BOOLEAN,
    source_agent    source_agent_type NOT NULL
);

CREATE TABLE audit_log (
    log_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id         UUID REFERENCES deals(deal_id) ON DELETE CASCADE,
    session_id      VARCHAR(128),
    actor_ip        VARCHAR(45),
    action_type     VARCHAR(30) NOT NULL,
    route           TEXT,
    target_path     TEXT,
    target_table    VARCHAR(50),
    agent_name      VARCHAR(50),
    metadata        JSONB,
    status_code     INT,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_audit_log_timestamp ON audit_log (timestamp DESC);
CREATE INDEX ix_audit_log_session ON audit_log (session_id, timestamp);

CREATE TABLE personal_financial_statements (
    pfs_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id           UUID REFERENCES entities(entity_id),
    document_id         UUID REFERENCES documents(document_id),
    as_of_date          DATE,
    cash_savings        NUMERIC(18,2),
    real_estate_value   NUMERIC(18,2),
    retirement_accounts NUMERIC(18,2),
    other_assets        NUMERIC(18,2),
    total_assets        NUMERIC(18,2),
    mortgage_balance    NUMERIC(18,2),
    auto_loans          NUMERIC(18,2),
    other_liabilities   NUMERIC(18,2),
    total_liabilities   NUMERIC(18,2),
    net_worth           NUMERIC(18,2),
    annual_income       NUMERIC(18,2),
    monthly_obligations NUMERIC(18,2),
    extracted_at        TIMESTAMPTZ,
    deal_id             UUID REFERENCES deals(deal_id) ON DELETE CASCADE
);

CREATE TABLE covenant_compliance_projections (
    compliance_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id             UUID REFERENCES deals(deal_id) ON DELETE CASCADE,
    pipeline_run_id     UUID REFERENCES pipeline_runs(pipeline_run_id),
    scenario            VARCHAR(10) NOT NULL,
    projection_year     INT NOT NULL,
    covenant_type       VARCHAR(40) NOT NULL,
    formula             TEXT,
    threshold_value     NUMERIC(10,4),
    threshold_operator  VARCHAR(5),
    computed_value      NUMERIC(10,4),
    headroom_pct        NUMERIC,
    status              covenant_status,
    is_breach_year      BOOLEAN DEFAULT FALSE,
    trigger_action      TEXT,
    UNIQUE (deal_id, pipeline_run_id, scenario, projection_year, covenant_type)
);

-- ──────────────────────────────────────────────────────────
-- Tier 3 — Entity-scoped tables (Pattern B indirect cascade)
-- ──────────────────────────────────────────────────────────
CREATE TABLE income_statements (
    statement_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id                   UUID NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
    document_id                 UUID REFERENCES documents(document_id),
    fiscal_year                 INT NOT NULL,
    fiscal_year_end             DATE,
    period_type                 VARCHAR(10) DEFAULT 'annual',
    revenue                     NUMERIC(18,2),
    revenue_segments            JSONB,
    cost_of_goods_sold          NUMERIC(18,2),
    cogs_product                NUMERIC(18,2),
    cogs_services               NUMERIC(18,2),
    gross_profit                NUMERIC(18,2),
    research_and_development    NUMERIC(18,2),
    selling_general_administrative NUMERIC(18,2),
    stock_based_compensation    NUMERIC(18,2),
    restructuring_charges       NUMERIC(18,2),
    operating_expenses          NUMERIC(18,2),
    ebitda                      NUMERIC(18,2),
    depreciation_amortization   NUMERIC(18,2),
    ebit                        NUMERIC(18,2),
    interest_expense            NUMERIC(18,2),
    pre_tax_income              NUMERIC(18,2),
    effective_tax_rate          NUMERIC(8,6),
    tax_expense                 NUMERIC(18,2),
    net_income                  NUMERIC(18,2),
    extracted_at                TIMESTAMPTZ,
    UNIQUE (entity_id, fiscal_year, period_type)
);

CREATE TABLE balance_sheets (
    balance_sheet_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id                   UUID REFERENCES entities(entity_id) ON DELETE CASCADE,
    document_id                 UUID REFERENCES documents(document_id),
    as_of_date                  DATE NOT NULL,
    cash_and_equivalents        NUMERIC(18,2),
    accounts_receivable         NUMERIC(18,2),
    days_sales_outstanding      NUMERIC(8,2),
    inventory                   NUMERIC(18,2),
    days_inventory_outstanding  NUMERIC(8,2),
    deferred_revenue            NUMERIC(18,2),
    accrued_liabilities         NUMERIC(18,2),
    other_current_assets        NUMERIC(18,2),
    total_current_assets        NUMERIC(18,2),
    pp_e_net                    NUMERIC(18,2),
    other_long_term_assets      NUMERIC(18,2),
    total_assets                NUMERIC(18,2),
    accounts_payable            NUMERIC(18,2),
    days_payable_outstanding    NUMERIC(8,2),
    short_term_debt             NUMERIC(18,2),
    other_current_liabilities   NUMERIC(18,2),
    total_current_liabilities   NUMERIC(18,2),
    long_term_debt              NUMERIC(18,2),
    funded_debt_rate_type       VARCHAR(20),
    weighted_avg_interest_rate  NUMERIC(8,6),
    debt_maturity_schedule      JSONB,
    other_long_term_liabilities NUMERIC(18,2),
    total_liabilities           NUMERIC(18,2),
    distributions               NUMERIC(18,2),
    retained_earnings           NUMERIC(18,2),
    total_equity                NUMERIC(18,2),
    extracted_at                TIMESTAMPTZ
);

CREATE TABLE cash_flow_statements (
    cashflow_id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id                   UUID REFERENCES entities(entity_id) ON DELETE CASCADE,
    document_id                 UUID REFERENCES documents(document_id),
    fiscal_year                 INT NOT NULL,
    operating_cash_flow         NUMERIC(18,2),
    stock_based_compensation    NUMERIC(18,2),
    working_capital_change      NUMERIC(18,2),
    working_capital_change_detail JSONB,
    capital_expenditures        NUMERIC(18,2),
    maintenance_capex           NUMERIC(18,2),
    growth_capex                NUMERIC(18,2),
    acquisitions                NUMERIC(18,2),
    investing_cash_flow         NUMERIC(18,2),
    debt_repayment              NUMERIC(18,2),
    share_repurchases           NUMERIC(18,2),
    financing_cash_flow         NUMERIC(18,2),
    net_change_in_cash          NUMERIC(18,2),
    free_cash_flow              NUMERIC(18,2),
    normalized_free_cash_flow   NUMERIC(18,2),
    extracted_at                TIMESTAMPTZ
);

CREATE TABLE financial_ratios (
    ratio_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id               UUID REFERENCES entities(entity_id) ON DELETE CASCADE,
    pipeline_run_id         UUID REFERENCES pipeline_runs(pipeline_run_id),
    fiscal_year             INT NOT NULL,
    dscr                    NUMERIC,
    fixed_charge_coverage   NUMERIC,
    leverage_ratio          NUMERIC,
    funded_debt_to_ebitda   NUMERIC,
    current_ratio           NUMERIC,
    quick_ratio             NUMERIC,
    debt_to_equity          NUMERIC,
    ebitda_margin           NUMERIC,
    net_profit_margin       NUMERIC,
    return_on_assets        NUMERIC,
    computed_at             TIMESTAMPTZ
);

CREATE TABLE forecasts (
    forecast_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id           UUID REFERENCES entities(entity_id) ON DELETE CASCADE,
    pipeline_run_id     UUID REFERENCES pipeline_runs(pipeline_run_id),
    metric              VARCHAR(30),
    forecast_period     DATE,
    forecast_value      NUMERIC(18,2),
    confidence_lower    NUMERIC(18,2),
    confidence_upper    NUMERIC(18,2),
    model_version       VARCHAR(50),
    computed_at         TIMESTAMPTZ
);

CREATE TABLE revenue_segments (
    segment_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id           UUID NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
    statement_id        UUID REFERENCES income_statements(statement_id),
    fiscal_year         INT NOT NULL,
    segment_name        VARCHAR(100) NOT NULL,
    segment_revenue     NUMERIC(18,2),
    pct_of_total_revenue NUMERIC,
    yoy_growth          NUMERIC,
    UNIQUE (entity_id, fiscal_year, segment_name)
);

CREATE TABLE management_guidance (
    guidance_id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id                   UUID REFERENCES entities(entity_id) ON DELETE CASCADE,
    document_id                 UUID REFERENCES documents(document_id),
    extracted_at                TIMESTAMPTZ,
    guidance_period             VARCHAR(20),
    next_year_revenue_low       NUMERIC(18,2),
    next_year_revenue_mid       NUMERIC(18,2),
    next_year_revenue_high      NUMERIC(18,2),
    next_year_ebitda_margin     NUMERIC(8,6),
    growth_drivers              JSONB,
    risk_factors                JSONB,
    source_text                 TEXT
);

CREATE TABLE projections (
    projection_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id                   UUID REFERENCES entities(entity_id) ON DELETE CASCADE,
    deal_id                     UUID REFERENCES deals(deal_id),
    pipeline_run_id             UUID REFERENCES pipeline_runs(pipeline_run_id),
    scenario                    VARCHAR(10) NOT NULL,
    projection_year             INT NOT NULL,
    projection_date             DATE,
    revenue                     NUMERIC(18,2),
    ebitda                      NUMERIC(18,2),
    ebit                        NUMERIC(18,2),
    net_income                  NUMERIC(18,2),
    operating_cash_flow         NUMERIC(18,2),
    capital_expenditures        NUMERIC(18,2),
    free_cash_flow              NUMERIC(18,2),
    dscr                        NUMERIC,
    funded_debt                 NUMERIC(18,2),
    funded_debt_to_ebitda       NUMERIC,
    ending_cash                 NUMERIC(18,2),
    revenue_growth_assumption   NUMERIC(8,6),
    ebitda_margin_assumption    NUMERIC(8,6),
    computed_at                 TIMESTAMPTZ,
    UNIQUE (entity_id, pipeline_run_id, scenario, projection_year)
);

-- pgvector embeddings table (PostgreSQL only — ChromaDB used locally)
CREATE TABLE embeddings (
    embedding_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID REFERENCES documents(document_id) ON DELETE CASCADE,
    chunk_index     INT NOT NULL,
    chunk_text      TEXT,
    embedding       vector(768),        -- IBM Slate 768-dim output
    model_name      VARCHAR(100),
    created_at      TIMESTAMPTZ
);
CREATE INDEX ix_embeddings_document ON embeddings (document_id);
-- ANN index (IVFFlat; tune lists after table has >10k rows)
-- CREATE INDEX ix_embeddings_ann ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Pipeline stage logs (cascades via pipeline_runs → deals)
CREATE TABLE pipeline_stage_logs (
    log_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_run_id     UUID REFERENCES pipeline_runs(pipeline_run_id) ON DELETE CASCADE,
    agent_name          VARCHAR(50) NOT NULL,
    stage_order         INT,
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    duration_seconds    INT,
    output_file_path    TEXT,
    status              pipeline_status,
    token_count_input   INT,
    token_count_output  INT
);

-- ──────────────────────────────────────────────────────────
-- SQL Views (Layer 3 — read-only query helpers for agents + API)
-- ──────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW v_financial_summary AS
SELECT
    is.entity_id,
    is.fiscal_year,
    is.revenue,
    is.ebitda,
    is.net_income,
    bs.total_assets,
    bs.total_liabilities,
    bs.total_equity,
    cf.operating_cash_flow,
    cf.free_cash_flow
FROM income_statements is
LEFT JOIN balance_sheets bs
    ON bs.entity_id = is.entity_id AND bs.as_of_date = is.fiscal_year_end
LEFT JOIN cash_flow_statements cf
    ON cf.entity_id = is.entity_id AND cf.fiscal_year = is.fiscal_year;

CREATE OR REPLACE VIEW v_ratio_dashboard AS
SELECT
    fr.ratio_id,
    fr.entity_id,
    fr.fiscal_year,
    fr.pipeline_run_id,
    fr.dscr                  AS historical_dscr,
    fr.fixed_charge_coverage,
    fr.leverage_ratio,
    fr.funded_debt_to_ebitda,
    fr.current_ratio,
    fr.ebitda_margin,
    fr.computed_at,
    d.deal_id,
    d.borrower_entity_name,
    d.naics_code
FROM financial_ratios fr
JOIN entities e ON e.entity_id = fr.entity_id
JOIN deals d ON d.deal_id = e.deal_id;

CREATE OR REPLACE VIEW v_covenant_tracker AS
SELECT
    c.covenant_id,
    c.deal_id,
    c.pipeline_run_id,
    c.metric,
    c.description,
    c.threshold_value,
    c.actual_value,
    c.pass_fail,
    c.source_agent,
    lt.proposed_annual_debt_service,
    c.actual_value                   AS covenant_test_dscr
FROM covenants c
LEFT JOIN loan_terms lt ON lt.deal_id = c.deal_id;

CREATE OR REPLACE VIEW v_slacr_components AS
SELECT
    ss.score_id,
    ss.deal_id,
    ss.pipeline_run_id,
    ss.sponsor_score,
    ss.leverage_score,
    ss.asset_quality_score,
    ss.cash_flow_score,
    ss.risk_score,
    ss.composite_score,
    ss.internal_rating,
    ss.occ_classification,
    ss.shap_values,
    ss.lime_values,
    ss.computed_at,
    fr.dscr AS historical_dscr
FROM slacr_scores ss
LEFT JOIN entities e ON e.deal_id = ss.deal_id
LEFT JOIN financial_ratios fr
    ON fr.entity_id = e.entity_id AND fr.pipeline_run_id = ss.pipeline_run_id;

CREATE OR REPLACE VIEW v_pipeline_history AS
SELECT
    pr.pipeline_run_id,
    pr.deal_id,
    pr.started_at,
    pr.completed_at,
    pr.status,
    pr.total_duration_seconds,
    pr.stages_completed,
    d.borrower_entity_name
FROM pipeline_runs pr
JOIN deals d ON d.deal_id = pr.deal_id
ORDER BY pr.started_at DESC;
