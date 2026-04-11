import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import agent_service, deck_service

logger = logging.getLogger("deckr.routers.deck")

router = APIRouter()


class GenerateRequest(BaseModel):
    session_id: str = "default"


class SectionRequest(BaseModel):
    section: str
    regenerate: bool = True
    session_id: str


class SaveRequest(BaseModel):
    content: str


@router.post("/generate")
def generate_deck(body: GenerateRequest):
    """Assemble deck from existing agent notes; fills gaps with PENDING placeholders."""
    sections: dict[str, str] = {}

    for section_name in deck_service.SECTION_NAMES:
        content = deck_service.load_section_from_agent_notes(section_name)
        if content:
            sections[section_name] = content

    sections_loaded = len(sections)
    logger.info("deck/generate: %d/%d sections loaded from agent notes", sections_loaded, len(deck_service.SECTION_NAMES))

    # If fewer than 3 sections have content, run the packaging agent's full_package prompt
    if sections_loaded < 3:
        logger.info("deck/generate: sparse content — running Packaging Agent full_package prompt")
        result = agent_service.run(
            agent_name="packaging",
            message="Generate a complete Credit Memorandum for this borrower.",
            session_id=body.session_id,
            messages=[],
            save_to_workspace=True,
            save_path="Deck/deck.md",
            action_type="full_package",
        )
        logger.info("deck/generate: full_package complete → Deck/deck.md")
        return {
            "generated": True,
            "path": "Deck/deck.md",
            "source": "full_package",
            "sections_loaded": sections_loaded,
        }

    # Enough existing content — assemble from agent notes
    content = deck_service.assemble_deck(sections)
    deck_service.save_deck(content)
    return {
        "generated": True,
        "path": "Deck/deck.md",
        "source": "agent_notes",
        "sections_loaded": sections_loaded,
    }


@router.get("")
def get_deck():
    """Read and return the current deck content."""
    content = deck_service.load_deck()
    if content is None:
        return {"content": None, "exists": False}
    return {"content": content, "exists": True}


@router.post("/save")
def save_deck(body: SaveRequest):
    """Persist raw deck content (used after inline section edits)."""
    deck_service.save_deck(body.content)
    logger.info("deck/save: Deck/deck.md updated (%d bytes)", len(body.content))
    return {"saved": True, "path": "Deck/deck.md"}


@router.post("/section")
def regenerate_section(body: SectionRequest):
    """Regenerate a single deck section using the appropriate agent and update deck.md."""
    if body.section not in deck_service.SECTION_NAMES:
        raise HTTPException(status_code=400, detail=f"Unknown section: '{body.section}'")

    logger.info("deck/section: regenerating '%s' (session=%s)", body.section, body.session_id)

    routing = deck_service.SECTION_AGENT_MAP[body.section]
    result = agent_service.run(
        agent_name=routing["agent"],
        message=routing["message"],
        session_id=body.session_id,
        messages=[],
        save_to_workspace=False,
        save_path=None,
        action_type=routing["action_type"],
    )

    new_content = result["reply"]

    # Update the section in the existing deck document
    updated_deck = deck_service.update_section_in_deck(body.section, new_content)
    deck_service.save_deck(updated_deck)

    logger.info("deck/section: '%s' regenerated and saved to Deck/deck.md", body.section)
    return {"section": body.section, "content": new_content, "saved": True}
