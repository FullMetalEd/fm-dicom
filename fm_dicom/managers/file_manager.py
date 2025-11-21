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

from fm_dicom.widgets.focus_aware import FocusAwareMessageBox, FocusAwareProgressDialog
from fm_dicom.dialogs.progress_dialogs import ZipExtractionDialog, DicomdirScanDialog
from fm_dicom.core.dicomdir_reader import DicomdirReader
from fm_dicom.utils.file_dialogs import get_file_dialog_manager
# Temporarily commented out for testing - from fm_dicom.utils.threaded_processor import FastDicomScanner


class FileManager(QObject):
    """Manager class for file operations"""
    
    # Signals
    files_loaded = pyqtSignal(list)    # Emitted when files are loaded
    files_to_append = pyqtSignal(list) # Emitted when files are to be appended
    loading_started = pyqtSignal()     # Emitted when loading starts
    loading_finished = pyqtSignal()    # Emitted when loading finishes
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.config = main_window.config
        self.temp_dirs = []  # Track temp directories for cleanup
        
    def open_file(self):
        """Open a single DICOM file"""
        logging.info("Opening file dialog")
        
        start_dir = self.config.get("default_import_dir", os.path.expanduser("~"))
        
        # Use enhanced file dialog manager
        dialog_manager = get_file_dialog_manager(self.config)
        file_paths = dialog_manager.open_file_dialog(
            self.main_window,
            "Open DICOM File",
            start_dir,
            "All Files (*);;DICOM Files (*.dcm *.dicom);;ZIP Archives (*.zip)",
            multiple=True,
        )
        
        if not file_paths:
            return

        if isinstance(file_paths, str):
            file_paths = [file_paths]

        if len(file_paths) == 1:
            file_path = file_paths[0]
            logging.info(f"Selected file: {file_path}")
            self.load_path(file_path)
            return

        logging.info(f"Selected {len(file_paths)} files for loading")
        self._load_multiple_paths(file_paths)
    
    def open_directory(self):
        """Open a directory containing DICOM files"""
        logging.info("Opening directory dialog")
        
        start_dir = self.config.get("default_import_dir", os.path.expanduser("~"))
        
        # Use enhanced file dialog manager
        dialog_manager = get_file_dialog_manager(self.config)
        dir_path = dialog_manager.open_directory_dialog(
            self.main_window,
            "Open Directory",
            start_dir
        )
        
        if dir_path:
            logging.info(f"Selected directory: {dir_path}")
            self.load_path(dir_path)

    def append_file(self):
        """Append a single DICOM file to currently loaded files"""
        logging.info("Opening file dialog for append operation")

        start_dir = self.config.get("default_import_dir", os.path.expanduser("~"))

        # Use enhanced file dialog manager
        dialog_manager = get_file_dialog_manager(self.config)
        file_path = dialog_manager.open_file_dialog(
            self.main_window,
            "Add DICOM File",
            start_dir,
            "All Files (*);;DICOM Files (*.dcm *.dicom);;ZIP Archives (*.zip)"
        )

        if file_path:
            logging.info(f"Selected file for append: {file_path}")
            self.load_path_additive(file_path)

    def append_directory(self):
        """Append a directory containing DICOM files to currently loaded files"""
        logging.info("Opening directory dialog for append operation")

        start_dir = self.config.get("default_import_dir", os.path.expanduser("~"))

        # Use enhanced file dialog manager
        dialog_manager = get_file_dialog_manager(self.config)
        dir_path = dialog_manager.open_directory_dialog(
            self.main_window,
            "Add Directory",
            start_dir
        )

        if dir_path:
            logging.info(f"Selected directory for append: {dir_path}")
            self.load_path_additive(dir_path)

    def load_path_additive(self, path):
        """Load files from a given path and append to existing files"""
        if not path or not os.path.exists(path):
            logging.warning(f"Path does not exist: {path}")
            return

        self.loading_started.emit()

        try:
            if os.path.isfile(path):
                if path.lower().endswith('.zip'):
                    self._load_zip_file_additive(path)
                else:
                    # Single DICOM file
                    self._load_single_file_additive(path)
            elif os.path.isdir(path):
                self._load_directory_additive(path)
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

    def _load_multiple_paths(self, paths):
        """Load several file selections in one batch."""
        valid_paths = [p for p in paths if p and os.path.exists(p)]
        missing_paths = [p for p in paths if not p or not os.path.exists(p)]

        if not valid_paths:
            if missing_paths:
                FocusAwareMessageBox.warning(
                    self.main_window,
                    "Invalid Selection",
                    "None of the selected files could be found."
                )
            return

        first_path = valid_paths[0]
        self.load_path(first_path)

        for path in valid_paths[1:]:
            self.load_path_additive(path)

        if missing_paths:
            logging.warning("Some selected files were missing: %s", missing_paths)

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
        """Load all DICOM files from a directory using comprehensive scanning"""
        logging.info(f"Loading directory: {dir_path}")
        
        # Use comprehensive scanning to handle mixed content
        self._scan_directory_comprehensive(dir_path)
    
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
        """Recursively scan directory for DICOM files with optimized processing"""
        import pydicom

        dicom_files = []

        # First pass: collect all file paths
        all_file_paths = []
        logging.info(f"Scanning directory structure: {dir_path}")

        for root, dirs, files in os.walk(dir_path):
            for file in files:
                file_path = os.path.join(root, file)
                all_file_paths.append(file_path)

        if not all_file_paths:
            FocusAwareMessageBox.information(
                self.main_window,
                "Empty Directory",
                "No files found in the selected directory."
            )
            return

        logging.info(f"Found {len(all_file_paths)} total files, pre-filtering for DICOM content")

        # Pre-filter using fast DICOM detection (temporarily disabled)
        # potential_dicom_files = FastDicomScanner.filter_dicom_files(all_file_paths)
        potential_dicom_files = all_file_paths  # Use all files for now

        if not potential_dicom_files:
            FocusAwareMessageBox.information(
                self.main_window,
                "No DICOM Files",
                "No potential DICOM files found in the selected directory."
            )
            return

        logging.info(f"Pre-filtering found {len(potential_dicom_files)} potential DICOM files")

        # Show progress dialog for DICOM processing
        progress = FocusAwareProgressDialog(
            "Processing DICOM files...",
            "Cancel",
            0,
            len(potential_dicom_files),
            self.main_window
        )
        progress.setWindowTitle("Loading Directory")
        progress.setMinimumDuration(0)
        progress.show()

        # Process potential DICOM files with better progress updates
        processed = 0
        successful_files = 0

        for file_path in potential_dicom_files:
            if progress.wasCanceled():
                logging.info(f"Directory scan cancelled after processing {processed} files")
                progress.close()
                return

            try:
                # Try to read as DICOM
                ds = pydicom.dcmread(file_path, stop_before_pixels=True)
                dicom_files.append((file_path, ds))
                successful_files += 1

            except Exception as e:
                # Not a valid DICOM file, skip silently
                if processed < 5:  # Log first few errors for debugging
                    logging.debug(f"Failed to read as DICOM: {file_path} - {e}")
                continue

            processed += 1

            # Update progress more frequently for responsiveness
            if processed % 10 == 0 or processed == len(potential_dicom_files):
                progress.setValue(processed)
                progress.setLabelText(f"Processed {successful_files} DICOM files\n({processed}/{len(potential_dicom_files)} files checked)")
                QApplication.processEvents()

        progress.close()

        if dicom_files:
            logging.info(f"Directory scan completed: {len(dicom_files)} DICOM files from {len(all_file_paths)} total files")
            self.files_loaded.emit(dicom_files)
        else:
            FocusAwareMessageBox.information(
                self.main_window,
                "No Valid DICOM Files",
                f"No valid DICOM files found in the selected directory.\n"
                f"Checked {len(potential_dicom_files)} potential files from {len(all_file_paths)} total files."
            )
    
    def _scan_directory_comprehensive(self, dir_path):
        """Comprehensively scan directory for all DICOM content (DICOMDIR, ZIP, individual files)"""
        logging.info(f"Starting comprehensive directory scan: {dir_path}")
        
        # Phase 1: Inventory all content types
        dicomdir_files = []
        zip_files = []
        individual_files = []
        
        # First pass: identify all content types
        for root, dirs, files in os.walk(dir_path):
            for file in files:
                file_path = os.path.join(root, file)
                
                if file.upper() == 'DICOMDIR':
                    dicomdir_files.append(file_path)
                elif file.lower().endswith('.zip'):
                    zip_files.append(file_path)
                # Note: We'll identify individual DICOM files in phase 2
        
        # Phase 2: Process each content type and aggregate results
        all_dicom_files = []
        total_operations = len(dicomdir_files) + len(zip_files) + (1 if not dicomdir_files else 0)
        current_operation = 0
        
        # Process DICOMDIR files
        if dicomdir_files:
            logging.info(f"Found {len(dicomdir_files)} DICOMDIR files")
            for dicomdir_path in dicomdir_files:
                current_operation += 1
                logging.info(f"Processing DICOMDIR {current_operation}/{total_operations}: {dicomdir_path}")
                
                try:
                    dicomdir_reader = DicomdirReader()
                    dicom_files = dicomdir_reader.read_dicomdir(dicomdir_path)
                    if dicom_files:
                        all_dicom_files.extend(dicom_files)
                        logging.info(f"DICOMDIR loaded {len(dicom_files)} files")
                except Exception as e:
                    logging.error(f"Error reading DICOMDIR {dicomdir_path}: {e}")
        
        # Process ZIP files
        if zip_files:
            logging.info(f"Found {len(zip_files)} ZIP files")
            for zip_path in zip_files:
                current_operation += 1
                logging.info(f"Processing ZIP {current_operation}/{total_operations}: {zip_path}")
                
                try:
                    zip_dicom_files = self._process_zip_file_for_comprehensive_scan(zip_path)
                    if zip_dicom_files:
                        all_dicom_files.extend(zip_dicom_files)
                        logging.info(f"ZIP file loaded {len(zip_dicom_files)} files")
                except Exception as e:
                    logging.error(f"Error processing ZIP {zip_path}: {e}")
        
        # Process individual DICOM files (only if no DICOMDIR files found)
        if not dicomdir_files:
            current_operation += 1
            logging.info(f"Scanning for individual DICOM files {current_operation}/{total_operations}")
            
            try:
                individual_dicom_files = self._scan_for_individual_dicom_files(dir_path, zip_files)
                if individual_dicom_files:
                    all_dicom_files.extend(individual_dicom_files)
                    logging.info(f"Individual scan found {len(individual_dicom_files)} files")
            except Exception as e:
                logging.error(f"Error scanning for individual DICOM files: {e}")
        
        # Phase 3: Emit results
        if all_dicom_files:
            logging.info(f"Comprehensive scan completed: {len(all_dicom_files)} total DICOM files")
            self.files_loaded.emit(all_dicom_files)
        else:
            FocusAwareMessageBox.information(
                self.main_window,
                "No DICOM Files",
                "No DICOM files found in the selected directory."
            )
    
    def _process_zip_file_for_comprehensive_scan(self, zip_path):
        """Process a ZIP file during comprehensive scan"""
        try:
            # Extract ZIP with progress dialog
            extraction_dialog = ZipExtractionDialog(zip_path, self.main_window)
            if extraction_dialog.exec() and extraction_dialog.success:
                temp_dir = extraction_dialog.temp_dir
                extracted_files = extraction_dialog.extracted_files
                
                # Track temp directory for cleanup
                self.temp_dirs.append(temp_dir)
                
                # Scan extracted files for DICOM content
                scan_dialog = DicomdirScanDialog(extracted_files, self.main_window)
                if scan_dialog.exec() and scan_dialog.success:
                    return scan_dialog.dicom_files
                else:
                    logging.warning(f"Failed to scan extracted files from {zip_path}")
                    return []
            else:
                logging.warning(f"Failed to extract ZIP file {zip_path}")
                return []
        except Exception as e:
            logging.error(f"Error processing ZIP file {zip_path}: {e}")
            return []
    
    def _scan_for_individual_dicom_files(self, dir_path, exclude_zip_files):
        """Scan for individual DICOM files, excluding ZIP files"""
        import pydicom
        
        dicom_files = []
        exclude_paths = set(exclude_zip_files)
        
        for root, dirs, files in os.walk(dir_path):
            for file in files:
                file_path = os.path.join(root, file)
                
                # Skip ZIP files (they're processed separately)
                if file_path in exclude_paths:
                    continue
                
                # Skip DICOMDIR files (they're processed separately)
                if file.upper() == 'DICOMDIR':
                    continue
                
                try:
                    # Try to read as DICOM
                    ds = pydicom.dcmread(file_path, stop_before_pixels=True)
                    dicom_files.append((file_path, ds))
                except Exception:
                    # Not a DICOM file, skip silently
                    continue
        
        return dicom_files

    # Additive loading methods (append to existing files instead of replacing)

    def _load_single_file_additive(self, file_path):
        """Load a single DICOM file for append operation"""
        logging.info(f"Loading single file for append: {file_path}")

        try:
            # Verify it's a DICOM file
            import pydicom
            ds = pydicom.dcmread(file_path, stop_before_pixels=True)

            # Successfully loaded - emit files_to_append instead of files_loaded
            files = [(file_path, ds)]
            self.files_to_append.emit(files)

        except Exception as e:
            logging.error(f"Failed to load DICOM file {file_path}: {e}")
            FocusAwareMessageBox.critical(
                self.main_window,
                "DICOM Load Error",
                f"Failed to load DICOM file:\\n{file_path}\\n\\nError: {str(e)}"
            )

    def _load_directory_additive(self, dir_path):
        """Load all DICOM files from a directory for append operation"""
        logging.info(f"Loading directory for append: {dir_path}")

        # Use comprehensive scanning to handle mixed content
        self._scan_directory_comprehensive_additive(dir_path)

    def _load_zip_file_additive(self, zip_path):
        """Load DICOM files from a ZIP archive for append operation"""
        logging.info(f"Loading ZIP file for append: {zip_path}")

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
                logging.info(f"Found {len(dicom_files)} DICOM files for append")

                if dicom_files:
                    self.files_to_append.emit(dicom_files)
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

    def _scan_directory_comprehensive_additive(self, dir_path):
        """Comprehensively scan directory for DICOM content for append operation"""
        logging.info(f"Starting comprehensive directory scan for append: {dir_path}")

        # Phase 1: Inventory all content types
        dicomdir_files = []
        zip_files = []

        # First pass: identify all content types
        for root, dirs, files in os.walk(dir_path):
            for file in files:
                file_path = os.path.join(root, file)

                if file.upper() == 'DICOMDIR':
                    dicomdir_files.append(file_path)
                elif file.lower().endswith('.zip'):
                    zip_files.append(file_path)

        # Phase 2: Process each content type and aggregate results
        all_dicom_files = []
        total_operations = len(dicomdir_files) + len(zip_files) + (1 if not dicomdir_files else 0)
        current_operation = 0

        # Process DICOMDIR files
        if dicomdir_files:
            logging.info(f"Found {len(dicomdir_files)} DICOMDIR files")
            for dicomdir_path in dicomdir_files:
                current_operation += 1
                logging.info(f"Processing DICOMDIR {current_operation}/{total_operations}: {dicomdir_path}")

                try:
                    dicomdir_reader = DicomdirReader()
                    dicom_files = dicomdir_reader.read_dicomdir(dicomdir_path)
                    if dicom_files:
                        all_dicom_files.extend(dicom_files)
                        logging.info(f"DICOMDIR loaded {len(dicom_files)} files")
                except Exception as e:
                    logging.error(f"Error reading DICOMDIR {dicomdir_path}: {e}")

        # Process ZIP files
        if zip_files:
            logging.info(f"Found {len(zip_files)} ZIP files")
            for zip_path in zip_files:
                current_operation += 1
                logging.info(f"Processing ZIP {current_operation}/{total_operations}: {zip_path}")

                try:
                    zip_dicom_files = self._process_zip_file_for_comprehensive_scan(zip_path)
                    if zip_dicom_files:
                        all_dicom_files.extend(zip_dicom_files)
                        logging.info(f"ZIP file loaded {len(zip_dicom_files)} files")
                except Exception as e:
                    logging.error(f"Error processing ZIP {zip_path}: {e}")

        # Process individual DICOM files (only if no DICOMDIR files found)
        if not dicomdir_files:
            current_operation += 1
            logging.info(f"Scanning for individual DICOM files {current_operation}/{total_operations}")

            try:
                individual_dicom_files = self._scan_for_individual_dicom_files(dir_path, zip_files)
                if individual_dicom_files:
                    all_dicom_files.extend(individual_dicom_files)
                    logging.info(f"Individual scan found {len(individual_dicom_files)} files")
            except Exception as e:
                logging.error(f"Error scanning for individual DICOM files: {e}")

        # Phase 3: Emit results for append
        if all_dicom_files:
            logging.info(f"Comprehensive scan for append completed: {len(all_dicom_files)} total DICOM files")
            self.files_to_append.emit(all_dicom_files)
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
