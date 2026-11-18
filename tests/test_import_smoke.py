from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Modules that must NOT be imported as part of passive smoke test (entrypoints or external hooks)
SKIP_MODULES = {
    "src.main",
    "src.__main__",
}


def _discover_src_modules() -> list[str]:
    src_dir = Path(__file__).resolve().parent.parent / "src"
    modules: list[str] = []

    for file_path in src_dir.rglob("*.py"):
        if file_path.name.startswith("."):
            continue
        rel = file_path.relative_to(src_dir.parent)
        parts = list(rel.parts)
        parts[-1] = file_path.stem
        mod_name = ".".join(parts)

        if mod_name not in SKIP_MODULES and not file_path.name.startswith("__"):
            modules.append(mod_name)

    return sorted(modules)


ALL_SRC_MODULES = _discover_src_modules()


@pytest.mark.parametrize("mod_name", ALL_SRC_MODULES)
def test_import_smoke(mod_name: str) -> None:
    """
    Import smoke test ensuring every single module in src/ can be cleanly imported
    without raising NameError, SyntaxError, or missing dependency errors.
    """
    dummy_env = {
        "DISCORD_TOKEN": "dummy_token_for_import_smoke",
        "DATABASE_URL": "postgresql://localhost:5432/postgres",
        "LAVALINK_URI": "http://localhost:2333",
        "LAVALINK_PASSWORD": "dummy_password",
        "ENVIRONMENT": "testing",
    }

    with patch.dict(os.environ, dummy_env):
        try:
            importlib.import_module(mod_name)
        except Exception as e:
            pytest.fail(f"Module '{mod_name}' failed smoke import check: {type(e).__name__}: {e}")
