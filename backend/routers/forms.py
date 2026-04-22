import json
import logging
import math

from fastapi import APIRouter, HTTPException

from models.borrower import BorrowerProfile
from models.loan import LoanRequest
from services import form_serializers, workspace_service

logger = logging.getLogger("deckr.routers.forms")

router = APIRouter()

_BORROWER_PATH = "Borrower/profile.md"
_LOAN_PATH = "Loan Request/request.md"
_LOAN_TERMS_PATH = "Financials/loan_terms.json"


@router.post("/borrower")
def save_borrower(profile: BorrowerProfile):
    content = form_serializers.serialize_borrower(profile)
    workspace_service.write_file(_BORROWER_PATH, content)
    logger.info("borrower profile saved: %s", _BORROWER_PATH)
    return {"saved": True, "path": _BORROWER_PATH}


@router.get("/borrower")
def get_borrower():
    try:
        content = workspace_service.read_file(_BORROWER_PATH)
    except HTTPException:
        return BorrowerProfile().model_dump()
    profile = form_serializers.parse_borrower(content)
    if profile is None:
        return BorrowerProfile().model_dump()
    return profile.model_dump()


@router.post("/loan")
def save_loan(request: LoanRequest):
    content = form_serializers.serialize_loan(request)
    workspace_service.write_file(_LOAN_PATH, content)
    logger.info("loan request saved: %s", _LOAN_PATH)

    # Also write Financials/loan_terms.json so projections_service can read actual deal terms.
    _write_loan_terms_json(request)

    return {"saved": True, "path": _LOAN_PATH}


@router.get("/loan")
def get_loan():
    try:
        content = workspace_service.read_file(_LOAN_PATH)
    except HTTPException:
        return LoanRequest().model_dump()
    request = form_serializers.parse_loan(content)
    if request is None:
        return LoanRequest().model_dump()
    return request.model_dump()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _write_loan_terms_json(request: LoanRequest) -> None:
    """
    Derive a machine-readable loan_terms.json from the loan form submission.
    Written to Financials/ so projections_service._load_loan_terms() picks it up.
    """
    try:
        amortization_years = round(request.amortization_months / 12, 2) if request.amortization_months else 20
        rate_decimal = round(request.interest_rate / 100.0, 6) if request.interest_rate else 0.0

        # Compute proposed_annual_debt_service when all three inputs are present.
        ads: float | None = None
        if request.loan_amount and rate_decimal and amortization_years:
            principal = float(request.loan_amount)
            r = rate_decimal / 12          # monthly rate
            n = int(amortization_years * 12)  # total months
            if r > 0 and n > 0:
                monthly = principal * r / (1 - (1 + r) ** -n)
                ads = round(monthly * 12, 2)
            elif n > 0:
                ads = round(principal / amortization_years, 2)

        lt: dict = {
            "loan_amount":                  float(request.loan_amount) if request.loan_amount else None,
            "loan_type":                    request.loan_type or None,       # term / revolver / LOC / SBA / bridge
            "interest_rate":               rate_decimal or None,
            "rate_type":                   "fixed",                           # fixed / floating — default fixed; update when floating-rate toggle added
            "amortization_years":          amortization_years if request.amortization_months else None,
            "term_months":                 request.term_months or None,
            "proposed_annual_debt_service": ads,
            "revolver_availability":       float(request.loan_amount) if request.loan_type == "LOC" else None,
        }
        # Strip None values for a clean file
        lt = {k: v for k, v in lt.items() if v is not None}

        workspace_service.write_file(_LOAN_TERMS_PATH, json.dumps(lt, indent=2))
        logger.info("loan_terms.json written: %s", _LOAN_TERMS_PATH)
    except Exception as exc:
        logger.warning("loan_terms.json write failed (non-blocking): %s", exc)
