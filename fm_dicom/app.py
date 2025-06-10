from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog,
    QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem, QMessageBox, QLineEdit, QInputDialog, QComboBox, QLabel, QCheckBox, QSizePolicy, QSplitter,
    QDialog, QFormLayout, QDialogButtonBox, QProgressDialog,
    QApplication, QToolBar, QGroupBox, QFrame, QStatusBar, QStyle, QMenu,
    QGridLayout, QRadioButton, QButtonGroup, QProgressBar
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

from pynetdicom import AE, AllStoragePresentationContexts
from pynetdicom.sop_class import Verification
VERIFICATION_SOP_CLASS = Verification
STORAGE_CONTEXTS = AllStoragePresentationContexts


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


class ZipExtractionWorker(QThread):
    """Worker thread for ZIP extraction with progress updates"""
    progress_updated = pyqtSignal(int, int, str)  # current, total, filename
    extraction_complete = pyqtSignal(str, list)  # temp_dir, extracted_files
    extraction_failed = pyqtSignal(str)  # error_message
    
    def __init__(self, zip_path, temp_dir):
        super().__init__()
        self.zip_path = zip_path
        self.temp_dir = temp_dir
        
    def run(self):
        try:
            with zipfile.ZipFile(self.zip_path, 'r') as zip_ref:
                file_list = zip_ref.namelist()
                total_files = len(file_list)
                extracted_files = []
                
                for i, filename in enumerate(file_list):
                    # Emit progress update
                    self.progress_updated.emit(i + 1, total_files, filename)
                    
                    # Extract individual file
                    zip_ref.extract(filename, self.temp_dir)
                    extracted_path = os.path.join(self.temp_dir, filename)
                    extracted_files.append(extracted_path)
                    
                    # Allow thread to be interrupted
                    if self.isInterruptionRequested():
                        break
                        
                self.extraction_complete.emit(self.temp_dir, extracted_files)
                
        except Exception as e:
            error_msg = f"Failed to extract ZIP file: {str(e)}"
            self.extraction_failed.emit(error_msg)

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
        QMessageBox.critical(self, "Extraction Error", error_message)
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

class DicomdirReader:
    """Reader for DICOMDIR files"""
    
    def __init__(self):
        self.dicomdir_path = None
        self.base_directory = None
        
    def find_dicomdir(self, search_path):
        """Recursively search for DICOMDIR files"""
        dicomdir_files = []
        
        for root, dirs, files in os.walk(search_path):
            for file in files:
                if file.upper() == 'DICOMDIR':
                    dicomdir_path = os.path.join(root, file)
                    dicomdir_files.append(dicomdir_path)
                    
        return dicomdir_files
        
    def read_dicomdir(self, dicomdir_path):
        """Read DICOMDIR and extract file references"""
        try:
            self.dicomdir_path = dicomdir_path
            self.base_directory = os.path.dirname(dicomdir_path)
            
            # Read the DICOMDIR file
            ds = pydicom.dcmread(dicomdir_path)
            
            # Extract file references from directory records
            file_paths = []
            
            if hasattr(ds, 'DirectoryRecordSequence'):
                for record in ds.DirectoryRecordSequence:
                    file_path = self._extract_file_path(record)
                    if file_path:
                        file_paths.append(file_path)
                        
            return file_paths
            
        except Exception as e:
            logging.error(f"Failed to read DICOMDIR {dicomdir_path}: {e}")
            return []
            
    def _extract_file_path(self, record):
        """Extract file path from a directory record"""
        try:
            # Check if this is an IMAGE record (actual DICOM file)
            if hasattr(record, 'DirectoryRecordType') and record.DirectoryRecordType == 'IMAGE':
                # Get the referenced file ID
                if hasattr(record, 'ReferencedFileID'):
                    file_id = record.ReferencedFileID
                    
                    # Convert file ID to actual path
                    # DICOM file IDs are typically arrays of path components
                    # Handle both regular lists/tuples AND pydicom MultiValue objects
                    if hasattr(file_id, '__iter__') and not isinstance(file_id, str):
                        # Join the path components (works for lists, tuples, and MultiValue)
                        relative_path = os.path.join(*file_id)
                        logging.debug(f"DEBUG: Joined path components {list(file_id)} -> {relative_path}")
                    else:
                        relative_path = str(file_id)
                        logging.debug(f"DEBUG: Used string conversion: {relative_path}")
                    
                    # Convert to absolute path
                    full_path = os.path.join(self.base_directory, relative_path)
                    
                    # Normalize path separators for current OS
                    full_path = os.path.normpath(full_path)
                    
                    logging.debug(f"DEBUG: Final path: {full_path}")
                    
                    # Check if file exists
                    if os.path.exists(full_path):
                        return full_path
                    else:
                        logging.warning(f"DICOMDIR references missing file: {full_path}")
                        
        except Exception as e:
            logging.warning(f"Failed to extract file path from directory record: {e}")
            
        return None

class DicomdirScanWorker(QThread):
    """Worker thread for scanning DICOMDIR files"""
    progress_updated = pyqtSignal(int, int, str)  # current, total, current_file
    scan_complete = pyqtSignal(list)  # list of DICOM file paths
    scan_failed = pyqtSignal(str)  # error message
    
    def __init__(self, extracted_files):
        super().__init__()
        self.extracted_files = extracted_files
        
    def run(self):
        try:
            # First, find all DICOMDIR files
            dicomdir_files = []
            for file_path in self.extracted_files:
                if os.path.basename(file_path).upper() == 'DICOMDIR':
                    dicomdir_files.append(file_path)
                    
            if not dicomdir_files:
                self.scan_failed.emit("No DICOMDIR files found in extracted archive")
                return
                
            # Process each DICOMDIR
            all_dicom_files = []
            reader = DicomdirReader()
            
            for idx, dicomdir_path in enumerate(dicomdir_files):
                self.progress_updated.emit(idx + 1, len(dicomdir_files), 
                                         f"Reading {os.path.basename(dicomdir_path)}")
                
                file_paths = reader.read_dicomdir(dicomdir_path)
                all_dicom_files.extend(file_paths)
                
                if self.isInterruptionRequested():
                    break
                    
            # Remove duplicates and verify files exist
            unique_files = []
            seen_files = set()
            
            for file_path in all_dicom_files:
                if file_path not in seen_files and os.path.exists(file_path):
                    unique_files.append(file_path)
                    seen_files.add(file_path)
                    
            self.scan_complete.emit(unique_files)
            
        except Exception as e:
            self.scan_failed.emit(f"DICOMDIR scanning failed: {str(e)}")

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


class DicomSendWorker(QThread):
    """Background worker for DICOM sending with auto-conversion on format rejection"""
    progress_updated = pyqtSignal(int, int, int, int, str)  # current, success, warnings, failed, current_file
    send_complete = pyqtSignal(int, int, int, list, int)  # success, warnings, failed, error_details, converted_count
    send_failed = pyqtSignal(str)  # error message
    association_status = pyqtSignal(str)  # status messages
    conversion_progress = pyqtSignal(int, int, str)  # current, total, filename
    
    def __init__(self, filepaths, send_params, unique_sop_classes):
        super().__init__()
        self.filepaths = filepaths
        self.calling_ae, self.remote_ae, self.host, self.port = send_params
        self.unique_sop_classes = unique_sop_classes
        self.cancelled = False
        self.temp_files = []  # Track temp files for cleanup
        self.converted_count = 0
        
    def run(self):
        try:
            logging.info("DicomSendWorker: Starting run() method")
            
            # First attempt: try with original formats
            self.association_status.emit("Testing server compatibility...")
            logging.info("DicomSendWorker: About to attempt initial send")
            
            result = self._attempt_send_with_formats(self.filepaths, test_mode=True)
            logging.info(f"DicomSendWorker: Initial send result: {result is not None}")
            
            if result is None:  # Cancelled
                logging.info("DicomSendWorker: Send was cancelled")
                return
                
            success, warnings, failed, error_details, incompatible_files = result
            logging.info(f"DicomSendWorker: Initial results - Success: {success}, Failed: {failed}, Incompatible: {len(incompatible_files)}")
            
            # If some files failed due to format issues, try converting them
            if incompatible_files:
                logging.info(f"DicomSendWorker: Converting {len(incompatible_files)} incompatible files")
                self.association_status.emit(f"Converting {len(incompatible_files)} incompatible files...")
                converted_files = self._convert_incompatible_files(incompatible_files)
                logging.info(f"DicomSendWorker: Conversion complete, got {len(converted_files)} converted files")
                
                if converted_files and not self.cancelled:
                    # Retry with converted files
                    logging.info("DicomSendWorker: Retrying with converted files")
                    self.association_status.emit("Retrying with converted files...")
                    retry_result = self._attempt_send_with_formats(converted_files, test_mode=False)
                    
                    if retry_result:
                        retry_success, retry_warnings, retry_failed, retry_errors, _ = retry_result
                        success += retry_success
                        warnings += retry_warnings
                        failed += retry_failed
                        error_details.extend(retry_errors)
                        logging.info(f"DicomSendWorker: Retry complete - Total success: {success}")
            
            logging.info("DicomSendWorker: About to emit send_complete signal")
            # Send completion signal
            self.send_complete.emit(success, warnings, failed, error_details, self.converted_count)
            logging.info("DicomSendWorker: send_complete signal emitted")
            
        except Exception as e:
            logging.error(f"DicomSendWorker: Exception in run(): {e}", exc_info=True)
            self.send_failed.emit(f"DICOM send failed: {str(e)}")
        finally:
            logging.info("DicomSendWorker: Cleaning up temp files")
            # Cleanup temp files
            self._cleanup_temp_files()
            logging.info("DicomSendWorker: run() method complete")
    
    def _attempt_send_with_formats(self, filepaths, test_mode=False):
        """Attempt to send files and identify format incompatibilities"""
        try:
            logging.info(f"DicomSendWorker: _attempt_send_with_formats called with {len(filepaths)} files, test_mode={test_mode}")
            
            # Create AE instance
            ae_instance = AE(ae_title=self.calling_ae)
            logging.info("DicomSendWorker: Created AE instance")
            
            # Add presentation contexts
            for sop_uid in self.unique_sop_classes:
                ae_instance.add_requested_context(sop_uid)
            ae_instance.add_requested_context(VERIFICATION_SOP_CLASS)
            logging.info(f"DicomSendWorker: Added {len(self.unique_sop_classes)} presentation contexts")
            
            # Establish association
            if test_mode:
                self.association_status.emit("Testing server compatibility...")
            else:
                self.association_status.emit("Sending files to server...")
            
            logging.info(f"DicomSendWorker: Attempting association to {self.host}:{self.port}")
            assoc = ae_instance.associate(self.host, self.port, ae_title=self.remote_ae)
            
            if not assoc.is_established:
                logging.error(f"DicomSendWorker: Association failed: {assoc}")
                if test_mode:
                    self.send_failed.emit(f"Failed to establish association with {self.host}:{self.port}")
                    return None
                else:
                    return 0, 0, len(filepaths), [f"Association failed for all {len(filepaths)} files"], []
            
            logging.info("DicomSendWorker: Association established successfully")
            
            # Set timeout
            assoc.dimse_timeout = 120
            
            # C-ECHO verification
            logging.info("DicomSendWorker: Performing C-ECHO")
            echo_status = assoc.send_c_echo()
            if echo_status and getattr(echo_status, 'Status', None) == 0x0000:
                logging.info("DicomSendWorker: C-ECHO verification successful.")
            else:
                logging.warning(f"DicomSendWorker: C-ECHO failed or status not 0x0000. Status: {echo_status}")
            
            # Send files
            logging.info(f"DicomSendWorker: Starting to send {len(filepaths)} files")
            sent_ok = 0
            sent_warning = 0
            failed_send = 0
            failed_details_list = []
            incompatible_files = []
            
            for idx, fp_send in enumerate(filepaths):
                if self.cancelled:
                    break
                
                try:
                    # Check association
                    if not assoc.is_established:
                        assoc = ae_instance.associate(self.host, self.port, ae_title=self.remote_ae)
                        if not assoc.is_established:
                            failed_details_list.append(f"{os.path.basename(fp_send)}: Could not re-establish association")
                            failed_send += 1
                            continue
                        assoc.dimse_timeout = 120
                    
                    # Read file
                    ds_send = pydicom.dcmread(fp_send)
                    
                    # Check SOP class support
                    if not any(ctx.abstract_syntax == ds_send.SOPClassUID and ctx.result == 0x00 for ctx in assoc.accepted_contexts):
                        err_msg = f"{os.path.basename(fp_send)}: SOP Class not accepted"
                        failed_details_list.append(err_msg)
                        failed_send += 1
                        
                        # This might be a format issue - add to incompatible list
                        if test_mode:
                            incompatible_files.append(fp_send)
                        
                        # UPDATE PROGRESS EVEN IN TEST MODE
                        if test_mode:
                            self.progress_updated.emit(idx + 1, sent_ok, sent_warning, failed_send, f"Testing {os.path.basename(fp_send)}")
                        else:
                            self.progress_updated.emit(idx + 1, sent_ok, sent_warning, failed_send, os.path.basename(fp_send))
                        continue
                    
                    # Send C-STORE
                    status = assoc.send_c_store(ds_send)
                    
                    # Process result
                    if status:
                        status_code = getattr(status, "Status", -1)
                        if status_code == 0x0000:
                            sent_ok += 1
                            logging.info(f"Successfully sent {os.path.basename(fp_send)}")
                        elif status_code in [0xB000, 0xB006, 0xB007]:
                            sent_warning += 1
                            warn_msg = f"{os.path.basename(fp_send)}: Warning 0x{status_code:04X}"
                            failed_details_list.append(warn_msg)
                        else:
                            failed_send += 1
                            err_msg = f"{os.path.basename(fp_send)}: Failed 0x{status_code:04X}"
                            failed_details_list.append(err_msg)
                            
                            # Check if this is a format-related failure
                            if test_mode and self._is_format_error(status_code):
                                incompatible_files.append(fp_send)
                    else:
                        failed_send += 1
                        failed_details_list.append(f"{os.path.basename(fp_send)}: No status returned")
                        if test_mode:
                            incompatible_files.append(fp_send)
                    
                    # UPDATE PROGRESS FOR BOTH TEST AND NORMAL MODE
                    if test_mode:
                        self.progress_updated.emit(idx + 1, sent_ok, sent_warning, failed_send, f"Testing {os.path.basename(fp_send)}")
                    else:
                        self.progress_updated.emit(idx + 1, sent_ok, sent_warning, failed_send, os.path.basename(fp_send))
                    
                except Exception as e:
                    error_str = str(e)
                    failed_send += 1
                    err_msg = f"{os.path.basename(fp_send)}: {error_str}"
                    failed_details_list.append(err_msg)
                    
                    # Check if this is a format/compression error
                    if test_mode and self._is_format_exception(error_str):
                        incompatible_files.append(fp_send)
                        logging.info(f"Detected format incompatibility for {os.path.basename(fp_send)}: {error_str}")
                    
                    # UPDATE PROGRESS FOR BOTH TEST AND NORMAL MODE
                    if test_mode:
                        self.progress_updated.emit(idx + 1, sent_ok, sent_warning, failed_send, f"Testing {os.path.basename(fp_send)}")
                    else:
                        self.progress_updated.emit(idx + 1, sent_ok, sent_warning, failed_send, os.path.basename(fp_send))
            
            # Close association
            try:
                assoc.release()
            except:
                pass
            
            return sent_ok, sent_warning, failed_send, failed_details_list, incompatible_files
            
        except Exception as e:
            logging.error(f"DicomSendWorker: Exception in _attempt_send_with_formats: {e}", exc_info=True)
            raise
    
    def _is_format_error(self, status_code):
        """Check if status code indicates a format/transfer syntax error"""
        # Common DICOM status codes for format/transfer syntax issues
        format_error_codes = [
            0x0122,  # SOP Class not supported
            0x0124,  # Not authorized
            0xA900,  # Dataset does not match SOP Class
            0xC000,  # Cannot understand
        ]
        return status_code in format_error_codes
    
    def _is_format_exception(self, error_str):
        """Check if exception indicates a format/compression issue"""
        format_keywords = [
            'presentation context',
            'transfer syntax',
            'compression',
            'jpeg',
            'jpeg2000',
            'not accepted',
            'not supported',
            'cannot decompress',
            'no suitable presentation context'
        ]
        error_lower = error_str.lower()
        return any(keyword in error_lower for keyword in format_keywords)
    
    def _convert_incompatible_files(self, filepaths):
        """Convert incompatible files to standard uncompressed format with validation"""
        converted_files = []
        total_files = len(filepaths)
        
        for idx, filepath in enumerate(filepaths):
            if self.cancelled:
                break
            
            # Emit conversion progress
            self.conversion_progress.emit(idx, total_files, os.path.basename(filepath))
            
            try:
                # Read original file
                ds_original = pydicom.dcmread(filepath)
                original_ts = str(ds_original.file_meta.TransferSyntaxUID)
                
                # Check if conversion is needed
                compressed_syntaxes = [
                    '1.2.840.10008.1.2.4.90',  # JPEG 2000 Lossless
                    '1.2.840.10008.1.2.4.91',  # JPEG 2000
                    '1.2.840.10008.1.2.4.50',  # JPEG Baseline
                    '1.2.840.10008.1.2.4.51',  # JPEG Extended
                    '1.2.840.10008.1.2.4.57',  # JPEG Lossless
                    '1.2.840.10008.1.2.4.70',  # JPEG Lossless SV1
                    '1.2.840.10008.1.2.4.80',  # JPEG-LS Lossless
                    '1.2.840.10008.1.2.4.81',  # JPEG-LS Lossy
                ]
                
                if original_ts not in compressed_syntaxes:
                    # No conversion needed
                    logging.info(f"No conversion needed for {os.path.basename(filepath)}: {original_ts}")
                    converted_files.append(filepath)
                    continue
                
                logging.info(f"Converting {os.path.basename(filepath)} from {original_ts}")
                
                # Create new dataset for conversion
                ds_converted = pydicom.Dataset()
                
                # Copy all non-pixel data elements
                for elem in ds_original:
                    if elem.tag != (0x7fe0, 0x0010):  # Skip PixelData for now
                        ds_converted[elem.tag] = elem
                
                # Handle pixel data conversion
                try:
                    # Force decompression by accessing pixel_array
                    pixel_array = ds_original.pixel_array
                    logging.info(f"Pixel array shape: {pixel_array.shape}, dtype: {pixel_array.dtype}")
                    
                    # Convert pixel array back to bytes in the correct format
                    if pixel_array.dtype != np.uint16 and ds_original.BitsAllocated == 16:
                        # Convert to uint16 if needed
                        pixel_array = pixel_array.astype(np.uint16)
                    elif pixel_array.dtype != np.uint8 and ds_original.BitsAllocated == 8:
                        # Convert to uint8 if needed
                        pixel_array = pixel_array.astype(np.uint8)
                    
                    # Convert back to bytes
                    pixel_bytes = pixel_array.tobytes()
                    
                    # Set the uncompressed pixel data
                    ds_converted.PixelData = pixel_bytes
                    
                    logging.info(f"Converted pixel data: {len(pixel_bytes)} bytes")
                    
                except Exception as e:
                    logging.error(f"Failed to convert pixel data for {filepath}: {e}")
                    converted_files.append(filepath)  # Use original
                    continue
                
                # Create proper file meta information for uncompressed format
                file_meta = pydicom.Dataset()
                
                # Copy essential file meta elements
                if hasattr(ds_original, 'file_meta'):
                    for elem in ds_original.file_meta:
                        if elem.tag != (0x0002, 0x0010):  # Skip TransferSyntaxUID
                            file_meta[elem.tag] = elem
                
                # Set transfer syntax to Explicit VR Little Endian (most compatible)
                file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
                file_meta.MediaStorageSOPClassUID = ds_converted.SOPClassUID
                file_meta.MediaStorageSOPInstanceUID = ds_converted.SOPInstanceUID
                
                # Ensure required file meta elements
                if not hasattr(file_meta, 'FileMetaInformationVersion'):
                    file_meta.FileMetaInformationVersion = b'\x00\x01'
                if not hasattr(file_meta, 'ImplementationClassUID'):
                    file_meta.ImplementationClassUID = pydicom.uid.PYDICOM_IMPLEMENTATION_UID
                if not hasattr(file_meta, 'ImplementationVersionName'):
                    file_meta.ImplementationVersionName = 'PYDICOM ' + pydicom.__version__
                
                # Assign file meta to dataset
                ds_converted.file_meta = file_meta
                
                # Update transfer syntax related elements in main dataset
                ds_converted.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
                
                # Create temp file
                temp_filepath = filepath + "_converted_explicit_vr.dcm"
                
                # Save the converted file
                ds_converted.save_as(temp_filepath, enforce_file_format=True)
                
                # Validate the converted file
                if self._validate_converted_file(temp_filepath, filepath):
                    converted_files.append(temp_filepath)
                    self.temp_files.append(temp_filepath)
                    self.converted_count += 1
                    logging.info(f"Successfully converted and validated {os.path.basename(filepath)}")
                else:
                    logging.warning(f"Converted file failed validation: {os.path.basename(filepath)}")
                    # Clean up failed conversion
                    try:
                        os.remove(temp_filepath)
                    except:
                        pass
                    converted_files.append(filepath)  # Use original
                    
            except Exception as e:
                logging.error(f"Failed to convert {filepath}: {e}", exc_info=True)
                converted_files.append(filepath)  # Use original
        
        # Signal conversion complete
        self.conversion_progress.emit(total_files, total_files, "Conversion complete")
        
        return converted_files

    def _validate_converted_file(self, converted_path, original_path):
        """Validate that the converted file is readable and has correct pixel data"""
        try:
            # Read the converted file
            ds_converted = pydicom.dcmread(converted_path)
            ds_original = pydicom.dcmread(original_path)
            
            # Check basic DICOM validity
            if not hasattr(ds_converted, 'SOPInstanceUID'):
                logging.error("Converted file missing SOPInstanceUID")
                return False
            
            # Check transfer syntax
            converted_ts = str(ds_converted.file_meta.TransferSyntaxUID)
            if converted_ts != pydicom.uid.ExplicitVRLittleEndian:
                logging.error(f"Converted file has wrong transfer syntax: {converted_ts}")
                return False
            
            # Check pixel data accessibility
            try:
                pixel_array_converted = ds_converted.pixel_array
                pixel_array_original = ds_original.pixel_array
                
                # Check dimensions match
                if pixel_array_converted.shape != pixel_array_original.shape:
                    logging.error(f"Pixel array shapes don't match: {pixel_array_converted.shape} vs {pixel_array_original.shape}")
                    return False
                
                # Check data types are reasonable
                if pixel_array_converted.dtype not in [np.uint8, np.uint16, np.int16]:
                    logging.error(f"Unexpected pixel data type: {pixel_array_converted.dtype}")
                    return False
                
                logging.info(f"Validation passed: {pixel_array_converted.shape}, {pixel_array_converted.dtype}")
                return True
                
            except Exception as e:
                logging.error(f"Cannot access pixel data in converted file: {e}")
                return False
                
        except Exception as e:
            logging.error(f"Cannot read converted file {converted_path}: {e}")
            return False
    
    def _cleanup_temp_files(self):
        """Clean up temporary files"""
        for temp_file in self.temp_files:
            try:
                os.remove(temp_file)
                logging.info(f"Cleaned up temp file: {os.path.basename(temp_file)}")
            except Exception as e:
                logging.warning(f"Could not remove temp file {temp_file}: {e}")
    
    def cancel(self):
        """Cancel the sending operation"""
        self.cancelled = True

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

class DicomPathGenerator:
    """Generate DICOM standard file paths and structure"""
    
    @staticmethod
    def generate_paths(filepaths):
        """
        Generate DICOM standard file paths from input files
        Returns: dict mapping {original_path: "DICOM/PAT00001/STU00001/SER00001/IMG00001"}
        """
        logging.info(f"Generating DICOM standard paths for {len(filepaths)} files")
        
        # Analyze files to build hierarchy
        hierarchy = {}
        
        for filepath in filepaths:
            try:
                ds = pydicom.dcmread(filepath, stop_before_pixels=True)
                
                patient_id = str(getattr(ds, 'PatientID', 'UNKNOWN'))
                patient_name = str(getattr(ds, 'PatientName', 'UNKNOWN'))
                study_uid = str(getattr(ds, 'StudyInstanceUID', 'UNKNOWN'))
                study_desc = str(getattr(ds, 'StudyDescription', 'UNKNOWN'))
                series_uid = str(getattr(ds, 'SeriesInstanceUID', 'UNKNOWN'))
                series_desc = str(getattr(ds, 'SeriesDescription', 'UNKNOWN'))
                instance_uid = str(getattr(ds, 'SOPInstanceUID', 'UNKNOWN'))
                instance_number = getattr(ds, 'InstanceNumber', 1)
                
                # Create hierarchy key
                patient_key = f"{patient_id}^{patient_name}"
                study_key = f"{study_uid}^{study_desc}"
                series_key = f"{series_uid}^{series_desc}"
                
                # Build hierarchy
                if patient_key not in hierarchy:
                    hierarchy[patient_key] = {}
                if study_key not in hierarchy[patient_key]:
                    hierarchy[patient_key][study_key] = {}
                if series_key not in hierarchy[patient_key][study_key]:
                    hierarchy[patient_key][study_key][series_key] = []
                
                hierarchy[patient_key][study_key][series_key].append({
                    'filepath': filepath,
                    'instance_uid': instance_uid,
                    'instance_number': instance_number
                })
                
            except Exception as e:
                logging.warning(f"Could not read DICOM file {filepath}: {e}")
                continue
        
        # Generate sequential IDs and paths
        file_mapping = {}
        patient_counter = 1
        
        for patient_key, studies in hierarchy.items():
            patient_dir = f"PAT{patient_counter:05d}"
            study_counter = 1
            
            for study_key, series_dict in studies.items():
                study_dir = f"STU{study_counter:05d}"
                series_counter = 1
                
                for series_key, instances in series_dict.items():
                    series_dir = f"SER{series_counter:05d}"
                    
                    # Sort instances by instance number
                    instances.sort(key=lambda x: x['instance_number'])
                    
                    for instance_idx, instance_info in enumerate(instances):
                        instance_file = f"IMG{instance_idx + 1:05d}"
                        
                        dicom_path = f"DICOM/{patient_dir}/{study_dir}/{series_dir}/{instance_file}"
                        file_mapping[instance_info['filepath']] = dicom_path
                    
                    series_counter += 1
                study_counter += 1
            patient_counter += 1
        
        logging.info(f"Generated {len(file_mapping)} DICOM standard paths")
        return file_mapping


class DicomdirBuilder:
    """Build valid DICOMDIR files using DICOM standard"""
    
    def __init__(self, file_set_id="DICOM_EXPORT"):
        self.file_set_id = file_set_id
        self.patients = {}
        self.studies = {}
        self.series = {}
        self.images = []

    def debug_dicomdir_structure(self, file_mapping):
        """Debug the DICOMDIR structure to see what patients/studies/series we have"""
        
        logging.info("=== DICOMDIR STRUCTURE DEBUG ===")
        
        # Analyze the original files to see patient distribution
        patient_analysis = {}
        
        for original_path, copied_path in file_mapping.items():
            try:
                ds = pydicom.dcmread(original_path, stop_before_pixels=True)
                patient_id = str(getattr(ds, 'PatientID', 'UNKNOWN'))
                patient_name = str(getattr(ds, 'PatientName', 'UNKNOWN'))
                study_uid = str(getattr(ds, 'StudyInstanceUID', 'UNKNOWN'))
                
                if patient_id not in patient_analysis:
                    patient_analysis[patient_id] = {
                        'name': patient_name,
                        'studies': set(),
                        'file_count': 0
                    }
                
                patient_analysis[patient_id]['studies'].add(study_uid)
                patient_analysis[patient_id]['file_count'] += 1
                
            except Exception as e:
                logging.warning(f"Could not analyze file {original_path}: {e}")
        
        logging.info(f"Found {len(patient_analysis)} unique patients in source files:")
        for patient_id, info in patient_analysis.items():
            logging.info(f"  Patient '{patient_id}' ({info['name']}): {info['file_count']} files, {len(info['studies'])} studies")
        
        # Now check our internal structure
        logging.info(f"DicomdirBuilder internal structure:")
        logging.info(f"  Patients: {len(self.patients)}")
        for patient_id, patient_info in self.patients.items():
            study_count = len(patient_info.get('studies', []))
            logging.info(f"    Patient '{patient_id}': {study_count} studies")
        
        logging.info(f"  Studies: {len(self.studies)}")
        logging.info(f"  Series: {len(self.series)}")
        logging.info(f"  Images: {len(self.images)}")
        
        logging.info("=== END DEBUG ===")
        
    def add_dicom_files(self, file_mapping):
        """
        Analyze copied files and build directory structure
        file_mapping: dict of {original_path: copied_path}
        """
        logging.info(f"Building DICOMDIR structure for {len(file_mapping)} files")
        
        # Reset structures to avoid accumulation from previous calls
        self.patients = {}
        self.studies = {}
        self.series = {}
        self.images = []
        
        for original_path, copied_path in file_mapping.items():
            try:
                ds = pydicom.dcmread(original_path, stop_before_pixels=True)
                
                # Extract metadata with proper defaults
                patient_id = str(getattr(ds, 'PatientID', 'UNKNOWN'))
                patient_name = str(getattr(ds, 'PatientName', 'UNKNOWN'))
                study_uid = str(getattr(ds, 'StudyInstanceUID', generate_uid()))
                study_desc = str(getattr(ds, 'StudyDescription', ''))
                study_date = str(getattr(ds, 'StudyDate', ''))
                study_time = str(getattr(ds, 'StudyTime', ''))
                study_id = str(getattr(ds, 'StudyID', ''))
                series_uid = str(getattr(ds, 'SeriesInstanceUID', generate_uid()))
                series_desc = str(getattr(ds, 'SeriesDescription', ''))
                series_number = str(getattr(ds, 'SeriesNumber', '1'))
                modality = str(getattr(ds, 'Modality', 'OT'))
                sop_class_uid = str(getattr(ds, 'SOPClassUID', ''))
                sop_instance_uid = str(getattr(ds, 'SOPInstanceUID', generate_uid()))
                transfer_syntax = str(getattr(ds.file_meta, 'TransferSyntaxUID', '1.2.840.10008.1.2'))
                instance_number = str(getattr(ds, 'InstanceNumber', '1'))
                
                logging.debug(f"Processing file: PatientID='{patient_id}', StudyUID='{study_uid[:8]}...', SeriesUID='{series_uid[:8]}...'")
                
                # Store patient info (create if doesn't exist)
                if patient_id not in self.patients:
                    self.patients[patient_id] = {
                        'PatientID': patient_id,
                        'PatientName': patient_name,
                        'studies': []
                    }
                    logging.debug(f"Created new patient: {patient_id}")
                
                # Store study info (create if doesn't exist)
                study_key = f"{patient_id}#{study_uid}"
                if study_key not in self.studies:
                    self.studies[study_key] = {
                        'StudyInstanceUID': study_uid,
                        'StudyDescription': study_desc,
                        'StudyDate': study_date,
                        'StudyTime': study_time,
                        'StudyID': study_id,
                        'PatientID': patient_id,
                        'series': []
                    }
                    # Link study to patient
                    if study_key not in self.patients[patient_id]['studies']:
                        self.patients[patient_id]['studies'].append(study_key)
                    logging.debug(f"Created new study: {study_key}")
                
                # Store series info (create if doesn't exist)
                series_key = f"{study_key}#{series_uid}"
                if series_key not in self.series:
                    self.series[series_key] = {
                        'SeriesInstanceUID': series_uid,
                        'SeriesDescription': series_desc,
                        'SeriesNumber': series_number,
                        'Modality': modality,
                        'StudyInstanceUID': study_uid,
                        'PatientID': patient_id,
                        'images': []
                    }
                    # Link series to study
                    if series_key not in self.studies[study_key]['series']:
                        self.studies[study_key]['series'].append(series_key)
                    logging.debug(f"Created new series: {series_key}")
                
                # Convert file path to DICOMDIR-relative path
                base_dir = os.path.dirname(copied_path)
                while not os.path.basename(base_dir) or os.path.basename(base_dir) != 'DICOM':
                    parent_dir = os.path.dirname(base_dir)
                    if parent_dir == base_dir:  # Reached root
                        break
                    base_dir = parent_dir
                
                # Create relative path from DICOMDIR location to image file
                dicomdir_base = os.path.dirname(base_dir)  # Parent of DICOM folder
                rel_path = os.path.relpath(copied_path, dicomdir_base)
                
                # Convert to DICOM file ID format (array of path components)
                path_components = rel_path.replace('\\', '/').split('/')
                
                # Store image info
                image_info = {
                    'ReferencedFileID': path_components,
                    'ReferencedSOPClassUIDInFile': sop_class_uid,
                    'ReferencedSOPInstanceUIDInFile': sop_instance_uid,
                    'ReferencedTransferSyntaxUIDInFile': transfer_syntax,
                    'InstanceNumber': instance_number,
                    'SeriesInstanceUID': series_uid,
                    'StudyInstanceUID': study_uid,
                    'PatientID': patient_id,
                    'copied_path': copied_path
                }
                
                self.images.append(image_info)
                # Link image to series
                self.series[series_key]['images'].append(image_info)
                
            except Exception as e:
                logging.warning(f"Could not process file {original_path} for DICOMDIR: {e}")
                continue
        
        # Debug the final structure
        self.debug_dicomdir_structure(file_mapping)
        
        logging.info(f"DICOMDIR structure: {len(self.patients)} patients, {len(self.studies)} studies, {len(self.series)} series, {len(self.images)} images")
    
    def generate_dicomdir(self, output_path):
        """Generate valid DICOMDIR file"""
        logging.info(f"Generating DICOMDIR at {output_path}")
        
        try:
            # Create base DICOMDIR dataset
            ds = self._create_base_dataset()
            
            # Build directory record sequence with proper linking
            ds.DirectoryRecordSequence = self._build_directory_records()
            
            # Set file set information
            ds.OffsetOfTheFirstDirectoryRecordOfTheRootDirectoryEntity = 0
            ds.OffsetOfTheLastDirectoryRecordOfTheRootDirectoryEntity = 0
            
            # Save DICOMDIR
            ds.save_as(output_path, enforce_file_format=True)
            logging.info("DICOMDIR created successfully")
            
        except Exception as e:
            logging.error(f"Failed to generate DICOMDIR: {e}")
            raise
    
    def _create_base_dataset(self):
        """Create base DICOMDIR dataset with all required elements"""
        ds = pydicom.Dataset()
        
        # File Meta Information
        ds.file_meta = pydicom.Dataset()
        ds.file_meta.MediaStorageSOPClassUID = "1.2.840.10008.1.3.10"  # Media Storage Directory Storage
        ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
        ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
        ds.file_meta.ImplementationClassUID = pydicom.uid.PYDICOM_IMPLEMENTATION_UID
        ds.file_meta.ImplementationVersionName = f"PYDICOM {pydicom.__version__}"
        ds.file_meta.FileMetaInformationVersion = b'\x00\x01'
        
        # Sanitize FileSetID for CS VR (Code String)
        # CS VR only allows: A-Z, 0-9, space, underscore
        sanitized_file_set_id = self._sanitize_for_cs_vr(self.file_set_id)
        
        # Required main dataset elements
        ds.FileSetID = sanitized_file_set_id[:16]  # Limit to 16 characters max
        ds.FileSetDescriptorFileID = ""  # No descriptor file
        ds.SpecificCharacterSet = "ISO_IR 100"
        ds.FileSetConsistencyFlag = 0x0000  # No known inconsistencies
        
        # Remove the invalid FileSetGroupLength attribute
        # This is not a standard DICOM attribute
        
        return ds

    def _sanitize_for_cs_vr(self, value):
        """
        Sanitize string for Code String (CS) VR
        CS VR allows only: A-Z, 0-9, space, underscore
        """
        if not value:
            return "DICOM_EXPORT"
        
        # Convert to uppercase
        sanitized = value.upper()
        
        # Replace invalid characters with underscore
        valid_chars = []
        for char in sanitized:
            if char.isalnum() or char in ' _':
                valid_chars.append(char)
            else:
                valid_chars.append('_')
        
        result = ''.join(valid_chars)
        
        # Ensure it's not empty and doesn't start/end with spaces
        result = result.strip()
        if not result:
            result = "DICOM_EXPORT"
        
        # Replace multiple consecutive underscores with single underscore
        while '__' in result:
            result = result.replace('__', '_')
        
        logging.debug(f"Sanitized FileSetID: '{value}' -> '{result}'")
        return result
    
    def _build_directory_records(self):
        """Build properly linked directory records"""
        records = []
        
        # Sort patients for consistent ordering
        sorted_patients = sorted(self.patients.items())
        
        logging.info(f"Building directory records for {len(sorted_patients)} patients")
        
        for patient_id, patient_info in sorted_patients:
            logging.debug(f"Processing patient: {patient_id}")
            
            # Create PATIENT record
            patient_record = self._create_patient_record(patient_info)
            records.append(patient_record)
            
            # Get studies for this patient
            study_keys = patient_info.get('studies', [])
            logging.debug(f"  Patient {patient_id} has {len(study_keys)} studies")
            
            sorted_studies = sorted([(k, self.studies[k]) for k in study_keys], 
                                key=lambda x: x[1].get('StudyDate', ''))
            
            for study_key, study_info in sorted_studies:
                logging.debug(f"  Processing study: {study_info['StudyInstanceUID'][:8]}...")
                
                # Create STUDY record
                study_record = self._create_study_record(study_info)
                records.append(study_record)
                
                # Get series for this study
                series_keys = study_info.get('series', [])
                logging.debug(f"    Study has {len(series_keys)} series")
                
                sorted_series = sorted([(k, self.series[k]) for k in series_keys], 
                                    key=lambda x: int(x[1].get('SeriesNumber', '0')))
                
                for series_key, series_info in sorted_series:
                    logging.debug(f"    Processing series: {series_info['SeriesInstanceUID'][:8]}...")
                    
                    # Create SERIES record
                    series_record = self._create_series_record(series_info)
                    records.append(series_record)
                    
                    # Get images for this series
                    images = series_info.get('images', [])
                    logging.debug(f"      Series has {len(images)} images")
                    
                    sorted_images = sorted(images, key=lambda x: int(x.get('InstanceNumber', '0')))
                    
                    for image_info in sorted_images:
                        # Create IMAGE record
                        image_record = self._create_image_record(image_info)
                        records.append(image_record)
        
        logging.info(f"Built {len(records)} directory records total")
        return records
    
    def _create_patient_record(self, patient_info):
        """Create PATIENT directory record"""
        record = pydicom.Dataset()
        record.OffsetOfTheNextDirectoryRecord = 0
        record.RecordInUseFlag = 0xFFFF
        record.OffsetOfReferencedLowerLevelDirectoryEntity = 0
        record.DirectoryRecordType = "PATIENT"
        
        # Required PATIENT level attributes
        record.PatientID = patient_info['PatientID'][:64]  # Limit length
        record.PatientName = patient_info['PatientName'][:320]  # Limit length
        
        return record
    
    def _create_study_record(self, study_info):
        """Create STUDY directory record"""
        record = pydicom.Dataset()
        record.OffsetOfTheNextDirectoryRecord = 0
        record.RecordInUseFlag = 0xFFFF
        record.OffsetOfReferencedLowerLevelDirectoryEntity = 0
        record.DirectoryRecordType = "STUDY"
        
        # Required STUDY level attributes
        record.StudyInstanceUID = study_info['StudyInstanceUID']
        
        # Optional but recommended STUDY attributes
        if study_info.get('StudyDate'):
            record.StudyDate = study_info['StudyDate'][:8]  # YYYYMMDD format
        if study_info.get('StudyTime'):
            record.StudyTime = study_info['StudyTime'][:16]  # HHMMSS.FFFFFF format
        if study_info.get('StudyDescription'):
            record.StudyDescription = study_info['StudyDescription'][:64]
        if study_info.get('StudyID'):
            record.StudyID = study_info['StudyID'][:16]
        
        return record
    
    def _create_series_record(self, series_info):
        """Create SERIES directory record"""
        record = pydicom.Dataset()
        record.OffsetOfTheNextDirectoryRecord = 0
        record.RecordInUseFlag = 0xFFFF
        record.OffsetOfReferencedLowerLevelDirectoryEntity = 0
        record.DirectoryRecordType = "SERIES"
        
        # Required SERIES level attributes
        record.SeriesInstanceUID = series_info['SeriesInstanceUID']
        record.Modality = series_info['Modality'][:16]  # Limit length
        
        # Optional but recommended SERIES attributes
        if series_info.get('SeriesNumber'):
            record.SeriesNumber = series_info['SeriesNumber'][:12]
        if series_info.get('SeriesDescription'):
            record.SeriesDescription = series_info['SeriesDescription'][:64]
        
        return record
    
    def _create_image_record(self, image_info):
        """Create IMAGE directory record"""
        record = pydicom.Dataset()
        record.OffsetOfTheNextDirectoryRecord = 0
        record.RecordInUseFlag = 0xFFFF
        record.OffsetOfReferencedLowerLevelDirectoryEntity = 0
        record.DirectoryRecordType = "IMAGE"
        
        # Required IMAGE level attributes
        record.ReferencedFileID = image_info['ReferencedFileID']
        record.ReferencedSOPClassUIDInFile = image_info['ReferencedSOPClassUIDInFile']
        record.ReferencedSOPInstanceUIDInFile = image_info['ReferencedSOPInstanceUIDInFile']
        record.ReferencedTransferSyntaxUIDInFile = image_info['ReferencedTransferSyntaxUIDInFile']
        
        # Optional but recommended IMAGE attributes
        if image_info.get('InstanceNumber'):
            record.InstanceNumber = image_info['InstanceNumber'][:12]
        
        return record

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
        toolbar.addSeparator()

        # Add after the existing toolbar actions
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
                QMessageBox.warning(self, "Unsupported", "Only .dcm and .zip files are supported.")
                return False
        elif os.path.isdir(path):
            return self._load_directory_consolidated(path)
        else:
            QMessageBox.warning(self, "Not Found", f"Path does not exist: {path}")
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
            QMessageBox.warning(self, "No DICOM", 
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
            QMessageBox.warning(self, "No DICOM", "No DICOM files found in directory.")
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
                    QMessageBox.warning(self, "DICOMDIR Error", 
                                    f"Failed to read DICOMDIR: {error_msg}\n\nFalling back to file scanning...")
            else:
                logging.info("DEBUG: DicomdirReader found no DICOMDIR files")
                
        except Exception as e:
            logging.error(f"DEBUG: Exception in DICOMDIR processing: {e}")
            QMessageBox.warning(self, "DICOMDIR Error", 
                            f"Error processing DICOMDIR: {str(e)}\n\nFalling back to file scanning...")
        
        return []

    def _scan_files_for_dicom(self, files, progress_text="Scanning files..."):
        """
        Scan a list of files and return those that are DICOM files.
        Shows progress dialog during scanning.
        """
        progress = QProgressDialog(progress_text, "Cancel", 0, len(files), self)
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
                self.load_path(file_paths[0])

    def open_directory(self):
        """GUI directory picker"""
        dir_path = QFileDialog.getExistingDirectory(
            self,
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
            QMessageBox.warning(self, "No Selection", "Please select items to validate.")
            return
        
        # Collect file paths from selected items
        file_paths = []
        for item in selected:
            paths = self._collect_instance_filepaths(item)
            file_paths.extend(paths)
        
        if not file_paths:
            QMessageBox.warning(self, "No Files", "No DICOM files found in selection.")
            return
        
        # Remove duplicates
        file_paths = list(set(file_paths))
        
        logging.info(f"Starting validation of {len(file_paths)} selected files")
        
        try:
            run_validation(file_paths, self)
        except Exception as e:
            logging.error(f"Validation error: {e}", exc_info=True)
            QMessageBox.critical(self, "Validation Error", 
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


    def display_selected_tree_file(self): # User's original method with performance diagnosis
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
            # Add performance timing
            start_time = time.time()
            
            ds = pydicom.dcmread(filepath) # Read full dataset for preview
            
            load_time = time.time() - start_time
            
            self.current_filepath = filepath
            self.current_ds = ds
            self.populate_tag_table(ds)
            
            # Diagnose if loading was slow
            if load_time > 0.5:  # If took more than 500ms
                logging.info(f"SLOW LOADING DETECTED ({load_time:.2f}s)")
                self.diagnose_image_performance(ds, filepath)
            elif load_time > 0.1:  # If took more than 100ms but less than 500ms
                logging.info(f"Moderate loading time: {load_time:.2f}s for {os.path.basename(filepath)}")
            
            self._update_image_preview(ds) # Call helper for preview logic
            
        except Exception as e:
            self.tag_table.setRowCount(0)
            self.current_filepath = None
            self.current_ds = None
            self.image_label.clear()
            self.image_label.setVisible(False)
            QMessageBox.critical(self, "Error", f"Error reading file: {filepath}\n{e}")
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
        progress = QProgressDialog(f"Loading {size_mb:.1f}MB image...", "Cancel", 0, 100, self)
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


    def edit_tag(self): # Enhanced with tag search
        """Edit a tag using searchable interface"""
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select an instance in the tree.")
            return
        item = selected[0]
        filepath = item.data(0, Qt.ItemDataRole.UserRole)
        if not filepath:
            QMessageBox.warning(self, "No Instance", "Please select an instance node.")
            return
        try:
            ds = pydicom.dcmread(filepath)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not read file: {e}")
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
                QMessageBox.warning(self, "Invalid Tag", "Invalid tag format.")
                return
        else:
            try:
                tag = pydicom.tag.Tag(tag_str.strip())
            except ValueError:
                QMessageBox.warning(self, "Invalid Tag", f"Tag '{tag_str}' not recognized.")
                return

        # Check if tag exists and get current value
        current_value = ""
        tag_exists = tag in ds
        
        if tag_exists:
            current_value = str(ds[tag].value)
        else:
            # Ask if user wants to add new tag
            reply = QMessageBox.question(
                self, "Tag Not Found", 
                f"Tag {tag_info['name']} ({tag}) not found in this file. Add it as a new tag?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
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
            QMessageBox.information(self, "Success", f"Tag {tag_info['name']} updated successfully.")
            self.display_selected_tree_file()
            
        except Exception as e:
            logging.error(f"Failed to update tag {tag}: {e}")
            QMessageBox.critical(self, "Error", f"Failed to update tag: {str(e)}")



    def batch_edit_tag(self): # Enhanced with tag search
        """Batch edit tags using searchable interface"""
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select a node in the tree.")
            return
        item = selected[0]
        filepaths = self._collect_instance_filepaths(item)
        if not filepaths:
            QMessageBox.warning(self, "No Instances", "No DICOM instances found under this node.")
            return

        
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
                QMessageBox.warning(self, "Invalid Tag", "Invalid tag format.")
                return
        else:
            try:
                tag = pydicom.tag.Tag(tag_str.strip())
            except ValueError:
                QMessageBox.warning(self, "Invalid Tag", f"Tag '{tag_str}' not recognized.")
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
            QMessageBox.critical(self, "Error", f"Could not read sample file: {e}")
            return

        # Show value entry dialog
        value_dialog = ValueEntryDialog(tag_info, current_value, self)
        value_dialog.setWindowTitle(f"Batch Edit: {tag_info['name']}")
        
        if value_dialog.exec() != QDialog.DialogCode.Accepted:
            return
            
        new_value = value_dialog.new_value
        
        # Confirm batch operation
        reply = QMessageBox.question(
            self, "Confirm Batch Edit",
            f"This will update the tag '{tag_info['name']}' in {len(filepaths)} files.\n"
            f"New value: '{new_value}'\n\n"
            "This operation cannot be undone. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Perform batch edit
        updated_count = 0
        failed_files = []
        progress = QProgressDialog(f"Batch editing {tag_info['name']}...", "Cancel", 0, len(filepaths), self)
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
            
        QMessageBox.information(self, "Batch Edit Complete", msg)
        
        if self.current_filepath in filepaths:
            self.display_selected_tree_file()
    
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


    def save_as(self): # User's original, now with DICOMDIR ZIP option
        selected = self.tree.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select a node in the tree to export.")
            return
        
        # FIXED: Collect files from ALL selected items, not just the first one
        filepaths = []
        for tree_item in selected:
            item_files = self._collect_instance_filepaths(tree_item)
            filepaths.extend(item_files)
        
        # Remove duplicates (in case of overlapping selections)
        filepaths = list(set(filepaths))

        if not filepaths:
            QMessageBox.warning(self, "No Instances", "No DICOM instances found under the selected nodes.")
            return

        # Show selection summary
        logging.info(f"Collected {len(filepaths)} files from {len(selected)} selected items")

        # MODIFIED: Add DICOMDIR ZIP option
        export_type, ok = QInputDialog.getItem(
            self, "Export Type", "Export as:", 
            ["Directory", "ZIP", "ZIP with DICOMDIR"], 0, False
        )
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
                    out_path = os.path.join(out_dir, os.path.basename(fp))
                    shutil.copy2(fp, out_path) 
                    exported_count +=1
                except Exception as e:
                    errors.append(f"Failed to export {os.path.basename(fp)}: {e}")
            progress.setValue(len(filepaths))
            msg = f"Exported {exported_count} files to {out_dir}."
            if errors: msg += "\n\nErrors:\n" + "\n".join(errors)
            QMessageBox.information(self, "Export Complete", msg)
            
        elif export_type == "ZIP":
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
                        zipf.write(fp, arcname=os.path.basename(fp))
                        zipped_count += 1
                msg = f"Exported {zipped_count} files to {out_zip_path}."
            except Exception as e:
                msg = f"Failed to create ZIP: {e}"
                logging.error(msg, exc_info=True)
            progress_zip.setValue(len(filepaths))
            if errors: msg += "\n\nErrors during zipping:\n" + "\n".join(errors)
            QMessageBox.information(self, "Export Complete", msg)
            
        elif export_type == "ZIP with DICOMDIR":
            # NEW: DICOMDIR ZIP export
            self._export_dicomdir_zip(filepaths)


    def dicom_send(self):
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
        
        tree_item_anchor = selected[0]
        filepaths = self._collect_instance_filepaths(tree_item_anchor)

        if not filepaths:
            QMessageBox.warning(self, "No Instances", "No DICOM instances found under the selected node.")
            return

        # Get send parameters
        dlg = DicomSendDialog(self, config=self.dicom_send_config)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        
        send_params = dlg.get_params()
        if send_params is None:
            return

        # Get unique SOP classes
        unique_sop_classes_to_send = set()
        for fp_ctx in filepaths:
            try:
                ds_ctx = pydicom.dcmread(fp_ctx, stop_before_pixels=True)
                if hasattr(ds_ctx, 'SOPClassUID'):
                    unique_sop_classes_to_send.add(ds_ctx.SOPClassUID)
            except Exception as e_ctx:
                logging.warning(f"Could not read SOPClassUID from {fp_ctx}: {e_ctx}")
        
        if not unique_sop_classes_to_send:
            QMessageBox.critical(self, "DICOM Send Error", "No valid SOP Class UIDs found.")
            return

        # Create progress dialog
        self.send_progress = QProgressDialog("Starting DICOM send...", "Cancel", 0, len(filepaths), self)
        self.send_progress.setWindowTitle("DICOM Send Progress")
        self.send_progress.setMinimumDuration(0)
        self.send_progress.setValue(0)
        self.send_progress.canceled.connect(self._cancel_dicom_send)
        
        logging.info("Main thread: About to create and start DicomSendWorker")
        
        # Start background send
        self.send_worker = DicomSendWorker(filepaths, send_params, unique_sop_classes_to_send)
        
        # Connect signals with debug logging
        self.send_worker.progress_updated.connect(lambda *args: logging.info(f"progress_updated signal: {args}"))
        self.send_worker.send_complete.connect(lambda *args: logging.info(f"send_complete signal: {args}"))
        self.send_worker.send_failed.connect(lambda msg: logging.error(f"send_failed signal: {msg}"))
        self.send_worker.association_status.connect(lambda msg: logging.info(f"association_status signal: {msg}"))
        self.send_worker.conversion_progress.connect(lambda *args: logging.info(f"conversion_progress signal: {args}"))
        
        # Also connect to your actual handlers
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
        
        QMessageBox.information(self, "DICOM Send Report", msg)
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
        
        QMessageBox.critical(self, "DICOM Send Failed", error_message)
        logging.error(error_message)

    def _on_association_status(self, status_message):
        """Handle association status updates"""
        logging.info(f"_on_association_status called: {status_message}")
        if hasattr(self, 'send_progress') and self.send_progress:
            # Check if we're starting conversion
            if "Converting" in status_message and "incompatible" in status_message:
                # Create conversion progress dialog
                self.conversion_progress = QProgressDialog("Converting incompatible files...", "Cancel", 0, 100, self)
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
            QMessageBox.warning(self, "No Selection", "Please select a node in the tree to anonymize.")
            return
            
        # Collect file paths from selected items
        file_paths = []
        for item in selected:
            paths = self._collect_instance_filepaths(item)
            file_paths.extend(paths)
            
        if not file_paths:
            QMessageBox.warning(self, "No Files", "No DICOM files found in selection.")
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
            QMessageBox.critical(self, "Anonymization Error", 
                            f"An error occurred during anonymization:\n{str(e)}")

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
        except Exception as e:
            QMessageBox.critical(self, "Merge Patients", f"Failed to read primary patient file: {e}")
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
            QMessageBox.warning(self, "Merge Studies", "Select at least two study nodes to merge.\nHold Ctrl or Shift to select multiple studies.")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return
        
        if not self._are_studies_under_same_patient(study_nodes):
            QMessageBox.warning(self, "Merge Studies", "All selected studies must belong to the same patient.")
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
            QMessageBox.warning(self, "Merge Studies", "Could not find any files in the primary study.")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return
        
        try:
            ds_primary = pydicom.dcmread(primary_study_files[0], stop_before_pixels=True)
            primary_study_uid = str(ds_primary.StudyInstanceUID)
            primary_study_desc = str(getattr(ds_primary, "StudyDescription", ""))
            primary_study_id = str(getattr(ds_primary, "StudyID", ""))
        except Exception as e:
            QMessageBox.critical(self, "Merge Studies", f"Failed to read primary study metadata: {e}")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return

        files_to_update = []
        secondary_nodes_to_process = [node for node in study_nodes if node is not primary_study_node]
        for node_sec in secondary_nodes_to_process:
            files_to_update.extend(self._collect_instance_filepaths(node_sec))

        if not files_to_update:
            QMessageBox.information(self, "Merge Studies", "No files found in the secondary studies to merge.")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return
        
        # Confirmation dialog
        reply = QMessageBox.question(
            self, "Confirm Merge",
            f"This will update {len(files_to_update)} files from other study(s) to merge into:\n"
            f"Study UID: {primary_study_uid}\n"
            f"Study Description: {primary_study_desc}\n"
            f"Study ID: {primary_study_id}\n"
            "This modifies files in-place. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return

        updated_m = 0; failed_m = []
        progress_m = QProgressDialog("Merging studies...", "Cancel", 0, len(files_to_update), self)
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
        QMessageBox.information(self, "Merge Studies Complete", msg_m)

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
            QMessageBox.warning(self, "Merge Series", "Select at least two series nodes to merge.\nHold Ctrl or Shift to select multiple series.")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return
        
        if not self._are_series_under_same_study(series_nodes):
            QMessageBox.warning(self, "Merge Series", "All selected series must belong to the same study.")
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
            QMessageBox.warning(self, "Merge Series", "Could not find any files in the primary series.")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return
        
        try:
            ds_primary = pydicom.dcmread(primary_series_files[0], stop_before_pixels=True)
            primary_series_uid = str(ds_primary.SeriesInstanceUID)
            primary_series_desc = str(getattr(ds_primary, "SeriesDescription", ""))
            primary_series_number = str(getattr(ds_primary, "SeriesNumber", ""))
            primary_modality = str(getattr(ds_primary, "Modality", ""))
        except Exception as e:
            QMessageBox.critical(self, "Merge Series", f"Failed to read primary series metadata: {e}")
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
            QMessageBox.information(self, "Merge Series", "No files found in the secondary series to merge.")
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return
        
        # Warn about modality conflicts
        warning_msg = ""
        if modality_conflicts:
            warning_msg = f"\nWarning: Modality conflicts detected: {', '.join(set(modality_conflicts))}\n"
        
        # Confirmation dialog
        reply = QMessageBox.question(
            self, "Confirm Series Merge",
            f"This will update {len(files_to_update)} files from {len(secondary_series)} series to merge into:\n"
            f"Series UID: {primary_series_uid}\n"
            f"Series Description: {primary_series_desc}\n"
            f"Series Number: {primary_series_number}\n"
            f"Modality: {primary_modality}\n"
            f"{warning_msg}\n"
            "This modifies files in-place. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
            return
        
        # Perform the merge
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
        QMessageBox.information(self, "Merge Series Complete", msg)

        # Refresh the tree (corrected - don't call clear_loaded_files)
        all_known_files_after_merge = [f_info[0] for f_info in self.loaded_files if os.path.exists(f_info[0])]
        if all_known_files_after_merge:
            self._load_dicom_files_from_list(all_known_files_after_merge, "data after series merge")

        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        logging.info(f"Series merge completed. Updated {updated_count} files.")

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

        # Refresh from the updated self.loaded_files
        remaining_files_after_delete = [f_info[0] for f_info in self.loaded_files if os.path.exists(f_info[0])]
        self._load_dicom_files_from_list(remaining_files_after_delete, "data after deletion")
        # Clear other UI elements that might refer to deleted items
        self.tag_table.setRowCount(0); self._all_tag_rows = []
        self.image_label.clear(); self.image_label.setVisible(False)
        self.current_filepath = None; self.current_ds = None

        msg_d = f"Deleted {deleted_d_count} file(s)."
        if failed_d_list: msg_d += "\n\nFailed to delete:\n" + "\n".join(failed_d_list[:3])
        QMessageBox.information(self, "Delete Complete", msg_d)

    def validate_dicom_files(self):
        """Run DICOM validation on loaded files"""
        if not self.loaded_files:
            QMessageBox.warning(self, "No Files", "No DICOM files loaded for validation.")
            return
        
        # Get list of file paths
        file_paths = [f_info[0] for f_info in self.loaded_files if os.path.exists(f_info[0])]
        
        if not file_paths:
            QMessageBox.warning(self, "No Files", "No valid file paths found.")
            return
        
        logging.info(f"Starting validation of {len(file_paths)} files")
        
        # Run validation
        try:
            run_validation(file_paths, self)
        except Exception as e:
            logging.error(f"Validation error: {e}", exc_info=True)
            QMessageBox.critical(self, "Validation Error", 
                               f"An error occurred during validation:\n{str(e)}")
    
    def manage_templates(self):
        """Open template management dialog"""
        try:
            template_dialog = TemplateSelectionDialog(self.template_manager, self)
            template_dialog.exec()
        except Exception as e:
            logging.error(f"Template management error: {e}", exc_info=True)
            QMessageBox.critical(self, "Template Management Error", 
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
        """Analyze performance characteristics of all loaded files"""
        logging.info("\n=== ANALYZING ALL LOADED FILES ===")
        
        file_details = []
        
        for filepath, _ in self.loaded_files:
            try:
                # Read WITH pixel data to see actual file sizes
                ds = pydicom.dcmread(filepath)
                
                # Get detailed info
                transfer_syntax = str(getattr(ds.file_meta, 'TransferSyntaxUID', 'Unknown'))
                rows = getattr(ds, 'Rows', 0)
                cols = getattr(ds, 'Columns', 0)
                bits_allocated = getattr(ds, 'BitsAllocated', 0)
                samples_per_pixel = getattr(ds, 'SamplesPerPixel', 1)
                photometric = getattr(ds, 'PhotometricInterpretation', 'Unknown')
                
                # Calculate estimated uncompressed size
                estimated_size = rows * cols * bits_allocated * samples_per_pixel // 8
                
                # Get actual file size
                file_size = os.path.getsize(filepath)
                
                file_details.append({
                    'filename': os.path.basename(filepath),
                    'filepath': filepath,
                    'transfer_syntax': transfer_syntax,
                    'dimensions': f"{cols}x{rows}",
                    'bits': bits_allocated,
                    'samples': samples_per_pixel,
                    'photometric': photometric,
                    'estimated_uncompressed': estimated_size,
                    'actual_file_size': file_size,
                    'compression_ratio': estimated_size / file_size if file_size > 0 else 0
                })
                
            except Exception as e:
                logging.info(f"Error reading {filepath}: {e}")
        
        # Sort by estimated uncompressed size (larger = potentially slower)
        file_details.sort(key=lambda x: x['estimated_uncompressed'], reverse=True)
        
        logging.info(f"\nDETAILED FILE ANALYSIS ({len(file_details)} files):")
        logging.info(f"{'Filename':<15} {'Dimensions':<10} {'Bits':<5} {'Photometric':<12} {'Uncompressed':<12} {'FileSize':<10} {'Compression':<10}")
        logging.info("-" * 90)
        
        for detail in file_details:
            uncompressed_mb = detail['estimated_uncompressed'] / (1024*1024)
            file_size_mb = detail['actual_file_size'] / (1024*1024)
            compression_ratio = detail['compression_ratio']
            
            logging.info(f"{detail['filename']:<15} {detail['dimensions']:<10} {detail['bits']:<5} "
                f"{detail['photometric']:<12} {uncompressed_mb:<11.1f}M {file_size_mb:<9.1f}M {compression_ratio:<9.1f}x")
        
        # Show summary stats
        logging.info(f"\nSUMMARY:")
        dimensions = [d['dimensions'] for d in file_details]
        unique_dimensions = list(set(dimensions))
        logging.info(f"Unique image dimensions: {unique_dimensions}")
        
        sizes = [d['estimated_uncompressed'] for d in file_details]
        logging.info(f"Size range: {min(sizes)/(1024*1024):.1f}MB to {max(sizes)/(1024*1024):.1f}MB")
        
        # Identify likely slow files
        large_files = [d for d in file_details if d['estimated_uncompressed'] > 10*1024*1024]  # >10MB
        if large_files:
            logging.info(f"\nLIKELY SLOW FILES (>10MB uncompressed):")
            for f in large_files:
                logging.info(f"  {f['filename']}: {f['dimensions']}, {f['estimated_uncompressed']/(1024*1024):.1f}MB")

    def test_loading_performance(self):
        """Test actual loading performance of all files"""
        logging.info("\n=== TESTING LOADING PERFORMANCE ===")
        
        import time
        results = []
        
        logging.info("Testing file loading times...")
        for i, (filepath, _) in enumerate(self.loaded_files):
            try:
                start_time = time.time()
                ds = pydicom.dcmread(filepath)
                load_time = time.time() - start_time
                
                # Try to access pixel data to test full loading
                try:
                    pixel_start = time.time()
                    _ = ds.pixel_array
                    pixel_time = time.time() - pixel_start
                    total_time = load_time + pixel_time
                except:
                    pixel_time = 0
                    total_time = load_time
                
                results.append({
                    'filename': os.path.basename(filepath),
                    'load_time': load_time,
                    'pixel_time': pixel_time,
                    'total_time': total_time
                })
                
                # Show progress
                if (i + 1) % 10 == 0:
                    logging.info(f"  Tested {i + 1}/{len(self.loaded_files)} files...")
                    
            except Exception as e:
                logging.info(f"  Error testing {filepath}: {e}")
        
        # Sort by total time
        results.sort(key=lambda x: x['total_time'], reverse=True)
        
        logging.info(f"\nPERFORMANCE RESULTS (slowest first):")
        logging.info(f"{'Filename':<15} {'Load':<8} {'Pixels':<8} {'Total':<8}")
        logging.info("-" * 45)
        
        for result in results[:10]:  # Show top 10 slowest
            logging.info(f"{result['filename']:<15} {result['load_time']:<7.2f}s {result['pixel_time']:<7.2f}s {result['total_time']:<7.2f}s")

    def _convert_for_dicom_send(self, filepaths, show_progress=True):
        """Convert compressed images to uncompressed for better DICOM send compatibility"""
        converted_files = []
        temp_files = []  # Track temp files for cleanup
        
        if show_progress:
            progress = QProgressDialog("Preparing files for DICOM send...", "Cancel", 0, len(filepaths), self)
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
                QMessageBox.critical(self, "Export Error", f"Failed to create DICOMDIR ZIP: {e}")

    def _create_dicomdir_structure(self, filepaths, temp_dir, output_zip):
        """Create DICOM standard structure with DICOMDIR"""
        
        progress = QProgressDialog("Creating DICOMDIR ZIP...", "Cancel", 0, 100, self)
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
            
            QMessageBox.information(self, "Export Complete", 
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