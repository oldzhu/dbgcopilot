"""Agent orchestrator scaffolding (POC).

Wires an LLM (via LangChain in future iterations) to tools that run debugger commands
and manage session state. Currently a minimal placeholder.
"""
from __future__ import annotations

from typing import Optional
from dbgcopilot.llm import providers


class AgentOrchestrator:
    """Placeholder orchestrator.

    In future iterations, this will:
    - Initialize LLM and prompt templates
    - Provide methods for suggest/ask/plan/auto/report
    - Use a Backend to run commands safely
    """

    def __init__(self, backend, state):
        self.backend = backend
        self.state = state

    def ask(self, question: str) -> str:
        """Placeholder ask handler; returns a canned response for now."""
        # Use selected provider from state if available
        pname = getattr(self.state, "selected_provider", None) or self.state.config.get("llm_provider")
        if pname:
            prov = providers.get_provider(pname)
            if prov:
                try:
                    return prov.ask(question)
                except Exception as e:
                    return f"[copilot] LLM provider error: {e}"

        # fallback placeholder
        return (
            "[copilot] (placeholder) I would likely start with 'bt' to inspect the stack.\n"
            "Would you like me to execute 'bt'? (y/N)"
        )

    def summary(self) -> str:
        """Return a simple summary placeholder."""
        # TODO: summarize from state/transcript
        return "[copilot] Session summary (placeholder)."
