import json
import logging
import re
from datetime import date
from pathlib import Path

from services import workspace_service

logger = logging.getLogger("deckr.deck_service")

SECTION_NAMES = [
    "Credit Request Summary",
    "Business Overview",
    "Financial Analysis",
    "Leverage",
    "Liquidity",
    "Collateral",
    "Guarantor",
    "Industry",
    "Risks",
    "Mitigants",
    "SLACR Score",
    "Recommendation",
    "Structure",
]

# Maps each section to its primary source file already in the workspace
_SECTION_SOURCE_MAP: dict[str, str] = {
    "Credit Request Summary": "Loan Request/request.md",
    "Business Overview":      "Agent Notes/business_overview.md",
    "Financial Analysis":     "Agent Notes/financial_analysis.md",
    "Leverage":               "Agent Notes/leverage_analysis.md",
    "Liquidity":              "Agent Notes/liquidity_analysis.md",
    "Collateral":             "Agent Notes/collateral_analysis.md",
    "Guarantor":              "Agent Notes/guarantor_analysis.md",
    "Industry":               "Research/",            # reads first .md file in Research/
    "Risks":                  "SLACR/slacr_analysis.md",
    "Mitigants":              "SLACR/slacr_analysis.md",
    "SLACR Score":            "SLACR/slacr.json",    # handled specially
    "Recommendation":         "Agent Notes/financial_summary.md",
    "Structure":              "Loan Request/request.md",
}

# Maps each section to the agent + action_type used by POST /api/deck/section
SECTION_AGENT_MAP: dict[str, dict] = {
    "Credit Request Summary": {
        "agent": "packaging",  "action_type": None,
        "message": "Generate the Credit Request Summary section of the underwriting memorandum.",
    },
    "Business Overview": {
        "agent": "packaging",  "action_type": "business_overview",
        "message": "",
    },
    "Financial Analysis": {
        "agent": "financial",  "action_type": None,
        "message": "Generate a comprehensive Financial Analysis section covering all key ratios and trends.",
    },
    "Leverage": {
        "agent": "financial",  "action_type": "analyze_leverage",
        "message": "",
    },
    "Liquidity": {
        "agent": "financial",  "action_type": "analyze_liquidity",
        "message": "",
    },
    "Collateral": {
        "agent": "packaging",  "action_type": "analyze_collateral",
        "message": "",
    },
    "Guarantor": {
        "agent": "packaging",  "action_type": "analyze_guarantor",
        "message": "",
    },
    "Industry": {
        "agent": "packaging",  "action_type": None,
        "message": (
            "Generate the Industry & Market Analysis section covering the borrower's industry, "
            "competitive position, market trends, and key industry risks."
        ),
    },
    "Risks": {
        "agent": "risk",  "action_type": None,
        "message": "Identify and categorize all primary credit risks (financial, operational, market, collateral, management).",
    },
    "Mitigants": {
        "agent": "risk",  "action_type": None,
        "message": "Identify and explain the mitigating factors that offset the identified credit risks.",
    },
    "SLACR Score": {
        "agent": "risk",  "action_type": None,
        "message": "Produce the SLACR risk score with per-dimension scores, composite score, rating band, and narrative.",
    },
    "Recommendation": {
        "agent": "packaging",  "action_type": None,
        "message": (
            "Provide the credit committee recommendation: "
            "Approve / Approve with Conditions / Decline, with supporting rationale and conditions."
        ),
    },
    "Structure": {
        "agent": "packaging",  "action_type": None,
        "message": (
            "Propose the loan structure including term, rate, amortization, covenants, "
            "conditions precedent, and reporting requirements."
        ),
    },
}


def load_section_from_agent_notes(section_name: str) -> str | None:
    """Load existing agent-generated content for a deck section. Returns None if not available."""
    root = workspace_service._get_root()
    source = _SECTION_SOURCE_MAP.get(section_name)
    if not source:
        return None

    # Special: SLACR Score — prefer structured JSON, fall back to markdown
    if source == "SLACR/slacr.json":
        json_path = root / "SLACR" / "slacr.json"
        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                logger.debug("deck section '%s': loaded from SLACR/slacr.json", section_name)
                return _format_slacr_json(data)
            except Exception:
                pass
        md_path = root / "SLACR" / "slacr_analysis.md"
        if md_path.exists():
            logger.debug("deck section '%s': loaded from SLACR/slacr_analysis.md", section_name)
            return _strip_frontmatter(md_path.read_text(encoding="utf-8"))
        logger.debug("deck section '%s': using placeholder", section_name)
        return None

    # Special: Industry — reads from Research/ folder
    if source == "Research/":
        research_dir = root / "Research"
        if research_dir.exists():
            md_files = sorted(research_dir.rglob("*.md"))
            if md_files:
                combined = "\n\n".join(
                    _strip_frontmatter(f.read_text(encoding="utf-8")) for f in md_files[:3]
                )
                logger.debug("deck section '%s': loaded from Research/", section_name)
                return combined
        logger.debug("deck section '%s': using placeholder", section_name)
        return None

    # Standard: read file if it exists
    file_path = root / source
    if file_path.exists():
        try:
            content = _strip_frontmatter(file_path.read_text(encoding="utf-8"))
            logger.debug("deck section '%s': loaded from agent notes", section_name)
            return content
        except (OSError, UnicodeDecodeError):
            pass

    logger.debug("deck section '%s': using placeholder", section_name)
    return None


def assemble_deck(sections: dict[str, str]) -> str:
    """Build the full deck markdown document from section name → content pairs."""
    borrower_name = _get_borrower_name()
    today = date.today().isoformat()

    lines: list[str] = [
        "---",
        "type: deck",
        f"borrower: {borrower_name}",
        f"created: {today}",
        "---",
        "",
        f"# {borrower_name} — Credit Memorandum",
        f"*Generated: {today}*",
        "",
    ]

    for i, name in enumerate(SECTION_NAMES, start=1):
        lines.append("---")
        lines.append("")
        lines.append(f"## {i}. {name}")
        lines.append("")
        content = sections.get(name)
        if content:
            lines.append(content.strip())
        else:
            agent = SECTION_AGENT_MAP[name]["agent"].title()
            lines.append(
                f'> **PENDING** — {agent} analysis not yet generated. '
                f'Use "Regenerate Section" to produce this content.'
            )
        lines.append("")

    document = "\n".join(lines)
    logger.info("memo assembled: %d/%d sections → Deck/memo.md", len(sections), len(SECTION_NAMES))
    return document


def load_deck() -> str | None:
    """Read Deck/memo.md if it exists; fall back to Deck/deck.md for in-progress deals."""
    root = workspace_service._get_root()
    memo_path = root / "Deck" / "memo.md"
    if memo_path.exists():
        try:
            return memo_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            pass
    # Fallback: legacy path used before Phase 25 rename — prevents data loss for
    # deals that completed the packaging pipeline before the rename was deployed.
    deck_path = root / "Deck" / "deck.md"
    if deck_path.exists():
        try:
            logger.info("load_deck: Deck/memo.md not found; falling back to Deck/deck.md")
            return deck_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            pass
    return None


def save_deck(content: str) -> None:
    """Write content to Deck/memo.md."""
    workspace_service.write_file("Deck/memo.md", content)


def update_section_in_deck(section_name: str, new_content: str) -> str:
    """Replace a single section's content in the existing deck, returning the updated document."""
    existing = load_deck()
    if not existing:
        return assemble_deck({section_name: new_content})

    section_idx = SECTION_NAMES.index(section_name) + 1 if section_name in SECTION_NAMES else None
    if section_idx is None:
        return existing

    cleaned = _strip_frontmatter(new_content).strip()
    heading_escaped = re.escape(f"## {section_idx}. {section_name}")

    # Match the heading through content up to the next section divider or EOF
    pattern = re.compile(
        rf"({heading_escaped}\n\n)(.*?)(?=\n\n---|\Z)",
        re.DOTALL,
    )
    replacement = f"## {section_idx}. {section_name}\n\n{cleaned}"
    updated, count = pattern.subn(replacement, existing)

    if count == 0:
        logger.warning("deck: could not locate section '%s' in memo.md for in-place update", section_name)
        return existing

    return updated


def _get_borrower_name() -> str:
    root = workspace_service._get_root()
    profile_path = root / "Borrower" / "profile.md"
    if profile_path.exists():
        try:
            content = profile_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                if line.startswith("business_name:"):
                    return line.split(":", 1)[1].strip().strip('"').strip("'")
                if line.startswith("# "):
                    return line[2:].strip()
        except (OSError, UnicodeDecodeError):
            pass
    return "Borrower"


def _strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter block from agent output before embedding in deck."""
    content = content.strip()
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return content


def _format_slacr_json(data: dict) -> str:
    """Format a SLACR JSON object as a readable markdown section."""
    composite = data.get("composite_score", "N/A")
    rating = data.get("rating_band", "N/A")
    dimensions = data.get("dimensions", [])

    lines = [
        f"**Composite SLACR Score: {composite}**",
        f"**Rating Band: {rating}**",
        "",
        "| Dimension | Weight | Score | Rationale |",
        "|---|---|---|---|",
    ]
    for dim in dimensions:
        lines.append(
            f"| {dim.get('name', '')} "
            f"| {dim.get('weight', '')} "
            f"| {dim.get('score', '')} "
            f"| {dim.get('rationale', '')} |"
        )

    narrative = data.get("narrative", "")
    if narrative:
        lines.extend(["", narrative])

    return "\n".join(lines)
