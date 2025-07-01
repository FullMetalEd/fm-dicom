"""
Refactored MainWindow using mixins and manager classes - FIXED VERSION.

This version of MainWindow uses the hybrid approach with:
- UI Layout that EXACTLY matches the original 
- Manager classes for business logic
- Proper signal/slot connections
"""

import os
import sys
import logging
import platform
import time
from PyQt6.QtWidgets import QMainWindow, QApplication, QMenu
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtCore import Qt, QPoint, QTimer

# Configuration and setup imports
from fm_dicom.config.config_manager import load_config, setup_logging, get_default_user_dir
from fm_dicom.config.dicom_setup import setup_gdcm_integration
from fm_dicom.themes.theme_manager import set_light_palette, set_dark_palette

# UI Layout - EXACT match to original
from fm_dicom.ui.layout_mixin import LayoutMixin

# Manager classes
from fm_dicom.managers.file_manager import FileManager
from fm_dicom.managers.tree_manager import TreeManager
from fm_dicom.managers.dicom_manager import DicomManager

# Existing modules that will be preserved
from fm_dicom.anonymization.anonymization import TemplateManager
from fm_dicom.widgets.focus_aware import FocusAwareMessageBox, FocusAwareProgressDialog
from fm_dicom.dialogs.utility_dialogs import LogViewerDialog, SettingsEditorDialog
from fm_dicom.dialogs.results_dialogs import FileAnalysisResultsDialog, PerformanceResultsDialog
from fm_dicom.workers.export_worker import ExportWorker

# Keep the pynetdicom imports for DICOM operations
from pynetdicom import AE, AllStoragePresentationContexts
from pynetdicom.sop_class import Verification
VERIFICATION_SOP_CLASS = Verification
STORAGE_CONTEXTS = AllStoragePresentationContexts

# Setup GDCM integration
setup_gdcm_integration()


class MainWindow(QMainWindow, LayoutMixin):
    """
    Refactored MainWindow using exact original UI + managers.
    
    This class serves as the main orchestrator, coordinating between:
    - EXACT original UI layout (via LayoutMixin)
    - Business logic (via managers)
    - Event handling and signal coordination
    """
    
    def __init__(self, start_path=None, config_path_override=None):
        super().__init__()
        
        # Initialize configuration and logging first
        self._setup_configuration(config_path_override)
        self._setup_logging()
        self._apply_theme()
        
        # Initialize template manager
        self._setup_template_manager()
        
        # Setup UI using layout mixin - EXACT original layout
        self.setup_ui_layout()
        
        # Initialize managers
        self._setup_managers()
        
        # Connect signals between managers and UI
        self._setup_signal_connections()
        
        # Initialize state
        self.loaded_files = []
        self.selected_files = []
        self.current_file = None
        self.current_file_path = None  # For image display compatibility
        
        # Handle start path
        if start_path:
            self.pending_start_path = start_path
            QTimer.singleShot(100, self.load_pending_start_path)
        
        logging.info("MainWindow initialized successfully")
    
    def _setup_configuration(self, config_path_override):
        """Setup application configuration"""
        self.config = load_config(config_path_override=config_path_override)
        
        # Set config attributes for compatibility
        self.dicom_send_config = self.config
        self.default_export_dir = self.config.get("default_export_dir")
        self.default_import_dir = self.config.get("default_import_dir")
        
        # Fallbacks for missing paths
        if not self.default_export_dir:
            self.default_export_dir = os.path.join(get_default_user_dir(), "DICOM_Exports")
        if not self.default_import_dir:
            downloads_dir = os.path.join(get_default_user_dir(), "Downloads")
            self.default_import_dir = downloads_dir if os.path.isdir(downloads_dir) else get_default_user_dir()
    
    def _setup_logging(self):
        """Setup application logging"""
        setup_logging(self.config.get("log_path"), self.config.get("log_level", "INFO"))
        logging.info("Application started")
        logging.debug(f"Loaded configuration: {self.config}")
    
    def _apply_theme(self):
        """Apply theme from configuration"""
        QApplication.setStyle("Fusion")
        current_theme = self.config.get("theme", "dark").lower()
        if current_theme == "dark":
            set_dark_palette(QApplication.instance())
        else:
            set_light_palette(QApplication.instance())
    
    def _setup_template_manager(self):
        """Setup anonymization template manager"""
        system = platform.system()
        app_name = "fm-dicom"
        
        if system == "Windows":
            appdata = os.environ.get("APPDATA")
            config_dir = os.path.join(appdata if appdata else os.path.dirname(sys.executable), app_name)
        elif system == "Darwin":
            config_dir = os.path.expanduser(f"~/Library/Application Support/{app_name}")
        else:
            xdg_config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
            config_dir = os.path.join(xdg_config_home, app_name)
        
        os.makedirs(config_dir, exist_ok=True)
        self.template_manager = TemplateManager(config_dir)
    
    def _setup_managers(self):
        """Initialize all manager classes"""
        self.file_manager = FileManager(self)
        self.tree_manager = TreeManager(self)
        self.dicom_manager = DicomManager(self)
    
    def _setup_signal_connections(self):
        """Setup signal connections between managers and UI"""
        # File manager signals
        self.file_manager.files_loaded.connect(self.tree_manager.populate_tree)
        self.file_manager.loading_started.connect(lambda: self.status_bar.showMessage("Loading files..."))
        self.file_manager.loading_finished.connect(lambda: self.status_bar.showMessage("Ready"))
        
        # Tree manager signals  
        self.tree_manager.selection_changed.connect(self._on_tree_selection_changed)
        self.tree_manager.tree_populated.connect(self._on_tree_populated)
        
        # DICOM manager signals
        self.dicom_manager.tag_data_changed.connect(self._on_tag_data_changed)
        self.dicom_manager.image_loaded.connect(self._on_image_loaded)
    
    # Event handlers and coordination methods
    def _on_tree_selection_changed(self, file_paths):
        """Handle tree selection changes"""
        self.selected_files = file_paths
        
        # Load first selected file for tag editing
        if file_paths:
            self.current_file = file_paths[0]
            self.current_file_path = file_paths[0]  # For compatibility
            self.dicom_manager.load_dicom_tags(self.current_file)
        else:
            self.current_file = None
            self.current_file_path = None
            self.dicom_manager.clear_tag_table()
    
    def _on_tree_populated(self, file_count):
        """Handle tree population completion"""
        self.loaded_files = self.tree_manager.get_loaded_files()
        logging.info(f"Loaded {file_count} DICOM files")
    
    def _on_tag_data_changed(self):
        """Handle DICOM tag data changes"""
        # This is where we could add auto-save functionality or change indicators
        pass
    
    def _on_image_loaded(self, pixmap):
        """Handle image loading completion"""
        # This is where we could add image processing or analysis
        pass
    
    # Delegate methods to managers (these maintain the existing API)
    def open_file(self):
        """Open a DICOM file - delegates to FileManager"""
        self.file_manager.open_file()
    
    def open_directory(self):
        """Open a directory - delegates to FileManager"""
        self.file_manager.open_directory()
    
    def load_path(self, path):
        """Load files from path - delegates to FileManager"""
        self.file_manager.load_path(path)
    
    def load_pending_start_path(self):
        """Load the pending start path after window is shown"""
        if hasattr(self, 'pending_start_path') and self.pending_start_path:
            path = self.pending_start_path
            self.pending_start_path = None
            
            if not self.isVisible():
                self.show()
                QApplication.processEvents()
            
            self.load_path(path)
    
    def display_selected_tree_file(self):
        """Handle tree selection changed - handled by TreeManager signals"""
        pass  # This is now handled by signal connections
    
    def filter_tree_items(self, text):
        """Filter tree items - delegates to TreeManager"""
        self.tree_manager.filter_tree_items(text)
    
    def filter_tag_table(self, text):
        """Filter tag table - delegates to DicomManager"""
        self.dicom_manager.filter_tag_table(text)
    
    def delete_selected_items(self):
        """Delete selected items - delegates to TreeManager"""
        self.tree_manager.delete_selected_items()
    
    def save_tag_changes(self):
        """Save tag changes - delegates to DicomManager"""
        self.dicom_manager.save_tag_changes()
    
    def revert_tag_changes(self):
        """Revert tag changes - delegates to DicomManager"""
        self.dicom_manager.revert_tag_changes()
    
    def validate_dicom_files(self):
        """Validate selected items - delegates to DicomManager"""
        self.dicom_manager.validate_selected_items(self.selected_files)
    
    def anonymise_selected(self):
        """Anonymize selected items - delegates to DicomManager"""
        self.dicom_manager.anonymize_selected_items(self.selected_files)
    
    def edit_tag(self):
        """Show tag search dialog - delegates to DicomManager"""
        self.dicom_manager.show_tag_search_dialog()
    
    def dicom_send(self):
        """Show DICOM send dialog - delegates to DicomManager"""
        selected_items = self.tree.selectedItems() if hasattr(self, 'tree') else []
        self.dicom_manager.show_dicom_send_dialog(self.selected_files, selected_items)
    
    def display_image(self):
        """Display image - delegates to DicomManager"""
        self.dicom_manager.display_image()
    
    # Context menu and merge functionality (preserved from original)
    def show_tree_context_menu(self, pos: QPoint):
        """Show enhanced tree context menu with all editing operations"""
        item = self.tree.itemAt(pos)
        if not item:
            return
        
        selected = self.tree.selectedItems()
        
        menu = QMenu(self)
        
        # View Details (for single item)
        if len(selected) == 1:
            details_action = QAction("📄 View Details", self)
            details_action.setShortcut(QKeySequence("Enter"))
            details_action.triggered.connect(lambda: self.display_selected_tree_file())
            menu.addAction(details_action)
            
            edit_tags_action = QAction("📝 Edit Tags...", self)
            edit_tags_action.triggered.connect(lambda: self.display_selected_tree_file())
            menu.addAction(edit_tags_action)
            
            menu.addSeparator()
        
        # Tag operations
        new_tag_action = QAction("➕ New Tag...", self)
        new_tag_action.setShortcut(QKeySequence("Ctrl+T"))
        new_tag_action.triggered.connect(self.edit_tag)
        menu.addAction(new_tag_action)
        
        batch_tag_action = QAction("📦 Batch New Tag...", self)
        batch_tag_action.setShortcut(QKeySequence("Ctrl+Shift+T"))
        batch_tag_action.triggered.connect(self.batch_edit_tag)
        menu.addAction(batch_tag_action)
        
        menu.addSeparator()
        
        # Patient/Study operations
        if len(selected) > 1:
            merge_action = QAction("🔀 Merge Selected", self)
            merge_action.setShortcut(QKeySequence("Ctrl+M"))
            merge_action.triggered.connect(self.merge_patients)
            menu.addAction(merge_action)
        
        delete_action = QAction("🗑️ Delete Selected", self)
        delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        delete_action.triggered.connect(self.delete_selected_items)
        menu.addAction(delete_action)
        
        menu.addSeparator()
        
        # Validation and Anonymization
        validate_action = QAction("✅ Validate", self)
        validate_action.setShortcut(QKeySequence("Ctrl+V"))
        validate_action.triggered.connect(self.validate_dicom_files)
        menu.addAction(validate_action)
        
        anon_action = QAction("🎭 Anonymize", self)
        anon_action.setShortcut(QKeySequence("Ctrl+A"))
        anon_action.triggered.connect(self.anonymise_selected)
        menu.addAction(anon_action)
        
        menu.addSeparator()
        
        # Export and Send
        send_action = QAction("📤 Send via DICOM...", self)
        send_action.setShortcut(QKeySequence("Ctrl+D"))
        send_action.triggered.connect(self.dicom_send)
        menu.addAction(send_action)
        
        save_as_action = QAction("💾 Save As...", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self.save_as)
        menu.addAction(save_as_action)
        
        menu.addSeparator()
        
        # Tree navigation
        if item.childCount() > 0:
            expand_action = QAction("🔍 Expand All Children", self)
            expand_action.triggered.connect(lambda: self._expand_item_recursively(item))
            menu.addAction(expand_action)
            
            collapse_action = QAction("📁 Collapse All Children", self)
            collapse_action.triggered.connect(lambda: self._collapse_item_recursively(item))
            menu.addAction(collapse_action)
        
        # Show context menu
        menu.exec(self.tree.viewport().mapToGlobal(pos))
    
    def _expand_item_recursively(self, item):
        """Expand item and all its children recursively"""
        item.setExpanded(True)
        for i in range(item.childCount()):
            self._expand_item_recursively(item.child(i))
    
    def _collapse_item_recursively(self, item):
        """Collapse item and all its children recursively"""
        for i in range(item.childCount()):
            self._collapse_item_recursively(item.child(i))
        item.setExpanded(False)
    
    def show_tag_table_context_menu(self, pos: QPoint):
        """Show enhanced tag table context menu for tag-specific operations"""
        if not hasattr(self, 'tag_table'):
            return
        
        row = self.tag_table.rowAt(pos.y())
        if row < 0:
            return
            
        # Get the tag at this row
        tag_id_item = self.tag_table.item(row, 0)
        desc_item = self.tag_table.item(row, 1)
        value_item = self.tag_table.item(row, 2)
        new_value_item = self.tag_table.item(row, 3)
        
        if not tag_id_item:
            return
            
        tag_id = tag_id_item.text()
        description = desc_item.text() if desc_item else "Unknown"
        current_value = value_item.text() if value_item else ""
        new_value = new_value_item.text() if new_value_item else ""
        
        menu = QMenu(self)
        
        # Edit Value
        edit_icon = self.style().standardIcon(self.style().StandardPixmap.SP_FileDialogListView)
        edit_action = QAction(edit_icon, "✏️ Edit Value", self)
        edit_action.triggered.connect(lambda: self._edit_tag_value_at_row(row))
        menu.addAction(edit_action)
        
        # Add New Tag
        add_icon = self.style().standardIcon(self.style().StandardPixmap.SP_FileDialogNewFolder)
        add_action = QAction(add_icon, "➕ Add New Tag...", self)
        add_action.setShortcut(QKeySequence("Ctrl+T"))
        add_action.triggered.connect(self.edit_tag)
        menu.addAction(add_action)
        
        # Remove tag (if it has a new value)
        if new_value:
            remove_icon = self.style().standardIcon(self.style().StandardPixmap.SP_DialogCancelButton)
            remove_action = QAction(remove_icon, "🗑️ Clear Edit", self)
            remove_action.triggered.connect(lambda: self._clear_tag_edit_at_row(row))
            menu.addAction(remove_action)
        
        menu.addSeparator()
        
        # Copy operations
        copy_icon = self.style().standardIcon(self.style().StandardPixmap.SP_FileDialogDetailedView)
        copy_tag_action = QAction(copy_icon, "📋 Copy Tag ID", self)
        copy_tag_action.triggered.connect(lambda: self._copy_to_clipboard(tag_id))
        menu.addAction(copy_tag_action)
        
        copy_value_action = QAction(copy_icon, "📋 Copy Value", self)
        copy_value_action.triggered.connect(lambda: self._copy_to_clipboard(current_value))
        menu.addAction(copy_value_action)
        
        if description != "Unknown":
            copy_desc_action = QAction(copy_icon, "📋 Copy Description", self)
            copy_desc_action.triggered.connect(lambda: self._copy_to_clipboard(description))
            menu.addAction(copy_desc_action)
        
        menu.addSeparator()
        
        # Find Similar Tags
        search_icon = self.style().standardIcon(self.style().StandardPixmap.SP_FileDialogInfoView)
        search_action = QAction(search_icon, "🔍 Find Similar Tags...", self)
        search_action.triggered.connect(lambda: self._find_similar_tags(description))
        menu.addAction(search_action)
        
        # Show context menu
        menu.exec(self.tag_table.viewport().mapToGlobal(pos))
    
    def _edit_tag_value_at_row(self, row):
        """Edit the tag value at the specified row"""
        if row < 0 or row >= self.tag_table.rowCount():
            return
            
        # Focus on the "New Value" column for this row
        new_value_item = self.tag_table.item(row, 3)
        if new_value_item:
            self.tag_table.setCurrentItem(new_value_item)
            self.tag_table.editItem(new_value_item)
    
    def _clear_tag_edit_at_row(self, row):
        """Clear the tag edit at the specified row"""
        if row < 0 or row >= self.tag_table.rowCount():
            return
            
        new_value_item = self.tag_table.item(row, 3)
        if new_value_item:
            new_value_item.setText("")
    
    def _copy_to_clipboard(self, text):
        """Copy text to clipboard"""
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        
        # Show brief status message
        if hasattr(self, 'status_bar'):
            self.status_bar.showMessage(f"Copied to clipboard: {text[:50]}{'...' if len(text) > 50 else ''}", 2000)
    
    def _find_similar_tags(self, description):
        """Find similar tags by filtering the tag table"""
        if not hasattr(self, 'search_bar') or not description:
            return
            
        # Extract key words from description for search
        search_terms = []
        common_words = {'the', 'and', 'or', 'of', 'in', 'to', 'for', 'with', 'by'}
        words = description.lower().split()
        for word in words:
            if len(word) > 3 and word not in common_words:
                search_terms.append(word)
        
        if search_terms:
            # Use the first meaningful word for search
            search_term = search_terms[0]
            self.search_bar.setText(search_term)
            
            # Show status message
            if hasattr(self, 'status_bar'):
                self.status_bar.showMessage(f"Searching for tags containing '{search_term}'", 2000)
    
    # Settings and utility dialogs (original methods preserved)
    def open_settings_editor(self):
        """Show settings dialog"""
        dialog = SettingsEditorDialog(self.config, "config.yaml", self)
        if dialog.exec():
            # Apply any settings changes
            if hasattr(dialog, 'new_config'):
                self.config.update(dialog.new_config)
    
    def show_log_viewer(self):
        """Show log viewer dialog"""
        log_path = self.config.get("log_path")
        if log_path and os.path.exists(log_path):
            dialog = LogViewerDialog(log_path, self)
            dialog.show()
        else:
            FocusAwareMessageBox.information(
                self, "No Log File", 
                "No log file found or logging is not configured."
            )
    
    def manage_templates(self):
        """Manage anonymization templates"""
        # This would use the template manager
        FocusAwareMessageBox.information(self, "Templates", "Template management functionality")
    
    def batch_edit_tag(self):
        """Batch edit tags using searchable interface with selection validation"""
        selected = self.tree.selectedItems() if hasattr(self, 'tree') else []
        if not selected:
            FocusAwareMessageBox.warning(self, "No Selection", "Please select a node in the tree.")
            return
        
        # Check selection level and provide guidance
        selection_info = self._analyze_batch_edit_selection(selected)
        
        if not selection_info['is_valid']:
            FocusAwareMessageBox.warning(self, "Invalid Selection for Batch Edit", selection_info['message'])
            return
        
        # If we have a valid selection, show info about what will be edited
        if selection_info['show_confirmation']:
            reply = FocusAwareMessageBox.question(
                self, "Confirm Batch Edit Scope",
                selection_info['confirmation_message'],
                FocusAwareMessageBox.StandardButton.Yes | FocusAwareMessageBox.StandardButton.No,
                FocusAwareMessageBox.StandardButton.Yes
            )
            if reply != FocusAwareMessageBox.StandardButton.Yes:
                return
        
        # Collect files from the selection
        filepaths = []
        for item in selected:
            item_files = self.tree_manager._collect_instance_filepaths(item)
            filepaths.extend(item_files)
        
        # Remove duplicates
        filepaths = list(set(filepaths))
        
        if not filepaths:
            FocusAwareMessageBox.warning(self, "No Instances", "No DICOM instances found under the selected nodes.")
            return
        
        # Delegate to DICOM manager for batch edit functionality
        self.dicom_manager.batch_edit_tags(filepaths)
    
    def _analyze_batch_edit_selection(self, selected_items):
        """Analyze the selection to determine if it's appropriate for batch editing"""
        
        if not selected_items:
            return {
                'is_valid': False,
                'message': "Please select a node in the tree.",
                'show_confirmation': False
            }
        
        # Analyze what types of nodes are selected
        depths = [self._get_tree_item_depth(item) for item in selected_items]
        unique_depths = set(depths)
        
        # Check for single instance selection
        if len(selected_items) == 1 and depths[0] == 3:  # Single instance node
            return {
                'is_valid': False,
                'message': (
                    "Batch edit requires multiple files to edit.\n\n"
                    "To batch edit:\n"
                    "• Select a Series node (edits all instances in that series)\n"
                    "• Select a Study node (edits all instances in that study)\n"
                    "• Select a Patient node (edits all instances for that patient)\n"
                    "• Hold Ctrl and select multiple individual instances\n"
                    "• Hold Ctrl and select multiple series/studies/patients"
                ),
                'show_confirmation': False
            }
        
        # Multiple instances selected
        if all(depth == 3 for depth in depths):
            instance_count = len(selected_items)
            return {
                'is_valid': True,
                'message': '',
                'show_confirmation': True,
                'confirmation_message': (
                    f"You have selected {instance_count} individual instances.\n\n"
                    f"This will batch edit tags in these {instance_count} specific files.\n\n"
                    "Continue with batch edit?"
                )
            }
        
        # Series level selection(s)
        if all(depth == 2 for depth in depths):
            series_count = len(selected_items)
            total_files = sum(len(self.tree_manager._collect_instance_filepaths(item)) for item in selected_items)
            return {
                'is_valid': True,
                'message': '',
                'show_confirmation': True,
                'confirmation_message': (
                    f"You have selected {series_count} series.\n\n"
                    f"This will batch edit tags in all {total_files} instances across these series.\n\n"
                    "Continue with batch edit?"
                )
            }
        
        # Study level selection(s)
        if all(depth == 1 for depth in depths):
            study_count = len(selected_items)
            total_files = sum(len(self.tree_manager._collect_instance_filepaths(item)) for item in selected_items)
            return {
                'is_valid': True,
                'message': '',
                'show_confirmation': True,
                'confirmation_message': (
                    f"You have selected {study_count} studies.\n\n"
                    f"This will batch edit tags in all {total_files} instances across these studies.\n\n"
                    "Continue with batch edit?"
                )
            }
        
        # Patient level selection(s)
        if all(depth == 0 for depth in depths):
            patient_count = len(selected_items)
            total_files = sum(len(self.tree_manager._collect_instance_filepaths(item)) for item in selected_items)
            return {
                'is_valid': True,
                'message': '',
                'show_confirmation': True,
                'confirmation_message': (
                    f"You have selected {patient_count} patients.\n\n"
                    f"This will batch edit tags in all {total_files} instances for these patients.\n\n"
                    "Continue with batch edit?"
                )
            }
        
        # Mixed selection
        return {
            'is_valid': True,
            'message': '',
            'show_confirmation': True,
            'confirmation_message': (
                f"You have selected {len(selected_items)} items at different levels.\n\n"
                "This will batch edit tags in all instances under the selected nodes.\n\n"
                "Continue with batch edit?"
            )
        }
    
    def _get_tree_item_depth(self, item):
        """Calculate the depth of a tree item (0 = root level)"""
        depth = 0
        current = item
        while current.parent():
            depth += 1
            current = current.parent()
        return depth
    
    def merge_patients(self):
        """Merge selected items (patients, studies, or series)"""
        from PyQt6.QtWidgets import QInputDialog, QTreeWidget
        
        # Allow multi-select for this operation
        if hasattr(self, 'tree'):
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.MultiSelection)
        
        selected = self.tree.selectedItems() if hasattr(self, 'tree') else []
        if len(selected) < 2:
            FocusAwareMessageBox.warning(
                self, "Merge Items", 
                "Select at least two items to merge.\nHold Ctrl or Shift to select multiple items."
            )
            if hasattr(self, 'tree'):
                self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return
        
        # Determine what type of merge this is based on the selection
        depths = [self._get_tree_item_depth(item) for item in selected]
        unique_depths = set(depths)
        
        if len(unique_depths) > 1:
            FocusAwareMessageBox.warning(
                self, "Invalid Selection", 
                "All selected items must be at the same level (all patients, all studies, or all series)."
            )
            if hasattr(self, 'tree'):
                self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return
        
        depth = depths[0]
        
        # Determine merge type and perform appropriate merge
        if depth == 0:  # Patient level
            self._merge_patients(selected)
        elif depth == 1:  # Study level
            self._merge_studies(selected)
        elif depth == 2:  # Series level
            self._merge_series(selected)
        else:
            FocusAwareMessageBox.warning(
                self, "Invalid Selection", 
                "Cannot merge individual instances. Select patients, studies, or series to merge."
            )
        
        # Restore selection mode
        if hasattr(self, 'tree'):
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
    
    def _merge_patients(self, patient_nodes):
        """Merge selected patients"""
        from PyQt6.QtWidgets import QInputDialog
        
        patient_labels = [item.text(0) for item in patient_nodes]
        primary_label_selected, ok = QInputDialog.getItem(
            self, "Merge Patients", "Select primary patient (whose metadata to keep):", patient_labels, 0, False
        )
        if not ok or not primary_label_selected:
            return
        
        primary_node = next(item for item in patient_nodes if item.text(0) == primary_label_selected)

        primary_fp_sample = None
        # Get a sample file from primary patient
        primary_node_fps = self.tree_manager._collect_instance_filepaths(primary_node)
        if primary_node_fps: 
            primary_fp_sample = primary_node_fps[0]

        if not primary_fp_sample:
            FocusAwareMessageBox.warning(
                self, "Merge Patients", 
                f"Could not find any DICOM file for the primary patient '{primary_label_selected}' to get ID/Name."
            )
            return
            
        try:
            import pydicom
            ds_primary = pydicom.dcmread(primary_fp_sample, stop_before_pixels=True)
            primary_id_val = str(ds_primary.PatientID)
            primary_name_val = str(ds_primary.PatientName)
        except Exception as e:
            FocusAwareMessageBox.critical(
                self, "Merge Patients", 
                f"Failed to read primary patient file: {e}"
            )
            return

        files_to_update = []
        secondary_nodes_to_process = [node for node in patient_nodes if node is not primary_node]
        for node_sec in secondary_nodes_to_process:
            files_to_update.extend(self.tree_manager._collect_instance_filepaths(node_sec))

        if not files_to_update:
            FocusAwareMessageBox.information(
                self, "Merge Patients", 
                "No files found in the secondary patient(s) to merge."
            )
            return

        reply = FocusAwareMessageBox.question(
            self, "Confirm Patient Merge",
            f"This will update {len(files_to_update)} files from other patient(s) to PatientID '{primary_id_val}' and PatientName '{primary_name_val}'.\n"
            "The original patient entries for these merged studies will be removed from the tree view.\n"
            "This modifies files in-place. Continue?",
            FocusAwareMessageBox.StandardButton.Yes | FocusAwareMessageBox.StandardButton.No, 
            FocusAwareMessageBox.StandardButton.No
        )
        if reply != FocusAwareMessageBox.StandardButton.Yes:
            return

        self._perform_patient_merge(files_to_update, primary_id_val, primary_name_val)
    
    def _merge_studies(self, study_nodes):
        """Merge selected studies under the same patient"""
        from PyQt6.QtWidgets import QInputDialog
        
        # Check that all studies are under the same patient
        patients = set()
        for study in study_nodes:
            if study.parent():
                patients.add(study.parent().text(0))
        
        if len(patients) > 1:
            FocusAwareMessageBox.warning(
                self, "Invalid Selection", 
                "All selected studies must be under the same patient."
            )
            return
        
        study_labels = [item.text(1) for item in study_nodes]  # Study is in column 1
        primary_label_selected, ok = QInputDialog.getItem(
            self, "Merge Studies", "Select primary study (whose metadata to keep):", study_labels, 0, False
        )
        if not ok or not primary_label_selected:
            return
        
        primary_node = next(item for item in study_nodes if item.text(1) == primary_label_selected)
        
        # Get primary study's UID and description
        primary_fp_sample = None
        primary_node_fps = self.tree_manager._collect_instance_filepaths(primary_node)
        if primary_node_fps:
            primary_fp_sample = primary_node_fps[0]
        
        if not primary_fp_sample:
            FocusAwareMessageBox.warning(
                self, "Merge Studies", 
                f"Could not find any DICOM file for the primary study."
            )
            return
        
        try:
            import pydicom
            ds_primary = pydicom.dcmread(primary_fp_sample, stop_before_pixels=True)
            primary_study_uid = str(ds_primary.StudyInstanceUID)
            primary_study_desc = str(getattr(ds_primary, 'StudyDescription', ''))
        except Exception as e:
            FocusAwareMessageBox.critical(
                self, "Merge Studies", 
                f"Failed to read primary study file: {e}"
            )
            return
        
        files_to_update = []
        secondary_nodes = [node for node in study_nodes if node is not primary_node]
        for node_sec in secondary_nodes:
            files_to_update.extend(self.tree_manager._collect_instance_filepaths(node_sec))
        
        if not files_to_update:
            FocusAwareMessageBox.information(
                self, "Merge Studies", 
                "No files found in the secondary studies to merge."
            )
            return
        
        reply = FocusAwareMessageBox.question(
            self, "Confirm Study Merge",
            f"This will update {len(files_to_update)} files from other studies to StudyInstanceUID '{primary_study_uid}'.\n"
            "This modifies files in-place. Continue?",
            FocusAwareMessageBox.StandardButton.Yes | FocusAwareMessageBox.StandardButton.No, 
            FocusAwareMessageBox.StandardButton.No
        )
        if reply != FocusAwareMessageBox.StandardButton.Yes:
            return
        
        self._perform_study_merge(files_to_update, primary_study_uid, primary_study_desc)
    
    def _merge_series(self, series_nodes):
        """Merge selected series under the same study"""
        from PyQt6.QtWidgets import QInputDialog
        
        # Check that all series are under the same study
        studies = set()
        for series in series_nodes:
            if series.parent():
                studies.add(series.parent().text(1))  # Study is in column 1
        
        if len(studies) > 1:
            FocusAwareMessageBox.warning(
                self, "Invalid Selection", 
                "All selected series must be under the same study."
            )
            return
        
        series_labels = [item.text(2) for item in series_nodes]  # Series is in column 2
        primary_label_selected, ok = QInputDialog.getItem(
            self, "Merge Series", "Select primary series (whose metadata to keep):", series_labels, 0, False
        )
        if not ok or not primary_label_selected:
            return
        
        primary_node = next(item for item in series_nodes if item.text(2) == primary_label_selected)
        
        # Get primary series UID and description
        primary_fp_sample = None
        primary_node_fps = self.tree_manager._collect_instance_filepaths(primary_node)
        if primary_node_fps:
            primary_fp_sample = primary_node_fps[0]
        
        if not primary_fp_sample:
            FocusAwareMessageBox.warning(
                self, "Merge Series", 
                f"Could not find any DICOM file for the primary series."
            )
            return
        
        try:
            import pydicom
            ds_primary = pydicom.dcmread(primary_fp_sample, stop_before_pixels=True)
            primary_series_uid = str(ds_primary.SeriesInstanceUID)
            primary_series_desc = str(getattr(ds_primary, 'SeriesDescription', ''))
        except Exception as e:
            FocusAwareMessageBox.critical(
                self, "Merge Series", 
                f"Failed to read primary series file: {e}"
            )
            return
        
        files_to_update = []
        secondary_nodes = [node for node in series_nodes if node is not primary_node]
        for node_sec in secondary_nodes:
            files_to_update.extend(self.tree_manager._collect_instance_filepaths(node_sec))
        
        if not files_to_update:
            FocusAwareMessageBox.information(
                self, "Merge Series", 
                "No files found in the secondary series to merge."
            )
            return
        
        reply = FocusAwareMessageBox.question(
            self, "Confirm Series Merge",
            f"This will update {len(files_to_update)} files from other series to SeriesInstanceUID '{primary_series_uid}'.\n"
            "This modifies files in-place. Continue?",
            FocusAwareMessageBox.StandardButton.Yes | FocusAwareMessageBox.StandardButton.No, 
            FocusAwareMessageBox.StandardButton.No
        )
        if reply != FocusAwareMessageBox.StandardButton.Yes:
            return
        
        self._perform_series_merge(files_to_update, primary_series_uid, primary_series_desc)
    
    def _perform_patient_merge(self, files_to_update, primary_id_val, primary_name_val):
        """Perform the actual patient merge operation"""
        from PyQt6.QtWidgets import QProgressDialog, QApplication
        import pydicom
        import os
        
        updated_count = 0
        failed_files = []
        
        progress = QProgressDialog("Merging patients...", "Cancel", 0, len(files_to_update), self)
        progress.setWindowTitle("Merging Patients")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        
        for idx, filepath in enumerate(files_to_update):
            progress.setValue(idx)
            if progress.wasCanceled():
                break
            QApplication.processEvents()
            
            try:
                ds = pydicom.dcmread(filepath)
                ds.PatientID = primary_id_val
                ds.PatientName = primary_name_val
                ds.save_as(filepath)
                updated_count += 1
            except Exception as e:
                failed_files.append(f"{os.path.basename(filepath)}: {str(e)}")
                logging.error(f"Failed to merge patient for {filepath}: {e}")
                
        progress.setValue(len(files_to_update))
        
        # Show results
        msg = f"Merged patient data.\nFiles updated: {updated_count}\nFailed: {len(failed_files)}"
        if failed_files:
            msg += "\n\nDetails (first few):\n" + "\n".join(failed_files[:3])
        FocusAwareMessageBox.information(self, "Merge Patients Complete", msg)

        # Refresh the tree to show merged data
        self._refresh_tree_after_merge()
    
    def _perform_study_merge(self, files_to_update, primary_study_uid, primary_study_desc):
        """Perform the actual study merge operation"""
        from PyQt6.QtWidgets import QProgressDialog, QApplication
        import pydicom
        import os
        
        updated_count = 0
        failed_files = []
        
        progress = QProgressDialog("Merging studies...", "Cancel", 0, len(files_to_update), self)
        progress.setWindowTitle("Merging Studies")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        
        for idx, filepath in enumerate(files_to_update):
            progress.setValue(idx)
            if progress.wasCanceled():
                break
            QApplication.processEvents()
            
            try:
                ds = pydicom.dcmread(filepath)
                ds.StudyInstanceUID = primary_study_uid
                if primary_study_desc:
                    ds.StudyDescription = primary_study_desc
                ds.save_as(filepath)
                updated_count += 1
            except Exception as e:
                failed_files.append(f"{os.path.basename(filepath)}: {str(e)}")
                logging.error(f"Failed to merge study for {filepath}: {e}")
                
        progress.setValue(len(files_to_update))
        
        # Show results
        msg = f"Merged study data.\nFiles updated: {updated_count}\nFailed: {len(failed_files)}"
        if failed_files:
            msg += "\n\nDetails (first few):\n" + "\n".join(failed_files[:3])
        FocusAwareMessageBox.information(self, "Merge Studies Complete", msg)

        # Refresh the tree to show merged data
        self._refresh_tree_after_merge()
    
    def _perform_series_merge(self, files_to_update, primary_series_uid, primary_series_desc):
        """Perform the actual series merge operation"""
        from PyQt6.QtWidgets import QProgressDialog, QApplication
        import pydicom
        import os
        
        updated_count = 0
        failed_files = []
        
        progress = QProgressDialog("Merging series...", "Cancel", 0, len(files_to_update), self)
        progress.setWindowTitle("Merging Series")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        
        for idx, filepath in enumerate(files_to_update):
            progress.setValue(idx)
            if progress.wasCanceled():
                break
            QApplication.processEvents()
            
            try:
                ds = pydicom.dcmread(filepath)
                ds.SeriesInstanceUID = primary_series_uid
                if primary_series_desc:
                    ds.SeriesDescription = primary_series_desc
                ds.save_as(filepath)
                updated_count += 1
            except Exception as e:
                failed_files.append(f"{os.path.basename(filepath)}: {str(e)}")
                logging.error(f"Failed to merge series for {filepath}: {e}")
                
        progress.setValue(len(files_to_update))
        
        # Show results
        msg = f"Merged series data.\nFiles updated: {updated_count}\nFailed: {len(failed_files)}"
        if failed_files:
            msg += "\n\nDetails (first few):\n" + "\n".join(failed_files[:3])
        FocusAwareMessageBox.information(self, "Merge Series Complete", msg)

        # Refresh the tree to show merged data
        self._refresh_tree_after_merge()
    
    def _refresh_tree_after_merge(self):
        """Refresh tree after patient merge to show updated hierarchy"""
        if hasattr(self, 'tree_manager') and self.tree_manager:
            self.tree_manager.refresh_tree()
        else:
            # Fallback to old method if tree manager not available
            self._legacy_refresh_tree_after_merge()
    
    def _legacy_refresh_tree_after_merge(self):
        """Legacy method for refreshing tree after merge"""
        # Get all currently loaded files that still exist
        all_known_files = []
        for file_info in self.loaded_files:
            # Handle both (filepath, dataset) tuples and just filepaths
            if isinstance(file_info, tuple):
                filepath = file_info[0]
            else:
                filepath = file_info
            
            if os.path.exists(filepath):
                all_known_files.append(filepath)
        
        if all_known_files:
            # Create tuples with datasets for tree manager
            file_tuples = []
            for filepath in all_known_files:
                try:
                    import pydicom
                    ds = pydicom.dcmread(filepath, stop_before_pixels=True)
                    file_tuples.append((filepath, ds))
                except Exception as e:
                    logging.warning(f"Could not reload {filepath}: {e}")
            
            if file_tuples:
                # Populate tree with refreshed data
                self.tree_manager.populate_tree(file_tuples)
    
    def save_as(self):
        """Export/save selected files"""
        selected = self.tree.selectedItems() if hasattr(self, 'tree') else []
        if not selected:
            FocusAwareMessageBox.warning(self, "No Selection", "Please select a node in the tree to export.")
            return
        
        # Collect files from ALL selected items
        filepaths = []
        for tree_item in selected:
            item_files = self.tree_manager._collect_instance_filepaths(tree_item)
            filepaths.extend(item_files)
        
        # Remove duplicates
        filepaths = list(set(filepaths))

        if not filepaths:
            FocusAwareMessageBox.warning(self, "No Instances", "No DICOM instances found under the selected nodes.")
            return

        # Show selection summary
        logging.info(f"Collected {len(filepaths)} files from {len(selected)} selected items")

        # Get export type
        from PyQt6.QtWidgets import QInputDialog, QFileDialog
        export_type, ok = QInputDialog.getItem(
            self, "Export Type", "Export as:", 
            ["Directory", "ZIP", "ZIP with DICOMDIR"], 0, False
        )
        if not ok:
            return

        # Map export_type to worker_export_type
        if export_type == "Directory":
            worker_export_type = "directory"
        elif export_type == "ZIP":
            worker_export_type = "zip"
        elif export_type == "ZIP with DICOMDIR":
            worker_export_type = "dicomdir_zip"
        else:
            worker_export_type = "directory"
        
        # Get output path based on export type
        if worker_export_type == "directory":
            output_path = QFileDialog.getExistingDirectory(
                self, "Select Export Directory", 
                self.config.get("default_export_dir", os.path.expanduser("~/Desktop"))
            )
        else:  # ZIP or ZIP with DICOMDIR
            output_path, _ = QFileDialog.getSaveFileName(
                self, "Save Export As", 
                os.path.join(self.config.get("default_export_dir", os.path.expanduser("~/Desktop")), "dicom_export.zip"),
                "ZIP files (*.zip)"
            )
        
        if not output_path:
            return

        # Start the export worker
        self._start_export_worker(filepaths, worker_export_type, output_path)
    
    def _start_export_worker(self, filepaths, export_type, output_path):
        """Start the export worker thread"""
        from PyQt6.QtWidgets import QProgressDialog
        import tempfile
        
        # Create progress dialog
        self.export_progress = QProgressDialog("Preparing export...", "Cancel", 0, 100, self)
        self.export_progress.setWindowTitle("Export Progress")
        self.export_progress.setMinimumDuration(0)
        self.export_progress.setValue(0)
        self.export_progress.canceled.connect(self._cancel_export)
        
        # Create temporary directory for DICOMDIR exports
        temp_dir = None
        if export_type == "dicomdir_zip":
            temp_dir = tempfile.mkdtemp()
        
        # Create and start worker
        from fm_dicom.workers.export_worker import ExportWorker
        self.export_worker = ExportWorker(filepaths, export_type, output_path, temp_dir)
        self.export_worker.progress_updated.connect(self._on_export_progress)
        self.export_worker.stage_changed.connect(self._on_export_stage_changed)
        self.export_worker.export_complete.connect(self._on_export_complete)
        self.export_worker.export_failed.connect(self._on_export_error)
        
        self.export_worker.start()
        self.export_progress.show()
    
    def _on_export_progress(self, current, total):
        """Handle export progress updates"""
        if hasattr(self, 'export_progress'):
            if total > 0:
                progress_value = int((current / total) * 100)
                self.export_progress.setValue(progress_value)
    
    def _on_export_stage_changed(self, stage_text):
        """Handle export stage changes"""
        if hasattr(self, 'export_progress'):
            self.export_progress.setLabelText(stage_text)
    
    def _on_export_complete(self, output_path):
        """Handle export completion"""
        if hasattr(self, 'export_progress'):
            self.export_progress.close()
        
        FocusAwareMessageBox.information(
            self, "Export Complete",
            f"Export completed successfully:\n{output_path}"
        )
    
    def _on_export_error(self, error_message):
        """Handle export errors"""
        if hasattr(self, 'export_progress'):
            self.export_progress.close()
        
        FocusAwareMessageBox.critical(
            self, "Export Error",
            f"Export failed:\n{error_message}"
        )
    
    def _cancel_export(self):
        """Cancel the export operation"""
        if hasattr(self, 'export_worker') and self.export_worker.isRunning():
            self.export_worker.requestInterruption()
            self.export_worker.wait(3000)
            if self.export_worker.isRunning():
                self.export_worker.terminate()
                self.export_worker.wait()
    
    # Helper Methods
    def _get_save_filename(self, caption, directory="", filter="", initial_filter=""):
        """Get filename to save using configured file picker"""
        from PyQt6.QtWidgets import QFileDialog
        dialog = QFileDialog(self, caption, directory, filter)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        
        # Configure based on user preference
        if not self.config.get("file_picker_native", False):
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        
        if initial_filter:
            dialog.selectNameFilter(initial_filter)
            
        if dialog.exec():
            filenames = dialog.selectedFiles()
            return filenames[0] if filenames else None, dialog.selectedNameFilter()
        return None, None

    # Analysis and Performance Testing Methods
    def analyze_all_loaded_files(self):
        """Analyze performance characteristics of all loaded files with UI dialog"""
        if not self.loaded_files:
            FocusAwareMessageBox.warning(self, "No Files", "No files loaded for analysis.")
            return
        
        logging.info("Starting comprehensive file analysis...")
        
        # Show progress dialog
        progress = FocusAwareProgressDialog("Analyzing files...", "Cancel", 0, len(self.loaded_files), self)
        progress.setWindowTitle("File Analysis")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        
        file_details = []
        unique_patients = set()
        unique_dimensions = set()
        transfer_syntaxes = {}
        large_files = []
        
        for idx, file_info in enumerate(self.loaded_files):
            if progress.wasCanceled():
                return
            
            # Handle different file_info formats
            if isinstance(file_info, tuple):
                filepath = file_info[0]  # (filepath, dataset) tuple
            else:
                filepath = file_info  # Just filepath string
                
            progress.setValue(idx)
            progress.setLabelText(f"Analyzing {os.path.basename(filepath)}...")
            QApplication.processEvents()
            
            try:
                import pydicom
                ds = pydicom.dcmread(filepath)
                
                # Extract detailed info
                transfer_syntax = str(getattr(ds.file_meta, 'TransferSyntaxUID', 'Unknown'))
                transfer_syntax_name = getattr(ds.file_meta.TransferSyntaxUID, 'name', 'Unknown') if hasattr(ds.file_meta, 'TransferSyntaxUID') else 'Unknown'
                rows = getattr(ds, 'Rows', 0)
                cols = getattr(ds, 'Columns', 0)
                bits_allocated = getattr(ds, 'BitsAllocated', 0)
                samples_per_pixel = getattr(ds, 'SamplesPerPixel', 1)
                photometric = getattr(ds, 'PhotometricInterpretation', 'Unknown')
                patient_id = str(getattr(ds, 'PatientID', 'Unknown'))
                
                # Calculate sizes
                estimated_size = rows * cols * bits_allocated * samples_per_pixel // 8
                file_size = os.path.getsize(filepath)
                compression_ratio = estimated_size / file_size if file_size > 0 else 0
                
                file_info = {
                    'filename': os.path.basename(filepath),
                    'filepath': filepath,
                    'patient_id': patient_id,
                    'transfer_syntax': transfer_syntax,
                    'transfer_syntax_name': transfer_syntax_name,
                    'dimensions': f"{cols}x{rows}",
                    'bits': bits_allocated,
                    'samples': samples_per_pixel,
                    'photometric': photometric,
                    'estimated_uncompressed': estimated_size,
                    'actual_file_size': file_size,
                    'uncompressed_mb': estimated_size / (1024*1024),
                    'file_size_mb': file_size / (1024*1024),
                    'compression_ratio': compression_ratio
                }
                
                file_details.append(file_info)
                unique_patients.add(patient_id)
                unique_dimensions.add(f"{cols}x{rows}")
                transfer_syntaxes[transfer_syntax_name] = transfer_syntaxes.get(transfer_syntax_name, 0) + 1
                
                # Check if it's a large file
                if estimated_size > 10*1024*1024:  # >10MB
                    large_files.append(file_info)
                    
            except Exception as e:
                logging.warning(f"Error analyzing {filepath}: {e}")
                continue
        
        progress.close()
        
        if not file_details:
            FocusAwareMessageBox.warning(self, "Analysis Failed", "No files could be analyzed.")
            return
        
        # Calculate summary statistics
        sizes = [f['estimated_uncompressed'] for f in file_details]
        size_range = f"{min(sizes)/(1024*1024):.1f}MB to {max(sizes)/(1024*1024):.1f}MB"
        
        # Prepare results for dialog
        analysis_results = {
            'files': file_details,
            'unique_patients': unique_patients,
            'unique_dimensions': list(unique_dimensions),
            'transfer_syntaxes': transfer_syntaxes,
            'large_files': large_files,
            'size_range': size_range
        }
        
        # Show detailed results dialog with export capabilities
        results_dialog = FileAnalysisResultsDialog(analysis_results, self)
        results_dialog.exec()

    def test_loading_performance(self):
        """Test actual loading performance of all files with UI dialog"""
        if not self.loaded_files:
            FocusAwareMessageBox.warning(self, "No Files", "No files loaded for performance testing.")
            return
        
        logging.info("Starting performance testing...")
        
        # Show progress dialog
        progress = FocusAwareProgressDialog("Testing performance...", "Cancel", 0, len(self.loaded_files), self)
        progress.setWindowTitle("Performance Testing")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        
        results = []
        
        for idx, file_info in enumerate(self.loaded_files):
            if progress.wasCanceled():
                return
            
            # Handle different file_info formats
            if isinstance(file_info, tuple):
                filepath = file_info[0]  # (filepath, dataset) tuple
            else:
                filepath = file_info  # Just filepath string
                
            progress.setValue(idx)
            progress.setLabelText(f"Testing {os.path.basename(filepath)}...")
            QApplication.processEvents()
            
            try:
                import pydicom
                # Test loading time
                start_time = time.time()
                ds = pydicom.dcmread(filepath)
                load_time = time.time() - start_time
                
                # Test pixel access time
                pixel_time = 0
                try:
                    pixel_start = time.time()
                    _ = ds.pixel_array
                    pixel_time = time.time() - pixel_start
                except Exception as e:
                    logging.warning(f"Could not access pixel data for {filepath}: {e}")
                    pixel_time = 0
                    
                total_time = load_time + pixel_time
                
                results.append({
                    'filename': os.path.basename(filepath),
                    'filepath': filepath,
                    'load_time': load_time,
                    'pixel_time': pixel_time,
                    'total_time': total_time
                })
                
            except Exception as e:
                logging.error(f"Error testing {filepath}: {e}")
                results.append({
                    'filename': os.path.basename(filepath),
                    'filepath': filepath,
                    'load_time': 0,
                    'pixel_time': 0,
                    'total_time': 0
                })
        
        progress.close()
        
        if not results:
            FocusAwareMessageBox.warning(self, "Performance Test Failed", "No files could be tested.")
            return
        
        # Analyze results
        slow_files = [r for r in results if r['total_time'] > 0.5]
        fastest_file = min(results, key=lambda x: x['total_time'])
        slowest_file = max(results, key=lambda x: x['total_time'])
        
        # Prepare results for dialog
        performance_results = {
            'files': results,
            'slow_files': slow_files,
            'fastest_file': fastest_file,
            'slowest_file': slowest_file
        }
        
        # Show detailed results dialog with export capabilities
        results_dialog = PerformanceResultsDialog(performance_results, self)
        results_dialog.exec()
    
    # Cleanup
    def closeEvent(self, event):
        """Handle application close"""
        # Check for unsaved changes
        if self.dicom_manager.has_unsaved_changes():
            reply = FocusAwareMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved tag changes. Save before closing?",
                FocusAwareMessageBox.StandardButton.Yes | 
                FocusAwareMessageBox.StandardButton.No | 
                FocusAwareMessageBox.StandardButton.Cancel,
                FocusAwareMessageBox.StandardButton.Cancel
            )
            
            if reply == FocusAwareMessageBox.StandardButton.Yes:
                self.dicom_manager.save_tag_changes()
            elif reply == FocusAwareMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        
        # Cleanup temporary files
        self.file_manager.cleanup_temp_dirs()
        
        # Save window size
        self.config["window_size"] = [self.width(), self.height()]
        
        event.accept()
        logging.info("Application closed")


# For compatibility, export the main class
__all__ = ['MainWindow']