"""Report builder scaffolding (POC)."""
from __future__ import annotations

from pathlib import Path
from .state import SessionState


def build_markdown_report(state: SessionState) -> str:
    """Return a minimal Markdown report string."""
    lines = [
        f"# Debugger Copilot Report — {state.session_id}",
        "",
        "## Context",
        f"- Goal: {state.goal or 'N/A'}",
        "",
        "## Key Findings",
    ]
    if state.facts:
        lines.extend([f"- {f}" for f in state.facts])
    else:
        lines.append("- (none yet)")
    if state.attempts:
        lines += ["", "## Commands Run"]
        for a in state.attempts[-10:]:  # last 10
            lines.append(f"- `{a.cmd}`: {a.output_snippet[:120]}...")
    lines += ["", "## Next Steps", "- (TBD)"]
    return "\n".join(lines)


def write_report_file(state: SessionState, reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    out = reports_dir / f"{state.session_id}.md"
    out.write_text(build_markdown_report(state), encoding="utf-8")
    return out
