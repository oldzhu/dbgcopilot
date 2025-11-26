"""Command-line interface for dbgagent."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
import textwrap

from dbgcopilot.llm import providers as provider_registry
from dbgcopilot.utils.tools import warn_missing_debugger_tools

from .runner import AgentRequest, DebugAgentRunner


SUPPORTED_DEBUGGERS = [
    "gdb",
    "rust-gdb",
    "lldb",
    "rust-lldb",
    "lldb-rust",
    "jdb",
    "pdb",
    "delve",
    "radare2",
]


def _default_path(prefix: str, suffix: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Path("/tmp") / f"{prefix}-{ts}{suffix}"


def build_parser() -> argparse.ArgumentParser:
    provider_choices = provider_registry.list_providers()
    default_provider = "openrouter"
    if provider_choices:
        if default_provider not in provider_choices:
            default_provider = provider_choices[0]
    else:
        provider_choices = []

    provider_hint = ", ".join(provider_choices) if provider_choices else "openrouter"

    parser = argparse.ArgumentParser(
        prog="dbgagent",
        description="Autonomous debugging agent for GDB and LLDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Example:
              dbgagent --debugger gdb --program ./a.out --goal crash --llm-provider deepseek \
                       --llm-key $DEEPSEEK_API_KEY --log-session

            To continue from a hand-edited report, pass --resume-from path/to/report.md.
            """
        ),
    )
    parser.add_argument(
        "--debugger",
        choices=SUPPORTED_DEBUGGERS,
        default="gdb",
        help="Debugger backend to use",
    )
    parser.add_argument("--program", help="Path to the binary under test", default=None)
    parser.add_argument("--core", dest="corefile", help="Path to a core dump", default=None)
    parser.add_argument(
        "--goal", choices=["crash", "hang", "leak", "custom"], default="crash", help="Primary investigation goal"
    )
    parser.add_argument("--goal-text", default="", help="Free-form goal description or question")
    provider_help = f"LLM provider to use (available: {provider_hint})"
    if provider_choices:
        parser.add_argument(
            "--llm-provider",
            choices=provider_choices,
            default=default_provider,
            help=provider_help,
        )
    else:
        parser.add_argument("--llm-provider", default=default_provider, help=provider_help)
    parser.add_argument("--llm-model", default=None, help="Override model for the selected provider")
    parser.add_argument("--llm-key", default=None, help="API key for the selected provider (optional)")
    parser.add_argument(
        "--classpath",
        default=None,
        help="Classpath for jdb (directory of classes or a JAR file)",
    )
    parser.add_argument(
        "--sourcepath",
        default=None,
        help="Optional source path for jdb (directory containing .java files)",
    )
    parser.add_argument(
        "--main-class",
        default=None,
        help="Main class for jdb (fully qualified, e.g. com.example.Main)",
    )
    parser.add_argument("--max-steps", type=int, default=16, help="Maximum auto iterations")
    parser.add_argument(
        "--language",
        default="en",
        help="Preferred language for plan/log/report (e.g., en, zh).",
    )
    parser.add_argument(
        "--log-session",
        action="store_true",
        help="Enable plaintext session logging (default path in /tmp)",
    )
    parser.add_argument("--log-file", default=None, help="Explicit log file path (implies --log-session)")
    parser.add_argument("--report-file", default=None, help="Where to write the final report (defaults to /tmp)")
    parser.add_argument("--resume-from", default=None, help="Existing report/notes to inject as additional context")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    warn_missing_debugger_tools("dbgagent")

    debugger = args.debugger

    if debugger == "jdb":
        if args.program:
            parser.error("--program is not supported with jdb; use --classpath/--main-class instead")
        if not args.classpath:
            parser.error("jdb debugger requires --classpath pointing to the compiled classes or jar")
        if not args.main_class:
            parser.error("jdb debugger requires --main-class (fully qualified entry point)")
    else:
        if debugger in {"delve", "radare2", "pdb", "rust-lldb", "lldb-rust"} and not args.program:
            parser.error(f"{debugger} debugger requires --program")

    log_enabled = bool(args.log_session or args.log_file or os.getenv("DBGAGENT_LOG"))
    report_path = Path(args.report_file) if args.report_file else _default_path("dbgagent-report", ".md")
    log_path: Path | None
    if log_enabled:
        log_path = Path(args.log_file) if args.log_file else _default_path("dbgagent", ".log")
    else:
        log_path = None

    resume_text = None
    if args.resume_from:
        resume_path = Path(args.resume_from)
        if not resume_path.is_file():
            parser.error(f"Resume file not found: {resume_path}")
        resume_text = resume_path.read_text(encoding="utf-8")

    request = AgentRequest(
        debugger=debugger,
        provider=args.llm_provider,
        model=args.llm_model,
        api_key=args.llm_key,
        program=None if debugger == "jdb" else args.program,
        classpath=args.classpath if debugger == "jdb" else None,
        sourcepath=args.sourcepath if debugger == "jdb" else None,
        main_class=args.main_class if debugger == "jdb" else None,
        corefile=args.corefile,
        goal_type=args.goal,
        goal_text=args.goal_text,
        resume_context=resume_text,
        max_steps=args.max_steps,
        language=args.language,
        log_enabled=log_enabled,
        log_path=log_path,
        report_path=report_path,
    )

    runner = DebugAgentRunner(request)
    try:
        final_report = runner.run()
    except Exception as exc:  # pragma: no cover - best effort CLI safeguard
        print(f"[dbgagent] Error: {exc}", file=sys.stderr)
        print("", file=sys.stderr)
        parser.print_help(sys.stderr)
        return 1

    print(f"[dbgagent] Session complete. Report saved to {report_path}")
    if log_enabled and log_path is not None:
        print(f"[dbgagent] Session log stored at {log_path}")
    if final_report.strip().startswith("Final Report"):
        print("[dbgagent] Investigation ended without a detailed report. Inspect the log for next steps.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
