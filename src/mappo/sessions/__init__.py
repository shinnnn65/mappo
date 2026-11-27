"""Read-only cross-agent session discovery and context handoff."""

from mappo.sessions.handoff import (
    SESSION_AGENTS,
    build_handoff,
    list_sessions,
    render_handoff_markdown,
    resolve_session,
)
from mappo.sessions.refs import ParsedRef, parse_session_ref

__all__ = [
    "ParsedRef",
    "SESSION_AGENTS",
    "build_handoff",
    "list_sessions",
    "parse_session_ref",
    "render_handoff_markdown",
    "resolve_session",
]
