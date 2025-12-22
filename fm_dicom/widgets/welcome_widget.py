"""
Welcome widget displayed when no files are loaded.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap, QFont

from fm_dicom.ui.icon_loader import themed_icon
from fm_dicom.themes.design_tokens import get_theme_tokens


class WelcomeWidget(QWidget):
    """
    A welcoming empty state widget that guides users to open files.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.setSpacing(20)
        
        self.setup_ui()
        
    def setup_ui(self):
        # Logo or Icon
        icon_label = QLabel()
        # Try to load app logo, fallback to generic icon if needed
        # Assuming main window has set window icon, but for widget we might need a resource path
        # For now, let's use a large text label or standard icon
        
        # Title
        title = QLabel("FM-DICOM Tag Editor")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = title.font()
        font.setPointSize(24)
        font.setBold(True)
        title.setFont(font)
        self.layout.addWidget(title)
        
        # Subtitle
        subtitle = QLabel("Open DICOM files or directories to get started")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: gray; font-size: 14px;")
        self.layout.addWidget(subtitle)
        
        self.layout.addSpacing(30)
        
        # Action Buttons Container
        buttons_frame = QFrame()
        buttons_layout = QHBoxLayout(buttons_frame)
        buttons_layout.setSpacing(20)
        buttons_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Open File Button
        self.btn_open_file = self._create_action_button(
            "Open File", 
            "Open a single DICOM file",
            "open-file"
        )
        buttons_layout.addWidget(self.btn_open_file)
        
        # Open Directory Button
        self.btn_open_dir = self._create_action_button(
            "Open Directory", 
            "Open a folder of files",
            "open-folder"
        )
        buttons_layout.addWidget(self.btn_open_dir)
        
        self.layout.addWidget(buttons_frame)
        
    def _create_action_button(self, text, subtext, icon_name):
        """Create a large styled action button"""
        btn = QPushButton()
        btn.setFixedSize(200, 120)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # We'll use a layout inside the button for icon + text + subtext
        layout = QVBoxLayout(btn)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Icon
        # Note: We need to set the icon on the button or use a label inside
        # Using a label inside gives more control
        # For simplicity in this iteration, we set text and rely on stylesheet
        
        title_lbl = QLabel(text)
        title_lbl.setStyleSheet("font-weight: bold; font-size: 16px;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        sub_lbl = QLabel(subtext)
        sub_lbl.setStyleSheet("font-size: 11px; color: gray;")
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(title_lbl)
        layout.addWidget(sub_lbl)
        
        return btn
        
    def set_callbacks(self, open_file_cb, open_dir_cb):
        """Connect button signals to callbacks"""
        self.btn_open_file.clicked.connect(open_file_cb)
        self.btn_open_dir.clicked.connect(open_dir_cb)
