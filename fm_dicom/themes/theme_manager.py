import logging
from PyQt6.QtGui import QColor, QPalette

from fm_dicom.themes.design_tokens import get_theme_tokens

MODERN_QSS = """
* {{
    font-family: {font_family};
    font-size: {font_size_base};
    color: {text_primary};
}}

QMainWindow {{
    background-color: {background_window};
}}

QWidget#CentralWidget {{
    background-color: {background_window};
}}

QWidget#SurfacePanel {{
    background-color: {background_surface};
    border: 1px solid {stroke};
    border-radius: {radius_large};
}}

QWidget#ControlBar {{
    background-color: {background_surface_alt};
    border: 1px solid {stroke};
    border-radius: {radius_medium};
}}

QMenuBar, QToolBar {{
    background-color: {background_surface_alt};
    border-bottom: 1px solid {stroke};
    padding: 4px 8px;
}}

QToolBar QToolButton {{
    background-color: transparent;
    border-radius: {radius_small};
    padding: 6px 10px;
    margin: 0 2px;
}}

QToolBar QToolButton:hover {{
    background-color: {accent_subtle};
}}

QMenu {{
    background-color: {background_popover};
    border: 1px solid {stroke};
    border-radius: {radius_small};
}}

QMenu::item {{
    padding: 6px 18px;
    border-radius: {radius_small};
}}

QMenu::item:selected {{
    background: {accent_subtle};
    color: {text_primary};
}}

QStatusBar {{
    background-color: {background_surface_alt};
    color: {text_secondary};
    border-top: 1px solid {stroke};
}}

QStatusBar::item {{
    border: none;
}}

QWidget#SummaryBar {{
    background-color: {background_surface_alt};
    border: 1px solid {stroke};
    border-radius: {radius_medium};
    padding: 0 12px;
}}

QLabel#SummaryLabel {{
    font-weight: 600;
    color: {text_primary};
}}

QLabel#SummaryStats {{
    color: {text_muted};
    font-size: {font_size_small};
}}

QLabel#ImagePreview {{
    background-color: {background_surface};
    border: 1px dashed {stroke};
    border-radius: {radius_large};
    color: {text_muted};
}}

QLabel#FormLabel {{
    font-weight: 600;
    color: {text_secondary};
    letter-spacing: 0.5px;
}}

QLineEdit, QComboBox {{
    background-color: {background_surface};
    border: 1px solid {stroke};
    border-radius: {radius_small};
    padding: 6px 10px;
    selection-background-color: {accent};
    selection-color: {selection_text};
}}

QLineEdit:focus, QComboBox:focus {{
    border-color: {accent};
}}

QLineEdit::placeholder {{
    color: {text_muted};
}}

QTreeWidget {{
    background-color: {background_surface};
    border: 1px solid {stroke};
    border-radius: {radius_medium};
    padding: 6px;
    alternate-background-color: {background_surface_alt};
    selection-background-color: {accent};
    selection-color: {selection_text};
}}

QTreeWidget::item {{
    padding: 4px 6px;
}}

QTableWidget {{
    background-color: {background_surface};
    border: 1px solid {stroke};
    border-radius: {radius_medium};
    gridline-color: {stroke};
    selection-background-color: {accent};
    selection-color: {selection_text};
}}

QHeaderView::section {{
    background-color: {background_surface_alt};
    color: {text_secondary};
    border: none;
    padding: 6px;
    font-size: {font_size_small};
}}

QPushButton {{
    background-color: {background_surface_alt};
    border: 1px solid {stroke};
    border-radius: {radius_small};
    padding: 6px 16px;
    font-weight: 500;
}}

QPushButton:hover {{
    border-color: {accent};
}}

QPushButton[primary="true"] {{
    background-color: {accent};
    border-color: {accent};
    color: #ffffff;
}}

QPushButton[primary="true"]:hover {{
    background-color: {accent_hover};
    border-color: {accent_hover};
}}

QCheckBox {{
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: {radius_small};
    border: 1px solid {stroke};
    background: {background_surface};
}}

QCheckBox::indicator:checked {{
    background-color: {accent};
    border-color: {accent};
}}

QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 4px;
}}

QScrollBar::groove:vertical {{
    background: {scrollbar_groove};
    border-radius: {radius_small};
}}

QScrollBar::handle:vertical {{
    background: {scrollbar_handle};
    border-radius: {radius_small};
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: {scrollbar_handle_hover};
}}

QProgressBar {{
    border: 1px solid {stroke};
    border-radius: {radius_small};
    background-color: {background_surface_alt};
    text-align: center;
    padding: 2px;
}}

QProgressBar::chunk {{
    background-color: {accent};
    border-radius: {radius_small};
}}
"""


def _apply_palette(app, theme_name: str) -> QPalette:
    """Create and apply a palette derived from the design tokens."""

    tokens = get_theme_tokens(theme_name).as_dict()
    palette = QPalette()

    background = QColor(tokens["background_window"])
    surface = QColor(tokens["background_surface"])
    text = QColor(tokens["text_primary"])
    muted = QColor(tokens["text_muted"])
    accent = QColor(tokens["accent"])
    selection_text = QColor(tokens.get("selection_text", tokens["text_primary"]))

    palette.setColor(QPalette.ColorRole.Window, background)
    palette.setColor(QPalette.ColorRole.Base, surface)
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(tokens["background_surface_alt"]))
    palette.setColor(QPalette.ColorRole.Button, surface)
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(tokens["background_popover"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.Highlight, accent)
    palette.setColor(QPalette.ColorRole.HighlightedText, selection_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, muted)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, muted)

    app.setPalette(palette)
    app.setStyleSheet(MODERN_QSS.format(**tokens))

    return palette


def set_dark_palette(app):
    """Apply the modern dark theme."""

    _apply_palette(app, "dark")
    logging.info("Applied modern dark theme.")


def set_light_palette(app):
    """Apply the modern light theme."""

    _apply_palette(app, "light")
    logging.info("Applied modern light theme.")


def set_catppuccin_palette(app):
    """Apply the Catppuccin Mocha theme."""

    _apply_palette(app, "catppuccin")
    logging.info("Applied Catppuccin Mocha theme.")
