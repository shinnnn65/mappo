"""Local HTTP host and static asset serving for the Web UI."""

from mappo.host.assets import load_asset
from mappo.host.web_server import DEFAULT_PORT, WebApp, create_server, serve_web

__all__ = ["DEFAULT_PORT", "WebApp", "create_server", "load_asset", "serve_web"]
