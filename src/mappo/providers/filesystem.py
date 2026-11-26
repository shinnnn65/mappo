"""Explicit user-scoped local directory scanner."""

import os
from pathlib import Path

from mappo.core.models import error_code

MARKERS = {
    ".git",
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "Package.swift",
}
EXCLUDED = {
    "node_modules",
    "vendor",
    "target",
    "build",
    "dist",
    "Pods",
    "__pycache__",
    "venv",
    "Library",
    "Caches",
    "DerivedData",
}


def filesystem(inv, root):
    def report(error):
        inv.note("filesystem", error.filename, str(error), error_code(error))

    for folder, dirs, files in os.walk(root, onerror=report):
        markers = sorted(MARKERS.intersection(dirs + files))
        dirs[:] = sorted(
            d
            for d in dirs
            if not d.startswith(".")
            and d not in EXCLUDED
            and not os.path.islink(os.path.join(folder, d))
        )
        if markers:
            inv.add("filesystem", "filesystem", [folder], Path(folder) / markers[0])
