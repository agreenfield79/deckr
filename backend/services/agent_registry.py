import logging

from fastapi import HTTPException

logger = logging.getLogger("deckr.agent_registry")

AGENTS: dict[str, dict] = {
    "industry": {
        "display_name":    "Industry Analysis Agent",
        "system_prompt":   "prompts/industry_agent.txt",
        # NAICS/business description lives in Borrower/ and Loan Request/;
        # Agent Notes/ provides prior agent outputs as supporting context.
        # context_folders drives the 10k-char Orchestrate context block in run().
        # The agent uses search_workspace + search_web tools for live research.
        "context_folders": ["Borrower/", "Loan Request/", "Agent Notes/"],
        "output_path":     "Agent Notes/industry_analysis.md",
        "model":           "granite",
        "mode":            "generate",
        "conversational":  False,
        # Agent calls save_to_workspace via Orchestrate (saves full industry_analysis.md),
        # then returns a brief 2-3 sentence confirmation as reply.
        # orchestrate_tool_save=True suppresses backend auto-save so the brief
        # confirmation does not overwrite the full content the tool already wrote.
        "orchestrate_tool_save": True,
    },
    "extraction": {
        "display_name":    "Financial Data Extraction Agent",
        "system_prompt":   "prompts/extraction_agent.txt",
        # Empty: context is pre-loaded by run_extraction() via _build_extraction_context(),
        # which reads sidecar files directly from COS.  _load_context() is not called
        # for this agent — the pipeline branches to run_extraction() instead of run().
        "context_folders": [],
        "output_path":     "Financials/extracted_data.json",
        "model":           "granite",
        "mode":            "generate",
        "conversational":  False,
        # orchestrate_tool_save removed: run_extraction() saves both output files
        # directly after parsing the Orchestrate response.  No save_to_workspace
        # tool call is made or expected.
    },
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
        # Agent is instructed to save its output via the save_to_workspace tool in Orchestrate.
        # Suppresses the backend auto-save in the Orchestrate path to prevent the tool-saved
        # full analysis from being overwritten by the agent's brief confirmation reply.
        "orchestrate_tool_save": True,
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
        # NOTE: The original gap-checker role for this agent is superseded by
        # status_service.py + StatusTab (deterministic, no AI needed).
        # This entry is reserved for the future Lender RFP Coordination Agent —
        # a multi-party agent that distributes deal packages, tracks lender
        # responses, and compares competing term sheets during syndication.
        # NOT deployed in Orchestrate. Requires Phase 13 tool calling + external
        # communication tools before it can be activated.
        "display_name":    "Coordination Agent",
        "system_prompt":   "prompts/coordination_agent.txt",
        "context_folders": ["all"],
        "output_path":     "Agent Notes/coordination_notes.md",
        "model":           "granite",
        "mode":            "generate",
        "conversational":  False,  # future phase — disabled in UI
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
