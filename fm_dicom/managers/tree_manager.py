"""
Tree management manager for MainWindow.

This manager handles all tree-related operations including population,
selection handling, and hierarchy management.
"""

import os
import logging
import pydicom
from PyQt6.QtWidgets import QTreeWidgetItem, QProgressDialog, QApplication, QMenu
from PyQt6.QtCore import QObject, pyqtSignal, Qt, QPoint
from PyQt6.QtGui import QIcon, QAction

from fm_dicom.widgets.focus_aware import FocusAwareMessageBox, FocusAwareProgressDialog
from fm_dicom.utils.threaded_processor import ThreadedDicomProcessor, DicomProcessingResult, FastDicomScanner
from fm_dicom.managers.duplication_manager import DuplicationManager, UIDConfiguration
from fm_dicom.dialogs.uid_configuration_dialog import UIDConfigurationDialog

TREE_PATH_ROLE = Qt.ItemDataRole.UserRole + 1


class TreeManager(QObject):
    """Manager class for tree operations"""
    
    # Signals
    selection_changed = pyqtSignal(list)  # Emitted when tree selection changes
    tree_populated = pyqtSignal(int)      # Emitted when tree is populated (file count)
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.tree = main_window.tree
        self.file_metadata = {}  # Disk-based DICOM files
        self.memory_items = {}   # In-memory duplicated items (survive refresh)
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

        # Duplication manager
        self.duplication_manager = DuplicationManager(main_window)

        # Duplication progress tracking
        self.duplication_progress_dialog = None

        # Connect to duplication signals for progress indication
        self.duplication_manager.duplication_started.connect(self._on_duplication_started)
        self.duplication_manager.duplication_progress.connect(self._on_duplication_progress)
        self.duplication_manager.duplication_completed.connect(self._on_duplication_completed)
        self.duplication_manager.duplication_error.connect(self._on_duplication_error)

        # Setup icons
        self._setup_icons()

        # Context menu integration is handled by main_window

        # Connect tree signals
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)

    def _on_selection_changed(self):
        """Handle tree selection change - load DICOM data for selected item"""
        try:
            selected_items = self.tree.selectedItems()

            # Emit signal with file paths for main window to handle
            selected_files = []
            for item in selected_items:
                # Get file path from item data
                file_path = item.data(0, Qt.ItemDataRole.UserRole)
                if file_path:
                    selected_files.append(file_path)

            # Emit the selection changed signal
            self.selection_changed.emit(selected_files)

        except Exception as e:
            logging.error(f"Error in tree selection changed: {e}", exc_info=True)

    def _setup_icons(self):
        """Setup icons for tree items"""
        style = self.main_window.style()
        self.patient_icon = style.standardIcon(style.StandardPixmap.SP_ComputerIcon)
        self.study_icon = style.standardIcon(style.StandardPixmap.SP_DirIcon)
        self.series_icon = style.standardIcon(style.StandardPixmap.SP_FileDialogDetailedView)

    def get_expanded_paths(self):
        """Return list of tree paths that are currently expanded"""
        expanded = []

        def visit(item):
            if item is None:
                return
            path = item.data(0, TREE_PATH_ROLE)
            if path and item.isExpanded():
                expanded.append(tuple(path))
            for i in range(item.childCount()):
                visit(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(i))
        return expanded

    def restore_expanded_paths(self, paths):
        """Re-expand tree nodes matching the provided paths"""
        if not paths:
            return

        targets = {tuple(p) for p in paths if p}
        if not targets:
            return

        self.tree.collapseAll()

        def visit(item):
            if item is None:
                return
            path = item.data(0, TREE_PATH_ROLE)
            if path in targets:
                item.setExpanded(True)
                parent = item.parent()
                while parent:
                    parent.setExpanded(True)
                    parent = parent.parent()
            for i in range(item.childCount()):
                visit(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(i))

    def get_primary_selected_path(self):
        """Return the path tuple for the first selected tree item"""
        selected_items = self.tree.selectedItems()
        for item in selected_items:
            path = item.data(0, TREE_PATH_ROLE)
            if path:
                return tuple(path)
        return None

    def select_item_by_file(self, file_path):
        """Select the tree item corresponding to a specific file path"""
        if not file_path:
            return False

        target = self._find_item_by(lambda item: item.data(0, Qt.ItemDataRole.UserRole) == file_path)
        if target:
            self._focus_on_item(target)
            return True
        return False

    def select_item_by_path(self, path_tuple):
        """Select the tree item matching the provided path tuple"""
        if not path_tuple:
            return False

        target = self._find_item_by(lambda item: item.data(0, TREE_PATH_ROLE) == tuple(path_tuple))
        if target:
            self._focus_on_item(target)
            return True
        return False

    def _find_item_by(self, predicate):
        """Find the first tree item that satisfies the predicate"""
        def visit(item):
            if item is None:
                return None
            try:
                if predicate(item):
                    return item
            except Exception:
                pass
            for i in range(item.childCount()):
                found = visit(item.child(i))
                if found:
                    return found
            return None

        for i in range(self.tree.topLevelItemCount()):
            found_item = visit(self.tree.topLevelItem(i))
            if found_item:
                return found_item
        return None

    def _focus_on_item(self, item):
        """Ensure the specified tree item is selected and visible"""
        if item is None:
            return

        parent = item.parent()
        while parent:
            parent.setExpanded(True)
            parent = parent.parent()

        self.tree.clearSelection()
        self.tree.setCurrentItem(item)
        item.setSelected(True)
        self.tree.scrollToItem(item)

    # Context menu integration handled by main_window's show_tree_context_menu
    
    def populate_tree(self, files, append=False):
        """Populate tree with DICOM file hierarchy using optimized processing"""
        if append:
            logging.info(f"Appending {len(files)} files to existing tree ({len(self.loaded_files)} already loaded)")
        else:
            logging.info(f"Starting tree population with {len(files)} files")

        if not append:
            self.tree.clear()
            self.file_metadata = {}
            self.loaded_files = files
        else:
            # Append mode - extend existing data instead of replacing
            self.loaded_files.extend(files)

        # Extract file paths from mixed input formats
        file_paths = self._extract_file_paths(files)

        # Decide whether to use threaded processing based on config and dataset size
        if (self.use_threaded_processing and
            len(file_paths) > self.thread_threshold):
            logging.info(f"Using threaded processing for {len(file_paths)} files (threshold: {self.thread_threshold})")
            self._append_mode = append  # Store for threaded processing completion
            self._populate_tree_threaded(file_paths)
        else:
            logging.info(f"Using sequential processing for {len(file_paths)} files")
            # Use original method for smaller datasets or when threading disabled
            new_hierarchy = self._build_hierarchy(files)
            if new_hierarchy is None:  # Cancelled
                return

            if append and self.hierarchy:
                # Merge new hierarchy with existing one
                self.hierarchy = self._merge_hierarchies(self.hierarchy, new_hierarchy)
            else:
                # Store hierarchy for performance optimization
                self.hierarchy = new_hierarchy

            # Populate tree widget (full rebuild for now - could optimize later)
            self._build_tree_structure(self.hierarchy)

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

        # Pre-filter files to remove obvious non-DICOM files
        filtered_paths = FastDicomScanner.filter_dicom_files(file_paths)
        if len(filtered_paths) != len(file_paths):
            logging.info(f"Pre-filtered {len(file_paths)} files to {len(filtered_paths)} potential DICOM files")

        # Create threaded processor
        self.threaded_processor = ThreadedDicomProcessor(
            max_workers=self.max_workers,
            batch_size=self.batch_size
        )

        # Connect signals for progressive updates
        self.threaded_processor.progress_updated.connect(self._on_threaded_progress)
        self.threaded_processor.file_processed.connect(self._on_file_processed)
        self.threaded_processor.batch_completed.connect(self._on_batch_completed)
        self.threaded_processor.processing_finished.connect(self._on_processing_finished)
        self.threaded_processor.processing_error.connect(self._on_processing_error)

        # Show progress dialog
        self.progress_dialog = FocusAwareProgressDialog(
            f"Processing {len(filtered_paths)} DICOM files...",
            "Cancel",
            0,
            len(filtered_paths),
            self.main_window
        )
        self.progress_dialog.setWindowTitle("Loading DICOM Files")
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.canceled.connect(self.threaded_processor.cancel_processing)
        self.progress_dialog.show()

        # Start threaded processing
        self.threaded_processor.process_files(
            filtered_paths,
            read_pixels=False,  # Headers only for hierarchy building
            required_tags=None  # Use defaults
        )

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
        if hasattr(self, '_append_mode') and self._append_mode and self.hierarchy:
            # Merge progressive hierarchy with existing hierarchy
            self.hierarchy = self._merge_hierarchies(self.hierarchy, self.progressive_hierarchy)
        else:
            self.hierarchy = self.progressive_hierarchy
        self._build_tree_structure(self.hierarchy)

        # Convert file paths back to loaded_files format
        if not (hasattr(self, '_append_mode') and self._append_mode):
            # Replace mode - rebuild loaded_files from hierarchy
            self.loaded_files = []

        # Extract files from current hierarchy and add to loaded_files
        new_files = []
        for patient_data in self.hierarchy.values():
            for study_data in patient_data.values():
                for series_data in study_data.values():
                    for instance_data in series_data.values():
                        filepath = instance_data['filepath']
                        dataset = instance_data.get('dataset')
                        if dataset:
                            new_files.append((filepath, dataset))
                        else:
                            new_files.append(filepath)

        if hasattr(self, '_append_mode') and self._append_mode:
            # Append mode - extend loaded_files with new files only
            existing_paths = {f[0] if isinstance(f, tuple) else f for f in self.loaded_files}
            for new_file in new_files:
                new_path = new_file[0] if isinstance(new_file, tuple) else new_file
                if new_path not in existing_paths:
                    self.loaded_files.append(new_file)
        else:
            # Replace mode
            self.loaded_files = new_files

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

        if hasattr(self.main_window, "prepare_for_tree_refresh"):
            self.main_window.prepare_for_tree_refresh()
            
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
            self.file_metadata = {}  # Clear disk-based items only
            # Keep memory_items - these are duplicated items that should survive refresh
            
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
            
            # Combine disk files and memory items for hierarchy building
            combined_files = []

            # Add disk files (force fresh read from disk)
            combined_files.extend(file_paths)

            # Add memory items (duplicated items that should be preserved)
            for memory_path, memory_dataset in self.memory_items.items():
                combined_files.append((memory_path, memory_dataset))

            logging.info(f"Building hierarchy with {len(file_paths)} disk files and {len(self.memory_items)} memory items")
            hierarchy = self._build_hierarchy(combined_files, progress, 30, 80)
            
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
                    # Check memory items first (duplicated items) before reading from disk
                    if file_path in self.memory_items:
                        ds = self.memory_items[file_path]
                        logging.debug(f"Loading duplicated item from memory: {file_path}")
                    else:
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
                
                # Debug logging for first few files and memory items
                if idx < 3 or file_path in self.memory_items:
                    item_type = "MEMORY" if file_path in self.memory_items else "DISK"
                    logging.debug(f"File {idx} ({item_type}): Patient={patient_label}, Study={study_label}, Series={series_label}")
                    if file_path in self.memory_items:
                        logging.debug(f"  Memory item path: {file_path}")
                        logging.debug(f"  Study UID: {study_uid}")
                        logging.debug(f"  Series UID: {series_uid}")
                
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

    def _merge_hierarchies(self, existing_hierarchy, new_hierarchy):
        """Merge a new hierarchy into an existing hierarchy"""
        logging.info(f"Merging hierarchies: {len(existing_hierarchy)} + {len(new_hierarchy)} patients")

        # Deep copy existing hierarchy to avoid modifying original
        merged_hierarchy = existing_hierarchy.copy()

        for patient_label, new_studies in new_hierarchy.items():
            if patient_label not in merged_hierarchy:
                # New patient - add directly
                merged_hierarchy[patient_label] = new_studies
                logging.debug(f"Added new patient: {patient_label}")
            else:
                # Existing patient - merge studies
                existing_studies = merged_hierarchy[patient_label]
                for study_label, new_series in new_studies.items():
                    if study_label not in existing_studies:
                        # New study - add directly
                        existing_studies[study_label] = new_series
                        logging.debug(f"Added new study: {study_label}")
                    else:
                        # Existing study - merge series
                        existing_series = existing_studies[study_label]
                        for series_label, new_instances in new_series.items():
                            if series_label not in existing_series:
                                # New series - add directly
                                existing_series[series_label] = new_instances
                                logging.debug(f"Added new series: {series_label}")
                            else:
                                # Existing series - merge instances
                                existing_instances = existing_series[series_label]
                                for instance_label, instance_data in new_instances.items():
                                    if instance_label not in existing_instances:
                                        # New instance - add directly
                                        existing_instances[instance_label] = instance_data
                                        logging.debug(f"Added new instance: {instance_label}")
                                    else:
                                        # Duplicate instance - this could happen if same file loaded twice
                                        # For now, we'll keep the existing one and log a warning
                                        logging.warning(f"Duplicate instance found: {instance_label}")

        logging.info(f"Hierarchy merge complete: {len(merged_hierarchy)} total patients")
        return merged_hierarchy

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
            patient_item.setData(0, TREE_PATH_ROLE, (patient,))
            self.tree.addTopLevelItem(patient_item)
            
            total_studies += len(studies)
            
            for study, series_dict in studies.items():
                logging.debug(f"  Study: {study} has {len(series_dict)} series")
                study_item = QTreeWidgetItem([patient, study, "", ""])
                study_item.setIcon(0, self.study_icon)
                study_item.setData(0, Qt.ItemDataRole.UserRole, None)  # No file for study
                study_item.setData(0, TREE_PATH_ROLE, (patient, study))
                patient_item.addChild(study_item)
                
                total_series += len(series_dict)
                
                for series, instances in series_dict.items():
                    logging.debug(f"    Series: {series} has {len(instances)} instances")
                    series_item = QTreeWidgetItem([patient, study, series, ""])
                    series_item.setIcon(0, self.series_icon)
                    series_item.setData(0, Qt.ItemDataRole.UserRole, None)  # No file for series
                    series_item.setData(0, TREE_PATH_ROLE, (patient, study, series))
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
                        instance_item.setData(0, TREE_PATH_ROLE, (patient, study, series, instance_label))
                        series_item.addChild(instance_item)
                        
                        # Calculate file size (skip for virtual/memory items)
                        try:
                            filepath = instance_data['filepath']
                            # Only calculate size for files that exist on disk (not memory items)
                            if filepath not in self.memory_items:
                                file_size = os.path.getsize(filepath)
                                total_size_bytes += file_size
                        except (OSError, KeyError):
                            pass  # Skip if file not accessible
        
        # Expand first level on initial load only
        if not getattr(self.main_window, "_pending_ui_state", None):
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

    def _collect_selection_metadata(self, selected_items):
        """Collect hierarchical metadata and deduplicate instance paths."""
        instances = []
        seen = set()

        for item in selected_items:
            paths = self._collect_instance_filepaths(item)
            for path in paths:
                if path in seen:
                    continue
                seen.add(path)
                meta = self.file_metadata.get(path)
                patient_label = None
                study_label = None
                series_label = None
                instance_label = None
                if isinstance(meta, tuple):
                    patient_label, study_label, series_label, instance_label = meta
                instances.append({
                    "path": path,
                    "patient_label": patient_label,
                    "study_label": study_label,
                    "series_label": series_label,
                    "instance_label": instance_label,
                })

        return {
            "instances": instances,
            "seen_paths": seen,
        }
    
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
        
        # Remove from metadata (both disk and memory)
        for file_path in files_to_remove:
            self.file_metadata.pop(file_path, None)
            self.memory_items.pop(file_path, None)
        
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
        self.memory_items.clear()  # Also clear memory items
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
        """Get metadata for a specific file from either disk cache or memory items"""
        # First check memory items (duplicated items)
        if file_path in self.memory_items:
            return self.memory_items[file_path]

        # Then check disk-based file metadata
        return self.file_metadata.get(file_path)
    
    def get_loaded_files(self):
        """Get list of all loaded files"""
        return self.loaded_files.copy()
    
    def get_file_count(self):
        """Get total number of loaded files"""
        return len(self.loaded_files)

    # Duplication functionality

    def _determine_context_duplication_level(self, selected_items):
        """Determine the appropriate duplication level based on selected items"""
        if not selected_items:
            return None

        # Analyze the selection to determine the most appropriate level
        levels = set()
        for item in selected_items:
            level = self._get_item_level(item)
            if level:
                levels.add(level)
                logging.info(f"[CONTEXT DEBUG] Item '{item.text(0)}' detected as level: {level}")

        logging.info(f"[CONTEXT DEBUG] All detected levels: {levels}")

        # If mixed selection, return "mixed"
        if len(levels) > 1:
            result = "mixed"
        elif len(levels) == 1:
            result = list(levels)[0]
        else:
            result = "instance"  # Default

        logging.info(f"[CONTEXT DEBUG] Final duplication level determined: {result}")
        return result

    def _get_item_level(self, item):
        """Determine the hierarchy level of a tree item"""
        # Count the depth to determine level
        depth = 0
        parent = item.parent()
        while parent is not None:
            depth += 1
            parent = parent.parent()

        if depth == 0:
            result = "patient"
        elif depth == 1:
            result = "study"
        elif depth == 2:
            result = "series"
        else:
            result = "instance"

        logging.info(f"[DEPTH DEBUG] Item '{item.text(0)}' has depth {depth}, classified as: {result}")
        return result

    def _duplicate_selected_items(self, duplication_level):
        """Duplicate selected items with user configuration"""
        try:
            selected_items = self.tree.selectedItems()
            if not selected_items:
                FocusAwareMessageBox.warning(
                    self.main_window,
                    "No Selection",
                    "Please select items to duplicate."
                )
                return

            # Build structured selection (dedup + hierarchy metadata)
            selection = self._collect_selection_metadata(selected_items)
            if not selection["instances"]:
                FocusAwareMessageBox.warning(
                    self.main_window,
                    "No Files",
                    "Selected items don't contain any files to duplicate."
                )
                return

            # Show UID configuration dialog
            uid_config = UIDConfigurationDialog.get_uid_configuration(
                self.main_window, duplication_level
            )

            if uid_config is None:
                return  # User cancelled

            # Perform duplication using the appropriate method for the level
            logging.info(
                f"[DUPLICATE DEBUG] Starting duplication at {duplication_level} level "
                f"with {len(selection['instances'])} instances"
            )
            logging.info(
                "[DUPLICATE DEBUG] UID config passed to duplication: "
                f"regenerate_study_uid={uid_config.regenerate_study_uid}"
            )

            duplicated_items = self.duplication_manager.duplicate_by_hierarchy(
                selection,
                duplication_level,
                uid_config,
            )

            # Success message will be handled by duplication_completed signal
            # Integration and tree refresh will be handled by signal handlers

        except Exception as e:
            logging.error(f"Failed to duplicate selected items: {e}", exc_info=True)
            FocusAwareMessageBox.critical(
                self.main_window,
                "Duplication Error",
                f"Failed to duplicate items:\n\n{e}"
            )

    def _quick_duplicate_instances(self):
        """Quick duplicate with new instance UIDs only"""
        try:
            selected_items = self.tree.selectedItems()
            if not selected_items:
                FocusAwareMessageBox.warning(
                    self.main_window,
                    "No Selection",
                    "Please select items to duplicate."
                )
                return

            selection = self._collect_selection_metadata(selected_items)
            if not selection["instances"]:
                FocusAwareMessageBox.warning(
                    self.main_window,
                    "No Files",
                    "Selected items don't contain any files to duplicate."
                )
                return

            context_level = self._determine_context_duplication_level(selected_items) or "instance"

            uid_config = UIDConfiguration()
            uid_config.add_derived_suffix = False
            uid_config.preserve_relationships = False

            if context_level == "patient":
                duplication_level = "study"
                uid_config.regenerate_patient_id = False
                uid_config.regenerate_study_uid = True
                uid_config.regenerate_series_uid = True
                uid_config.regenerate_instance_uid = True
            elif context_level == "study":
                duplication_level = "study"
                uid_config.regenerate_patient_id = False
                uid_config.regenerate_study_uid = True
                uid_config.regenerate_series_uid = True
                uid_config.regenerate_instance_uid = True
            elif context_level == "series":
                duplication_level = "series"
                uid_config.regenerate_patient_id = False
                uid_config.regenerate_study_uid = False
                uid_config.regenerate_series_uid = True
                uid_config.regenerate_instance_uid = True
            else:
                duplication_level = "instance"
                uid_config.regenerate_patient_id = False
                uid_config.regenerate_study_uid = False
                uid_config.regenerate_series_uid = False
                uid_config.regenerate_instance_uid = True

            duplicated_items = self.duplication_manager.duplicate_by_hierarchy(
                selection,
                duplication_level,
                uid_config,
            )

            # Success message will be handled by duplication_completed signal
            # Integration and tree refresh will be handled by signal handlers

        except Exception as e:
            logging.error(f"Quick duplicate instances failed: {e}", exc_info=True)

    def _quick_duplicate_all_new(self):
        """Quick duplicate with all new UIDs"""
        try:
            selected_items = self.tree.selectedItems()
            if not selected_items:
                FocusAwareMessageBox.warning(
                    self.main_window,
                    "No Selection",
                    "Please select items to duplicate."
                )
                return

            selection = self._collect_selection_metadata(selected_items)
            if not selection["instances"]:
                FocusAwareMessageBox.warning(
                    self.main_window,
                    "No Files",
                    "Selected items don't contain any files to duplicate."
                )
                return

            duplication_level = self._determine_context_duplication_level(selected_items) or "patient"

            # Create configuration for all new UIDs
            uid_config = UIDConfiguration()
            uid_config.regenerate_instance_uid = True
            uid_config.regenerate_patient_id = True
            uid_config.regenerate_study_uid = True
            uid_config.regenerate_series_uid = True
            uid_config.add_derived_suffix = True

            # Perform duplication
            duplicated_items = self.duplication_manager.duplicate_by_hierarchy(
                selection,
                duplication_level,
                uid_config,
            )

            # Success message will be handled by duplication_completed signal
            # Integration and tree refresh will be handled by signal handlers

        except Exception as e:
            logging.error(f"Quick duplicate all new failed: {e}", exc_info=True)

    def _integrate_duplicated_items(self, duplicated_items):
        """Integrate duplicated DICOM items into the tree manager's data structures"""
        try:
            for duplicated_item in duplicated_items:
                # Create a virtual path for the duplicated item
                # Use original path with a suffix to make it unique
                original_path = duplicated_item.original_path
                base_name = os.path.splitext(os.path.basename(original_path))[0]

                # Generate unique virtual path using new UIDs
                if 'SOPInstanceUID' in duplicated_item.new_uids:
                    # Use part of the new SOP Instance UID to make it unique
                    instance_uid_part = duplicated_item.new_uids['SOPInstanceUID'].split('.')[-1][:8]
                    virtual_path = f"{original_path}_duplicate_{instance_uid_part}"
                else:
                    # Fallback to using timestamp-based ID
                    import time
                    virtual_path = f"{original_path}_duplicate_{int(time.time())}"

                # Add to memory items (these survive tree refresh)
                self.memory_items[virtual_path] = duplicated_item.duplicated_dataset

                # Add to loaded files list
                exists = False
                for entry in self.loaded_files:
                    if isinstance(entry, tuple) and entry[0] == virtual_path:
                        exists = True
                        break
                    if entry == virtual_path:
                        exists = True
                        break
                if not exists:
                    self.loaded_files.append((virtual_path, duplicated_item.duplicated_dataset))

                logging.info(f"Integrated duplicated item: {virtual_path}")

        except Exception as e:
            logging.error(f"Failed to integrate duplicated items: {e}", exc_info=True)

    def _on_duplication_started(self, level: str, count: int):
        """Handle duplication started signal - show progress dialog"""
        try:
            level_name = level.title() if level != "mixed" else "Selected Items"
            self.duplication_progress_dialog = FocusAwareProgressDialog(
                f"Duplicating {count} {level_name}...", "Cancel", 0, count, self.main_window
            )
            self.duplication_progress_dialog.setWindowTitle(f"Duplicating {level_name}")
            self.duplication_progress_dialog.setMinimumDuration(0)
            self.duplication_progress_dialog.setValue(0)
            self.duplication_progress_dialog.show()

            # Connect cancel to duplication manager if it supports cancellation
            # For now, just close dialog - cancellation can be added later if needed
            self.duplication_progress_dialog.canceled.connect(self._on_duplication_cancelled)

            logging.info(f"Started duplication progress dialog for {count} {level} items")

        except Exception as e:
            logging.error(f"Error showing duplication progress: {e}", exc_info=True)

    def _on_duplication_progress(self, current: int, total: int):
        """Handle duplication progress signal - update progress dialog"""
        try:
            if self.duplication_progress_dialog:
                progress_percent = int((current / total) * 100) if total > 0 else 0
                self.duplication_progress_dialog.setValue(current)
                self.duplication_progress_dialog.setLabelText(
                    f"Processing item {current} of {total} ({progress_percent}%)"
                )
                QApplication.processEvents()  # Keep UI responsive

        except Exception as e:
            logging.error(f"Error updating duplication progress: {e}", exc_info=True)

    def _on_duplication_completed(self, duplicated_items: list):
        """Handle duplication completed signal - close progress, integrate items, refresh tree"""
        try:
            # Close progress dialog
            if self.duplication_progress_dialog:
                self.duplication_progress_dialog.close()
                self.duplication_progress_dialog = None

            if duplicated_items:
                # Integrate duplicated items into memory storage
                self._integrate_duplicated_items(duplicated_items)

                # Refresh the tree to show new items (now includes memory items)
                self.refresh_tree()

                # Show success message
                FocusAwareMessageBox.information(
                    self.main_window,
                    "Duplication Complete",
                    f"Successfully duplicated {len(duplicated_items)} items.\n\n"
                    f"The duplicated items are now visible in the tree. "
                    f"Use 'Save Duplicated Items' to write them to disk if needed."
                )

            logging.info(f"Duplication completed with {len(duplicated_items)} items")

        except Exception as e:
            logging.error(f"Error handling duplication completion: {e}", exc_info=True)

    def _on_duplication_error(self, error_message: str):
        """Handle duplication error signal - close progress and show error"""
        try:
            # Close progress dialog
            if self.duplication_progress_dialog:
                self.duplication_progress_dialog.close()
                self.duplication_progress_dialog = None

            # Show error message
            FocusAwareMessageBox.critical(
                self.main_window,
                "Duplication Error",
                f"Duplication failed:\n\n{error_message}"
            )

            logging.error(f"Duplication error: {error_message}")

        except Exception as e:
            logging.error(f"Error handling duplication error: {e}", exc_info=True)

    def _on_duplication_cancelled(self):
        """Handle duplication cancelled by user"""
        try:
            # Close progress dialog
            if self.duplication_progress_dialog:
                self.duplication_progress_dialog.close()
                self.duplication_progress_dialog = None

            logging.info("Duplication cancelled by user")

        except Exception as e:
            logging.error(f"Error handling duplication cancellation: {e}", exc_info=True)

    def _view_duplicated_items(self):
        """Show a list of duplicated items"""
        duplicated_items = self.duplication_manager.get_duplicated_items()
        if not duplicated_items:
            FocusAwareMessageBox.information(
                self.main_window,
                "No Duplicated Items",
                "There are currently no duplicated items in memory."
            )
            return

        # Create a summary message
        summary = f"Duplicated Items in Memory: {len(duplicated_items)}\n\n"

        for idx, item in enumerate(duplicated_items[:10]):  # Show first 10
            summary += f"{idx + 1}. {os.path.basename(item.original_path)}\n"
            summary += f"   Level: {item.duplication_level}\n"
            summary += f"   Modified: {'Yes' if item.is_modified else 'No'}\n\n"

        if len(duplicated_items) > 10:
            summary += f"... and {len(duplicated_items) - 10} more items.\n"

        summary += "\nUse 'Save Duplicated Items' to write them to disk."

        FocusAwareMessageBox.information(
            self.main_window,
            "Duplicated Items",
            summary
        )

    def _save_duplicated_items(self):
        """Save duplicated items to disk"""
        from PyQt6.QtWidgets import QFileDialog

        duplicated_items = self.duplication_manager.get_duplicated_items()
        if not duplicated_items:
            return

        # Ask user for output directory
        output_dir = QFileDialog.getExistingDirectory(
            self.main_window,
            "Select Directory to Save Duplicated Items",
            os.path.expanduser("~/DICOM_Duplicates")
        )

        if not output_dir:
            return

        try:
            saved_paths = self.duplication_manager.save_duplicated_items(
                duplicated_items, output_dir
            )

            FocusAwareMessageBox.information(
                self.main_window,
                "Save Complete",
                f"Successfully saved {len(saved_paths)} duplicated items to:\n{output_dir}"
            )

        except Exception as e:
            logging.error(f"Failed to save duplicated items: {e}", exc_info=True)
            FocusAwareMessageBox.critical(
                self.main_window,
                "Save Error",
                f"Failed to save duplicated items:\n\n{e}"
            )

    def _clear_duplicated_items(self):
        """Clear all duplicated items from memory"""
        duplicated_count = len(self.duplication_manager.get_duplicated_items())
        if duplicated_count == 0:
            return

        reply = FocusAwareMessageBox.question(
            self.main_window,
            "Clear Duplicated Items",
            f"This will remove {duplicated_count} duplicated items from memory.\n\n"
            f"Any unsaved changes will be lost. Continue?",
            FocusAwareMessageBox.StandardButton.Yes | FocusAwareMessageBox.StandardButton.No,
            FocusAwareMessageBox.StandardButton.No
        )

        if reply == FocusAwareMessageBox.StandardButton.Yes:
            self.duplication_manager.clear_duplicated_items()
            FocusAwareMessageBox.information(
                self.main_window,
                "Items Cleared",
                "All duplicated items have been cleared from memory."
            )
