"""Known macOS Coding Agent, editor, and extension signatures."""

import json
import os
import plistlib
import re
from pathlib import Path

SUPPORT = Path("Library/Application Support")
EDITORS = {
    "cursor": "Cursor",
    "codebuddy": "CodeBuddy CN",
    "trae": "Trae",
    "vscode": "Code",
}
MAC_APP_VARIANTS = {
    "antigravity": (("Antigravity", None), ("Antigravity IDE", None)),
    "codex": (("Codex", None), ("ChatGPT", "com.openai.codex")),
    "trae": (("Trae", None), ("Trae CN", None)),
}
CLI_ALIASES = {
    "antigravity": ("agy", "antigravity", "antigravity-ide"),
    "vscode": ("code",),
    "trae": ("trae", "trae-cn"),
}
EXTRA_DATA_LOCATIONS = {
    "antigravity": (
        ".gemini/antigravity-ide",
        ".gemini/antigravity-cli",
        ".gemini/config/projects",
        str(SUPPORT / "Antigravity IDE"),
    ),
    "claude": (".claude.json",),
}
CUSTOM_TOOLS_REL_PATH = Path(".config/mappo/custom_tools.json")
_VALID_TOOL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def read_mac_bundle_id(app_path):
    """Read CFBundleIdentifier from a macOS .app bundle Info.plist if present."""
    plist_path = Path(app_path) / "Contents" / "Info.plist"
    try:
        with plist_path.open("rb") as fh:
            data = plistlib.load(fh)
        if isinstance(data, dict):
            return data.get("CFBundleIdentifier")
    except (OSError, plistlib.InvalidFileException, ValueError):
        return None
    return None


EDITOR_EXTENSION_DIRS = {
    "vscode": ".vscode",
    "cursor": ".cursor",
    "codebuddy": ".codebuddycn",
    "trae": ".trae",
}
EXTENSIONS = {
    "copilot": "github.copilot-chat",
    "stagewise": "stagewise.stagewise-vscode-extension",
    "continue": "continue.continue",
    "codegeex": "aminer.codegeex",
    "pencil": "highagency.pencildev",
}
# Signatures supplement CLI discovery (including uninstalled apps with data left behind).
PRODUCTS = {
    "codex": ("Codex", ".codex"),
    "cursor": ("Cursor", ".cursor"),
    "codebuddy": ("CodeBuddy CN", ".codebuddy"),
    "workbuddy": ("WorkBuddy", ".workbuddy"),
    "dsh": ("DeepSeek Harness", ".dsh"),
    "claude": ("Claude", ".claude"),
    "trae": ("Trae", ".trae"),
    "vscode": ("Visual Studio Code", ".vscode"),
    "antigravity": ("Antigravity", ".gemini/antigravity"),
    "openclaw": ("OpenClaw", ".openclaw"),
    "opencode": ("OpenCode", ".config/opencode"),
    "gemini": ("Gemini", ".gemini"),
    "continue": ("Continue", ".continue"),
    "kiro": ("Kiro", ".kiro"),
    "marscode": ("MarsCode", ".marscode"),
    "codegeex": ("CodeGeeX", ".codegeex"),
    "cline": ("Cline", "Documents/Cline"),
    "copilot": ("GitHub Copilot", ""),
    "stagewise": ("Stagewise", ""),
    "pencil": ("Pencil", ".pencil"),
}
LIMITS = {
    "marscode": "本机快照库没有标准 SQLite 文件头，缺少已验证的目录解析方式",
    "kiro": "发现 settings 与 skills，尚未定位本机发现记录",
    "cline": "发现 Rules 与 Workflows，尚未定位任务路径索引",
}


def load_custom_tools(home=None):
    """Load optional user-local tool definitions from ~/.config/mappo/custom_tools.json."""
    env_override = os.environ.get("MAPPO_CUSTOM_TOOLS", "").strip()
    if env_override:
        config_path = Path(env_override).expanduser()
    else:
        base_home = Path(home) if home is not None else Path.home()
        config_path = base_home / CUSTOM_TOOLS_REL_PATH
    try:
        if not config_path.is_file():
            return {}, {}, {}
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, {}, {}
    if not isinstance(raw, dict):
        return {}, {}, {}

    extra_products = {}
    extra_extensions = {}
    extra_limits = {}

    raw_exts = raw.get("extensions")
    if isinstance(raw_exts, dict):
        for tool_id, spec in raw_exts.items():
            if (
                not isinstance(tool_id, str)
                or not _VALID_TOOL_ID_RE.match(tool_id)
                or not isinstance(spec, dict)
            ):
                continue
            ext_id = spec.get("extension_id")
            if not isinstance(ext_id, str) or not ext_id.strip():
                continue
            name = spec.get("name")
            display = name.strip() if isinstance(name, str) and name.strip() else tool_id
            data_dir = spec.get("data_dir")
            location = data_dir.strip() if isinstance(data_dir, str) else ""
            extra_extensions[tool_id] = ext_id.strip()
            extra_products[tool_id] = (display, location)

    raw_products = raw.get("products")
    if isinstance(raw_products, dict):
        for tool_id, spec in raw_products.items():
            if (
                not isinstance(tool_id, str)
                or not _VALID_TOOL_ID_RE.match(tool_id)
                or not isinstance(spec, dict)
                or tool_id in extra_extensions
            ):
                continue
            name = spec.get("name")
            display = name.strip() if isinstance(name, str) and name.strip() else tool_id
            data_dir = spec.get("data_dir")
            location = data_dir.strip() if isinstance(data_dir, str) else ""
            extra_products[tool_id] = (display, location)
            limit = spec.get("limit")
            if isinstance(limit, str) and limit.strip():
                extra_limits[tool_id] = limit.strip()

    return extra_products, extra_extensions, extra_limits


def merged_registry(home=None):
    """Return per-scan copies of (products, extensions, limits) including local custom tools."""
    products = dict(PRODUCTS)
    extensions = dict(EXTENSIONS)
    limits = dict(LIMITS)
    extra_products, extra_extensions, extra_limits = load_custom_tools(home=home)
    for tool_id, value in extra_products.items():
        if tool_id not in products:
            products[tool_id] = value
    for tool_id, ext_id in extra_extensions.items():
        if tool_id not in extensions:
            extensions[tool_id] = ext_id
    for tool_id, reason in extra_limits.items():
        if tool_id not in limits:
            limits[tool_id] = reason
    return products, extensions, limits


def tool_category(agent, extensions=None):
    """Classify a registered tool as an editor, extension, or coding_agent."""
    if agent in EDITORS:
        return "editor"
    ext_map = EXTENSIONS if extensions is None else extensions
    if agent in ext_map:
        return "extension"
    return "coding_agent"


def detect_extension_hosts(installed=(), data=(), workspaces=()):
    """Infer host editors for an extension from discovery records, installs, and data dirs."""
    counts = {}
    installed_hosts = set()
    data_hosts = set()
    editor_order = {editor_id: idx for idx, editor_id in enumerate(EDITORS)}
    support_prefix = SUPPORT.as_posix()

    for row in workspaces or ():
        matched = set()
        for raw in row.get("sources") or ():
            norm = str(raw).replace("\\", "/")
            for editor_id, product in EDITORS.items():
                if f"/{support_prefix}/{product}/" in norm:
                    matched.add(editor_id)
        for editor_id in matched:
            counts[editor_id] = counts.get(editor_id, 0) + 1

    for raw in installed or ():
        norm = str(raw).replace("\\", "/")
        for editor_id, ext_dir in EDITOR_EXTENSION_DIRS.items():
            if f"/{ext_dir}/extensions/" in norm:
                installed_hosts.add(editor_id)

    for raw in data or ():
        norm = str(raw).replace("\\", "/")
        for editor_id, product in EDITORS.items():
            if f"/{support_prefix}/{product}/" in norm:
                data_hosts.add(editor_id)

    hosts = set(counts) | installed_hosts | data_hosts
    ordered = sorted(
        hosts,
        key=lambda eid: (
            -counts.get(eid, 0),
            eid not in installed_hosts,
            editor_order.get(eid, 99),
        ),
    )
    return [
        {
            "agent": eid,
            "display_name": PRODUCTS.get(eid, (EDITORS[eid], ""))[0],
            "records": counts.get(eid, 0),
            "installed": eid in installed_hosts,
        }
        for eid in ordered
    ]
