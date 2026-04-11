from pydantic import BaseModel, Field


class SlacrInput(BaseModel):
    strength: int = Field(ge=1, le=5, description="Sponsor/Management Quality: 1=excellent, 5=high risk")
    leverage: int = Field(ge=1, le=5, description="Leverage & Capitalization: 1=excellent, 5=high risk")
    ability_to_repay: int = Field(ge=1, le=5, description="Cash Flow / Repayment Capacity: 1=excellent, 5=high risk")
    collateral: int = Field(ge=1, le=5, description="Asset Quality / Collateral: 1=excellent, 5=high risk")
    risk_factors: int = Field(ge=1, le=5, description="Industry & Market Risk: 1=excellent, 5=high risk")
    notes: dict[str, str] = Field(default_factory=dict)


class SlacrOutput(BaseModel):
    weighted_score: float
    rating: str
    decision: str
    mitigants: list[str]
    ai_narrative: str
    input: SlacrInput
