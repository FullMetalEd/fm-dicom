"""
Task Center Widget
A modern job monitor for tracking background tasks.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, 
    QPushButton, QFrame, QProgressBar, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer, QEvent, QSize
from PyQt6.QtGui import QFont, QColor
import logging

class JobCardWidget(QFrame):
    """A row representing a single background job."""
    
    dismissed = pyqtSignal(object)
    
    def __init__(self, job, parent=None):
        super().__init__(parent)
        self.job = job
        self.setObjectName("jobRow")
        
        # Style as a clean row
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("""
            #jobRow {
                background-color: transparent;
                border-bottom: 1px solid #333;
                margin: 0px;
                padding: 0px;
            }
            #jobRow[state="error"] QLabel#statusLabel { color: #ff6b6b; }
            #jobRow[state="success"] QLabel#statusLabel { color: #51cf66; }
        """)
        
        self.setup_ui()
        self._connect_signals()
        
        # Timer for duration update
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._update_duration)
        
    def setup_ui(self):
        # Vertical layout for the entire row
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # Ensure the card itself doesn't force a width
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        # --- TOP ROW: Title and Buttons ---
        top_line = QHBoxLayout()
        top_line.setSpacing(8)
        top_line.setContentsMargins(0, 0, 0, 0)
        
        self.title_label = QLabel(self.job.title)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(10)
        self.title_label.setFont(title_font)
        self.title_label.setWordWrap(True)
        self.title_label.setMinimumSize(0, 0) # Allow shrinking
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        top_line.addWidget(self.title_label)
        
        # Action Buttons Container (Right-aligned)
        btns_layout = QHBoxLayout()
        btns_layout.setSpacing(6)
        
        self.view_btn = QPushButton("View")
        self.view_btn.setVisible(False)
        self.view_btn.setFixedSize(70, 26) # Increased size and height
        self.view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.view_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b5bdb;
                color: white;
                font-size: 12px;
                font-weight: bold;
                border-radius: 4px;
                border: 1px solid #2b45b0;
                padding: 2px 5px;
            }
            QPushButton:hover { background-color: #4c6ef5; }
            QPushButton:pressed { background-color: #364fc7; }
        """)
        self.view_btn.clicked.connect(self._on_view_clicked)
        btns_layout.addWidget(self.view_btn)

        self.action_btn = QPushButton("✕")
        self.action_btn.setFixedSize(26, 26) # Match height
        self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action_btn.setToolTip("Cancel task")
        self.action_btn.setStyleSheet("""
            QPushButton { 
                color: #adb5bd; 
                background-color: rgba(255, 255, 255, 0.08);
                border: 1px solid #495057;
                border-radius: 13px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { 
                color: #fff; 
                background-color: rgba(255, 255, 255, 0.15); 
                border-color: #ced4da;
            }
        """)
        self.action_btn.clicked.connect(self._on_action_clicked)
        btns_layout.addWidget(self.action_btn)
        
        top_line.addLayout(btns_layout)
        layout.addLayout(top_line)
        
        # --- MIDDLE ROW: Status, Percentage, Timer ---
        status_line = QHBoxLayout()
        status_line.setSpacing(10)
        status_line.setContentsMargins(0, 0, 0, 0)
        
        self.status_label = QLabel("Initializing...")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setStyleSheet("color: #868e96; font-size: 11px;")
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumSize(0, 0)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        status_line.addWidget(self.status_label)
        
        self.percent_label = QLabel("0%")
        self.percent_label.setStyleSheet("color: #4dabf7; font-size: 11px; font-weight: bold;")
        self.percent_label.setFixedWidth(35)
        self.percent_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        status_line.addWidget(self.percent_label)

        self.duration_label = QLabel("00:00")
        self.duration_label.setStyleSheet("color: #868e96; font-size: 11px; font-family: monospace;")
        self.duration_label.setFixedWidth(40)
        self.duration_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        status_line.addWidget(self.duration_label)
        
        layout.addLayout(status_line)
        
        # --- BOTTOM ROW: Progress Bar ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(5)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumWidth(0)
        self.progress_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #212529;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #339af0;
                border-radius: 2px;
            }
        """)
        layout.addWidget(self.progress_bar)

    def _connect_signals(self):
        self.job.signals.started.connect(self._on_started)
        self.job.signals.progress.connect(self._on_progress)
        self.job.signals.finished.connect(self._on_finished)
        self.job.signals.failed.connect(self._on_failed)
        self.job.signals.cancelled.connect(self._on_cancelled)
        
    def _on_action_clicked(self):
        if self.timer.isActive():
            self.job.cancel()
            self.status_label.setText("Cancelling...")
            self.action_btn.setEnabled(False)
        else:
            self.dismissed.emit(self)

    @pyqtSlot()
    def _on_view_clicked(self):
        """Handle view button click with error handling"""
        try:
            logging.info(f"Viewing results for job: {self.job.title}")
            self.job.view_results()
        except Exception as e:
            logging.error(f"Error viewing results: {e}", exc_info=True)

    def _update_duration(self):
        duration = int(self.job.get_duration())
        mins = duration // 60
        secs = duration % 60
        self.duration_label.setText(f"{mins:02d}:{secs:02d}")

    @pyqtSlot()
    def _on_started(self):
        self.status_label.setText("Running...")
        self.timer.start()

    @pyqtSlot(int, int, str)
    def _on_progress(self, current, total, status):
        # Prevent very long strings without spaces from breaking layout
        if len(status) > 100:
            status = status[:45] + "..." + status[-45:]
        
        self.status_label.setText(status)
        if total > 0:
            percent = int((current / total) * 100)
            self.progress_bar.setValue(percent)
            self.percent_label.setText(f"{percent}%")

    @pyqtSlot(object)
    def _on_finished(self, result):
        self.timer.stop()
        self._update_duration()
        self.status_label.setText("Completed")
        self.progress_bar.setValue(100)
        self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #40c057; }")
        self.percent_label.setText("100%")
        self.percent_label.setStyleSheet("color: #51cf66; font-size: 11px; font-weight: bold;")
        
        # Show view button if the job is finished
        self.view_btn.setVisible(True)
            
        self.action_btn.setToolTip("Dismiss")
        self.action_btn.setEnabled(True)
        self.setProperty("state", "success")
        self.style().unpolish(self)
        self.style().polish(self)
        self.updateGeometry()

    @pyqtSlot(str)
    def _on_failed(self, error):
        self.timer.stop()
        self._update_duration()
        self.status_label.setText(f"Error: {error}")
        self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: #fa5252; }")
        self.percent_label.setStyleSheet("color: #ff6b6b; font-size: 11px; font-weight: bold;")
        
        # Show view button on failure too
        self.view_btn.setVisible(True)
        
        self.action_btn.setToolTip("Dismiss")
        self.action_btn.setEnabled(True)
        self.setProperty("state", "error")
        self.style().unpolish(self)
        self.style().polish(self)
        self.updateGeometry()

    @pyqtSlot()
    def _on_cancelled(self):
        self.timer.stop()
        self._update_duration()
        self.status_label.setText("Cancelled")
        self.action_btn.setToolTip("Dismiss")
        self.action_btn.setEnabled(True)
        self.updateGeometry()


class TaskCenterWidget(QWidget):
    """
    Central widget for displaying background jobs.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Scroll Area for Job Cards
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("background: transparent;")
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.scroll_content = QWidget()
        self.scroll_content.setMinimumWidth(0)
        self.cards_layout = QVBoxLayout(self.scroll_content)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(0)
        self.cards_layout.addStretch()
        
        self.scroll.setWidget(self.scroll_content)
        layout.addWidget(self.scroll)
        
        # Empty state label
        self.empty_label = QLabel("No active tasks")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #495057; margin-top: 50px; font-size: 12px;")
        self.cards_layout.insertWidget(0, self.empty_label)

        # Force content width to match scroll viewport for correct wrapping
        self.scroll.installEventFilter(self)

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.Resize and source is self.scroll:
            self.scroll_content.setFixedWidth(self.scroll.viewport().width())
        return super().eventFilter(source, event)

    def add_job_card(self, job):
        """Add a new job card to the task center."""
        self.empty_label.hide()
        
        card = JobCardWidget(job)
        card.dismissed.connect(self._remove_card)
        # Insert at top
        self.cards_layout.insertWidget(0, card)
        
    def _remove_card(self, card):
        """Remove a job card from the layout."""
        self.cards_layout.removeWidget(card)
        card.deleteLater()
        
        # Show empty label if no more cards (accounting for the stretch at the end)
        if self.cards_layout.count() <= 2: # empty_label + stretch
            self.empty_label.show()
