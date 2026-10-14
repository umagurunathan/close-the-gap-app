"""Tunable settings, read from config/settings.toml (see the comments in that file).

Use it like `settings.urgency.urgent_hours`. A missing setting fails at startup with a clear error rather than being
guessed. Set SETTINGS_PATH to point at a different file (for example to try values after a team discussion).
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from types import SimpleNamespace

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.toml"


def _namespace(d: dict) -> SimpleNamespace:
    return SimpleNamespace(**{k: _namespace(v) if isinstance(v, dict) else v for k, v in d.items()})


def load(path: str | os.PathLike | None = None) -> SimpleNamespace:
    p = Path(path or os.getenv("SETTINGS_PATH") or DEFAULT_PATH)
    # utf-8-sig: some Windows editors add an invisible byte-order mark at the start of the file; accept it
    return _namespace(tomllib.loads(p.read_text(encoding="utf-8-sig")))


settings = load()
