from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem, QMessageBox, QLineEdit, QInputDialog, QComboBox, QLabel, QCheckBox, QSizePolicy, QSplitter,
    QDialog, QFormLayout, QDialogButtonBox, QProgressDialog,
    QApplication, QToolBar, QGroupBox, QFrame, QStatusBar, QStyle, QMenu,
    QGridLayout
)
from PyQt6.QtGui import QPixmap, QImage, QIcon, QPalette, QColor, QFont, QAction
from PyQt6.QtCore import QDir, Qt, QPoint, QSize
import pydicom
import zipfile
import tempfile
import os
import shutil
import numpy as np
import sys
import yaml # Ensure this is here
from pydicom.dataelem import DataElement
from pydicom.uid import generate_uid
import datetime
import logging
import platform # Ensure this is here

# Add import for pynetdicom
try:
    from pynetdicom import AE, AllStoragePresentationContexts
    from pynetdicom.sop_class import Verification
    VERIFICATION_SOP_CLASS = Verification
    STORAGE_CONTEXTS = AllStoragePresentationContexts
except Exception as e:
    print(f"PYNETDICOM IMPORT ERROR: {e}", file=sys.stderr)
    AE = None
    STORAGE_CONTEXTS = []
    VERIFICATION_SOP_CLASS = None

# Add depth method to QTreeWidgetItem
def depth(self):
    """Return the depth of the item in the tree."""
    depth_val = 0 # Renamed to avoid conflict if self is reused
    parent_item = self.parent() # Use a different variable name
    while parent_item:
        depth_val += 1
        parent_item = parent_item.parent()
    return depth_val

QTreeWidgetItem.depth = depth

# --- Theme Handling ---
def set_light_palette(app):
    # Revert to a standard palette or define your own light theme
    app.setPalette(QApplication.style().standardPalette())
    # If you have a specific light theme, apply it here.
    # For example:
    # palette = QPalette()
    # palette.setColor(QPalette.ColorRole.Window, QColor(240, 240, 240))
    # ... other light theme colors ...
    # app.setPalette(palette)
    logging.info("Applied light theme.")


def set_dark_palette(app): # User's original dark palette
    palette = QPalette()
    background = QColor(32, 34, 37)
    palette.setColor(QPalette.ColorRole.Window, background)
    palette.setColor(QPalette.ColorRole.Base, background)
    palette.setColor(QPalette.ColorRole.AlternateBase, background)
    palette.setColor(QPalette.ColorRole.Button, background)
    palette.setColor(QPalette.ColorRole.ToolTipBase, background)
    light_text = QColor(245, 245, 245)
    palette.setColor(QPalette.ColorRole.WindowText, light_text)
    palette.setColor(QPalette.ColorRole.Text, light_text)
    palette.setColor(QPalette.ColorRole.ButtonText, light_text)
    palette.setColor(QPalette.ColorRole.ToolTipText, light_text)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(80, 140, 255))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 85, 85))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(100, 100, 100))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(100, 100, 100))
    app.setPalette(palette)
    logging.info("Applied dark theme.")

# --- Configuration and Logging Setup (NEW/REFINED) ---

def get_default_user_dir():
    # QDir is imported from PyQt6.QtCore at the top of the file
    return str(QDir.homePath())

def ensure_dir_exists(file_path):
    if not file_path:
        # Logging might not be set up when this is first called by load_config for default log path
        print(f"Warning (ensure_dir_exists): Called with empty file_path.", file=sys.stderr)
        return False
    try:
        dir_name = os.path.dirname(file_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
            return True
    except Exception as e:
        print(f"Warning (ensure_dir_exists): Could not create directory for {file_path}: {e}", file=sys.stderr)
    return False

def load_config(config_path_override=None):
    system = platform.system()
    app_name = "fm-dicom"

    # Determine platform-specific default paths
    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        base_dir = appdata if appdata else os.path.dirname(sys.executable) # Use exe dir if APPDATA not found (portable case)
        preferred_config_path = os.path.join(base_dir, app_name, "config.yml")
        
        log_base = os.environ.get("LOCALAPPDATA", appdata if appdata else get_default_user_dir()) # Prefer LOCALAPPDATA for logs
        default_log_path = os.path.join(log_base, app_name, "logs", f"{app_name}.log")
    elif system == "Darwin": # macOS
        preferred_config_path = os.path.expanduser(f"~/Library/Application Support/{app_name}/config.yml")
        default_log_path = os.path.expanduser(f"~/Library/Logs/{app_name}/{app_name}.log")
    else:  # Linux/Unix like systems
        xdg_config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        preferred_config_path = os.path.join(xdg_config_home, app_name, "config.yml")
        
        xdg_state_home = os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state"))
        default_log_path = os.path.join(xdg_state_home, app_name, "logs", f"{app_name}.log")

    default_user_home_dir = get_default_user_dir()
    default_config_data = {
        "log_path": default_log_path,
        "log_level": "INFO",
        "show_image_preview": False,
        "ae_title": "DCMSCU",
        "destinations": [],
        "window_size": [1200, 800],
        "default_export_dir": os.path.join(default_user_home_dir, "DICOM_Exports"), # Default subfolder
        "default_import_dir": os.path.join(default_user_home_dir, "Downloads"), # Default to Downloads
        "anonymization": {},
        "recent_paths": [],
        "theme": "dark", # Default theme
        "language": "en"
    }

    paths_to_check = []
    if config_path_override:
        paths_to_check.append(os.path.expanduser(config_path_override))
    
    paths_to_check.append(preferred_config_path)
    if system == "Windows": # Fallback for portable mode (config.yml next to exe)
        paths_to_check.append(os.path.join(os.path.dirname(sys.executable), "config.yml"))
    # paths_to_check.append(os.path.join(os.path.dirname(__file__), "config.yml")) # For a bundled default (read-only)

    loaded_user_config = None
    # loaded_config_source_path = None # To know which file was loaded
    for path_to_try in paths_to_check:
        if path_to_try and os.path.exists(path_to_try):
            try:
                with open(path_to_try, "r", encoding="utf-8") as f:
                    content = f.read()
                    if not content.strip(): # Handle truly empty file
                        loaded_user_config = {}
                    else:
                        loaded_user_config = yaml.safe_load(content)
                        if loaded_user_config is None: # If file had only comments or invalid YAML resulting in None
                            loaded_user_config = {}
                # Use print here as logging might not be set up yet
                print(f"INFO (load_config): Loaded configuration from {path_to_try}", file=sys.stderr)
                # loaded_config_source_path = path_to_try
                break 
            except Exception as e:
                print(f"Warning (load_config): Could not load/parse config from {path_to_try}: {e}", file=sys.stderr)
                loaded_user_config = None # Ensure reset

    final_config = default_config_data.copy()
    if loaded_user_config is not None:
        final_config.update(loaded_user_config) # User settings override defaults

    path_keys = ["log_path", "default_export_dir", "default_import_dir"]
    for key in path_keys:
        if key in final_config and final_config[key] is not None:
            final_config[key] = os.path.expanduser(str(final_config[key]))
        elif key not in final_config: # Key missing entirely
             final_config[key] = default_config_data.get(key) # Fallback to default's default
             print(f"Warning (load_config): Path key '{key}' missing, using default: {final_config[key]}", file=sys.stderr)
        elif final_config[key] is None and key in default_config_data: # Key present but explicitly null
            final_config[key] = default_config_data[key] # Revert to default
            print(f"Info (load_config): Path key '{key}' was null, reverted to default: {final_config[key]}", file=sys.stderr)

    if loaded_user_config is None: # No config file found or loaded successfully
        print(f"INFO (load_config): No existing config found. Creating default at: {preferred_config_path}", file=sys.stderr)
        if ensure_dir_exists(preferred_config_path): # Ensure config directory exists
            try:
                with open(preferred_config_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(final_config, f, sort_keys=False, allow_unicode=True)
                if final_config.get("log_path"): # Ensure default log directory exists
                    ensure_dir_exists(final_config["log_path"])
            except Exception as e:
                print(f"ERROR (load_config): Could not create default config at {preferred_config_path}: {e}", file=sys.stderr)
        else:
            print(f"ERROR (load_config): Could not create dir for default config: {os.path.dirname(preferred_config_path)}. Using in-memory defaults.", file=sys.stderr)
    
    return final_config

def setup_logging(log_path_from_config, log_level_str_from_config): # Renamed params for clarity
    log_level_str = str(log_level_str_from_config).upper()
    log_level = getattr(logging, log_level_str, logging.INFO) # Default to INFO if invalid
    
    logger = logging.getLogger() # Get root logger
    logger.setLevel(log_level)

    if logger.hasHandlers(): # Clear any existing handlers from previous runs or calls
        logger.handlers.clear()

    # Always add StreamHandler for console output
    stream_handler = logging.StreamHandler(sys.stderr)
    # Simple format for console, can be more detailed if needed
    stream_formatter = logging.Formatter("%(asctime)s [%(levelname)-7.7s] %(message)s") 
    stream_handler.setFormatter(stream_formatter)
    logger.addHandler(stream_handler)

    if not log_path_from_config:
        # Logging is already set up with StreamHandler, so use it.
        logging.error("Log path not configured. File logging disabled. Logging to stderr only.")
        return

    # Ensure the log directory exists (critical step before attempting FileHandler)
    if not ensure_dir_exists(log_path_from_config):
        logging.error(f"Could not create log directory for {log_path_from_config}. File logging disabled. Logging to stderr only.")
        return

    # Proceed with FileHandler
    try:
        # mode="w" truncates log on each run. Use mode="a" to append.
        file_handler = logging.FileHandler(log_path_from_config, mode="w", encoding="utf-8")
        # More detailed format for file logs
        file_formatter = logging.Formatter("%(asctime)s [%(levelname)-5.5s] %(name)s (%(module)s.%(funcName)s:%(lineno)d): %(message)s")
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        # Initial log message to confirm file logging is active
        logging.info(f"File logging initialized. Level: {log_level_str}. Output to: {log_path_from_config}")
    except Exception as e:
        # If FileHandler fails, logging will still go to StreamHandler
        logging.error(f"Could not set up file logger at {log_path_from_config}: {e}. Logging to stderr only.")


# --- Main Application Classes (User's Original Structure) ---

class DicomSendDialog(QDialog): # User's original DicomSendDialog
    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.setWindowTitle("DICOM Send")
        layout = QFormLayout(self)

        self.destinations = config.get("destinations", []) if config else []
        self.dest_combo = QComboBox()
        self.dest_combo.addItem("Manual Entry")
        for dest in self.destinations:
            label = dest.get("label") or f"{dest.get('ae_title','')}@{dest.get('host','')}:{dest.get('port','')}"
            self.dest_combo.addItem(label)
        self.dest_combo.currentIndexChanged.connect(self._on_dest_changed)
        layout.addRow("Destination:", self.dest_combo)

        default_ae = config.get("ae_title", "DCMSCU") if config else "DCMSCU"
        self.ae_title = QLineEdit(default_ae)
        self.ae_title.setToolTip(
            "Calling AE Title: This is the Application Entity Title your system presents to the remote DICOM server. "
            "It identifies your workstation or application to the remote PACS. "
            "If unsure, use a unique name or the default."
        )
        self.remote_ae = QLineEdit("DCMRCVR")
        self.host = QLineEdit("127.0.0.1")
        self.port = QLineEdit("104")
        layout.addRow("Calling AE Title:", self.ae_title)
        layout.addRow("Remote AE Title:", self.remote_ae)
        layout.addRow("Remote Host:", self.host)
        layout.addRow("Remote Port:", self.port)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        # Initialize fields based on current selection if destinations exist
        if self.destinations:
            self._on_dest_changed(self.dest_combo.currentIndex())


    def _on_dest_changed(self, idx):
        config_ae_default = "DCMSCU" # Fallback if not in config
        if hasattr(self, 'parentWidget') and hasattr(self.parentWidget(), 'config'): # Access main window config
             config_ae_default = self.parentWidget().config.get("ae_title", "DCMSCU")

        if idx == 0 or not self.destinations: # Manual entry selected or no destinations defined
            # Set to defaults or clear for manual entry
            self.remote_ae.setText("DCMRCVR") # Or some other default
            self.host.setText("127.0.0.1")
            self.port.setText("104")
            self.ae_title.setText(config_ae_default) # Use global default calling AE
            return
        
        # idx-1 because "Manual Entry" is at index 0
        dest = self.destinations[idx-1] 
        self.remote_ae.setText(str(dest.get("ae_title", "DCMRCVR")))
        self.host.setText(str(dest.get("host", "127.0.0.1")))
        self.port.setText(str(dest.get("port", "104")))
        # Use destination-specific calling AE if provided, else global default
        self.ae_title.setText(str(dest.get("calling_ae_title", config_ae_default)))


    def get_params(self):
        try:
            port_val = int(self.port.text().strip())
            if not (0 < port_val < 65536):
                raise ValueError("Port out of range")
        except ValueError:
            QMessageBox.critical(self, "Invalid Port", "Port must be a number between 1 and 65535.")
            return None # Indicate error
        
        return (
            self.ae_title.text().strip(),
            self.remote_ae.text().strip(),
            self.host.text().strip(),
            port_val # Already int
        )

class MainWindow(QMainWindow):
    def __init__(self, start_path=None, config_path_override=None): # Renamed arg
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
            self.default_import_dir = os.path.join(get_default_user_dir(), "Downloads")
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

        act_save = QAction(save_icon, "Save As", self) # User's toolbar save
        act_save.triggered.connect(self.save_as)
        toolbar.addAction(act_save)

        act_delete = QAction(delete_icon, "Delete", self)
        act_delete.triggered.connect(self.delete_selected_items)
        toolbar.addAction(act_delete)

        act_merge = QAction(merge_icon, "Merge Patients", self)
        act_merge.triggered.connect(self.merge_patients)
        toolbar.addAction(act_merge)

        act_expand = QAction(expand_icon, "Expand All", self)
        act_expand.triggered.connect(self.tree_expand_all)
        toolbar.addAction(act_expand)

        act_collapse = QAction(collapse_icon, "Collapse All", self)
        act_collapse.triggered.connect(self.tree_collapse_all)
        toolbar.addAction(act_collapse)
        toolbar.addSeparator() # User had this

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
        self.search_bar.textChanged.connect(self.filter_tag_table)
        right_layout.addWidget(self.search_bar)

        self.tag_table = QTableWidget()
        self.tag_table.setColumnCount(4)
        self.tag_table.setHorizontalHeaderLabels(["Tag ID", "Description", "Value", "New Value"])
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

        if start_path:
            self.load_path_on_start(start_path)

        logging.info("MainWindow UI initialized")
        
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
        if self.config: # Ensure config object exists
            self.config["window_size"] = [self.size().width(), self.size().height()]
            self.save_configuration() # Save all pending config changes
        
        self.cleanup_temp_dir() # Clean up any temporary files
        logging.info("Application closing.")
        super().closeEvent(event) # Important to call the superclass method

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

    def load_path_on_start(self, path): # User's original
        path = os.path.expanduser(path)
        if os.path.isfile(path):
            if path.lower().endswith('.zip'):
                self.clear_loaded_files()
                self.temp_dir = tempfile.mkdtemp()
                try:
                    with zipfile.ZipFile(path, 'r') as zip_ref:
                        zip_ref.extractall(self.temp_dir)
                    dcm_files = []
                    all_files = []
                    for root, dirs, files in os.walk(self.temp_dir):
                        for name in files:
                            all_files.append(os.path.join(root, name))
                    progress = QProgressDialog("Scanning ZIP for DICOM files...", "Cancel", 0, len(all_files), self)
                    progress.setWindowTitle("Loading ZIP")
                    progress.setMinimumDuration(0)
                    progress.setValue(0)
                    for idx, f in enumerate(all_files):
                        if progress.wasCanceled():
                            break
                        if f.lower().endswith('.dcm'):
                            dcm_files.append(f)
                        progress.setValue(idx + 1)
                        QApplication.processEvents()
                    progress.close()
                    if not dcm_files:
                        QMessageBox.warning(self, "No DICOM", "No DICOM (.dcm) files found in ZIP archive.")
                        return
                    self.loaded_files = [(f, self.temp_dir) for f in dcm_files]
                    self.populate_tree(dcm_files)
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Error reading ZIP: {e}")
                    self.cleanup_temp_dir()
            elif path.lower().endswith('.dcm'):
                self.clear_loaded_files()
                self.loaded_files = [(path, None)]
                self.populate_tree([path])
            else:
                QMessageBox.warning(self, "Unsupported", "Only .dcm and .zip files are supported.")
        elif os.path.isdir(path):
            self.clear_loaded_files()
            dcm_files = []
            all_files = []
            for root, dirs, files in os.walk(path):
                for name in files:
                    all_files.append(os.path.join(root, name))
            progress = QProgressDialog("Scanning directory for DICOM files...", "Cancel", 0, len(all_files), self)
            progress.setWindowTitle("Loading Directory")
            progress.setMinimumDuration(0)
            progress.setValue(0)
            for idx, f in enumerate(all_files):
                if progress.wasCanceled():
                    break
                if f.lower().endswith('.dcm'):
                    dcm_files.append(f)
                progress.setValue(idx + 1)
                QApplication.processEvents()
            progress.close()
            if not dcm_files:
                QMessageBox.warning(self, "No DICOM", "No DICOM (.dcm) files found in directory.")
                return
            self.loaded_files = [(f, None) for f in dcm_files]
            self.populate_tree(dcm_files)
        else:
            QMessageBox.warning(self, "Not Found", f"Path does not exist: {path}")

    def open_file(self): # User's original
        dialog = QFileDialog(
            self,
            "Open DICOM or ZIP File",
            self.default_import_dir,
            "ZIP Archives (*.zip);;DICOM Files (*.dcm);;All Files (*)"
        )
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        if dialog.exec():
            file_paths = dialog.selectedFiles()
            if file_paths:
                file_path = file_paths[0]
                self.clear_loaded_files()
                if file_path.lower().endswith('.zip'):
                    self.temp_dir = tempfile.mkdtemp()
                    try:
                        with zipfile.ZipFile(file_path, 'r') as zip_ref:
                            zip_ref.extractall(self.temp_dir)
                        dcm_files = []
                        all_files = []
                        for root, dirs, files in os.walk(self.temp_dir):
                            for name in files:
                                all_files.append(os.path.join(root, name))
                        progress = QProgressDialog("Scanning ZIP for DICOM files...", "Cancel", 0, len(all_files), self)
                        progress.setWindowTitle("Loading ZIP")
                        progress.setMinimumDuration(0)
                        progress.setValue(0)
                        for idx, f in enumerate(all_files):
                            if progress.wasCanceled():
                                break
                            if f.lower().endswith('.dcm'):
                                dcm_files.append(f)
                            progress.setValue(idx + 1)
                            QApplication.processEvents()
                        progress.close()
                        if not dcm_files:
                            # User had self.tag_view.setText here, but tag_view isn't defined in their MainWindow snippet.
                            # Using QMessageBox instead for consistency.
                            QMessageBox.warning(self, "No DICOM", "No DICOM (.dcm) files found in ZIP archive.")
                            return
                        self.loaded_files = [(f, self.temp_dir) for f in dcm_files]
                        self.populate_tree(dcm_files)
                    except Exception as e:
                        QMessageBox.critical(self, "ZIP Error", f"Error reading ZIP: {e}")
                        self.cleanup_temp_dir()
                else:
                    self.loaded_files = [(file_path, None)]
                    self.populate_tree([file_path])

    def open_directory(self): # User's original
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Open DICOM Directory",
            self.default_import_dir
        )
        if dir_path:
            self.clear_loaded_files()
            dcm_files = []
            all_files = []
            for root, dirs, files in os.walk(dir_path):
                for name in files:
                    all_files.append(os.path.join(root, name))
            progress = QProgressDialog("Scanning directory for DICOM files...", "Cancel", 0, len(all_files), self)
            progress.setWindowTitle("Loading Directory")
            progress.setMinimumDuration(0)
            progress.setValue(0)
            for idx, f in enumerate(all_files):
                if progress.wasCanceled():
                    break
                if f.lower().endswith('.dcm'):
                    dcm_files.append(f)
                progress.setValue(idx + 1)
                QApplication.processEvents()
            progress.close()
            if not dcm_files:
                # User had self.tag_view.setText here. Using QMessageBox.
                QMessageBox.warning(self, "No DICOM", "No DICOM (.dcm) files found in directory.")
                return
            self.loaded_files = [(f, None) for f in dcm_files]
            self.populate_tree(dcm_files)

    def show_tree_context_menu(self, pos: QPoint): # User's original
        item = self.tree.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        delete_action = QAction(QIcon.fromTheme("edit-delete"), "Delete", self)
        delete_action.triggered.connect(self.delete_selected_items)
        menu.addAction(delete_action)
        if item.depth() == 0:
            merge_action = QAction("Merge Patients", self)
            merge_action.triggered.connect(self.merge_patients)
            menu.addAction(merge_action)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def filter_tree_items(self, text): # User's original (basic filter)
        # Simple filter: hide items that don't match text in any column
        def match(item):
            for col in range(item.columnCount()):
                if text.lower() in item.text(col).lower():
                    return True
            # Recursively check children - if a child matches, parent should be visible
            for i in range(item.childCount()):
                if match(item.child(i)):
                    item.setExpanded(True) # Expand parent if child matches
                    return True
            return False

        def filter_item_recursive(item):
            # If the item itself matches OR any of its children match, it's visible
            is_visible = match(item)
            item.setHidden(not is_visible)
            
            # Even if parent is hidden, children might need to be processed if filter is removed later
            # But for current filtering, if parent is hidden, children are effectively hidden.
            # If parent is visible, ensure its children's visibility is also updated.
            if is_visible:
                for i in range(item.childCount()):
                    filter_item_recursive(item.child(i))
            # If not text (filter cleared), show all items by making them not hidden
            if not text:
                item.setHidden(False)
                for i in range(item.childCount()):
                    filter_item_recursive(item.child(i))


        for i in range(self.tree.topLevelItemCount()):
            filter_item_recursive(self.tree.topLevelItem(i))


    def populate_tree(self, files): # User's original populate_tree
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
                if instance_number is not None:
                    instance_label = f"Instance {instance_number} [{sop_uid}]"
                else:
                    instance_label = f"{os.path.basename(f)} [{sop_uid}]"
                modality = getattr(ds, "Modality", None)
                if modality:
                    modalities.add(str(modality))
                self.file_metadata[f] = (patient_label, study_label, series_label, instance_label)
                hierarchy.setdefault(patient_label, {}).setdefault(study_label, {}).setdefault(series_label, {})[instance_label] = f
            except Exception:
                # logging.warning(f"Could not parse DICOM header for {f}: {e}", exc_info=True) # Add logging
                continue # Skip problematic files
            progress.setValue(idx + 1)
            QApplication.processEvents()
        progress.close()

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
                    for instance, filepath in sorted(instances.items()):
                        instance_item = QTreeWidgetItem([patient, study, series, str(instance)])
                        instance_item.setIcon(3, instance_icon)
                        # Store filepath in UserRole for easy access, not in display text
                        instance_item.setData(0, Qt.ItemDataRole.UserRole, filepath) 
                        series_item.addChild(instance_item)
        self.tree.expandAll()

        patient_count = len(hierarchy)
        study_count = sum(len(studies) for studies in hierarchy.values())
        series_count = sum(len(series_dict) for studies in hierarchy.values() for series_dict in studies.values())
        instance_count = len(files) # This should be len of successfully processed files
        modality_str = ", ".join(sorted(modalities)) if modalities else "Unknown"
        total_bytes = sum(os.path.getsize(f) for f in files if os.path.exists(f)) # Use successfully processed files
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
            QMessageBox.critical(self, "Error", f"Error reading file: {e}")


    def display_selected_tree_file(self): # User's original method
        selected = self.tree.selectedItems()
        if not selected:
            self.tag_table.setRowCount(0)
            self.current_filepath = None
            self.current_ds = None
            self.image_label.clear()
            self.image_label.setVisible(False)
            return
        item = selected[0]
        # Corrected to use UserRole for filepath
        filepath = item.data(0, Qt.ItemDataRole.UserRole) # Assuming filepath is stored here by populate_tree

        if not filepath: # If not an instance node or filepath not set
            self.tag_table.setRowCount(0)
            self.current_filepath = None
            self.current_ds = None
            self.image_label.clear()
            self.image_label.setVisible(False)
            return
        
        # Avoid reloading if the same file is already current, unless preview toggle changed things
        if self.current_filepath == filepath and self.current_ds is not None:
            # Check if preview needs update due to toggle (handled by _update_image_preview)
            self._update_image_preview(self.current_ds)
            return

        try:
            ds = pydicom.dcmread(filepath) # Read full dataset for preview
            self.current_filepath = filepath
            self.current_ds = ds
            self.populate_tag_table(ds)
            self._update_image_preview(ds) # Call helper for preview logic
        except Exception as e:
            self.tag_table.setRowCount(0)
            self.current_filepath = None
            self.current_ds = None
            self.image_label.clear()
            self.image_label.setVisible(False)
            QMessageBox.critical(self, "Error", f"Error reading file: {filepath}\n{e}")
            logging.error(f"Error reading file {filepath}: {e}", exc_info=True)

    # Helper for image preview logic (separated from display_selected_tree_file)
    def _update_image_preview(self, ds):
        if self.preview_toggle.isChecked():
            pixmap = self._get_dicom_pixmap(ds)
            if pixmap:
                # Scale pixmap to fit the label while maintaining aspect ratio
                # Prefer scaling to height, but if it becomes wider than label, scale to width
                scaled_pixmap = pixmap.scaledToHeight(self.image_label.height(), Qt.TransformationMode.SmoothTransformation)
                if scaled_pixmap.width() > self.image_label.width():
                    scaled_pixmap = pixmap.scaledToWidth(self.image_label.width(), Qt.TransformationMode.SmoothTransformation)
                self.image_label.setPixmap(scaled_pixmap)
                self.image_label.setVisible(True)
            else:
                self.image_label.setText("No preview available") # More informative than just clear
                self.image_label.setVisible(True) # Show the label
        else:
            self.image_label.clear()
            self.image_label.setVisible(False)


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

    def populate_tag_table(self, ds): # User's original
        self.tag_table.setRowCount(0)
        self._all_tag_rows = []
        for elem in ds:
            if elem.tag == (0x7fe0, 0x0010):
                value = "<Pixel Data not shown>"
            elif elem.VR in ("OB", "OW", "UN"): # User had "UN" here
                value = "<Binary data not shown>"
            else:
                value = str(elem.value)
            tag_id = f"({elem.tag.group:04X},{elem.tag.element:04X})"
            desc = elem.name
            row_data = [tag_id, desc, value, ""] # Data for the row
            # Store the pydicom element itself for reference (e.g. VR, original type)
            self._all_tag_rows.append({'elem_obj': elem, 'display_row': row_data}) 
        self.apply_tag_table_filter() # Call to apply filter/populate

    def filter_tag_table(self, text): # User's original (text arg often passed by textChanged signal)
        self.apply_tag_table_filter() # Relies on self.search_bar.text()

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
        self.tag_table.resizeColumnsToContents()


    def save_tag_changes(self): # User's original
        if not self.current_ds or not self.current_filepath:
            QMessageBox.warning(self, "No File", "No DICOM file selected.")
            return

        level = self.edit_level_combo.currentText()
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select a node in the tree.")
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
            QMessageBox.warning(self, "No Instances", "No DICOM instances found under this node for the selected level.")
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
                    QMessageBox.warning(self, "Error", f"Failed to parse tag {tag_id_str} or get original element: {e}")
                    logging.error(f"Error parsing tag {tag_id_str}: {e}", exc_info=True)


        if not edits:
            QMessageBox.information(self, "No Changes", "No tags were changed.")
            return

        updated_count = 0
        failed_files = []
        progress = QProgressDialog(f"Saving changes to {level}...", "Cancel", 0, len(filepaths), self)
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
        QMessageBox.information(self, "Batch Edit Complete", msg)
        
        # Refresh view if the currently displayed file was part of the batch
        if self.current_filepath in filepaths:
            self.display_selected_tree_file()
        elif filepaths: # If any files were processed, clear tag table to avoid stale "New Value"
            self.tag_table.setRowCount(0) 


    def edit_tag(self): # User's original
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select an instance in the tree.")
            return
        item = selected[0]
        filepath = item.data(0, Qt.ItemDataRole.UserRole) # Corrected: UserRole
        if not filepath:
            QMessageBox.warning(self, "No Instance", "Please select an instance node.")
            return
        try:
            ds = pydicom.dcmread(filepath)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not read file: {e}")
            return

        tag_str, ok = QInputDialog.getText(self, "Edit Tag", "Enter tag name or (gggg,eeee):")
        if not ok or not tag_str.strip():
            return

        tag = None
        if ',' in tag_str and tag_str.startswith("(") and tag_str.endswith(")"): # Basic check for (g,e) format
            try:
                group, elem = tag_str[1:-1].split(',') # Remove parentheses before splitting
                tag = (int(group, 16), int(elem, 16))
            except ValueError: # Handles non-hex or incorrect split
                QMessageBox.warning(self, "Invalid Tag", "Tag format should be (gggg,eeee) in hex, e.g., (0010,0010).")
                return
        else: # Try to find by name (keyword)
            try:
                # pydicom.tag.Tag can take a keyword string
                tag = pydicom.tag.Tag(tag_str.strip())
            except ValueError: # If keyword is not recognized by pydicom
                 QMessageBox.warning(self, "Not Found", f"Tag keyword '{tag_str}' not recognized by pydicom or not found by name in this file.")
                 return

        # Check if tag exists (Tag object will be created even if not in ds)
        if tag not in ds:
            # Ask if user wants to add it - requires VR
            reply = QMessageBox.question(self, "Tag Not Found", f"Tag {tag_str} ({tag}) not found in this file. Add it as a new tag?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                vr, vr_ok = QInputDialog.getText(self, "Enter VR", "Enter VR for new tag (e.g., LO, SH, UI):")
                if not vr_ok or not vr.strip():
                    return
                new_value, val_ok = QInputDialog.getText(self, "Enter Value", f"Enter value for new tag {tag_str} (VR: {vr.upper()}):")
                if not val_ok: # User can enter empty string if intended
                    return
                try:
                    # Type conversion based on VR for new tag (simplified)
                    if vr.upper() == "UI": converted_val = new_value
                    elif vr.upper() in ["IS", "SL", "SS", "UL", "US"]: converted_val = int(new_value)
                    elif vr.upper() in ["FL", "FD", "DS"]: converted_val = float(new_value)
                    else: converted_val = new_value # Default to string

                    ds.add_new(tag, vr.upper(), converted_val)
                    ds.save_as(filepath)
                    QMessageBox.information(self, "Success", f"Tag {tag_str} added with value '{new_value}'.")
                    self.display_selected_tree_file() # Refresh
                except Exception as e_add:
                    QMessageBox.critical(self, "Error", f"Failed to add new tag: {e_add}")
            return # End here if tag was not found and not added
        
        # If tag exists, proceed to edit
        old_value = str(ds[tag].value)
        new_value, ok = QInputDialog.getText(self, "Edit Tag", f"Tag: {ds[tag].name} {tag}\nCurrent value: {old_value}\nEnter new value:")
        if not ok: # User cancelled or entered nothing they wanted to commit implicitly
            return

        try:
            # Attempt to convert to original type
            original_element = ds[tag]
            original_py_type = type(original_element.value)
            
            if original_element.VR == "UI": ds[tag].value = new_value
            elif original_element.VR in ["IS", "SL", "SS", "UL", "US"]: ds[tag].value = int(new_value)
            elif original_element.VR in ["FL", "FD", "DS"]: ds[tag].value = float(new_value)
            elif original_element.VR == "DA": ds[tag].value = new_value.replace("-","")
            elif original_element.VR == "TM": ds[tag].value = new_value.replace(":","")
            elif isinstance(original_element.value, list): ds[tag].value = [v.strip() for v in new_value.split('\\')]
            elif isinstance(original_element.value, pydicom.personname.PersonName): ds[tag].value = new_value
            else: ds[tag].value = original_py_type(new_value) # General cast

            ds.save_as(filepath)
            QMessageBox.information(self, "Success", f"Tag {tag} updated.")
            self.display_selected_tree_file()
        except Exception as e_update:
            logging.warning(f"Failed to update tag {tag} with value '{new_value}'. Error: {e_update}. Saving as string.")
            try: # Fallback: try saving as string if conversion failed but tag is editable
                ds[tag].value = new_value
                ds.save_as(filepath)
                QMessageBox.information(self, "Success (as string)", f"Tag {tag} updated as string value due to conversion issue.")
                self.display_selected_tree_file()
            except Exception as e_fallback:
                QMessageBox.critical(self, "Error", f"Failed to update tag even as string: {e_fallback}")


    def batch_edit_tag(self): # User's original
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select a node in the tree.")
            return
        item = selected[0] # Anchor node for collecting files
        filepaths = self._collect_instance_filepaths(item)
        if not filepaths:
            QMessageBox.warning(self, "No Instances", "No DICOM instances found under this node.")
            return

        tag_str, ok = QInputDialog.getText(self, "Batch Edit Tag", "Enter tag name or (gggg,eeee):")
        if not ok or not tag_str.strip():
            return

        tag = None
        ds_sample = None # To infer VR if tag exists
        try:
            ds_sample = pydicom.dcmread(filepaths[0], stop_before_pixels=True)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not read sample file {filepaths[0]}: {e}")
            return

        if ',' in tag_str and tag_str.startswith("(") and tag_str.endswith(")"):
            try:
                group, elem = tag_str[1:-1].split(',')
                tag = (int(group, 16), int(elem, 16))
            except ValueError:
                QMessageBox.warning(self, "Invalid Tag", "Tag format should be (gggg,eeee) in hex.")
                return
        else:
            try:
                tag = pydicom.tag.Tag(tag_str.strip())
            except ValueError:
                QMessageBox.warning(self, "Not Found", f"Tag keyword '{tag_str}' not recognized.")
                return

        # Check if tag exists in sample, determine if adding new or editing existing
        vr_for_new_tag = None
        is_new_tag_scenario = (tag not in ds_sample)
        
        if is_new_tag_scenario:
            vr_input, vr_ok = QInputDialog.getText(self, "Enter VR", f"Tag {tag_str} is new. Enter VR (e.g., LO, SH, UI):")
            if not vr_ok or not vr_input.strip():
                return
            vr_for_new_tag = vr_input.strip().upper()
            old_value_display = "<New Tag>"
        else:
            old_value_display = str(ds_sample[tag].value)

        new_value, val_ok = QInputDialog.getText(self, "Batch Edit Tag", 
                                                 f"Tag: {tag_str} ({tag})\n"
                                                 f"Current value (from first file): {old_value_display}\n"
                                                 f"Enter new value to apply to all ({len(filepaths)} files):")
        if not val_ok: # User can enter empty string
            return

        updated_count = 0
        failed_files_info = {} # Store {filepath: error_message}
        progress_batch = QProgressDialog(f"Batch editing tag {tag_str}...", "Cancel", 0, len(filepaths), self)
        progress_batch.setWindowTitle("Batch Tag Edit"); progress_batch.setMinimumDuration(0); progress_batch.setValue(0)

        for idx, fp_batch in enumerate(filepaths):
            progress_batch.setValue(idx)
            if progress_batch.wasCanceled(): break
            QApplication.processEvents()
            try:
                ds_to_edit = pydicom.dcmread(fp_batch)
                current_vr = vr_for_new_tag # For new tags
                if tag in ds_to_edit: # Existing tag, use its VR for conversion
                    current_vr = ds_to_edit[tag].VR
                elif not vr_for_new_tag: # Should not happen if logic above is correct
                    failed_files_info[fp_batch] = "VR missing for new tag scenario (internal error)."
                    continue
                
                # Type conversion (simplified, expand as needed)
                if current_vr == "UI": converted_batch_val = new_value
                elif current_vr in ["IS", "SL", "SS", "UL", "US"]: converted_batch_val = int(new_value)
                elif current_vr in ["FL", "FD", "DS"]: converted_batch_val = float(new_value)
                # Add DA, TM, PN, multi-value list handling
                else: converted_batch_val = new_value # Default to string

                if tag in ds_to_edit:
                    ds_to_edit[tag].value = converted_batch_val
                else: # Add as new tag
                    ds_to_edit.add_new(tag, current_vr, converted_batch_val)
                
                ds_to_edit.save_as(fp_batch)
                updated_count += 1
            except Exception as e_batch_file:
                failed_files_info[fp_batch] = str(e_batch_file)
        progress_batch.setValue(len(filepaths))

        msg_batch = f"Batch edit for tag {tag_str} complete.\nUpdated {updated_count} file(s)."
        if failed_files_info:
            msg_batch += f"\nFailed to update {len(failed_files_info)} file(s)."
            # Optionally list some errors or refer to logs
        QMessageBox.information(self, "Batch Edit Complete", msg_batch)
        if self.current_filepath in filepaths: # Refresh if current file was affected
            self.display_selected_tree_file()


    def save_as(self): # User's original, ensure it uses self.default_export_dir
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select a node in the tree to export.")
            return
        tree_item = selected[0]
        # Always traverse up to the patient node (depth 0) for full patient export context
        # Or, if user selects a Study/Series, export just that. For now, full patient from selection.
        # This can be refined to export exactly what's selected + children.
        # For simplicity of reverting to user's code:
        # while tree_item.parent(): 
        #    tree_item = tree_item.parent() # This makes it always export the patient of the selected item
        # More flexible: export based on the selected item and its children
        filepaths = self._collect_instance_filepaths(tree_item) # Collect from the selected item downwards

        if not filepaths:
            QMessageBox.warning(self, "No Instances", "No DICOM instances found under the selected node.")
            return

        export_type, ok = QInputDialog.getItem(self, "Export Type", "Export as:", ["Directory", "ZIP"], 0, False)
        if not ok:
            return

        if export_type == "Directory":
            out_dir = QFileDialog.getExistingDirectory(self, "Select Export Directory", self.default_export_dir)
            if not out_dir: return

            exported_count = 0; errors = []
            progress = QProgressDialog("Exporting files to directory...", "Cancel", 0, len(filepaths), self)
            progress.setWindowTitle("Exporting to Directory"); progress.setMinimumDuration(0); progress.setValue(0)
            for idx, fp in enumerate(filepaths):
                progress.setValue(idx)
                if progress.wasCanceled(): break
                QApplication.processEvents()
                try:
                    # Save flat into the selected directory.
                    # To preserve structure, more complex path construction for out_path is needed.
                    out_path = os.path.join(out_dir, os.path.basename(fp))
                    # Using shutil.copy2 to preserve metadata and avoid re-reading/saving dataset if not modified.
                    shutil.copy2(fp, out_path) 
                    exported_count +=1
                except Exception as e:
                    errors.append(f"Failed to export {os.path.basename(fp)}: {e}")
            progress.setValue(len(filepaths))
            msg = f"Exported {exported_count} files to {out_dir}."
            if errors: msg += "\n\nErrors:\n" + "\n".join(errors)
            QMessageBox.information(self, "Export Complete", msg)
        else:  # ZIP
            out_zip_path, _ = QFileDialog.getSaveFileName(self, "Save ZIP Archive", self.default_export_dir, "ZIP Archives (*.zip)")
            if not out_zip_path: return
            if not out_zip_path.lower().endswith('.zip'): out_zip_path += '.zip'

            zipped_count = 0; errors = []
            progress_zip = QProgressDialog("Creating ZIP archive...", "Cancel", 0, len(filepaths), self)
            progress_zip.setWindowTitle("Creating ZIP"); progress_zip.setMinimumDuration(0); progress_zip.setValue(0)
            try:
                with zipfile.ZipFile(out_zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zipf:
                    for idx, fp in enumerate(filepaths):
                        progress_zip.setValue(idx)
                        if progress_zip.wasCanceled(): break
                        QApplication.processEvents()
                        # arcname is the name inside the ZIP. For flat structure, use basename.
                        zipf.write(fp, arcname=os.path.basename(fp))
                        zipped_count += 1
                msg = f"Exported {zipped_count} files to {out_zip_path}."
            except Exception as e:
                msg = f"Failed to create ZIP: {e}"
                logging.error(msg, exc_info=True)
            progress_zip.setValue(len(filepaths))
            if errors: msg += "\n\nErrors during zipping:\n" + "\n".join(errors) # Should populate errors inside loop
            QMessageBox.information(self, "Export Complete", msg)


    def dicom_send(self): # User's original (with minor logging/error message consistency)
        logging.info("DICOM send initiated")
        if AE is None or not STORAGE_CONTEXTS or VERIFICATION_SOP_CLASS is None:
            logging.error("pynetdicom not available or not fully imported.")
            QMessageBox.critical(self, "Missing Dependency",
                                 "pynetdicom is required for DICOM send.\n"
                                 "Check your environment and restart the application.\n"
                                 f"Python executable: {sys.executable}\n")
            return
        
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select a node in the tree to send.")
            return
        
        # Collect all instances under the first selected item (could be refined to send all selected items' children)
        tree_item_anchor = selected[0]
        # For simplicity, let's assume we send all instances under this anchor, regardless of its level.
        # To send only the patient of the selected item, traverse up first:
        # while tree_item_anchor.parent():
        #     tree_item_anchor = tree_item_anchor.parent()
        filepaths = self._collect_instance_filepaths(tree_item_anchor)

        if not filepaths:
            QMessageBox.warning(self, "No Instances", "No DICOM instances found under the selected node.")
            return

        dlg = DicomSendDialog(self, config=self.dicom_send_config) # Pass full config
        if dlg.exec() != QDialog.DialogCode.Accepted:
            logging.info("DICOM send cancelled by user.")
            return
        
        send_params = dlg.get_params()
        if send_params is None: return # Error handled in get_params
        calling_ae, remote_ae, host, port = send_params
        
        logging.info(f"Sending {len(filepaths)} files to {host}:{port} (Remote AE: {remote_ae}, Calling AE: {calling_ae})")

        ae_instance = AE(ae_title=calling_ae) # Renamed from ae to ae_instance
        
        # Dynamically add contexts based on files to be sent
        unique_sop_classes_to_send = set()
        for fp_ctx in filepaths:
            try:
                ds_ctx = pydicom.dcmread(fp_ctx, stop_before_pixels=True) # Only need header for SOPClassUID
                if hasattr(ds_ctx, 'SOPClassUID'):
                    unique_sop_classes_to_send.add(ds_ctx.SOPClassUID)
            except Exception as e_ctx:
                logging.warning(f"Could not read SOPClassUID from {fp_ctx} for context setup: {e_ctx}")
        
        if not unique_sop_classes_to_send:
            QMessageBox.critical(self, "DICOM Send Error", "No valid SOP Class UIDs found in the selected files to determine transfer contexts.")
            return

        for sop_uid in unique_sop_classes_to_send:
            ae_instance.add_requested_context(sop_uid) # Add specific SOP classes found in the files
        ae_instance.add_requested_context(VERIFICATION_SOP_CLASS) # For C-ECHO

        assoc = ae_instance.associate(host, port, ae_title=remote_ae)
        if not assoc.is_established:
            logging.error(f"Association to {host}:{port} ({remote_ae}) failed. Details: {assoc}")
            QMessageBox.critical(self, "DICOM Send Failed", f"Association to {host}:{port} (Remote AE: {remote_ae}) failed.\nDetails: {assoc}")
            return

        logging.info("Association established.")
        # C-ECHO (Verification)
        echo_status = assoc.send_c_echo()
        if echo_status and getattr(echo_status, 'Status', None) == 0x0000:
            logging.info("C-ECHO verification successful.")
        else:
            logging.warning(f"C-ECHO verification failed or status not 0x0000. Status: {echo_status}")
            # Optionally ask user if they want to proceed without successful C-ECHO

        # Progress Dialog
        total_files = len(filepaths)
        # total_bytes = sum(os.path.getsize(fp) for fp in filepaths if os.path.exists(fp)) # Can be slow for many files
        # mb_total = total_bytes / (1024 * 1024)
        progress = QProgressDialog("Sending DICOM files...", "Cancel", 0, total_files, self)
        progress.setWindowTitle("DICOM Send Progress"); progress.setMinimumDuration(0); progress.setValue(0)
        # progress.setLabelText(f"Sent 0/{total_files} images, 0.0/{mb_total:.1f} MB")

        sent_ok = 0; sent_warning = 0; failed_send = 0
        failed_details_list = [] # For storing details of failures
        # sent_bytes = 0

        for idx, fp_send in enumerate(filepaths):
            progress.setValue(idx + 1)
            # mb_sent = sent_bytes / (1024 * 1024)
            # progress.setLabelText(f"Sent {sent_ok+sent_warning}/{total_files} images, {mb_sent:.1f}/{mb_total:.1f} MB. Failed: {failed_send}")
            progress.setLabelText(f"Sending {idx+1}/{total_files}. Success: {sent_ok}, Warn: {sent_warning}, Fail: {failed_send}")

            if progress.wasCanceled():
                failed_details_list.append("User cancelled operation.")
                break
            QApplication.processEvents()
            try:
                ds_send = pydicom.dcmread(fp_send)
                # Check if the SOP Class for this dataset is supported by the association
                if not any(ctx.abstract_syntax == ds_send.SOPClassUID and ctx.result == 0x00 for ctx in assoc.accepted_contexts):
                    err_msg = f"{os.path.basename(fp_send)}: SOP Class {ds_send.SOPClassUID} not accepted by remote."
                    logging.error(err_msg)
                    failed_details_list.append(err_msg)
                    failed_send += 1
                    continue

                status = assoc.send_c_store(ds_send)
                # file_size = os.path.getsize(fp_send) if os.path.exists(fp_send) else 0 # For byte count

                if status:
                    status_code = getattr(status, "Status", -1) # Default to -1 if Status attr missing
                    if status_code == 0x0000: # Success
                        sent_ok += 1
                        # sent_bytes += file_size
                    elif status_code in [0xB000, 0xB006, 0xB007]: # Warnings considered "sent" but with issues
                        sent_warning +=1
                        # sent_bytes += file_size
                        warn_msg = f"{os.path.basename(fp_send)}: Sent with warning, Status 0x{status_code:04X}"
                        logging.warning(warn_msg)
                        failed_details_list.append(warn_msg) # Also list warnings in details
                    else: # Failure
                        err_msg = f"{os.path.basename(fp_send)}: C-STORE failed, Status 0x{status_code:04X}"
                        logging.error(err_msg + f" - {status}")
                        failed_details_list.append(err_msg)
                        failed_send += 1
                else: # No status object returned
                    err_msg = f"{os.path.basename(fp_send)}: C-STORE failed, no status returned."
                    logging.error(err_msg)
                    failed_details_list.append(err_msg)
                    failed_send += 1
            except Exception as e_store:
                err_msg = f"{os.path.basename(fp_send)}: Exception - {e_store}"
                logging.error(f"Send failed for {fp_send}: {e_store}", exc_info=True)
                failed_details_list.append(err_msg)
                failed_send += 1
        
        assoc.release()
        progress.close() # Ensure progress dialog is closed
        
        msg_final = f"DICOM Send Complete.\n\nSuccess: {sent_ok}\nSent with Warnings: {sent_warning}\nFailed: {failed_send}"
        if failed_details_list:
            msg_final += "\n\nDetails (first few issues):\n" + "\n".join(failed_details_list[:5]) # Show first 5
            if len(failed_details_list) > 5: msg_final += f"\n...and {len(failed_details_list)-5} more (see application logs)."
        logging.info(msg_final) # Log the full summary
        QMessageBox.information(self, "DICOM Send Report", msg_final)


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

    def anonymise_selected(self): # User's original
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select a node in the tree to anonymise.")
            return
        tree_item = selected[0] # Anchor on the first selected item
        # Traverse up to the patient node to anonymize the whole patient
        while tree_item.parent():
            tree_item = tree_item.parent()
        
        filepaths = self._collect_instance_filepaths(tree_item)
        if not filepaths:
            QMessageBox.warning(self, "No Instances", f"No DICOM instances found under patient: {tree_item.text(0)}")
            return

        reply = QMessageBox.question(
            self, "Confirm Anonymization",
            f"This will irreversibly anonymize {len(filepaths)} files in-place for patient '{tree_item.text(0)}'.\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes: return

        tags_to_blank = [ # User's list
            (0x0010, 0x0010), (0x0010, 0x0020), (0x0010, 0x0030), (0x0010, 0x0032), (0x0010, 0x0040),
            (0x0010, 0x1000), (0x0010, 0x1001), (0x0010, 0x2160), (0x0010, 0x4000), (0x0008, 0x0090),
            (0x0008, 0x0050), (0x0008, 0x0080), (0x0008, 0x0081), (0x0008, 0x1040), (0x0008, 0x1070),
            (0x0008, 0x1030), (0x0008, 0x103E), (0x0020, 0x0010) # StudyID
            # UIDs (0x0020,0x000D), (0x0020,0x000E), (0x0008,0x0018) are handled separately below
        ]
        now = datetime.datetime.now()
        anon_prefix = f"ANON_{now.strftime('%Y%m%d_%H%M%S')}"
        
        # Consistent new UIDs for this patient's anonymization batch
        new_main_study_uid_for_patient = generate_uid() # One study UID for all studies of this anon patient
        series_uid_map_anon = {} # old_series_uid -> new_anon_series_uid (within this patient's batch)

        updated = 0; failed = []
        progress = QProgressDialog(f"Anonymizing files for patient '{tree_item.text(0)}'...", "Cancel", 0, len(filepaths), self)
        progress.setWindowTitle("Anonymizing"); progress.setMinimumDuration(0); progress.setValue(0)

        for idx_anon, fp_anon in enumerate(filepaths):
            progress.setValue(idx_anon)
            if progress.wasCanceled(): break
            QApplication.processEvents()
            try:
                ds = pydicom.dcmread(fp_anon)
                # Apply consistent anonymized PatientName and PatientID
                ds.PatientName = f"{anon_prefix}_PATIENT"
                ds.PatientID = f"{anon_prefix}_PID"
                
                for tag_tuple in tags_to_blank:
                    if tag_tuple in ds:
                        elem = ds[tag_tuple]
                        # More specific blanking based on VR
                        if elem.VR == "DA": elem.value = "19000101"
                        elif elem.VR == "TM": elem.value = "000000"
                        elif elem.VR == "CS" and tag_tuple == (0x0010,0x0040): elem.value = "O" # PatientSex
                        elif elem.VR == "PN": elem.value = f"{anon_prefix}_NAME" # For PN
                        else: elem.value = "" # Default blanking for other text types

                # UIDs: StudyInstanceUID becomes consistent for this patient's anonymized studies
                # SeriesInstanceUID becomes consistent per original series (but new)
                # SOPInstanceUID becomes new unique per instance
                ds.StudyInstanceUID = new_main_study_uid_for_patient 
                
                old_series_uid_anon = str(ds.SeriesInstanceUID)
                if old_series_uid_anon not in series_uid_map_anon:
                    series_uid_map_anon[old_series_uid_anon] = generate_uid()
                ds.SeriesInstanceUID = series_uid_map_anon[old_series_uid_anon]
                
                ds.SOPInstanceUID = generate_uid() # New unique SOP Instance UID
                if hasattr(ds, "file_meta") and hasattr(ds.file_meta, "MediaStorageSOPInstanceUID"):
                    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
                
                # Optionally remove private tags, curves, overlays from config later
                # ds.remove_private_tags()

                ds.save_as(fp_anon)
                updated += 1
            except Exception as e_anon_file:
                failed.append(f"{os.path.basename(fp_anon)}: {e_anon_file}")
                logging.error(f"Failed to anonymize {fp_anon}: {e_anon_file}", exc_info=True)
        progress.setValue(len(filepaths))

        msg = f"Anonymization complete.\nFiles updated: {updated}\nFailed: {len(failed)}"
        if failed: msg += "\n\nDetails:\n" + "\n".join(failed[:5]) # Show first 5 errors
        QMessageBox.information(self, "Anonymization", msg)
        
        # Refresh tree (important as identifiers have changed)
        # This simplified refresh re-scans all currently known files.
        all_current_fps_after_anon = [f_info[0] for f_info in self.loaded_files if os.path.exists(f_info[0])]
        self.clear_loaded_files()
        if all_current_fps_after_anon:
            # Determine a source description or just pass the list
            self._load_dicom_files_from_list(all_current_fps_after_anon, "data after anonymization")


    def merge_patients(self): # User's original
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.MultiSelection) # Allow multi-select for this op
        selected = self.tree.selectedItems()
        patient_nodes = [item for item in selected if item.depth() == 0]
        
        if len(patient_nodes) < 2:
            QMessageBox.warning(self, "Merge Patients", "Select at least two patient nodes to merge.\nHold Ctrl or Shift to select multiple patients.")
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
            QMessageBox.warning(self, "Merge Patients", f"Could not find any DICOM file for the primary patient '{primary_label_selected}' to get ID/Name.")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection) # Restore
            return
        try:
            ds_primary = pydicom.dcmread(primary_fp_sample, stop_before_pixels=True)
            primary_id_val = str(ds_primary.PatientID)
            primary_name_val = str(ds_primary.PatientName)
        except Exception as e_merge_primary:
            QMessageBox.critical(self, "Merge Patients", f"Failed to read primary patient file: {e_merge_primary}")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection) # Restore
            return

        files_to_update = []
        secondary_nodes_to_process = [node for node in patient_nodes if node is not primary_node]
        for node_sec in secondary_nodes_to_process:
            files_to_update.extend(self._collect_instance_filepaths(node_sec))

        if not files_to_update:
             QMessageBox.information(self, "Merge Patients", "No files found in the secondary patient(s) to merge.")
             self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection) # Restore
             return


        reply = QMessageBox.question(
            self, "Confirm Merge",
            f"This will update {len(files_to_update)} files from other patient(s) to PatientID '{primary_id_val}' and PatientName '{primary_name_val}'.\n"
            "The original patient entries for these merged studies will be removed from the tree view.\n"
            "This modifies files in-place. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection) # Restore
            return

        updated_m = 0; failed_m = []
        progress_m = QProgressDialog("Merging patients...", "Cancel", 0, len(files_to_update), self)
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
        QMessageBox.information(self, "Merge Patients Complete", msg_m)
        
        # Refresh the tree from all known files to reflect the merge
        all_known_files_after_merge = list(set(f_info[0] for f_info in self.loaded_files if os.path.exists(f_info[0])))
        self.clear_loaded_files() # Clear UI and internal state
        if all_known_files_after_merge:
            self._load_dicom_files_from_list(all_known_files_after_merge, "data after merge")

        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection) # Restore selection mode


    def delete_selected_items(self): # User's original
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Delete", "Please select one or more items to delete.")
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
            QMessageBox.warning(self, "Delete", "No actual files found corresponding to selected items.")
            return

        summary_str = ", ".join([f"{v} {k}(s)" for k,v in item_counts.items() if v > 0])
        confirm_msg = (f"You are about to delete: {summary_str}.\n"
                       f"This will permanently delete {len(files_to_delete)} file(s) from disk.\n"
                       "THIS CANNOT BE UNDONE. Are you sure?")
        
        reply = QMessageBox.question(self, "Confirm Delete", confirm_msg,
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No) # Default to No
        if reply != QMessageBox.StandardButton.Yes:
            return

        progress_d = QProgressDialog("Deleting files...", "Cancel", 0, len(files_to_delete), self)
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

        # Refresh tree from the updated self.loaded_files
        remaining_files_after_delete = [f_info[0] for f_info in self.loaded_files if os.path.exists(f_info[0])]
        self._load_dicom_files_from_list(remaining_files_after_delete, "data after deletion")
        # Clear other UI elements that might refer to deleted items
        self.tag_table.setRowCount(0); self._all_tag_rows = []
        self.image_label.clear(); self.image_label.setVisible(False)
        self.current_filepath = None; self.current_ds = None

        msg_d = f"Deleted {deleted_d_count} file(s)."
        if failed_d_list: msg_d += "\n\nFailed to delete:\n" + "\n".join(failed_d_list[:3])
        QMessageBox.information(self, "Delete Complete", msg_d)


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