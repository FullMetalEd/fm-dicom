"""
Action Center Widget
A dockable container for tool results (Validation, Anonymization) to replace modal dialogs.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget, 
    QPushButton, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIcon

from fm_dicom.validation.validation_ui import ValidationResultsWidget
from fm_dicom.anonymization.anonymization_ui import AnonymizationResultsWidget

class ActionCenterWidget(QWidget):
    """
    Central widget for displaying tool outputs (Validation, Anonymization).
    Designed to be placed in a QDockWidget.
    """
    
    close_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        self.header = QFrame()
        self.header.setObjectName("actionCenterHeader")
        self.header.setStyleSheet("""
            #actionCenterHeader {
                background-color: palette(alternate-base);
                border-bottom: 1px solid palette(mid);
            }
        """)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(10, 5, 10, 5)
        
        self.title_label = QLabel("Action Center")
        font = self.title_label.font()
        font.setBold(True)
        self.title_label.setFont(font)
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        
        # Close button (optional, since Dock has one, but good for UX)
        self.close_btn = QPushButton("✕")
        self.close_btn.setFlat(True)
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setToolTip("Close Action Center")
        self.close_btn.clicked.connect(self.close_requested.emit)
        header_layout.addWidget(self.close_btn)
        
        layout.addWidget(self.header)
        
        # Stacked content area
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        
        # Initial empty state
        self.empty_page = QWidget()
        empty_layout = QVBoxLayout(self.empty_page)
        empty_label = QLabel("No active tools.\nRun Validation or Anonymization to see results here.")
        empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_label.setStyleSheet("color: gray;")
        empty_layout.addWidget(empty_label)
        self.stack.addWidget(self.empty_page)
        
    def show_validation_results(self, result):
        """Display validation results"""
        self.title_label.setText("Validation Results")
        
        # Remove previous validation widget if any
        # (For simplicity, we just add new one and remove old ones later if memory is an issue, 
        # but standard QStackedWidget usage often involves reusing or replacing)
        
        widget = ValidationResultsWidget(result)
        self.stack.addWidget(widget)
        self.stack.setCurrentWidget(widget)
        
    def show_anonymization_results(self, result):
        """Display anonymization results"""
        self.title_label.setText("Anonymization Results")
        
        widget = AnonymizationResultsWidget(result)
        self.stack.addWidget(widget)
        self.stack.setCurrentWidget(widget)
        
    def clear(self):
        """Reset to empty state"""
        self.title_label.setText("Action Center")
        self.stack.setCurrentWidget(self.empty_page)
