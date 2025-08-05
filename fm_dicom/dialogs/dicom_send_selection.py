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
    QTreeWidgetItem, QProgressDialog, QApplication
)

from fm_dicom.widgets.focus_aware import FocusAwareProgressDialog
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer

from fm_dicom.widgets.checkbox_tree import OptimizedCheckboxTreeWidget
from fm_dicom.widgets.selection_summary import LazySelectionSummaryWidget


class AsyncTreePopulator(QThread):
    """Background worker for populating tree structure without blocking UI"""
    
    # Signals for communication with main thread
    tree_data_ready = pyqtSignal(object)  # Processed hierarchy data
    progress_updated = pyqtSignal(int, int, str)  # current, total, status
    population_complete = pyqtSignal()
    population_failed = pyqtSignal(str)  # error message
    
    def __init__(self, loaded_files, hierarchy_data):
        super().__init__()
        self.loaded_files = loaded_files
        self.hierarchy_data = hierarchy_data
        self.cancelled = False
    
    def run(self):
        """Process hierarchy data in background thread"""
        try:
            logging.info("AsyncTreePopulator: Starting background tree population")
            
            # Convert hierarchy data or build from loaded files
            if self.hierarchy_data:
                self.progress_updated.emit(0, 100, "Converting hierarchy data...")
                hierarchy = self._convert_hierarchy_data(self.hierarchy_data)
                self.progress_updated.emit(50, 100, "Hierarchy converted")
            else:
                self.progress_updated.emit(0, 100, "Building hierarchy from files...")
                hierarchy = self._build_hierarchy_from_loaded_files()
                self.progress_updated.emit(80, 100, "Hierarchy built")
            
            if self.cancelled:
                return
            
            self.progress_updated.emit(100, 100, "Tree data ready")
            self.tree_data_ready.emit(hierarchy)
            self.population_complete.emit()
            
            logging.info("AsyncTreePopulator: Background tree population complete")
            
        except Exception as e:
            logging.error(f"AsyncTreePopulator: Error during tree population: {e}", exc_info=True)
            self.population_failed.emit(str(e))
    
    def cancel(self):
        """Cancel the background operation"""
        self.cancelled = True
        self.requestInterruption()
    
    def _convert_hierarchy_data(self, hierarchy_data):
        """Convert TreeManager hierarchy format to selection dialog format"""
        converted_hierarchy = {}
        items_processed = 0
        total_items = sum(
            len(series_data) 
            for patient_data in hierarchy_data.values()
            for study_data in patient_data.values()
            for series_data in study_data.values()
        )
        
        for patient_label, patient_data in hierarchy_data.items():
            if self.cancelled:
                break
            for study_label, study_data in patient_data.items():
                if self.cancelled:
                    break
                for series_label, series_data in study_data.items():
                    if self.cancelled:
                        break
                    for instance_label, instance_data in series_data.items():
                        if self.cancelled:
                            break
                        file_path = instance_data['filepath']
                        
                        # Convert to selection dialog format
                        converted_hierarchy.setdefault(patient_label, {}).setdefault(study_label, {}).setdefault(series_label, {})[instance_label] = file_path
                        
                        items_processed += 1
                        
                        # Yield control periodically
                        if items_processed % 100 == 0:
                            progress = int((items_processed / total_items) * 45) + 5  # 5-50% range
                            self.progress_updated.emit(progress, 100, f"Converting hierarchy... ({items_processed}/{total_items})")
                            # Remove msleep to avoid blocking - Qt thread scheduling handles this
        
        return converted_hierarchy
    
    def _build_hierarchy_from_loaded_files(self):
        """Build hierarchy from loaded files (fallback for backward compatibility)"""
        hierarchy = {}
        file_paths = [file_info[0] for file_info in self.loaded_files]
        total_files = len(file_paths)
        
        for idx, file_path in enumerate(file_paths):
            if self.cancelled:
                break
                
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
                
                # Update progress periodically
                if idx % 100 == 0:
                    progress = int((idx / total_files) * 80)  # Use 80% for file processing
                    self.progress_updated.emit(progress, 100, f"Processing file {idx + 1} of {total_files}")
                
            except Exception as e:
                logging.warning(f"Could not read DICOM file {file_path}: {e}")
                continue
        
        return hierarchy


class DicomSendSelectionDialog(QDialog):
    """Dialog for selecting files to send via DICOM with hierarchical checkboxes"""
    
    def __init__(self, loaded_files, initial_selection_items, parent=None, hierarchy_data=None):
        super().__init__(parent)
        
        # Store references
        self.loaded_files = loaded_files  # Fallback for backward compatibility
        self.initial_selection_items = initial_selection_items
        self.selected_files = []
        self.hierarchy_data = hierarchy_data  # Pre-built hierarchy for performance
        self.tree_populated = False
        self.tree_populator = None
        self.progress_dialog = None  # Backup progress dialog for large datasets
        
        # Add some debug logging
        if hierarchy_data:
            logging.info(f"DicomSendSelectionDialog initialized with pre-built hierarchy")
        else:
            logging.info(f"DicomSendSelectionDialog initialized with {len(self.loaded_files)} loaded files (will build hierarchy)")
        
        self.setWindowTitle("Select Files for DICOM Send")
        self.setModal(True)
        self.resize(600, 500)
        
        # Setup UI immediately so dialog can be shown
        self._setup_ui()
        
        # Defer worker start to allow UI to fully render
        QTimer.singleShot(100, self._start_async_tree_population)  # Increased delay
    
    def _start_async_tree_population(self):
        """Start background tree population worker"""
        # Create and configure worker
        self.tree_populator = AsyncTreePopulator(self.loaded_files, self.hierarchy_data)
        
        # Connect signals with queued connections for thread safety
        self.tree_populator.tree_data_ready.connect(self._on_tree_data_ready, Qt.ConnectionType.QueuedConnection)
        self.tree_populator.progress_updated.connect(self._on_population_progress, Qt.ConnectionType.QueuedConnection)
        self.tree_populator.population_complete.connect(self._on_population_complete, Qt.ConnectionType.QueuedConnection)
        self.tree_populator.population_failed.connect(self._on_population_failed, Qt.ConnectionType.QueuedConnection)
        
        # Show loading state in tree and force UI update
        self._show_loading_state()
        
        # For very large datasets, also show a progress dialog
        total_files = len(self.loaded_files) if self.loaded_files else 0
        if total_files > 5000:
            self.progress_dialog = FocusAwareProgressDialog("Loading file hierarchy...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowTitle("Loading DICOM Files")
            self.progress_dialog.setMinimumDuration(0)
            self.progress_dialog.setValue(0)
            self.progress_dialog.canceled.connect(self._cancel_population)
            self.progress_dialog.show()
        
        # Start worker
        self.tree_populator.start()
        logging.info("Started async tree population worker")
    
    def _show_loading_state(self):
        """Show loading indicator in tree area"""
        # Ensure tree widget exists
        if not hasattr(self, 'tree_widget') or not self.tree_widget:
            logging.warning("Tree widget not available for loading state")
            return
            
        # Clear tree and show loading message
        self.tree_widget.clear()
        loading_item = QTreeWidgetItem(["Loading file hierarchy...", "", ""])
        loading_item.setFlags(Qt.ItemFlag.NoItemFlags)  # Make it non-interactive
        self.tree_widget.addTopLevelItem(loading_item)
        
        # Expand to show the loading message
        self.tree_widget.expandAll()
        
        # Disable buttons until loading is complete
        if hasattr(self, 'send_btn') and self.send_btn:
            self.send_btn.setEnabled(False)
            self.send_btn.setText("Loading...")
        
        # Force UI update to ensure loading state is visible
        self.update()
        
        logging.info("Loading state displayed")
    
    def _on_tree_data_ready(self, hierarchy):
        """Handle tree data ready from background worker"""
        try:
            logging.info("Tree data ready, populating tree widget")
            
            # Clear loading indicator
            self.tree_widget.clear()
            
            # Populate tree with processed data (fast since data is ready)
            self.tree_widget.setUpdatesEnabled(False)
            try:
                self._populate_tree_widget_sync(hierarchy)
            finally:
                self.tree_widget.setUpdatesEnabled(True)
            
            # Expand tree intelligently
            self._expand_tree_intelligently(hierarchy)
            
            # Mark as populated
            self.tree_populated = True
            
            # Enable interface
            self.send_btn.setEnabled(False)  # Will be enabled when selection is made
            self.send_btn.setText("Send Selected Files")
            
            # Set initial selection
            self._set_initial_selection()
            
            # Ensure dialog remains visible and responsive
            self.show()
            self.raise_()
            self.activateWindow()
            
            logging.info("Tree population complete, dialog ready for interaction")
            
        except Exception as e:
            logging.error(f"Error in _on_tree_data_ready: {e}", exc_info=True)
            self._on_population_failed(f"Failed to populate tree: {str(e)}")
    
    def _on_population_progress(self, current, total, status):
        """Handle progress updates from background worker"""
        try:
            # Update loading message
            if self.tree_widget.topLevelItemCount() > 0:
                loading_item = self.tree_widget.topLevelItem(0)
                if loading_item:
                    progress_percent = int((current / total) * 100) if total > 0 else 0
                    loading_item.setText(0, f"{status} ({progress_percent}%)")
            
            # Update progress dialog if visible
            if self.progress_dialog:
                self.progress_dialog.setValue(current)
                self.progress_dialog.setLabelText(status)
                
        except Exception as e:
            logging.error(f"Error in _on_population_progress: {e}", exc_info=True)
    
    def _on_population_complete(self):
        """Handle completion of tree population"""
        try:
            # Close progress dialog if it was shown
            if self.progress_dialog:
                # Disconnect the canceled signal before closing to prevent unwanted rejection
                self.progress_dialog.canceled.disconnect()
                self.progress_dialog.close()
                self.progress_dialog = None
            
            # Ensure dialog remains open and responsive
            if not self.isVisible():
                logging.warning("Dialog was hidden, making it visible again")
                self.show()
                self.raise_()
                self.activateWindow()
            
            logging.info("Async tree population completed successfully - dialog should remain open")
            
        except Exception as e:
            logging.error(f"Error in _on_population_complete: {e}", exc_info=True)
    
    def _cancel_population(self):
        """Handle cancellation of tree population"""
        if self.tree_populator:
            self.tree_populator.cancel()
        self.reject()
    
    def _on_population_failed(self, error_message):
        """Handle tree population failure"""
        try:
            logging.error(f"Tree population failed: {error_message}")
            
            # Close progress dialog if it was shown
            if self.progress_dialog:
                # Disconnect the canceled signal before closing to prevent unwanted rejection
                self.progress_dialog.canceled.disconnect()
                self.progress_dialog.close()
                self.progress_dialog = None
            
            # Clear loading indicator and show error
            self.tree_widget.clear()
            error_item = QTreeWidgetItem([f"Error loading files: {error_message}", "", ""])
            error_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.tree_widget.addTopLevelItem(error_item)
            
            # Keep buttons disabled
            self.send_btn.setText("Error - Cannot Send")
            
            # Ensure dialog remains visible even with error
            self.show()
            self.raise_()
            
        except Exception as e:
            logging.error(f"Error in _on_population_failed: {e}", exc_info=True)
        
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
        
        # Use pre-built hierarchy if available, otherwise build from loaded files
        if self.hierarchy_data:
            hierarchy = self._convert_hierarchy_data(self.hierarchy_data)
        else:
            hierarchy = self._build_hierarchy_from_loaded_files()
            
        if not hierarchy:
            logging.warning("No hierarchy data available")
            return
        
        # Count total instances for progress tracking
        total_instances = sum(
            len(instances) 
            for patient_data in hierarchy.values()
            for study_data in patient_data.values() 
            for series_data in study_data.values()
            for instances in series_data.values()
        )
        
        # Show progress dialog for large datasets
        progress = None
        if total_instances > 1000:
            progress = FocusAwareProgressDialog("Populating file selection tree...", "Cancel", 0, total_instances, self)
            progress.setWindowTitle("Building File Tree")
            progress.setMinimumDuration(0)
            progress.setValue(0)
            progress.show()
            QApplication.processEvents()
        
        # Optimize tree population with batch updates and progress feedback
        self.tree_widget.setUpdatesEnabled(False)
        try:
            cancelled = self._populate_tree_widget_with_progress(hierarchy, progress)
            if cancelled:
                self.reject()
                return
        finally:
            self.tree_widget.setUpdatesEnabled(True)
            if progress:
                progress.close()
            
        # Expand tree selectively for better performance
        self._expand_tree_intelligently(hierarchy)
        
        logging.info(f"Populated tree with {len(hierarchy)} patients")
    
    def _convert_hierarchy_data(self, hierarchy_data):
        """Convert TreeManager hierarchy format to selection dialog format"""
        logging.info("Converting hierarchy data for selection dialog")
        
        converted_hierarchy = {}
        
        for patient_label, patient_data in hierarchy_data.items():
            for study_label, study_data in patient_data.items():
                for series_label, series_data in study_data.items():
                    for instance_label, instance_data in series_data.items():
                        file_path = instance_data['filepath']
                        
                        # Convert to selection dialog format
                        converted_hierarchy.setdefault(patient_label, {}).setdefault(study_label, {}).setdefault(series_label, {})[instance_label] = file_path
        
        return converted_hierarchy
    
    def _build_hierarchy_from_loaded_files(self):
        """Build hierarchy from loaded files (fallback for backward compatibility)"""
        logging.info("Building hierarchy from loaded files")
        
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
        
        return hierarchy
    
    def _populate_tree_widget_with_progress(self, hierarchy, progress=None):
        """Populate tree widget with proper checkbox setup and progress feedback"""
        instances_processed = 0
        batch_size = 100  # Process in batches to yield UI control
        
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
                    
                    # Set file count immediately
                    series_item.setText(1, str(series_file_count))
                    
                    # Skip file size calculation for large series to avoid UI freezing
                    if series_file_count > 50:  # Large series - skip calculation
                        series_item.setText(2, f"~{series_file_count} files")
                    else:
                        # Only calculate size for small series
                        series_size = self._calculate_series_size_fast(instances)
                        if series_size > 0:
                            series_size_mb = series_size / (1024 * 1024)
                            series_item.setText(2, f"{series_size_mb:.1f}MB")
                        else:
                            series_item.setText(2, f"{series_file_count} files")
                    
                    # Process instances in batches to avoid UI freezing
                    instance_items = []
                    for instance, filepath in sorted(instances.items()):
                        instance_item = QTreeWidgetItem([instance, "1", ""])
                        
                        # CORRECT: Only ItemIsUserCheckable for leaf items
                        instance_item.setFlags(
                            instance_item.flags() | 
                            Qt.ItemFlag.ItemIsUserCheckable
                        )
                        instance_item.setCheckState(0, Qt.CheckState.Unchecked)
                        instance_item.setData(0, Qt.ItemDataRole.UserRole, filepath)  # Store file path
                        
                        instance_items.append(instance_item)
                        instances_processed += 1
                        
                        # Check for cancellation and yield UI control in batches
                        if instances_processed % batch_size == 0:
                            if progress:
                                if progress.wasCanceled():
                                    return True  # Cancelled
                                progress.setValue(instances_processed)
                                progress.setLabelText(f"Processing {patient}... ({instances_processed} items)")
                            
                            # Yield control to UI
                            QApplication.processEvents()
                    
                    # Add all instance items at once for better performance
                    for item in instance_items:
                        series_item.addChild(item)
                
                study_item.setText(1, str(study_file_count))
            
            patient_item.setText(1, str(patient_file_count))
            
            # Update progress after each patient
            if progress:
                progress.setValue(instances_processed)
                progress.setLabelText(f"Processed {patient}")
                QApplication.processEvents()
        
        if progress:
            progress.setValue(progress.maximum())
            progress.setLabelText("Tree population complete")
        
        return False  # Not cancelled
    
    def _populate_tree_widget_sync(self, hierarchy):
        """Synchronous tree population for use after async data processing"""
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
                    
                    # Set file count immediately
                    series_item.setText(1, str(series_file_count))
                    
                    # Skip file size calculation for fast population
                    series_item.setText(2, f"{series_file_count} files")
                    
                    # Add instance items
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
    
    def _populate_tree_widget(self, hierarchy):
        """Legacy method for backward compatibility"""
        return self._populate_tree_widget_with_progress(hierarchy, None)
    
    def _calculate_series_size_fast(self, instances):
        """Fast series size calculation with limited file checks"""
        if len(instances) > 50:
            return 0  # Skip calculation for large series
        
        total_size = 0
        checked_files = 0
        max_checks = 10  # Limit file system calls
        
        for filepath in instances.values():
            if checked_files >= max_checks:
                break
            try:
                if os.path.exists(filepath):
                    total_size += os.path.getsize(filepath)
                    checked_files += 1
            except OSError:
                # Skip files that can't be accessed
                continue
        
        # Estimate total size based on sample
        if checked_files > 0 and len(instances) > checked_files:
            avg_size = total_size / checked_files
            total_size = avg_size * len(instances)
        
        return total_size
    
    def _calculate_series_size(self, instances):
        """Calculate series size with error handling (legacy method)"""
        total_size = 0
        for filepath in instances.values():
            try:
                if os.path.exists(filepath):
                    total_size += os.path.getsize(filepath)
            except OSError:
                # Skip files that can't be accessed
                continue
        return total_size
    
    def _expand_tree_intelligently(self, hierarchy):
        """Expand tree intelligently based on size to improve performance"""
        total_patients = len(hierarchy)
        
        # If small dataset, expand all
        if total_patients <= 3:
            self.tree_widget.expandAll()
            return
        
        # For larger datasets, expand only patient level initially
        for i in range(self.tree_widget.topLevelItemCount()):
            patient_item = self.tree_widget.topLevelItem(i)
            patient_item.setExpanded(True)
            
            # Only expand studies if there are few of them
            if patient_item.childCount() <= 3:
                for j in range(patient_item.childCount()):
                    study_item = patient_item.child(j)
                    study_item.setExpanded(True)
                    
                    # Only expand series if there are very few
                    if study_item.childCount() <= 2:
                        for k in range(study_item.childCount()):
                            series_item = study_item.child(k)
                            series_item.setExpanded(True)
    
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
    
    def closeEvent(self, event):
        """Handle dialog close event"""
        # Cancel background worker if still running
        if self.tree_populator and self.tree_populator.isRunning():
            logging.info("Cancelling background tree population worker")
            self.tree_populator.cancel()
            self.tree_populator.wait(3000)  # Wait up to 3 seconds
            if self.tree_populator.isRunning():
                self.tree_populator.terminate()
                self.tree_populator.wait()
        
        super().closeEvent(event)
    
    def reject(self):
        """Handle dialog rejection (Cancel button)"""
        # Cancel background worker if still running
        if self.tree_populator and self.tree_populator.isRunning():
            logging.info("Cancelling background tree population worker on reject")
            self.tree_populator.cancel()
        
        super().reject()