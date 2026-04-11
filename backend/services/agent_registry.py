import logging

from fastapi import HTTPException

logger = logging.getLogger("deckr.agent_registry")

AGENTS: dict[str, dict] = {
    "packaging": {
        "display_name":    "Packaging Agent",
        "system_prompt":   "prompts/packaging_agent.txt",
        "context_folders": ["all"],
        "output_path":     "Deck/deck.md",
        "model":           "llama-70b",
        "mode":            "generate",
        "conversational":  True,
    },
    "financial": {
        "display_name":    "Financial Analysis Agent",
        "system_prompt":   "prompts/financial_agent.txt",
        "context_folders": ["Financials/", "Tax Returns/", "Financials/bank_statements/"],
        "output_path":     "Agent Notes/financial_analysis.md",
        "model":           "granite",
        "mode":            "generate",
        "conversational":  True,
        "action_map": {
            "business_overview":   "Agent Notes/business_overview.md",
            "financial_summary":   "Agent Notes/financial_summary.md",
            "leverage_analysis":   "Agent Notes/leverage_analysis.md",
            "liquidity_analysis":  "Agent Notes/liquidity_analysis.md",
            "collateral_analysis": "Agent Notes/collateral_analysis.md",
            "guarantor_analysis":  "Agent Notes/guarantor_analysis.md",
        },
    },
    "risk": {
        "display_name":    "SLACR Risk Agent",
        "system_prompt":   "prompts/slacr_agent.txt",
        "context_folders": ["Financials/", "Borrower/", "Loan Request/", "SLACR/"],
        "output_path":     "SLACR/slacr_analysis.md",
        "model":           "granite",
        "mode":            "generate",
        "conversational":  True,
    },
    "coordination": {
        "display_name":    "Coordination Agent",
        "system_prompt":   "prompts/coordination_agent.txt",
        "context_folders": ["all"],
        "output_path":     "Agent Notes/coordination_notes.md",
        "model":           "granite",
        "mode":            "generate",
        "conversational":  False,  # stub — auto-invoked only
    },
    "review": {
        "display_name":    "Review Agent",
        "system_prompt":   "prompts/review_agent.txt",
        "context_folders": ["Deck/", "Agent Notes/"],
        "output_path":     "Agent Notes/review_notes.md",
        "model":           "llama-70b",
        "mode":            "generate",
        "conversational":  False,  # stub
    },
}


def get_agent(name: str) -> dict:
    agent = AGENTS.get(name)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: '{name}'")
    return agent


def list_agents() -> list[dict]:
    return [
        {
            "name": name,
            "display_name": cfg["display_name"],
            "mode": cfg["mode"],
            "conversational": cfg["conversational"],
        }
        for name, cfg in AGENTS.items()
    ]
