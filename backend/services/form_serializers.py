"""
form_serializers.py — serialize BorrowerProfile / LoanRequest to markdown and back.

Round-trip strategy: the human-readable markdown body is the primary representation
(AI agents read it as context). The original JSON is preserved in a hidden HTML comment
block at the end of the file so the GET endpoint can restore the Pydantic model exactly.

  <!--deckr-data
  {...json...}
  -->

HTML comments are stripped by markdown renderers so users never see the raw JSON.
"""
import json
import re
from datetime import date

from models.borrower import BorrowerProfile
from models.loan import LoanRequest

_DATA_START = "<!--deckr-data"
_DATA_END = "-->"


def _embed_data(content: str, data: dict) -> str:
    return content + f"\n{_DATA_START}\n{json.dumps(data, indent=2)}\n{_DATA_END}\n"


def _extract_data(content: str) -> dict | None:
    match = re.search(
        r"<!--deckr-data\s*(.*?)\s*-->",
        content,
        re.DOTALL,
    )
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# BorrowerProfile
# ---------------------------------------------------------------------------

def serialize_borrower(profile: BorrowerProfile) -> str:
    today = date.today().isoformat()

    ownership_table = ""
    if profile.ownership_structure:
        ownership_table = (
            "| Name | % | Role |\n"
            "|---|---|---|\n"
        )
        for row in profile.ownership_structure:
            ownership_table += f"| {row.get('name','')} | {row.get('percent','')} | {row.get('role','')} |\n"
    else:
        ownership_table = "_No ownership entries provided._\n"

    bio_sections = ""
    for bio in profile.management_bios:
        bio_sections += f"\n### {bio.get('name', 'Unknown')}\n{bio.get('bio', '')}\n"
    if not bio_sections:
        bio_sections = "_No management bios provided._\n"

    body = f"""---
type: borrower_profile
project: default
created: {today}
agent_source: onboarding_form
---

# Borrower Profile

## Business Information

- **Business Name:** {profile.business_name}
- **Entity Type:** {profile.entity_type}
- **Industry:** {profile.industry}
- **Years in Business:** {profile.years_in_business}
- **Address:** {profile.address}
- **Website:** {profile.website}
- **Existing Banking Relationship:** {profile.existing_banking_relationship}

## Ownership Structure

{ownership_table}
## Management Team
{bio_sections}
"""
    return _embed_data(body, profile.model_dump())


def parse_borrower(content: str) -> BorrowerProfile | None:
    data = _extract_data(content)
    if data is None:
        return None
    try:
        return BorrowerProfile(**data)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# LoanRequest
# ---------------------------------------------------------------------------

def serialize_loan(request: LoanRequest) -> str:
    today = date.today().isoformat()

    collateral_list = "\n".join(f"- {item}" for item in request.collateral_offered) or "_None provided._"

    guarantor_table = ""
    if request.guarantors:
        guarantor_table = (
            "| Name | Relationship | Net Worth |\n"
            "|---|---|---|\n"
        )
        for g in request.guarantors:
            guarantor_table += f"| {g.get('name','')} | {g.get('relationship','')} | {g.get('net_worth','')} |\n"
    else:
        guarantor_table = "_No guarantors provided._\n"

    body = f"""---
type: loan_request
project: default
created: {today}
agent_source: loan_form
---

# Loan Request

## Credit Request

- **Loan Amount:** ${request.loan_amount:,.2f}
- **Loan Type:** {request.loan_type}
- **Loan Purpose:** {request.loan_purpose}
- **Repayment Source:** {request.repayment_source}
- **Term Requested:** {request.term_months} months
- **Amortization:** {request.amortization_months} months
- **Desired Timing:** {request.desired_timing}

## Collateral Offered

{collateral_list}

## Guarantors

{guarantor_table}
"""
    return _embed_data(body, request.model_dump())


def parse_loan(content: str) -> LoanRequest | None:
    data = _extract_data(content)
    if data is None:
        return None
    try:
        return LoanRequest(**data)
    except Exception:
        return None
