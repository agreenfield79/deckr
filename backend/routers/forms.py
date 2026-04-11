import logging

from fastapi import APIRouter, HTTPException

from models.borrower import BorrowerProfile
from models.loan import LoanRequest
from services import form_serializers, workspace_service

logger = logging.getLogger("deckr.routers.forms")

router = APIRouter()

_BORROWER_PATH = "Borrower/profile.md"
_LOAN_PATH = "Loan Request/request.md"


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
