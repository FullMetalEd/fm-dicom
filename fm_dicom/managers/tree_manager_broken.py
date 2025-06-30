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
        
        # Connect tree signals
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
    
    def populate_tree(self, files):
        """Populate tree with DICOM file hierarchy"""
        self.tree.clear()
        self.file_metadata = {}
        self.loaded_files = files
        
        hierarchy = {}
        modalities = set()
        
        # Progress dialog for loading
        progress = QProgressDialog("Loading DICOM headers...", "Cancel", 0, len(files), self.main_window)
        progress.setWindowTitle("Loading DICOM Files")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        
        for idx, file_info in enumerate(files):
            if progress.wasCanceled():
                break
            
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
                }\n                \n            except Exception as e:\n                logging.warning(f"Could not process file {file_path}: {e}")\n                continue\n            \n            progress.setValue(idx + 1)\n            if idx % 10 == 0:  # Update UI periodically\n                QApplication.processEvents()\n        \n        progress.close()\n        \n        if progress.wasCanceled():\n            logging.info("Tree population was cancelled")\n            return\n        \n        # Populate tree widget\n        self._build_tree_structure(hierarchy)\n        \n        # Update status\n        total_files = len([f for f in files if not progress.wasCanceled()])\n        self.tree_populated.emit(total_files)\n        \n        logging.info(f"Tree populated with {total_files} files")\n    \n    def _build_tree_structure(self, hierarchy):\n        """Build the actual tree structure from hierarchy data"""\n        for patient, studies in hierarchy.items():\n            patient_item = QTreeWidgetItem([patient, ""])\n            patient_item.setData(0, Qt.ItemDataRole.UserRole, None)  # No file for patient\n            self.tree.addTopLevelItem(patient_item)\n            \n            patient_file_count = 0\n            for study, series_dict in studies.items():\n                study_item = QTreeWidgetItem([study, ""])\n                study_item.setData(0, Qt.ItemDataRole.UserRole, None)  # No file for study\n                patient_item.addChild(study_item)\n                \n                study_file_count = 0\n                for series, instances in series_dict.items():\n                    series_item = QTreeWidgetItem([series, ""])\n                    series_item.setData(0, Qt.ItemDataRole.UserRole, None)  # No file for series\n                    study_item.addChild(series_item)\n                    \n                    # Sort instances by instance number\n                    sorted_instances = sorted(\n                        instances.items(),\n                        key=lambda x: x[1]['sort_key']\n                    )\n                    \n                    series_file_count = len(sorted_instances)\n                    for instance_label, instance_data in sorted_instances:\n                        instance_item = QTreeWidgetItem([instance_label, "Instance"])\n                        instance_item.setData(0, Qt.ItemDataRole.UserRole, instance_data['filepath'])\n                        series_item.addChild(instance_item)\n                    \n                    series_item.setText(1, f"{series_file_count} files")\n                    study_file_count += series_file_count\n                \n                study_item.setText(1, f"{study_file_count} files")\n                patient_file_count += study_file_count\n            \n            patient_item.setText(1, f"{patient_file_count} files")\n        \n        # Expand first level by default\n        for i in range(self.tree.topLevelItemCount()):\n            self.tree.topLevelItem(i).setExpanded(True)\n    \n    def _on_selection_changed(self):\n        """Handle tree selection changes"""\n        selected_items = self.tree.selectedItems()\n        file_paths = []\n        \n        for item in selected_items:\n            paths = self._collect_instance_filepaths(item)\n            file_paths.extend(paths)\n        \n        # Remove duplicates while preserving order\n        unique_paths = []\n        seen = set()\n        for path in file_paths:\n            if path not in seen:\n                unique_paths.append(path)\n                seen.add(path)\n        \n        self.selection_changed.emit(unique_paths)\n    \n    def _collect_instance_filepaths(self, item):\n        """Recursively collect file paths from a tree item and its children"""\n        filepaths = []\n        \n        # Check if this item has a file path\n        file_path = item.data(0, Qt.ItemDataRole.UserRole)\n        if file_path:\n            filepaths.append(file_path)\n        \n        # Recursively check children\n        for i in range(item.childCount()):\n            child_paths = self._collect_instance_filepaths(item.child(i))\n            filepaths.extend(child_paths)\n        \n        return filepaths\n    \n    def filter_tree_items(self, text):\n        """Filter tree items based on search text"""\n        text = text.lower()\n        \n        def match_item(item):\n            # Check if any column text matches\n            for col in range(item.columnCount()):\n                if text in item.text(col).lower():\n                    return True\n            \n            # Check children\n            for i in range(item.childCount()):\n                if match_item(item.child(i)):\n                    item.setExpanded(True)\n                    return True\n            \n            return False\n        \n        def filter_recursive(item):\n            is_visible = match_item(item) if text else True\n            item.setHidden(not is_visible)\n            \n            if is_visible or not text:\n                for i in range(item.childCount()):\n                    filter_recursive(item.child(i))\n        \n        # Apply filter to all top-level items\n        for i in range(self.tree.topLevelItemCount()):\n            filter_recursive(self.tree.topLevelItem(i))\n    \n    def get_selected_files(self):\n        """Get list of currently selected file paths"""\n        selected_items = self.tree.selectedItems()\n        file_paths = []\n        \n        for item in selected_items:\n            paths = self._collect_instance_filepaths(item)\n            file_paths.extend(paths)\n        \n        return list(set(file_paths))  # Remove duplicates\n    \n    def delete_selected_items(self):\n        """Delete selected items from tree and loaded files"""\n        selected_items = self.tree.selectedItems()\n        if not selected_items:\n            FocusAwareMessageBox.warning(\n                self.main_window,\n                "No Selection",\n                "Please select items to delete."\n            )\n            return\n        \n        # Confirm deletion\n        file_count = 0\n        for item in selected_items:\n            file_count += len(self._collect_instance_filepaths(item))\n        \n        reply = FocusAwareMessageBox.question(\n            self.main_window,\n            "Confirm Deletion",\n            f"Delete {len(selected_items)} selected items ({file_count} files)?",\n            FocusAwareMessageBox.StandardButton.Yes | FocusAwareMessageBox.StandardButton.No,\n            FocusAwareMessageBox.StandardButton.No\n        )\n        \n        if reply != FocusAwareMessageBox.StandardButton.Yes:\n            return\n        \n        # Collect files to remove\n        files_to_remove = set()\n        for item in selected_items:\n            files_to_remove.update(self._collect_instance_filepaths(item))\n        \n        # Remove from loaded files\n        self.loaded_files = [\n            f for f in self.loaded_files \n            if (f[0] if isinstance(f, tuple) else f) not in files_to_remove\n        ]\n        \n        # Remove from metadata\n        for file_path in files_to_remove:\n            self.file_metadata.pop(file_path, None)\n        \n        # Remove items from tree\n        for item in selected_items:\n            parent = item.parent()\n            if parent:\n                parent.removeChild(item)\n            else:\n                index = self.tree.indexOfTopLevelItem(item)\n                self.tree.takeTopLevelItem(index)\n        \n        # Update counts and emit signal\n        self.tree_populated.emit(len(self.loaded_files))\n        self._on_selection_changed()  # Update selection\n        \n        logging.info(f"Deleted {len(files_to_remove)} files from tree")\n    \n    def clear_tree(self):\n        """Clear all tree contents"""\n        self.tree.clear()\n        self.file_metadata.clear()\n        self.loaded_files.clear()\n        self.tree_populated.emit(0)\n        \n    def expand_all(self):\n        """Expand all tree items"""\n        self.tree.expandAll()\n    \n    def collapse_all(self):\n        """Collapse all tree items"""\n        self.tree.collapseAll()\n    \n    def select_all(self):\n        """Select all tree items"""\n        self.tree.selectAll()\n    \n    def clear_selection(self):\n        """Clear tree selection"""\n        self.tree.clearSelection()\n    \n    def get_file_metadata(self, file_path):\n        """Get metadata for a specific file"""\n        return self.file_metadata.get(file_path)\n    \n    def get_loaded_files(self):\n        """Get list of all loaded files"""\n        return self.loaded_files.copy()\n    \n    def get_file_count(self):\n        """Get total number of loaded files"""\n        return len(self.loaded_files)