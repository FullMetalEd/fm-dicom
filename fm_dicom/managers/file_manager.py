"""
File operations manager for MainWindow.

This manager handles all file-related operations including loading,
ZIP extraction, and file system interactions.
"""

import os
import logging
import tempfile
import shutil
from PyQt6.QtWidgets import QFileDialog, QApplication
from PyQt6.QtCore import QObject, pyqtSignal

from fm_dicom.widgets.focus_aware import FocusAwareMessageBox
from fm_dicom.dialogs.progress_dialogs import ZipExtractionDialog, DicomdirScanDialog
from fm_dicom.core.dicomdir_reader import DicomdirReader


class FileManager(QObject):
    """Manager class for file operations"""
    
    # Signals
    files_loaded = pyqtSignal(list)  # Emitted when files are loaded
    loading_started = pyqtSignal()   # Emitted when loading starts
    loading_finished = pyqtSignal()  # Emitted when loading finishes
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.config = main_window.config
        self.temp_dirs = []  # Track temp directories for cleanup
        
    def open_file(self):
        """Open a single DICOM file"""
        logging.info("Opening file dialog")
        
        start_dir = self.config.get("default_import_dir", os.path.expanduser("~"))
        
        file_path, _ = QFileDialog.getOpenFileName(
            self.main_window,
            "Open DICOM File",
            start_dir,
            "All Files (*);;DICOM Files (*.dcm *.dicom);;ZIP Archives (*.zip)"
        )
        
        if file_path:
            logging.info(f"Selected file: {file_path}")
            self.load_path(file_path)
    
    def open_directory(self):
        """Open a directory containing DICOM files"""
        logging.info("Opening directory dialog")
        
        start_dir = self.config.get("default_import_dir", os.path.expanduser("~"))
        
        dir_path = QFileDialog.getExistingDirectory(
            self.main_window,
            "Open Directory",
            start_dir
        )
        
        if dir_path:
            logging.info(f"Selected directory: {dir_path}")
            self.load_path(dir_path)
    
    def load_path(self, path):
        """Load files from a given path (file, directory, or ZIP)"""
        if not path or not os.path.exists(path):
            logging.warning(f"Path does not exist: {path}")
            return
        
        self.loading_started.emit()
        
        try:
            if os.path.isfile(path):
                if path.lower().endswith('.zip'):
                    self._load_zip_file(path)
                else:
                    # Single DICOM file
                    self._load_single_file(path)
            elif os.path.isdir(path):
                self._load_directory(path)
            else:
                logging.warning(f"Unknown path type: {path}")
                FocusAwareMessageBox.warning(
                    self.main_window,
                    "Invalid Path",
                    f"Cannot load path: {path}"
                )
        except Exception as e:
            logging.error(f"Error loading path {path}: {e}", exc_info=True)
            FocusAwareMessageBox.critical(
                self.main_window,
                "Loading Error",
                f"Failed to load {path}:\\n\\n{str(e)}"
            )
        finally:
            self.loading_finished.emit()
    
    def _load_single_file(self, file_path):
        """Load a single DICOM file"""
        logging.info(f"Loading single file: {file_path}")
        
        try:
            # Verify it's a DICOM file
            import pydicom
            ds = pydicom.dcmread(file_path, stop_before_pixels=True)
            
            # Successfully loaded
            files = [(file_path, ds)]
            self.files_loaded.emit(files)
            
        except Exception as e:
            logging.error(f"Failed to load DICOM file {file_path}: {e}")
            FocusAwareMessageBox.critical(
                self.main_window,
                "DICOM Load Error",
                f"Failed to load DICOM file:\\n{file_path}\\n\\nError: {str(e)}"
            )
    
    def _load_directory(self, dir_path):
        """Load all DICOM files from a directory"""
        logging.info(f"Loading directory: {dir_path}")
        
        # Check for DICOMDIR first
        dicomdir_reader = DicomdirReader()
        dicomdir_files = dicomdir_reader.find_dicomdir(dir_path)
        
        if dicomdir_files:
            logging.info(f"Found DICOMDIR, using it to load files")
            self._load_from_dicomdir(dicomdir_files[0], dir_path)
        else:
            logging.info("No DICOMDIR found, scanning directory recursively")
            self._scan_directory_recursive(dir_path)
    
    def _load_zip_file(self, zip_path):
        """Load DICOM files from a ZIP archive"""
        logging.info(f"Loading ZIP file: {zip_path}")
        
        # Extract ZIP with progress dialog
        extraction_dialog = ZipExtractionDialog(zip_path, self.main_window)
        if extraction_dialog.exec() and extraction_dialog.success:
            temp_dir = extraction_dialog.temp_dir
            extracted_files = extraction_dialog.extracted_files
            
            # Track temp directory for cleanup
            self.temp_dirs.append(temp_dir)
            
            logging.info(f"Extracted {len(extracted_files)} files to {temp_dir}")
            
            # Scan for DICOM files with progress
            scan_dialog = DicomdirScanDialog(extracted_files, self.main_window)
            if scan_dialog.exec() and scan_dialog.success:
                dicom_files = scan_dialog.dicom_files
                logging.info(f"Found {len(dicom_files)} DICOM files")
                
                if dicom_files:
                    self.files_loaded.emit(dicom_files)
                else:
                    FocusAwareMessageBox.information(
                        self.main_window,
                        "No DICOM Files",
                        "No DICOM files found in the ZIP archive."
                    )
            else:
                if hasattr(scan_dialog, 'error_message'):
                    FocusAwareMessageBox.critical(
                        self.main_window,
                        "Scan Error",
                        f"Error scanning for DICOM files:\\n{scan_dialog.error_message}"
                    )
        else:
            logging.warning("ZIP extraction failed or was cancelled")
    
    def _load_from_dicomdir(self, dicomdir_path, base_dir):
        """Load files using DICOMDIR"""
        try:
            dicomdir_reader = DicomdirReader()
            dicom_files = dicomdir_reader.read_dicomdir(dicomdir_path)
            
            if dicom_files:
                logging.info(f"DICOMDIR loaded {len(dicom_files)} files")
                self.files_loaded.emit(dicom_files)
            else:
                logging.warning("DICOMDIR found but no files loaded")
                FocusAwareMessageBox.warning(
                    self.main_window,
                    "DICOMDIR Empty",
                    "DICOMDIR file found but contains no readable DICOM files."
                )
                
        except Exception as e:
            logging.error(f"Error reading DICOMDIR: {e}", exc_info=True)
            FocusAwareMessageBox.critical(
                self.main_window,
                "DICOMDIR Error",
                f"Error reading DICOMDIR:\\n{str(e)}"
            )
    
    def _scan_directory_recursive(self, dir_path):
        """Recursively scan directory for DICOM files"""
        import pydicom
        
        dicom_files = []
        file_count = 0
        
        # Count files first for progress
        for root, dirs, files in os.walk(dir_path):
            file_count += len(files)
        
        if file_count == 0:
            FocusAwareMessageBox.information(
                self.main_window,
                "Empty Directory",
                "No files found in the selected directory."
            )
            return
        
        # Progress tracking
        processed = 0
        
        # Scan files
        for root, dirs, files in os.walk(dir_path):
            for file in files:
                file_path = os.path.join(root, file)
                processed += 1
                
                try:
                    # Try to read as DICOM
                    ds = pydicom.dcmread(file_path, stop_before_pixels=True)
                    dicom_files.append((file_path, ds))
                    
                except Exception:
                    # Not a DICOM file, skip silently
                    continue
                
                # Update progress occasionally
                if processed % 100 == 0:
                    QApplication.processEvents()
        
        if dicom_files:
            logging.info(f"Directory scan found {len(dicom_files)} DICOM files")
            self.files_loaded.emit(dicom_files)
        else:
            FocusAwareMessageBox.information(
                self.main_window,
                "No DICOM Files",
                "No DICOM files found in the selected directory."
            )
    
    def cleanup_temp_dirs(self):
        """Clean up temporary directories"""
        for temp_dir in self.temp_dirs:
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    logging.info(f"Cleaned up temp directory: {temp_dir}")
                except Exception as e:
                    logging.warning(f"Failed to clean up temp directory {temp_dir}: {e}")
        
        self.temp_dirs.clear()
    
    def get_file_info(self, file_path):
        """Get basic file information"""
        if not os.path.exists(file_path):
            return None
        
        stat = os.stat(file_path)
        return {
            'size': stat.st_size,
            'modified': stat.st_mtime,
            'name': os.path.basename(file_path),
            'dir': os.path.dirname(file_path)
        }