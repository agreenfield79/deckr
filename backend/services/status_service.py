import logging
from pathlib import Path

from services import workspace_service

logger = logging.getLogger("deckr.status_service")

_CHECKLIST = [
    {
        "label":  "Borrower Info",
        "path":   "Borrower/profile.md",
        "type":   "file_nonempty",
        "tab":    "onboarding",
        "action": "Complete Onboarding",
    },
    {
        "label":  "Loan Request",
        "path":   "Loan Request/request.md",
        "type":   "file_exists",
        "tab":    "loan",
        "action": "Fill Loan Request",
    },
    {
        "label":  "Financials",
        "path":   "Financials/",
        "type":   "folder_has_files",
        "tab":    "documents",
        "action": "Upload Financials",
    },
    {
        "label":  "Tax Returns",
        "path":   "Tax Returns/",
        "type":   "folder_has_files",
        "tab":    "documents",
        "action": "Upload Tax Returns",
    },
    {
        "label":  "Collateral Docs",
        "path":   "Collateral/",
        "type":   "folder_has_files",
        "tab":    "documents",
        "action": "Upload Collateral Docs",
    },
    {
        "label":  "Guarantor Docs",
        "path":   "Guarantors/",
        "type":   "folder_has_files",
        "tab":    "documents",
        "action": "Upload Guarantor Docs",
    },
    {
        "label":    "Industry Research",
        "path":     "Research/",
        "type":     "folder_has_files_alt",
        "alt_path": "Industry/",
        "tab":      "research",
        "action":   "Add Research Notes",
    },
    {
        "label":  "Agent Analysis",
        "path":   "Agent Notes/",
        "type":   "folder_has_files",
        "tab":    None,
        "action": "Run an Agent →",
    },
    {
        "label":  "SLACR Scored",
        "path":   "SLACR/slacr.json",
        "type":   "file_exists",
        "tab":    None,
        "action": "Run Risk Agent →",
    },
    {
        "label":  "Deck Generated",
        "path":   "Deck/deck.md",
        "type":   "file_exists",
        "tab":    "deck",
        "action": "Generate Deck",
    },
]


def _is_complete(item: dict, root: Path) -> bool:
    path = root / item["path"].rstrip("/")
    match item["type"]:
        case "file_nonempty":
            return path.exists() and path.stat().st_size > 0
        case "file_exists":
            return path.exists()
        case "folder_has_files":
            if not path.exists() or not path.is_dir():
                return False
            return any(f.is_file() for f in path.iterdir())
        case "folder_has_files_alt":
            if path.exists() and path.is_dir() and any(f.is_file() for f in path.iterdir()):
                return True
            alt = root / item.get("alt_path", "").rstrip("/")
            return alt.exists() and alt.is_dir() and any(f.is_file() for f in alt.iterdir())
        case _:
            return False


def get_status() -> dict:
    root = workspace_service._get_root()
    result_items: list[dict] = []
    complete_count = 0

    for item in _CHECKLIST:
        complete = _is_complete(item, root)
        if complete:
            complete_count += 1
        result_items.append({
            "label":    item["label"],
            "complete": complete,
            "path":     item["path"],
            "tab":      item.get("tab"),
            "action":   item.get("action"),
        })

    total = len(_CHECKLIST)
    percentage = round(complete_count / total * 100) if total > 0 else 0
    logger.debug(
        "status: %d/%d items complete (%d%%)", complete_count, total, percentage
    )

    return {"items": result_items, "percentage": percentage}
