import logging
import re

from fastapi import APIRouter
from pydantic import BaseModel

from services import agent_service, workspace_service

logger = logging.getLogger("deckr.routers.deckr")

router = APIRouter()

DECKR_PATH = "Deck/deckr.md"

_GENERATE_PROMPT = (
    "Run Deckr Agent — read Deck/memo.md and Agent Notes/financial_analysis.md, "
    "then produce a concise borrower-facing deal sheet with advocacy framing "
    "(lead with strengths; convert risk+mitigant pairs into stand-alone affirmative attributes; "
    "cite actual figures from the memo). "
    "Output sections using ## N. Section Name format. "
    "Save the complete deal sheet to Deck/deckr.md via the save_to_workspace tool."
)


class GenerateRequest(BaseModel):
    session_id: str = "default"


class SectionRequest(BaseModel):
    section: str
    regenerate: bool = True
    session_id: str


class SaveRequest(BaseModel):
    content: str


def _update_section(section_name: str, new_content: str, full_text: str) -> str:
    """Replace a single ## N. Section Name block in deckr.md with new_content."""
    heading_escaped = re.escape(section_name)
    pattern = re.compile(
        rf"(## \d+\. {heading_escaped}\n\n)([\s\S]*?)(?=\n\n---|\n## \d+\.|$)"
    )
    return pattern.sub(lambda m: m.group(1) + new_content.strip(), full_text)


@router.get("")
def get_deckr():
    """Read and return the current Deck/deckr.md content."""
    try:
        content = workspace_service.read_file(DECKR_PATH)
        return {"content": content, "exists": True}
    except Exception:
        return {"content": None, "exists": False}


@router.post("/save")
def save_deckr(body: SaveRequest):
    """Persist raw deckr.md content (used after inline section edits in ProposalTab)."""
    workspace_service.write_file(DECKR_PATH, body.content)
    logger.info("deckr/save: %s updated (%d bytes)", DECKR_PATH, len(body.content))
    return {"saved": True, "path": DECKR_PATH}


@router.post("/generate")
def generate_deckr(body: GenerateRequest):
    """Run the deckr agent to produce Deck/deckr.md from memo.md."""
    logger.info("deckr/generate: running deckr agent (session=%s)", body.session_id)
    agent_service.run(
        agent_name="deckr",
        message=_GENERATE_PROMPT,
        session_id=body.session_id,
        messages=[],
        save_to_workspace=True,
        save_path=DECKR_PATH,
    )
    logger.info("deckr/generate: complete → %s", DECKR_PATH)
    return {"generated": True, "path": DECKR_PATH, "source": "deckr_agent"}


@router.post("/section")
def regenerate_deckr_section(body: SectionRequest):
    """Regenerate a single section of deckr.md using the deckr agent."""
    logger.info(
        "deckr/section: regenerating '%s' (session=%s)", body.section, body.session_id
    )
    prompt = (
        f"Read Deck/memo.md to get the source data. "
        f"Then regenerate ONLY the '{body.section}' section of the borrower-facing deal sheet "
        f"using advocacy framing (lead with strengths, convert risk+mitigant pairs into "
        f"affirmative attributes, cite actual figures). "
        f"Output ONLY the section content — no heading, no other sections, no preamble."
    )
    result = agent_service.run(
        agent_name="deckr",
        message=prompt,
        session_id=body.session_id,
        messages=[],
        save_to_workspace=False,
        save_path=None,
    )
    new_content = result["reply"]

    try:
        current = workspace_service.read_file(DECKR_PATH)
        updated = _update_section(body.section, new_content, current)
        workspace_service.write_file(DECKR_PATH, updated)
        logger.info("deckr/section: '%s' regenerated and saved to %s", body.section, DECKR_PATH)
    except Exception as exc:
        logger.warning("deckr/section: could not update %s — %s", DECKR_PATH, exc)

    return {"section": body.section, "content": new_content, "saved": True}
