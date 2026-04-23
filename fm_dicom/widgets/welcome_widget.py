"""
Welcome widget displayed when no files are loaded.
"""

import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame,
    QListWidget, QListWidgetItem, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QFont

from fm_dicom.ui.icon_loader import themed_icon
from fm_dicom.themes.design_tokens import get_theme_tokens


class WelcomeWidget(QWidget):
    """
    A welcoming empty state widget that guides users to open files.
    """
    
    path_selected = pyqtSignal(str)
    
    def __init__(self, parent=None, recent_paths=None):
        super().__init__(parent)
        self.recent_paths = recent_paths or []
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.setSpacing(20)
        self.layout.setContentsMargins(40, 40, 40, 40)
        
        self.setup_ui()
        
    def setup_ui(self):
        # Title section
        title_container = QWidget()
        title_layout = QVBoxLayout(title_container)
        title_layout.setSpacing(5)
        
        # Title
        title = QLabel("FM-DICOM Tag Editor")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = title.font()
        font.setPointSize(28)
        font.setBold(True)
        title.setFont(font)
        title_layout.addWidget(title)
        
        # Subtitle
        subtitle = QLabel("Open DICOM files or directories to get started")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #888; font-size: 15px;")
        title_layout.addWidget(subtitle)
        
        self.layout.addWidget(title_container)
        self.layout.addSpacing(20)
        
        # Main content area (Horizontal: Action Buttons | Recent Activity)
        content_frame = QFrame()
        content_layout = QHBoxLayout(content_frame)
        content_layout.setSpacing(40)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Left Side: Action Buttons
        actions_container = QWidget()
        actions_layout = QVBoxLayout(actions_container)
        actions_layout.setSpacing(15)
        
        self.btn_open_file = self._create_action_button(
            "Open File", 
            "Open a single DICOM file",
            "open-file"
        )
        actions_layout.addWidget(self.btn_open_file)
        
        self.btn_open_dir = self._create_action_button(
            "Open Directory", 
            "Open a folder of files",
            "open-folder"
        )
        actions_layout.addWidget(self.btn_open_dir)
        
        content_layout.addWidget(actions_container)
        
        # Right Side: Recent Activity (only if we have recent paths)
        if self.recent_paths:
            # Separator line (vertical)
            v_line = QFrame()
            v_line.setFrameShape(QFrame.Shape.VLine)
            v_line.setFrameShadow(QFrame.Shadow.Sunken)
            v_line.setStyleSheet("color: #444;")
            content_layout.addWidget(v_line)
            
            recent_container = QWidget()
            recent_layout = QVBoxLayout(recent_container)
            recent_layout.setContentsMargins(0, 0, 0, 0)
            
            recent_header = QLabel("Recent Activity")
            recent_header.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 5px;")
            recent_layout.addWidget(recent_header)
            
            self.recent_list = QListWidget()
            self.recent_list.setFixedWidth(350)
            self.recent_list.setMinimumHeight(250)
            self.recent_list.setStyleSheet("""
                QListWidget {
                    background-color: transparent;
                    border: none;
                    outline: none;
                }
                QListWidget::item {
                    padding: 0px;
                    border-radius: 5px;
                    margin-bottom: 2px;
                }
                QListWidget::item:hover {
                    background-color: rgba(255, 255, 255, 0.05);
                }
                QListWidget::item:selected {
                    background-color: rgba(255, 255, 255, 0.1);
                    color: white;
                }
            """)
            
            for path in self.recent_paths:
                if not path:
                    continue
                    
                item = QListWidgetItem()
                # Create a custom widget for the item to show path better
                item_widget = QWidget()
                item_layout = QVBoxLayout(item_widget)
                item_layout.setContentsMargins(10, 8, 10, 8)
                item_layout.setSpacing(2)
                
                name_label = QLabel(os.path.basename(path) or path)
                name_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #ddd; background: transparent;")
                
                path_label = QLabel(path)
                path_label.setStyleSheet("color: #888; font-size: 11px; background: transparent;")
                path_label.setWordWrap(False)
                # Elide text if too long
                metrics = path_label.fontMetrics()
                elided_path = metrics.elidedText(path, Qt.TextElideMode.ElideMiddle, 330)
                path_label.setText(elided_path)
                
                item_layout.addWidget(name_label)
                item_layout.addWidget(path_label)
                
                item.setSizeHint(item_widget.sizeHint())
                self.recent_list.addItem(item)
                self.recent_list.setItemWidget(item, item_widget)
                
                # Store the path in the item for retrieval
                item.setData(Qt.ItemDataRole.UserRole, path)
            
            self.recent_list.itemClicked.connect(self._on_recent_clicked)
            recent_layout.addWidget(self.recent_list)
            
            content_layout.addWidget(recent_container)
        
        self.layout.addWidget(content_frame)
        
    def _create_action_button(self, text, subtext, icon_name):
        """Create a large styled action button"""
        btn = QPushButton()
        btn.setFixedSize(280, 80)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Styling for the button
        btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid #444;
                border-radius: 8px;
                text-align: left;
                padding-left: 15px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.07);
                border: 1px solid #666;
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.1);
            }
        """)
        
        # We'll use a layout inside the button for icon + text + subtext
        layout = QHBoxLayout(btn)
        layout.setSpacing(15)
        
        # Icon
        icon_lbl = QLabel()
        icon = themed_icon(icon_name)
        if icon:
            icon_lbl.setPixmap(icon.pixmap(32, 32))
        layout.addWidget(icon_lbl)
        
        text_container = QWidget()
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        
        title_lbl = QLabel(text)
        title_lbl.setStyleSheet("font-weight: bold; font-size: 15px; color: #eee; background: transparent;")
        
        sub_lbl = QLabel(subtext)
        sub_lbl.setStyleSheet("font-size: 11px; color: #888; background: transparent;")
        
        text_layout.addWidget(title_lbl)
        text_layout.addWidget(sub_lbl)
        
        layout.addWidget(text_container)
        layout.addStretch()
        
        return btn
        
    def _on_recent_clicked(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.path_selected.emit(path)
            
    def set_callbacks(self, open_file_cb, open_dir_cb, recent_path_cb=None):
        """Connect button signals to callbacks"""
        self.btn_open_file.clicked.connect(open_file_cb)
        self.btn_open_dir.clicked.connect(open_dir_cb)
        if recent_path_cb:
            self.path_selected.connect(recent_path_cb)
