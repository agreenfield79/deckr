-- init_schema.sql — PostgreSQL DDL for cloud / Docker mode (Phase 3B target schema).
-- For local SQLite: schema is created by Base.metadata.create_all() + alembic upgrade head.
-- Run once on a fresh PostgreSQL instance:
--   psql -U deckr -d deckr_db -f migrations/init_schema.sql
--
-- Execution order matters: ENUMs → root tables → child tables → indexes → views.

-- ──────────────────────────────────────────────────────────────────────────────
-- Named ENUM types (string-backed in ORM via native_enum=False)
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TYPE deal_status       AS ENUM ('draft', 'review', 'approved', 'declined', 'closed');
CREATE TYPE extraction_status AS ENUM ('pending', 'running', 'complete', 'partial', 'failed');
CREATE TYPE pipeline_status   AS ENUM ('pending', 'running', 'complete', 'failed', 'partial');
CREATE TYPE covenant_status   AS ENUM ('compliant', 'tight', 'breach', 'waived');
CREATE TYPE source_agent_type AS ENUM ('risk', 'review', 'financial', 'collateral', 'guarantor', 'industry', 'packaging', 'extraction');
CREATE TYPE contact_type      AS ENUM ('primary', 'legal', 'cpa', 'appraiser', 'relationship_manager', 'lender');
CREATE TYPE guarantee_type    AS ENUM ('full', 'limited', 'completion', 'payment', 'performance');
CREATE TYPE user_role         AS ENUM ('analyst', 'underwriter', 'approver', 'admin', 'readonly');
CREATE TYPE access_level      AS ENUM ('read', 'write', 'approve');

-- pgvector extension (required for embeddings table)
CREATE EXTENSION IF NOT EXISTS vector;

-- ──────────────────────────────────────────────────────────────────────────────
-- Group A — Deal & Entity Core
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE workspaces (
    workspace_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_path    TEXT NOT NULL UNIQUE,
    borrower_name   VARCHAR(255),
    deal_id         UUID,   -- FK set after deals table exists (ALTER below)
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
    pipeline_version        VARCHAR(20),
    storage_backend         VARCHAR(20) DEFAULT 'local',
    created_at              TIMESTAMPTZ NOT NULL,
    updated_at              TIMESTAMPTZ
);

ALTER TABLE workspaces
    ADD CONSTRAINT fk_workspace_deal
    FOREIGN KEY (deal_id) REFERENCES deals(deal_id) ON DELETE SET NULL;

CREATE TABLE entities (
    entity_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id                 UUID NOT NULL REFERENCES deals(deal_id) ON DELETE CASCADE,
    entity_type             VARCHAR(30) NOT NULL,
    legal_name              VARCHAR(255) NOT NULL,
    tax_id_masked           VARCHAR(20),
    state_of_incorporation  CHAR(2),
    years_in_business       INT,
    role                    VARCHAR(30),
    dba                     VARCHAR(255),
    ein                     VARCHAR(15),
    created_at              TIMESTAMPTZ
);

CREATE TABLE contacts (
    contact_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id       UUID REFERENCES entities(entity_id) ON DELETE CASCADE,
    deal_id         UUID REFERENCES deals(deal_id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    title           VARCHAR(100),
    email           VARCHAR(255),
    phone           VARCHAR(30),
    contact_type    contact_type NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ix_contacts_deal_id    ON contacts (deal_id);
CREATE INDEX ix_contacts_entity_id  ON contacts (entity_id);

-- ──────────────────────────────────────────────────────────────────────────────
-- Group C — Industry & Benchmarks
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE benchmarks (
    benchmark_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    naics_code      VARCHAR(10) NOT NULL,
    metric_name     VARCHAR(50) NOT NULL,
    percentile_25   NUMERIC(10,4),
    percentile_50   NUMERIC(10,4),
    percentile_75   NUMERIC(10,4),
    source          VARCHAR(100),
    as_of_year      INT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (naics_code, metric_name, as_of_year)
);
CREATE INDEX ix_benchmarks_naics  ON benchmarks (naics_code);
CREATE INDEX ix_benchmarks_metric ON benchmarks (metric_name);

-- ──────────────────────────────────────────────────────────────────────────────
-- Group F — Pipeline & Document Catalog (pipeline_runs must precede documents and child tables)
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE pipeline_runs (
    pipeline_run_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id             UUID REFERENCES deals(deal_id) ON DELETE CASCADE,
    workspace_id        UUID REFERENCES workspaces(workspace_id),
    started_at          TIMESTAMPTZ NOT NULL,
    completed_at        TIMESTAMPTZ,
    status              pipeline_status,
    stages_completed    JSONB,
    total_elapsed_ms    INT,
    triggered_by        VARCHAR(50),
    pipeline_version    VARCHAR(20)
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
    extraction_run_id   UUID REFERENCES pipeline_runs(pipeline_run_id),
    content_hash        CHAR(64),
    page_count          INT,
    file_size_bytes     BIGINT
);

CREATE TABLE pipeline_stage_logs (
    log_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_run_id     UUID REFERENCES pipeline_runs(pipeline_run_id) ON DELETE CASCADE,
    agent_name          VARCHAR(50) NOT NULL,
    stage_order         INT,
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    elapsed_ms          INT,
    output_file_path    TEXT,
    status              pipeline_status,
    error_code          VARCHAR(30),
    token_count_input   INT,
    token_count_output  INT
);

-- ──────────────────────────────────────────────────────────────────────────────
-- Group G — AI/ML Feature Store & Model Governance
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE model_versions (
    model_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name              VARCHAR(100) NOT NULL,
    version                 VARCHAR(20) NOT NULL,
    architecture            VARCHAR(50),
    deployed_at             TIMESTAMPTZ NOT NULL,
    deprecated_at           TIMESTAMPTZ,
    training_dataset_hash   CHAR(64),
    validation_auc          NUMERIC(6,4),
    validation_ks_statistic NUMERIC(6,4),
    calibration_brier_score NUMERIC(6,4),
    feature_names           JSONB,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (model_name, version)
);

-- ──────────────────────────────────────────────────────────────────────────────
-- Group D — Loan Structure
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE loan_terms (
    loan_terms_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id                     UUID NOT NULL REFERENCES deals(deal_id) ON DELETE CASCADE,
    entity_id                   UUID REFERENCES entities(entity_id),
    loan_amount                 NUMERIC(18,2) NOT NULL,
    loan_type                   VARCHAR(30),
    interest_rate               NUMERIC(8,6),
    rate_type                   VARCHAR(20),
    rate_index                  VARCHAR(20),
    spread_bps                  INT,
    amortization_years          INT,
    term_months                 INT,
    balloon_payment             NUMERIC(18,2),
    proposed_annual_debt_service NUMERIC(18,2),
    origination_fee_bps         INT,
    prepayment_penalty          BOOLEAN,
    draw_period_months          INT,
    revolver_availability       NUMERIC(18,2),
    target_close_date           DATE,
    status                      VARCHAR(20) DEFAULT 'proposed',
    created_at                  TIMESTAMPTZ,
    UNIQUE (deal_id)
);

CREATE TABLE collateral (
    collateral_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id         UUID REFERENCES deals(deal_id) ON DELETE CASCADE,
    entity_id       UUID REFERENCES entities(entity_id),
    document_id     UUID REFERENCES documents(document_id),
    collateral_type VARCHAR(30),
    description     VARCHAR(255),
    appraised_value NUMERIC(18,2),
    appraisal_date  DATE,
    appraiser_name  VARCHAR(255),
    ltv_ratio       NUMERIC(5,4),
    lien_position   INT,
    address         TEXT,
    parcel_id       VARCHAR(50)
);

CREATE TABLE covenants (
    covenant_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id          UUID REFERENCES deals(deal_id) ON DELETE CASCADE,
    loan_terms_id    UUID REFERENCES loan_terms(loan_terms_id),
    pipeline_run_id  UUID REFERENCES pipeline_runs(pipeline_run_id),
    covenant_type    VARCHAR(20),
    description      VARCHAR(255),
    metric           VARCHAR(50),
    threshold_value  NUMERIC(10,4),
    actual_value     NUMERIC(10,4),
    unit             VARCHAR(20),
    pass_fail        BOOLEAN,
    headroom_pct     NUMERIC(8,4),
    test_frequency   VARCHAR(20),
    last_tested_at   DATE,
    cure_period_days INT,
    waiver_count     INT DEFAULT 0,
    source_agent     source_agent_type NOT NULL,
    status           covenant_status
);

CREATE TABLE guarantees (
    guarantee_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id             UUID NOT NULL REFERENCES deals(deal_id) ON DELETE CASCADE,
    guarantor_entity_id UUID NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
    loan_terms_id       UUID REFERENCES loan_terms(loan_terms_id),
    guarantee_type      guarantee_type NOT NULL,
    coverage_amount     NUMERIC(18,2),
    coverage_pct        NUMERIC(5,4),
    personal_net_worth  NUMERIC(18,2),
    liquid_assets       NUMERIC(18,2),
    executed_at         DATE,
    expires_at          DATE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (deal_id, guarantor_entity_id)
);
CREATE INDEX ix_guarantees_deal_id ON guarantees (deal_id);

-- ──────────────────────────────────────────────────────────────────────────────
-- Group H — Auth, Access & Audit
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE users (
    user_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    role            user_role NOT NULL,
    institution_id  UUID,
    password_hash   CHAR(128),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login      TIMESTAMPTZ,
    is_active       BOOLEAN DEFAULT TRUE
);

CREATE TABLE sessions (
    session_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID REFERENCES users(user_id) ON DELETE CASCADE,
    issued_at           TIMESTAMPTZ NOT NULL,
    expires_at          TIMESTAMPTZ NOT NULL,
    refresh_token_hash  CHAR(128),
    revoked             BOOLEAN DEFAULT FALSE,
    ip_address          VARCHAR(45)
);
CREATE INDEX ix_sessions_user_id    ON sessions (user_id);
CREATE INDEX ix_sessions_expires_at ON sessions (expires_at);

CREATE TABLE deal_access (
    access_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID REFERENCES users(user_id) ON DELETE CASCADE,
    deal_id      UUID REFERENCES deals(deal_id) ON DELETE CASCADE,
    access_level access_level NOT NULL,
    granted_by   UUID REFERENCES users(user_id),
    granted_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, deal_id)
);

CREATE TABLE audit_log (
    log_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(user_id),
    deal_id         UUID REFERENCES deals(deal_id) ON DELETE CASCADE,
    session_id      VARCHAR(128),
    actor_ip        VARCHAR(45),
    action_type     VARCHAR(30) NOT NULL,
    route           TEXT,
    target_path     TEXT,
    target_table    VARCHAR(50),
    agent_name      VARCHAR(50),
    old_value       JSONB,
    new_value       JSONB,
    metadata        JSONB,
    status_code     INT,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ix_audit_log_timestamp ON audit_log (timestamp DESC);
CREATE INDEX ix_audit_log_session   ON audit_log (session_id, timestamp);

-- ──────────────────────────────────────────────────────────────────────────────
-- Group B — Historical Financial Statements
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE personal_financial_statements (
    pfs_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id           UUID REFERENCES entities(entity_id) ON DELETE CASCADE,
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
    deal_id             UUID NOT NULL REFERENCES deals(deal_id) ON DELETE CASCADE
);

CREATE TABLE income_statements (
    statement_id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id                       UUID NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
    document_id                     UUID REFERENCES documents(document_id),
    fiscal_year                     INT NOT NULL,
    fiscal_year_end                 DATE,
    period_type                     VARCHAR(10) DEFAULT 'annual',
    revenue                         NUMERIC(18,2),
    cost_of_goods_sold              NUMERIC(18,2),
    cogs_product                    NUMERIC(18,2),
    cogs_services                   NUMERIC(18,2),
    gross_profit                    NUMERIC(18,2),
    research_and_development        NUMERIC(18,2),
    selling_general_administrative  NUMERIC(18,2),
    stock_based_compensation        NUMERIC(18,2),
    restructuring_charges           NUMERIC(18,2),
    operating_expenses              NUMERIC(18,2),
    ebitda                          NUMERIC(18,2),
    depreciation_amortization       NUMERIC(18,2),
    ebit                            NUMERIC(18,2),
    interest_expense                NUMERIC(18,2),
    pre_tax_income                  NUMERIC(18,2),
    effective_tax_rate              NUMERIC(8,6),
    tax_expense                     NUMERIC(18,2),
    net_income                      NUMERIC(18,2),
    shares_outstanding              BIGINT,
    eps                             NUMERIC(10,4),
    extracted_at                    TIMESTAMPTZ,
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
    cashflow_id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id                       UUID REFERENCES entities(entity_id) ON DELETE CASCADE,
    document_id                     UUID REFERENCES documents(document_id),
    fiscal_year                     INT NOT NULL,
    operating_cash_flow             NUMERIC(18,2),
    stock_based_compensation        NUMERIC(18,2),
    working_capital_change          NUMERIC(18,2),
    working_capital_change_detail   JSONB,
    capital_expenditures            NUMERIC(18,2),
    maintenance_capex               NUMERIC(18,2),
    growth_capex                    NUMERIC(18,2),
    acquisitions                    NUMERIC(18,2),
    investing_cash_flow             NUMERIC(18,2),
    debt_repayment                  NUMERIC(18,2),
    share_repurchases               NUMERIC(18,2),
    financing_cash_flow             NUMERIC(18,2),
    net_change_in_cash              NUMERIC(18,2),
    free_cash_flow                  NUMERIC(18,2),
    normalized_free_cash_flow       NUMERIC(18,2),
    extracted_at                    TIMESTAMPTZ
);

CREATE TABLE revenue_segments (
    segment_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id           UUID NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
    statement_id        UUID REFERENCES income_statements(statement_id),
    fiscal_year         INT NOT NULL,
    segment_name        VARCHAR(100) NOT NULL,
    segment_type        VARCHAR(30),
    segment_revenue     NUMERIC(18,2),
    gross_profit        NUMERIC(18,2),
    segment_margin      NUMERIC(8,6),
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
    source                      VARCHAR(50)
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
    interest_coverage       NUMERIC(10,4),
    asset_turnover          NUMERIC(10,4),
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

-- ──────────────────────────────────────────────────────────────────────────────
-- Group E — Projections & Scenario Analysis
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE projection_assumptions (
    assumptions_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id                 UUID REFERENCES deals(deal_id) ON DELETE CASCADE,
    pipeline_run_id         UUID REFERENCES pipeline_runs(pipeline_run_id),
    model_id                UUID REFERENCES model_versions(model_id),
    scenario                VARCHAR(10) NOT NULL,
    revenue_growth_rate     NUMERIC(8,6),
    ebitda_margin_assumption NUMERIC(8,6),
    capex_pct_revenue       NUMERIC(8,6),
    interest_rate_assumption NUMERIC(8,6),
    debt_paydown_rate       NUMERIC(8,6),
    macro_scenario_tag      VARCHAR(50),
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (deal_id, pipeline_run_id, scenario)
);

CREATE TABLE projections (
    projection_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id                   UUID REFERENCES entities(entity_id) ON DELETE CASCADE,
    deal_id                     UUID REFERENCES deals(deal_id),
    pipeline_run_id             UUID REFERENCES pipeline_runs(pipeline_run_id),
    assumptions_id              UUID REFERENCES projection_assumptions(assumptions_id),
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
    leverage_ratio              NUMERIC(10,4),
    funded_debt                 NUMERIC(18,2),
    funded_debt_to_ebitda       NUMERIC,
    debt_balance                NUMERIC(18,2),
    ending_cash                 NUMERIC(18,2),
    revenue_growth_assumption   NUMERIC(8,6),
    ebitda_margin_assumption    NUMERIC(8,6),
    computed_at                 TIMESTAMPTZ,
    UNIQUE (entity_id, pipeline_run_id, scenario, projection_year)
);

CREATE TABLE covenant_compliance_projections (
    compliance_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id             UUID REFERENCES deals(deal_id) ON DELETE CASCADE,
    pipeline_run_id     UUID REFERENCES pipeline_runs(pipeline_run_id),
    covenant_id         UUID REFERENCES covenants(covenant_id),
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
    trigger_action      VARCHAR(255),
    UNIQUE (deal_id, pipeline_run_id, scenario, projection_year, covenant_type)
);

CREATE TABLE sensitivity_analyses (
    sensitivity_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id              UUID REFERENCES deals(deal_id) ON DELETE CASCADE,
    pipeline_run_id      UUID REFERENCES pipeline_runs(pipeline_run_id),
    variable_shocked     VARCHAR(30) NOT NULL,
    shock_magnitude_pct  NUMERIC(8,4) NOT NULL,
    resulting_dscr       NUMERIC(10,4),
    resulting_leverage   NUMERIC(10,4),
    resulting_fcf        NUMERIC(18,2),
    covenant_breach_year INT,
    computed_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (deal_id, pipeline_run_id, variable_shocked, shock_magnitude_pct)
);

-- ──────────────────────────────────────────────────────────────────────────────
-- Group G continued — slacr_scores, feature_store, model_outcomes
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE slacr_scores (
    score_id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id                     UUID REFERENCES deals(deal_id) ON DELETE CASCADE,
    entity_id                   UUID REFERENCES entities(entity_id),
    pipeline_run_id             UUID REFERENCES pipeline_runs(pipeline_run_id),
    model_id                    UUID REFERENCES model_versions(model_id),
    sponsor_score               NUMERIC(5,2),
    leverage_score              NUMERIC(5,2),
    asset_quality_score         NUMERIC(5,2),
    cash_flow_score             NUMERIC(5,2),
    risk_score                  NUMERIC(5,2),
    composite_score             NUMERIC(5,2),
    internal_rating             VARCHAR(20) NOT NULL,
    occ_classification          VARCHAR(30) NOT NULL,
    model_version               VARCHAR(20),
    confidence_interval_low     NUMERIC(5,2),
    confidence_interval_high    NUMERIC(5,2),
    input_features_snapshot     JSONB,
    shap_values                 JSONB,
    lime_values                 JSONB,
    computed_at                 TIMESTAMPTZ
);

CREATE TABLE feature_store (
    feature_snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id             UUID REFERENCES deals(deal_id) ON DELETE CASCADE,
    pipeline_run_id     UUID REFERENCES pipeline_runs(pipeline_run_id),
    computed_at         TIMESTAMPTZ NOT NULL,
    dscr_t0             NUMERIC(10,4),
    dscr_t1             NUMERIC(10,4),
    leverage_t0         NUMERIC(10,4),
    ebitda_margin_t0    NUMERIC(8,6),
    current_ratio_t0    NUMERIC(10,4),
    industry_risk_tier  VARCHAR(10),
    collateral_coverage NUMERIC(8,4),
    guarantor_net_worth NUMERIC(18,2),
    naics_code          VARCHAR(10),
    years_in_business   INT,
    revenue_cagr_3yr    NUMERIC(8,6),
    UNIQUE (deal_id, pipeline_run_id)
);

CREATE TABLE model_outcomes (
    outcome_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id             UUID REFERENCES deals(deal_id) ON DELETE SET NULL,
    loan_terms_id       UUID REFERENCES loan_terms(loan_terms_id),
    predicted_rating    VARCHAR(30) NOT NULL,
    predicted_at        TIMESTAMPTZ NOT NULL,
    actual_outcome      VARCHAR(30),
    outcome_date        DATE,
    loss_given_default  NUMERIC(18,2),
    recorded_at         TIMESTAMPTZ DEFAULT NOW()
);

-- pgvector embeddings (PostgreSQL only — ChromaDB used locally)
CREATE TABLE embeddings (
    embedding_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID REFERENCES documents(document_id) ON DELETE CASCADE,
    deal_id         UUID,
    entity_id       UUID,
    document_type   VARCHAR(30),
    chunk_index     INT NOT NULL,
    chunk_text      TEXT,
    embedding       vector(768),    -- IBM Slate 768-dim output
    model_name      VARCHAR(100),
    created_at      TIMESTAMPTZ
);
CREATE INDEX ix_embeddings_document ON embeddings (document_id);
-- ANN index (tune lists after >10k rows):
-- CREATE INDEX ix_embeddings_ann ON embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ──────────────────────────────────────────────────────────────────────────────
-- SQL Views (Phase 3B target — 7 views)
-- ──────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW v_financial_summary AS
SELECT
    is2.entity_id,
    e.deal_id,
    e.legal_name,
    is2.fiscal_year,
    is2.period_type,
    is2.revenue,
    is2.ebitda,
    is2.ebit,
    is2.net_income,
    bs.total_assets,
    bs.total_liabilities,
    bs.total_equity,
    cf.operating_cash_flow,
    cf.free_cash_flow,
    cf.capital_expenditures
FROM income_statements is2
JOIN entities e ON e.entity_id = is2.entity_id
LEFT JOIN balance_sheets bs
    ON bs.entity_id = is2.entity_id AND bs.as_of_date = is2.fiscal_year_end
LEFT JOIN cash_flow_statements cf
    ON cf.entity_id = is2.entity_id AND cf.fiscal_year = is2.fiscal_year;

CREATE OR REPLACE VIEW v_ratio_dashboard AS
SELECT
    fr.ratio_id,
    fr.entity_id,
    fr.fiscal_year,
    fr.pipeline_run_id,
    fr.dscr,
    fr.fixed_charge_coverage,
    fr.leverage_ratio,
    fr.funded_debt_to_ebitda,
    fr.current_ratio,
    fr.quick_ratio,
    fr.ebitda_margin,
    fr.interest_coverage,
    fr.computed_at,
    d.deal_id,
    d.borrower_entity_name,
    d.naics_code,
    b25.percentile_25 AS dscr_p25,
    b50.percentile_50 AS dscr_p50,
    b75.percentile_75 AS dscr_p75
FROM financial_ratios fr
JOIN entities e ON e.entity_id = fr.entity_id
JOIN deals d    ON d.deal_id = e.deal_id
LEFT JOIN benchmarks b25 ON b25.naics_code = d.naics_code AND b25.metric_name = 'dscr'
LEFT JOIN benchmarks b50 ON b50.naics_code = d.naics_code AND b50.metric_name = 'dscr'
LEFT JOIN benchmarks b75 ON b75.naics_code = d.naics_code AND b75.metric_name = 'dscr';

CREATE OR REPLACE VIEW v_covenant_tracker AS
SELECT
    c.covenant_id,
    c.deal_id,
    c.loan_terms_id,
    c.pipeline_run_id,
    c.covenant_type,
    c.metric,
    c.description,
    c.threshold_value,
    c.actual_value,
    c.pass_fail,
    c.headroom_pct,
    c.status,
    c.source_agent,
    lt.loan_amount,
    lt.proposed_annual_debt_service,
    fr.dscr AS financial_ratio_dscr
FROM covenants c
LEFT JOIN loan_terms lt ON lt.deal_id = c.deal_id
LEFT JOIN entities e    ON e.deal_id = c.deal_id AND e.entity_type = 'borrower'
LEFT JOIN financial_ratios fr
    ON fr.entity_id = e.entity_id AND fr.pipeline_run_id = c.pipeline_run_id;

CREATE OR REPLACE VIEW v_slacr_components AS
SELECT
    ss.score_id,
    ss.deal_id,
    ss.entity_id,
    ss.pipeline_run_id,
    ss.sponsor_score,
    ss.leverage_score,
    ss.asset_quality_score,
    ss.cash_flow_score,
    ss.risk_score,
    ss.composite_score,
    ss.internal_rating,
    ss.occ_classification,
    ss.confidence_interval_low,
    ss.confidence_interval_high,
    ss.shap_values,
    ss.computed_at,
    fr.dscr                  AS historical_dscr,
    fr.funded_debt_to_ebitda AS historical_leverage
FROM slacr_scores ss
LEFT JOIN financial_ratios fr
    ON fr.entity_id = ss.entity_id AND fr.pipeline_run_id = ss.pipeline_run_id;

CREATE OR REPLACE VIEW v_pipeline_history AS
SELECT
    pr.pipeline_run_id,
    pr.deal_id,
    pr.started_at,
    pr.completed_at,
    pr.status,
    pr.total_elapsed_ms,
    pr.pipeline_version,
    pr.triggered_by,
    d.borrower_entity_name,
    COUNT(psl.log_id) AS stages_total,
    SUM(CASE WHEN psl.status = 'complete' THEN 1 ELSE 0 END) AS stages_complete
FROM pipeline_runs pr
JOIN deals d ON d.deal_id = pr.deal_id
LEFT JOIN pipeline_stage_logs psl ON psl.pipeline_run_id = pr.pipeline_run_id
GROUP BY pr.pipeline_run_id, pr.deal_id, pr.started_at, pr.completed_at,
         pr.status, pr.total_elapsed_ms, pr.pipeline_version, pr.triggered_by,
         d.borrower_entity_name
ORDER BY pr.started_at DESC;

CREATE OR REPLACE VIEW v_projection_stress AS
SELECT
    p.deal_id,
    p.entity_id,
    p.pipeline_run_id,
    p.scenario,
    p.projection_year,
    p.revenue,
    p.ebitda,
    p.dscr,
    p.leverage_ratio,
    p.free_cash_flow,
    ccp.covenant_type,
    ccp.threshold_value,
    ccp.computed_value,
    ccp.headroom_pct,
    ccp.status        AS covenant_status,
    ccp.is_breach_year
FROM projections p
LEFT JOIN covenant_compliance_projections ccp
    ON ccp.deal_id = p.deal_id
    AND ccp.pipeline_run_id = p.pipeline_run_id
    AND ccp.scenario = p.scenario
    AND ccp.projection_year = p.projection_year;

CREATE OR REPLACE VIEW v_deal_snapshot AS
SELECT
    d.deal_id,
    d.borrower_entity_name,
    d.naics_code,
    d.status              AS deal_status,
    d.pipeline_version,
    d.storage_backend,
    d.created_at          AS deal_created_at,
    lt.loan_amount,
    lt.loan_type,
    lt.term_months,
    lt.rate_type,
    lt.status             AS loan_status,
    ss.composite_score    AS slacr_score,
    ss.internal_rating,
    ss.occ_classification,
    fr.dscr               AS latest_dscr,
    fr.funded_debt_to_ebitda AS latest_leverage,
    pr.pipeline_run_id    AS latest_run_id,
    pr.status             AS pipeline_status,
    pr.completed_at       AS pipeline_completed_at,
    COUNT(DISTINCT doc.document_id) AS document_count,
    COUNT(DISTINCT e.entity_id)     AS entity_count
FROM deals d
LEFT JOIN loan_terms lt ON lt.deal_id = d.deal_id
LEFT JOIN pipeline_runs pr ON pr.deal_id = d.deal_id
    AND pr.started_at = (
        SELECT MAX(pr2.started_at) FROM pipeline_runs pr2 WHERE pr2.deal_id = d.deal_id
    )
LEFT JOIN slacr_scores ss ON ss.deal_id = d.deal_id AND ss.pipeline_run_id = pr.pipeline_run_id
LEFT JOIN entities e      ON e.deal_id = d.deal_id
LEFT JOIN financial_ratios fr
    ON fr.entity_id = e.entity_id
    AND fr.pipeline_run_id = pr.pipeline_run_id
    AND e.entity_type = 'borrower'
LEFT JOIN documents doc ON doc.deal_id = d.deal_id
GROUP BY d.deal_id, d.borrower_entity_name, d.naics_code, d.status,
         d.pipeline_version, d.storage_backend, d.created_at,
         lt.loan_amount, lt.loan_type, lt.term_months, lt.rate_type, lt.status,
         ss.composite_score, ss.internal_rating, ss.occ_classification,
         fr.dscr, fr.funded_debt_to_ebitda,
         pr.pipeline_run_id, pr.status, pr.completed_at;
