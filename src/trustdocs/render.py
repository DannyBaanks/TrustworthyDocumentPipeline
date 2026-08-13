"""Human-readable rendering of a pipeline outcome for the terminal.

ANSI escape codes only -- no new dependency. Never prints extracted field
values or document content, only metadata and hashes, matching the safety
property the CLI already documents for its JSON output.
"""
from __future__ import annotations

import sys

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"

_STATUS_STYLE = {
    "AUTO_APPROVED": (GREEN, "✓"),
    "APPROVED_BY_HUMAN": (GREEN, "✓"),
    "REJECTED": (RED, "✗"),
}
_VALIDATION_STYLE = {
    "PASS": (GREEN, "✓"),
    "WARNING": (YELLOW, "⚠"),
    "FAIL": (RED, "✗"),
}


def supports_color(stream=None) -> bool:
    stream = stream or sys.stdout
    return hasattr(stream, "isatty") and stream.isatty()


def _style(color: str, icon: str, text: str, *, color_enabled: bool) -> str:
    if not color_enabled:
        return f"{icon} {text}"
    return f"{color}{icon} {text}{RESET}"


def render_pretty(outcome: dict, *, color_enabled: bool | None = None) -> str:
    """Render a summary block from the same outcome dict the CLI's --json
    output uses. Never renders extracted field values -- only status,
    hashes, and validation rule metadata."""
    if color_enabled is None:
        color_enabled = supports_color()

    bold = BOLD if color_enabled else ""
    dim = DIM if color_enabled else ""
    reset = RESET if color_enabled else ""

    status = outcome["status"]
    color, icon = _STATUS_STYLE.get(status, (RESET, "?"))

    lines = [
        f"{bold}Trustworthy Document Pipeline{reset}",
        "-" * 34,
        f"  Status:       {_style(color, icon, status, color_enabled=color_enabled)}",
        f"  Document:     {dim}sha256:{outcome['document_sha256'][:16]}...{reset}",
        f"  Fields:       {outcome['field_count']} extracted",
        f"  Reviewed:     {'yes (human)' if outcome['reviewed'] else 'no (auto)'}",
    ]

    validation = outcome.get("validation") or []
    if validation:
        lines.append("  Validation:")
        for finding in validation:
            vcolor, vicon = _VALIDATION_STYLE.get(finding["status"], (RESET, "?"))
            styled = _style(vcolor, vicon, finding["rule_id"], color_enabled=color_enabled)
            lines.append(f"    {styled} -- {finding['message']}")

    lines.append(f"  Evidence:     {dim}sha256:{outcome['evidence_sha256'][:16]}...{reset}")
    lines.append(f"  Execution ID: {outcome['execution_id']}")
    if outcome.get("evidence_path"):
        lines.append(f"  Saved to:     {outcome['evidence_path']}")
    lines.append("-" * 34)
    return "\n".join(lines)
