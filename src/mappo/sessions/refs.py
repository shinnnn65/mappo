"""Parse pasted session references, URIs, and resume commands."""

import re
from dataclasses import dataclass
from typing import Optional

SUPPORTED_SESSION_AGENTS = ("codex", "antigravity", "cursor", "codebuddy")

_AGENT_ALIASES = {
    "codex": "codex",
    "antigravity": "antigravity",
    "agy": "antigravity",
    "conversation": "antigravity",
    "cursor": "cursor",
    "codebuddy": "codebuddy",
    "cb": "codebuddy",
}

_CD_CWD_RE = re.compile(
    r"""\bcd\s+(?:'([^']+)'|"([^"]+)"|([^\s;&|]+))""",
    re.IGNORECASE,
)
_CODEX_URI_RE = re.compile(
    r"""codex://(?:threads|sessions)/([0-9a-fA-F-]{6,64})""",
    re.IGNORECASE,
)
_CODEX_CMD_RE = re.compile(
    r"""\bcodex\s+(?:resume|fork|session)\s+(?:--[a-z0-9-]+\s+)*['"]?([0-9a-fA-F-]{6,64})['"]?""",
    re.IGNORECASE,
)
_AGY_URI_RE = re.compile(
    r"""(?:conversation|antigravity)://(?:conversations/)?([0-9a-fA-F-]{6,64})""",
    re.IGNORECASE,
)
_MAPPO_URI_RE = re.compile(
    r"""mappo://sessions?/([a-z0-9_-]+)/([0-9a-zA-Z_-]{6,64})""",
    re.IGNORECASE,
)
_PREFIXED_REF_RE = re.compile(
    r"""^(codex|antigravity|agy|cursor|codebuddy|cb):([0-9a-zA-Z_-]{6,64})$""",
    re.IGNORECASE,
)
_UUID_RE = re.compile(
    r"""\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b"""
)
_HEX32_RE = re.compile(r"""\b([0-9a-fA-F]{32})\b""")
_SHORT_ID_RE = re.compile(r"""^[0-9a-fA-F-]{6,64}$""")


@dataclass(frozen=True)
class ParsedRef:
    raw: str
    agent: Optional[str]
    session_id: str
    cwd_hint: Optional[str] = None


def _extract_cwd_hint(text):
    match = _CD_CWD_RE.search(text)
    if not match:
        return None
    return next((group for group in match.groups() if group), None)


def parse_session_ref(raw_ref, default_agent=None):
    """Parse a session URI, resume command, prefixed ref, or bare ID."""
    if not isinstance(raw_ref, str) or not raw_ref.strip():
        raise ValueError("请提供会话 ID、URI 或 resume 命令")
    text = raw_ref.strip()
    cwd_hint = _extract_cwd_hint(text)
    norm_default = _AGENT_ALIASES.get(default_agent.lower()) if default_agent else None

    match = _MAPPO_URI_RE.search(text)
    if match:
        agent = _AGENT_ALIASES.get(match.group(1).lower())
        if not agent:
            raise ValueError(f"暂不支持的会话来源：{match.group(1)}")
        return ParsedRef(text, agent, match.group(2), cwd_hint)

    match = _CODEX_URI_RE.search(text)
    if match:
        return ParsedRef(text, "codex", match.group(1), cwd_hint)

    match = _CODEX_CMD_RE.search(text)
    if match:
        return ParsedRef(text, "codex", match.group(1), cwd_hint)

    match = _AGY_URI_RE.search(text)
    if match:
        return ParsedRef(text, "antigravity", match.group(1), cwd_hint)

    match = _PREFIXED_REF_RE.match(text)
    if match:
        agent = _AGENT_ALIASES[match.group(1).lower()]
        return ParsedRef(text, agent, match.group(2), cwd_hint)

    match = _UUID_RE.search(text)
    if match:
        return ParsedRef(text, norm_default, match.group(1), cwd_hint)

    match = _HEX32_RE.search(text)
    if match:
        return ParsedRef(text, norm_default, match.group(1), cwd_hint)

    if _SHORT_ID_RE.match(text):
        return ParsedRef(text, norm_default, text, cwd_hint)

    raise ValueError(
        "无法识别会话引用；支持 codex://threads/<id>、codex resume <id>、"
        "conversation://<id>、<agent>:<id> 或会话 UUID/短 ID"
    )
