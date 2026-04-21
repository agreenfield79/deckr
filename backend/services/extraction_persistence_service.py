"""
Extraction Persistence Service — Integration Point 1 (IP1).

Called synchronously after run_extraction() completes and BEFORE the parallel
ThreadPoolExecutor stage starts. This is the IP1 gate.

Gate contract (DD Layer 7):
  - SQL financial rows COUNT > 0 for the primary entity
  - Neo4j anchor nodes created (Company, Loan, Collateral)
  Only when both checks pass does the parallel stage proceed.
  On failure: raises ExtractionSeedError so agent_service.py emits step_error and halts.
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import date

logger = logging.getLogger("deckr.extraction_persistence")


class ExtractionSeedError(Exception):
    """Raised when IP1 gate checks fail — pipeline must halt."""
    pass


@dataclass
class SeedResult:
    success: bool
    sql_row_count: int
    neo4j_nodes_created: int
    entity_id: str | None = None
    deal_id: str | None = None
    workspace_id: str | None = None
    errors: list[str] | None = None


def _sql_seed_atomic(
    workspace_id: str,
    workspace_root: str,
    borrower_name: str,
    deal_id: str,
    entity_structure: str | None,
    naics_code: str | None,
    fiscal_years: dict,
    raw_segments: dict,
    raw_guidance: dict,
    loan_terms_path: str,
    state_of_incorporation: str | None = None,
    years_in_business: int | None = None,
) -> tuple[str | None, int, list[str]]:
    """
    Write all IP1 SQL rows (workspace, deal, entity, financial statements,
    loan terms, revenue segments, management guidance) in a SINGLE atomic
    transaction. Rolls back everything if any write fails.

    Returns (entity_id, sql_rows_written, error_list).
    Raises ExtractionSeedError on unrecoverable failures.
    """
    from services.db_factory import atomic_session
    from models.sql_models import (
        Workspace, Deal, Entity,
        IncomeStatement, BalanceSheet, CashFlowStatement,
        LoanTerms, RevenueSegment, ManagementGuidance,
    )
    from datetime import datetime, timezone
    from uuid import uuid4 as _uuid4

    entity_id = str(_uuid4())
    sql_rows = 0
    errors: list[str] = []
    now = datetime.now(timezone.utc)

    try:
        with atomic_session() as session:
            # Workspace — upsert by PK, with fallback lookup by project_path.
            # project_path has a UNIQUE constraint, so re-runs with a fresh
            # workspace_id UUID must reuse the existing row rather than INSERT.
            from sqlalchemy import select as _select
            existing_ws = session.get(Workspace, workspace_id)
            if existing_ws is None:
                existing_ws = session.execute(
                    _select(Workspace).where(Workspace.project_path == workspace_root)
                ).scalar_one_or_none()
                if existing_ws:
                    workspace_id = existing_ws.workspace_id  # reuse stable ID
            if existing_ws:
                existing_ws.borrower_name = borrower_name
                existing_ws.updated_at = now
            else:
                session.add(Workspace(
                    workspace_id=workspace_id, project_path=workspace_root,
                    borrower_name=borrower_name, created_at=now, updated_at=now,
                ))

            # Deal — upsert
            existing_deal = session.get(Deal, deal_id)
            if existing_deal:
                existing_deal.updated_at = now
            else:
                session.add(Deal(
                    deal_id=deal_id, workspace_id=workspace_id,
                    borrower_entity_name=borrower_name,
                    entity_structure=entity_structure,
                    naics_code=naics_code,
                    created_at=now, updated_at=now,
                ))

            # Entity — insert (new each seed run)
            session.add(Entity(
                entity_id=entity_id, deal_id=deal_id,
                entity_type="borrower_company", legal_name=borrower_name,
                state_of_incorporation=state_of_incorporation,
                years_in_business=years_in_business,
                created_at=now,
            ))
            session.flush()  # make entity_id available for FK references below

            # Financial statements — one row per year per statement type
            for year_str, year_data in fiscal_years.items():
                year = _safe_int(year_str.replace("FY", "").replace("fy", "")) or _safe_int(year_str)
                if year is None:
                    continue

                is_data = year_data.get("income_statement", {})
                if is_data:
                    session.add(IncomeStatement(
                        statement_id=str(_uuid4()), entity_id=entity_id,
                        fiscal_year=year, extracted_at=now, **_map_income(is_data),
                    ))
                    sql_rows += 1

                bs_data = year_data.get("balance_sheet", {})
                if bs_data:
                    as_of = _fiscal_year_end(year, bs_data)
                    session.add(BalanceSheet(
                        balance_sheet_id=str(_uuid4()), entity_id=entity_id,
                        as_of_date=as_of, extracted_at=now,
                        **{**_map_balance(bs_data), **_map_balance_str(bs_data)},
                    ))
                    sql_rows += 1

                cf_data = year_data.get("cash_flow", {})
                if cf_data:
                    session.add(CashFlowStatement(
                        cashflow_id=str(_uuid4()), entity_id=entity_id,
                        fiscal_year=year, extracted_at=now, **_map_cashflow(cf_data),
                    ))
                    sql_rows += 1

            # Loan terms — from loan_terms.json if present
            if os.path.exists(loan_terms_path):
                try:
                    with open(loan_terms_path, "r", encoding="utf-8") as f:
                        lt = json.load(f)
                    session.add(LoanTerms(
                        loan_terms_id=str(_uuid4()), deal_id=deal_id,
                        entity_id=entity_id,
                        created_at=now, **_map_loan_terms(lt),
                    ))
                except Exception as exc:
                    errors.append(f"loan_terms.json seed failed: {exc}")

            # Revenue segments (v2)
            for yr_label, seg_list in raw_segments.items():
                yr = _safe_int(yr_label.replace("FY", "").replace("fy", "")) or _safe_int(yr_label)
                if yr is None or not isinstance(seg_list, list):
                    continue
                for seg in seg_list:
                    if not isinstance(seg, dict) or not seg.get("segment_name"):
                        continue
                    session.add(RevenueSegment(
                        segment_id=str(_uuid4()),
                        entity_id=entity_id,
                        fiscal_year=yr,
                        segment_name=seg["segment_name"],
                        segment_revenue=_safe_float(seg.get("segment_revenue")),
                        pct_of_total_revenue=_safe_float(seg.get("pct_of_total_revenue")),
                    ))

            # Management guidance (v2)
            if raw_guidance:
                session.add(ManagementGuidance(
                    guidance_id=str(_uuid4()),
                    entity_id=entity_id,
                    extracted_at=now,
                    guidance_period=raw_guidance.get("guidance_period"),
                    next_year_revenue_low=_safe_float(raw_guidance.get("next_year_revenue_low")),
                    next_year_revenue_mid=_safe_float(raw_guidance.get("next_year_revenue_mid")),
                    next_year_revenue_high=_safe_float(raw_guidance.get("next_year_revenue_high")),
                    next_year_ebitda_margin=_safe_float(raw_guidance.get("next_year_ebitda_margin")),
                    growth_drivers=raw_guidance.get("growth_drivers"),
                    risk_factors=raw_guidance.get("risk_factors"),
                    source=raw_guidance.get("source"),
                ))

    except ExtractionSeedError:
        raise
    except Exception as exc:
        raise ExtractionSeedError(
            f"IP1 SQL atomic write failed — full rollback applied: {exc}"
        ) from exc

    return entity_id, sql_rows, errors


def seed(workspace_root: str, deal_id: str | None = None,
         workspace_id: str | None = None) -> SeedResult:
    """
    Read extracted_data.json from workspace, map fields to ORM objects,
    write to SQL + MongoDB + Neo4j. Runs synchronously (blocks pipeline).

    Returns SeedResult with sql_row_count > 0 on success.
    Raises ExtractionSeedError if the gate fails (no financial rows seeded).
    """
    from services import sql_service, mongo_service, graph_service

    errors: list[str] = []
    sql_rows = 0
    neo4j_nodes = 0

    # ── 1. Load extracted_data.json ──────────────────────────────────────────
    extracted_path = os.path.join(workspace_root, "Financials", "extracted_data.json")
    if not os.path.exists(extracted_path):
        raise ExtractionSeedError(
            f"extracted_data.json not found at {extracted_path} — extraction may have failed"
        )
    try:
        with open(extracted_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        raise ExtractionSeedError(f"Failed to parse extracted_data.json: {exc}") from exc

    # ── 2. Derive IDs ────────────────────────────────────────────────────────
    company_raw = data.get("company", {})
    # Extraction agent YAML outputs company as a plain string (legal name).
    # IP1 also accepts the richer dict form used by v2 layout.
    if isinstance(company_raw, str):
        company: dict = {"company_name": company_raw}
    elif isinstance(company_raw, dict):
        company = company_raw
    else:
        company = {}
    borrower_name = company.get("company_name") or company.get("borrower_name", "Unknown Borrower")
    naics_code = company.get("naics_code")
    entity_structure = company.get("entity_structure") or company.get("structure")

    if not deal_id:
        from uuid import uuid4
        deal_id = str(uuid4())
        logger.info("[IP1] No deal_id provided — generated new deal_id: %s", deal_id)

    if not workspace_id:
        from uuid import uuid4
        workspace_id = str(uuid4())

    # ── 3-7. SQL — Derive fiscal year data, then write atomically ────────────
    fiscal_years: dict = data.get("fiscal_years", {})
    # Extraction agent may return fiscal_years as a list of year objects rather
    # than a year-keyed dict. Normalise to dict before calling _sql_seed_atomic.
    if isinstance(fiscal_years, list):
        converted: dict = {}
        for yr_obj in fiscal_years:
            if isinstance(yr_obj, dict):
                yr_key = str(
                    yr_obj.get("year") or yr_obj.get("fiscal_year") or len(converted)
                )
                converted[yr_key] = yr_obj
        fiscal_years = converted
    if not fiscal_years:
        fiscal_years = _reshape_v1(data)

    # revenue_segments may also arrive as a list; normalise to dict
    raw_segments = data.get("revenue_segments", {})
    if isinstance(raw_segments, list):
        raw_segments = {}  # list format not yet supported; skip silently

    # management_guidance may arrive as a list; take first element if so
    raw_guidance = data.get("management_guidance", {})
    if isinstance(raw_guidance, list):
        raw_guidance = raw_guidance[0] if raw_guidance else {}

    entity_id, sql_rows, sql_errors = _sql_seed_atomic(
        workspace_id=workspace_id,
        workspace_root=workspace_root,
        borrower_name=borrower_name,
        deal_id=deal_id,
        entity_structure=entity_structure,
        naics_code=naics_code,
        fiscal_years=fiscal_years,
        raw_segments=raw_segments,
        raw_guidance=raw_guidance,
        loan_terms_path=os.path.join(workspace_root, "Financials", "loan_terms.json"),
        state_of_incorporation=company.get("state_of_incorporation"),
        years_in_business=_safe_int(company.get("years_in_business")),
    )
    errors.extend(sql_errors)
    if not entity_id:
        errors.append("SQL seed returned no entity_id — IP1 will fail gate check")

    # ── 8. MongoDB — Document Index ───────────────────────────────────────────
    # 3C.2: upsert_workspace (mongo) removed — SQL workspaces table is authoritative
    for upload_info in data.get("uploaded_documents", []):
        mongo_service.index_document(
            workspace_id=workspace_id,
            deal_id=deal_id,
            document_id=upload_info.get("document_id", ""),
            file_name=upload_info.get("file_name", ""),
            file_path=upload_info.get("file_path", ""),
            document_type=upload_info.get("document_type", "other"),
            entity_id=entity_id,
        )

    # ── 9. Neo4j — 5A Anchor Nodes ────────────────────────────────────────────
    if entity_id:
        company_data = data.get("company", {})
        if isinstance(company_data, str):
            company_data = {}
        ok = graph_service.write_company_node(
            deal_id=deal_id,
            entity_id=entity_id,
            legal_name=borrower_name,
            naics_code=naics_code,
            role="borrower",
            entity_type="borrower_company",
            dba=company_data.get("dba"),
            formation_date=company_data.get("formation_date"),
            status=company_data.get("status"),
        )
        if ok:
            neo4j_nodes += 1
        if naics_code:
            graph_service.write_operates_in_relationship(
                entity_id, naics_code, primary_flag=True,
            )

    # Loan node + REQUESTS relationship (Phase 3D.2 / 3D.7-D2)
    loan_terms_data = sql_service.get_loan_terms(deal_id)
    loan_terms_id = (loan_terms_data or {}).get("loan_terms_id", "")
    if entity_id and loan_terms_id:
        raw_lt = data.get("loan_terms", {})
        if isinstance(raw_lt, list):
            raw_lt = raw_lt[0] if raw_lt else {}
        ok_loan = graph_service.write_loan_node(
            deal_id=deal_id,
            loan_terms_id=loan_terms_id,
            loan_type=raw_lt.get("loan_type"),
            term_months=_safe_int(raw_lt.get("term_months")),
            rate_type=raw_lt.get("rate_type"),
            status=raw_lt.get("status") or "pending",
        )
        if ok_loan:
            neo4j_nodes += 1
        graph_service.write_requests_relationship(
            entity_id=entity_id,
            loan_terms_id=loan_terms_id,
        )

    # Document nodes — one per uploaded file (Phase 3D.2)
    # If the extraction agent didn't populate uploaded_documents, fall back to a
    # workspace directory scan so chunking still runs for any PDFs/docs present.
    uploaded_documents = data.get("uploaded_documents") or []
    if not uploaded_documents:
        _ws_root_path = os.path.join(workspace_root)
        _chunkable_exts = {".pdf", ".txt", ".md", ".docx"}
        _skip_dirs = {"Agent Notes", "Deck", "Loan Request", "Borrower"}
        try:
            for _dirpath, _dirs, _fnames in os.walk(_ws_root_path):
                _rel_dir = os.path.relpath(_dirpath, _ws_root_path)
                if any(_rel_dir.startswith(sd) for sd in _skip_dirs):
                    continue
                for _fname in _fnames:
                    if any(_fname.lower().endswith(ext) for ext in _chunkable_exts):
                        _abs = os.path.join(_dirpath, _fname)
                        _rel = os.path.relpath(_abs, _ws_root_path).replace("\\", "/")
                        uploaded_documents.append({
                            "document_id": str(__import__("uuid").uuid4()),
                            "file_name": _fname,
                            "file_path": _abs,
                            "document_type": "financial_statement" if "Financials" in _dirpath else "other",
                        })
        except Exception as _scan_exc:
            logger.warning("IP1: workspace scan for uploaded_documents failed — %s", _scan_exc)

    for upload_info in uploaded_documents:
        doc_id = upload_info.get("document_id", "")
        if not doc_id:
            continue
        # SQL documents row must exist BEFORE chunk_and_index_document so that
        # MongoDB document_chunks.document_id FK resolves (target schema 2D).
        try:
            sql_service.insert_document(
                workspace_id  = workspace_id,
                deal_id       = deal_id,
                file_name     = upload_info.get("file_name", ""),
                file_path     = upload_info.get("file_path", ""),
                document_type = upload_info.get("document_type") or "other",
                entity_id     = entity_id,
                document_id   = doc_id,
            )
        except Exception as _doc_exc:
            logger.warning("IP1: insert_document failed doc=%s — %s", doc_id, _doc_exc)
        graph_service.write_document_node(
            document_id=doc_id,
            deal_id=deal_id,
            file_name=upload_info.get("file_name", ""),
            document_type=upload_info.get("document_type"),
        )
        neo4j_nodes += 1
        if entity_id:
            graph_service.write_appears_in_edge(
                entity_id=entity_id,
                document_id=doc_id,
                role="borrower",
            )
        # 3E.5 — Chunk and index document text into MongoDB + vector store (D-3: fail-silent)
        if entity_id:
            try:
                from services import extraction_service as _ext_svc
                _ext_svc.chunk_and_index_document(
                    relative_path = upload_info.get("file_path", ""),
                    document_id   = doc_id,
                    deal_id       = deal_id,
                    entity_id     = entity_id,
                    document_type = upload_info.get("document_type"),
                )
            except Exception as _ce:
                logger.warning("IP1: chunk_and_index_document failed doc=%s — %s", doc_id, _ce)

    # Guarantor nodes
    for g in data.get("guarantors", []):
        g_entity_id = sql_service.insert_entity(
            deal_id=deal_id,
            entity_type="guarantor_individual",
            legal_name=g.get("name", "Unknown Guarantor"),
        )
        if g_entity_id:
            graph_service.write_individual_node(
                deal_id=deal_id,
                entity_id=g_entity_id,
                legal_name=g.get("name", ""),
                role="guarantor",
            )
            neo4j_nodes += 1
            if loan_terms_id:
                graph_service.write_guarantees_relationship(
                    g_entity_id, loan_terms_id,
                    guarantee_type=g.get("guarantee_type"),
                    coverage_pct=_safe_float(g.get("coverage_pct")),
                )

    # ── IP1 Gate Check ────────────────────────────────────────────────────────
    db_count = sql_service.count_financial_rows(entity_id or "")
    logger.info(
        "[IP1] seed complete — deal_id=%s entity_id=%s sql_rows=%d neo4j_nodes=%d db_count=%d errors=%d",
        deal_id, entity_id, sql_rows, neo4j_nodes, db_count, len(errors),
    )

    # P-4: Neo4j consistency check — warn if Neo4j online but no anchor nodes written
    if neo4j_nodes == 0 and entity_id:
        from services.db_factory import ping_neo4j
        if ping_neo4j():
            logger.warning(
                "[IP1] Neo4j is reachable but 0 anchor nodes were written for entity_id=%s. "
                "Graph and SQL may have diverged — check graph_service logs.",
                entity_id,
            )
            errors.append(
                f"Neo4j online but no anchor nodes created for entity_id={entity_id} "
                "— graph/SQL divergence detected."
            )
        else:
            logger.info("[IP1] Neo4j offline — skipping Neo4j consistency check")

    if db_count == 0:
        raise ExtractionSeedError(
            f"IP1 gate failed: 0 financial rows found in SQL for entity_id={entity_id}. "
            "Extraction may have produced no structured data. Halting pipeline."
        )

    return SeedResult(
        success=True,
        sql_row_count=db_count,
        neo4j_nodes_created=neo4j_nodes,
        entity_id=entity_id,
        deal_id=deal_id,
        workspace_id=workspace_id,
        errors=errors or None,
    )


# ---------------------------------------------------------------------------
# Field mapping helpers
# ---------------------------------------------------------------------------

def _safe_int(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _safe_float(val) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _fiscal_year_end(year: int, bs: dict) -> date:
    raw = bs.get("as_of_date") or bs.get("fiscal_year_end")
    if raw:
        try:
            from datetime import datetime
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except Exception:
            pass
    return date(year, 12, 31)


def _map_income(d: dict) -> dict:
    return {k: _safe_float(v) for k, v in {
        "revenue": d.get("revenue") or d.get("total_revenue"),
        "cost_of_goods_sold": d.get("cost_of_goods_sold") or d.get("cogs"),
        "cogs_product": d.get("cogs_product"),
        "cogs_services": d.get("cogs_services"),
        "gross_profit": d.get("gross_profit"),
        "research_and_development": d.get("research_and_development") or d.get("r_and_d"),
        "selling_general_administrative": d.get("selling_general_administrative") or d.get("sga"),
        "stock_based_compensation": d.get("stock_based_compensation") or d.get("sbc"),
        "restructuring_charges": d.get("restructuring_charges"),
        "operating_expenses": d.get("operating_expenses"),
        "ebitda": d.get("ebitda"),
        "depreciation_amortization": d.get("depreciation_amortization") or d.get("da"),
        "ebit": d.get("ebit") or d.get("operating_income"),
        "interest_expense": d.get("interest_expense"),
        "pre_tax_income": d.get("pre_tax_income") or d.get("pretax_income"),
        "effective_tax_rate": d.get("effective_tax_rate"),
        "tax_expense": d.get("tax_expense") or d.get("income_tax"),
        "net_income": d.get("net_income"),
    }.items() if v is not None}


def _map_balance(d: dict) -> dict:
    return {k: _safe_float(v) for k, v in {
        "cash_and_equivalents": d.get("cash_and_equivalents") or d.get("cash"),
        "accounts_receivable": d.get("accounts_receivable"),
        "days_sales_outstanding": d.get("days_sales_outstanding"),
        "inventory": d.get("inventory"),
        "days_inventory_outstanding": d.get("days_inventory_outstanding"),
        "deferred_revenue": d.get("deferred_revenue"),
        "accrued_liabilities": d.get("accrued_liabilities"),
        "total_current_assets": d.get("total_current_assets") or d.get("current_assets"),
        "total_assets": d.get("total_assets"),
        "accounts_payable": d.get("accounts_payable"),
        "days_payable_outstanding": d.get("days_payable_outstanding"),
        "short_term_debt": d.get("short_term_debt"),
        "total_current_liabilities": d.get("total_current_liabilities") or d.get("current_liabilities"),
        "long_term_debt": d.get("long_term_debt"),
        "funded_debt_rate_type": None,  # string field — handled separately below
        "weighted_avg_interest_rate": d.get("weighted_avg_interest_rate"),
        "total_liabilities": d.get("total_liabilities"),
        "retained_earnings": d.get("retained_earnings"),
        "total_equity": d.get("total_equity") or d.get("stockholders_equity"),
    }.items() if v is not None}


def _map_balance_str(d: dict) -> dict:
    """Return string-typed v2 balance sheet fields (not floats)."""
    result = {}
    if d.get("funded_debt_rate_type"):
        result["funded_debt_rate_type"] = str(d["funded_debt_rate_type"])
    if d.get("debt_maturity_schedule"):
        result["debt_maturity_schedule"] = d["debt_maturity_schedule"]  # kept as-is (JSON)
    return result


def _map_cashflow(d: dict) -> dict:
    return {k: _safe_float(v) for k, v in {
        "operating_cash_flow": d.get("operating_cash_flow") or d.get("cfo"),
        "stock_based_compensation": d.get("stock_based_compensation") or d.get("sbc"),
        "capital_expenditures": d.get("capital_expenditures") or d.get("capex"),
        "maintenance_capex": d.get("maintenance_capex"),
        "growth_capex": d.get("growth_capex"),
        "acquisitions": d.get("acquisitions"),
        "investing_cash_flow": d.get("investing_cash_flow") or d.get("cfi"),
        "debt_repayment": d.get("debt_repayment"),
        "share_repurchases": d.get("share_repurchases"),
        "financing_cash_flow": d.get("financing_cash_flow") or d.get("cff"),
        "net_change_in_cash": d.get("net_change_in_cash"),
        "free_cash_flow": d.get("free_cash_flow") or d.get("fcf"),
    }.items() if v is not None}


def _map_loan_terms(d: dict) -> dict:
    return {k: v for k, v in {
        "loan_amount": _safe_float(d.get("loan_amount")),
        "interest_rate": _safe_float(d.get("interest_rate")),
        "rate_type": d.get("rate_type"),
        "amortization_years": _safe_int(d.get("amortization_years")),
        "term_months": _safe_int(d.get("term_months")),
        "proposed_annual_debt_service": _safe_float(d.get("proposed_annual_debt_service")),
        "revolver_availability": _safe_float(d.get("revolver_availability")),
    }.items() if v is not None}


def _reshape_v1(data: dict) -> dict:
    """
    Reshape flat v1 / agent-YAML extracted_data.json into the fiscal_years dict.

    Handles three input formats:
      A) Agent YAML output — income_statement = {field: {FY2024: val, FY2025: val}, ...}
         (fields are keys, values are year-keyed dicts — transposed/inverted layout)
      B) Simple top-level year keys — {"2024": {income_statement: {...}, ...}}
      C) Last resort — flat single-year data
    """
    fiscal_years: dict = {}

    # Format B: year-keyed dicts at the top level
    for possible_year_key in ["2025", "2024", "2023", "2022", "2021", "2020"]:
        if possible_year_key in data:
            fiscal_years[possible_year_key] = data[possible_year_key]
    if fiscal_years:
        return fiscal_years

    # Format A: agent YAML output — income_statement values are year-keyed dicts
    raw_is = data.get("income_statement", {})
    raw_bs = data.get("balance_sheet", {})
    raw_cf = data.get("cash_flow_statement", {}) or data.get("cash_flow", {})

    # Collect all year labels present across any statement
    all_years: set[str] = set()
    for stmnt in (raw_is, raw_bs, raw_cf):
        for field_vals in stmnt.values():
            if isinstance(field_vals, dict):
                all_years.update(field_vals.keys())

    if all_years:
        # Pivot: year → {income_statement: {field: val}, balance_sheet: ..., cash_flow: ...}
        for yr in sorted(all_years):
            is_row = {field: vals.get(yr) for field, vals in raw_is.items() if isinstance(vals, dict)}
            bs_row = {field: vals.get(yr) for field, vals in raw_bs.items() if isinstance(vals, dict)}
            cf_row = {field: vals.get(yr) for field, vals in raw_cf.items() if isinstance(vals, dict)}
            fiscal_years[yr] = {
                "income_statement": {k: v for k, v in is_row.items() if v is not None},
                "balance_sheet":    {k: v for k, v in bs_row.items() if v is not None},
                "cash_flow":        {k: v for k, v in cf_row.items() if v is not None},
            }
        return fiscal_years

    # Format C: last resort — treat flat data as a single year entry
    current_year = data.get("fiscal_year") or "2024"
    fiscal_years[str(current_year)] = {
        "income_statement": raw_is or {},
        "balance_sheet":    raw_bs or {},
        "cash_flow":        raw_cf or {},
    }
    return fiscal_years
