"""
Financials Router — structured financial data endpoints.
Reads from SQL tables / views populated by the pipeline.
"""

import logging

from fastapi import APIRouter, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger("deckr.routers.financials")
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

_NOT_IMPL = {"status": "not_implemented", "message": "Phase 4B/10 required"}


@router.get("/chart-data")
def get_chart_data(request: Request, deal_id: str | None = None):
    """Revenue, EBITDA, Net Income bar chart data for a deal. Fully wired in Phase 10."""
    try:
        if deal_id is None:
            return {"status": "error", "message": "deal_id required"}
        from services.db_factory import get_sql_session
        from models.sql_models import IncomeStatement, Entity
        from sqlalchemy import select
        with next(get_sql_session()) as session:
            entity_ids = [
                r[0] for r in session.execute(
                    select(Entity.entity_id).where(Entity.deal_id == deal_id)
                ).all()
            ]
            if not entity_ids:
                return {"deal_id": deal_id, "rows": []}
            rows = session.execute(
                select(
                    IncomeStatement.fiscal_year,
                    IncomeStatement.revenue,
                    IncomeStatement.ebitda,
                    IncomeStatement.net_income,
                ).where(IncomeStatement.entity_id.in_(entity_ids))
                .order_by(IncomeStatement.fiscal_year)
            ).all()
            return {
                "deal_id": deal_id,
                "rows": [
                    {"fiscal_year": r.fiscal_year, "revenue": float(r.revenue or 0),
                     "ebitda": float(r.ebitda or 0), "net_income": float(r.net_income or 0)}
                    for r in rows
                ],
            }
    except Exception as exc:
        logger.warning("get_chart_data failed: %s", exc)
        return {"status": "error", "message": str(exc)}


@router.get("/ratios/{deal_id}")
def get_ratios(deal_id: str, request: Request):
    """Return financial ratios for a deal (v_ratio_dashboard view equivalent)."""
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import FinancialRatio, Entity
        from sqlalchemy import select
        with next(get_sql_session()) as session:
            entity_ids = [
                r[0] for r in session.execute(
                    select(Entity.entity_id).where(Entity.deal_id == deal_id)
                ).all()
            ]
            if not entity_ids:
                return {"deal_id": deal_id, "ratios": []}
            rows = session.execute(
                select(FinancialRatio).where(
                    FinancialRatio.entity_id.in_(entity_ids)
                ).order_by(FinancialRatio.fiscal_year)
            ).scalars().all()
            return {
                "deal_id": deal_id,
                "ratios": [
                    {
                        "fiscal_year": r.fiscal_year,
                        "historical_dscr": float(r.dscr) if r.dscr else None,
                        "fixed_charge_coverage": float(r.fixed_charge_coverage) if r.fixed_charge_coverage else None,
                        "leverage_ratio": float(r.leverage_ratio) if r.leverage_ratio else None,
                        "funded_debt_to_ebitda": float(r.funded_debt_to_ebitda) if r.funded_debt_to_ebitda else None,
                        "current_ratio": float(r.current_ratio) if r.current_ratio else None,
                        "ebitda_margin": float(r.ebitda_margin) if r.ebitda_margin else None,
                    }
                    for r in rows
                ],
            }
    except Exception as exc:
        logger.warning("get_ratios failed: %s", exc)
        return {"status": "error", "message": str(exc)}


@router.get("/covenants/{deal_id}")
def get_covenants(deal_id: str, request: Request):
    """Return covenant pass/fail status for a deal."""
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import Covenant
        from sqlalchemy import select
        with next(get_sql_session()) as session:
            rows = session.execute(
                select(Covenant).where(Covenant.deal_id == deal_id)
            ).scalars().all()
            return {
                "deal_id": deal_id,
                "covenants": [
                    {
                        "metric": r.metric,
                        "description": r.description,
                        "threshold_value": float(r.threshold_value) if r.threshold_value else None,
                        "actual_value": float(r.actual_value) if r.actual_value else None,
                        "pass_fail": r.pass_fail,
                        "source_agent": r.source_agent,
                    }
                    for r in rows
                ],
            }
    except Exception as exc:
        logger.warning("get_covenants failed: %s", exc)
        return {"status": "error", "message": str(exc)}


@router.get("/forecast")
def get_forecast(request: Request, deal_id: str | None = None):
    """Granite TTM time-series forecast output. Fully wired in Phase 10."""
    return _NOT_IMPL


@router.get("/summary")
def get_summary(request: Request, deal_id: str | None = None):
    """3-year side-by-side income + balance + cashflow summary for a deal (v_financial_summary)."""
    try:
        if deal_id is None:
            return {"status": "error", "message": "deal_id required"}
        from services.db_factory import get_sql_session
        from models.sql_models import IncomeStatement, BalanceSheet, CashFlowStatement, Entity
        from sqlalchemy import select
        with next(get_sql_session()) as session:
            entity_ids = [
                r[0] for r in session.execute(
                    select(Entity.entity_id).where(Entity.deal_id == deal_id)
                ).all()
            ]
            if not entity_ids:
                return {"deal_id": deal_id, "rows": []}

            inc_rows = session.execute(
                select(
                    IncomeStatement.fiscal_year,
                    IncomeStatement.revenue,
                    IncomeStatement.gross_profit,
                    IncomeStatement.ebitda,
                    IncomeStatement.ebit,
                    IncomeStatement.net_income,
                    IncomeStatement.interest_expense,
                    IncomeStatement.depreciation_amortization,
                    IncomeStatement.operating_expenses,
                ).where(IncomeStatement.entity_id.in_(entity_ids))
                .order_by(IncomeStatement.fiscal_year)
            ).all()

            bs_rows = session.execute(
                select(
                    BalanceSheet.total_assets,
                    BalanceSheet.total_liabilities,
                    BalanceSheet.total_equity,
                    BalanceSheet.total_current_assets,
                    BalanceSheet.total_current_liabilities,
                    BalanceSheet.cash_and_equivalents,
                    BalanceSheet.long_term_debt,
                    BalanceSheet.short_term_debt,
                ).where(BalanceSheet.entity_id.in_(entity_ids))
                .order_by(BalanceSheet.as_of_date)
            ).all()

            cf_rows = session.execute(
                select(
                    CashFlowStatement.fiscal_year,
                    CashFlowStatement.operating_cash_flow,
                    CashFlowStatement.capital_expenditures,
                    CashFlowStatement.free_cash_flow,
                ).where(CashFlowStatement.entity_id.in_(entity_ids))
                .order_by(CashFlowStatement.fiscal_year)
            ).all()

            def _f(v):
                return float(v) if v is not None else None

            income = [
                {
                    "fiscal_year": r.fiscal_year,
                    "revenue": _f(r.revenue),
                    "gross_profit": _f(r.gross_profit),
                    "ebitda": _f(r.ebitda),
                    "ebit": _f(r.ebit),
                    "net_income": _f(r.net_income),
                    "interest_expense": _f(r.interest_expense),
                    "depreciation_amortization": _f(r.depreciation_amortization),
                    "operating_expenses": _f(r.operating_expenses),
                }
                for r in inc_rows
            ]
            balance = [
                {
                    "total_assets": _f(r.total_assets),
                    "total_liabilities": _f(r.total_liabilities),
                    "total_equity": _f(r.total_equity),
                    "current_assets": _f(r.total_current_assets),
                    "current_liabilities": _f(r.total_current_liabilities),
                    "cash": _f(r.cash_and_equivalents),
                    "long_term_debt": _f(r.long_term_debt),
                    "short_term_debt": _f(r.short_term_debt),
                }
                for r in bs_rows
            ]
            cashflow = [
                {
                    "fiscal_year": r.fiscal_year,
                    "operating_cash_flow": _f(r.operating_cash_flow),
                    "capex": _f(r.capital_expenditures),
                    "free_cash_flow": _f(r.free_cash_flow),
                }
                for r in cf_rows
            ]
            return {
                "deal_id": deal_id,
                "income_statement": income,
                "balance_sheet": balance,
                "cash_flow": cashflow,
            }
    except Exception as exc:
        logger.warning("get_summary failed: %s", exc)
        return {"status": "error", "message": str(exc)}
