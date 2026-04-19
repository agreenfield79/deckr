from pydantic import BaseModel


class LoanRequest(BaseModel):
    loan_amount: float = 0.0
    loan_type: str = ""
    loan_purpose: str = ""
    repayment_source: str = ""
    interest_rate: float = 0.0          # annual rate as a percentage, e.g. 6.75 = 6.75%
    term_months: int = 0
    amortization_months: int = 0
    collateral_offered: list[str] = []
    guarantors: list[dict] = []
    desired_timing: str = ""
