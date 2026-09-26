"""Swing Desk — small module-level shared state (avoids circular imports)."""
from __future__ import annotations

from typing import Callable

from .ui.theme import THEMES, Theme

_active_theme_key: str = "obsidian"


def set_active_theme(key: str) -> None:
    global _active_theme_key
    _active_theme_key = key if key in THEMES else "obsidian"


def active_theme() -> Theme:
    return THEMES.get(_active_theme_key, THEMES["obsidian"])
