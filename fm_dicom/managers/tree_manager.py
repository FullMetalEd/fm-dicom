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

from fm_dicom.widgets.focus_aware import FocusAwareMessageBox, FocusAwareProgressDialog
# Temporarily commented out for testing - from fm_dicom.utils.threaded_processor import ThreadedDicomProcessor, DicomProcessingResult, FastDicomScanner


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
        self.hierarchy = {}  # Store hierarchy data for performance

        # Performance optimization settings from config
        perf_config = main_window.config.get('performance', {})
        self.use_threaded_processing = perf_config.get('use_threaded_processing', True)
        self.thread_threshold = perf_config.get('thread_threshold', 100)
        self.max_workers = perf_config.get('max_worker_threads', 4)
        self.batch_size = perf_config.get('batch_size', 50)
        self.progress_frequency = perf_config.get('progress_update_frequency', 20)

        # Threaded processor
        self.threaded_processor = None
        self.progressive_hierarchy = {}  # Build hierarchy progressively
        self.processing_stats = {'processed': 0, 'total': 0, 'errors': 0}

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
        """Populate tree with DICOM file hierarchy using optimized processing"""
        logging.info(f"Starting tree population with {len(files)} files")
        self.tree.clear()
        self.file_metadata = {}
        self.loaded_files = files

        # Extract file paths from mixed input formats
        file_paths = self._extract_file_paths(files)

        # Temporarily disable threaded processing due to import issue
        logging.info(f"Using sequential processing for {len(file_paths)} files")
        # Use original method for all datasets
        hierarchy = self._build_hierarchy(files)
        if hierarchy is None:  # Cancelled
            return

        # Store hierarchy for performance optimization
        self.hierarchy = hierarchy

        # Populate tree widget
        self._build_tree_structure(hierarchy)

        # Update status
        total_files = len(files)
        self.tree_populated.emit(total_files)

        logging.info(f"Tree populated with {total_files} files")

    def _extract_file_paths(self, files):
        """Extract file paths from mixed input formats (paths, tuples)"""
        file_paths = []
        for file_info in files:
            if isinstance(file_info, tuple):
                file_paths.append(file_info[0])  # Extract path from (path, dataset) tuple
            else:
                file_paths.append(file_info)  # Already just a path
        return file_paths

    def _populate_tree_threaded(self, file_paths):
        """Populate tree using threaded processing for large datasets"""
        # Initialize processing state
        self.progressive_hierarchy = {}
        self.processing_stats = {'processed': 0, 'total': len(file_paths), 'errors': 0}

        # Pre-filter files to remove obvious non-DICOM files (temporarily disabled)
        # filtered_paths = FastDicomScanner.filter_dicom_files(file_paths)
        filtered_paths = file_paths  # Use all files for now
        # if len(filtered_paths) != len(file_paths):
        #     logging.info(f"Pre-filtered {len(file_paths)} files to {len(filtered_paths)} potential DICOM files")

        # Create threaded processor (temporarily disabled)
        # self.threaded_processor = ThreadedDicomProcessor(
        #     max_workers=self.max_workers,
        #     batch_size=self.batch_size
        # )

        # Connect signals for progressive updates (temporarily disabled)
        # self.threaded_processor.progress_updated.connect(self._on_threaded_progress)
        # self.threaded_processor.file_processed.connect(self._on_file_processed)
        # self.threaded_processor.batch_completed.connect(self._on_batch_completed)
        # self.threaded_processor.processing_finished.connect(self._on_processing_finished)
        # self.threaded_processor.processing_error.connect(self._on_processing_error)

        # Show progress dialog (temporarily disabled)
        # self.progress_dialog = FocusAwareProgressDialog(
        #     f"Processing {len(filtered_paths)} DICOM files...",
        #     "Cancel",
        #     0,
        #     len(filtered_paths),
        #     self.main_window
        # )
        # self.progress_dialog.setWindowTitle("Loading DICOM Files")
        # self.progress_dialog.setMinimumDuration(0)
        # self.progress_dialog.canceled.connect(self.threaded_processor.cancel_processing)
        # self.progress_dialog.show()

        # Start threaded processing (temporarily disabled)
        # self.threaded_processor.process_files(
        #     filtered_paths,
        #     read_pixels=False,  # Headers only for hierarchy building
        #     required_tags=None  # Use defaults
        # )

    def _on_threaded_progress(self, current, total, current_file):
        """Handle progress updates from threaded processor"""
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.setValue(current)
            self.progress_dialog.setLabelText(f"Processing: {current_file}\n({current}/{total} files)")
            QApplication.processEvents()

    def _on_file_processed(self, result):
        """Handle single file processing completion"""
        if result.success:
            # Add to progressive hierarchy
            self._add_to_progressive_hierarchy(result)
        else:
            self.processing_stats['errors'] += 1
            if self.processing_stats['errors'] <= 5:  # Log first few errors
                logging.warning(f"Failed to process {result.file_path}: {result.error}")

    def _on_batch_completed(self, batch_results):
        """Handle batch completion - update tree structure progressively"""
        # Update tree with current hierarchy state
        if self.progressive_hierarchy:
            # Build tree incrementally - only add new nodes
            self._update_tree_structure_progressive(self.progressive_hierarchy)

    def _on_processing_finished(self):
        """Handle completion of all threaded processing"""
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.close()

        # Final hierarchy build and tree update
        self.hierarchy = self.progressive_hierarchy
        self._build_tree_structure(self.hierarchy)

        # Convert file paths back to loaded_files format
        self.loaded_files = []
        for patient_data in self.hierarchy.values():
            for study_data in patient_data.values():
                for series_data in study_data.values():
                    for instance_data in series_data.values():
                        filepath = instance_data['filepath']
                        dataset = instance_data.get('dataset')
                        if dataset:
                            self.loaded_files.append((filepath, dataset))
                        else:
                            self.loaded_files.append(filepath)

        # Update status
        total_files = len(self.loaded_files)
        errors = self.processing_stats['errors']
        self.tree_populated.emit(total_files)

        logging.info(f"Threaded tree population completed: {total_files} files, {errors} errors")

    def _on_processing_error(self, error_message):
        """Handle processing error"""
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.close()

        FocusAwareMessageBox.critical(
            self.main_window,
            "Processing Error",
            f"Error during threaded DICOM processing:\n\n{error_message}"
        )

    def _add_to_progressive_hierarchy(self, result):
        """Add processing result to progressive hierarchy"""
        if not result.success or not result.metadata:
            return

        metadata = result.metadata
        dataset = result.dataset

        # Extract hierarchy information from metadata
        patient_id = metadata.get('PatientID', 'Unknown ID')
        patient_name = metadata.get('PatientName', 'Unknown Name')
        patient_label = f"{patient_name} ({patient_id})"

        study_uid = metadata.get('StudyInstanceUID', 'Unknown StudyUID')
        study_desc = metadata.get('StudyDescription', 'No Study Description')
        study_label = f"{study_desc} [{study_uid}]"

        series_uid = metadata.get('SeriesInstanceUID', 'Unknown SeriesUID')
        series_desc = metadata.get('SeriesDescription', 'No Series Description')
        series_label = f"{series_desc} [{series_uid}]"

        # Create instance label
        instance_number = metadata.get('InstanceNumber')
        sop_uid = metadata.get('SOPInstanceUID', os.path.basename(result.file_path))

        if instance_number:
            instance_label = f"Instance {instance_number} [{sop_uid}]"
            try:
                instance_sort_key = int(instance_number)
            except (ValueError, TypeError):
                instance_sort_key = 999999
        else:
            instance_label = f"{os.path.basename(result.file_path)} [{sop_uid}]"
            instance_sort_key = 999999

        # Store metadata for the UI
        self.file_metadata[result.file_path] = (
            patient_label, study_label, series_label, instance_label
        )

        # Build progressive hierarchy
        self.progressive_hierarchy.setdefault(patient_label, {}).setdefault(
            study_label, {}
        ).setdefault(series_label, {})[instance_label] = {
            'filepath': result.file_path,
            'sort_key': instance_sort_key,
            'instance_number': instance_number,
            'dataset': dataset
        }

    def _update_tree_structure_progressive(self, hierarchy):
        """Update tree structure progressively during processing"""
        # This method could implement progressive tree building
        # For now, we'll update the full tree periodically
        # In a future optimization, we could add only new nodes
        pass
    
    def refresh_tree(self):
        """Refresh the tree with current loaded files, showing progress"""
        if not self.loaded_files:
            return
            
        # Show progress dialog
        progress = FocusAwareProgressDialog("Refreshing tree...", "Cancel", 0, 100, self.main_window)
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
                
            # Store hierarchy for performance optimization
            self.hierarchy = hierarchy
            
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
            progress = FocusAwareProgressDialog("Loading DICOM headers...", "Cancel", 0, len(files), self.main_window)
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
                study_item.setIcon(0, self.study_icon)
                study_item.setData(0, Qt.ItemDataRole.UserRole, None)  # No file for study
                patient_item.addChild(study_item)
                
                total_series += len(series_dict)
                
                for series, instances in series_dict.items():
                    logging.debug(f"    Series: {series} has {len(instances)} instances")
                    series_item = QTreeWidgetItem([patient, study, series, ""])
                    series_item.setIcon(0, self.series_icon)
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
            instances=total_instances,
            total_size_gb=total_size_gb
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