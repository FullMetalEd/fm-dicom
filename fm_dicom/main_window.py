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

from pynetdicom import AE, AllStoragePresentationContexts
from pynetdicom.sop_class import Verification
VERIFICATION_SOP_CLASS = Verification
STORAGE_CONTEXTS = AllStoragePresentationContexts


class ZipExtractionDialog(QProgressDialog):
    """Progress dialog for ZIP extraction"""
    
    def __init__(self, zip_path, parent=None):
        super().__init__("Preparing to extract ZIP...", "Cancel", 0, 100, parent)
        self.setWindowTitle("Extracting ZIP Archive")
        self.setMinimumDuration(0)
        self.setAutoClose(False)
        self.setAutoReset(False)
        
        self.zip_path = zip_path
        self.temp_dir = tempfile.mkdtemp()
        self.extracted_files = []
        self.success = False
        
        # Start extraction in worker thread
        self.worker = ZipExtractionWorker(zip_path, self.temp_dir)
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.extraction_complete.connect(self.extraction_finished)
        self.worker.extraction_failed.connect(self.extraction_error)
        self.worker.start()
        
        # Cancel handling
        self.canceled.connect(self.cancel_extraction)
        
    def update_progress(self, current, total, filename):
        if total > 0:
            progress_value = int((current / total) * 100)
            self.setValue(progress_value)
        self.setLabelText(f"Extracting: {os.path.basename(filename)} ({current}/{total})")
        QApplication.processEvents()
        
    def extraction_finished(self, temp_dir, extracted_files):
        self.temp_dir = temp_dir
        self.extracted_files = extracted_files
        self.success = True
        self.setValue(100)
        self.setLabelText("Extraction complete")
        self.accept()
        
    def extraction_error(self, error_message):
        self.success = False
        FocusAwareMessageBox.critical(self, "Extraction Error", error_message)
        self.reject()
        
    def cancel_extraction(self):
        if self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(3000)
            if self.worker.isRunning():
                self.worker.terminate()
                self.worker.wait()
        
        # Clean up temp directory
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except:
                pass
        self.reject()



class DicomdirScanDialog(QProgressDialog):
    """Progress dialog for DICOMDIR scanning"""
    
    def __init__(self, extracted_files, parent=None):
        super().__init__("Searching for DICOMDIR files...", "Cancel", 0, 100, parent)
        self.setWindowTitle("Reading DICOMDIR")
        self.setMinimumDuration(0)
        self.setAutoClose(False)
        self.setAutoReset(False)
        
        self.extracted_files = extracted_files
        self.dicom_files = []
        self.success = False
        
        # Start scanning in worker thread
        self.worker = DicomdirScanWorker(extracted_files)
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.scan_complete.connect(self.scan_finished)
        self.worker.scan_failed.connect(self.scan_error)
        self.worker.start()
        
        # Cancel handling
        self.canceled.connect(self.cancel_scan)
        
    def update_progress(self, current, total, current_file):
        if total > 0:
            progress_value = int((current / total) * 100)
            self.setValue(progress_value)
        self.setLabelText(f"Reading DICOMDIR: {current_file}")
        QApplication.processEvents()
        
    def scan_finished(self, dicom_files):
        self.dicom_files = dicom_files
        self.success = True
        self.setValue(100)
        self.setLabelText(f"Found {len(dicom_files)} DICOM files")
        self.accept()
        
    def scan_error(self, error_message):
        self.success = False
        self.error_message = error_message
        self.reject()
        
    def cancel_scan(self):
        if self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(3000)
            if self.worker.isRunning():
                self.worker.terminate()
                self.worker.wait()
        self.reject()



class FocusAwareMessageBox(QMessageBox):
    """QMessageBox that doesn't steal focus unless app is already active"""
    
    def __init__(self, icon, title, text, buttons=QMessageBox.StandardButton.Ok, parent=None):
        super().__init__(icon, title, text, buttons, parent)
        
        # If app doesn't have focus, prevent focus stealing
        if not self._app_has_focus():
            self.setWindowFlags(
                self.windowFlags() | 
                Qt.WindowType.WindowDoesNotAcceptFocus
            )
    
    def _app_has_focus(self):
        """Check if our app currently has focus"""
        return QApplication.activeWindow() is not None
    
    @staticmethod
    def information(parent, title, text, *args, **kwargs):
        """Drop-in replacement for QMessageBox.information"""
        msgbox = FocusAwareMessageBox(QMessageBox.Icon.Information, title, text, parent=parent)
        return msgbox.exec()
    
    @staticmethod
    def warning(parent, title, text, *args, **kwargs):
        """Drop-in replacement for QMessageBox.warning"""
        msgbox = FocusAwareMessageBox(QMessageBox.Icon.Warning, title, text, parent=parent)
        return msgbox.exec()
    
    @staticmethod
    def critical(parent, title, text, *args, **kwargs):
        """Drop-in replacement for QMessageBox.critical"""
        msgbox = FocusAwareMessageBox(QMessageBox.Icon.Critical, title, text, parent=parent)
        return msgbox.exec()
    
    @staticmethod
    def question(parent, title, text, buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, defaultButton=QMessageBox.StandardButton.NoButton, *args, **kwargs):
        """Drop-in replacement for QMessageBox.question"""
        msgbox = FocusAwareMessageBox(QMessageBox.Icon.Question, title, text, buttons, parent)
        if defaultButton != QMessageBox.StandardButton.NoButton:
            msgbox.setDefaultButton(defaultButton)
        return msgbox.exec()


class FocusAwareProgressDialog(QProgressDialog):
    """QProgressDialog that doesn't steal focus unless app is already active"""
    
    def __init__(self, labelText, cancelButtonText, minimum, maximum, parent=None):
        super().__init__(labelText, cancelButtonText, minimum, maximum, parent)
        
        # If app doesn't have focus, prevent focus stealing
        if not self._app_has_focus():
            self.setWindowFlags(
                self.windowFlags() | 
                Qt.WindowType.WindowDoesNotAcceptFocus
            )
            self.setModal(False)  # Don't block other apps
    
    def _app_has_focus(self):
        """Check if our app currently has focus"""
        return QApplication.activeWindow() is not None


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
        logging.debug(f"Warning (ensure_dir_exists): Called with empty file_path.", file=sys.stderr)
        return False
    try:
        dir_name = os.path.dirname(file_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
            return True
    except Exception as e:
        logging.error(f"Warning (ensure_dir_exists): Could not create directory for {file_path}: {e}", file=sys.stderr)
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
        "default_export_dir": os.path.join(default_user_home_dir, "DICOM_Exports"),
        "default_import_dir": os.path.join(default_user_home_dir, "Downloads"),
        "anonymization": {},
        "recent_paths": [],
        "theme": "dark",
        "language": "en",
        "file_picker_native": False  # ADD THIS LINE - False = use Python/Qt picker by default
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
                logging.info(f"INFO (load_config): Loaded configuration from {path_to_try}", file=sys.stderr)
                # loaded_config_source_path = path_to_try
                break 
            except Exception as e:
                logging.critical(f"Warning (load_config): Could not load/parse config from {path_to_try}: {e}", file=sys.stderr)
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
             logging.critical(f"Warning (load_config): Path key '{key}' missing, using default: {final_config[key]}", file=sys.stderr)
        elif final_config[key] is None and key in default_config_data: # Key present but explicitly null
            final_config[key] = default_config_data[key] # Revert to default
            logging.info(f"Info (load_config): Path key '{key}' was null, reverted to default: {final_config[key]}", file=sys.stderr)

    if loaded_user_config is None: # No config file found or loaded successfully
        logging.info(f"INFO (load_config): No existing config found. Creating default at: {preferred_config_path}", file=sys.stderr)
        if ensure_dir_exists(preferred_config_path): # Ensure config directory exists
            try:
                with open(preferred_config_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(final_config, f, sort_keys=False, allow_unicode=True)
                if final_config.get("log_path"): # Ensure default log directory exists
                    ensure_dir_exists(final_config["log_path"])
            except Exception as e:
                logging.critical(f"ERROR (load_config): Could not create default config at {preferred_config_path}: {e}", file=sys.stderr)
        else:
            logging.critical(f"ERROR (load_config): Could not create dir for default config: {os.path.dirname(preferred_config_path)}. Using in-memory defaults.", file=sys.stderr)
    
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

# Force pydicom to recognize GDCM is available
try:
    import python_gdcm
    sys.modules['gdcm'] = python_gdcm
    
    # Force set the HAVE_GDCM flag
    from pydicom.pixel_data_handlers import gdcm_handler
    gdcm_handler.HAVE_GDCM = True
    
    if gdcm_handler.is_available():
        handlers = pydicom.config.pixel_data_handlers
        if gdcm_handler in handlers:
            handlers.remove(gdcm_handler)
            handlers.insert(0, gdcm_handler)
        logging.info("✅ GDCM forced available and prioritized")
    else:
        logging.error("❌ GDCM still not available")
        
except Exception as e:
    logging.error(f"❌ Error forcing GDCM: {e}")

# --- Primary Selection Dialog (NEW) ---
class PrimarySelectionDialog(QDialog):
    def __init__(self, parent, items, item_type):
        super().__init__(parent)
        self.setWindowTitle(f"Select Primary {item_type}")
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        
        label = QLabel(f"Select which {item_type.lower()} to use as primary (whose metadata will be kept):")
        layout.addWidget(label)
        
        self.button_group = QButtonGroup()
        self.radio_buttons = []
        
        for i, item in enumerate(items):
            radio = QRadioButton(item.text(0))  # Display the tree item text
            if i == 0:  # Default to first
                radio.setChecked(True)
            self.button_group.addButton(radio, i)
            self.radio_buttons.append(radio)
            layout.addWidget(radio)
        
        # OK/Cancel buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def get_selected_index(self):
        """Return the index of the selected primary item"""
        return self.button_group.checkedId()



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
            FocusAwareMessageBox.critical(self, "Invalid Port", "Port must be a number between 1 and 65535.")
            return None # Indicate error
        
        return (
            self.ae_title.text().strip(),
            self.remote_ae.text().strip(),
            self.host.text().strip(),
            port_val # Already int
        )

class FileAnalysisResultsDialog(QDialog):
    """Dialog to display file analysis results with export capabilities"""
    
    def __init__(self, analysis_results, parent=None):
        super().__init__(parent)
        self.analysis_results = analysis_results
        self.setWindowTitle("File Analysis Results")
        self.setModal(True)
        self.resize(900, 600)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Summary section
        summary_group = QGroupBox("Summary")
        summary_layout = QVBoxLayout(summary_group)
        
        total_files = len(self.analysis_results['files'])
        unique_dimensions = len(self.analysis_results['unique_dimensions'])
        patients_count = len(self.analysis_results['unique_patients'])
        
        summary_text = f"""
        Total Files: {total_files}
        Unique Patients: {patients_count}
        Unique Image Dimensions: {unique_dimensions}
        Size Range: {self.analysis_results['size_range']}
        Large Files (>10MB): {len(self.analysis_results['large_files'])}
        Transfer Syntaxes: {len(self.analysis_results['transfer_syntaxes'])}
        """
        
        summary_label = QLabel(summary_text)
        summary_label.setFont(QFont("monospace"))
        summary_layout.addWidget(summary_label)
        layout.addWidget(summary_group)
        
        # Detailed results table
        results_group = QGroupBox("Detailed File Analysis")
        results_layout = QVBoxLayout(results_group)
        
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(9)
        self.results_table.setHorizontalHeaderLabels([
            "Filename", "Patient ID", "Dimensions", "Bits", "Photometric", 
            "Transfer Syntax", "Uncompressed Size", "File Size", "Compression Ratio"
        ])
        
        # Populate table
        self.results_table.setRowCount(len(self.analysis_results['files']))
        for row, file_info in enumerate(self.analysis_results['files']):
            self.results_table.setItem(row, 0, QTableWidgetItem(file_info['filename']))
            self.results_table.setItem(row, 1, QTableWidgetItem(file_info['patient_id']))
            self.results_table.setItem(row, 2, QTableWidgetItem(file_info['dimensions']))
            self.results_table.setItem(row, 3, QTableWidgetItem(str(file_info['bits'])))
            self.results_table.setItem(row, 4, QTableWidgetItem(file_info['photometric']))
            self.results_table.setItem(row, 5, QTableWidgetItem(file_info['transfer_syntax_name']))
            self.results_table.setItem(row, 6, QTableWidgetItem(f"{file_info['uncompressed_mb']:.1f} MB"))
            self.results_table.setItem(row, 7, QTableWidgetItem(f"{file_info['file_size_mb']:.1f} MB"))
            self.results_table.setItem(row, 8, QTableWidgetItem(f"{file_info['compression_ratio']:.1f}x"))
        
        self.results_table.resizeColumnsToContents()
        results_layout.addWidget(self.results_table)
        layout.addWidget(results_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        export_csv_btn = QPushButton("Export CSV")
        export_csv_btn.clicked.connect(self.export_csv)
        
        export_report_btn = QPushButton("Export Report")
        export_report_btn.clicked.connect(self.export_report)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        
        button_layout.addWidget(export_csv_btn)
        button_layout.addWidget(export_report_btn)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
    
    def export_csv(self):
        """Export results to CSV file"""
        filename, _ = self.parent()._get_save_filename(
            "Export Analysis Results", 
            "file_analysis_results.csv", 
            "CSV Files (*.csv)"
        )
        if not filename:
            return
            
        try:
            import csv
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header
                headers = [
                    "Filename", "Patient ID", "Dimensions", "Bits", "Photometric",
                    "Transfer Syntax", "Uncompressed Size (MB)", "File Size (MB)", "Compression Ratio"
                ]
                writer.writerow(headers)
                
                # Write data
                for file_info in self.analysis_results['files']:
                    writer.writerow([
                        file_info['filename'],
                        file_info['patient_id'],
                        file_info['dimensions'],
                        file_info['bits'],
                        file_info['photometric'],
                        file_info['transfer_syntax_name'],
                        f"{file_info['uncompressed_mb']:.1f}",
                        f"{file_info['file_size_mb']:.1f}",
                        f"{file_info['compression_ratio']:.1f}"
                    ])
            
            FocusAwareMessageBox.information(self, "Export Complete", f"Analysis results exported to:\n{filename}")
            
        except Exception as e:
            FocusAwareMessageBox.critical(self, "Export Error", f"Failed to export CSV:\n{str(e)}")
    
    def export_report(self):
        """Export detailed report to text file"""
        filename, _ = self.parent()._get_save_filename(
            "Export Analysis Report", 
            "file_analysis_report.txt", 
            "Text Files (*.txt)"
        )
        if not filename:
            return
            
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("DICOM FILE ANALYSIS REPORT\n")
                f.write("=" * 50 + "\n\n")
                
                # Summary
                f.write("SUMMARY\n")
                f.write("-" * 20 + "\n")
                f.write(f"Total Files: {len(self.analysis_results['files'])}\n")
                f.write(f"Unique Patients: {len(self.analysis_results['unique_patients'])}\n")
                f.write(f"Unique Dimensions: {self.analysis_results['unique_dimensions']}\n")
                f.write(f"Size Range: {self.analysis_results['size_range']}\n")
                f.write(f"Large Files (>10MB): {len(self.analysis_results['large_files'])}\n\n")
                
                # Transfer Syntaxes
                f.write("TRANSFER SYNTAXES\n")
                f.write("-" * 20 + "\n")
                for ts_name, count in self.analysis_results['transfer_syntaxes'].items():
                    f.write(f"  {ts_name}: {count} files\n")
                f.write("\n")
                
                # Large Files
                if self.analysis_results['large_files']:
                    f.write("LARGE FILES (>10MB uncompressed)\n")
                    f.write("-" * 35 + "\n")
                    for file_info in self.analysis_results['large_files']:
                        f.write(f"  {file_info['filename']}: {file_info['dimensions']}, {file_info['uncompressed_mb']:.1f}MB\n")
                    f.write("\n")
                
                # Detailed file list
                f.write("DETAILED FILE LIST\n")
                f.write("-" * 20 + "\n")
                for file_info in self.analysis_results['files']:
                    f.write(f"File: {file_info['filename']}\n")
                    f.write(f"  Patient: {file_info['patient_id']}\n")
                    f.write(f"  Dimensions: {file_info['dimensions']}\n")
                    f.write(f"  Transfer Syntax: {file_info['transfer_syntax_name']}\n")
                    f.write(f"  Size: {file_info['file_size_mb']:.1f}MB (compressed), {file_info['uncompressed_mb']:.1f}MB (uncompressed)\n")
                    f.write(f"  Compression: {file_info['compression_ratio']:.1f}x\n\n")
            
            FocusAwareMessageBox.information(self, "Export Complete", f"Analysis report exported to:\n{filename}")
            
        except Exception as e:
            FocusAwareMessageBox.critical(self, "Export Error", f"Failed to export report:\n{str(e)}")


class PerformanceResultsDialog(QDialog):
    """Dialog to display performance test results with export capabilities"""
    
    def __init__(self, performance_results, parent=None):
        super().__init__(parent)
        self.performance_results = performance_results
        self.setWindowTitle("Performance Test Results")
        self.setModal(True)
        self.resize(800, 500)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Summary section
        summary_group = QGroupBox("Performance Summary")
        summary_layout = QVBoxLayout(summary_group)
        
        results = self.performance_results
        avg_load_time = sum(r['load_time'] for r in results['files']) / len(results['files'])
        avg_pixel_time = sum(r['pixel_time'] for r in results['files']) / len(results['files'])
        avg_total_time = sum(r['total_time'] for r in results['files']) / len(results['files'])
        
        summary_text = f"""
        Files Tested: {len(results['files'])}
        Average Load Time: {avg_load_time:.3f}s
        Average Pixel Access Time: {avg_pixel_time:.3f}s
        Average Total Time: {avg_total_time:.3f}s
        Slow Files (>0.5s): {len(results['slow_files'])}
        Fastest File: {results['fastest_file']['filename']} ({results['fastest_file']['total_time']:.3f}s)
        Slowest File: {results['slowest_file']['filename']} ({results['slowest_file']['total_time']:.3f}s)
        """
        
        summary_label = QLabel(summary_text)
        summary_label.setFont(QFont("monospace"))
        summary_layout.addWidget(summary_label)
        layout.addWidget(summary_group)
        
        # Performance results table
        results_group = QGroupBox("Detailed Performance Results")
        results_layout = QVBoxLayout(results_group)
        
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(5)
        self.results_table.setHorizontalHeaderLabels([
            "Filename", "Load Time (s)", "Pixel Time (s)", "Total Time (s)", "Status"
        ])
        
        # Populate table (show slowest first)
        sorted_files = sorted(results['files'], key=lambda x: x['total_time'], reverse=True)
        self.results_table.setRowCount(len(sorted_files))
        
        for row, file_info in enumerate(sorted_files):
            self.results_table.setItem(row, 0, QTableWidgetItem(file_info['filename']))
            self.results_table.setItem(row, 1, QTableWidgetItem(f"{file_info['load_time']:.3f}"))
            self.results_table.setItem(row, 2, QTableWidgetItem(f"{file_info['pixel_time']:.3f}"))
            self.results_table.setItem(row, 3, QTableWidgetItem(f"{file_info['total_time']:.3f}"))
            
            # Status based on performance
            if file_info['total_time'] > 0.5:
                status = "Slow"
            elif file_info['total_time'] > 0.1:
                status = "Moderate"
            else:
                status = "Fast"
            self.results_table.setItem(row, 4, QTableWidgetItem(status))
        
        self.results_table.resizeColumnsToContents()
        results_layout.addWidget(self.results_table)
        layout.addWidget(results_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        export_csv_btn = QPushButton("Export CSV")
        export_csv_btn.clicked.connect(self.export_csv)
        
        export_report_btn = QPushButton("Export Report")
        export_report_btn.clicked.connect(self.export_report)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        
        button_layout.addWidget(export_csv_btn)
        button_layout.addWidget(export_report_btn)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
    
    def export_csv(self):
        """Export performance results to CSV"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Performance Results", "performance_results.csv", "CSV Files (*.csv)"
        )
        if not filename:
            return
            
        try:
            import csv
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header
                writer.writerow(["Filename", "Load Time (s)", "Pixel Time (s)", "Total Time (s)", "Status"])
                
                # Write data
                for file_info in self.performance_results['files']:
                    status = "Slow" if file_info['total_time'] > 0.5 else "Moderate" if file_info['total_time'] > 0.1 else "Fast"
                    writer.writerow([
                        file_info['filename'],
                        f"{file_info['load_time']:.3f}",
                        f"{file_info['pixel_time']:.3f}",
                        f"{file_info['total_time']:.3f}",
                        status
                    ])
            
            FocusAwareMessageBox.information(self, "Export Complete", f"Performance results exported to:\n{filename}")
            
        except Exception as e:
            FocusAwareMessageBox.critical(self, "Export Error", f"Failed to export CSV:\n{str(e)}")
    
    def export_report(self):
        """Export detailed performance report"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Performance Report", "performance_report.txt", "Text Files (*.txt)"
        )
        if not filename:
            return
            
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                results = self.performance_results
                
                f.write("DICOM PERFORMANCE TEST REPORT\n")
                f.write("=" * 40 + "\n\n")
                
                # Summary
                avg_load = sum(r['load_time'] for r in results['files']) / len(results['files'])
                avg_pixel = sum(r['pixel_time'] for r in results['files']) / len(results['files'])
                avg_total = sum(r['total_time'] for r in results['files']) / len(results['files'])
                
                f.write("PERFORMANCE SUMMARY\n")
                f.write("-" * 20 + "\n")
                f.write(f"Files Tested: {len(results['files'])}\n")
                f.write(f"Average Load Time: {avg_load:.3f}s\n")
                f.write(f"Average Pixel Time: {avg_pixel:.3f}s\n")
                f.write(f"Average Total Time: {avg_total:.3f}s\n")
                f.write(f"Slow Files (>0.5s): {len(results['slow_files'])}\n\n")
                
                # Slow files section
                if results['slow_files']:
                    f.write("SLOW FILES (>0.5s total time)\n")
                    f.write("-" * 30 + "\n")
                    for file_info in results['slow_files']:
                        f.write(f"  {file_info['filename']}: {file_info['total_time']:.3f}s\n")
                    f.write("\n")
                
                # Detailed results
                f.write("DETAILED PERFORMANCE RESULTS\n")
                f.write("-" * 30 + "\n")
                f.write(f"{'Filename':<30} {'Load':<8} {'Pixel':<8} {'Total':<8} {'Status'}\n")
                f.write("-" * 60 + "\n")
                
                sorted_files = sorted(results['files'], key=lambda x: x['total_time'], reverse=True)
                for file_info in sorted_files:
                    status = "Slow" if file_info['total_time'] > 0.5 else "Moderate" if file_info['total_time'] > 0.1 else "Fast"
                    f.write(f"{file_info['filename']:<30} {file_info['load_time']:<8.3f} {file_info['pixel_time']:<8.3f} {file_info['total_time']:<8.3f} {status}\n")
            
            FocusAwareMessageBox.information(self, "Export Complete", f"Performance report exported to:\n{filename}")
            
        except Exception as e:
            FocusAwareMessageBox.critical(self, "Export Error", f"Failed to export report:\n{str(e)}")

class LogViewerDialog(QDialog):
    """Live log viewer dialog with tail -f functionality"""
    
    def __init__(self, log_path, parent=None):
        super().__init__(parent)
        self.log_path = log_path
        self.file_position = 0
        self.is_paused = False
        self.auto_scroll = True
        
        self.setWindowTitle(f"Log Viewer - {os.path.basename(log_path)}")
        self.setModal(False)  # Non-modal so user can interact with main app
        self.resize(800, 600)
        
        self.setup_ui()
        self.setup_timer()
        self.load_initial_content()
        
    def setup_ui(self):
        """Setup the UI components"""
        layout = QVBoxLayout(self)
        
        # Toolbar
        toolbar_layout = QHBoxLayout()
        
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setCheckable(True)
        self.pause_btn.clicked.connect(self.toggle_pause)
        
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear_log_display)
        
        self.auto_scroll_cb = QCheckBox("Auto-scroll")
        self.auto_scroll_cb.setChecked(True)
        self.auto_scroll_cb.stateChanged.connect(self.toggle_auto_scroll)
        
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.force_refresh)
        
        self.copy_btn = QPushButton("Copy All")
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        
        toolbar_layout.addWidget(self.pause_btn)
        toolbar_layout.addWidget(self.clear_btn)
        toolbar_layout.addWidget(self.auto_scroll_cb)
        toolbar_layout.addWidget(self.refresh_btn)
        toolbar_layout.addWidget(self.copy_btn)
        toolbar_layout.addStretch()
        
        # Status label
        self.status_label = QLabel(f"Watching: {self.log_path}")
        self.status_label.setStyleSheet("QLabel { color: #888; font-size: 10px; }")
        
        # Log content area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("monospace", 9))
        
        # Set dark theme for log viewer
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a1a;
                color: #f0f0f0;
                border: 1px solid #444;
                selection-background-color: #0078d4;
            }
        """)
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        
        # Layout
        layout.addLayout(toolbar_layout)
        layout.addWidget(self.status_label)
        layout.addWidget(self.log_text)
        layout.addWidget(close_btn)
        
    def setup_timer(self):
        """Setup timer for periodic log updates"""
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_log_content)
        self.update_timer.start(1000)  # Update every 1 second
        
    def load_initial_content(self):
        """Load initial log content (last 1000 lines)"""
        try:
            if not os.path.exists(self.log_path):
                self.log_text.append(f"Log file does not exist: {self.log_path}")
                return
                
            with open(self.log_path, 'r', encoding='utf-8', errors='ignore') as f:
                # Read last 1000 lines
                lines = f.readlines()
                if len(lines) > 1000:
                    lines = lines[-1000:]
                    self.log_text.append("... (showing last 1000 lines) ...\n")
                
                content = ''.join(lines)
                self.log_text.append(content)
                
                # Set file position to end
                f.seek(0, 2)  # Seek to end
                self.file_position = f.tell()
                
            if self.auto_scroll:
                self.scroll_to_bottom()
                
        except Exception as e:
            self.log_text.append(f"Error reading log file: {e}")
            
    def update_log_content(self):
        """Update log content with new lines (tail -f behavior)"""
        if self.is_paused:
            return
            
        try:
            if not os.path.exists(self.log_path):
                return
                
            with open(self.log_path, 'r', encoding='utf-8', errors='ignore') as f:
                # Check if file was truncated (log rotation)
                f.seek(0, 2)  # Seek to end
                current_size = f.tell()
                
                if current_size < self.file_position:
                    # File was truncated, start from beginning
                    self.file_position = 0
                    self.log_text.append("\n--- Log file was rotated ---\n")
                
                # Read new content
                f.seek(self.file_position)
                new_content = f.read()
                
                if new_content:
                    # Color-code log levels
                    new_content = self.colorize_log_content(new_content)
                    self.log_text.append(new_content)
                    self.file_position = f.tell()
                    
                    if self.auto_scroll:
                        self.scroll_to_bottom()
                        
        except Exception as e:
            # Don't spam errors, just log once
            if not hasattr(self, '_error_logged'):
                self.log_text.append(f"Error updating log: {e}")
                self._error_logged = True
                
    def colorize_log_content(self, content):
        """Add basic color coding for log levels"""
        # This is basic - you could make it more sophisticated
        lines = content.split('\n')
        colored_lines = []
        
        for line in lines:
            if '[ERROR]' in line or '[CRITICAL]' in line:
                colored_lines.append(f'<span style="color: #ff6b6b;">{line}</span>')
            elif '[WARNING]' in line or '[WARN]' in line:
                colored_lines.append(f'<span style="color: #ffa500;">{line}</span>')
            elif '[INFO]' in line:
                colored_lines.append(f'<span style="color: #87ceeb;">{line}</span>')
            elif '[DEBUG]' in line:
                colored_lines.append(f'<span style="color: #98fb98;">{line}</span>')
            else:
                colored_lines.append(line)
        
        return '\n'.join(colored_lines)
    
    def scroll_to_bottom(self):
        """Scroll to bottom of log"""
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
    def toggle_pause(self, checked):
        """Toggle pause/resume log updates"""
        self.is_paused = checked
        self.pause_btn.setText("Resume" if checked else "Pause")
        
        if checked:
            self.status_label.setText(f"PAUSED - {self.log_path}")
            self.status_label.setStyleSheet("QLabel { color: #ff6b6b; font-size: 10px; }")
        else:
            self.status_label.setText(f"Watching: {self.log_path}")
            self.status_label.setStyleSheet("QLabel { color: #888; font-size: 10px; }")
            
    def toggle_auto_scroll(self, state):
        """Toggle auto-scroll feature"""
        self.auto_scroll = (state == Qt.CheckState.Checked.value)
        
    def clear_log_display(self):
        """Clear the log display (not the actual log file)"""
        self.log_text.clear()
        
    def force_refresh(self):
        """Force refresh the log content"""
        self.log_text.clear()
        self.file_position = 0
        self.load_initial_content()
        
    def copy_to_clipboard(self):
        """Copy all log content to clipboard"""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.log_text.toPlainText())
        
        # Brief status update
        original_text = self.status_label.text()
        self.status_label.setText("Copied to clipboard!")
        QTimer.singleShot(2000, lambda: self.status_label.setText(original_text))
        
    def closeEvent(self, event):
        """Clean up when closing"""
        # Close log viewer if open
        if hasattr(self, 'log_viewer') and self.log_viewer:
            self.log_viewer.close()
            
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()
        event.accept()

class SettingsEditorDialog(QDialog):
    """Dialog for editing application settings as YAML"""
    
    def __init__(self, config_data, config_file_path, parent=None):
        super().__init__(parent)
        self.config_data = config_data
        self.config_file_path = config_file_path
        self.setWindowTitle("Settings Editor")
        self.setModal(True)
        self.resize(800, 600)
        self.setup_ui()
        self.load_yaml_content()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Header with file path
        header_layout = QHBoxLayout()
        header_label = QLabel("Editing configuration file:")
        self.path_label = QLabel(self.config_file_path)
        self.path_label.setStyleSheet("font-family: monospace; color: #888;")
        header_layout.addWidget(header_label)
        header_layout.addWidget(self.path_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # YAML editor
        editor_group = QGroupBox("Configuration (YAML Format)")
        editor_layout = QVBoxLayout(editor_group)
        
        self.yaml_editor = QTextEdit()
        self.yaml_editor.setFont(QFont("monospace", 10))
        
        # Basic YAML syntax highlighting
        self._setup_syntax_highlighting()
        
        editor_layout.addWidget(self.yaml_editor)
        layout.addWidget(editor_group)
        
        # Validation status
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: green; font-weight: bold;")
        layout.addWidget(self.status_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        validate_btn = QPushButton("Validate YAML")
        validate_btn.clicked.connect(self.validate_yaml)
        
        reset_btn = QPushButton("Reset to Original")
        reset_btn.clicked.connect(self.load_yaml_content)
        
        save_btn = QPushButton("Save & Apply")
        save_btn.clicked.connect(self.save_and_apply)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(validate_btn)
        button_layout.addWidget(reset_btn)
        button_layout.addStretch()
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        
        # Auto-validate on text change (with delay)
        self.validation_timer = QTimer()
        self.validation_timer.setSingleShot(True)
        self.validation_timer.timeout.connect(self.validate_yaml_silent)
        self.yaml_editor.textChanged.connect(self._on_text_changed)
    
    def _setup_syntax_highlighting(self):
        """Setup basic YAML syntax highlighting"""
        try:
            # Simple YAML highlighting
            self.yaml_editor.setStyleSheet("""
                QTextEdit {
                    background-color: #2b2b2b;
                    color: #f8f8f2;
                    border: 1px solid #3c3c3c;
                    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                    font-size: 11px;
                    line-height: 1.4;
                }
            """)
        except Exception as e:
            logging.warning(f"Could not setup syntax highlighting: {e}")
    
    def load_yaml_content(self):
        """Load current configuration as YAML text"""
        try:
            yaml_content = yaml.dump(self.config_data, default_flow_style=False, sort_keys=False, allow_unicode=True)
            self.yaml_editor.setPlainText(yaml_content)
            self.status_label.setText("✅ Configuration loaded")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        except Exception as e:
            self.status_label.setText(f"❌ Error loading config: {e}")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
    
    def _on_text_changed(self):
        """Called when text changes - start validation timer"""
        self.validation_timer.stop()
        self.validation_timer.start(1000)  # Validate after 1 second of no typing
    
    def validate_yaml_silent(self):
        """Validate YAML without showing success message"""
        try:
            yaml_text = self.yaml_editor.toPlainText()
            yaml.safe_load(yaml_text)
            self.status_label.setText("✅ Valid YAML")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            return True
        except yaml.YAMLError as e:
            self.status_label.setText(f"❌ YAML Error: {str(e)}")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            return False
        except Exception as e:
            self.status_label.setText(f"❌ Parse Error: {str(e)}")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            return False
    
    def validate_yaml(self):
        """Validate YAML and show result"""
        if self.validate_yaml_silent():
            FocusAwareMessageBox.information(self, "Validation Success", "YAML syntax is valid!")
        else:
            FocusAwareMessageBox.warning(self, "Validation Failed", "Please fix the YAML syntax errors before saving.")
    
    def save_and_apply(self):
        """Save the YAML configuration and apply changes"""
        # Validate first
        if not self.validate_yaml_silent():
            reply = FocusAwareMessageBox.question(
                self, "Invalid YAML",
                "The YAML contains syntax errors. Save anyway?",
                FocusAwareMessageBox.StandardButton.Yes | FocusAwareMessageBox.StandardButton.No,
                FocusAwareMessageBox.StandardButton.No
            )
            if reply != FocusAwareMessageBox.StandardButton.Yes:
                return
        
        try:
            # Parse the YAML
            yaml_text = self.yaml_editor.toPlainText()
            new_config = yaml.safe_load(yaml_text)
            
            if new_config is None:
                new_config = {}
            
            # Validate required fields exist
            self._validate_config_structure(new_config)
            
            # Create backup of original file
            backup_path = self.config_file_path + ".backup"
            if os.path.exists(self.config_file_path):
                shutil.copy2(self.config_file_path, backup_path)
                logging.info(f"Created config backup: {backup_path}")
            
            # Ensure directory exists
            config_dir = os.path.dirname(self.config_file_path)
            os.makedirs(config_dir, exist_ok=True)
            
            # Save the new configuration
            with open(self.config_file_path, 'w', encoding='utf-8') as f:
                yaml.dump(new_config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            
            self.status_label.setText("✅ Configuration saved successfully!")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            
            # Return the new config for the parent to apply
            self.new_config = new_config
            
            FocusAwareMessageBox.information(
                self, "Settings Saved",
                f"Configuration saved successfully!\n\n"
                f"File: {self.config_file_path}\n"
                f"Backup: {backup_path}\n\n"
                "Some changes may require restarting the application."
            )
            
            self.accept()
            
        except Exception as e:
            logging.error(f"Failed to save configuration: {e}")
            FocusAwareMessageBox.critical(
                self, "Save Failed",
                f"Failed to save configuration:\n\n{str(e)}\n\n"
                f"Your changes have not been saved."
            )
    
    def _validate_config_structure(self, config):
        """Validate that required configuration keys exist"""
        required_keys = ['log_path', 'log_level', 'ae_title']
        missing_keys = []
        
        for key in required_keys:
            if key not in config or config[key] is None:
                missing_keys.append(key)
        
        if missing_keys:
            reply = FocusAwareMessageBox.question(
                self, "Missing Required Settings",
                f"The following required settings are missing or null:\n\n"
                f"{', '.join(missing_keys)}\n\n"
                f"This may cause the application to malfunction. Continue anyway?",
                FocusAwareMessageBox.StandardButton.Yes | FocusAwareMessageBox.StandardButton.No,
                FocusAwareMessageBox.StandardButton.No
            )
            if reply != FocusAwareMessageBox.StandardButton.Yes:
                raise ValueError(f"Missing required configuration keys: {missing_keys}")

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

class LazySelectionSummaryWidget(QWidget):
    """Widget showing real-time summary with lazy calculation"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._file_size_cache = {}  # Cache file sizes
        
    def _setup_ui(self):
        """Setup the summary UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # Create summary labels
        self.file_count_label = QLabel("Files: 0")
        self.size_label = QLabel("Size: 0 MB")
        self.breakdown_label = QLabel("Patients: 0, Studies: 0, Series: 0")
        
        # Style the labels
        font = QFont()
        font.setBold(True)
        for label in [self.file_count_label, self.size_label, self.breakdown_label]:
            label.setFont(font)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Add to layout
        layout.addWidget(self.file_count_label)
        layout.addWidget(self.size_label)
        layout.addWidget(self.breakdown_label)
        
        # Style the widget
        self.setStyleSheet("""
            QWidget {
                background-color: #2c2f33;
                border: 1px solid #444;
                border-radius: 5px;
            }
            QLabel {
                color: #f5f5f5;
                padding: 2px;
            }
        """)
    
    def update_summary(self, selected_files):
        """Update summary with lazy calculation"""
        if not selected_files:
            self.file_count_label.setText("Files: 0")
            self.size_label.setText("Size: 0 MB")
            self.breakdown_label.setText("Patients: 0, Studies: 0, Series: 0")
            return
        
        # Just show file count immediately
        file_count = len(selected_files)
        self.file_count_label.setText(f"Files: {file_count}")
        
        # Calculate size from cache or estimate
        total_size = 0
        for file_path in selected_files:
            if file_path in self._file_size_cache:
                total_size += self._file_size_cache[file_path]
            elif os.path.exists(file_path):
                try:
                    size = os.path.getsize(file_path)
                    self._file_size_cache[file_path] = size
                    total_size += size
                except:
                    # Estimate 500KB per file if can't read
                    total_size += 500 * 1024
        
        # Format size
        if total_size < 1024 * 1024:  # Less than 1MB
            size_str = f"{total_size / 1024:.1f} KB"
        elif total_size < 1024 * 1024 * 1024:  # Less than 1GB
            size_str = f"{total_size / (1024 * 1024):.1f} MB"
        else:
            size_str = f"{total_size / (1024 * 1024 * 1024):.2f} GB"
        
        self.size_label.setText(f"Size: {size_str}")
        
        # Simplified breakdown - just estimate from file paths
        # This avoids reading DICOM headers
        unique_patients = set()
        unique_studies = set()
        unique_series = set()
        
        for file_path in selected_files:
            # Extract IDs from file path or use simple heuristics
            path_parts = file_path.split(os.sep)
            if len(path_parts) >= 3:
                unique_patients.add(path_parts[-3] if len(path_parts) > 3 else "patient1")
                unique_studies.add(path_parts[-2] if len(path_parts) > 2 else "study1")
                unique_series.add(path_parts[-1] if len(path_parts) > 1 else "series1")
        
        self.breakdown_label.setText(f"Est. Patients: {len(unique_patients)}, Studies: {len(unique_studies)}, Series: {len(unique_series)}")

class DicomSendSelectionDialog(QDialog):
    """Dialog for selecting files to send via DICOM with hierarchical checkboxes"""
    
    def __init__(self, loaded_files, initial_selection_items, parent=None):
        super().__init__(parent)
        
        # Store references
        self.loaded_files = loaded_files  # Now this will work
        self.initial_selection_items = initial_selection_items
        self.selected_files = []
        
        # Add some debug logging
        logging.info(f"DicomSendSelectionDialog initialized with {len(self.loaded_files)} loaded files")
        
        self.setWindowTitle("Select Files for DICOM Send")
        self.setModal(True)
        self.resize(600, 500)
        
        # Now call the setup methods
        self._setup_ui()
        self._populate_tree()
        self._set_initial_selection()
        
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
        
        # Build hierarchy from loaded files
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
        
        # Populate tree widget with proper checkbox setup
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
                    
                    # Calculate series size
                    series_size = sum(os.path.getsize(fp) for fp in instances.values() if os.path.exists(fp))
                    series_size_mb = series_size / (1024 * 1024)
                    
                    series_item.setText(1, str(series_file_count))
                    series_item.setText(2, f"{series_size_mb:.1f}MB")
                    
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
        
        # Expand tree by default
        self.tree_widget.expandAll()
        
        logging.info(f"Populated tree with {len(hierarchy)} patients")
    
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
        
        # Show results dialog
        dialog = FileAnalysisResultsDialog(analysis_results, self)
        dialog.exec()

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
        
        # Show results dialog
        dialog = PerformanceResultsDialog(performance_results, self)
        dialog.exec()

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