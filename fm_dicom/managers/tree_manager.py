"""
Tree management manager for MainWindow.

This manager handles all tree-related operations including population,
selection handling, and hierarchy management.
"""

import os
import logging
import pydicom
from PyQt6.QtWidgets import QTreeWidgetItem, QProgressDialog, QApplication
from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtGui import QIcon

from fm_dicom.widgets.focus_aware import FocusAwareMessageBox


class TreeManager(QObject):
    """Manager class for tree operations"""
    
    # Signals
    selection_changed = pyqtSignal(list)  # Emitted when tree selection changes
    tree_populated = pyqtSignal(int)      # Emitted when tree is populated (file count)
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.tree = main_window.tree
        self.file_metadata = {}
        self.loaded_files = []
        
        # Setup icons
        self._setup_icons()
        
        # Connect tree signals
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
    
    def _setup_icons(self):
        """Setup icons for tree items"""
        style = self.main_window.style()
        self.patient_icon = style.standardIcon(style.StandardPixmap.SP_ComputerIcon)
        self.study_icon = style.standardIcon(style.StandardPixmap.SP_DirIcon)
        self.series_icon = style.standardIcon(style.StandardPixmap.SP_FileDialogDetailedView)
    
    def populate_tree(self, files):
        """Populate tree with DICOM file hierarchy"""
        logging.info(f"Starting tree population with {len(files)} files")
        self.tree.clear()
        self.file_metadata = {}
        self.loaded_files = files
        
        hierarchy = self._build_hierarchy(files)
        if hierarchy is None:  # Cancelled
            return
        
        # Populate tree widget
        self._build_tree_structure(hierarchy)
        
        # Update status
        total_files = len(files)
        self.tree_populated.emit(total_files)
        
        logging.info(f"Tree populated with {total_files} files")
    
    def refresh_tree(self):
        """Refresh the tree with current loaded files, showing progress"""
        if not self.loaded_files:
            return
            
        # Show progress dialog
        progress = QProgressDialog("Refreshing tree...", "Cancel", 0, 100, self.main_window)
        progress.setWindowTitle("Refreshing File Tree")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()
        
        try:
            # Clear current tree
            progress.setValue(10)
            progress.setLabelText("Clearing current tree...")
            QApplication.processEvents()
            
            self.tree.clear()
            self.file_metadata = {}
            
            # Rebuild hierarchy - force re-reading from disk to get updated data
            progress.setValue(30)
            progress.setLabelText("Re-reading DICOM files from disk...")
            QApplication.processEvents()
            
            # Extract file paths and force re-reading from disk
            file_paths = []
            for file_info in self.loaded_files:
                if isinstance(file_info, tuple):
                    file_paths.append(file_info[0])  # Extract path from (path, dataset) tuple
                else:
                    file_paths.append(file_info)  # Already just a path
            
            logging.info(f"Tree refresh: Re-reading {len(file_paths)} files from disk")
            if file_paths:
                logging.debug(f"First file path: {file_paths[0]}")
            
            # Force fresh read from disk by passing just paths (not cached datasets)
            hierarchy = self._build_hierarchy(file_paths, progress, 30, 80)
            
            if progress.wasCanceled():
                return
                
            # Update loaded_files with fresh data (extract from hierarchy)
            progress.setValue(75)
            progress.setLabelText("Updating file cache...")
            QApplication.processEvents()
            
            fresh_loaded_files = []
            for patient_data in hierarchy.values():
                for study_data in patient_data.values():
                    for series_data in study_data.values():
                        for instance_data in series_data.values():
                            filepath = instance_data['filepath']
                            dataset = instance_data['dataset']
                            fresh_loaded_files.append((filepath, dataset))
            
            self.loaded_files = fresh_loaded_files
                
            # Rebuild tree structure
            progress.setValue(80)
            progress.setLabelText("Building tree structure...")
            QApplication.processEvents()
            
            self._build_tree_structure(hierarchy)
            
            progress.setValue(100)
            progress.setLabelText("Tree refresh complete")
            QApplication.processEvents()
            
            # Emit signal
            self.tree_populated.emit(len(self.loaded_files))
            
        finally:
            progress.close()
    
    def _build_hierarchy(self, files, progress_dialog=None, start_progress=0, end_progress=100):
        """Build hierarchy from file list with optional progress updates"""
        hierarchy = {}
        modalities = set()
        
        # Check if we need to read headers or if they're already loaded
        needs_header_reading = any(not isinstance(f, tuple) for f in files)
        logging.info(f"Headers already loaded: {not needs_header_reading}")
        
        if needs_header_reading and progress_dialog is None:
            # Progress dialog for loading headers
            progress = QProgressDialog("Loading DICOM headers...", "Cancel", 0, len(files), self.main_window)
            progress.setWindowTitle("Loading DICOM Files")
            progress.setMinimumDuration(0)
            progress.setValue(0)
        else:
            # Use provided progress dialog or no dialog
            progress = progress_dialog
        
        for idx, file_info in enumerate(files):
            if progress and progress.wasCanceled():
                logging.warning(f"Progress dialog cancelled at index {idx}")
                return None
            
            try:
                # Handle both (filepath, dataset) tuples and just filepaths
                if isinstance(file_info, tuple):
                    file_path, ds = file_info
                else:
                    file_path = file_info
                    ds = pydicom.dcmread(file_path, stop_before_pixels=True)
                
                # Extract hierarchy information
                patient_id = getattr(ds, "PatientID", "Unknown ID")
                patient_name = getattr(ds, "PatientName", "Unknown Name")
                patient_label = f"{patient_name} ({patient_id})"
                
                study_uid = getattr(ds, "StudyInstanceUID", "Unknown StudyUID")
                study_desc = getattr(ds, "StudyDescription", "No Study Description")
                study_label = f"{study_desc} [{study_uid}]"
                
                series_uid = getattr(ds, "SeriesInstanceUID", "Unknown SeriesUID")
                series_desc = getattr(ds, "SeriesDescription", "No Series Description")
                series_label = f"{series_desc} [{series_uid}]"
                
                # Debug logging for first few files
                if idx < 3:
                    logging.debug(f"File {idx}: Patient={patient_label}, Study={study_label}, Series={series_label}")
                
                instance_number = getattr(ds, "InstanceNumber", None)
                sop_uid = getattr(ds, "SOPInstanceUID", os.path.basename(file_path))
                
                # Create instance label with sorting info
                if instance_number is not None:
                    instance_label = f"Instance {instance_number} [{sop_uid}]"
                    try:
                        instance_sort_key = int(instance_number)
                    except (ValueError, TypeError):
                        instance_sort_key = 999999
                else:
                    instance_label = f"{os.path.basename(file_path)} [{sop_uid}]"
                    instance_sort_key = 999999
                
                modality = getattr(ds, "Modality", None)
                if modality:
                    modalities.add(str(modality))
                
                # Store metadata
                self.file_metadata[file_path] = (
                    patient_label, study_label, series_label, instance_label
                )
                
                # Build hierarchy with sort information
                hierarchy.setdefault(patient_label, {}).setdefault(
                    study_label, {}
                ).setdefault(series_label, {})[instance_label] = {
                    'filepath': file_path,
                    'sort_key': instance_sort_key,
                    'instance_number': instance_number,
                    'dataset': ds
                }
                
            except Exception as e:
                logging.warning(f"Could not process file {file_path}: {e}")
                continue
            
            # Update progress
            if progress:
                if progress_dialog is None:  # Own progress dialog
                    progress.setValue(idx + 1)
                else:  # Using parent's progress dialog with range
                    current_progress = start_progress + int((idx + 1) / len(files) * (end_progress - start_progress))
                    progress.setValue(current_progress)
                    
            # Update UI periodically - less frequent for large datasets
            update_frequency = max(1, len(files) // 100)  # Update every 1% for large sets
            if idx % update_frequency == 0:
                QApplication.processEvents()
        
        # Check for cancellation before closing progress dialog
        was_cancelled = False
        if progress and progress_dialog is None:  # Only close if we created it
            was_cancelled = progress.wasCanceled()
            progress.close()
            if was_cancelled:
                logging.info(f"Tree population was cancelled after processing {len(files)} files")
                return None
        
        return hierarchy
    
    def _build_tree_structure(self, hierarchy):
        """Build the actual tree structure from hierarchy data"""
        logging.debug(f"Building tree structure with {len(hierarchy)} patients")
        
        # Calculate statistics
        total_patients = len(hierarchy)
        total_studies = 0
        total_series = 0
        total_instances = 0
        total_size_bytes = 0
        
        for patient, studies in hierarchy.items():
            logging.debug(f"Patient: {patient} has {len(studies)} studies")
            patient_item = QTreeWidgetItem([patient, "", "", ""])
            patient_item.setIcon(0, self.patient_icon)
            patient_item.setData(0, Qt.ItemDataRole.UserRole, None)  # No file for patient
            self.tree.addTopLevelItem(patient_item)
            
            total_studies += len(studies)
            
            for study, series_dict in studies.items():
                logging.debug(f"  Study: {study} has {len(series_dict)} series")
                study_item = QTreeWidgetItem([patient, study, "", ""])
                study_item.setIcon(1, self.study_icon)
                study_item.setData(0, Qt.ItemDataRole.UserRole, None)  # No file for study
                patient_item.addChild(study_item)
                
                total_series += len(series_dict)
                
                for series, instances in series_dict.items():
                    logging.debug(f"    Series: {series} has {len(instances)} instances")
                    series_item = QTreeWidgetItem([patient, study, series, ""])
                    series_item.setIcon(2, self.series_icon)
                    series_item.setData(0, Qt.ItemDataRole.UserRole, None)  # No file for series
                    study_item.addChild(series_item)
                    
                    total_instances += len(instances)
                    
                    # Sort instances by instance number
                    sorted_instances = sorted(
                        instances.items(),
                        key=lambda x: x[1]['sort_key']
                    )
                    
                    for instance_label, instance_data in sorted_instances:
                        instance_item = QTreeWidgetItem([patient, study, series, instance_label])
                        instance_item.setData(0, Qt.ItemDataRole.UserRole, instance_data['filepath'])
                        series_item.addChild(instance_item)
                        
                        # Calculate file size
                        try:
                            file_size = os.path.getsize(instance_data['filepath'])
                            total_size_bytes += file_size
                        except (OSError, KeyError):
                            pass  # Skip if file not accessible
        
        # Expand first level by default
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setExpanded(True)
        
        # Update statistics display
        total_size_gb = total_size_bytes / (1024**3)  # Convert to GB
        self.main_window.update_stats_display(
            patients=total_patients,
            studies=total_studies, 
            series=total_series,
            instances=total_instances
        )
        self.main_window.update_file_info_display(
            total_files=total_instances,
            selected_count=0,
            current_file=None
        )
        
        # Update summary text  
        if hasattr(self.main_window, 'summary_label'):
            if total_instances > 0:
                size_str = f"{total_size_gb:.2f} GB" if total_size_gb >= 0.01 else f"{total_size_bytes / (1024**2):.1f} MB"
                self.main_window.summary_label.setText(f"{total_instances} DICOM files loaded ({size_str})")
            else:
                self.main_window.summary_label.setText("No DICOM files loaded")
    
    def _on_selection_changed(self):
        """Handle tree selection changes"""
        selected_items = self.tree.selectedItems()
        file_paths = []
        
        for item in selected_items:
            paths = self._collect_instance_filepaths(item)
            file_paths.extend(paths)
        
        # Remove duplicates while preserving order
        unique_paths = []
        seen = set()
        for path in file_paths:
            if path not in seen:
                unique_paths.append(path)
                seen.add(path)
        
        # Update file info display with selection count
        current_file = unique_paths[0] if unique_paths else None
        self.main_window.update_file_info_display(
            total_files=len(self.loaded_files),
            selected_count=len(unique_paths),
            current_file=current_file
        )
        
        self.selection_changed.emit(unique_paths)
    
    def _collect_instance_filepaths(self, item):
        """Recursively collect file paths from a tree item and its children"""
        filepaths = []
        
        # Check if this item has a file path
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        if file_path:
            filepaths.append(file_path)
        
        # Recursively check children
        for i in range(item.childCount()):
            child_paths = self._collect_instance_filepaths(item.child(i))
            filepaths.extend(child_paths)
        
        return filepaths
    
    def filter_tree_items(self, text):
        """Filter tree items based on search text"""
        text = text.lower()
        
        def match_item(item):
            # Check if any column text matches
            for col in range(item.columnCount()):
                if text in item.text(col).lower():
                    return True
            
            # Check children
            for i in range(item.childCount()):
                if match_item(item.child(i)):
                    item.setExpanded(True)
                    return True
            
            return False
        
        def filter_recursive(item):
            is_visible = match_item(item) if text else True
            item.setHidden(not is_visible)
            
            if is_visible or not text:
                for i in range(item.childCount()):
                    filter_recursive(item.child(i))
        
        # Apply filter to all top-level items
        for i in range(self.tree.topLevelItemCount()):
            filter_recursive(self.tree.topLevelItem(i))
    
    def get_selected_files(self):
        """Get list of currently selected file paths"""
        selected_items = self.tree.selectedItems()
        file_paths = []
        
        for item in selected_items:
            paths = self._collect_instance_filepaths(item)
            file_paths.extend(paths)
        
        return list(set(file_paths))  # Remove duplicates
    
    def delete_selected_items(self):
        """Delete selected items from tree and loaded files"""
        selected_items = self.tree.selectedItems()
        if not selected_items:
            FocusAwareMessageBox.warning(
                self.main_window,
                "No Selection",
                "Please select items to delete."
            )
            return
        
        # Confirm deletion
        file_count = 0
        for item in selected_items:
            file_count += len(self._collect_instance_filepaths(item))
        
        reply = FocusAwareMessageBox.question(
            self.main_window,
            "Confirm Deletion",
            f"Delete {len(selected_items)} selected items ({file_count} files)?",
            FocusAwareMessageBox.StandardButton.Yes | FocusAwareMessageBox.StandardButton.No,
            FocusAwareMessageBox.StandardButton.No
        )
        
        if reply != FocusAwareMessageBox.StandardButton.Yes:
            return
        
        # Collect files to remove
        files_to_remove = set()
        for item in selected_items:
            files_to_remove.update(self._collect_instance_filepaths(item))
        
        # Remove from loaded files
        self.loaded_files = [
            f for f in self.loaded_files 
            if (f[0] if isinstance(f, tuple) else f) not in files_to_remove
        ]
        
        # Remove from metadata
        for file_path in files_to_remove:
            self.file_metadata.pop(file_path, None)
        
        # Remove items from tree
        for item in selected_items:
            parent = item.parent()
            if parent:
                parent.removeChild(item)
            else:
                index = self.tree.indexOfTopLevelItem(item)
                self.tree.takeTopLevelItem(index)
        
        # Update counts and emit signal
        self.tree_populated.emit(len(self.loaded_files))
        self._on_selection_changed()  # Update selection
        
        logging.info(f"Deleted {len(files_to_remove)} files from tree")
    
    def clear_tree(self):
        """Clear all tree contents"""
        self.tree.clear()
        self.file_metadata.clear()
        self.loaded_files.clear()
        self.tree_populated.emit(0)
        
    def expand_all(self):
        """Expand all tree items"""
        self.tree.expandAll()
    
    def collapse_all(self):
        """Collapse all tree items"""
        self.tree.collapseAll()
    
    def select_all(self):
        """Select all tree items"""
        self.tree.selectAll()
    
    def clear_selection(self):
        """Clear tree selection"""
        self.tree.clearSelection()
    
    def get_file_metadata(self, file_path):
        """Get metadata for a specific file"""
        return self.file_metadata.get(file_path)
    
    def get_loaded_files(self):
        """Get list of all loaded files"""
        return self.loaded_files.copy()
    
    def get_file_count(self):
        """Get total number of loaded files"""
        return len(self.loaded_files)