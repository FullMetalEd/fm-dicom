"""
Widget showing real-time summary with lazy calculation.

This module provides a widget for displaying selection summary information
with lazy calculation of file sizes and metadata.
"""

import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt


class LazySelectionSummaryWidget(QWidget):
    """Widget showing real-time summary with lazy calculation"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._file_size_cache = {}  # Cache file sizes
        
    def _setup_ui(self):
        """Setup the summary UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # Create summary labels
        self.file_count_label = QLabel("Files: 0")
        self.size_label = QLabel("Size: 0 MB")
        self.breakdown_label = QLabel("Patients: 0, Studies: 0, Series: 0")
        
        # Style the labels
        font = QFont()
        font.setBold(True)
        for label in [self.file_count_label, self.size_label, self.breakdown_label]:
            label.setFont(font)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Add to layout
        layout.addWidget(self.file_count_label)
        layout.addWidget(self.size_label)
        layout.addWidget(self.breakdown_label)
        
        # Style the widget
        self.setStyleSheet("""
            QWidget {
                background-color: #2c2f33;
                border: 1px solid #444;
                border-radius: 5px;
            }
            QLabel {
                color: #f5f5f5;
                padding: 2px;
            }
        """)
    
    def update_summary(self, selected_files):
        """Update summary with lazy calculation"""
        if not selected_files:
            self.file_count_label.setText("Files: 0")
            self.size_label.setText("Size: 0 MB")
            self.breakdown_label.setText("Patients: 0, Studies: 0, Series: 0")
            return
        
        # Just show file count immediately
        file_count = len(selected_files)
        self.file_count_label.setText(f"Files: {file_count}")
        
        # Calculate size from cache or estimate
        total_size = 0
        for file_path in selected_files:
            if file_path in self._file_size_cache:
                total_size += self._file_size_cache[file_path]
            elif os.path.exists(file_path):
                try:
                    size = os.path.getsize(file_path)
                    self._file_size_cache[file_path] = size
                    total_size += size
                except:
                    # Estimate 500KB per file if can't read
                    total_size += 500 * 1024
        
        # Format size
        if total_size < 1024 * 1024:  # Less than 1MB
            size_str = f"{total_size / 1024:.1f} KB"
        elif total_size < 1024 * 1024 * 1024:  # Less than 1GB
            size_str = f"{total_size / (1024 * 1024):.1f} MB"
        else:
            size_str = f"{total_size / (1024 * 1024 * 1024):.2f} GB"
        
        self.size_label.setText(f"Size: {size_str}")
        
        # Simplified breakdown - just estimate from file paths
        # This avoids reading DICOM headers
        unique_patients = set()
        unique_studies = set()
        unique_series = set()
        
        for file_path in selected_files:
            # Extract IDs from file path or use simple heuristics
            path_parts = file_path.split(os.sep)
            if len(path_parts) >= 3:
                unique_patients.add(path_parts[-3] if len(path_parts) > 3 else "patient1")
                unique_studies.add(path_parts[-2] if len(path_parts) > 2 else "study1")
                unique_series.add(path_parts[-1] if len(path_parts) > 1 else "series1")
        
        self.breakdown_label.setText(f"Est. Patients: {len(unique_patients)}, Studies: {len(unique_studies)}, Series: {len(unique_series)}")