"""
DICOM operations manager for MainWindow.

This manager handles DICOM-specific operations including tag editing,
validation, anonymization, and network operations.
"""

import os
import logging
import pydicom
from PyQt6.QtWidgets import QTableWidgetItem, QApplication
from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtGui import QPixmap, QImage

from fm_dicom.widgets.focus_aware import FocusAwareMessageBox
from fm_dicom.validation.validation_ui import run_validation
from fm_dicom.anonymization.anonymization_ui import run_anonymization
from fm_dicom.tag_browser.tag_browser import TagSearchDialog, ValueEntryDialog
from fm_dicom.dialogs.dicom_send_selection import DicomSendSelectionDialog
from fm_dicom.dialogs.selection_dialogs import DicomSendDialog


class DicomManager(QObject):
    """Manager class for DICOM operations"""
    
    # Signals
    tag_data_changed = pyqtSignal()       # Emitted when tag data changes
    image_loaded = pyqtSignal(QPixmap)    # Emitted when image is loaded
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.config = main_window.config
        self.tag_table = main_window.tag_table
        self.search_bar = main_window.search_bar
        self.image_label = main_window.image_label
        self.frame_selector = getattr(main_window, 'frame_selector', None)
        
        # Current state
        self.current_file = None
        self.current_dataset = None
        self._all_tag_rows = []  # For filtering
        self._has_unsaved_changes = False
        self._current_filter_text = ""  # Store current search filter
        
        # Connect signals
        self.tag_table.itemChanged.connect(self._on_tag_changed)
    
    def load_dicom_tags(self, file_path):
        """Load DICOM tags for a file into the tag table"""
        if not file_path or not os.path.exists(file_path):
            self.clear_tag_table()
            return
        
        try:
            # Read DICOM file
            ds = pydicom.dcmread(file_path)
            self.current_file = file_path
            self.current_dataset = ds
            
            # Update image frames if applicable
            self._update_frame_selector(ds)
            
            # Populate tag table
            self._populate_tag_table(ds)
            
            # Load image if preview is enabled
            if self.config.get("show_image_preview", True):
                self.display_image()
            
            logging.info(f"Loaded DICOM tags for: {file_path}")
            
        except Exception as e:
            logging.error(f"Error loading DICOM file {file_path}: {e}", exc_info=True)
            FocusAwareMessageBox.critical(
                self.main_window,
                "DICOM Load Error",
                f"Failed to load DICOM file:\n{file_path}\n\nError: {str(e)}"
            )
            self.clear_tag_table()
    
    def _populate_tag_table(self, ds):
        """Populate the tag table with DICOM dataset elements"""
        self.tag_table.setRowCount(0)
        self._all_tag_rows = []
        
        # Iterate through all elements in dataset
        for elem in ds:
            try:
                tag_id = f"({elem.tag.group:04X},{elem.tag.element:04X})"
                
                # Get tag description
                try:
                    desc = pydicom.datadict.keyword_for_tag(elem.tag)
                    if not desc:
                        desc = "Private Tag" if elem.tag.is_private else "Unknown"
                except Exception as e:
                    logging.debug(f"Could not get tag description for {elem.tag}: {e}")
                    desc = "Unknown"
                
                # Format value for display
                if elem.VR in ("OB", "OW", "UN"):
                    if len(elem.value) > 100:
                        value_str = f"<Binary data, {len(elem.value)} bytes>"
                    else:
                        value_str = f"<Binary data>"
                elif elem.VR == "SQ":
                    value_str = f"<Sequence, {len(elem.value)} items>"
                elif elem.tag == (0x7fe0, 0x0010):  # Pixel Data
                    value_str = "<Pixel Data>"
                else:
                    try:
                        value_str = str(elem.value)
                        if len(value_str) > 200:
                            value_str = value_str[:200] + "..."
                    except Exception as e:
                        logging.debug(f"Could not format value for tag {elem.tag}: {e}")
                        value_str = "<Cannot display>"
                
                # Store row data for filtering
                display_row = [tag_id, desc, value_str, ""]
                self._all_tag_rows.append({
                    'elem_obj': elem,
                    'display_row': display_row
                })
                
            except Exception as e:
                logging.warning(f"Error processing tag {elem.tag}: {e}")
                continue
        
        # Sort by tag ID
        self._all_tag_rows.sort(key=lambda x: x['display_row'][0])
        
        # Populate table
        self._refresh_tag_table()
    
    def _refresh_tag_table(self):
        """Refresh the tag table display, applying current filter if any"""
        self.tag_table.setRowCount(0)
        
        # Apply current filter or show all tags
        filter_text = self._current_filter_text
        
        for row_info in self._all_tag_rows:
            elem_obj = row_info['elem_obj']
            display_row = row_info['display_row']
            tag_id, desc, value, _ = display_row
            
            # Check if row matches current filter (if any)
            if filter_text and not (
                filter_text in tag_id.lower() or 
                filter_text in desc.lower() or
                filter_text in value.lower()
            ):
                continue  # Skip this row if it doesn't match filter
            
            # Add matching row to table
            row_idx = self.tag_table.rowCount()
            self.tag_table.insertRow(row_idx)
            
            # Set table items
            self.tag_table.setItem(row_idx, 0, QTableWidgetItem(tag_id))
            self.tag_table.setItem(row_idx, 1, QTableWidgetItem(desc))
            self.tag_table.setItem(row_idx, 2, QTableWidgetItem(value))
            
            # New value column
            new_value_item = QTableWidgetItem("")
            new_value_item.setData(Qt.ItemDataRole.UserRole, elem_obj)
            
            # Make certain tags non-editable
            if (elem_obj.tag == (0x7fe0, 0x0010) or 
                elem_obj.VR in ("OB", "OW", "UN", "SQ")):
                new_value_item.setFlags(new_value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                new_value_item.setToolTip("This tag cannot be edited")
            
            self.tag_table.setItem(row_idx, 3, new_value_item)
        
        # Set column widths
        self.tag_table.setColumnWidth(0, 110)
        self.tag_table.setColumnWidth(1, 220) 
        self.tag_table.setColumnWidth(2, 260)
        self.tag_table.setColumnWidth(3, 160)
    
    def filter_tag_table(self, text):
        """Filter tag table based on search text"""
        self._current_filter_text = text.lower()  # Store current filter
        self._refresh_tag_table()  # Refresh table with new filter
    
    def _on_tag_changed(self, item):
        """Handle tag value changes"""
        if item.column() == 3:  # New value column
            self._has_unsaved_changes = True
            # Enable save button if it exists
            if hasattr(self.main_window, 'save_btn'):
                self.main_window.save_btn.setEnabled(True)
            self.tag_data_changed.emit()
    
    def save_tag_changes(self):
        """Save tag changes to DICOM files based on selected level"""
        if not self.current_file or not self.current_dataset:
            FocusAwareMessageBox.warning(self.main_window, "No File", "No DICOM file selected.")
            return

        # Get the selected level from the combo box
        level = self.main_window.edit_level_combo.currentText()
        selected = self.main_window.tree.selectedItems()
        if not selected:
            FocusAwareMessageBox.warning(self.main_window, "No Selection", "Please select a node in the tree.")
            return
        tree_item = selected[0]

        level_map = {"Patient": 0, "Study": 1, "Series": 2, "Instance": 3}
        target_level = level_map[level]
        
        # Find the node corresponding to the selected level relative to the clicked item
        node_at_target_level = tree_item
        while self._get_tree_item_depth(node_at_target_level) > target_level and node_at_target_level.parent():
            node_at_target_level = node_at_target_level.parent()

        filepaths = self.main_window.tree_manager._collect_instance_filepaths(node_at_target_level)
        if not filepaths:
            FocusAwareMessageBox.warning(self.main_window, "No Instances", "No DICOM instances found under this node for the selected level.")
            return

        # Collect edits from the tag table
        edits = []
        for i in range(self.tag_table.rowCount()):
            new_value_item = self.tag_table.item(i, 3)
            if new_value_item and new_value_item.text().strip() != "":
                tag_id_str = self.tag_table.item(i, 0).text()
                original_elem = new_value_item.data(Qt.ItemDataRole.UserRole)

                try:
                    group_hex, elem_hex = tag_id_str[1:-1].split(",")
                    tag_tuple = (int(group_hex, 16), int(elem_hex, 16))
                    
                    edits.append({
                        'tag': tag_tuple, 
                        'value_str': new_value_item.text(), 
                        'original_elem': original_elem
                    })
                except Exception as e:
                    FocusAwareMessageBox.warning(self.main_window, "Error", f"Failed to parse tag {tag_id_str}: {e}")
                    logging.error(f"Error parsing tag {tag_id_str}: {e}", exc_info=True)

        if not edits:
            FocusAwareMessageBox.information(self.main_window, "No Changes", "No tags were changed.")
            return

        # Perform the batch update
        self._perform_level_tag_save(filepaths, edits, level)
    
    def _perform_level_tag_save(self, filepaths, edits, level):
        """Perform tag saves across multiple files at the specified level"""
        import pydicom
        from PyQt6.QtWidgets import QProgressDialog, QApplication
        import os
        
        updated_count = 0
        failed_files = []
        
        progress = QProgressDialog(f"Saving changes to {level}...", "Cancel", 0, len(filepaths), self.main_window)
        progress.setWindowTitle("Saving Tag Changes")
        progress.setMinimumDuration(0)
        progress.setValue(0)

        for idx, fp in enumerate(filepaths):
            progress.setValue(idx)
            if progress.wasCanceled():
                break
            QApplication.processEvents()
            
            try:
                ds = pydicom.dcmread(fp)
                file_updated = False
                
                for edit_info in edits:
                    tag = edit_info['tag']
                    new_val_str = edit_info['value_str']
                    original_elem_ref = edit_info['original_elem']

                    if tag in ds:  # Modify existing tag
                        target_elem = ds[tag]
                        try:
                            # Convert value based on VR
                            converted_value = self._convert_value_by_vr_advanced(new_val_str, original_elem_ref, target_elem)
                            target_elem.value = converted_value
                            file_updated = True
                        except Exception as e_conv:
                            logging.warning(f"Could not convert value '{new_val_str}' for tag {tag} in {fp}. Error: {e_conv}. Saving as string.")
                            target_elem.value = new_val_str  # Fallback to string
                            file_updated = True
                    else:  # Add new tag
                        try:
                            # Get VR from original element reference
                            vr = original_elem_ref.VR if hasattr(original_elem_ref, 'VR') else 'LO'
                            # Convert value based on VR
                            converted_value = self._convert_value_by_vr(new_val_str, vr)
                            # Add new tag to dataset
                            ds.add_new(tag, vr, converted_value)
                            file_updated = True
                            logging.info(f"Added new tag {tag} with VR {vr} and value '{new_val_str}' to {fp}")
                        except Exception as e_add:
                            logging.warning(f"Could not add new tag {tag} to {fp}. Error: {e_add}. Trying with string value.")
                            try:
                                # Fallback to string value with LO VR
                                ds.add_new(tag, 'LO', new_val_str)
                                file_updated = True
                            except Exception as e_fallback:
                                logging.error(f"Failed to add new tag {tag} to {fp}: {e_fallback}")
                                continue
                
                if file_updated:
                    ds.save_as(fp)
                    updated_count += 1
                    
            except Exception as e_file:
                logging.error(f"Failed to process file {fp}: {e_file}", exc_info=True)
                failed_files.append(f"{os.path.basename(fp)}: {str(e_file)}")
                
        progress.setValue(len(filepaths))
        
        # Show results
        msg = f"Tag changes saved to {level}.\nUpdated {updated_count} of {len(filepaths)} files."
        if failed_files:
            msg += f"\nFailed: {len(failed_files)} files."
            
        FocusAwareMessageBox.information(self.main_window, "Changes Saved", msg)
        
        # Clear change indicators and reload current file
        for row in range(self.tag_table.rowCount()):
            new_value_item = self.tag_table.item(row, 3)
            if new_value_item:
                new_value_item.setText("")
        
        self._has_unsaved_changes = False
        if hasattr(self.main_window, 'save_btn'):
            self.main_window.save_btn.setEnabled(False)
            
        # Reload current file to show updated values
        if self.current_file in filepaths:
            self.load_dicom_tags(self.current_file)
            
        # Refresh tree to show updated patient names and other hierarchy changes
        if hasattr(self.main_window, 'tree_manager') and self.main_window.tree_manager:
            self.main_window.tree_manager.refresh_tree()
            logging.info("Tree refreshed after tag save")
    
    def _convert_value_by_vr_advanced(self, new_val_str, original_elem_ref, target_elem):
        """Advanced value conversion based on VR and original element"""
        import pydicom
        
        if original_elem_ref.VR == "UI":
            return new_val_str
        elif original_elem_ref.VR in ["IS", "SL", "SS", "UL", "US"]:
            return int(new_val_str)
        elif original_elem_ref.VR in ["FL", "FD", "DS"]:
            return float(new_val_str)
        elif original_elem_ref.VR == "DA":
            return new_val_str.replace("-", "")  # YYYYMMDD
        elif original_elem_ref.VR == "TM":
            return new_val_str.replace(":", "")  # HHMMSS.FFFFFF
        elif isinstance(target_elem.value, list):
            # For multi-valued elements
            return [v.strip() for v in new_val_str.split('\\')]  # DICOM standard is backslash
        elif isinstance(target_elem.value, pydicom.personname.PersonName):
            return new_val_str  # pydicom handles PersonName string
        else:
            # Try direct cast to original Python type
            return type(target_elem.value)(new_val_str)
    
    def _get_tree_item_depth(self, item):
        """Calculate the depth of a tree item (0 = root level)"""
        depth = 0
        current = item
        while current.parent():
            depth += 1
            current = current.parent()
        return depth
    
    def revert_tag_changes(self):
        """Revert unsaved tag changes"""
        # Clear all new value fields
        for row in range(self.tag_table.rowCount()):
            new_value_item = self.tag_table.item(row, 3)
            if new_value_item:
                new_value_item.setText("")
        
        self._has_unsaved_changes = False
        # Disable save button if it exists
        if hasattr(self.main_window, 'save_btn'):
            self.main_window.save_btn.setEnabled(False)
    
    def clear_search_filter(self):
        """Clear the search filter and update UI"""
        self._current_filter_text = ""
        if hasattr(self, 'search_bar') and self.search_bar:
            self.search_bar.clear()
    
    def clear_tag_table(self):
        """Clear the tag table"""
        self.tag_table.setRowCount(0)
        self._all_tag_rows = []
        self.current_file = None
        self.current_dataset = None
        self._has_unsaved_changes = False
        self.clear_search_filter()  # Clear search filter and UI
        
        # Clear image
        self.image_label.clear()
        self.image_label.setText("No file selected")
        
        # Clear frame selector
        if self.frame_selector:
            self.frame_selector.clear()
    
    def _update_frame_selector(self, ds):
        """Update frame selector for multi-frame images"""
        if not self.frame_selector:
            return
            
        self.frame_selector.clear()
        
        try:
            # Check if image has multiple frames
            if hasattr(ds, 'NumberOfFrames') and ds.NumberOfFrames > 1:
                for i in range(int(ds.NumberOfFrames)):
                    self.frame_selector.addItem(f"Frame {i + 1}")
                self.frame_selector.setEnabled(True)
            else:
                self.frame_selector.addItem("Frame 1")
                self.frame_selector.setEnabled(False)
        except Exception as e:
            logging.debug(f"Could not set up frame selector: {e}")
            self.frame_selector.addItem("Frame 1")
            self.frame_selector.setEnabled(False)
    
    def display_image(self):
        """Display DICOM image in preview"""
        if not self.current_dataset or not self.config.get("show_image_preview", True):
            return
        
        try:
            ds = self.current_dataset
            
            # Check if dataset has pixel data
            if not hasattr(ds, 'pixel_array'):
                self.image_label.setText("No image data")
                return
            
            # Get selected frame
            frame_index = 0
            if self.frame_selector:
                frame_index = self.frame_selector.currentIndex()
                if frame_index < 0:
                    frame_index = 0
            
            # Get pixel array
            pixel_array = ds.pixel_array
            
            # Handle multi-frame images
            if len(pixel_array.shape) > 2:
                if frame_index < pixel_array.shape[0]:
                    pixel_array = pixel_array[frame_index]
                else:
                    pixel_array = pixel_array[0]
            
            # Normalize pixel data to 0-255 range
            if pixel_array.dtype != 'uint8':
                pixel_array = ((pixel_array - pixel_array.min()) * 255.0 / 
                             (pixel_array.max() - pixel_array.min())).astype('uint8')
            
            # Create QImage
            height, width = pixel_array.shape
            q_image = QImage(pixel_array.data, width, height, width, QImage.Format.Format_Grayscale8)
            
            # Convert to pixmap and scale to fit
            pixmap = QPixmap.fromImage(q_image)
            label_size = self.image_label.size()
            scaled_pixmap = pixmap.scaled(
                label_size, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            
            self.image_label.setPixmap(scaled_pixmap)
            self.image_loaded.emit(scaled_pixmap)
            
        except Exception as e:
            logging.warning(f"Could not display image: {e}")
            self.image_label.setText("Could not display image")
    
    def validate_selected_items(self, file_paths):
        """Validate selected DICOM files"""
        if not file_paths:
            FocusAwareMessageBox.warning(
                self.main_window,
                "No Selection",
                "Please select files to validate."
            )
            return
        
        logging.info(f"Starting validation of {len(file_paths)} files")
        
        try:
            run_validation(file_paths, self.main_window)
        except Exception as e:
            logging.error(f"Validation error: {e}", exc_info=True)
            FocusAwareMessageBox.critical(
                self.main_window,
                "Validation Error",
                f"An error occurred during validation:\n{str(e)}"
            )
    
    def anonymize_selected_items(self, file_paths):
        """Anonymize selected DICOM files"""
        if not file_paths:
            FocusAwareMessageBox.warning(
                self.main_window,
                "No Selection",
                "Please select files to anonymize."
            )
            return
        
        logging.info(f"Starting anonymization of {len(file_paths)} files")
        
        try:
            result = run_anonymization(file_paths, self.main_window.template_manager, self.main_window)
            # Refresh tree to show updated patient names and other changes
            if result is not None:  # Anonymization completed successfully
                if hasattr(self.main_window, 'tree_manager') and self.main_window.tree_manager:
                    self.main_window.tree_manager.refresh_tree()
                    logging.info("Tree refreshed after anonymization")
        except Exception as e:
            logging.error(f"Anonymization error: {e}", exc_info=True)
            FocusAwareMessageBox.critical(
                self.main_window,
                "Anonymization Error",
                f"An error occurred during anonymization:\n{str(e)}"
            )
    
    def show_tag_search_dialog(self):
        """Show tag search dialog and handle new tag creation"""
        if not self.current_dataset:
            FocusAwareMessageBox.information(
                self.main_window,
                "No File Loaded",
                "Please load a DICOM file first."
            )
            return
        
        # Show tag search dialog
        dialog = TagSearchDialog(self.main_window, "Select Tag to Add")
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
            
        # Get selected tag information
        tag_info = dialog.get_selected_tag_info()
        if not tag_info['tag']:
            return
            
        # Parse the selected tag
        tag = None
        tag_str = tag_info['tag']
        
        if ',' in tag_str and tag_str.startswith("(") and tag_str.endswith(")"):
            # Handle hex format like (GGGG,EEEE)
            try:
                group, elem = tag_str[1:-1].split(',')
                tag = (int(group, 16), int(elem, 16))
            except ValueError:
                FocusAwareMessageBox.warning(self.main_window, "Invalid Tag", "Invalid tag format.")
                return
        else:
            # Handle keyword or custom tag names
            try:
                import pydicom
                # First try as a known DICOM keyword
                tag_obj = pydicom.tag.Tag(tag_str.strip())
                tag = (tag_obj.group, tag_obj.element)
            except ValueError:
                # If not a known keyword, treat as custom private tag
                # Use private group 0x7777 for custom tags
                # Create a simple hash-based element number from the tag name
                import hashlib
                tag_hash = hashlib.md5(tag_str.encode()).hexdigest()
                # Use first 4 hex chars as element number, ensure it's odd (private)
                element = int(tag_hash[:4], 16)
                if element % 2 == 0:  # Make sure it's odd for private tags
                    element += 1
                tag = (0x7777, element)
                logging.info(f"Created custom private tag for '{tag_str}': {tag}")
                
                # Update tag_info to reflect the generated tag
                tag_info['tag'] = f"({tag[0]:04X},{tag[1]:04X})"
                tag_info['name'] = f"Custom Tag: {tag_str}"
                tag_info['vr'] = 'LO'  # Default VR for custom tags

        # Check if tag already exists in current dataset
        current_value = ""
        if tag in self.current_dataset:
            current_value = str(self.current_dataset[tag].value)
        else:
            current_value = "<New Tag>"

        # Show value entry dialog
        value_dialog = ValueEntryDialog(tag_info, current_value, self.main_window)
        value_dialog.setWindowTitle(f"Enter Value: {tag_info['name']}")
        
        if value_dialog.exec() != value_dialog.DialogCode.Accepted:
            return
            
        new_value = value_dialog.new_value
        
        # Add the new tag entry to the tag table for editing
        self._add_new_tag_to_table(tag, tag_info, new_value)
    
    def _add_new_tag_to_table(self, tag, tag_info, new_value):
        """Add a new tag entry to the tag table for editing"""
        try:
            # Format tag ID for display
            tag_id = f"({tag[0]:04X},{tag[1]:04X})"
            
            # Create a mock element for the new tag
            import pydicom
            vr = tag_info.get('vr', 'LO')  # Default to LO if VR not specified
            
            # Create a new DataElement
            try:
                # Convert value based on VR
                converted_value = self._convert_value_by_vr(new_value, vr)
                mock_elem = pydicom.DataElement(tag, vr, converted_value)
            except Exception as e:
                logging.warning(f"Could not convert value for VR {vr}: {e}. Using string value.")
                mock_elem = pydicom.DataElement(tag, vr, new_value)
            
            # Add to the tag table rows for display
            display_row = [tag_id, tag_info['name'], str(new_value), ""]
            self._all_tag_rows.append({
                'elem_obj': mock_elem,
                'display_row': display_row
            })
            
            # Sort by tag ID to maintain order
            self._all_tag_rows.sort(key=lambda x: x['display_row'][0])
            
            # Refresh the tag table display
            self._refresh_tag_table()
            
            # Find the row with our new tag and set the new value
            for row in range(self.tag_table.rowCount()):
                tag_item = self.tag_table.item(row, 0)
                if tag_item and tag_item.text() == tag_id:
                    new_value_item = self.tag_table.item(row, 3)
                    if new_value_item:
                        new_value_item.setText(new_value)
                        # Mark as changed
                        self._has_unsaved_changes = True
                        if hasattr(self.main_window, 'save_btn'):
                            self.main_window.save_btn.setEnabled(True)
                        self.tag_data_changed.emit()
                        
                        # Select and scroll to the new row
                        self.tag_table.selectRow(row)
                        self.tag_table.scrollToItem(tag_item)
                    break
            
            FocusAwareMessageBox.information(
                self.main_window,
                "Tag Added",
                f"Tag '{tag_info['name']}' has been added to the editing table.\n"
                f"Value: {new_value}\n\n"
                "Click 'Save Changes' to save this tag to the DICOM file."
            )
            
            logging.info(f"Added new tag {tag_id} ({tag_info['name']}) with value '{new_value}' to editing table")
            
        except Exception as e:
            logging.error(f"Error adding new tag to table: {e}", exc_info=True)
            FocusAwareMessageBox.critical(
                self.main_window,
                "Error Adding Tag",
                f"Failed to add tag to editing table:\n{str(e)}"
            )
    
    def show_dicom_send_dialog(self, file_paths, selected_items):
        """Show DICOM send dialog"""
        if not file_paths:
            FocusAwareMessageBox.warning(
                self.main_window,
                "No Selection",
                "Please select files to send."
            )
            return
        
        try:
            # Get pre-built hierarchy data from TreeManager for performance
            hierarchy_data = None
            if hasattr(self.main_window, 'tree_manager') and hasattr(self.main_window.tree_manager, 'hierarchy'):
                hierarchy_data = getattr(self.main_window.tree_manager, 'hierarchy', None)
            
            # Show file selection dialog first
            loaded_files = [(path, None) for path in file_paths]  # Convert to expected format
            
            from fm_dicom.dialogs.dicom_send_selection import DicomSendSelectionDialog
            selection_dialog = DicomSendSelectionDialog(
                loaded_files, 
                selected_items, 
                self.main_window,
                hierarchy_data=hierarchy_data
            )
            
            if selection_dialog.exec():
                selected_files = selection_dialog.get_selected_files()
                
                if selected_files:
                    # Show DICOM send dialog to get connection parameters
                    send_dialog = DicomSendDialog(
                        self.main_window,
                        self.config
                    )
                    if send_dialog.exec():
                        # Get connection parameters from dialog
                        params = send_dialog.get_params()
                        if params:
                            # Start DICOM send with selected files and parameters
                            self._start_dicom_send(selected_files, params)
                else:
                    FocusAwareMessageBox.information(
                        self.main_window,
                        "No Files Selected",
                        "No files were selected for sending."
                    )
        
        except Exception as e:
            logging.error(f"DICOM send error: {e}", exc_info=True)
            FocusAwareMessageBox.critical(
                self.main_window,
                "DICOM Send Error",
                f"An error occurred preparing DICOM send:\n{str(e)}"
            )
    
    def _start_dicom_send(self, selected_files, send_params):
        """Start DICOM send worker with selected files and parameters"""
        try:
            # Analyze files to get unique SOP classes
            unique_sop_classes = set()
            for filepath in selected_files:
                try:
                    ds = pydicom.dcmread(filepath, stop_before_pixels=True)
                    if hasattr(ds, 'SOPClassUID'):
                        unique_sop_classes.add(ds.SOPClassUID)
                except Exception as e:
                    logging.warning(f"Could not read SOP class from {filepath}: {e}")
            
            if not unique_sop_classes:
                FocusAwareMessageBox.warning(
                    self.main_window,
                    "No Valid DICOM Files",
                    "No valid DICOM files found for sending."
                )
                return
            
            # Create progress dialog
            from PyQt6.QtWidgets import QProgressDialog
            self.send_progress = QProgressDialog("Preparing DICOM send...", "Cancel", 0, 100, self.main_window)
            self.send_progress.setWindowTitle("DICOM Send Progress")
            self.send_progress.setMinimumDuration(0)
            self.send_progress.setValue(0)
            
            # Store total file count for progress calculation
            self.send_total_files = len(selected_files)
            
            # Create and start worker
            from fm_dicom.workers.dicom_send_worker import DicomSendWorker
            self.send_worker = DicomSendWorker(selected_files, send_params, list(unique_sop_classes))
            
            # Connect signals
            self.send_worker.progress_updated.connect(self._on_send_progress)
            self.send_worker.send_complete.connect(self._on_send_complete)
            self.send_worker.send_failed.connect(self._on_send_failed)
            self.send_worker.association_status.connect(self._on_send_status)
            self.send_worker.conversion_progress.connect(self._on_conversion_progress)
            self.send_progress.canceled.connect(self.send_worker.cancel)
            
            # Start worker
            self.send_worker.start()
            self.send_progress.show()
            
            logging.info(f"Started DICOM send for {len(selected_files)} files")
            
        except Exception as e:
            logging.error(f"Error starting DICOM send: {e}", exc_info=True)
            FocusAwareMessageBox.critical(
                self.main_window,
                "DICOM Send Error",
                f"Failed to start DICOM send:\n{str(e)}"
            )
    
    def _on_send_progress(self, current, success, warnings, failed, current_file):
        """Handle DICOM send progress updates"""
        import logging
        logging.debug(f"DicomManager: Send progress: {current}/{self.send_total_files} - {current_file}")
        
        if hasattr(self, 'send_progress') and hasattr(self, 'send_total_files'):
            # Calculate progress based on current file index vs total files
            if self.send_total_files > 0:
                progress_percent = int((current / self.send_total_files) * 100)
                self.send_progress.setValue(progress_percent)
            
            # Improve label text to distinguish between test and send phases
            if current_file.startswith("Testing "):
                # Extract actual filename from "Testing filename.dcm"
                actual_filename = current_file.replace("Testing ", "")
                self.send_progress.setLabelText(f"Checking compatibility: {actual_filename} ({current}/{self.send_total_files})")
            else:
                self.send_progress.setLabelText(f"Sending: {current_file} ({current}/{self.send_total_files})")
            
            # Make sure the dialog is visible after conversion phase
            if not self.send_progress.isVisible():
                logging.warning("DicomManager: Progress dialog was hidden, showing it again")
                self.send_progress.show()
    
    def _on_send_status(self, status):
        """Handle DICOM send status updates"""
        if hasattr(self, 'send_progress'):
            self.send_progress.setLabelText(status)
            
            # Make sure the dialog is visible
            if not self.send_progress.isVisible():
                self.send_progress.show()
    
    def _on_conversion_progress(self, current, total, message):
        """Handle DICOM conversion progress updates"""
        import logging
        logging.debug(f"DicomManager: Conversion progress: {current}/{total} - {message}")
        
        if hasattr(self, 'send_progress'):
            # Update progress bar based on conversion progress
            if total > 0:
                progress_percent = int((current / total) * 100)
                self.send_progress.setValue(progress_percent)
            self.send_progress.setLabelText(message)
            
            # Make sure the dialog is visible and not closed
            if not self.send_progress.isVisible():
                self.send_progress.show()
    
    def _on_send_complete(self, success, warnings, failed, error_details, converted_count, timing_info=None):
        """Handle DICOM send completion"""
        import logging
        logging.info("DicomManager: _on_send_complete called")
        
        if hasattr(self, 'send_progress'):
            self.send_progress.close()
        
        # Show results with timing breakdown
        msg = f"DICOM send complete.\nSuccess: {success}\nWarnings: {warnings}\nFailed: {failed}"
        if converted_count > 0:
            msg += f"\nConverted: {converted_count}"
        
        # Add timing information
        if timing_info:
            msg += "\n\nTiming Breakdown:"
            if timing_info.get('analysis_time', 0) > 0:
                msg += f"\nAnalysis: {timing_info['analysis_time']:.1f}s"
            if timing_info.get('compatibility_check_time', 0) > 0:
                msg += f"\nCompatibility Check: {timing_info['compatibility_check_time']:.1f}s"
            if timing_info.get('conversion_time', 0) > 0:
                msg += f"\nConversion: {timing_info['conversion_time']:.1f}s"
            if timing_info.get('send_time', 0) > 0:
                msg += f"\nSending: {timing_info['send_time']:.1f}s"
            if timing_info.get('total_time', 0) > 0:
                msg += f"\nTotal: {timing_info['total_time']:.1f}s"
        
        logging.info(f"DicomManager: About to show completion dialog with message: {msg}")
        
        if failed == 0:
            FocusAwareMessageBox.information(self.main_window, "DICOM Send Complete", msg)
        else:
            detailed_msg = msg
            if error_details:
                detailed_msg += "\n\nFirst few errors:\n" + "\n".join(error_details[:3])
            FocusAwareMessageBox.warning(self.main_window, "DICOM Send Completed with Errors", detailed_msg)
        
        logging.info(f"DICOM send completed: {success} success, {warnings} warnings, {failed} failed")
    
    def _on_send_failed(self, error_message):
        """Handle DICOM send failure"""
        if hasattr(self, 'send_progress'):
            self.send_progress.close()
        
        FocusAwareMessageBox.critical(
            self.main_window,
            "DICOM Send Failed",
            f"DICOM send failed:\n{error_message}"
        )
        
        logging.error(f"DICOM send failed: {error_message}")
    
    def has_unsaved_changes(self):
        """Check if there are unsaved tag changes"""
        return self._has_unsaved_changes
    
    def batch_edit_tags(self, file_paths):
        """Batch edit tags for multiple files"""
        if not file_paths:
            FocusAwareMessageBox.warning(
                self.main_window,
                "No Files",
                "No files selected for batch editing."
            )
            return
        
        # Show tag search dialog
        tag_dialog = TagSearchDialog(self.main_window, "Select Tag for Batch Edit")
        if tag_dialog.exec() != tag_dialog.DialogCode.Accepted:
            return
            
        tag_info = tag_dialog.get_selected_tag_info()
        if not tag_info['tag']:
            return
            
        # Parse the selected tag
        tag = None
        tag_str = tag_info['tag']
        
        if ',' in tag_str and tag_str.startswith("(") and tag_str.endswith(")"):
            # Handle hex format like (GGGG,EEEE)
            try:
                group, elem = tag_str[1:-1].split(',')
                tag = (int(group, 16), int(elem, 16))
            except ValueError:
                FocusAwareMessageBox.warning(self.main_window, "Invalid Tag", "Invalid tag format.")
                return
        else:
            # Handle keyword or custom tag names
            try:
                import pydicom
                # First try as a known DICOM keyword
                tag = pydicom.tag.Tag(tag_str.strip())
            except ValueError:
                # If not a known keyword, treat as custom private tag
                # Use private group 0x7777 for custom tags
                # Create a simple hash-based element number from the tag name
                import hashlib
                tag_hash = hashlib.md5(tag_str.encode()).hexdigest()
                # Use first 4 hex chars as element number, ensure it's odd (private)
                element = int(tag_hash[:4], 16)
                if element % 2 == 0:  # Make sure it's odd for private tags
                    element += 1
                tag = (0x7777, element)
                logging.info(f"Created custom private tag for '{tag_str}': {tag}")
                
                # Update tag_info to reflect the generated tag
                tag_info['tag'] = f"({tag[0]:04X},{tag[1]:04X})"
                tag_info['name'] = f"Custom Tag: {tag_str}"
                tag_info['vr'] = 'LO'  # Default VR for custom tags

        # Check if tag exists in sample file
        current_value = ""
        try:
            import pydicom
            ds_sample = pydicom.dcmread(file_paths[0], stop_before_pixels=True)
            if tag in ds_sample:
                current_value = str(ds_sample[tag].value)
            else:
                current_value = "<New Tag>"
        except Exception as e:
            FocusAwareMessageBox.critical(self.main_window, "Error", f"Could not read sample file: {e}")
            return

        # Show value entry dialog
        value_dialog = ValueEntryDialog(tag_info, current_value, self.main_window)
        value_dialog.setWindowTitle(f"Batch Edit: {tag_info['name']}")
        
        if value_dialog.exec() != value_dialog.DialogCode.Accepted:
            return
            
        new_value = value_dialog.new_value
        
        # Final confirmation with file count
        reply = FocusAwareMessageBox.question(
            self.main_window, "Confirm Batch Edit",
            f"This will update the tag '{tag_info['name']}' in {len(file_paths)} files.\n"
            f"New value: '{new_value}'\n\n"
            "This operation cannot be undone. Continue?",
            FocusAwareMessageBox.StandardButton.Yes | FocusAwareMessageBox.StandardButton.No,
            FocusAwareMessageBox.StandardButton.No
        )
        if reply != FocusAwareMessageBox.StandardButton.Yes:
            return

        # Perform batch edit
        self._perform_batch_edit(file_paths, tag, tag_info, new_value)
    
    def _perform_batch_edit(self, file_paths, tag, tag_info, new_value):
        """Perform the actual batch edit operation"""
        updated_count = 0
        failed_files = []
        
        from PyQt6.QtWidgets import QProgressDialog
        progress = QProgressDialog(f"Batch editing {tag_info['name']}...", "Cancel", 0, len(file_paths), self.main_window)
        progress.setWindowTitle("Batch Tag Edit")
        progress.setMinimumDuration(0)
        progress.setValue(0)

        for idx, filepath in enumerate(file_paths):
            progress.setValue(idx)
            if progress.wasCanceled():
                break
            QApplication.processEvents()
            
            try:
                import pydicom
                ds = pydicom.dcmread(filepath)
                
                # Determine VR
                if tag in ds:
                    vr = ds[tag].VR
                else:
                    vr = tag_info.get('vr', 'LO')
                    
                # Convert value
                converted_value = self._convert_value_by_vr(new_value, vr)
                
                # Update or add tag
                if tag in ds:
                    ds[tag].value = converted_value
                else:
                    ds.add_new(tag, vr, converted_value)
                    
                ds.save_as(filepath)
                updated_count += 1
                
            except Exception as e:
                failed_files.append(f"{os.path.basename(filepath)}: {str(e)}")
                logging.error(f"Failed to update {filepath}: {e}")
                
        progress.setValue(len(file_paths))
        
        # Show results
        msg = f"Batch edit complete.\nUpdated {updated_count} of {len(file_paths)} files."
        if failed_files:
            msg += f"\nFailed: {len(failed_files)} files."
            
        FocusAwareMessageBox.information(self.main_window, "Batch Edit Complete", msg)
        
        # Refresh current file display if it was part of the batch
        if hasattr(self, 'current_file') and self.current_file in file_paths:
            self.load_dicom_tags(self.current_file)
            
        # Refresh tree to show updated patient names and other hierarchy changes
        if hasattr(self.main_window, 'tree_manager') and self.main_window.tree_manager:
            self.main_window.tree_manager.refresh_tree()
            logging.info("Tree refreshed after batch edit")
    
    def _convert_value_by_vr(self, value, vr):
        """Convert string value to appropriate type based on VR"""
        if not value:
            return ""
            
        try:
            # Integer types
            if vr in ['US', 'SS', 'UL', 'SL', 'IS']:
                return int(value)
            # Float types  
            elif vr in ['FL', 'FD', 'DS']:
                return float(value)
            # Date/Time types - keep as string but could add validation
            elif vr in ['DA', 'TM', 'DT']:
                return str(value)
            # Default to string
            else:
                return str(value)
        except (ValueError, TypeError):
            # If conversion fails, return as string
            return str(value)