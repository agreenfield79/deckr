from pydantic import BaseModel


class BorrowerProfile(BaseModel):
    business_name: str = ""
    entity_type: str = ""
    industry: str = ""
    years_in_business: int = 0
    address: str = ""
    ownership_structure: list[dict] = []
    management_bios: list[dict] = []
    existing_banking_relationship: str = ""
    website: str = ""
