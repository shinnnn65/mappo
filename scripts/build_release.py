"""Build the standalone mappo 0.3.0 zip application."""

import argparse
import shutil
import tempfile
import zipapp
from pathlib import Path


def _ignore_pycache(_directory, names):
    return {name for name in names if name == "__pycache__" or name.endswith(".pyc")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="destination for mappo.pyz")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    pkg_src = root / "src" / "mappo"
    web_src = root / "apps" / "web"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        pkg_dst = temp_path / "mappo"
        shutil.copytree(pkg_src, pkg_dst, ignore=_ignore_pycache)
        assets_dst = pkg_dst / "_web_assets"
        shutil.copytree(web_src, assets_dst, ignore=_ignore_pycache)
        (assets_dst / "__init__.py").write_text(
            '"""Bundled apps/web assets for zipapp distribution."""\n',
            encoding="utf-8",
        )
        zipapp.create_archive(
            temp_path,
            args.output,
            interpreter="/usr/bin/env python3",
            main="mappo.cli:run",
            compressed=True,
        )


if __name__ == "__main__":
    main()
