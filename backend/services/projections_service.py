"""
Projections Service — Deterministic 3-Statement Projection Model (Phase 4B).

Architecture rule: no LLM involvement. Pure Python arithmetic.
Reads SQL financial tables (with extracted_data.json fallback).
Writes projections + covenant_compliance_projections SQL tables +
projections.json / covenant_compliance.json / projections_summary.md to Financials/.

Three scenarios × 5 projection years:
  Base   — historical CAGR, stable margins
  Upside — management guidance or CAGR + 3%, margin expansion
  Stress — Y1 −20% revenue shock, slow recovery, margins compressed 250bps

Five covenants tested per year × scenario:
  DSCR                   ≥ 1.25x
  Funded Debt / EBITDA   ≤ 4.0x
  Fixed Charge Coverage  ≥ 1.10x
  Minimum Liquidity      ≥ threshold (from loan_terms or $200k default)
  Springing Trigger      DSCR < 1.10x → cash sweep / revolver block
"""

import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger("deckr.projections_service")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PROJECTION_YEARS = 5
_TAX_RATE_DEFAULT = 0.21
_DEFAULT_MIN_LIQUIDITY = 200_000.0

# Covenant definitions (operator: "gte" = ≥, "lte" = ≤)
_COVENANTS: list[dict] = [
    {"covenant_type": "dscr",                  "threshold_value": 1.25, "threshold_operator": "gte",
     "formula": "(EBITDA − CapEx) / AnnualDebtService",      "trigger_action": "technical default"},
    {"covenant_type": "funded_debt_ebitda",     "threshold_value": 4.0,  "threshold_operator": "lte",
     "formula": "FundedDebt / EBITDA",                        "trigger_action": "revolver block"},
    {"covenant_type": "fixed_charge_coverage",  "threshold_value": 1.10, "threshold_operator": "gte",
     "formula": "(EBITDA − CapEx) / AnnualDebtService",       "trigger_action": "cash sweep"},
    {"covenant_type": "minimum_liquidity",      "threshold_value": _DEFAULT_MIN_LIQUIDITY,
     "threshold_operator": "gte",
     "formula": "Cash + RevolverAvailability",                "trigger_action": "springing trigger"},
    {"covenant_type": "springing_trigger",      "threshold_value": 1.10, "threshold_operator": "gte",
     "formula": "DSCR (lower threshold)",                     "trigger_action": "cash sweep / revolver block"},
]

_DEFAULT_LOAN_TERMS: dict = {
    "loan_amount": 2_500_000.0,
    "interest_rate": 0.0675,
    "rate_type": "fixed",
    "amortization_years": 20,
    "term_months": 84,
    "proposed_annual_debt_service": 214_800.0,
    "revolver_availability": 0.0,
    "covenant_definitions": [],
    "loan_terms_id": None,
}


# ---------------------------------------------------------------------------
# Input loaders
# ---------------------------------------------------------------------------

def _load_financials_from_sql(entity_id: str) -> tuple[list, list, list]:
    """Returns (income_stmts, balance_sheets, cash_flows) from SQL."""
    from services import sql_service
    return (
        sql_service.get_income_statements(entity_id),
        sql_service.get_balance_sheets(entity_id),
        sql_service.get_cash_flow_statements(entity_id),
    )


def _load_financials_from_json(workspace_root: str) -> tuple[list, list, list]:
    """
    Fallback: parse extracted_data.json into the same list-of-dict shapes
    that the SQL read helpers return.
    """
    json_path = Path(workspace_root) / "Financials" / "extracted_data.json"
    if not json_path.exists():
        logger.warning("projections: extracted_data.json not found at %s", json_path)
        return [], [], []

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("projections: failed to parse extracted_data.json — %s", exc)
        return [], [], []

    fiscal_years: list[str] = data.get("fiscal_years", [])
    is_raw = data.get("income_statement", {})
    bs_raw = data.get("balance_sheet", {})
    cf_raw = data.get("cash_flow_statement", {})

    def _flt(d: dict, key: str, fy: str) -> float:
        v = d.get(key, {})
        if isinstance(v, dict):
            v = v.get(fy)
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _fy_to_int(fy: str) -> int:
        digits = "".join(c for c in fy if c.isdigit())
        try:
            return int(digits[-4:]) if len(digits) >= 4 else int(digits)
        except ValueError:
            return 0

    income_stmts, balance_sheets, cash_flows = [], [], []
    for fy in fiscal_years:
        yr = _fy_to_int(fy)
        if not yr:
            continue
        ebitda = _flt(is_raw, "ebitda", fy)
        revenue = _flt(is_raw, "revenue", fy)
        da = _flt(is_raw, "depreciation_amortization", fy)
        interest = _flt(is_raw, "interest_expense", fy)
        net_income = _flt(is_raw, "net_income", fy)
        gross = _flt(is_raw, "gross_profit", fy)

        income_stmts.append({
            "fiscal_year": yr,
            "revenue": revenue,
            "gross_profit": gross,
            "ebitda": ebitda,
            "ebit": ebitda - da if da else ebitda,
            "interest_expense": interest,
            "depreciation_amortization": da,
            "net_income": net_income,
            "effective_tax_rate": _TAX_RATE_DEFAULT,
            "selling_general_administrative": 0.0,
            "research_and_development": 0.0,
        })

        balance_sheets.append({
            "as_of_date": f"{yr}-12-31",
            "cash_and_equivalents": _flt(bs_raw, "cash", fy),
            "total_current_assets": _flt(bs_raw, "current_assets", fy),
            "total_current_liabilities": _flt(bs_raw, "current_liabilities", fy),
            "total_assets": _flt(bs_raw, "total_assets", fy),
            "total_liabilities": _flt(bs_raw, "total_liabilities", fy),
            "total_equity": _flt(bs_raw, "total_equity", fy),
            "long_term_debt": _flt(bs_raw, "long_term_debt", fy),
            "short_term_debt": _flt(bs_raw, "total_debt", fy) - _flt(bs_raw, "long_term_debt", fy),
        })

        cash_flows.append({
            "fiscal_year": yr,
            "operating_cash_flow": _flt(cf_raw, "operating_cash_flow", fy),
            "capital_expenditures": _flt(cf_raw, "capex", fy),
            "free_cash_flow": _flt(cf_raw, "free_cash_flow", fy),
        })

    return income_stmts, balance_sheets, cash_flows


def _load_loan_terms(deal_id: str, workspace_root: str) -> dict:
    """SQL → loan_terms.json → hardcoded defaults."""
    from services import sql_service
    lt = sql_service.get_loan_terms(deal_id)
    if lt:
        logger.info("projections: loan_terms loaded from SQL deal_id=%s", deal_id)
        return lt

    json_path = Path(workspace_root) / "Financials" / "loan_terms.json"
    if json_path.exists():
        try:
            lt = json.loads(json_path.read_text(encoding="utf-8"))
            lt.setdefault("loan_terms_id", None)
            logger.info("projections: loan_terms loaded from loan_terms.json")
            return lt
        except Exception as exc:
            logger.warning("projections: loan_terms.json parse failed — %s", exc)

    logger.info("projections: using default loan terms (no SQL row or file found)")
    return dict(_DEFAULT_LOAN_TERMS)


# ---------------------------------------------------------------------------
# Assumption helpers
# ---------------------------------------------------------------------------

def _safe_cagr(values: list[float]) -> float:
    """Geometric CAGR from a list of sequential annual values. Returns 0.0 on edge cases."""
    clean = [v for v in values if v and v > 0]
    if len(clean) < 2:
        return 0.0
    try:
        return (clean[-1] / clean[0]) ** (1.0 / (len(clean) - 1)) - 1.0
    except (ZeroDivisionError, ValueError):
        return 0.0


def _avg(values: list[float]) -> float:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else 0.0


def _compute_debt_service(lt: dict) -> float:
    """Use proposed_annual_debt_service if set; otherwise compute from loan terms."""
    ads = lt.get("proposed_annual_debt_service") or 0.0
    if ads > 0:
        return ads
    principal = lt.get("loan_amount") or 0.0
    r = lt.get("interest_rate") or 0.0
    n = lt.get("amortization_years") or 20
    if principal <= 0 or n <= 0:
        return 0.0
    if r == 0:
        return principal / n
    # Standard amortization formula: P × r / (1 − (1+r)^−n)
    try:
        return principal * r / (1 - (1 + r) ** (-n))
    except ZeroDivisionError:
        return principal / n


def _scenario_assumptions(
    income_stmts: list[dict],
    cash_flows: list[dict],
    guidance: dict | None,
) -> dict:
    """Compute Base/Upside/Stress growth and margin assumptions from historical data."""
    revenues = [r["revenue"] for r in income_stmts if r.get("revenue")]
    ebitdas  = [r["ebitda"]  for r in income_stmts if r.get("ebitda")]
    capexes  = [c["capital_expenditures"] for c in cash_flows if c.get("capital_expenditures")]

    base_cagr         = _safe_cagr(revenues)
    base_ebitda_margin = _avg([e / r for e, r in zip(ebitdas, revenues) if r > 0])
    avg_capex_pct     = _avg([c / r for c, r in zip(capexes, revenues) if r > 0])

    # Base: historical trend, modest 50bps margin compression for conservatism
    base_margin = max(base_ebitda_margin - 0.005, 0.0)

    # Upside: management guidance Y1 anchor if available, then base CAGR; or CAGR + 3%
    upside_cagr   = base_cagr + 0.03
    upside_margin = base_ebitda_margin + 0.01   # 100bps improvement
    upside_guidance_revenue: float | None = None
    if guidance and guidance.get("next_year_revenue_mid"):
        upside_guidance_revenue = guidance["next_year_revenue_mid"]
    if guidance and guidance.get("next_year_ebitda_margin"):
        upside_margin = guidance["next_year_ebitda_margin"]

    # Stress: Y1 −20% shock, then half-speed recovery; margin −250bps
    stress_y1_growth = -0.20
    stress_recovery_cagr = base_cagr * 0.5
    stress_margin = max(base_ebitda_margin - 0.025, 0.0)

    return {
        "base":   {"cagr": base_cagr,   "ebitda_margin": base_margin,   "capex_pct": avg_capex_pct},
        "upside": {"cagr": upside_cagr, "ebitda_margin": upside_margin, "capex_pct": avg_capex_pct,
                   "guidance_y1_revenue": upside_guidance_revenue},
        "stress": {"cagr": stress_recovery_cagr, "ebitda_margin": stress_margin,
                   "capex_pct": avg_capex_pct, "y1_shock": stress_y1_growth},
    }


# ---------------------------------------------------------------------------
# Per-year projection
# ---------------------------------------------------------------------------

def _project_year(
    scenario: str,
    year_idx: int,          # 0-based; 0 = first projection year
    prior_revenue: float,
    prior_funded_debt: float,
    prior_cash: float,
    assumptions: dict,
    loan_terms: dict,
    debt_service: float,
    base_year: int,
) -> dict:
    """
    Compute one projected year for a given scenario.
    Returns a dict matching the Projection SQL model fields.
    """
    sa = assumptions[scenario]
    proj_year = base_year + year_idx + 1

    # Revenue
    if scenario == "upside" and year_idx == 0 and sa.get("guidance_y1_revenue"):
        revenue = sa["guidance_y1_revenue"]
    elif scenario == "stress" and year_idx == 0:
        revenue = prior_revenue * (1 + sa["y1_shock"])
    else:
        revenue = prior_revenue * (1 + sa["cagr"])

    # Income statement
    ebitda_margin = sa["ebitda_margin"]
    ebitda        = revenue * ebitda_margin
    capex         = revenue * sa["capex_pct"]
    interest      = prior_funded_debt * (loan_terms.get("interest_rate") or 0.0675)
    da            = capex * 0.8          # simplified: D&A ≈ 80% of capex
    ebit          = ebitda - da
    pre_tax       = max(ebit - interest, 0.0)
    tax           = pre_tax * _TAX_RATE_DEFAULT
    net_income    = pre_tax - tax

    # Cash flow
    operating_cf = net_income + da
    free_cf      = operating_cf - capex

    # Balance sheet — straight-line debt amortization
    annual_principal = (loan_terms.get("loan_amount") or 0.0) / (loan_terms.get("amortization_years") or 20)
    funded_debt      = max(prior_funded_debt - annual_principal, 0.0)
    ending_cash      = prior_cash + free_cf - debt_service + (loan_terms.get("revolver_availability") or 0.0) * 0.0

    # DSCR = (EBITDA − CapEx) / debt_service
    dscr = (ebitda - capex) / debt_service if debt_service > 0 else None
    # Cap DSCR at 20.0x — values above this indicate missing/default loan terms
    # (e.g. large-cap borrower vs. $2.5M default ADS) and would skew ML feature inputs.
    _DSCR_CAP = 20.0
    if dscr is not None and dscr > _DSCR_CAP:
        logger.warning(
            "projections: DSCR %.1fx exceeds cap of %.1fx — capping for feature store "
            "(deal likely using default loan terms; check loan_terms SQL row)",
            dscr, _DSCR_CAP,
        )
        dscr = _DSCR_CAP
    funded_debt_to_ebitda = funded_debt / ebitda if ebitda > 0 else None

    return {
        "scenario":                  scenario,
        "projection_year":           proj_year,
        "projection_date":           date(proj_year, 12, 31),
        "revenue":                   round(revenue, 2),
        "ebitda":                    round(ebitda, 2),
        "ebit":                      round(ebit, 2),
        "net_income":                round(net_income, 2),
        "operating_cash_flow":       round(operating_cf, 2),
        "capital_expenditures":      round(capex, 2),
        "free_cash_flow":            round(free_cf, 2),
        "dscr":                      round(dscr, 4) if dscr is not None else None,
        "funded_debt":               round(funded_debt, 2),
        "funded_debt_to_ebitda":     round(funded_debt_to_ebitda, 4) if funded_debt_to_ebitda is not None else None,
        "ending_cash":               round(ending_cash, 2),
        "revenue_growth_assumption": round(sa["cagr"] if year_idx > 0 or scenario != "stress"
                                           else sa["y1_shock"], 6),
        "ebitda_margin_assumption":  round(ebitda_margin, 6),
    }


# ---------------------------------------------------------------------------
# Covenant testing
# ---------------------------------------------------------------------------

def _test_covenants(
    proj: dict,
    loan_terms: dict,
    debt_service: float,
    deal_id: str,
    pipeline_run_id: str,
) -> list[dict]:
    """Return one covenant result dict per covenant for a single projected year × scenario."""
    dscr          = proj.get("dscr") or 0.0
    funded_debt   = proj.get("funded_debt") or 0.0
    ebitda        = proj.get("ebitda") or 0.0
    capex         = proj.get("capital_expenditures") or 0.0
    ending_cash   = proj.get("ending_cash") or 0.0
    revolver      = loan_terms.get("revolver_availability") or 0.0
    fcc           = (ebitda - capex) / debt_service if debt_service > 0 else 0.0
    liquidity     = ending_cash + revolver

    # Override minimum_liquidity threshold from covenants table if a row exists
    min_liq_threshold = _DEFAULT_MIN_LIQUIDITY
    try:
        from services.sql_service import get_minimum_liquidity_threshold
        _deal_id = loan_terms.get("deal_id") or deal_id
        _override = get_minimum_liquidity_threshold(_deal_id)
        if _override is not None:
            min_liq_threshold = _override
    except Exception:
        pass  # fall back to default — non-fatal

    computed_values = {
        "dscr":                 dscr,
        "funded_debt_ebitda":   funded_debt / ebitda if ebitda > 0 else 0.0,
        "fixed_charge_coverage": fcc,
        "minimum_liquidity":    liquidity,
        "springing_trigger":    dscr,
    }
    thresholds = {
        "dscr":                 1.25,
        "funded_debt_ebitda":   4.0,
        "fixed_charge_coverage": 1.10,
        "minimum_liquidity":    min_liq_threshold,
        "springing_trigger":    1.10,
    }

    results = []
    for cov in _COVENANTS:
        ct      = cov["covenant_type"]
        thresh  = thresholds[ct]
        op      = cov["threshold_operator"]
        computed = computed_values[ct]
        results.append({
            "deal_id":            deal_id,
            "pipeline_run_id":    pipeline_run_id,
            "scenario":           proj["scenario"],
            "projection_year":    proj["projection_year"],
            "covenant_type":      ct,
            "formula":            cov["formula"],
            "threshold_value":    thresh,
            "threshold_operator": op,
            "computed_value":     round(computed, 4),
            "trigger_action":     cov["trigger_action"],
            "is_breach_year":     False,  # set below for stress DSCR
        })

    # Flag first stress DSCR < 1.25 year as is_breach_year
    if proj["scenario"] == "stress":
        for r in results:
            if r["covenant_type"] == "dscr" and (r["computed_value"] or 0) < 1.25:
                r["is_breach_year"] = True

    return results


# ---------------------------------------------------------------------------
# Markdown summary writer
# ---------------------------------------------------------------------------

def _build_summary_md(
    all_projections: dict[str, list[dict]],
    all_covenants: dict[str, list[dict]],
    borrower_name: str,
    base_year: int,
    debt_service: float,
) -> str:
    scenarios = ["base", "upside", "stress"]
    years = sorted({p["projection_year"] for p in all_projections.get("base", [])})

    def _fmt(v, pct=False, x=False):
        if v is None:
            return "—"
        if pct:
            return f"{v*100:.1f}%"
        if x:
            return f"{v:.2f}x"
        if abs(v) >= 1_000_000:
            return f"${v/1_000_000:,.1f}M"
        if abs(v) >= 1_000:
            return f"${v/1_000:,.0f}K"
        return f"${v:,.0f}"

    lines = [
        f"## Projections Summary — {borrower_name}",
        f"*Generated {date.today().isoformat()} | Base year: {base_year} | Annual debt service: {_fmt(debt_service)}*",
        "",
        "### Revenue & EBITDA",
        "| Year | " + " | ".join(f"Rev ({s.title()})" for s in scenarios) +
        " | " + " | ".join(f"EBITDA ({s.title()})" for s in scenarios) + " |",
        "|---|" + "---|" * (len(scenarios) * 2),
    ]
    for yr in years:
        row_parts = [str(yr)]
        for s in scenarios:
            p = next((p for p in all_projections.get(s, []) if p["projection_year"] == yr), {})
            row_parts.append(_fmt(p.get("revenue")))
        for s in scenarios:
            p = next((p for p in all_projections.get(s, []) if p["projection_year"] == yr), {})
            margin = (p.get("ebitda") or 0) / (p.get("revenue") or 1)
            row_parts.append(f"{_fmt(p.get('ebitda'))} ({margin*100:.1f}%)")
        lines.append("| " + " | ".join(row_parts) + " |")

    lines += [
        "",
        "### DSCR by Scenario",
        "| Year | Base | Upside | Stress | Threshold |",
        "|---|---|---|---|---|",
    ]
    for yr in years:
        dscrs = {}
        for s in scenarios:
            p = next((p for p in all_projections.get(s, []) if p["projection_year"] == yr), {})
            dscrs[s] = p.get("dscr")
        stress_flag = " ⚠" if (dscrs.get("stress") or 9) < 1.25 else ""
        lines.append(
            f"| {yr} | {_fmt(dscrs.get('base'), x=True)} | "
            f"{_fmt(dscrs.get('upside'), x=True)} | "
            f"{_fmt(dscrs.get('stress'), x=True)}{stress_flag} | ≥ 1.25x |"
        )

    # Stress breach year callout
    breach_years = [
        r["projection_year"]
        for r in all_covenants.get("stress", [])
        if r.get("covenant_type") == "dscr" and r.get("is_breach_year")
    ]
    lines.append("")
    if breach_years:
        lines.append(
            f"> **Stress breach year: {min(breach_years)}** — "
            "DSCR falls below 1.25x threshold in the stress scenario. "
            "Technical default covenant triggered."
        )
    else:
        lines.append(
            "> **No stress breach year** — DSCR remains above 1.25x across all projection years "
            "even in the stress scenario."
        )

    lines += [
        "",
        "### Funded Debt / EBITDA",
        "| Year | Base | Upside | Stress | Threshold |",
        "|---|---|---|---|---|",
    ]
    for yr in years:
        fdes = {}
        for s in scenarios:
            p = next((p for p in all_projections.get(s, []) if p["projection_year"] == yr), {})
            fdes[s] = p.get("funded_debt_to_ebitda")
        lines.append(
            f"| {yr} | {_fmt(fdes.get('base'), x=True)} | "
            f"{_fmt(fdes.get('upside'), x=True)} | "
            f"{_fmt(fdes.get('stress'), x=True)} | ≤ 4.0x |"
        )

    lines += ["", f"*Projections are model outputs — not audited financial statements.*"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def run_projections(
    deal_id: str,
    workspace_root: str = "",
    pipeline_run_id: str | None = None,
) -> dict:
    """
    Run the deterministic 3-statement projection model for a deal.

    Input fallback chain:
      1. SQL tables (populated by IP1 pipeline run)
      2. Financials/extracted_data.json (always present after extraction)
      3. Hardcoded defaults (loan_terms only)
    """
    from services import sql_service, workspace_service as _ws

    if not workspace_root:
        workspace_root = str(_ws._get_root())

    run_id = pipeline_run_id or str(uuid4())
    logger.info("[projections] starting deal_id=%s run_id=%s", deal_id, run_id)

    # ── 1. Resolve entity_id ──────────────────────────────────────────────────
    entity_id = sql_service.get_entity_id_for_deal(deal_id) or ""
    if not entity_id:
        logger.info("[projections] entity_id not in SQL — using filesystem fallback for deal_id=%s", deal_id)

    # ── 2. Load financial statements ─────────────────────────────────────────
    income_stmts, balance_sheets, cash_flows = ([], [], [])
    if entity_id:
        income_stmts, balance_sheets, cash_flows = _load_financials_from_sql(entity_id)

    if not income_stmts:
        logger.info("[projections] SQL tables empty — loading from extracted_data.json")
        income_stmts, balance_sheets, cash_flows = _load_financials_from_json(workspace_root)

    if not income_stmts:
        return {
            "status": "error",
            "deal_id": deal_id,
            "message": "No financial data available — run extraction first",
        }

    # Sort ascending by year
    income_stmts = sorted(income_stmts, key=lambda r: r["fiscal_year"])
    balance_sheets = sorted(balance_sheets, key=lambda r: r["as_of_date"])
    cash_flows = sorted(cash_flows, key=lambda r: r["fiscal_year"])

    # ── 3. Load management guidance (optional) ───────────────────────────────
    guidance = sql_service.get_management_guidance(entity_id) if entity_id else None

    # ── 4. Load loan terms ───────────────────────────────────────────────────
    loan_terms = _load_loan_terms(deal_id, workspace_root)
    debt_service = _compute_debt_service(loan_terms)

    # ── 5. Derive base-year anchor values ────────────────────────────────────
    latest_is  = income_stmts[-1]
    latest_bs  = balance_sheets[-1] if balance_sheets else {}
    base_year  = latest_is["fiscal_year"]
    base_rev   = latest_is["revenue"]
    base_cash  = latest_bs.get("cash_and_equivalents") or 0.0
    base_debt  = (latest_bs.get("long_term_debt") or 0.0) + (latest_bs.get("short_term_debt") or 0.0)

    borrower_name = deal_id  # display fallback; overridden below if SQL has it
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import Deal
        from sqlalchemy import select
        with next(get_sql_session()) as session:
            deal_row = session.execute(
                select(Deal).where(Deal.deal_id == deal_id).limit(1)
            ).scalar_one_or_none()
        if deal_row:
            borrower_name = deal_row.borrower_entity_name
    except Exception:
        pass

    # ── 6. Compute scenario assumptions ─────────────────────────────────────
    assumptions = _scenario_assumptions(income_stmts, cash_flows, guidance)
    logger.info(
        "[projections] assumptions base_cagr=%.2f%% base_ebitda_margin=%.1f%% "
        "debt_service=%.0f base_year=%d",
        assumptions["base"]["cagr"] * 100,
        assumptions["base"]["ebitda_margin"] * 100,
        debt_service, base_year,
    )

    # ── 7. Run 3-statement model ─────────────────────────────────────────────
    all_projections: dict[str, list[dict]] = {"base": [], "upside": [], "stress": []}
    all_covenants:   dict[str, list[dict]] = {"base": [], "upside": [], "stress": []}

    for scenario in ("base", "upside", "stress"):
        prior_rev  = base_rev
        prior_debt = base_debt
        prior_cash = base_cash

        for i in range(_PROJECTION_YEARS):
            proj = _project_year(
                scenario=scenario, year_idx=i,
                prior_revenue=prior_rev, prior_funded_debt=prior_debt,
                prior_cash=prior_cash, assumptions=assumptions,
                loan_terms=loan_terms, debt_service=debt_service,
                base_year=base_year,
            )
            proj["entity_id"]        = entity_id
            proj["deal_id"]          = deal_id
            proj["pipeline_run_id"]  = run_id

            covs = _test_covenants(proj, loan_terms, debt_service, deal_id, run_id)

            all_projections[scenario].append(proj)
            all_covenants[scenario].extend(covs)

            # Carry forward for next year
            prior_rev  = proj["revenue"]
            prior_debt = proj["funded_debt"]
            prior_cash = proj["ending_cash"]

    # ── 8. Write filesystem outputs ──────────────────────────────────────────
    financials_dir = Path(workspace_root) / "Financials"
    financials_dir.mkdir(parents=True, exist_ok=True)

    proj_json_path = financials_dir / "projections.json"
    cov_json_path  = financials_dir / "covenant_compliance.json"
    summary_path   = financials_dir / "projections_summary.md"

    proj_payload = {
        "deal_id":         deal_id,
        "entity_id":       entity_id,
        "pipeline_run_id": run_id,
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "base_year":       base_year,
        "debt_service":    debt_service,
        "scenarios":       {s: _serialise(all_projections[s]) for s in ("base", "upside", "stress")},
    }
    cov_payload = {
        "deal_id":         deal_id,
        "pipeline_run_id": run_id,
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "scenarios":       {s: _serialise(all_covenants[s]) for s in ("base", "upside", "stress")},
    }

    try:
        proj_json_path.write_text(json.dumps(proj_payload, indent=2, default=str), encoding="utf-8")
        cov_json_path.write_text(json.dumps(cov_payload, indent=2, default=str), encoding="utf-8")
        logger.info("[projections] wrote projections.json + covenant_compliance.json")
    except Exception as exc:
        logger.warning("[projections] filesystem write failed: %s", exc)

    try:
        md = _build_summary_md(all_projections, all_covenants, borrower_name, base_year, debt_service)
        summary_path.write_text(md, encoding="utf-8")
        logger.info("[projections] wrote projections_summary.md")
    except Exception as exc:
        logger.warning("[projections] summary md write failed: %s", exc)

    # ── 9b. Persist projection assumptions first (D-3: fail-silent) ────────────
    # Must run before step 9 so assumptions_id is available to link to projection rows.
    assumptions_ids: dict[str, str | None] = {"base": None, "upside": None, "stress": None}
    for scenario in ("base", "upside", "stress"):
        scen_assump = assumptions[scenario]
        try:
            aid = sql_service.insert_projection_assumptions(deal_id, run_id, {
                "scenario":                scenario,
                "revenue_growth_rate":     scen_assump.get("cagr"),
                "ebitda_margin_assumption": scen_assump.get("ebitda_margin"),
                "capex_pct_revenue":       scen_assump.get("capex_pct"),
                "interest_rate_assumption": None,
                "debt_paydown_rate":       None,
                "macro_scenario_tag":      scenario,
            })
            assumptions_ids[scenario] = aid
        except Exception as _ae:
            logger.warning("[projections] insert_projection_assumptions(%s) failed: %s", scenario, _ae)

    # ── 9. Persist to SQL (D-3: fail-silent) ────────────────────────────────
    # DELETE-before-insert: remove any existing rows for this entity+run to
    # prevent accumulation across repeated projections calls (Issue B fix).
    # Target schema UNIQUE key is (entity_id, pipeline_run_id, scenario, projection_year).
    try:
        from services.db_factory import get_sql_session
        from models.sql_models import Projection
        from sqlalchemy import delete as _delete
        with next(get_sql_session()) as _del_session:
            _del_session.execute(
                _delete(Projection).where(
                    Projection.entity_id == entity_id,
                    Projection.pipeline_run_id == run_id,
                )
            )
            _del_session.commit()
    except Exception as _del_exc:
        logger.warning("[projections] DELETE-before-insert failed — %s", _del_exc)

    proj_rows_written = 0
    cov_rows_written  = 0
    for scenario in ("base", "upside", "stress"):
        for proj in all_projections[scenario]:
            sql_row = {k: v for k, v in proj.items()
                       if k not in ("entity_id", "deal_id", "pipeline_run_id")}
            sql_row["entity_id"]       = entity_id
            sql_row["deal_id"]         = deal_id
            sql_row["pipeline_run_id"] = run_id
            sql_row["assumptions_id"]  = assumptions_ids.get(scenario)
            if sql_service.insert_projection(sql_row):
                proj_rows_written += 1

        for cov in all_covenants[scenario]:
            if sql_service.insert_covenant_compliance_projection(cov):
                cov_rows_written += 1

    logger.info(
        "[projections] SQL: %d projection rows, %d covenant rows written",
        proj_rows_written, cov_rows_written,
    )

    # ── 9c. Persist sensitivity analyses — stress vs base shocks (D-3) ──────
    # shock_magnitude_pct is stored as a decimal fraction (e.g. -0.20 = 20% shock),
    # NOT as a percentage. y1_shock is already -0.20; margin delta is already fractional.
    try:
        base_last  = all_projections["base"][-1]  if all_projections["base"]  else {}
        stress_last = all_projections["stress"][-1] if all_projections["stress"] else {}
        if base_last and stress_last:
            # Revenue shock row — y1_shock is stored as-is (e.g. -0.20)
            sql_service.insert_sensitivity_analysis(deal_id, run_id, {
                "variable_shocked":   "revenue_growth",
                "shock_magnitude_pct": assumptions["stress"].get("y1_shock", -0.20),
                "resulting_dscr":     stress_last.get("dscr"),
                "resulting_leverage": stress_last.get("funded_debt_to_ebitda"),
                "resulting_fcf":      stress_last.get("free_cash_flow"),
                "covenant_breach_year": next(
                    (r["projection_year"] for r in all_covenants["stress"]
                     if r.get("covenant_type") == "dscr" and r.get("is_breach_year")),
                    None,
                ),
            })
            # EBITDA margin compression row — delta is already fractional (e.g. -0.025)
            margin_shock = round(
                assumptions["stress"]["ebitda_margin"] - assumptions["base"]["ebitda_margin"], 6
            )
            sql_service.insert_sensitivity_analysis(deal_id, run_id, {
                "variable_shocked":    "ebitda_margin",
                "shock_magnitude_pct": margin_shock,
                "resulting_dscr":      stress_last.get("dscr"),
                "resulting_leverage":  stress_last.get("funded_debt_to_ebitda"),
                "resulting_fcf":       stress_last.get("free_cash_flow"),
                "covenant_breach_year": next(
                    (r["projection_year"] for r in all_covenants["stress"]
                     if r.get("covenant_type") == "dscr" and r.get("is_breach_year")),
                    None,
                ),
            })
    except Exception as _se:
        logger.warning("[projections] insert_sensitivity_analysis failed: %s", _se)

    # ── 10. Build summary for caller ────────────────────────────────────────
    stress_breach = next(
        (r["projection_year"]
         for r in all_covenants["stress"]
         if r.get("covenant_type") == "dscr" and r.get("is_breach_year")),
        None,
    )
    return {
        "status":            "complete",
        "deal_id":           deal_id,
        "pipeline_run_id":   run_id,
        "base_year":         base_year,
        "projection_years":  _PROJECTION_YEARS,
        "debt_service":      debt_service,
        "scenarios_run":     ["base", "upside", "stress"],
        "stress_breach_year": stress_breach,
        "sql_projection_rows": proj_rows_written,
        "sql_covenant_rows":   cov_rows_written,
        "outputs": {
            "projections_json":       str(proj_json_path),
            "covenant_compliance_json": str(cov_json_path),
            "projections_summary_md": str(summary_path),
        },
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialise(rows: list[dict]) -> list[dict]:
    """Convert date objects to ISO strings for JSON serialisation."""
    out = []
    for row in rows:
        r = {}
        for k, v in row.items():
            r[k] = v.isoformat() if isinstance(v, date) else v
        out.append(r)
    return out
