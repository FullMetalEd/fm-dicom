import logging
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor


def set_light_palette(app):
    # Revert to a standard palette or define your own light theme
    app.setPalette(QApplication.style().standardPalette())
    # If you have a specific light theme, apply it here.
    # For example:
    # palette = QPalette()
    # palette.setColor(QPalette.ColorRole.Window, QColor(240, 240, 240))
    # ... other light theme colors ...
    # app.setPalette(palette)
    logging.info("Applied light theme.")


def set_dark_palette(app): # User's original dark palette
    palette = QPalette()
    background = QColor(32, 34, 37)
    palette.setColor(QPalette.ColorRole.Window, background)
    palette.setColor(QPalette.ColorRole.Base, background)
    palette.setColor(QPalette.ColorRole.AlternateBase, background)
    palette.setColor(QPalette.ColorRole.Button, background)
    palette.setColor(QPalette.ColorRole.ToolTipBase, background)
    light_text = QColor(245, 245, 245)
    palette.setColor(QPalette.ColorRole.WindowText, light_text)
    palette.setColor(QPalette.ColorRole.Text, light_text)
    palette.setColor(QPalette.ColorRole.ButtonText, light_text)
    palette.setColor(QPalette.ColorRole.ToolTipText, light_text)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(80, 140, 255))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 85, 85))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(100, 100, 100))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(100, 100, 100))
    app.setPalette(palette)
    logging.info("Applied dark theme.")
