"""
SQL Service — session management, schema init, and persistence helpers.

D-2: create_all() on startup for local SQLite.
D-3: all operations catch exceptions and log warnings rather than raising.
OCC mapping lives in graph_models.occ_classify() — called here at SLACR INSERT time (IP3).
"""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger("deckr.sql_service")

# ---------------------------------------------------------------------------
# Retry decorator (P-3) — retries transient OperationalError up to 3 times
# ---------------------------------------------------------------------------

try:
    from tenacity import (
        retry as _tenacity_retry,
        stop_after_attempt,
        wait_exponential,
        retry_if_exception_type,
    )
    from sqlalchemy.exc import OperationalError as _OperationalError

    def _sql_retry(fn):
        """Wrap a callable with 3-attempt exponential-backoff retry on SQLAlchemy OperationalError."""
        return _tenacity_retry(
            retry=retry_if_exception_type(_OperationalError),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            reraise=True,
        )(fn)

except ImportError:
    def _sql_retry(fn):
        """No-op fallback if tenacity is not installed."""
        return fn


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_float(val) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Schema init (called from main.py lifespan)
# ---------------------------------------------------------------------------

def init_schema():
    """D-2: create_all() for local SQLite. No-op if tables already exist."""
    try:
        from services.db_factory import init_sql_schema
        init_sql_schema()
    except Exception as exc:
        logger.warning("SQL schema init failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Deal / Workspace seed
# ---------------------------------------------------------------------------

def upsert_workspace(workspace_id: str, project_path: str, borrower_name: str | None = None) -> bool:
    """Insert or update a workspace row. Returns True on success."""
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import Workspace
        with next(get_sql_session()) as session:
            existing = session.get(Workspace, workspace_id)
            if existing:
                if borrower_name:
                    existing.borrower_name = borrower_name
                existing.updated_at = _now()
            else:
                session.add(Workspace(
                    workspace_id=workspace_id,
                    project_path=project_path,
                    borrower_name=borrower_name,
                    created_at=_now(),
                    updated_at=_now(),
                ))
            session.commit()
        return True
    except Exception as exc:
        logger.warning("upsert_workspace failed: %s", exc)
        return False


def upsert_deal(deal_id: str, workspace_id: str, borrower_entity_name: str,
                entity_structure: str | None = None, requested_loan_amount: float | None = None,
                loan_purpose: str | None = None, naics_code: str | None = None) -> bool:
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import Deal
        with next(get_sql_session()) as session:
            existing = session.get(Deal, deal_id)
            if existing:
                existing.updated_at = _now()
            else:
                session.add(Deal(
                    deal_id=deal_id,
                    workspace_id=workspace_id,
                    borrower_entity_name=borrower_entity_name,
                    entity_structure=entity_structure,
                    requested_loan_amount=requested_loan_amount,
                    loan_purpose=loan_purpose,
                    naics_code=naics_code,
                    created_at=_now(),
                    updated_at=_now(),
                ))
            session.commit()
        return True
    except Exception as exc:
        logger.warning("upsert_deal failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Entity / Document seed
# ---------------------------------------------------------------------------

def insert_entity(deal_id: str, entity_type: str, legal_name: str,
                  entity_id: str | None = None, **kwargs) -> str | None:
    """Insert entity row. Returns entity_id on success, None on failure."""
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import Entity
        eid = entity_id or str(uuid4())
        with next(get_sql_session()) as session:
            session.add(Entity(
                entity_id=eid, deal_id=deal_id,
                entity_type=entity_type, legal_name=legal_name,
                created_at=_now(), **kwargs,
            ))
            session.commit()
        return eid
    except Exception as exc:
        logger.warning("insert_entity failed: %s", exc)
        return None


def insert_document(workspace_id: str, deal_id: str, file_name: str, file_path: str,
                    document_type: str, entity_id: str | None = None,
                    document_id: str | None = None, **kwargs) -> str | None:
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import Document
        did = document_id or str(uuid4())
        with next(get_sql_session()) as session:
            session.add(Document(
                document_id=did, workspace_id=workspace_id, deal_id=deal_id,
                entity_id=entity_id, file_name=file_name, file_path=file_path,
                document_type=document_type, upload_timestamp=_now(), **kwargs,
            ))
            session.commit()
        return did
    except Exception as exc:
        logger.warning("insert_document failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Financial statement inserts (called by extraction_persistence_service at IP1)
# ---------------------------------------------------------------------------

def insert_income_statement(entity_id: str, fiscal_year: int, data: dict) -> bool:
    try:
        @_sql_retry
        def _execute():
            from services.db_factory import get_sql_session
            from models.sql_models import IncomeStatement
            with next(get_sql_session()) as session:
                session.add(IncomeStatement(
                    statement_id=str(uuid4()), entity_id=entity_id,
                    fiscal_year=fiscal_year, extracted_at=_now(), **data,
                ))
                session.commit()
        _execute()
        return True
    except Exception as exc:
        logger.warning("insert_income_statement failed (year %s): %s", fiscal_year, exc)
        return False


def insert_balance_sheet(entity_id: str, as_of_date: Any, data: dict) -> bool:
    try:
        @_sql_retry
        def _execute():
            from services.db_factory import get_sql_session
            from models.sql_models import BalanceSheet
            with next(get_sql_session()) as session:
                session.add(BalanceSheet(
                    balance_sheet_id=str(uuid4()), entity_id=entity_id,
                    as_of_date=as_of_date, extracted_at=_now(), **data,
                ))
                session.commit()
        _execute()
        return True
    except Exception as exc:
        logger.warning("insert_balance_sheet failed: %s", exc)
        return False


def insert_cash_flow(entity_id: str, fiscal_year: int, data: dict) -> bool:
    try:
        @_sql_retry
        def _execute():
            from services.db_factory import get_sql_session
            from models.sql_models import CashFlowStatement
            with next(get_sql_session()) as session:
                session.add(CashFlowStatement(
                    cashflow_id=str(uuid4()), entity_id=entity_id,
                    fiscal_year=fiscal_year, extracted_at=_now(), **data,
                ))
                session.commit()
        _execute()
        return True
    except Exception as exc:
        logger.warning("insert_cash_flow failed (year %s): %s", fiscal_year, exc)
        return False


def insert_loan_terms(deal_id: str, data: dict) -> bool:
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import LoanTerms
        with next(get_sql_session()) as session:
            session.add(LoanTerms(
                loan_terms_id=str(uuid4()), deal_id=deal_id,
                created_at=_now(), **data,
            ))
            session.commit()
        return True
    except Exception as exc:
        logger.warning("insert_loan_terms failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# IP2 — Financial Agent sidecar (D-4: reads financial_ratios.json)
# ---------------------------------------------------------------------------

def write_financial_ratios(entity_id: str, pipeline_run_id: str,
                           fiscal_year: int, data: dict) -> bool:
    """
    D-4: called after financial agent writes Agent Notes/financial_ratios.json.
    `data` is the parsed JSON from that sidecar.
    """
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import FinancialRatio
        with next(get_sql_session()) as session:
            session.add(FinancialRatio(
                ratio_id=str(uuid4()), entity_id=entity_id,
                pipeline_run_id=pipeline_run_id,
                fiscal_year=fiscal_year, computed_at=_now(), **data,
            ))
            session.commit()
        return True
    except Exception as exc:
        logger.warning("write_financial_ratios failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# IP3 — Risk Agent (OCC mapping applied here, not by the agent)
# ---------------------------------------------------------------------------

def write_slacr_score(deal_id: str, pipeline_run_id: str, scores: dict,
                      internal_rating: str, dscr: float | None = None,
                      shap_values: dict | None = None,
                      lime_values: dict | None = None) -> bool:
    """
    Applies OCC mapping deterministically at INSERT time (never by the agent).
    `internal_rating` comes from slacr.json 'rating' field.
    """
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import SlacrScore
        from models.graph_models import occ_classify

        occ = occ_classify(internal_rating, dscr)

        with next(get_sql_session()) as session:
            session.add(SlacrScore(
                score_id=str(uuid4()),
                deal_id=deal_id,
                pipeline_run_id=pipeline_run_id,
                internal_rating=internal_rating,
                occ_classification=occ,
                shap_values=shap_values,
                lime_values=lime_values,
                computed_at=_now(),
                **scores,
            ))
            session.commit()
        return True
    except Exception as exc:
        logger.warning("write_slacr_score failed: %s", exc)
        return False


def insert_covenant(deal_id: str, pipeline_run_id: str, data: dict) -> bool:
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import Covenant
        with next(get_sql_session()) as session:
            session.add(Covenant(
                covenant_id=str(uuid4()),
                deal_id=deal_id,
                pipeline_run_id=pipeline_run_id,
                **data,
            ))
            session.commit()
        return True
    except Exception as exc:
        logger.warning("insert_covenant failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Pipeline run tracking
# ---------------------------------------------------------------------------

def insert_pipeline_run(pipeline_run_id: str, deal_id: str,
                        workspace_id: str) -> bool:
    try:
        @_sql_retry
        def _execute():
            from services.db_factory import get_sql_session
            from models.sql_models import PipelineRun, PipelineStatus
            with next(get_sql_session()) as session:
                session.add(PipelineRun(
                    pipeline_run_id=pipeline_run_id,
                    deal_id=deal_id,
                    workspace_id=workspace_id,
                    started_at=_now(),
                    status=PipelineStatus.running,
                    stages_completed=[],
                ))
                session.commit()
        _execute()
        return True
    except Exception as exc:
        logger.warning("insert_pipeline_run failed: %s", exc)
        return False


def update_pipeline_run(pipeline_run_id: str, status: str,
                        stages_completed: list | None = None,
                        duration_seconds: int | None = None) -> bool:
    try:
        @_sql_retry
        def _execute():
            from services.db_factory import get_sql_session
            from models.sql_models import PipelineRun
            with next(get_sql_session()) as session:
                run = session.get(PipelineRun, pipeline_run_id)
                if run:
                    run.status = status
                    run.completed_at = _now()
                    if stages_completed is not None:
                        run.stages_completed = stages_completed
                    if duration_seconds is not None:
                        run.total_duration_seconds = duration_seconds
                    session.commit()
        _execute()
        return True
    except Exception as exc:
        logger.warning("update_pipeline_run failed: %s", exc)
        return False


def insert_stage_log(pipeline_run_id: str, agent_name: str, stage_order: int,
                     started_at: datetime, completed_at: datetime | None = None,
                     status: str = "complete", output_file_path: str | None = None,
                     token_count_input: int | None = None,
                     token_count_output: int | None = None) -> bool:
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import PipelineStageLog
        with next(get_sql_session()) as session:
            duration = None
            if completed_at and started_at:
                duration = int((completed_at - started_at).total_seconds())
            session.add(PipelineStageLog(
                log_id=str(uuid4()),
                pipeline_run_id=pipeline_run_id,
                agent_name=agent_name,
                stage_order=stage_order,
                started_at=started_at,
                completed_at=completed_at or _now(),
                duration_seconds=duration,
                output_file_path=output_file_path,
                status=status,
                token_count_input=token_count_input,
                token_count_output=token_count_output,
            ))
            session.commit()
        return True
    except Exception as exc:
        logger.warning("insert_stage_log failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Audit log (append-only)
# ---------------------------------------------------------------------------

def append_audit(action_type: str, deal_id: str | None = None,
                 route: str | None = None, agent_name: str | None = None,
                 actor_ip: str | None = None, status_code: int | None = None,
                 metadata: dict | None = None) -> bool:
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import AuditLog
        with next(get_sql_session()) as session:
            session.add(AuditLog(
                log_id=str(uuid4()),
                deal_id=deal_id,
                action_type=action_type,
                route=route,
                agent_name=agent_name,
                actor_ip=actor_ip,
                status_code=status_code,
                audit_metadata=metadata,
                timestamp=_now(),
            ))
            session.commit()
        return True
    except Exception as exc:
        logger.warning("append_audit failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Read helpers (used by /api/financials/* endpoints)
# ---------------------------------------------------------------------------

def count_financial_rows(entity_id: str) -> int:
    """IP1 gate check — returns total rows across the three financial tables for this entity."""
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import IncomeStatement, BalanceSheet, CashFlowStatement
        from sqlalchemy import select, func
        with next(get_sql_session()) as session:
            total = 0
            for model in (IncomeStatement, BalanceSheet, CashFlowStatement):
                total += session.execute(
                    select(func.count()).where(model.entity_id == entity_id)
                ).scalar_one()
        return total
    except Exception as exc:
        logger.warning("count_financial_rows failed: %s", exc)
        return 0


def get_entity_id_for_deal(deal_id: str) -> str | None:
    """Return the primary borrower entity_id for a deal (entity_type='borrower_company')."""
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import Entity
        from sqlalchemy import select
        with next(get_sql_session()) as session:
            row = session.execute(
                select(Entity).where(
                    Entity.deal_id == deal_id,
                    Entity.entity_type == "borrower_company",
                ).limit(1)
            ).scalar_one_or_none()
        return str(row.entity_id) if row else None
    except Exception as exc:
        logger.warning("get_entity_id_for_deal failed: %s", exc)
        return None


def get_income_statements(entity_id: str) -> list[dict]:
    """Return all income statement rows for entity, sorted ascending by fiscal_year."""
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import IncomeStatement
        from sqlalchemy import select
        with next(get_sql_session()) as session:
            rows = session.execute(
                select(IncomeStatement).where(IncomeStatement.entity_id == entity_id)
                .order_by(IncomeStatement.fiscal_year)
            ).scalars().all()
        return [
            {
                "fiscal_year": r.fiscal_year,
                "revenue": float(r.revenue or 0),
                "gross_profit": float(r.gross_profit or 0),
                "ebitda": float(r.ebitda or 0),
                "ebit": float(r.ebit or 0),
                "interest_expense": float(r.interest_expense or 0),
                "depreciation_amortization": float(r.depreciation_amortization or 0),
                "net_income": float(r.net_income or 0),
                "effective_tax_rate": float(r.effective_tax_rate or 0.21),
                "selling_general_administrative": float(r.selling_general_administrative or 0),
                "research_and_development": float(r.research_and_development or 0),
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("get_income_statements failed: %s", exc)
        return []


def get_balance_sheets(entity_id: str) -> list[dict]:
    """Return all balance sheet rows for entity, sorted ascending by as_of_date."""
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import BalanceSheet
        from sqlalchemy import select
        with next(get_sql_session()) as session:
            rows = session.execute(
                select(BalanceSheet).where(BalanceSheet.entity_id == entity_id)
                .order_by(BalanceSheet.as_of_date)
            ).scalars().all()
        return [
            {
                "as_of_date": str(r.as_of_date),
                "cash_and_equivalents": float(r.cash_and_equivalents or 0),
                "total_current_assets": float(r.total_current_assets or 0),
                "total_current_liabilities": float(r.total_current_liabilities or 0),
                "total_assets": float(r.total_assets or 0),
                "total_liabilities": float(r.total_liabilities or 0),
                "total_equity": float(r.total_equity or 0),
                "long_term_debt": float(r.long_term_debt or 0),
                "short_term_debt": float(r.short_term_debt or 0),
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("get_balance_sheets failed: %s", exc)
        return []


def get_cash_flow_statements(entity_id: str) -> list[dict]:
    """Return all cash flow rows for entity, sorted ascending by fiscal_year."""
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import CashFlowStatement
        from sqlalchemy import select
        with next(get_sql_session()) as session:
            rows = session.execute(
                select(CashFlowStatement).where(CashFlowStatement.entity_id == entity_id)
                .order_by(CashFlowStatement.fiscal_year)
            ).scalars().all()
        return [
            {
                "fiscal_year": r.fiscal_year,
                "operating_cash_flow": float(r.operating_cash_flow or 0),
                "capital_expenditures": float(r.capital_expenditures or 0),
                "free_cash_flow": float(r.free_cash_flow or 0),
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("get_cash_flow_statements failed: %s", exc)
        return []


def get_loan_terms(deal_id: str) -> dict | None:
    """Return the loan_terms row for a deal, or None if not seeded."""
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import LoanTerms
        from sqlalchemy import select
        with next(get_sql_session()) as session:
            row = session.execute(
                select(LoanTerms).where(LoanTerms.deal_id == deal_id).limit(1)
            ).scalar_one_or_none()
        if not row:
            return None
        return {
            "loan_terms_id": str(row.loan_terms_id),
            "loan_amount": float(row.loan_amount or 0),
            "interest_rate": float(row.interest_rate or 0.0675),
            "rate_type": row.rate_type or "fixed",
            "amortization_years": int(row.amortization_years or 20),
            "term_months": int(row.term_months or 84),
            "proposed_annual_debt_service": float(row.proposed_annual_debt_service or 0),
            "revolver_availability": float(row.revolver_availability or 0),
            "covenant_definitions": row.covenant_definitions or [],
        }
    except Exception as exc:
        logger.warning("get_loan_terms failed: %s", exc)
        return None


def get_management_guidance(entity_id: str) -> dict | None:
    """Return the most recent management_guidance row, or None if not available."""
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import ManagementGuidance
        from sqlalchemy import select
        with next(get_sql_session()) as session:
            row = session.execute(
                select(ManagementGuidance).where(ManagementGuidance.entity_id == entity_id)
                .order_by(ManagementGuidance.extracted_at.desc())
                .limit(1)
            ).scalar_one_or_none()
        if not row:
            return None
        return {
            "next_year_revenue_low": float(row.next_year_revenue_low) if row.next_year_revenue_low else None,
            "next_year_revenue_mid": float(row.next_year_revenue_mid) if row.next_year_revenue_mid else None,
            "next_year_revenue_high": float(row.next_year_revenue_high) if row.next_year_revenue_high else None,
            "next_year_ebitda_margin": float(row.next_year_ebitda_margin) if row.next_year_ebitda_margin else None,
        }
    except Exception as exc:
        logger.warning("get_management_guidance failed: %s", exc)
        return None


def insert_revenue_segment(entity_id: str, fiscal_year: int, statement_id: str | None,
                            segment_name: str, segment_revenue: float | None,
                            pct_of_total_revenue: float | None) -> bool:
    """Insert one revenue segment row. Skips gracefully on SQL failure."""
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import RevenueSegment
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        with next(get_sql_session()) as session:
            seg = RevenueSegment(
                entity_id=entity_id,
                statement_id=statement_id,
                fiscal_year=fiscal_year,
                segment_name=segment_name,
                segment_revenue=segment_revenue,
                pct_of_total_revenue=pct_of_total_revenue,
            )
            session.merge(seg)
            session.commit()
        return True
    except Exception as exc:
        logger.warning("insert_revenue_segment failed: %s", exc)
        return False


def insert_management_guidance(entity_id: str, data: dict) -> bool:
    """Insert / replace management_guidance row for this entity."""
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import ManagementGuidance
        from datetime import datetime, timezone
        with next(get_sql_session()) as session:
            row = ManagementGuidance(
                entity_id=entity_id,
                extracted_at=datetime.now(timezone.utc),
                guidance_period=data.get("guidance_period"),
                next_year_revenue_low=_safe_float(data.get("next_year_revenue_low")),
                next_year_revenue_mid=_safe_float(data.get("next_year_revenue_mid")),
                next_year_revenue_high=_safe_float(data.get("next_year_revenue_high")),
                next_year_ebitda_margin=_safe_float(data.get("next_year_ebitda_margin")),
                growth_drivers=data.get("growth_drivers") or [],
                risk_factors=data.get("risk_factors") or [],
                source_text=data.get("source_text"),
            )
            session.add(row)
            session.commit()
        return True
    except Exception as exc:
        logger.warning("insert_management_guidance failed: %s", exc)
        return False


def insert_projection(row: dict) -> bool:
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import Projection
        with next(get_sql_session()) as session:
            session.add(Projection(projection_id=str(uuid4()), computed_at=_now(), **row))
            session.commit()
        return True
    except Exception as exc:
        logger.warning("insert_projection failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Gate-check helpers (IP2 / IP3)
# ---------------------------------------------------------------------------

def count_financial_ratio_rows(entity_id: str) -> int:
    """IP2 gate check — total FinancialRatio rows for this entity."""
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import FinancialRatio
        from sqlalchemy import select, func
        with next(get_sql_session()) as session:
            return session.execute(
                select(func.count()).where(FinancialRatio.entity_id == entity_id)
            ).scalar_one()
    except Exception as exc:
        logger.warning("count_financial_ratio_rows failed: %s", exc)
        return 0


def count_slacr_score_rows(deal_id: str) -> int:
    """IP3 gate check — total slacr_scores rows for this deal."""
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import SlacrScore
        from sqlalchemy import select, func
        with next(get_sql_session()) as session:
            return session.execute(
                select(func.count()).where(SlacrScore.deal_id == deal_id)
            ).scalar_one()
    except Exception as exc:
        logger.warning("count_slacr_score_rows failed: %s", exc)
        return 0


def get_slacr_shap_lime(deal_id: str) -> dict | None:
    """Return SHAP/LIME + summary from the most recent slacr_scores row for a deal."""
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import SlacrScore
        from sqlalchemy import select
        with next(get_sql_session()) as session:
            row = session.execute(
                select(SlacrScore)
                .where(SlacrScore.deal_id == deal_id)
                .order_by(SlacrScore.computed_at.desc())
                .limit(1)
            ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "shap_values":     row.shap_values,
            "lime_values":     row.lime_values,
            "composite_score": float(row.composite_score or 0),
            "internal_rating": row.internal_rating,
        }
    except Exception as exc:
        logger.warning("get_slacr_shap_lime failed: %s", exc)
        return None


def insert_covenant_compliance_projection(row: dict) -> bool:
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import CovenantComplianceProjection, CovenantStatus
        # Derive status from pass_fail and headroom
        computed = row.get("computed_value", 0) or 0
        threshold = row.get("threshold_value", 0) or 0
        operator = row.get("threshold_operator", "gte")
        if operator == "gte":
            passes = computed >= threshold
            headroom = (computed - threshold) / threshold if threshold else 0
        else:  # lte
            passes = computed <= threshold
            headroom = (threshold - computed) / threshold if threshold else 0
        if not passes:
            status = CovenantStatus.breach
        elif headroom < 0.10:
            status = CovenantStatus.tight
        else:
            status = CovenantStatus.compliant
        with next(get_sql_session()) as session:
            session.add(CovenantComplianceProjection(
                compliance_id=str(uuid4()),
                status=status,
                headroom_pct=round(headroom * 100, 2),
                **{k: v for k, v in row.items()
                   if k not in ("status", "headroom_pct")},
            ))
            session.commit()
        return True
    except Exception as exc:
        logger.warning("insert_covenant_compliance_projection failed: %s", exc)
        return False
