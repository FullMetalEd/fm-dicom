"""
Dialog for selecting files to send via DICOM with hierarchical checkboxes.

This module provides a dialog for selecting DICOM files for network transmission
with hierarchical organization and selection capabilities.
"""

import os
import logging
import pydicom
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTreeWidgetItem
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

from fm_dicom.widgets.checkbox_tree import OptimizedCheckboxTreeWidget
from fm_dicom.widgets.selection_summary import LazySelectionSummaryWidget


class DicomSendSelectionDialog(QDialog):
    """Dialog for selecting files to send via DICOM with hierarchical checkboxes"""
    
    def __init__(self, loaded_files, initial_selection_items, parent=None):
        super().__init__(parent)
        
        # Store references
        self.loaded_files = loaded_files  # Now this will work
        self.initial_selection_items = initial_selection_items
        self.selected_files = []
        
        # Add some debug logging
        logging.info(f"DicomSendSelectionDialog initialized with {len(self.loaded_files)} loaded files")
        
        self.setWindowTitle("Select Files for DICOM Send")
        self.setModal(True)
        self.resize(600, 500)
        
        # Now call the setup methods
        self._setup_ui()
        self._populate_tree()
        self._set_initial_selection()
        
    def _setup_ui(self):
        """Setup the dialog UI"""
        layout = QVBoxLayout(self)
        
        # Title
        title_label = QLabel("Select Files for DICOM Send")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Search bar
        search_layout = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search patients, studies, series...")
        self.search_bar.textChanged.connect(self._filter_tree)
        
        # Expand/Collapse buttons
        self.expand_btn = QPushButton("Expand All")
        self.collapse_btn = QPushButton("Collapse All")
        self.expand_btn.clicked.connect(self._expand_all)
        self.collapse_btn.clicked.connect(self._collapse_all)
        
        search_layout.addWidget(QLabel("Search:"))
        search_layout.addWidget(self.search_bar)
        search_layout.addStretch()
        search_layout.addWidget(self.expand_btn)
        search_layout.addWidget(self.collapse_btn)
        layout.addLayout(search_layout)
        
        # Main content area
        content_layout = QHBoxLayout()
        
        # Left side: Tree
        tree_layout = QVBoxLayout()
        tree_label = QLabel("Available Files:")
        tree_label.setFont(QFont("", weight=QFont.Weight.Bold))
        tree_layout.addWidget(tree_label)
        
        # IMPORTANT: Use the correct widget class name
        self.tree_widget = OptimizedCheckboxTreeWidget()
        self.tree_widget.selection_changed.connect(self._on_selection_changed)
        tree_layout.addWidget(self.tree_widget)
        
        # Quick action buttons
        action_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_none_btn = QPushButton("Select None")
        self.select_all_btn.clicked.connect(self.tree_widget.select_all)
        self.select_none_btn.clicked.connect(self.tree_widget.select_none)
        
        action_layout.addWidget(self.select_all_btn)
        action_layout.addWidget(self.select_none_btn)
        action_layout.addStretch()
        tree_layout.addLayout(action_layout)
        
        content_layout.addLayout(tree_layout, 2)
        
        # Right side: Summary
        summary_layout = QVBoxLayout()
        summary_label = QLabel("Selection Summary:")
        summary_label.setFont(QFont("", weight=QFont.Weight.Bold))
        summary_layout.addWidget(summary_label)
        
        # IMPORTANT: Use the correct widget class name
        self.summary_widget = LazySelectionSummaryWidget()
        summary_layout.addWidget(self.summary_widget)
        summary_layout.addStretch()
        
        content_layout.addLayout(summary_layout, 1)
        layout.addLayout(content_layout)
        
        # Bottom buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.cancel_btn = QPushButton("Cancel")
        self.send_btn = QPushButton("Send Selected Files")
        self.send_btn.setDefault(True)
        
        # Style the send button
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #508cff;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #6ea3ff;
            }
            QPushButton:pressed {
                background-color: #3d75e6;
            }
        """)
        
        self.cancel_btn.clicked.connect(self.reject)
        self.send_btn.clicked.connect(self.accept)
        
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.send_btn)
        layout.addLayout(button_layout)
    
    def _populate_tree(self):
        """Populate tree with file hierarchy and proper checkboxes"""
        logging.info("Populating DICOM send selection tree")
        
        # Build hierarchy from loaded files
        hierarchy = {}
        file_paths = [file_info[0] for file_info in self.loaded_files]
        
        for file_path in file_paths:
            try:
                ds = pydicom.dcmread(file_path, stop_before_pixels=True)
                
                patient_id = getattr(ds, "PatientID", "Unknown ID")
                patient_name = getattr(ds, "PatientName", "Unknown Name")
                patient_label = f"{patient_name} ({patient_id})"
                
                study_uid = getattr(ds, "StudyInstanceUID", "Unknown StudyUID")
                study_desc = getattr(ds, "StudyDescription", "No Study Description")
                study_label = f"{study_desc}"
                
                series_uid = getattr(ds, "SeriesInstanceUID", "Unknown SeriesUID")
                series_desc = getattr(ds, "SeriesDescription", "No Series Description")
                series_number = getattr(ds, "SeriesNumber", "")
                series_label = f"{series_desc}"
                if series_number:
                    series_label += f" (#{series_number})"
                
                instance_number = getattr(ds, "InstanceNumber", None)
                sop_uid = getattr(ds, "SOPInstanceUID", os.path.basename(file_path))
                if instance_number is not None:
                    instance_label = f"Instance {instance_number}"
                else:
                    instance_label = f"{os.path.basename(file_path)}"
                
                # Build hierarchy
                hierarchy.setdefault(patient_label, {}).setdefault(study_label, {}).setdefault(series_label, {})[instance_label] = file_path
                
            except Exception as e:
                logging.warning(f"Could not read DICOM file {file_path}: {e}")
                continue
        
        # Populate tree widget with proper checkbox setup
        for patient, studies in hierarchy.items():
            patient_item = QTreeWidgetItem([patient, "", ""])
            
            # FIXED: Only ItemIsUserCheckable - let OptimizedCheckboxTreeWidget handle tri-state
            patient_item.setFlags(
                patient_item.flags() | 
                Qt.ItemFlag.ItemIsUserCheckable
                # NO tri-state flags - custom widget handles this
            )
            patient_item.setCheckState(0, Qt.CheckState.Unchecked)
            
            self.tree_widget.addTopLevelItem(patient_item)
            
            patient_file_count = 0
            for study, series_dict in studies.items():
                study_item = QTreeWidgetItem([study, "", ""])
                
                # FIXED: Only ItemIsUserCheckable - let OptimizedCheckboxTreeWidget handle tri-state
                study_item.setFlags(
                    study_item.flags() | 
                    Qt.ItemFlag.ItemIsUserCheckable
                    # NO tri-state flags - custom widget handles this
                )
                study_item.setCheckState(0, Qt.CheckState.Unchecked)
                
                patient_item.addChild(study_item)
                
                study_file_count = 0
                for series, instances in series_dict.items():
                    series_item = QTreeWidgetItem([series, "", ""])
                    
                    # FIXED: Only ItemIsUserCheckable - let OptimizedCheckboxTreeWidget handle tri-state
                    series_item.setFlags(
                        series_item.flags() | 
                        Qt.ItemFlag.ItemIsUserCheckable
                        # NO tri-state flags - custom widget handles this
                    )
                    series_item.setCheckState(0, Qt.CheckState.Unchecked)
                    
                    study_item.addChild(series_item)
                    
                    series_file_count = len(instances)
                    study_file_count += series_file_count
                    patient_file_count += series_file_count
                    
                    # Calculate series size
                    series_size = sum(os.path.getsize(fp) for fp in instances.values() if os.path.exists(fp))
                    series_size_mb = series_size / (1024 * 1024)
                    
                    series_item.setText(1, str(series_file_count))
                    series_item.setText(2, f"{series_size_mb:.1f}MB")
                    
                    for instance, filepath in sorted(instances.items()):
                        instance_item = QTreeWidgetItem([instance, "1", ""])
                        
                        # CORRECT: Only ItemIsUserCheckable for leaf items
                        instance_item.setFlags(
                            instance_item.flags() | 
                            Qt.ItemFlag.ItemIsUserCheckable
                        )
                        instance_item.setCheckState(0, Qt.CheckState.Unchecked)
                        instance_item.setData(0, Qt.ItemDataRole.UserRole, filepath)  # Store file path
                        
                        series_item.addChild(instance_item)
                
                study_item.setText(1, str(study_file_count))
            
            patient_item.setText(1, str(patient_file_count))
        
        # Expand tree by default
        self.tree_widget.expandAll()
        
        logging.info(f"Populated tree with {len(hierarchy)} patients")
    
    def _set_initial_selection(self):
        """Set initial selection based on what user had selected in main tree"""
        if not self.initial_selection_items:
            return
        
        # Collect file paths from initial selection
        initial_file_paths = []
        for item in self.initial_selection_items:
            file_paths = self._collect_instance_filepaths_from_item(item)
            initial_file_paths.extend(file_paths)
        
        # Set selection in tree
        self.tree_widget.set_initial_selection(initial_file_paths)
        
        logging.info(f"Set initial selection: {len(initial_file_paths)} files")
    
    def _collect_instance_filepaths_from_item(self, tree_item):
        """Collect file paths from a tree item (reuse MainWindow logic)"""
        filepaths = []
        
        def collect(item):
            fp = item.data(0, Qt.ItemDataRole.UserRole)
            if fp:
                filepaths.append(fp)
            for i in range(item.childCount()):
                collect(item.child(i))
        
        collect(tree_item)
        return filepaths
    
    def _on_selection_changed(self, selected_files):
        """Handle selection changes"""
        self.selected_files = selected_files
        self.summary_widget.update_summary(selected_files)
        
        # Update send button text
        if selected_files:
            self.send_btn.setText(f"Send {len(selected_files)} Files")
            self.send_btn.setEnabled(True)
        else:
            self.send_btn.setText("Send Selected Files")
            self.send_btn.setEnabled(False)
    
    def _filter_tree(self, text):
        """Filter tree based on search text"""
        # TODO: Implement filtering logic
        pass
    
    def _expand_all(self):
        """Expand all tree items"""
        self.tree_widget.expandAll()
    
    def _collapse_all(self):
        """Collapse all tree items"""
        self.tree_widget.collapseAll()
    
    def get_selected_files(self):
        """Return list of selected file paths"""
        return self.selected_files