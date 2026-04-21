"""Quick schema verification after Phase 3B + 3B.10 migrations."""
import sqlite3

con = sqlite3.connect("data/deckr.db")

tables = sorted([r[0] for r in con.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()])

views = sorted([r[0] for r in con.execute(
    "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name"
).fetchall()])

indexes = {r[0] for r in con.execute(
    "SELECT name FROM sqlite_master WHERE type='index'"
).fetchall()}

print(f"TABLES ({len(tables)}):")
for t in tables:
    print(f"  {t}")

print(f"\nVIEWS ({len(views)}):")
for v in views:
    print(f"  {v}")

# -------------------------------------------------------------------
# Phase 3B — original checks
# -------------------------------------------------------------------
cols_mg = [r[1] for r in con.execute("PRAGMA table_info(management_guidance)").fetchall()]
cols_lt = [r[1] for r in con.execute("PRAGMA table_info(loan_terms)").fetchall()]
cols_is = [r[1] for r in con.execute("PRAGMA table_info(income_statements)").fetchall()]

print("\n--- Phase 3B original checks ---")
print("  source_text removed from management_guidance:", "source_text" not in cols_mg)
print("  source added to management_guidance:", "source" in cols_mg)
print("  covenant_definitions removed from loan_terms:", "covenant_definitions" not in cols_lt)
print("  revenue_segments removed from income_statements:", "revenue_segments" not in cols_is)

# -------------------------------------------------------------------
# Phase 3B.10 — discrepancy correction checks
# -------------------------------------------------------------------
cols_cov = [r[1] for r in con.execute("PRAGMA table_info(covenants)").fetchall()]
cols_fr  = [r[1] for r in con.execute("PRAGMA table_info(financial_ratios)").fetchall()]
cols_ss  = {r[1]: r for r in con.execute("PRAGMA table_info(slacr_scores)").fetchall()}
cols_rs  = [r[1] for r in con.execute("PRAGMA table_info(revenue_segments)").fetchall()]
cols_pr  = [r[1] for r in con.execute("PRAGMA table_info(projections)").fetchall()]
cols_al  = [r[1] for r in con.execute("PRAGMA table_info(audit_log)").fetchall()]
alembic_ver = con.execute("SELECT version_num FROM alembic_version").fetchone()

print("\n--- Phase 3B.10 discrepancy correction checks ---")
print(f"  Alembic version:                                   {alembic_ver[0] if alembic_ver else 'MISSING'}")
print(f"  covenants.threshold_operator added:                {'threshold_operator' in cols_cov}")
print(f"  covenants.covenant_type present:                   {'covenant_type' in cols_cov}")
print(f"  financial_ratios.interest_coverage present:        {'interest_coverage' in cols_fr}")
print(f"  financial_ratios.asset_turnover present:           {'asset_turnover' in cols_fr}")
print(f"  slacr_scores.internal_rating present:              {'internal_rating' in cols_ss}")
print(f"  revenue_segments.pct_of_total_revenue present:     {'pct_of_total_revenue' in cols_rs}")
print(f"  revenue_segments.yoy_growth present:               {'yoy_growth' in cols_rs}")
print(f"  projections.dscr present:                          {'dscr' in cols_pr}")
print(f"  projections.funded_debt_to_ebitda present:         {'funded_debt_to_ebitda' in cols_pr}")
print(f"  audit_log deal_id+timestamp index created:         {'ix_audit_log_deal_timestamp' in indexes}")

con.close()
