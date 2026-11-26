"""Read-only workspace providers for Coding Agents, editors, extensions, and local folders."""

from mappo.providers.antigravity import agy
from mappo.providers.claude import claude
from mappo.providers.codebuddy import codebuddy_history
from mappo.providers.codex import codex
from mappo.providers.dsh import dsh
from mappo.providers.editors import editor
from mappo.providers.filesystem import filesystem
from mappo.providers.other import other
from mappo.providers.registry import (
    CLI_ALIASES,
    EDITOR_EXTENSION_DIRS,
    EDITORS,
    EXTENSIONS,
    EXTRA_DATA_LOCATIONS,
    LIMITS,
    MAC_APP_VARIANTS,
    PRODUCTS,
    SUPPORT,
    detect_extension_hosts,
    load_custom_tools,
    merged_registry,
    read_mac_bundle_id,
    tool_category,
)
from mappo.providers.workbuddy import workbuddy

__all__ = [
    "CLI_ALIASES",
    "EDITOR_EXTENSION_DIRS",
    "EDITORS",
    "EXTENSIONS",
    "EXTRA_DATA_LOCATIONS",
    "LIMITS",
    "MAC_APP_VARIANTS",
    "PRODUCTS",
    "SUPPORT",
    "agy",
    "claude",
    "codebuddy_history",
    "codex",
    "detect_extension_hosts",
    "dsh",
    "editor",
    "filesystem",
    "load_custom_tools",
    "merged_registry",
    "other",
    "read_mac_bundle_id",
    "tool_category",
    "workbuddy",
]
