from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem, QMessageBox, QLineEdit, QInputDialog, QComboBox, QLabel, QCheckBox, QSizePolicy, QSplitter,
    QDialog, QFormLayout, QDialogButtonBox, QProgressDialog,
    QApplication, QToolBar, QGroupBox, QFrame, QStatusBar, QStyle, QMenu,
    QGridLayout, QRadioButton, QButtonGroup, QProgressBar, QTextEdit
)
from PyQt6.QtGui import QPixmap, QImage, QIcon, QPalette, QColor, QFont, QAction, QPainter
from PyQt6.QtCore import QDir, Qt, QPoint, QSize, QThread, pyqtSignal, QTimer

import pydicom
import zipfile
import tempfile
import os
import shutil
import numpy as np
import sys
import yaml
from pydicom.dataelem import DataElement
from pydicom.uid import generate_uid
import time
import logging
import platform
from fm_dicom.validation.validation import DicomValidator
from fm_dicom.validation.validation_ui import run_validation, ValidationResultsDialog
from fm_dicom.anonymization.anonymization import TemplateManager, AnonymizationEngine
from fm_dicom.anonymization.anonymization_ui import run_anonymization, TemplateSelectionDialog
from fm_dicom.tag_browser.tag_browser import TagSearchDialog, ValueEntryDialog
from fm_dicom.core.dicomdir_reader import DicomdirReader
from fm_dicom.core.path_generator import DicomPathGenerator
from fm_dicom.core.dicomdir_builder import DicomdirBuilder
from fm_dicom.workers.zip_worker import ZipExtractionWorker
from fm_dicom.workers.dicom_worker import DicomdirScanWorker
from fm_dicom.workers.export_worker import ExportWorker
from fm_dicom.workers.dicom_send_worker import DicomSendWorker
from fm_dicom.utils.helpers import depth  # Import to activate QTreeWidgetItem.depth extension
from fm_dicom.config.config_manager import load_config, setup_logging, get_default_user_dir, ensure_dir_exists
from fm_dicom.config.dicom_setup import setup_gdcm_integration
from fm_dicom.themes.theme_manager import set_light_palette, set_dark_palette
from fm_dicom.widgets.focus_aware import FocusAwareMessageBox, FocusAwareProgressDialog
from fm_dicom.dialogs.selection_dialogs import PrimarySelectionDialog, DicomSendDialog
from fm_dicom.dialogs.results_dialogs import FileAnalysisResultsDialog, PerformanceResultsDialog
from fm_dicom.dialogs.progress_dialogs import ZipExtractionDialog, DicomdirScanDialog
from fm_dicom.dialogs.utility_dialogs import LogViewerDialog, SettingsEditorDialog
from fm_dicom.widgets.checkbox_tree import OptimizedCheckboxTreeWidget
from fm_dicom.widgets.selection_summary import LazySelectionSummaryWidget
from fm_dicom.dialogs.dicom_send_selection import DicomSendSelectionDialog

from pynetdicom import AE, AllStoragePresentationContexts
from pynetdicom.sop_class import Verification
VERIFICATION_SOP_CLASS = Verification
STORAGE_CONTEXTS = AllStoragePresentationContexts



# Setup GDCM integration for DICOM pixel data handling
setup_gdcm_integration()



class MainWindow(QMainWindow):
    def __init__(self, start_path=None, config_path_override=None):
        super().__init__() # Call super constructor first

        # Load configuration FIRST
        self.config = load_config(config_path_override=config_path_override)
        
        # Setup logging SECOND, using paths from the loaded/defaulted config
        setup_logging(self.config.get("log_path"), self.config.get("log_level", "INFO")) # Provide default for level
        
        logging.info("Application started")
        logging.debug(f"Loaded configuration: {self.config}")
        
        # Apply theme from config
        QApplication.setStyle("Fusion") # Base style
        current_theme = self.config.get("theme", "dark").lower() # Default to dark if not in config
        if current_theme == "dark":
            set_dark_palette(QApplication.instance())
        else:
            set_light_palette(QApplication.instance()) # Assuming you have a light palette function

        # Initialize anonymization template manager with proper config directory
        system = platform.system()
        app_name = "fm-dicom"
        if system == "Windows":
            appdata = os.environ.get("APPDATA")
            config_dir = os.path.join(appdata if appdata else os.path.dirname(sys.executable), app_name)
        elif system == "Darwin":  # macOS
            config_dir = os.path.expanduser(f"~/Library/Application Support/{app_name}")
        else:  # Linux/Unix
            xdg_config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
            config_dir = os.path.join(xdg_config_home, app_name)
        
        # Ensure template config directory exists
        os.makedirs(config_dir, exist_ok=True)
        self.template_manager = TemplateManager(config_dir)
        
        # Set config attributes for other parts of the app
        self.dicom_send_config = self.config # DicomSendDialog uses this
        
        # Initialize default directories from config (now guaranteed to be expanded)
        self.default_export_dir = self.config.get("default_export_dir")
        self.default_import_dir = self.config.get("default_import_dir")

        # Fallbacks if paths are somehow still None (shouldn't happen with new load_config)
        if not self.default_export_dir:
            self.default_export_dir = os.path.join(get_default_user_dir(), "DICOM_Exports")
            logging.warning(f"default_export_dir was None after config load, fell back to: {self.default_export_dir}")
        if not self.default_import_dir:
            # Default to user's Downloads folder if available
            downloads_dir = os.path.join(get_default_user_dir(), "Downloads")
            if os.path.isdir(downloads_dir):
                self.default_import_dir = downloads_dir
            else:
                self.default_import_dir = get_default_user_dir()
            logging.warning(f"default_import_dir was None after config load, fell back to: {self.default_import_dir}")

        # --- User's Original UI Setup Starts Here ---
        self.setWindowTitle("FM DICOM Tag Editor")
        w, h = self.config.get("window_size", [1200, 800])
        self.resize(w, h)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Toolbar (User's Original)
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        open_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
        save_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        delete_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon)
        merge_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder)
        expand_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown)
        collapse_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp)

        act_open = QAction(open_icon, "Open", self)
        act_open.triggered.connect(self.open_file)
        toolbar.addAction(act_open)

        act_open_dir = QAction(QIcon.fromTheme("folder"), "Open Directory", self) # User's icon choice
        act_open_dir.triggered.connect(self.open_directory)
        toolbar.addAction(act_open_dir)

        act_delete = QAction(delete_icon, "Delete", self)
        act_delete.triggered.connect(self.delete_selected_items)
        toolbar.addAction(act_delete)

        act_expand = QAction(expand_icon, "Expand All", self)
        act_expand.triggered.connect(self.tree_expand_all)
        toolbar.addAction(act_expand)

        act_collapse = QAction(collapse_icon, "Collapse All", self)
        act_collapse.triggered.connect(self.tree_collapse_all)
        toolbar.addAction(act_collapse)
        toolbar.addSeparator()

        validate_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton)
        act_validate = QAction(validate_icon, "Validate", self)
        act_validate.triggered.connect(self.validate_dicom_files)
        toolbar.addAction(act_validate)

        toolbar.addSeparator()

        template_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        act_templates = QAction(template_icon, "Manage Templates", self)
        act_templates.triggered.connect(self.manage_templates)
        toolbar.addAction(act_templates)

        logs_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        act_show_logs = QAction(logs_icon, "Show Logs", self)
        act_show_logs.triggered.connect(self.show_log_viewer)
        toolbar.addAction(act_show_logs)

        settings_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        act_settings = QAction(settings_icon, "Settings", self)
        act_settings.triggered.connect(self.open_settings_editor)
        toolbar.addAction(act_settings)

        # Main Splitter (User's Original)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        tree_search_layout = QHBoxLayout()
        self.tree_search_bar = QLineEdit()
        self.tree_search_bar.setPlaceholderText("Search patients/studies/series/instances...")
        self.tree_search_bar.textChanged.connect(self.filter_tree_items)
        tree_search_layout.addWidget(self.tree_search_bar)
        left_layout.addLayout(tree_search_layout)

        self.tree = QTreeWidget()
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.setHeaderLabels(["Patient", "Study", "Series", "Instance"])
        self.tree.itemSelectionChanged.connect(self.display_selected_tree_file)
        self.tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tree.setAlternatingRowColors(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_tree_context_menu)
        left_layout.addWidget(self.tree)

        self.preview_toggle = QCheckBox("Show Image Preview")
        self.preview_toggle.setChecked(bool(self.config.get("show_image_preview", False)))
        # Connect both refresh and state saving
        self.preview_toggle.stateChanged.connect(self.save_preview_toggle_state_and_refresh_display)
        left_layout.addWidget(self.preview_toggle)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumHeight(256) # User's value
        self.image_label.setVisible(False)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding) # User's policy
        left_layout.addWidget(self.image_label)
        main_splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search tags by ID or description...")
        self.search_bar.textChanged.connect(self.filter_tag_table)  # Ensure this is connected
        right_layout.addWidget(self.search_bar)

        self.tag_table = QTableWidget()
        self.tag_table.setColumnCount(4)
        self.tag_table.setHorizontalHeaderLabels(["Tag ID", "Description", "Value", "New Value"])
        # Set reasonable default column widths
        self.tag_table.setColumnWidth(0, 110)   # Tag ID
        self.tag_table.setColumnWidth(1, 220)   # Description
        self.tag_table.setColumnWidth(2, 260)   # Value
        self.tag_table.setColumnWidth(3, 160)   # New Value
        self.tag_table.horizontalHeader().setStretchLastSection(True)
        self.tag_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tag_table.setAlternatingRowColors(True)
        # User's original stylesheet for tag_table
        self.tag_table.setStyleSheet("""
            QTableWidget {
                background-color: #23272a;
                alternate-background-color: #2c2f33;
                color: #f5f5f5;
                selection-background-color: #508cff;
                selection-color: #fff;
                gridline-color: #444;
            }
            QHeaderView::section {
                background-color: #202225;
                color: #f5f5f5;
                font-weight: bold;
            }
        """)
        self.tag_table.cellActivated.connect(self._populate_new_value_on_edit)
        self.tag_table.cellClicked.connect(self._populate_new_value_on_edit)
        right_layout.addWidget(self.tag_table)
        main_splitter.addWidget(right_widget)
        
        main_splitter.setStretchFactor(0, 1) # User's stretch factors
        main_splitter.setStretchFactor(1, 2)
        layout.addWidget(main_splitter)

        # Grouped Button Layouts (User's Original)
        btn_grid = QGridLayout()
        btn_grid.setHorizontalSpacing(32)
        btn_grid.setVerticalSpacing(10)

        edit_group = QGroupBox("Editing")
        edit_layout = QVBoxLayout()
        edit_layout.setSpacing(10)
        self.edit_level_combo = QComboBox()
        self.edit_level_combo.addItems(["Instance", "Series", "Study", "Patient"])
        self.edit_level_combo.setCurrentText("Series")
        edit_layout.addWidget(self.edit_level_combo)
        self.save_btn = QPushButton(save_icon, "Submit Changes") # User had save_icon here
        self.save_btn.clicked.connect(self.save_tag_changes)
        edit_layout.addWidget(self.save_btn)
        self.anon_btn = QPushButton("Anonymise Patient")
        self.anon_btn.clicked.connect(self.anonymise_selected)
        edit_layout.addWidget(self.anon_btn)
        edit_group.setLayout(edit_layout)

        export_group = QGroupBox("Export/Send")
        export_layout = QVBoxLayout()
        export_layout.setSpacing(10)
        self.save_as_btn = QPushButton(save_icon, "Save As") # User had this button here
        self.save_as_btn.clicked.connect(self.save_as)
        export_layout.addWidget(self.save_as_btn)
        self.dicom_send_btn = QPushButton("DICOM Send")
        self.dicom_send_btn.clicked.connect(self.dicom_send)
        export_layout.addWidget(self.dicom_send_btn)
        export_group.setLayout(export_layout)

        tag_group = QGroupBox("Tags/Batch")
        tag_layout = QVBoxLayout()
        tag_layout.setSpacing(10)
        self.edit_btn = QPushButton("New Tag") # User's text
        self.edit_btn.clicked.connect(self.edit_tag)
        tag_layout.addWidget(self.edit_btn)
        self.batch_edit_btn = QPushButton("Batch New Tag") # User's text
        self.batch_edit_btn.clicked.connect(self.batch_edit_tag)
        tag_layout.addWidget(self.batch_edit_btn)
        tag_group.setLayout(tag_layout)

        self.merge_patients_btn = QPushButton(merge_icon, "Merge Patients")
        self.merge_patients_btn.clicked.connect(self.merge_patients)
        self.merge_patients_btn.setMinimumWidth(120)
        self.merge_patients_btn.setMinimumHeight(36)
        self.delete_btn = QPushButton(delete_icon, "Delete")
        self.delete_btn.setToolTip("Delete selected patients, studies, series, or instances")
        self.delete_btn.clicked.connect(self.delete_selected_items)
        self.delete_btn.setMinimumWidth(80)
        self.delete_btn.setMinimumHeight(36)

        # Add these in your toolbar setup
        debug_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        act_debug = QAction(debug_icon, "Analyze Files", self)
        act_debug.triggered.connect(self.analyze_all_loaded_files)
        toolbar.addAction(act_debug)

        timing_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton)
        act_timing = QAction(timing_icon, "Test Performance", self)
        act_timing.triggered.connect(self.test_loading_performance)
        toolbar.addAction(act_timing)

        btn_grid.addWidget(edit_group, 0, 0, 2, 1)
        btn_grid.addWidget(export_group, 0, 1)
        btn_grid.addWidget(tag_group, 0, 2)
        btn_grid.addWidget(self.merge_patients_btn, 1, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        btn_grid.addWidget(self.delete_btn, 1, 2, alignment=Qt.AlignmentFlag.AlignLeft)
        
        btn_bar = QWidget()
        btn_bar.setLayout(btn_grid)
        btn_bar.setMaximumHeight(170) # User's height
        btn_bar.setStyleSheet( # User's stylesheet for button bar
            "QGroupBox { font-weight: bold; margin-top: 18px; }"
            "QPushButton { min-height: 36px; min-width: 120px; font-size: 13px; }"
        )
        layout.addWidget(btn_bar)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready")

        self.summary_label = QLineEdit()
        self.summary_label.setReadOnly(True)
        self.summary_label.setStyleSheet( # User's stylesheet for summary
            "background: #202225; color: #f5f5f5; border: none; font-weight: bold;"
        )
        layout.addWidget(self.summary_label)

        searchbar_style = ( # User's search bar style
            "background: #202225; color: #f5f5f5; border: 1px solid #444;"
            "selection-background-color: #508cff;"
            "selection-color: #fff;"
        )
        self.tree_search_bar.setStyleSheet(searchbar_style)
        self.search_bar.setStyleSheet(searchbar_style)

        # Initial Load (User's Original)
        self.loaded_files = []
        self.file_metadata = {}
        self.temp_dir = None
        self.current_filepath = None
        self.current_ds = None
        self._all_tag_rows = []

        #For discard changes dialog tracking
        self.has_unsaved_tag_changes = False
        self.reverting_selection= False

        self.pending_start_path = start_path  # Store for later loading
        if start_path:
            # Defer loading until window is shown
            QTimer.singleShot(100, self.load_pending_start_path)

        logging.info("MainWindow UI initialized")

    def load_pending_start_path(self):
        """Load the pending start path after the window is shown"""
        if hasattr(self, 'pending_start_path') and self.pending_start_path:
            path = self.pending_start_path
            self.pending_start_path = None  # Clear it
            
            # Ensure window is visible
            if not self.isVisible():
                self.show()
                QApplication.processEvents()
                
            self.load_path_on_start(path)
        
    def save_preview_toggle_state_and_refresh_display(self, qt_state):
        # Convert Qt.CheckState enum to boolean
        is_checked = (qt_state == Qt.CheckState.Checked.value) # Or simply bool(qt_state) for PyQt6 if direct cast works
        self.config["show_image_preview"] = is_checked
        logging.debug(f"Preview toggle state changed to: {is_checked}, saved to config.")
        # self.save_configuration() # Optionally save config immediately, or rely on closeEvent
        self.display_selected_tree_file() # Refresh display as user originally had

    def save_configuration(self):
        """Saves the current self.config to the preferred_config_path."""
        system = platform.system()
        app_name = "fm-dicom"
        # Determine preferred_config_path (same logic as in load_config)
        if system == "Windows":
            appdata = os.environ.get("APPDATA")
            base_dir = appdata if appdata else os.path.dirname(sys.executable)
            config_file_path = os.path.join(base_dir, app_name, "config.yml")
        elif system == "Darwin":
            config_file_path = os.path.expanduser(f"~/Library/Application Support/{app_name}/config.yml")
        else: # Linux/Unix
            xdg_config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
            config_file_path = os.path.join(xdg_config_home, app_name, "config.yml")

        try:
            if ensure_dir_exists(config_file_path): # Ensure directory exists before writing
                with open(config_file_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(self.config, f, sort_keys=False, allow_unicode=True)
                logging.info(f"Configuration saved to {config_file_path}")
            else:
                logging.error(f"Could not create directory for config file, not saving: {config_file_path}")
        except Exception as e:
            logging.error(f"Failed to save configuration to {config_file_path}: {e}", exc_info=True)

    def closeEvent(self, event):
        # Save window size before saving the rest of the config
        if hasattr(self, 'button_widget') and self.button_widget:
            self._remove_button_widget()

        # Clean up export worker if running
        if hasattr(self, 'export_worker') and self.export_worker and self.export_worker.isRunning():
            self.export_worker.cancel()
            self.export_worker.wait(3000)
            if self.export_worker.isRunning():
                self.export_worker.terminate()
                
        if self.config: # Ensure config object exists
            self.config["window_size"] = [self.size().width(), self.size().height()]
            self.save_configuration() # Save all pending config changes
        
        self.cleanup_temp_dir() # Clean up any temporary files
        logging.info("Application closing.")
        super().closeEvent(event) # Important to call the superclass method

    def _are_studies_under_same_patient(self, study_nodes):
        """Ensure all studies belong to same patient"""
        if not study_nodes:
            return False
        # Compare patient text instead of QTreeWidgetItem objects
        parent_patient_texts = {study.parent().text(0) if study.parent() else None for study in study_nodes}
        return len(parent_patient_texts) == 1 and None not in parent_patient_texts

    def _are_series_under_same_study(self, series_nodes):
        """Ensure all series belong to same study"""
        if not series_nodes:
            return False
        # Compare study text instead of QTreeWidgetItem objects
        parent_study_texts = {series.parent().text(1) if series.parent() else None for series in series_nodes}
        return len(parent_study_texts) == 1 and None not in parent_study_texts
    

    def load_path(self, path):
        """
        Universal file/directory loading function.
        Handles: individual files (.dcm), ZIP archives, directories
        Returns: True if successful, False if failed/cancelled
        """
        if not path:
            return False
            
        path = os.path.expanduser(path)
        self.clear_loaded_files()
        
        if os.path.isfile(path):
            if path.lower().endswith('.zip'):
                return self._load_zip_consolidated(path)
            elif path.lower().endswith('.dcm'):
                return self._load_single_file(path)
            else:
                FocusAwareMessageBox.warning(self, "Unsupported", "Only .dcm and .zip files are supported.")
                return False
        elif os.path.isdir(path):
            return self._load_directory_consolidated(path)
        else:
            FocusAwareMessageBox.warning(self, "Not Found", f"Path does not exist: {path}")
            return False

    def _load_zip_consolidated(self, zip_path):
        """Consolidated ZIP loading with DICOMDIR support"""
        logging.info(f"DEBUG: Loading ZIP file: {zip_path}")
        
        # Extract ZIP file
        extraction_dialog = ZipExtractionDialog(zip_path, self)
        if not (extraction_dialog.exec() == QDialog.DialogCode.Accepted and extraction_dialog.success):
            return False
        
        self.temp_dir = extraction_dialog.temp_dir
        all_extracted_files = extraction_dialog.extracted_files
        
        logging.info(f"DEBUG: Extracted {len(all_extracted_files)} files")
        
        # Try DICOMDIR first
        dicom_files = self._try_dicomdir_loading(self.temp_dir, all_extracted_files)
        if dicom_files:
            logging.debug(f"DEBUG: DICOMDIR loading successful: {len(dicom_files)} files")
            self.loaded_files = [(f, self.temp_dir) for f in dicom_files]
            self.populate_tree(dicom_files)
            self.statusBar().showMessage(f"Loaded {len(dicom_files)} DICOM files from DICOMDIR in ZIP")
            return True
        
        # Fallback to file scanning
        logging.debug("DEBUG: DICOMDIR not found/failed, scanning all files")
        dicom_files = self._scan_files_for_dicom(all_extracted_files, "Scanning ZIP contents...")
        
        if not dicom_files:
            FocusAwareMessageBox.warning(self, "No DICOM", 
                            f"No DICOM files found in ZIP archive.\nExtracted {len(all_extracted_files)} files.")
            self.cleanup_temp_dir()
            return False
        
        self.loaded_files = [(f, self.temp_dir) for f in dicom_files]
        self.populate_tree(dicom_files)
        self.statusBar().showMessage(f"Loaded {len(dicom_files)} DICOM files from ZIP")
        return True

    def _load_directory_consolidated(self, dir_path):
        """Consolidated directory loading with DICOMDIR support"""
        logging.info(f"DEBUG: Loading directory: {dir_path}")
        
        # Get all files in directory
        all_files = []
        for root, dirs, files in os.walk(dir_path):
            for name in files:
                all_files.append(os.path.join(root, name))
        
        # Try DICOMDIR first
        dicom_files = self._try_dicomdir_loading(dir_path, all_files)
        if dicom_files:
            logging.debug(f"DEBUG: DICOMDIR loading successful: {len(dicom_files)} files")
            self.loaded_files = [(f, None) for f in dicom_files]
            self.populate_tree(dicom_files)
            self.statusBar().showMessage(f"Loaded {len(dicom_files)} DICOM files from DICOMDIR")
            return True
        
        # Fallback to file scanning
        logging.debug("DEBUG: DICOMDIR not found/failed, scanning all files")
        dicom_files = self._scan_files_for_dicom(all_files, "Scanning directory...")
        
        if not dicom_files:
            FocusAwareMessageBox.warning(self, "No DICOM", "No DICOM files found in directory.")
            return False
        
        self.loaded_files = [(f, None) for f in dicom_files]
        self.populate_tree(dicom_files)
        self.statusBar().showMessage(f"Loaded {len(dicom_files)} DICOM files from directory")
        return True

    def _load_single_file(self, file_path):
        """Load a single DICOM file"""
        self.loaded_files = [(file_path, None)]
        self.populate_tree([file_path])
        self.statusBar().showMessage(f"Loaded single DICOM file")
        return True

    def _try_dicomdir_loading(self, base_path, all_files):
        """
        Try to find and use DICOMDIR files for loading.
        Returns list of DICOM files if successful, empty list if failed/not found.
        """
        # Find DICOMDIR files
        dicomdir_files = []
        for file_path in all_files:
            if os.path.basename(file_path).upper() == 'DICOMDIR':
                dicomdir_files.append(file_path)
                logging.debug(f"DEBUG: Found DICOMDIR: {file_path}")
        
        if not dicomdir_files:
            return []
        
        # Use the first DICOMDIR found
        dicomdir_path = dicomdir_files[0]
        dicomdir_dir = os.path.dirname(dicomdir_path)
        
        logging.debug(f"DEBUG: Using DICOMDIR in directory: {dicomdir_dir}")
        
        try:
            # Try using DicomdirReader
            reader = DicomdirReader()
            found_dicomdirs = reader.find_dicomdir(dicomdir_dir)
            
            logging.debug(f"DEBUG: DicomdirReader.find_dicomdir returned: {found_dicomdirs}")
            
            if found_dicomdirs:
                # DicomdirScanDialog expects the list of all files, not the directory!
                dicomdir_dialog = DicomdirScanDialog(all_files, self)  # <-- Fixed: pass all_files
                
                if dicomdir_dialog.exec() == QDialog.DialogCode.Accepted and dicomdir_dialog.success:
                    logging.debug(f"DEBUG: DicomdirScanDialog loaded {len(dicomdir_dialog.dicom_files)} files")
                    return dicomdir_dialog.dicom_files
                else:
                    error_msg = getattr(dicomdir_dialog, 'error_message', 'Unknown error')
                    logging.debug(f"DEBUG: DicomdirScanDialog failed: {error_msg}")
                    FocusAwareMessageBox.warning(self, "DICOMDIR Error", 
                                    f"Failed to read DICOMDIR: {error_msg}\n\nFalling back to file scanning...")
            else:
                logging.info("DEBUG: DicomdirReader found no DICOMDIR files")
                
        except Exception as e:
            logging.error(f"DEBUG: Exception in DICOMDIR processing: {e}")
            FocusAwareMessageBox.warning(self, "DICOMDIR Error", 
                            f"Error processing DICOMDIR: {str(e)}\n\nFalling back to file scanning...")
        
        return []

    def _scan_files_for_dicom(self, files, progress_text="Scanning files..."):
        """
        Scan a list of files and return those that are DICOM files.
        Shows progress dialog during scanning.
        """
        progress = FocusAwareProgressDialog(progress_text, "Cancel", 0, len(files), self)
        progress.setWindowTitle("Loading Files")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        
        dicom_files = []
        for idx, file_path in enumerate(files):
            if progress.wasCanceled():
                break
            
            if self._is_dicom_file(file_path):
                dicom_files.append(file_path)
                
            progress.setValue(idx + 1)
            QApplication.processEvents()
        
        progress.close()
        logging.info(f"DEBUG: Found {len(dicom_files)} DICOM files out of {len(files)} total files")
        return dicom_files

    def _is_dicom_file(self, filepath):
        """Helper method to check if a file is a DICOM file by reading its header"""
        try:
            # Quick check for .dcm extension first
            if filepath.lower().endswith('.dcm'):
                return True
                
            with open(filepath, 'rb') as f:
                # Check for DICOM file signature
                f.seek(128)  # Skip preamble
                signature = f.read(4)
                if signature == b'DICM':
                    return True
                
                # Some DICOM files don't have preamble, check for common DICOM tags at start
                f.seek(0)
                data = f.read(256)
                # Look for common DICOM patterns
                return b'\x08\x00' in data[:32] or b'\x10\x00' in data[:32]
        except:
            return False

    def _load_dicom_files_from_list(self, filepaths, source_description="files"):
        """Helper method to load DICOM files from a list"""
        if not filepaths:
            self.summary_label.setText("No files to load.")
            self.statusBar().showMessage("No files to load.")
            return
        
        # Clear existing data but preserve temp_dir info from original loaded_files
        temp_dir_map = {f_info[0]: f_info[1] for f_info in self.loaded_files}
        
        self.tree.clear()
        self.file_metadata = {}
        self.tag_table.setRowCount(0)
        self._all_tag_rows = []
        self.image_label.clear()
        self.image_label.setVisible(False)
        self.current_filepath = None
        self.current_ds = None
        
        # Update loaded_files, preserving temp_dir info
        self.loaded_files = [(f, temp_dir_map.get(f, None)) for f in filepaths if os.path.exists(f)]
        
        # Repopulate tree
        self.populate_tree(filepaths)
        
        logging.info(f"Refreshed tree view with {len(filepaths)} files from {source_description}")

    # --- User's Original Methods (Ensure these are exactly as user provided) ---
    def tree_expand_all(self):
        self.tree.expandAll()

    def tree_collapse_all(self):
        self.tree.collapseAll()

    def _populate_new_value_on_edit(self, row, col):
        if col != 3:
            return
        new_value_item = self.tag_table.item(row, 3)
        current_value_item = self.tag_table.item(row, 2)
        if new_value_item and current_value_item and not new_value_item.text().strip():
            new_value_item.setText(current_value_item.text())

    def open_file(self):
        """GUI file picker"""
        filename, _ = self._get_open_filename(
            "Open DICOM or ZIP File",
            self.default_import_dir,
            "ZIP Archives (*.zip);;DICOM Files (*.dcm);;All Files (*)"
        )
        if filename:
            self.load_path(filename)

    def open_directory(self):
        """GUI directory picker"""
        dir_path = self._get_existing_directory(
            "Open DICOM Directory",
            self.default_import_dir
        )
        if dir_path:
            self.load_path(dir_path)

    def load_pending_start_path(self):
        """Load the pending start path after the window is shown"""
        if hasattr(self, 'pending_start_path') and self.pending_start_path:
            path = self.pending_start_path
            self.pending_start_path = None  # Clear it
            
            # Ensure window is visible
            if not self.isVisible():
                self.show()
                QApplication.processEvents()
                
            self.load_path(path)

    def load_path_on_start(self, path):
        """CLI loading (now just calls load_path)"""
        self.load_path(path)

    def show_tree_context_menu(self, pos: QPoint): # Updated with study and series merge options
        item = self.tree.itemAt(pos)
        if not item:
            return
        
        selected = self.tree.selectedItems()
        
        # Analyze selection for different merge types
        patient_nodes = [item for item in selected if item.depth() == 0]
        study_nodes = [item for item in selected if item.depth() == 1]
        series_nodes = [item for item in selected if item.depth() == 2]
        
        studies_same_patient = self._are_studies_under_same_patient(study_nodes)
        series_same_study = self._are_series_under_same_study(series_nodes)
        
        menu = QMenu(self)
        
        # Delete action (always available)
        delete_action = QAction(QIcon.fromTheme("edit-delete"), "Delete", self)
        delete_action.triggered.connect(self.delete_selected_items)
        menu.addAction(delete_action)

        validate_action = QAction("Validate Selected", self)
        validate_action.triggered.connect(self.validate_selected_items)
        menu.addAction(validate_action)
        
        menu.addSeparator()
        
        # Merge actions based on selection
        if len(patient_nodes) >= 2:
            merge_patients_action = QAction("Merge Patients", self)
            merge_patients_action.triggered.connect(self.merge_patients)
            menu.addAction(merge_patients_action)
        
        if len(study_nodes) >= 2 and studies_same_patient:
            merge_studies_action = QAction("Merge Studies", self)
            merge_studies_action.triggered.connect(self.merge_studies)
            menu.addAction(merge_studies_action)
        
        if len(series_nodes) >= 2 and series_same_study:
            merge_series_action = QAction("Merge Series", self)
            merge_series_action.triggered.connect(self.merge_series)
            menu.addAction(merge_series_action)
        
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def validate_selected_items(self):
        """Validate only the selected items in the tree"""
        selected = self.tree.selectedItems()
        if not selected:
            FocusAwareMessageBox.warning(self, "No Selection", "Please select items to validate.")
            return
        
        # Collect file paths from selected items
        file_paths = []
        for item in selected:
            paths = self._collect_instance_filepaths(item)
            file_paths.extend(paths)
        
        if not file_paths:
            FocusAwareMessageBox.warning(self, "No Files", "No DICOM files found in selection.")
            return
        
        # Remove duplicates
        file_paths = list(set(file_paths))
        
        logging.info(f"Starting validation of {len(file_paths)} selected files")
        
        try:
            run_validation(file_paths, self)
        except Exception as e:
            logging.error(f"Validation error: {e}", exc_info=True)
            FocusAwareMessageBox.critical(self, "Validation Error", 
                            f"An error occurred during validation:\n{str(e)}")

    def filter_tree_items(self, text):
        """Filter the study list tree based on the provided text."""
        text = text.lower()
        def match(item):
            for col in range(item.columnCount()):
                if text in item.text(col).lower():
                    return True
            for i in range(item.childCount()):
                if match(item.child(i)):
                    item.setExpanded(True)
                    return True
            return False

        def filter_item_recursive(item):
            is_visible = match(item)
            item.setHidden(not is_visible)
            if is_visible:
                for i in range(item.childCount()):
                    filter_item_recursive(item.child(i))
            if not text:
                item.setHidden(False)
                for i in range(item.childCount()):
                    filter_item_recursive(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            filter_item_recursive(self.tree.topLevelItem(i))

    def filter_tag_table(self, text):
        """Filter the tag table based on the provided text."""
        filter_text = text.lower()
        self.tag_table.setRowCount(0)
        for row_info in self._all_tag_rows:
            elem_obj = row_info['elem_obj']
            display_row_data = row_info['display_row']
            tag_id, desc, value, _ = display_row_data

            if filter_text in tag_id.lower() or filter_text in desc.lower():
                row_idx = self.tag_table.rowCount()
                self.tag_table.insertRow(row_idx)
                self.tag_table.setItem(row_idx, 0, QTableWidgetItem(tag_id))
                self.tag_table.setItem(row_idx, 1, QTableWidgetItem(desc))
                self.tag_table.setItem(row_idx, 2, QTableWidgetItem(value))
                new_value_item = QTableWidgetItem("")
                new_value_item.setData(Qt.ItemDataRole.UserRole, elem_obj)
                if elem_obj.tag == (0x7fe0, 0x0010) or elem_obj.VR in ("OB", "OW", "UN", "SQ"):
                    new_value_item.setFlags(new_value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tag_table.setItem(row_idx, 3, new_value_item)
        # Set sensible default column widths after populating
        self.tag_table.setColumnWidth(0, 110)
        self.tag_table.setColumnWidth(1, 220)
        self.tag_table.setColumnWidth(2, 260)
        self.tag_table.setColumnWidth(3, 160)

    def populate_tree(self, files):
        self.tree.clear()
        hierarchy = {}
        self.file_metadata = {}
        modalities = set()
        progress = QProgressDialog("Loading DICOM headers...", "Cancel", 0, len(files), self)
        progress.setWindowTitle("Loading DICOM Files")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        
        for idx, f in enumerate(files):
            if progress.wasCanceled():
                break
            try:
                ds = pydicom.dcmread(f, stop_before_pixels=True)
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
                sop_uid = getattr(ds, "SOPInstanceUID", os.path.basename(f))
                
                # Create instance label but store numerical info for sorting
                if instance_number is not None:
                    instance_label = f"Instance {instance_number} [{sop_uid}]"
                    # Convert to int for proper numerical sorting
                    try:
                        instance_sort_key = int(instance_number)
                    except (ValueError, TypeError):
                        instance_sort_key = 999999  # Put non-numeric at end
                else:
                    instance_label = f"{os.path.basename(f)} [{sop_uid}]"
                    instance_sort_key = 999999  # Put missing instance numbers at end
                
                modality = getattr(ds, "Modality", None)
                if modality:
                    modalities.add(str(modality))
                
                self.file_metadata[f] = (patient_label, study_label, series_label, instance_label)
                
                # CHANGED: Store both filepath and sort key for proper ordering
                hierarchy.setdefault(patient_label, {}).setdefault(study_label, {}).setdefault(series_label, {})[instance_label] = {
                    'filepath': f,
                    'sort_key': instance_sort_key,
                    'instance_number': instance_number
                }
                
            except Exception:
                continue
            progress.setValue(idx + 1)
            QApplication.processEvents()
        progress.close()

        # Icons (unchanged)
        patient_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        study_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        series_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)
        instance_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)

        for patient, studies in hierarchy.items():
            patient_item = QTreeWidgetItem([patient])
            patient_item.setIcon(0, patient_icon)
            font = patient_item.font(0)
            font.setBold(True)
            patient_item.setFont(0, font)
            self.tree.addTopLevelItem(patient_item)
            
            for study, series_dict in studies.items():
                study_item = QTreeWidgetItem([patient, study])
                study_item.setIcon(1, study_icon)
                font2 = study_item.font(1)
                font2.setBold(True)
                study_item.setFont(1, font2)
                patient_item.addChild(study_item)
                
                for series, instances in series_dict.items():
                    series_item = QTreeWidgetItem([patient, study, series])
                    series_item.setIcon(2, series_icon)
                    study_item.addChild(series_item)
                    
                    # CHANGED: Sort instances by numerical InstanceNumber instead of alphabetical
                    sorted_instances = sorted(instances.items(), key=lambda x: x[1]['sort_key'])
                    
                    for instance_label, instance_data in sorted_instances:
                        filepath = instance_data['filepath']
                        instance_item = QTreeWidgetItem([patient, study, series, str(instance_label)])
                        instance_item.setIcon(3, instance_icon)
                        # Store filepath in UserRole for easy access
                        instance_item.setData(0, Qt.ItemDataRole.UserRole, filepath)
                        series_item.addChild(instance_item)
        
        self.tree.expandAll()

        # Rest of summary calculation (unchanged)
        patient_count = len(hierarchy)
        study_count = sum(len(studies) for studies in hierarchy.values())
        series_count = sum(len(series_dict) for studies in hierarchy.values() for series_dict in studies.values())
        instance_count = len(files)
        modality_str = ", ".join(sorted(modalities)) if modalities else "Unknown"
        total_bytes = sum(os.path.getsize(f) for f in files if os.path.exists(f))
        if total_bytes < 1024 * 1024 * 1024:
            size_str = f"{total_bytes / (1024 * 1024):.2f} MB"
        else:
            size_str = f"{total_bytes / (1024 * 1024 * 1024):.2f} GB"
        self.summary_label.setText(
            f"Patients: {patient_count} | Studies: {study_count} | Series: {series_count} | Instances: {instance_count} | Modalities: {modality_str} | Size: {size_str}"
        )
        self.statusBar().showMessage(f"Loaded {instance_count} instances.")


    def display_selected_file(self, row): # User's original display_selected_file (seems for a list, not tree)
        if row < 0 or row >= len(self.loaded_files):
            # self.tag_view.clear() # tag_view not defined in MainWindow snippet
            return
        file_path, _ = self.loaded_files[row]
        try:
            ds = pydicom.dcmread(file_path)
            tags = []
            for elem in ds:
                if elem.tag == (0x7fe0, 0x0010):
                    tags.append(f"{elem.tag} {elem.name}: <Pixel Data not shown>")
                elif elem.VR == "OB" or elem.VR == "OW" or elem.VR == "UN":
                    tags.append(f"{elem.tag} {elem.name}: <Binary data not shown>")
                else:
                    tags.append(f"{elem.tag} {elem.name}: {elem.value}")
            # self.tag_view.setText("\n".join(tags)) # tag_view not defined
        except Exception as e:
            # self.tag_view.setText(f"Error reading file: {e}") # tag_view not defined
            FocusAwareMessageBox.critical(self, "Error", f"Error reading file: {e}")


    def display_selected_tree_file(self):
        # Safety check: ensure flags are initialized
        if not hasattr(self, 'has_unsaved_tag_changes'):
            self.has_unsaved_tag_changes = False
        if not hasattr(self, 'reverting_selection'):
            self.reverting_selection = False
        
        # Skip if we're in the middle of reverting selection
        if self.reverting_selection:
            return
        
        # Check for unsaved changes before navigating away
        if self.has_unsaved_tag_changes and self.current_filepath:
            choice = self._prompt_for_unsaved_changes()
            
            if choice == "keep_editing":
                # Don't navigate away, revert tree selection to current file
                self._revert_tree_selection_to_current_file()
                return
            # If choice == "discard", continue with navigation and clear changes
        
        # Original display_selected_tree_file logic
        selected = self.tree.selectedItems()
        if not selected:
            self.tag_table.setRowCount(0)
            self.current_filepath = None
            self.current_ds = None
            self.image_label.clear()
            self.image_label.setVisible(False)
            self._clear_unsaved_changes()
            return
        
        item = selected[0]
        filepath = item.data(0, Qt.ItemDataRole.UserRole)

        if not filepath:
            self.tag_table.setRowCount(0)
            self.current_filepath = None
            self.current_ds = None
            self.image_label.clear()
            self.image_label.setVisible(False)
            self._clear_unsaved_changes()
            return
        
        # Avoid reloading if the same file is already current
        if self.current_filepath == filepath and self.current_ds is not None:
            self._update_image_preview(self.current_ds)
            return

        try:
            start_time = time.time()
            
            ds = pydicom.dcmread(filepath)
            
            load_time = time.time() - start_time
            
            self.current_filepath = filepath
            self.current_ds = ds
            self.populate_tag_table(ds)
            
            if load_time > 0.5:
                print(f"SLOW LOADING DETECTED ({load_time:.2f}s)")
                self.diagnose_image_performance(ds, filepath)
            elif load_time > 0.1:
                print(f"Moderate loading time: {load_time:.2f}s for {os.path.basename(filepath)}")
            
            self._update_image_preview(ds)
            
        except Exception as e:
            self.tag_table.setRowCount(0)
            self.current_filepath = None
            self.current_ds = None
            self.image_label.clear()
            self.image_label.setVisible(False)
            self._clear_unsaved_changes()
            FocusAwareMessageBox.critical(self, "Error", f"Error reading file: {filepath}\n{e}")
            logging.error(f"Error reading file {filepath}: {e}", exc_info=True)

    def _update_image_preview(self, ds):
        """Update image preview with proper clearing and load button for large images"""
        # ALWAYS clear everything first, regardless of toggle state
        self._clear_all_preview_content()
        
        if not self.preview_toggle.isChecked():
            return
        
        # Check image size
        rows = getattr(ds, 'Rows', 0)
        cols = getattr(ds, 'Columns', 0)
        bits = getattr(ds, 'BitsAllocated', 8)
        samples = getattr(ds, 'SamplesPerPixel', 1)
        estimated_size_mb = (rows * cols * bits * samples) / (8 * 1024 * 1024)
        
        if estimated_size_mb > 5:  # Show button for large images
            self._show_load_button(ds, estimated_size_mb)
        else:
            # Load normally for small images
            try:
                pixmap = self._get_dicom_pixmap(ds)
                if pixmap:
                    # Scale pixmap to fit the label while maintaining aspect ratio
                    scaled_pixmap = pixmap.scaledToHeight(self.image_label.height(), Qt.TransformationMode.SmoothTransformation)
                    if scaled_pixmap.width() > self.image_label.width():
                        scaled_pixmap = pixmap.scaledToWidth(self.image_label.width(), Qt.TransformationMode.SmoothTransformation)
                    self.image_label.setPixmap(scaled_pixmap)
                    self.image_label.setVisible(True)
                else:
                    self.image_label.setText("No preview available")
                    self.image_label.setVisible(True)
            except Exception as e:
                logging.error(f"Error creating pixmap: {e}")
                self.image_label.setText("Error loading image")
                self.image_label.setVisible(True)

    def _clear_all_preview_content(self):
        """Clear all possible preview content (images, buttons, progress, etc.)"""
        # Clear image label
        self.image_label.clear()
        self.image_label.setStyleSheet("")  # Reset any error styling
        self.image_label.setVisible(False)
        
        # Remove button widget if it exists
        if hasattr(self, 'button_widget') and self.button_widget:
            self.button_widget.setParent(None)
            self.button_widget.deleteLater()
            self.button_widget = None
        
        # Remove progress widget if it exists
        if hasattr(self, 'progress_widget') and self.progress_widget:
            self.progress_widget.setParent(None)
            self.progress_widget.deleteLater()
            self.progress_widget = None
        
        # Cancel any running image loading
        if hasattr(self, 'image_loader') and self.image_loader and self.image_loader.isRunning():
            self.image_loader.cancel()
            self.image_loader.wait(100)

    def _show_load_button(self, ds, size_mb):
        """Show load button for large images"""
        # Make sure everything is cleared first
        self._clear_all_preview_content()
        
        # Create button widget
        button_widget = QWidget()
        button_layout = QVBoxLayout(button_widget)
        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        button_layout.setSpacing(10)
        
        # Info label
        info_label = QLabel(f"Large Image\n{size_mb:.1f}MB\n{getattr(ds, 'Columns', '?')} x {getattr(ds, 'Rows', '?')} pixels")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet("""
            QLabel {
                color: #f5f5f5;
                font-size: 12px;
                background-color: #2c2f33;
                padding: 10px;
                border-radius: 5px;
            }
        """)
        
        # Load button
        load_btn = QPushButton("Load Image")
        load_btn.setFixedSize(120, 40)
        load_btn.setStyleSheet("""
            QPushButton {
                background-color: #508cff;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #6ea3ff;
            }
            QPushButton:pressed {
                background-color: #3d75e6;
            }
        """)
        
        # Connect button to loading function
        load_btn.clicked.connect(lambda: self._load_large_image(ds, size_mb))
        
        button_layout.addWidget(info_label)
        button_layout.addWidget(load_btn)
        
        # Store reference and add to layout
        self.button_widget = button_widget
        
        # Find the image label's parent layout and insert button widget
        parent_layout = self.image_label.parent().layout()
        if parent_layout:
            index = parent_layout.indexOf(self.image_label)
            parent_layout.insertWidget(index, button_widget)

    def _load_large_image(self, ds, size_mb):
        """Load large image with progress dialog"""
        # Clear button widget first
        if hasattr(self, 'button_widget') and self.button_widget:
            self.button_widget.setParent(None)
            self.button_widget.deleteLater()
            self.button_widget = None
        
        # Show progress dialog
        progress = FocusAwareProgressDialog(f"Loading {size_mb:.1f}MB image...", "Cancel", 0, 100, self)
        progress.setWindowTitle("Loading Large Image")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        
        try:
            # Update progress
            progress.setValue(25)
            QApplication.processEvents()
            
            if progress.wasCanceled():
                self._show_cancelled_message()
                return
            
            progress.setValue(50)
            progress.setLabelText("Processing pixel data...")
            QApplication.processEvents()
            
            # Load the image
            pixmap = self._get_dicom_pixmap(ds)
            
            progress.setValue(100)
            QApplication.processEvents()
            
            if pixmap and not progress.wasCanceled():
                # Scale and display
                scaled_pixmap = pixmap.scaledToHeight(self.image_label.height(), Qt.TransformationMode.SmoothTransformation)
                if scaled_pixmap.width() > self.image_label.width():
                    scaled_pixmap = pixmap.scaledToWidth(self.image_label.width(), Qt.TransformationMode.SmoothTransformation)
                self.image_label.setPixmap(scaled_pixmap)
                self.image_label.setVisible(True)
            else:
                self._show_error_message("Failed to load image")
                
        except Exception as e:
            logging.error(f"Error loading large image: {e}")
            self._show_error_message(f"Error: {e}")
        finally:
            progress.close()

    def _remove_button_widget(self):
        """Remove button widget and restore image label"""
        if hasattr(self, 'button_widget') and self.button_widget:
            self.button_widget.setParent(None)
            self.button_widget.deleteLater()
            self.button_widget = None
        
        self.image_label.setVisible(True)

    def _show_cancelled_message(self):
        """Show cancelled message"""
        self.image_label.setText("Loading Cancelled")
        self.image_label.setStyleSheet("color: #f5f5f5; background-color: #444; padding: 20px;")
        self.image_label.setVisible(True)

    def _show_error_message(self, message):
        """Show error message in image area"""
        self.image_label.setText(f"Error Loading Image\n\n{message}")
        self.image_label.setStyleSheet("color: #ff6b6b; background-color: #444; padding: 20px;")
        self.image_label.setVisible(True)

    def _get_dicom_pixmap(self, ds): # User's original
        try:
            if 'PixelData' not in ds:
                return None
            arr = ds.pixel_array
            if arr.ndim == 2:
                arr = self._normalize_grayscale(arr)
                h, w = arr.shape
                # Ensure data is C-contiguous for QImage
                if not arr.flags.c_contiguous: arr = np.ascontiguousarray(arr)
                qimg = QImage(arr.data, w, h, w, QImage.Format.Format_Grayscale8)
            elif arr.ndim == 3:
                if arr.shape[2] == 3: # RGB
                    h, w, c = arr.shape
                    # Ensure data is C-contiguous and uint8 for RGB888
                    if arr.dtype != np.uint8: arr = (arr / arr.max() * 255).astype(np.uint8) # Basic normalization if not uint8
                    if not arr.flags.c_contiguous: arr = np.ascontiguousarray(arr)
                    qimg = QImage(arr.data, w, h, 3 * w, QImage.Format.Format_RGB888)
                else:
                    return None # Not grayscale or RGB
            else:
                return None # Not 2D or 3D array
            return QPixmap.fromImage(qimg)
        except Exception as e:
            logging.error(f"Error creating pixmap: {e}", exc_info=True)
            return None

    def _normalize_grayscale(self, arr): # User's original
        arr = arr.astype(np.float32)
        arr -= arr.min()
        if arr.max() > 0: # Avoid division by zero for blank images
            arr /= arr.max()
        arr = (arr * 255).astype(np.uint8)
        return arr

    def populate_tag_table(self, ds):
        self.tag_table.setRowCount(0)
        self._all_tag_rows = []
        
        # Temporarily disconnect change tracking to avoid false positives during population
        try:
            self.tag_table.itemChanged.disconnect()
        except:
            pass  # No connection exists yet
        
        for elem in ds:
            if elem.tag == (0x7fe0, 0x0010):
                value = "<Pixel Data not shown>"
            elif elem.VR in ("OB", "OW", "UN"):
                value = "<Binary data not shown>"
            else:
                value = str(elem.value)
            tag_id = f"({elem.tag.group:04X},{elem.tag.element:04X})"
            desc = elem.name
            row_data = [tag_id, desc, value, ""]
            self._all_tag_rows.append({'elem_obj': elem, 'display_row': row_data})
        
        self.apply_tag_table_filter()
        
        # Clear unsaved changes flag when loading new file
        self._clear_unsaved_changes()
        
        # Connect change tracking
        self.tag_table.itemChanged.connect(self._on_tag_item_changed)

    def apply_tag_table_filter(self): # User's original logic, adapted to use _all_tag_rows structure
        filter_text = self.search_bar.text().lower()
        self.tag_table.setRowCount(0)
        for row_info in self._all_tag_rows:
            elem_obj = row_info['elem_obj']
            display_row_data = row_info['display_row']
            tag_id, desc, value, _ = display_row_data # Original value, new_value placeholder

            if filter_text in tag_id.lower() or filter_text in desc.lower():
                row_idx = self.tag_table.rowCount()
                self.tag_table.insertRow(row_idx)
                self.tag_table.setItem(row_idx, 0, QTableWidgetItem(tag_id))
                self.tag_table.setItem(row_idx, 1, QTableWidgetItem(desc))
                self.tag_table.setItem(row_idx, 2, QTableWidgetItem(value))
                
                new_value_item = QTableWidgetItem("") # Placeholder for new value input
                # Store original pydicom element with the "New Value" item for easy access to VR, etc.
                new_value_item.setData(Qt.ItemDataRole.UserRole, elem_obj)

                if elem_obj.tag == (0x7fe0, 0x0010) or elem_obj.VR in ("OB", "OW", "UN", "SQ"): # SQ also not editable this way
                    new_value_item.setFlags(new_value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.tag_table.setItem(row_idx, 3, new_value_item)
        # Set sensible default column widths after populating
        self.tag_table.setColumnWidth(0, 110)   # Tag ID
        self.tag_table.setColumnWidth(1, 220)   # Description
        self.tag_table.setColumnWidth(2, 260)   # Value
        self.tag_table.setColumnWidth(3, 160)   # New Value
        # Do NOT call resizeColumnsToContents here, so user-resizing is preserved

    def save_tag_changes(self): # User's original
        if not self.current_ds or not self.current_filepath:
            FocusAwareMessageBox.warning(self, "No File", "No DICOM file selected.")
            return

        level = self.edit_level_combo.currentText()
        selected = self.tree.selectedItems()
        if not selected:
            FocusAwareMessageBox.warning(self, "No Selection", "Please select a node in the tree.")
            return
        tree_item = selected[0]

        level_map = {"Patient": 0, "Study": 1, "Series": 2, "Instance": 3}
        target_level = level_map[level]
        
        # Correctly find the node corresponding to the selected level relative to the clicked item
        # If "Patient" is selected, find the patient ancestor of the clicked item.
        node_at_target_level = tree_item
        while node_at_target_level.depth() > target_level and node_at_target_level.parent():
            node_at_target_level = node_at_target_level.parent()
        # If current node is shallower than target level (e.g. selected series, want instance), this logic might be insufficient.
        # The _collect_instance_filepaths should start from node_at_target_level

        filepaths = self._collect_instance_filepaths(node_at_target_level) # Use the adjusted node
        if not filepaths:
            FocusAwareMessageBox.warning(self, "No Instances", "No DICOM instances found under this node for the selected level.")
            return

        edits = []
        for i in range(self.tag_table.rowCount()):
            new_value_item = self.tag_table.item(i, 3) # Corrected item access
            if new_value_item and new_value_item.text().strip() != "":
                tag_id_str = self.tag_table.item(i, 0).text()
                original_elem = new_value_item.data(Qt.ItemDataRole.UserRole) # Get original elem

                try:
                    group_hex, elem_hex = tag_id_str[1:-1].split(",") # Corrected string slicing
                    tag_tuple = (int(group_hex, 16), int(elem_hex, 16))
                    
                    # Use original_elem to guide type conversion
                    edits.append({'tag': tag_tuple, 'value_str': new_value_item.text(), 'original_elem': original_elem})
                except Exception as e:
                    FocusAwareMessageBox.warning(self, "Error", f"Failed to parse tag {tag_id_str} or get original element: {e}")
                    logging.error(f"Error parsing tag {tag_id_str}: {e}", exc_info=True)


        if not edits:
            FocusAwareMessageBox.information(self, "No Changes", "No tags were changed.")
            return

        updated_count = 0
        failed_files = []
        progress = FocusAwareProgressDialog(f"Saving changes to {level}...", "Cancel", 0, len(filepaths), self)
        progress.setWindowTitle("Saving Tag Changes"); progress.setMinimumDuration(0); progress.setValue(0)

        for idx, fp in enumerate(filepaths):
            progress.setValue(idx)
            if progress.wasCanceled(): break
            QApplication.processEvents()
            try:
                ds = pydicom.dcmread(fp)
                file_updated = False
                for edit_info in edits:
                    tag = edit_info['tag']
                    new_val_str = edit_info['value_str']
                    original_elem_ref = edit_info['original_elem'] # This is a pydicom.DataElement

                    if tag in ds: # Modify existing tag
                        target_elem = ds[tag]
                        try:
                            # Attempt type conversion based on original element's VR
                            if original_elem_ref.VR == "UI": converted_value = new_val_str
                            elif original_elem_ref.VR in ["IS", "SL", "SS", "UL", "US"]: converted_value = int(new_val_str)
                            elif original_elem_ref.VR in ["FL", "FD", "DS"]: converted_value = float(new_val_str)
                            elif original_elem_ref.VR == "DA": converted_value = new_val_str.replace("-","") # YYYYMMDD
                            elif original_elem_ref.VR == "TM": converted_value = new_val_str.replace(":","") # HHMMSS.FFFFFF
                            elif isinstance(target_elem.value, list): # For multi-valued elements
                                converted_value = [v.strip() for v in new_val_str.split('\\')] # DICOM standard is backslash
                            elif isinstance(target_elem.value, pydicom.personname.PersonName):
                                converted_value = new_val_str # pydicom handles PersonName string
                            else: # Try direct cast to original Python type
                                converted_value = type(target_elem.value)(new_val_str)
                            
                            target_elem.value = converted_value
                            file_updated = True
                        except Exception as e_conv:
                            logging.warning(f"Could not convert value '{new_val_str}' for tag {tag} (VR: {original_elem_ref.VR}) in {fp}. Error: {e_conv}. Saving as string.")
                            target_elem.value = new_val_str # Fallback to string if conversion fails
                            file_updated = True
                if file_updated:
                    ds.save_as(fp)
                    updated_count += 1
            except Exception as e_file:
                logging.error(f"Failed to process file {fp}: {e_file}", exc_info=True)
                failed_files.append(os.path.basename(fp))
        progress.setValue(len(filepaths))
        
        msg = f"Updated {updated_count} of {len(filepaths)} file(s) at the {level} level."
        if failed_files:
            msg += f"\nFailed to update: {', '.join(failed_files)}"
        FocusAwareMessageBox.information(self, "Batch Edit Complete", msg)
        
        self._clear_unsaved_changes()

        # Refresh view if the currently displayed file was part of the batch
        if self.current_filepath in filepaths:
            self.display_selected_tree_file()
        elif filepaths: # If any files were processed, clear tag table to avoid stale "New Value"
            self.tag_table.setRowCount(0) 


    def edit_tag(self): # Enhanced with tag search
        """Edit a tag using searchable interface"""
        selected = self.tree.selectedItems()
        if not selected:
            FocusAwareMessageBox.warning(self, "No Selection", "Please select an instance in the tree.")
            return
        item = selected[0]
        filepath = item.data(0, Qt.ItemDataRole.UserRole)
        if not filepath:
            FocusAwareMessageBox.warning(self, "No Instance", "Please select an instance node.")
            return
        try:
            ds = pydicom.dcmread(filepath)
        except Exception as e:
            FocusAwareMessageBox.critical(self, "Error", f"Could not read file: {e}")
            return
        
        # Show tag search dialog
        tag_dialog = TagSearchDialog(self, "Select Tag to Edit")
        if tag_dialog.exec() != QDialog.DialogCode.Accepted:
            return
            
        tag_info = tag_dialog.get_selected_tag_info()
        if not tag_info['tag']:
            return
            
        # Parse the selected tag
        tag = None
        tag_str = tag_info['tag']
        
        if ',' in tag_str and tag_str.startswith("(") and tag_str.endswith(")"):
            try:
                group, elem = tag_str[1:-1].split(',')
                tag = (int(group, 16), int(elem, 16))
            except ValueError:
                FocusAwareMessageBox.warning(self, "Invalid Tag", "Invalid tag format.")
                return
        else:
            try:
                tag = pydicom.tag.Tag(tag_str.strip())
            except ValueError:
                FocusAwareMessageBox.warning(self, "Invalid Tag", f"Tag '{tag_str}' not recognized.")
                return

        # Check if tag exists and get current value
        current_value = ""
        tag_exists = tag in ds
        
        if tag_exists:
            current_value = str(ds[tag].value)
        else:
            # Ask if user wants to add new tag
            reply = FocusAwareMessageBox.question(
                self, "Tag Not Found", 
                f"Tag {tag_info['name']} ({tag}) not found in this file. Add it as a new tag?",
                FocusAwareMessageBox.StandardButton.Yes | FocusAwareMessageBox.StandardButton.No
            )
            if reply != FocusAwareMessageBox.StandardButton.Yes:
                return
                
        # Show value entry dialog
        value_dialog = ValueEntryDialog(tag_info, current_value, self)
        if value_dialog.exec() != QDialog.DialogCode.Accepted:
            return
            
        new_value = value_dialog.new_value
        
        try:
            if tag_exists:
                # Modify existing tag
                original_element = ds[tag]
                
                # Type conversion based on VR
                if tag_info['vr']:
                    converted_value = self._convert_value_by_vr(new_value, tag_info['vr'])
                else:
                    # Fall back to original type conversion
                    if original_element.VR == "UI": 
                        converted_value = new_value
                    elif original_element.VR in ["IS", "SL", "SS", "UL", "US"]: 
                        converted_value = int(new_value)
                    elif original_element.VR in ["FL", "FD", "DS"]: 
                        converted_value = float(new_value)
                    elif original_element.VR == "DA": 
                        converted_value = new_value.replace("-","")
                    elif original_element.VR == "TM": 
                        converted_value = new_value.replace(":","")
                    else: 
                        converted_value = new_value
                        
                ds[tag].value = converted_value
                
            else:
                # Add new tag
                vr = tag_info['vr'] or 'LO'  # Default to LO if VR unknown
                converted_value = self._convert_value_by_vr(new_value, vr)
                ds.add_new(tag, vr, converted_value)
                
            ds.save_as(filepath)
            FocusAwareMessageBox.information(self, "Success", f"Tag {tag_info['name']} updated successfully.")
            self.display_selected_tree_file()
            
        except Exception as e:
            logging.error(f"Failed to update tag {tag}: {e}")
            FocusAwareMessageBox.critical(self, "Error", f"Failed to update tag: {str(e)}")


    def batch_edit_tag(self):
        """Batch edit tags using searchable interface with selection validation"""
        selected = self.tree.selectedItems()
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
            item_files = self._collect_instance_filepaths(item)
            filepaths.extend(item_files)
        
        # Remove duplicates
        filepaths = list(set(filepaths))
        
        if not filepaths:
            FocusAwareMessageBox.warning(self, "No Instances", "No DICOM instances found under the selected nodes.")
            return

        # ... rest of your existing batch_edit_tag method (tag search, confirmation, etc.) ...
        
        # Show tag search dialog
        tag_dialog = TagSearchDialog(self, "Select Tag for Batch Edit")
        if tag_dialog.exec() != QDialog.DialogCode.Accepted:
            return
            
        tag_info = tag_dialog.get_selected_tag_info()
        if not tag_info['tag']:
            return
            
        # Parse the selected tag
        tag = None
        tag_str = tag_info['tag']
        
        if ',' in tag_str and tag_str.startswith("(") and tag_str.endswith(")"):
            try:
                group, elem = tag_str[1:-1].split(',')
                tag = (int(group, 16), int(elem, 16))
            except ValueError:
                FocusAwareMessageBox.warning(self, "Invalid Tag", "Invalid tag format.")
                return
        else:
            try:
                tag = pydicom.tag.Tag(tag_str.strip())
            except ValueError:
                FocusAwareMessageBox.warning(self, "Invalid Tag", f"Tag '{tag_str}' not recognized.")
                return

        # Check if tag exists in sample file
        current_value = ""
        try:
            ds_sample = pydicom.dcmread(filepaths[0], stop_before_pixels=True)
            if tag in ds_sample:
                current_value = str(ds_sample[tag].value)
            else:
                current_value = "<New Tag>"
        except Exception as e:
            FocusAwareMessageBox.critical(self, "Error", f"Could not read sample file: {e}")
            return

        # Show value entry dialog
        value_dialog = ValueEntryDialog(tag_info, current_value, self)
        value_dialog.setWindowTitle(f"Batch Edit: {tag_info['name']}")
        
        if value_dialog.exec() != QDialog.DialogCode.Accepted:
            return
            
        new_value = value_dialog.new_value
        
        # Final confirmation with file count
        reply = FocusAwareMessageBox.question(
            self, "Confirm Batch Edit",
            f"This will update the tag '{tag_info['name']}' in {len(filepaths)} files.\n"
            f"New value: '{new_value}'\n\n"
            "This operation cannot be undone. Continue?",
            FocusAwareMessageBox.StandardButton.Yes | FocusAwareMessageBox.StandardButton.No,
            FocusAwareMessageBox.StandardButton.No
        )
        if reply != FocusAwareMessageBox.StandardButton.Yes:
            return

        # Perform batch edit
        updated_count = 0
        failed_files = []
        progress = FocusAwareProgressDialog(f"Batch editing {tag_info['name']}...", "Cancel", 0, len(filepaths), self)
        progress.setWindowTitle("Batch Tag Edit")
        progress.setMinimumDuration(0)
        progress.setValue(0)

        for idx, filepath in enumerate(filepaths):
            progress.setValue(idx)
            if progress.wasCanceled():
                break
            QApplication.processEvents()
            
            try:
                ds = pydicom.dcmread(filepath)
                
                # Determine VR
                if tag in ds:
                    vr = ds[tag].VR
                else:
                    vr = tag_info['vr'] or 'LO'
                    
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
                
        progress.setValue(len(filepaths))
        
        # Show results
        msg = f"Batch edit complete.\nUpdated {updated_count} of {len(filepaths)} files."
        if failed_files:
            msg += f"\nFailed: {len(failed_files)} files."
            
        FocusAwareMessageBox.information(self, "Batch Edit Complete", msg)
        
        all_known_files_after_edit = [f_info[0] for f_info in self.loaded_files if os.path.exists(f_info[0])]
        if all_known_files_after_edit:
            self._load_dicom_files_from_list(all_known_files_after_edit, "data after batch edit")
        
        # Refresh current file display if it was part of the batch
        if self.current_filepath in filepaths:
            self.display_selected_tree_file()

    def _analyze_batch_edit_selection(self, selected_items):
        """Analyze the selection to determine if it's appropriate for batch editing"""
        
        if not selected_items:
            return {
                'is_valid': False,
                'message': "Please select a node in the tree.",
                'show_confirmation': False
            }
        
        # Analyze what types of nodes are selected
        depths = [item.depth() for item in selected_items]
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
            total_files = sum(len(self._collect_instance_filepaths(item)) for item in selected_items)
            return {
                'is_valid': True,
                'message': '',
                'show_confirmation': True,
                'confirmation_message': (
                    f"You have selected {series_count} series.\n\n"
                    f"This will batch edit tags in approximately {total_files} files across these series.\n\n"
                    "Continue with batch edit?"
                )
            }
        
        # Study level selection(s)
        if all(depth == 1 for depth in depths):
            study_count = len(selected_items)
            total_files = sum(len(self._collect_instance_filepaths(item)) for item in selected_items)
            return {
                'is_valid': True,
                'message': '',
                'show_confirmation': True,
                'confirmation_message': (
                    f"You have selected {study_count} studies.\n\n"
                    f"This will batch edit tags in approximately {total_files} files across these studies.\n\n"
                    "Continue with batch edit?"
                )
            }
        
        # Patient level selection(s)
        if all(depth == 0 for depth in depths):
            patient_count = len(selected_items)
            total_files = sum(len(self._collect_instance_filepaths(item)) for item in selected_items)
            return {
                'is_valid': True,
                'message': '',
                'show_confirmation': True,
                'confirmation_message': (
                    f"You have selected {patient_count} patients.\n\n"
                    f"This will batch edit tags in approximately {total_files} files for these patients.\n\n"
                    "Continue with batch edit?"
                )
            }
        
        # Mixed selection levels
        level_names = {0: "Patient", 1: "Study", 2: "Series", 3: "Instance"}
        selected_levels = [level_names[depth] for depth in unique_depths]
        total_files = sum(len(self._collect_instance_filepaths(item)) for item in selected_items)
        
        return {
            'is_valid': True,
            'message': '',
            'show_confirmation': True,
            'confirmation_message': (
                f"You have selected items at multiple levels: {', '.join(selected_levels)}.\n\n"
                f"This will batch edit tags in approximately {total_files} files.\n\n"
                "Continue with batch edit?"
            )
        }
    
    def _convert_value_by_vr(self, value_str, vr):
        """Convert string value to appropriate type based on VR"""
        if not value_str:
            return value_str
            
        try:
            if vr in ["IS", "SL", "SS", "UL", "US"]:
                return int(value_str)
            elif vr in ["FL", "FD", "DS"]:
                return float(value_str)
            elif vr == "DA":
                return value_str.replace("-", "")  # Remove dashes from dates
            elif vr == "TM":
                return value_str.replace(":", "")  # Remove colons from times
            else:
                return value_str  # String types
        except ValueError:
            # If conversion fails, return as string
            return value_str


    def save_as(self): 
        selected = self.tree.selectedItems()
        if not selected:
            FocusAwareMessageBox.warning(self, "No Selection", "Please select a node in the tree to export.")
            return
        
        # Collect files from ALL selected items
        filepaths = []
        for tree_item in selected:
            item_files = self._collect_instance_filepaths(tree_item)
            filepaths.extend(item_files)
        
        # Remove duplicates
        filepaths = list(set(filepaths))

        if not filepaths:
            FocusAwareMessageBox.warning(self, "No Instances", "No DICOM instances found under the selected nodes.")
            return

        # Show selection summary
        logging.info(f"Collected {len(filepaths)} files from {len(selected)} selected items")

        # Get export type
        export_type, ok = QInputDialog.getItem(
            self, "Export Type", "Export as:", 
            ["Directory", "ZIP", "ZIP with DICOMDIR"], 0, False
        )
        if not ok:
            return

        # FIX: Map export_type to worker_export_type
        if export_type == "Directory":
            worker_export_type = "directory"
        elif export_type == "ZIP":
            worker_export_type = "zip"
        elif export_type == "ZIP with DICOMDIR":
            worker_export_type = "zip_with_dicomdir"
        else:
            # Fallback - should not happen but just in case
            worker_export_type = "directory"
        
        # Get output path based on export type
        if worker_export_type == "directory":
            output_path = QFileDialog.getExistingDirectory(
                self, "Select Export Directory", 
                os.path.expanduser("~/Desktop")
            )
        else:  # ZIP or ZIP with DICOMDIR
            output_path, _ = QFileDialog.getSaveFileName(
                self, "Save Export As", 
                os.path.expanduser("~/Desktop/dicom_export.zip"),
                "ZIP files (*.zip)"
            )
        
        if not output_path:
            return

        # Now start the export worker
        self._start_export_worker(filepaths, worker_export_type, output_path)

    def _start_export_worker(self, filepaths, export_type, output_path):
        """Start the export worker thread"""
        
        # Create progress dialog
        self.export_progress = FocusAwareProgressDialog("Preparing export...", "Cancel", 0, 100, self)
        self.export_progress.setWindowTitle("Export Progress")
        self.export_progress.setMinimumDuration(0)
        self.export_progress.setValue(0)
        self.export_progress.canceled.connect(self._cancel_export)
        
        # Create temporary directory for DICOMDIR exports
        temp_dir = None
        if export_type == "dicomdir_zip":
            temp_dir = tempfile.mkdtemp()
        
        # Create and start worker
        self.export_worker = ExportWorker(filepaths, export_type, output_path, temp_dir)
        self.export_worker.progress_updated.connect(self._on_export_progress)
        self.export_worker.stage_changed.connect(self._on_export_stage_changed)
        self.export_worker.export_complete.connect(self._on_export_complete)
        self.export_worker.export_failed.connect(self._on_export_failed)
        
        logging.info(f"Starting {export_type} export to {output_path}")
        self.export_worker.start()

    def _on_export_progress(self, current, total, operation):
        """Handle export progress updates"""
        if hasattr(self, 'export_progress') and self.export_progress:
            if total > 0:
                progress_value = int((current / total) * 100)
                self.export_progress.setValue(progress_value)
            self.export_progress.setLabelText(f"{operation}\n({current}/{total})")

    def _on_export_stage_changed(self, stage_description):
        """Handle export stage changes"""
        if hasattr(self, 'export_progress') and self.export_progress:
            self.export_progress.setLabelText(stage_description)
            logging.info(f"Export stage: {stage_description}")

    def _on_export_complete(self, output_path, statistics):
        """Handle successful export completion"""
        if hasattr(self, 'export_progress') and self.export_progress:
            self.export_progress.close()
            self.export_progress = None
        
        # Clean up worker
        if hasattr(self, 'export_worker'):
            self.export_worker = None
        
        # Create completion message
        stats = statistics
        export_type = stats.get('export_type', 'Export')
        exported_count = stats.get('exported_count', 0)
        total_files = stats.get('total_files', 0)
        errors = stats.get('errors', [])
        
        msg = f"{export_type} completed successfully!\n\n"
        msg += f"Files exported: {exported_count}/{total_files}\n"
        
        if 'total_size_mb' in stats:
            msg += f"Total size: {stats['total_size_mb']:.1f} MB\n"
        if 'patients' in stats:
            msg += f"Patients: {stats['patients']}\n"
            
        msg += f"Output: {output_path}"
        
        if errors:
            msg += f"\n\nErrors ({len(errors)}):\n" + "\n".join(errors[:3])
            if len(errors) > 3:
                msg += f"\n...and {len(errors) - 3} more."
        
        FocusAwareMessageBox.information(self, "Export Complete", msg)
        logging.info(f"Export completed: {output_path}")

    def _on_export_failed(self, error_message):
        """Handle export failure"""
        if hasattr(self, 'export_progress') and self.export_progress:
            self.export_progress.close()
            self.export_progress = None
        
        # Clean up worker
        if hasattr(self, 'export_worker'):
            self.export_worker = None
        
        # CHANGED: Use focus-aware dialog
        FocusAwareMessageBox.information(self, "Export Failed", 
                                    f"Export failed:\n\n{error_message}")
        
        logging.error(f"Export failed: {error_message}")

    def _cancel_export(self):
        """Cancel the export operation"""
        logging.info("Export cancellation requested")
        
        if hasattr(self, 'export_worker') and self.export_worker and self.export_worker.isRunning():
            logging.info("Cancelling export worker")
            self.export_worker.cancel()
            self.export_worker.wait(3000)
            if self.export_worker.isRunning():
                logging.warning("Export worker didn't stop, terminating")
                self.export_worker.terminate()
            
            # Close progress dialog
            if hasattr(self, 'export_progress') and self.export_progress:
                self.export_progress.close()
                self.export_progress = None
        
        logging.info("Export cancelled")


    def dicom_send(self):
        """Enhanced DICOM send with file selection dialog"""
        logging.info("DICOM send initiated")
        
        if AE is None or not STORAGE_CONTEXTS or VERIFICATION_SOP_CLASS is None:
            logging.error("pynetdicom not available or not fully imported.")
            FocusAwareMessageBox.critical(self, "Missing Dependency",
                                "pynetdicom is required for DICOM send.\n"
                                "Check your environment and restart the application.\n"
                                f"Python executable: {sys.executable}\n")
            return
        
        # Get current selection for pre-population
        selected = self.tree.selectedItems()
        if not selected:
            FocusAwareMessageBox.warning(self, "No Selection", "Please select a node in the tree to send.")
            return
        
        # Show file selection dialog
        selection_dialog = DicomSendSelectionDialog(self.loaded_files, selected, self)
        
        if selection_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        # Get selected files from dialog
        filepaths = selection_dialog.get_selected_files()
        
        if not filepaths:
            FocusAwareMessageBox.warning(self, "No Files", "No files selected for sending.")
            return
        
        logging.info(f"User selected {len(filepaths)} files for DICOM send")
        
        # Continue with existing workflow - get send parameters
        dlg = DicomSendDialog(self, config=self.dicom_send_config)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        
        send_params = dlg.get_params()
        if send_params is None:
            return

        # Get unique SOP classes from selected files
        unique_sop_classes_to_send = set()
        for fp_ctx in filepaths:
            try:
                ds_ctx = pydicom.dcmread(fp_ctx, stop_before_pixels=True)
                if hasattr(ds_ctx, 'SOPClassUID'):
                    unique_sop_classes_to_send.add(ds_ctx.SOPClassUID)
            except Exception as e_ctx:
                logging.warning(f"Could not read SOPClassUID from {fp_ctx}: {e_ctx}")
        
        if not unique_sop_classes_to_send:
            FocusAwareMessageBox.critical(self, "DICOM Send Error", "No valid SOP Class UIDs found.")
            return

        # Create progress dialog
        self.send_progress = FocusAwareProgressDialog("Starting DICOM send...", "Cancel", 0, len(filepaths), self)
        self.send_progress.setWindowTitle("DICOM Send Progress")
        self.send_progress.setMinimumDuration(0)
        self.send_progress.setValue(0)
        self.send_progress.canceled.connect(self._cancel_dicom_send)
        
        logging.info("Main thread: About to create and start DicomSendWorker")
        
        # Start background send with selected files
        self.send_worker = DicomSendWorker(filepaths, send_params, unique_sop_classes_to_send)
        
        # Connect signals
        self.send_worker.progress_updated.connect(self._on_send_progress)
        self.send_worker.send_complete.connect(self._on_send_complete)
        self.send_worker.send_failed.connect(self._on_send_failed)
        self.send_worker.association_status.connect(self._on_association_status)
        self.send_worker.conversion_progress.connect(self._on_conversion_progress)
        
        logging.info("Main thread: Starting worker thread")
        self.send_worker.start()
        logging.info("Main thread: Worker thread started")

    def _on_send_progress(self, current, success, warnings, failed, current_file):
        """Handle progress updates from send worker"""
        logging.info(f"_on_send_progress called: {current}, {success}, {warnings}, {failed}, {current_file}")
        if hasattr(self, 'send_progress') and self.send_progress:
            self.send_progress.setValue(current)
            
            # Different messages for testing vs sending
            if current_file.startswith("Testing "):
                # Remove "Testing " prefix for display
                display_file = current_file.replace("Testing ", "")
                self.send_progress.setLabelText(f"Testing compatibility: {display_file}\nTested: {current}, Found incompatible: {failed}")
            else:
                # Normal sending
                self.send_progress.setLabelText(f"Sending {current_file}\nSuccess: {success}, Warnings: {warnings}, Failed: {failed}")

    def _on_send_complete(self, success, warnings, failed, error_details, converted_count):
        """Handle successful completion of send"""
        logging.info(f"_on_send_complete called: {success}, {warnings}, {failed}, {converted_count}")
        if hasattr(self, 'send_progress') and self.send_progress:
            self.send_progress.close()
            self.send_progress = None
        
        # Close conversion progress if it exists
        if hasattr(self, 'conversion_progress') and self.conversion_progress:
            self.conversion_progress.close()
            self.conversion_progress = None
        
        # Show results
        msg = f"DICOM Send Complete.\n\nSuccess: {success}\nWarnings: {warnings}\nFailed: {failed}"
        if converted_count > 0:
            msg += f"\n\nAutomatically converted {converted_count} incompatible files."
        if error_details:
            msg += "\n\nFirst few issues:\n" + "\n".join(error_details[:5])
            if len(error_details) > 5:
                msg += f"\n...and {len(error_details)-5} more."
        
        FocusAwareMessageBox.information(self, "DICOM Send Report", msg)
        logging.info(msg)

    def _on_send_failed(self, error_message):
        """Handle send failure"""
        logging.error(f"_on_send_failed called: {error_message}")
        if hasattr(self, 'send_progress') and self.send_progress:
            self.send_progress.close()
            self.send_progress = None
        
        # Close conversion progress if it exists
        if hasattr(self, 'conversion_progress') and self.conversion_progress:
            self.conversion_progress.close()
            self.conversion_progress = None
        
        FocusAwareMessageBox.critical(self, "DICOM Send Failed", error_message)
        logging.error(error_message)

    def _on_association_status(self, status_message):
        """Handle association status updates"""
        logging.info(f"_on_association_status called: {status_message}")
        if hasattr(self, 'send_progress') and self.send_progress:
            # Check if we're starting conversion
            if "Converting" in status_message and "incompatible" in status_message:
                # Create conversion progress dialog
                self.conversion_progress = FocusAwareProgressDialog("Converting incompatible files...", "Cancel", 0, 100, self)
                self.conversion_progress.setWindowTitle("Converting Images")
                self.conversion_progress.setMinimumDuration(0)
                self.conversion_progress.setValue(0)
                self.conversion_progress.canceled.connect(self._cancel_dicom_send)
                logging.info("Created conversion progress dialog")
            elif "Sending files to server" in status_message:
                # Reset the main progress bar for actual sending
                self.send_progress.setValue(0)
                self.send_progress.setLabelText("Starting file transfer...")
            else:
                # Normal status update
                self.send_progress.setLabelText(status_message)

    def _on_conversion_progress(self, current, total, filename):
        """Handle conversion progress updates"""
        logging.info(f"_on_conversion_progress called: {current}, {total}, {filename}")
        if hasattr(self, 'conversion_progress') and self.conversion_progress:
            if current < total:
                progress_percent = int((current / total) * 100) if total > 0 else 0
                self.conversion_progress.setValue(progress_percent)
                self.conversion_progress.setLabelText(f"Converting {filename}\n({current + 1}/{total})")
            else:
                # Conversion complete - close conversion dialog but DON'T trigger cancel
                logging.info("Conversion complete, closing conversion progress dialog")
                if hasattr(self, 'conversion_progress') and self.conversion_progress:
                    # Disconnect cancel signal before closing to prevent false cancellation
                    self.conversion_progress.canceled.disconnect()
                    self.conversion_progress.close()
                    self.conversion_progress = None
                    
                # Update main progress
                if hasattr(self, 'send_progress') and self.send_progress:
                    self.send_progress.setLabelText("Conversion complete, retrying send...")

    def _cancel_dicom_send(self):
        """Cancel the DICOM send operation"""
        logging.info("_cancel_dicom_send called")
        if hasattr(self, 'send_worker') and self.send_worker and self.send_worker.isRunning():
            logging.info("Cancelling send worker")
            self.send_worker.cancel()
            self.send_worker.wait(3000)
            if self.send_worker.isRunning():
                logging.warning("Send worker didn't stop, terminating")
                self.send_worker.terminate()
            
            # Close progress dialogs
            if hasattr(self, 'send_progress') and self.send_progress:
                self.send_progress.close()
                self.send_progress = None
            
            if hasattr(self, 'conversion_progress') and self.conversion_progress:
                self.conversion_progress.close()
                self.conversion_progress = None
        
        logging.info("DICOM send cancelled")

    def _cleanup_temp_files(self, temp_files):
        """Clean up temporary files"""
        logging.info(f"Cleaning up {len(temp_files)} temp files")
        for temp_file in temp_files:
            try:
                os.remove(temp_file)
                logging.info(f"Cleaned up temp file: {os.path.basename(temp_file)}")
            except Exception as e:
                logging.warning(f"Could not remove temp file {temp_file}: {e}")


    def _collect_instance_filepaths(self, tree_item): # User's original
        filepaths = []
        def collect(item):
            # Corrected: Use UserRole to get filepath
            fp = item.data(0, Qt.ItemDataRole.UserRole) # Get data from UserRole
            if fp:
                filepaths.append(fp)
            for i in range(item.childCount()):
                collect(item.child(i))
        collect(tree_item)
        return filepaths

    def clear_loaded_files(self): # User's original
        self.cleanup_temp_dir()
        self.loaded_files = []
        self.file_metadata.clear() # Also clear metadata cache
        self.tree.clear()
        # Also clear tag table and current selection state
        self.tag_table.setRowCount(0)
        self._all_tag_rows = []
        self.image_label.clear()
        self.image_label.setVisible(False)
        self.current_filepath = None
        self.current_ds = None
        self.summary_label.setText("No files loaded.") # Update summary
        self.statusBar().showMessage("Ready. Cleared loaded files.")

    def cleanup_temp_dir(self): # User's original
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                logging.info(f"Cleaned up temp directory: {self.temp_dir}")
            except Exception as e:
                logging.error(f"Error cleaning up temp directory {self.temp_dir}: {e}", exc_info=True)
            self.temp_dir = None # Reset after cleanup

    def anonymise_selected(self):
        """Advanced anonymization using templates"""
        selected = self.tree.selectedItems()
        if not selected:
            FocusAwareMessageBox.warning(self, "No Selection", "Please select a node in the tree to anonymize.")
            return
            
        # Collect file paths from selected items
        file_paths = []
        for item in selected:
            paths = self._collect_instance_filepaths(item)
            file_paths.extend(paths)
            
        if not file_paths:
            FocusAwareMessageBox.warning(self, "No Files", "No DICOM files found in selection.")
            return
            
        # Remove duplicates
        file_paths = list(set(file_paths))
        
        logging.info(f"Starting template-based anonymization of {len(file_paths)} files")
        
        try:
            result = run_anonymization(file_paths, self.template_manager, self)
            
            if result and result.anonymized_count > 0:
                # Refresh tree to show anonymized data
                all_known_files = [f_info[0] for f_info in self.loaded_files if os.path.exists(f_info[0])]
                if all_known_files:
                    self._load_dicom_files_from_list(all_known_files, "data after anonymization")
                    
        except Exception as e:
            logging.error(f"Anonymization error: {e}", exc_info=True)
            FocusAwareMessageBox.critical(self, "Anonymization Error", 
                            f"An error occurred during anonymization:\n{str(e)}")

    def merge_patients(self): # User's original
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.MultiSelection) # Allow multi-select for this op
        selected = self.tree.selectedItems()
        patient_nodes = [item for item in selected if item.depth() == 0]
        
        if len(patient_nodes) < 2:
            FocusAwareMessageBox.warning(self, "Merge Patients", "Select at least two patient nodes to merge.\nHold Ctrl or Shift to select multiple patients.")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection) # Restore selection mode
            return

        patient_labels = [item.text(0) for item in patient_nodes]
        primary_label_selected, ok = QInputDialog.getItem(
            self, "Merge Patients", "Select primary patient (whose metadata to keep):", patient_labels, 0, False
        )
        if not ok or not primary_label_selected:
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection) # Restore
            return
        
        primary_node = next(item for item in patient_nodes if item.text(0) == primary_label_selected)

        primary_fp_sample = None
        # Simplified way to get a sample file from primary patient
        primary_node_fps = self._collect_instance_filepaths(primary_node)
        if primary_node_fps: primary_fp_sample = primary_node_fps[0]

        if not primary_fp_sample:
            FocusAwareMessageBox.warning(self, "Merge Patients", f"Could not find any DICOM file for the primary patient '{primary_label_selected}' to get ID/Name.")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection) # Restore
            return
        try:
            ds_primary = pydicom.dcmread(primary_fp_sample, stop_before_pixels=True)
            primary_id_val = str(ds_primary.PatientID)
            primary_name_val = str(ds_primary.PatientName)
        except Exception as e:
            FocusAwareMessageBox.critical(self, "Merge Patients", f"Failed to read primary patient file: {e}")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection) # Restore
            return

        files_to_update = []
        secondary_nodes_to_process = [node for node in patient_nodes if node is not primary_node]
        for node_sec in secondary_nodes_to_process:
            files_to_update.extend(self._collect_instance_filepaths(node_sec))

        if not files_to_update:
             FocusAwareMessageBox.information(self, "Merge Patients", "No files found in the secondary patient(s) to merge.")
             self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection) # Restore
             return


        reply = FocusAwareMessageBox.question(
            self, "Confirm Merge",
            f"This will update {len(files_to_update)} files from other patient(s) to PatientID '{primary_id_val}' and PatientName '{primary_name_val}'.\n"
            "The original patient entries for these merged studies will be removed from the tree view.\n"
            "This modifies files in-place. Continue?",
            FocusAwareMessageBox.StandardButton.Yes | FocusAwareMessageBox.StandardButton.No, FocusAwareMessageBox.StandardButton.No
        )
        if reply != FocusAwareMessageBox.StandardButton.Yes:
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection) # Restore
            return

        updated_m = 0; failed_m = []
        progress_m = FocusAwareProgressDialog("Merging patients...", "Cancel", 0, len(files_to_update), self)
        progress_m.setWindowTitle("Merging Patients"); progress_m.setMinimumDuration(0); progress_m.setValue(0)
        for idx_m, fp_m in enumerate(files_to_update):
            progress_m.setValue(idx_m)
            if progress_m.wasCanceled(): break
            QApplication.processEvents()
            try:
                ds_m = pydicom.dcmread(fp_m)
                ds_m.PatientID = primary_id_val
                ds_m.PatientName = primary_name_val
                ds_m.save_as(fp_m)
                updated_m += 1
            except Exception as e_m_file:
                failed_m.append(f"{os.path.basename(fp_m)}: {e_m_file}")
        progress_m.setValue(len(files_to_update))
        
        # Update self.loaded_files: PatientID/Name changed, but filepath is the same.
        # The tree refresh will pick up new patient grouping.

        msg_m = f"Merged patient data.\nFiles updated: {updated_m}\nFailed: {len(failed_m)}"
        if failed_m: msg_m += "\n\nDetails (first few):\n" + "\n".join(failed_m[:3])
        FocusAwareMessageBox.information(self, "Merge Patients Complete", msg_m)

        # Refresh the tree (corrected - don't call clear_loaded_files)
        all_known_files_after_merge = [f_info[0] for f_info in self.loaded_files if os.path.exists(f_info[0])]
        if all_known_files_after_merge:
            self._load_dicom_files_from_list(all_known_files_after_merge, "data after merge")

        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)

    # --- NEW: Study Merging ---
    def merge_studies(self):
        """Merge multiple studies under the same patient into a single study"""
        logging.info("Study merge initiated")
        
        # Enable multi-selection temporarily
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.MultiSelection)
        selected = self.tree.selectedItems()
        study_nodes = [item for item in selected if item.depth() == 1]
        
        # Validate selection
        if len(study_nodes) < 2:
            FocusAwareMessageBox.warning(self, "Merge Studies", "Select at least two study nodes to merge.\nHold Ctrl or Shift to select multiple studies.")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return
        
        if not self._are_studies_under_same_patient(study_nodes):
            FocusAwareMessageBox.warning(self, "Merge Studies", "All selected studies must belong to the same patient.")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return
        
        # Show primary selection dialog
        primary_dialog = PrimarySelectionDialog(self, study_nodes, "Study")
        if primary_dialog.exec() != QDialog.DialogCode.Accepted:
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return
        
        primary_index = primary_dialog.get_selected_index()
        primary_study_node = study_nodes[primary_index]
        
        # Get primary study metadata
        primary_study_files = self._collect_instance_filepaths(primary_study_node)
        if not primary_study_files:
            FocusAwareMessageBox.warning(self, "Merge Studies", "Could not find any files in the primary study.")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return
        
        try:
            ds_primary = pydicom.dcmread(primary_study_files[0], stop_before_pixels=True)
            primary_study_uid = str(ds_primary.StudyInstanceUID)
            primary_study_desc = str(getattr(ds_primary, "StudyDescription", ""))
            primary_study_id = str(getattr(ds_primary, "StudyID", ""))
        except Exception as e:
            FocusAwareMessageBox.critical(self, "Merge Studies", f"Failed to read primary study metadata: {e}")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return

        files_to_update = []
        secondary_nodes_to_process = [node for node in study_nodes if node is not primary_study_node]
        for node_sec in secondary_nodes_to_process:
            files_to_update.extend(self._collect_instance_filepaths(node_sec))

        if not files_to_update:
            FocusAwareMessageBox.information(self, "Merge Studies", "No files found in the secondary studies to merge.")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return
        
        # Confirmation dialog
        reply = FocusAwareMessageBox.question(
            self, "Confirm Merge",
            f"This will update {len(files_to_update)} files from other study(s) to merge into:\n"
            f"Study UID: {primary_study_uid}\n"
            f"Study Description: {primary_study_desc}\n"
            f"Study ID: {primary_study_id}\n"
            "This modifies files in-place. Continue?",
            FocusAwareMessageBox.StandardButton.Yes | FocusAwareMessageBox.StandardButton.No, FocusAwareMessageBox.StandardButton.No
        )
        if reply != FocusAwareMessageBox.StandardButton.Yes:
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return

        updated_m = 0; failed_m = []
        progress_m = FocusAwareProgressDialog("Merging studies...", "Cancel", 0, len(files_to_update), self)
        progress_m.setWindowTitle("Merging Studies"); progress_m.setMinimumDuration(0); progress_m.setValue(0)
        for idx_m, fp_m in enumerate(files_to_update):
            progress_m.setValue(idx_m)
            if progress_m.wasCanceled(): break
            QApplication.processEvents()
            try:
                ds_m = pydicom.dcmread(fp_m)
                ds_m.StudyInstanceUID = primary_study_uid
                ds_m.StudyDescription = primary_study_desc
                ds_m.StudyID = primary_study_id
                ds_m.save_as(fp_m)
                updated_m += 1
            except Exception as e_m_file:
                failed_m.append(f"{os.path.basename(fp_m)}: {e_m_file}")
        progress_m.setValue(len(files_to_update))
        
        # Update self.loaded_files: StudyID/Description changed, but filepath is the same.
        # The tree refresh will pick up new study grouping.

        msg_m = f"Merged study data.\nFiles updated: {updated_m}\nFailed: {len(failed_m)}"
        if failed_m: msg_m += "\n\nDetails (first few):\n" + "\n".join(failed_m[:3])
        FocusAwareMessageBox.information(self, "Merge Studies Complete", msg_m)

        # Refresh the tree (corrected - don't call clear_loaded_files)
        all_known_files_after_merge = [f_info[0] for f_info in self.loaded_files if os.path.exists(f_info[0])]
        if all_known_files_after_merge:
            self._load_dicom_files_from_list(all_known_files_after_merge, "data after merge")

        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        logging.info(f"Study merge completed. Updated {updated_m} files.")

    # --- NEW: Series Merging ---
    def merge_series(self):
        """Merge multiple series under the same study into a single series"""
        logging.info("Series merge initiated")
        
        # Enable multi-selection temporarily
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.MultiSelection)
        selected = self.tree.selectedItems()
        series_nodes = [item for item in selected if item.depth() == 2]
        
        # Validate selection
        if len(series_nodes) < 2:
            FocusAwareMessageBox.warning(self, "Merge Series", "Select at least two series nodes to merge.\nHold Ctrl or Shift to select multiple series.")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return
        
        if not self._are_series_under_same_study(series_nodes):
            FocusAwareMessageBox.warning(self, "Merge Series", "All selected series must belong to the same study.")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return
        
        # Show primary selection dialog
        primary_dialog = PrimarySelectionDialog(self, series_nodes, "Series")
        if primary_dialog.exec() != QDialog.DialogCode.Accepted:
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return
        
        primary_index = primary_dialog.get_selected_index()
        primary_series_node = series_nodes[primary_index]
        
        # Get primary series metadata
        primary_series_files = self._collect_instance_filepaths(primary_series_node)
        if not primary_series_files:
            FocusAwareMessageBox.warning(self, "Merge Series", "Could not find any files in the primary series.")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return
        
        try:
            ds_primary = pydicom.dcmread(primary_series_files[0], stop_before_pixels=True)
            primary_series_uid = str(ds_primary.SeriesInstanceUID)
            primary_series_desc = str(getattr(ds_primary, "SeriesDescription", ""))
            primary_series_number = str(getattr(ds_primary, "SeriesNumber", ""))
            primary_modality = str(getattr(ds_primary, "Modality", ""))
        except Exception as e:
            FocusAwareMessageBox.critical(self, "Merge Series", f"Failed to read primary series metadata: {e}")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return
        
        # Collect files from secondary series and check for modality conflicts
        files_to_update = []
        secondary_series = [node for node in series_nodes if node is not primary_series_node]
        modality_conflicts = []
        
        for series_node in secondary_series:
            series_files = self._collect_instance_filepaths(series_node)
            if series_files:
                try:
                    ds_check = pydicom.dcmread(series_files[0], stop_before_pixels=True)
                    secondary_modality = str(getattr(ds_check, "Modality", ""))
                    if secondary_modality and primary_modality and secondary_modality != primary_modality:
                        modality_conflicts.append(f"{secondary_modality} → {primary_modality}")
                except:
                    pass  # Continue even if we can't check modality
                
                files_to_update.extend(series_files)
        
        if not files_to_update:
            FocusAwareMessageBox.information(self, "Merge Series", "No files found in the secondary series to merge.")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return
        
        # Warn about modality conflicts
        warning_msg = ""
        if modality_conflicts:
            warning_msg = f"\nWarning: Modality conflicts detected: {', '.join(set(modality_conflicts))}\n"
        
        # Confirmation dialog
        reply = FocusAwareMessageBox.question(
            self, "Confirm Series Merge",
            f"This will update {len(files_to_update)} files from {len(secondary_series)} series to merge into:\n"
            f"Series UID: {primary_series_uid}\n"
            f"Series Description: {primary_series_desc}\n"
            f"Series Number: {primary_series_number}\n"
            f"Modality: {primary_modality}\n"
            f"{warning_msg}\n"
            "This modifies files in-place. Continue?",
            FocusAwareMessageBox.StandardButton.Yes | FocusAwareMessageBox.StandardButton.No, FocusAwareMessageBox.StandardButton.No
        )
        if reply != FocusAwareMessageBox.StandardButton.Yes:
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return
        
        # Perform the merge
        updated_count = 0
        failed_files = []
        progress = FocusAwareProgressDialog("Merging series...", "Cancel", 0, len(files_to_update), self)
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
                
                # Update series-level tags
                ds.SeriesInstanceUID = primary_series_uid
                if primary_series_desc:
                    ds.SeriesDescription = primary_series_desc
                if primary_series_number:
                    ds.SeriesNumber = primary_series_number
                # Note: We keep the original Modality unless explicitly requested to change it
                
                ds.save_as(filepath)
                updated_count += 1
                
            except Exception as e:
                failed_files.append(f"{os.path.basename(filepath)}: {e}")
                logging.error(f"Failed to merge series for file {filepath}: {e}", exc_info=True)
        
        progress.setValue(len(files_to_update))
        
        # Show results
        msg = f"Series merge complete.\nFiles updated: {updated_count}\nFailed: {len(failed_files)}"
        if failed_files:
            msg += "\n\nDetails (first few):\n" + "\n".join(failed_files[:3])
        FocusAwareMessageBox.information(self, "Merge Series Complete", msg)

        # Refresh the tree (corrected - don't call clear_loaded_files)
        all_known_files_after_merge = [f_info[0] for f_info in self.loaded_files if os.path.exists(f_info[0])]
        if all_known_files_after_merge:
            self._load_dicom_files_from_list(all_known_files_after_merge, "data after series merge")

        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        logging.info(f"Series merge completed. Updated {updated_count} files.")

    def delete_selected_items(self): # User's original
        selected = self.tree.selectedItems()
        if not selected:
            FocusAwareMessageBox.warning(self, "Delete", "Please select one or more items to delete.")
            return

        files_to_delete = set() # Use a set to avoid duplicates
        # Summary for confirmation dialog
        item_counts = {"Patient": 0, "Study": 0, "Series": 0, "Instance": 0}
        
        for item in selected:
            depth = item.depth()
            if depth == 0: item_counts["Patient"] +=1
            elif depth == 1: item_counts["Study"] +=1
            elif depth == 2: item_counts["Series"] +=1
            elif item.data(0, Qt.ItemDataRole.UserRole): item_counts["Instance"] +=1 # Is an instance
            
            files_to_delete.update(self._collect_instance_filepaths(item))

        if not files_to_delete:
            FocusAwareMessageBox.warning(self, "Delete", "No actual files found corresponding to selected items.")
            return

        summary_str = ", ".join([f"{v} {k}(s)" for k,v in item_counts.items() if v > 0])
        confirm_msg = (f"You are about to delete: {summary_str}.\n"
                       f"This will permanently delete {len(files_to_delete)} file(s) from disk.\n"
                       "THIS CANNOT BE UNDONE. Are you sure?")
        
        reply = FocusAwareMessageBox.question(self, "Confirm Delete", confirm_msg,
                                     FocusAwareMessageBox.StandardButton.Yes | FocusAwareMessageBox.StandardButton.No,
                                     FocusAwareMessageBox.StandardButton.No) # Default to No
        if reply != FocusAwareMessageBox.StandardButton.Yes:
            return

        progress_d = FocusAwareProgressDialog("Deleting files...", "Cancel", 0, len(files_to_delete), self)
        progress_d.setWindowTitle("Deleting"); progress_d.setMinimumDuration(0); progress_d.setValue(0)
        
        deleted_d_count = 0; failed_d_list = []
        # Convert set to list for progress dialog indexing
        files_to_delete_list = list(files_to_delete) 

        for idx_d, fp_d in enumerate(files_to_delete_list):
            progress_d.setValue(idx_d)
            if progress_d.wasCanceled(): break
            QApplication.processEvents()
            try:
                if os.path.exists(fp_d):
                    os.remove(fp_d)
                    # Remove from self.loaded_files tracker
                    self.loaded_files = [(f, temp) for f, temp in self.loaded_files if f != fp_d]
                    deleted_d_count += 1
                else: # File was already gone but listed, still remove from tracker
                    self.loaded_files = [(f, temp) for f, temp in self.loaded_files if f != fp_d]
            except Exception as e_d_file:
                failed_d_list.append(f"{os.path.basename(fp_d)}: {e_d_file}")
        progress_d.setValue(len(files_to_delete_list))

        # Refresh from the updated self.loaded_files
        remaining_files_after_delete = [f_info[0] for f_info in self.loaded_files if os.path.exists(f_info[0])]
        self._load_dicom_files_from_list(remaining_files_after_delete, "data after deletion")
        # Clear other UI elements that might refer to deleted items
        self.tag_table.setRowCount(0); self._all_tag_rows = []
        self.image_label.clear(); self.image_label.setVisible(False)
        self.current_filepath = None; self.current_ds = None

        msg_d = f"Deleted {deleted_d_count} file(s)."
        if failed_d_list: msg_d += "\n\nFailed to delete:\n" + "\n".join(failed_d_list[:3])
        FocusAwareMessageBox.information(self, "Delete Complete", msg_d)

    def validate_dicom_files(self):
        """Run DICOM validation on loaded files"""
        if not self.loaded_files:
            FocusAwareMessageBox.warning(self, "No Files", "No DICOM files loaded for validation.")
            return
        
        # Get list of file paths
        file_paths = [f_info[0] for f_info in self.loaded_files if os.path.exists(f_info[0])]
        
        if not file_paths:
            FocusAwareMessageBox.warning(self, "No Files", "No valid file paths found.")
            return
        
        logging.info(f"Starting validation of {len(file_paths)} files")
        
        # Run validation
        try:
            run_validation(file_paths, self)
        except Exception as e:
            logging.error(f"Validation error: {e}", exc_info=True)
            FocusAwareMessageBox.critical(self, "Validation Error", 
                               f"An error occurred during validation:\n{str(e)}")
    
    def manage_templates(self):
        """Open template management dialog"""
        try:
            template_dialog = TemplateSelectionDialog(self.template_manager, self)
            template_dialog.exec()
        except Exception as e:
            logging.error(f"Template management error: {e}", exc_info=True)
            FocusAwareMessageBox.critical(self, "Template Management Error", 
                            f"An error occurred:\n{str(e)}")
            
    def diagnose_image_performance(self, ds, filepath):
        """Print key tags that affect image loading performance"""
        
        logging.info(f"\n=== PERFORMANCE DIAGNOSIS: {os.path.basename(filepath)} ===")
        
        # Most important: Transfer Syntax (compression method)
        transfer_syntax = getattr(ds.file_meta, 'TransferSyntaxUID', 'Unknown')
        logging.info(f"Transfer Syntax: {transfer_syntax}")
        logging.info(f"  Name: {getattr(transfer_syntax, 'name', 'Unknown')}")
        
        # Image format tags
        logging.info(f"Photometric Interpretation: {getattr(ds, 'PhotometricInterpretation', 'Unknown')}")
        logging.info(f"Samples Per Pixel: {getattr(ds, 'SamplesPerPixel', 'Unknown')}")
        logging.info(f"Bits Allocated: {getattr(ds, 'BitsAllocated', 'Unknown')}")
        logging.info(f"Bits Stored: {getattr(ds, 'BitsStored', 'Unknown')}")
        logging.info(f"Pixel Representation: {getattr(ds, 'PixelRepresentation', 'Unknown')}")
        
        # Image size
        rows = getattr(ds, 'Rows', 'Unknown')
        cols = getattr(ds, 'Columns', 'Unknown') 
        logging.info(f"Image Size: {cols} x {rows}")
        
        # Color/grayscale info
        planar_config = getattr(ds, 'PlanarConfiguration', 'Unknown')
        if planar_config != 'Unknown':
            logging.info(f"Planar Configuration: {planar_config}")
        
        logging.info("=" * 50)

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
        
        for idx, (filepath, _) in enumerate(self.loaded_files):
            if progress.wasCanceled():
                return
                
            progress.setValue(idx)
            progress.setLabelText(f"Analyzing {os.path.basename(filepath)}...")
            QApplication.processEvents()
            
            try:
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
        
        # Prepare results
        analysis_results = {
            'files': file_details,
            'unique_patients': unique_patients,
            'unique_dimensions': list(unique_dimensions),
            'transfer_syntaxes': transfer_syntaxes,
            'large_files': large_files,
            'size_range': size_range
        }
        
        # Show results (dialog moved to separate file)
        FocusAwareMessageBox.information(self, "Analysis Complete", 
                                        f"Analysis completed successfully.\n\n"
                                        f"Total Files: {len(analysis_results['files'])}\n"
                                        f"Unique Patients: {len(analysis_results['unique_patients'])}\n"
                                        f"Unique Dimensions: {len(analysis_results['unique_dimensions'])}\n"
                                        f"Size Range: {analysis_results['size_range']}\n"
                                        f"Large Files (>10MB): {len(analysis_results['large_files'])}")

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
        
        for idx, (filepath, _) in enumerate(self.loaded_files):
            if progress.wasCanceled():
                return
                
            progress.setValue(idx)
            progress.setLabelText(f"Testing {os.path.basename(filepath)}...")
            QApplication.processEvents()
            
            try:
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
        
        performance_results = {
            'files': results,
            'slow_files': slow_files,
            'fastest_file': fastest_file,
            'slowest_file': slowest_file
        }
        
        # Show results (dialog moved to separate file)
        avg_load_time = sum(r['load_time'] for r in performance_results['files']) / len(performance_results['files'])
        avg_total_time = sum(r['total_time'] for r in performance_results['files']) / len(performance_results['files'])
        FocusAwareMessageBox.information(self, "Performance Test Complete", 
                                        f"Performance test completed successfully.\n\n"
                                        f"Files Tested: {len(performance_results['files'])}\n"
                                        f"Average Load Time: {avg_load_time:.3f}s\n"
                                        f"Average Total Time: {avg_total_time:.3f}s\n"
                                        f"Slow Files (>0.5s): {len(performance_results['slow_files'])}\n"
                                        f"Fastest File: {performance_results['fastest_file']['filename']} ({performance_results['fastest_file']['total_time']:.3f}s)\n"
                                        f"Slowest File: {performance_results['slowest_file']['filename']} ({performance_results['slowest_file']['total_time']:.3f}s)")

    def _convert_for_dicom_send(self, filepaths, show_progress=True):
        """Convert compressed images to uncompressed for better DICOM send compatibility"""
        converted_files = []
        temp_files = []  # Track temp files for cleanup
        
        if show_progress:
            progress = FocusAwareProgressDialog("Preparing files for DICOM send...", "Cancel", 0, len(filepaths), self)
            progress.setWindowTitle("Converting Images")
            progress.setMinimumDuration(0)
            progress.setValue(0)
        
        for idx, filepath in enumerate(filepaths):
            if show_progress:
                progress.setValue(idx)
                if progress.wasCanceled():
                    # Cleanup temp files if cancelled
                    for temp_file in temp_files:
                        try:
                            os.remove(temp_file)
                        except:
                            pass
                    return None
                QApplication.processEvents()
            
            try:
                ds = pydicom.dcmread(filepath, stop_before_pixels=True)
                transfer_syntax = str(ds.file_meta.TransferSyntaxUID)
                
                # Check if conversion is needed
                if transfer_syntax in ['1.2.840.10008.1.2.4.90', '1.2.840.10008.1.2.4.91']:  # JPEG2000
                    logging.info(f"Converting compressed file: {os.path.basename(filepath)}")
                    
                    # Read full dataset
                    ds_full = pydicom.dcmread(filepath)
                    
                    # Force decompress pixel data
                    _ = ds_full.pixel_array  # This decompresses the data
                    
                    # Change to uncompressed transfer syntax
                    ds_full.file_meta.TransferSyntaxUID = '1.2.840.10008.1.2'  # Implicit VR Little Endian
                    
                    # Create temp file
                    temp_filepath = filepath + "_temp_uncompressed.dcm"
                    ds_full.save_as(temp_filepath, write_like_original=False)
                    
                    converted_files.append(temp_filepath)
                    temp_files.append(temp_filepath)
                    logging.info(f"Converted {os.path.basename(filepath)} to uncompressed")
                else:
                    # No conversion needed
                    converted_files.append(filepath)
                    
            except Exception as e:
                logging.error(f"Failed to process {filepath}: {e}")
                # Use original file if conversion fails
                converted_files.append(filepath)
        
        if show_progress:
            progress.setValue(len(filepaths))
            progress.close()
        
        return converted_files, temp_files
    
    def _export_dicomdir_zip(self, filepaths):
        """Export files as ZIP with DICOMDIR using DICOM standard structure"""
        
        # DEBUG: Check patient distribution in source files
        logging.info("=== PRE-EXPORT PATIENT ANALYSIS ===")
        patient_debug = {}
        for fp in filepaths:
            try:
                ds = pydicom.dcmread(fp, stop_before_pixels=True)
                pid = str(getattr(ds, 'PatientID', 'UNKNOWN'))
                pname = str(getattr(ds, 'PatientName', 'UNKNOWN'))
                if pid not in patient_debug:
                    patient_debug[pid] = {'name': pname, 'count': 0}
                patient_debug[pid]['count'] += 1
            except:
                pass
        
        for pid, info in patient_debug.items():
            logging.info(f"Source Patient '{pid}' ({info['name']}): {info['count']} files")
        logging.info("=== END PRE-EXPORT ANALYSIS ===")

        # Get output path
        out_zip_path, _ = QFileDialog.getSaveFileName(
            self, "Save DICOMDIR ZIP Archive", 
            self.default_export_dir, "ZIP Archives (*.zip)"
        )
        if not out_zip_path:
            return
        if not out_zip_path.lower().endswith('.zip'):
            out_zip_path += '.zip'

        # Use temporary directory for staging
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                self._create_dicomdir_structure(filepaths, temp_dir, out_zip_path)
                
            except Exception as e:
                logging.error(f"DICOMDIR ZIP export failed: {e}", exc_info=True)
                FocusAwareMessageBox.critical(self, "Export Error", f"Failed to create DICOMDIR ZIP: {e}")

    def _create_dicomdir_structure(self, filepaths, temp_dir, output_zip):
        """Create DICOM standard structure with DICOMDIR"""
        
        progress = FocusAwareProgressDialog("Creating DICOMDIR ZIP...", "Cancel", 0, 100, self)
        progress.setWindowTitle("DICOMDIR Export")
        progress.setMinimumDuration(0)
        progress.setValue(0)
        
        try:
            # Step 1: Analyze files and generate paths (20%)
            progress.setValue(10)
            progress.setLabelText("Analyzing DICOM files...")
            QApplication.processEvents()
            
            if progress.wasCanceled():
                return
            
            path_generator = DicomPathGenerator()
            file_mapping = path_generator.generate_paths(filepaths)
            
            if not file_mapping:
                raise Exception("No valid DICOM files found for export")
            
            # Step 2: Copy files to structured layout (60%)
            progress.setValue(20)
            progress.setLabelText("Creating directory structure...")
            QApplication.processEvents()
            
            copied_mapping = self._copy_files_to_dicom_structure(filepaths, file_mapping, temp_dir, progress)
            
            if progress.wasCanceled():
                return
            
            # Step 3: Generate DICOMDIR (80%)
            progress.setValue(80)
            progress.setLabelText("Generating DICOMDIR...")
            QApplication.processEvents()
            
            builder = DicomdirBuilder(self.config.get("ae_title", "DICOM_EXPORT"))
            builder.add_dicom_files(copied_mapping)
            dicomdir_path = os.path.join(temp_dir, "DICOMDIR")
            builder.generate_dicomdir(dicomdir_path)
            
            # Validate the DICOMDIR
            if not self._validate_dicomdir(dicomdir_path):
                raise Exception("Generated DICOMDIR failed validation")
            
            if progress.wasCanceled():
                return
            
            # Step 4: Create ZIP (100%)
            progress.setValue(90)
            progress.setLabelText("Creating ZIP archive...")
            QApplication.processEvents()
            
            self._create_zip_from_directory(temp_dir, output_zip)
            
            progress.setValue(100)
            
            # Calculate statistics
            total_files = len(file_mapping)
            total_size = sum(os.path.getsize(f) for f in filepaths if os.path.exists(f))
            size_mb = total_size / (1024 * 1024)
            
            FocusAwareMessageBox.information(self, "Export Complete", 
                                f"DICOMDIR ZIP created successfully!\n\n"
                                f"Files: {total_files}\n"
                                f"Size: {size_mb:.1f} MB\n"
                                f"Output: {output_zip}")
            
        finally:
            progress.close()

    def _validate_dicomdir(self, dicomdir_path):
        """Validate the generated DICOMDIR file"""
        try:
            logging.info(f"Validating DICOMDIR: {dicomdir_path}")
            
            # Try to read the DICOMDIR
            ds = pydicom.dcmread(dicomdir_path)
            
            # Check required elements
            required_elements = [
                'FileSetID', 'FileSetDescriptorFileID', 'SpecificCharacterSet',
                'FileSetConsistencyFlag', 'DirectoryRecordSequence'
            ]
            
            missing_elements = []
            for element in required_elements:
                if not hasattr(ds, element):
                    missing_elements.append(element)
            
            if missing_elements:
                logging.error(f"DICOMDIR missing required elements: {missing_elements}")
                return False
            
            # Check directory records
            if not ds.DirectoryRecordSequence:
                logging.error("DICOMDIR has no directory records")
                return False
            
            record_types = {}
            for record in ds.DirectoryRecordSequence:
                record_type = getattr(record, 'DirectoryRecordType', 'UNKNOWN')
                record_types[record_type] = record_types.get(record_type, 0) + 1
            
            logging.info(f"DICOMDIR validation passed. Records: {record_types}")
            return True
            
        except Exception as e:
            logging.error(f"DICOMDIR validation failed: {e}")
            return False

    def _copy_files_to_dicom_structure(self, filepaths, file_mapping, temp_dir, progress):
        """Copy files according to DICOM standard structure"""
        
        copied_mapping = {}  # original_path -> copied_path
        total_files = len(filepaths)
        
        for idx, original_path in enumerate(filepaths):
            if progress.wasCanceled():
                break
                
            # Get DICOM standard path
            if original_path not in file_mapping:
                logging.warning(f"No mapping found for {original_path}, skipping")
                continue
                
            dicom_path = file_mapping[original_path]
            full_target_path = os.path.join(temp_dir, dicom_path)
            
            try:
                # Create directory structure
                os.makedirs(os.path.dirname(full_target_path), exist_ok=True)
                
                # Copy file
                shutil.copy2(original_path, full_target_path)
                copied_mapping[original_path] = full_target_path
                
                # Verify the copied file is readable
                try:
                    test_ds = pydicom.dcmread(full_target_path, stop_before_pixels=True)
                    logging.debug(f"Successfully copied and verified: {os.path.basename(full_target_path)}")
                except Exception as e:
                    logging.warning(f"Copied file may be corrupted: {full_target_path}: {e}")
                
            except Exception as e:
                logging.error(f"Failed to copy {original_path} to {full_target_path}: {e}")
                continue
            
            # Update progress (20% to 80% range)
            file_progress = 20 + int((idx + 1) / total_files * 60)
            progress.setValue(file_progress)
            progress.setLabelText(f"Copying files... ({idx + 1}/{total_files})")
            QApplication.processEvents()
        
        logging.info(f"Copied {len(copied_mapping)} files to DICOM structure")
        return copied_mapping

    def _create_zip_from_directory(self, source_dir, output_zip):
        """Create ZIP file from directory contents"""
        
        with zipfile.ZipFile(output_zip, 'w', compression=zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(source_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, source_dir)
                    zipf.write(file_path, arcname)
        
        logging.info(f"Created ZIP archive: {output_zip}")
    
    def _on_tag_item_changed(self, item):
        """Called when a tag table item is edited - only track actual changes"""
        # Only track changes in the "New Value" column (column 3)
        if item.column() == 3:
            row = item.row()
            new_value = item.text().strip()
            
            # Get the original value from the "Value" column (column 2)
            current_value_item = self.tag_table.item(row, 2)
            original_value = current_value_item.text() if current_value_item else ""
            
            # Only flag as changed if there's actually a difference AND new value is not empty
            if new_value and new_value != original_value:
                self.has_unsaved_tag_changes = True
                logging.debug(f"Detected unsaved change in row {row}: '{original_value}' -> '{new_value}'")
            else:
                # Value was cleared or changed back to original, check if any other changes exist
                self._check_for_remaining_changes()

    def _check_for_remaining_changes(self):
        """Check if any unsaved changes remain in the tag table"""
        has_changes = False
        
        for row in range(self.tag_table.rowCount()):
            new_value_item = self.tag_table.item(row, 3)
            current_value_item = self.tag_table.item(row, 2)
            
            if new_value_item and current_value_item:
                new_value = new_value_item.text().strip()
                current_value = current_value_item.text()
                
                # Has changes if new value exists and is different from current
                if new_value and new_value != current_value:
                    has_changes = True
                    break
        
        self.has_unsaved_tag_changes = has_changes
        logging.debug(f"Remaining changes check: {has_changes}")

    def _clear_unsaved_changes(self):
        """Clear the unsaved changes flag"""
        self.has_unsaved_tag_changes = False
        logging.debug("Cleared unsaved changes flag")

    def _prompt_for_unsaved_changes(self):
        """Prompt user about unsaved changes - simplified to keep/discard only"""
        current_filename = os.path.basename(self.current_filepath) if self.current_filepath else "current file"
        
        msg = (f"You have unsaved tag changes in '{current_filename}'.\n\n"
            "These changes will be lost if you navigate away.\n\n"
            "What would you like to do?")
        
        msgbox = FocusAwareMessageBox(
            FocusAwareMessageBox.Icon.Warning,
            "Unsaved Changes", 
            msg,
            FocusAwareMessageBox.StandardButton.NoButton,
            self
        )
        
        keep_editing_btn = msgbox.addButton("Keep Editing", FocusAwareMessageBox.ButtonRole.RejectRole)
        discard_btn = msgbox.addButton("Discard Changes", FocusAwareMessageBox.ButtonRole.DestructiveRole)
        
        msgbox.setDefaultButton(keep_editing_btn)
        msgbox.exec()
        
        clicked_button = msgbox.clickedButton()
        
        if clicked_button == discard_btn:
            return "discard"
        else:  # keep_editing_btn or closed dialog
            return "keep_editing"
        
    def _revert_tree_selection_to_current_file(self):
        """Revert tree selection back to the currently displayed file"""
        if not self.current_filepath:
            return
        
        # Set flag to prevent recursion
        self.reverting_selection = True
        
        try:
            # Find the tree item that corresponds to current_filepath
            current_item = self._find_tree_item_by_filepath(self.current_filepath)
            
            if current_item:
                # Clear current selection
                self.tree.clearSelection()
                
                # Select the current item
                current_item.setSelected(True)
                
                # Ensure the item is visible (expand parents if needed)
                self._ensure_item_visible(current_item)
                
                logging.debug(f"Reverted tree selection to current file: {os.path.basename(self.current_filepath)}")
            else:
                logging.warning(f"Could not find tree item for current file: {self.current_filepath}")
        
        finally:
            # Clear the flag
            self.reverting_selection = False
    
    def _find_tree_item_by_filepath(self, filepath):
        """Find a tree item by its stored filepath"""
        def search_item(item):
            # Check if this item has the filepath we're looking for
            item_filepath = item.data(0, Qt.ItemDataRole.UserRole)
            if item_filepath == filepath:
                return item
            
            # Search children
            for i in range(item.childCount()):
                found = search_item(item.child(i))
                if found:
                    return found
            return None
        
        # Search all top-level items (patients)
        for i in range(self.tree.topLevelItemCount()):
            found = search_item(self.tree.topLevelItem(i))
            if found:
                return found
        
        return None

    def _ensure_item_visible(self, item):
        """Ensure a tree item is visible by expanding its parents"""
        # Expand all parent items
        parent = item.parent()
        while parent:
            parent.setExpanded(True)
            parent = parent.parent()
        
        # Scroll to make the item visible
        self.tree.scrollToItem(item)

    def _get_open_filename(self, caption, directory="", filter="", initial_filter=""):
        """Get filename to open using configured file picker"""
        dialog = QFileDialog(self, caption, directory, filter)
        
        # Configure based on user preference
        if not self.config.get("file_picker_native", False):
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        
        if initial_filter:
            dialog.selectNameFilter(initial_filter)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            files = dialog.selectedFiles()
            if files:
                return files[0], dialog.selectedNameFilter()
        
        return "", ""

    def _get_save_filename(self, caption, directory="", filter="", initial_filter=""):
        """Get filename to save using configured file picker"""
        dialog = QFileDialog(self, caption, directory, filter)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        
        # Configure based on user preference
        if not self.config.get("file_picker_native", False):
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        
        if initial_filter:
            dialog.selectNameFilter(initial_filter)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            files = dialog.selectedFiles()
            if files:
                return files[0], dialog.selectedNameFilter()
        
        return "", ""

    def _get_existing_directory(self, caption, directory=""):
        """Get existing directory using configured file picker"""
        dialog = QFileDialog(self, caption, directory)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        
        # Configure based on user preference
        if not self.config.get("file_picker_native", False):
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            dirs = dialog.selectedFiles()
            if dirs:
                return dirs[0]
        
        return ""
    
    def show_log_viewer(self):
        """Show the live log viewer dialog"""
        log_path = self.config.get("log_path")
        
        if not log_path:
            FocusAwareMessageBox.warning(
                self, "No Log File", 
                "No log file path configured.\n\nCheck your configuration file."
            )
            return
        
        if not os.path.exists(log_path):
            # Try to create the log directory and file if it doesn't exist
            try:
                os.makedirs(os.path.dirname(log_path), exist_ok=True)
                # Touch the log file
                with open(log_path, 'a'):
                    pass
            except Exception as e:
                FocusAwareMessageBox.critical(
                    self, "Log File Error", 
                    f"Cannot access log file:\n{log_path}\n\nError: {e}"
                )
                return
        
        # Check if log viewer is already open
        if hasattr(self, 'log_viewer') and self.log_viewer and self.log_viewer.isVisible():
            # Bring existing viewer to front
            self.log_viewer.raise_()
            self.log_viewer.activateWindow()
            return
        
        # Create new log viewer
        try:
            self.log_viewer = LogViewerDialog(log_path, self)
            self.log_viewer.show()
            logging.info(f"Opened log viewer for: {log_path}")
        except Exception as e:
            FocusAwareMessageBox.critical(
                self, "Log Viewer Error", 
                f"Failed to open log viewer:\n{str(e)}"
            )
            logging.error(f"Failed to open log viewer: {e}")
    
    def open_settings_editor(self):
        """Open the YAML settings editor dialog"""
        try:
            # Determine the config file path (same logic as load_config)
            system = platform.system()
            app_name = "fm-dicom"
            
            if system == "Windows":
                appdata = os.environ.get("APPDATA")
                base_dir = appdata if appdata else os.path.dirname(sys.executable)
                config_file_path = os.path.join(base_dir, app_name, "config.yml")
            elif system == "Darwin":
                config_file_path = os.path.expanduser(f"~/Library/Application Support/{app_name}/config.yml")
            else:  # Linux/Unix
                xdg_config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
                config_file_path = os.path.join(xdg_config_home, app_name, "config.yml")
            
            # Open the settings editor
            dialog = SettingsEditorDialog(self.config, config_file_path, self)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                # Settings were saved, apply the new configuration
                if hasattr(dialog, 'new_config'):
                    self._apply_new_config(dialog.new_config)
            
        except Exception as e:
            logging.error(f"Failed to open settings editor: {e}")
            FocusAwareMessageBox.critical(
                self, "Settings Error",
                f"Failed to open settings editor:\n\n{str(e)}"
            )

    def _apply_new_config(self, new_config):
        """Apply new configuration settings"""
        try:
            # Update the current config
            old_config = self.config.copy()
            self.config = new_config
            
            # Apply changes that can be applied immediately
            changes_applied = []
            
            # Update export directories
            if 'default_export_dir' in new_config:
                self.default_export_dir = os.path.expanduser(str(new_config['default_export_dir']))
                changes_applied.append("Export directory")
            
            if 'default_import_dir' in new_config:
                self.default_import_dir = os.path.expanduser(str(new_config['default_import_dir']))
                changes_applied.append("Import directory")
            
            # Update image preview setting
            if 'show_image_preview' in new_config:
                preview_enabled = bool(new_config['show_image_preview'])
                self.preview_toggle.setChecked(preview_enabled)
                changes_applied.append("Image preview setting")
            
            # Update theme if changed
            if 'theme' in new_config and new_config['theme'] != old_config.get('theme'):
                if new_config['theme'].lower() == 'dark':
                    set_dark_palette(QApplication.instance())
                else:
                    set_light_palette(QApplication.instance())
                changes_applied.append("Theme")
            
            # Update DICOM send config
            self.dicom_send_config = self.config
            changes_applied.append("DICOM send settings")
            
            # Show what was applied
            if changes_applied:
                FocusAwareMessageBox.information(
                    self, "Settings Applied",
                    f"Applied changes to:\n\n• " + "\n• ".join(changes_applied) + 
                    "\n\nNote: Some changes (like logging settings) require restarting the application."
                )
            
            logging.info("Configuration updated successfully")
            
        except Exception as e:
            logging.error(f"Failed to apply new configuration: {e}")
            FocusAwareMessageBox.warning(
                self, "Configuration Warning",
                f"Settings were saved but some changes could not be applied:\n\n{str(e)}\n\n"
                "You may need to restart the application."
            )

# --- Main Execution ---
if __name__ == "__main__":
    # Configure basic console logging before QApplication for early messages from load_config
    # This will be overridden by setup_logging later if a file path is available
    logging.basicConfig(level=logging.INFO, 
                        format="%(asctime)s [%(levelname)-7.7s] %(message)s",
                        handlers=[logging.StreamHandler(sys.stderr)])

    app = QApplication(sys.argv)

    start_path_arg = None
    config_path_override_arg = None # Use a distinct name from MainWindow's param
    
    idx = 1
    while idx < len(sys.argv):
        arg = sys.argv[idx]
        if arg.startswith("--config="):
            config_path_override_arg = arg.split("=", 1)[1]
        elif arg == "--config" and idx + 1 < len(sys.argv):
            config_path_override_arg = sys.argv[idx+1]
            idx +=1 
        elif start_path_arg is None and (os.path.exists(os.path.expanduser(arg)) or arg.lower().endswith(".zip")):
            start_path_arg = os.path.expanduser(arg)
        else:
            logging.warning(f"Unrecognized command line argument: {arg}")
        idx += 1

    main_window = MainWindow(start_path=start_path_arg, config_path_override=config_path_override_arg)
    main_window.show()
    sys.exit(app.exec())