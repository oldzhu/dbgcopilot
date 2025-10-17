"""Agent orchestrator scaffolding (POC).

Wires an LLM (via LangChain in future iterations) to tools that run debugger commands
and manage session state. Currently a minimal placeholder.
"""
from __future__ import annotations

from typing import Optional


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
        # TODO: integrate prompt templates & LLM
        return (
            "[copilot] (placeholder) I would likely start with 'bt' to inspect the stack.\n"
            "Would you like me to execute 'bt'? (y/N)"
        )

    def summary(self) -> str:
        """Return a simple summary placeholder."""
        # TODO: summarize from state/transcript
        return "[copilot] Session summary (placeholder)."
