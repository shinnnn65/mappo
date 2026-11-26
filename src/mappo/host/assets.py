"""Static asset loader supporting source checkouts (apps/web) and mappo.pyz zipapps."""

import pkgutil
from pathlib import Path

_REPO_WEB_DIR = Path(__file__).resolve().parents[3] / "apps" / "web"


def load_asset(name: str) -> bytes:
    rel = Path(name)
    if rel.is_absolute() or ".." in rel.parts:
        raise FileNotFoundError(f"非法前端资源路径：{name}")
    try:
        data = pkgutil.get_data("mappo._web_assets", name)
    except (ModuleNotFoundError, ImportError, ValueError):
        data = None
    if data is not None:
        return data
    path = (_REPO_WEB_DIR / rel).resolve()
    if _REPO_WEB_DIR.resolve() in path.parents and path.is_file():
        return path.read_bytes()
    raise FileNotFoundError(f"缺少前端资源：{name}")
