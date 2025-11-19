"""
Lightweight icon loader that provides access to the modern SVG icon set.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

from PyQt6.QtGui import QIcon

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"


@lru_cache(maxsize=None)
def _load_icon(icon_name: str) -> Optional[QIcon]:
    icon_path = ICON_DIR / f"{icon_name}.svg"
    if icon_path.exists():
        return QIcon(str(icon_path))
    logging.warning("Icon '%s' not found at %s", icon_name, icon_path)
    return None


def themed_icon(icon_name: str, fallback: Optional[QIcon] = None) -> QIcon:
    """
    Return a themed icon by name, falling back to the provided QIcon (or empty icon).
    """

    icon = _load_icon(icon_name)
    if icon is not None and not icon.isNull():
        return icon
    return fallback if fallback is not None else QIcon()
