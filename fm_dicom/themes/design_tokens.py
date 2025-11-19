"""
Design tokens for the FM-Dicom modern UI theme system.

These tokens centralize the color, typography, and spacing values so the
application can stay visually consistent across widgets and future style tweaks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class ThemeTokens:
    """Container for a flattened set of theme values."""

    name: str
    values: Dict[str, str]

    def as_dict(self) -> Dict[str, str]:
        """Return the raw dictionary for formatting helpers."""
        return self.values


THEME_TOKENS: Dict[str, ThemeTokens] = {
    "dark": ThemeTokens(
        name="Aurora Dark",
        values={
            "background_window": "#0b1220",
            "background_surface": "#121a2a",
            "background_surface_alt": "#182237",
            "background_popover": "#1f2a42",
            "stroke": "#25314d",
            "stroke_strong": "#2e3d5c",
            "accent": "#3dd2ff",
            "accent_hover": "#63e2ff",
            "accent_subtle": "#123546",
            "text_primary": "#f5f7ff",
            "text_secondary": "#c6e3ff",
            "text_muted": "#90a4c6",
            "success": "#47d7b7",
            "warning": "#f5c978",
            "danger": "#ff7b93",
            "shadow": "rgba(2, 7, 20, 0.55)",
            "scrollbar_groove": "#1a2438",
            "scrollbar_handle": "#2e3c58",
            "scrollbar_handle_hover": "#3d5075",
            "selection_text": "#05070f",
            "font_family": "'mononoki Nerd Font', 'mononoki', Inter, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
            "font_size_base": "13px",
            "font_size_small": "12px",
            "font_size_large": "15px",
            "radius_small": "6px",
            "radius_medium": "10px",
            "radius_large": "16px",
        },
    ),
    "light": ThemeTokens(
        name="Aurora Light",
        values={
            "background_window": "#f4f6fb",
            "background_surface": "#ffffff",
            "background_surface_alt": "#eef1fb",
            "background_popover": "#ffffff",
            "stroke": "#d5d9e2",
            "stroke_strong": "#c2c8d8",
            "accent": "#4f46e5",
            "accent_hover": "#4338ca",
            "accent_subtle": "#e0e7ff",
            "text_primary": "#111827",
            "text_secondary": "#1f2a37",
            "text_muted": "#4b5563",
            "success": "#059669",
            "warning": "#d97706",
            "danger": "#dc2626",
            "shadow": "rgba(15, 23, 42, 0.18)",
            "scrollbar_groove": "#e2e8f0",
            "scrollbar_handle": "#cbd5f5",
            "scrollbar_handle_hover": "#a5b4fc",
            "selection_text": "#ffffff",
            "font_family": "Inter, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
            "font_size_base": "13px",
            "font_size_small": "12px",
            "font_size_large": "15px",
            "radius_small": "6px",
            "radius_medium": "10px",
            "radius_large": "16px",
        },
    ),
    "catppuccin": ThemeTokens(
        name="Catppuccin Macchiato",
        values={
            "background_window": "#181926",
            "background_surface": "#24273a",
            "background_surface_alt": "#1e2030",
            "background_popover": "#2a2d44",
            "stroke": "#363a56",
            "stroke_strong": "#4b4f6c",
            "accent": "#8aadf4",
            "accent_hover": "#7dc4e4",
            "accent_subtle": "#2e3650",
            "text_primary": "#cad3f5",
            "text_secondary": "#b8c0e0",
            "text_muted": "#a5adcb",
            "success": "#a6da95",
            "warning": "#eed49f",
            "danger": "#f5bde6",
            "shadow": "rgba(8, 10, 20, 0.55)",
            "scrollbar_groove": "#2b2f47",
            "scrollbar_handle": "#444966",
            "scrollbar_handle_hover": "#5b6181",
            "selection_text": "#181926",
            "font_family": "'mononoki Nerd Font', 'mononoki', Inter, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
            "font_size_base": "13px",
            "font_size_small": "12px",
            "font_size_large": "15px",
            "radius_small": "6px",
            "radius_medium": "10px",
            "radius_large": "16px",
        },
    ),
}


def get_theme_tokens(theme_name: str) -> ThemeTokens:
    """
    Return the requested theme tokens, defaulting to the dark palette when the
    provided theme name is unknown.
    """

    normalized = (theme_name or "dark").lower()
    return THEME_TOKENS.get(normalized, THEME_TOKENS["dark"])
