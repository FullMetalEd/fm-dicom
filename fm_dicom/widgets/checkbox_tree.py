"""
Tree widget with hierarchical checkbox behavior and tri-state logic.

This module provides an optimized tree widget for DICOM file selection with
hierarchical checkbox behavior and proper tri-state logic.
"""

import os
import logging
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem
from PyQt6.QtCore import Qt, pyqtSignal


class OptimizedCheckboxTreeWidget(QTreeWidget):
    """Tree widget with hierarchical checkbox behavior and tri-state logic"""
    
    selection_changed = pyqtSignal(list)  # Emits list of selected file paths
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Item", "Files", "Size"])
        self.setColumnWidth(0, 300)
        self.setColumnWidth(1, 80)
        self.setColumnWidth(2, 80)
        
        # Enable checkboxes
        self.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        self.setRootIsDecorated(True)  # Show expand/collapse icons
        
        # Connect signals
        self.itemChanged.connect(self._on_item_changed)
        
        # Track programmatic changes to avoid recursion
        self._updating_programmatically = False
        
    def _on_item_changed(self, item, column):
        if column != 0 or self._updating_programmatically:
            return
        
        # Prevent recursive calls
        self._updating_programmatically = True
        
        try:
            check_state = item.checkState(0)
            
            # Check if this is a leaf node (instance) or parent node
            if item.childCount() == 0:
                # This is a leaf node (instance) - only update parents
                self._update_parent_chain(item)
            else:
                # This is a parent node - update children then parents
                self._update_children_recursive(item, check_state)
                self._update_parent_chain(item)
            
            # Emit selection changed
            self._emit_selection_changed()
            
        except Exception as e:
            logging.error(f"Error in checkbox update: {e}", exc_info=True)
        finally:
            self._updating_programmatically = False
    
    def _update_children_recursive(self, parent_item, check_state):
        """Update all children to match parent state"""
        try:
            for i in range(parent_item.childCount()):
                child = parent_item.child(i)
                if child:
                    child.setCheckState(0, check_state)
                    # Recursively update grandchildren
                    self._update_children_recursive(child, check_state)
        except Exception as e:
            logging.warning(f"Error updating children: {e}")
    
    def _update_parent_chain(self, child_item):
        """Update parent chain from this item upward"""
        try:
            current = child_item.parent()
            while current is not None:
                self._update_single_parent(current)
                current = current.parent()
        except Exception as e:
            logging.warning(f"Error updating parent chain: {e}")
    
    def _update_single_parent(self, parent_item):
        """Update a single parent based on its children"""
        try:
            if not parent_item:
                return
                
            total_children = parent_item.childCount()
            if total_children == 0:
                return
                
            checked_children = 0
            partially_checked_children = 0
            
            for i in range(total_children):
                child = parent_item.child(i)
                if child:
                    state = child.checkState(0)
                    if state == Qt.CheckState.Checked:
                        checked_children += 1
                    elif state == Qt.CheckState.PartiallyChecked:
                        partially_checked_children += 1
            
            # Determine parent state
            if checked_children == total_children:
                parent_item.setCheckState(0, Qt.CheckState.Checked)
            elif checked_children == 0 and partially_checked_children == 0:
                parent_item.setCheckState(0, Qt.CheckState.Unchecked)
            else:
                parent_item.setCheckState(0, Qt.CheckState.PartiallyChecked)
                
        except Exception as e:
            logging.warning(f"Error updating single parent: {e}")
    
    def _emit_selection_changed(self):
        """Emit list of selected file paths"""
        try:
            selected_files = self.get_selected_files()
            self.selection_changed.emit(selected_files)
        except Exception as e:
            logging.warning(f"Error emitting selection changed: {e}")
    
    def get_selected_files(self):
        """Return list of selected file paths - only from leaf nodes"""
        selected_files = []
        try:
            self._collect_checked_files(self.invisibleRootItem(), selected_files)
        except Exception as e:
            logging.warning(f"Error collecting selected files: {e}")
        return selected_files
    
    def _collect_checked_files(self, item, file_list):
        """Recursively collect checked files from leaf nodes only"""
        try:
            for i in range(item.childCount()):
                child = item.child(i)
                if not child:
                    continue
                
                # Only collect from leaf nodes (instances)
                if child.childCount() == 0:
                    # This is a leaf node - check if it's selected and has file path
                    file_path = child.data(0, Qt.ItemDataRole.UserRole)
                    if file_path and child.checkState(0) == Qt.CheckState.Checked:
                        file_list.append(file_path)
                else:
                    # This is a parent node - recurse into children
                    self._collect_checked_files(child, file_list)
                    
        except Exception as e:
            logging.warning(f"Error collecting files from item: {e}")
    
    def set_initial_selection(self, file_paths):
        """Set initial selection based on file paths"""
        if not file_paths:
            return
            
        self._updating_programmatically = True
        
        try:
            # Convert to set for faster lookup
            selected_paths = set(file_paths)
            
            # Mark leaf items as checked if their file path is in selection
            self._mark_initial_selection(self.invisibleRootItem(), selected_paths)
            
            # Update all parent states from bottom up
            self._update_all_parents_bottom_up()
            
        except Exception as e:
            logging.error(f"Error setting initial selection: {e}", exc_info=True)
        finally:
            self._updating_programmatically = False
            
        self._emit_selection_changed()
    
    def _mark_initial_selection(self, item, selected_paths):
        """Mark leaf items as checked based on file paths"""
        try:
            for i in range(item.childCount()):
                child = item.child(i)
                if not child:
                    continue
                
                if child.childCount() == 0:
                    # This is a leaf node - check if it should be selected
                    file_path = child.data(0, Qt.ItemDataRole.UserRole)
                    if file_path and file_path in selected_paths:
                        child.setCheckState(0, Qt.CheckState.Checked)
                    else:
                        child.setCheckState(0, Qt.CheckState.Unchecked)
                else:
                    # This is a parent node - recurse and set to unchecked initially
                    child.setCheckState(0, Qt.CheckState.Unchecked)
                    self._mark_initial_selection(child, selected_paths)
                    
        except Exception as e:
            logging.warning(f"Error marking initial selection: {e}")
    
    def _update_all_parents_bottom_up(self):
        """Update all parent states from bottom up"""
        try:
            # Get all items in tree
            all_items = []
            self._collect_all_items(self.invisibleRootItem(), all_items)
            
            # Process leaf nodes first to update their parents
            for item in all_items:
                if item.childCount() == 0:  # Leaf node
                    self._update_parent_chain(item)
                    
        except Exception as e:
            logging.warning(f"Error updating all parents: {e}")
    
    def _collect_all_items(self, item, item_list):
        """Collect all items in the tree"""
        try:
            for i in range(item.childCount()):
                child = item.child(i)
                if child:
                    item_list.append(child)
                    self._collect_all_items(child, item_list)
        except Exception as e:
            logging.warning(f"Error collecting all items: {e}")
    
    def select_all(self):
        """Check all leaf items"""
        self._updating_programmatically = True
        try:
            self._set_all_leaf_items_state(self.invisibleRootItem(), Qt.CheckState.Checked)
            # Update parents after setting all leaves
            self._update_all_parents_bottom_up()
        except Exception as e:
            logging.warning(f"Error selecting all: {e}")
        finally:
            self._updating_programmatically = False
        self._emit_selection_changed()
    
    def select_none(self):
        """Uncheck all items"""
        self._updating_programmatically = True
        try:
            self._set_all_items_state(self.invisibleRootItem(), Qt.CheckState.Unchecked)
        except Exception as e:
            logging.warning(f"Error selecting none: {e}")
        finally:
            self._updating_programmatically = False
        self._emit_selection_changed()
    
    def _set_all_leaf_items_state(self, item, state):
        """Set state only for leaf items"""
        try:
            for i in range(item.childCount()):
                child = item.child(i)
                if child:
                    if child.childCount() == 0:  # Leaf node
                        child.setCheckState(0, state)
                    else:  # Parent node
                        self._set_all_leaf_items_state(child, state)
        except Exception as e:
            logging.warning(f"Error setting leaf items state: {e}")
    
    def _set_all_items_state(self, item, state):
        """Recursively set state for all items"""
        try:
            for i in range(item.childCount()):
                child = item.child(i)
                if child:
                    child.setCheckState(0, state)
                    self._set_all_items_state(child, state)
        except Exception as e:
            logging.warning(f"Error setting all items state: {e}")