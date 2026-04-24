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
from fm_dicom.core.dicomdir_reader import DicomdirReader
from fm_dicom.utils.file_dialogs import get_file_dialog_manager


class FileManager(QObject):
    """Manager class for file operations using Task Center background jobs"""
    
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
        self._loading_additive = False
        
    def open_file(self):
        """Open a single DICOM file"""
        logging.info("Opening file dialog")
        
        start_dir = self.config.get("default_import_dir", os.path.expanduser("~"))
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

        self.load_paths(file_paths)
    
    def open_directory(self):
        """Open a directory containing DICOM files"""
        logging.info("Opening directory dialog")
        
        start_dir = self.config.get("default_import_dir", os.path.expanduser("~"))
        dialog_manager = get_file_dialog_manager(self.config)
        dir_path = dialog_manager.open_directory_dialog(
            self.main_window,
            "Open Directory",
            start_dir
        )
        
        if dir_path:
            self.load_path(dir_path)

    def append_file(self):
        """Append a single DICOM file to currently loaded files"""
        logging.info("Opening file dialog for append operation")

        start_dir = self.config.get("default_import_dir", os.path.expanduser("~"))
        dialog_manager = get_file_dialog_manager(self.config)
        file_paths = dialog_manager.open_file_dialog(
            self.main_window,
            "Add DICOM File",
            start_dir,
            "All Files (*);;DICOM Files (*.dcm *.dicom);;ZIP Archives (*.zip)",
            multiple=True,
        )

        if not file_paths:
            return

        if isinstance(file_paths, str):
            file_paths = [file_paths]

        self.load_paths_additive(file_paths)

    def append_directory(self):
        """Append a directory containing DICOM files to currently loaded files"""
        logging.info("Opening directory dialog for append operation")

        start_dir = self.config.get("default_import_dir", os.path.expanduser("~"))
        dialog_manager = get_file_dialog_manager(self.config)
        dir_path = dialog_manager.open_directory_dialog(
            self.main_window,
            "Add Directory",
            start_dir
        )

        if dir_path:
            self.load_path_additive(dir_path)

    def load_path_additive(self, path):
        """Load files from a given path and append to existing files"""
        if not path or not os.path.exists(path):
            return

        try:
            from fm_dicom.jobs.file_operation_jobs import FileLoadJob
            job = FileLoadJob(path, self)
            job.title = f"Adding {os.path.basename(path) or path}"
            
            # Use a closure to capture the current state
            def start_additive():
                self._loading_additive = True
            
            def end_additive(result):
                self._loading_additive = False
            
            job.signals.started.connect(start_additive)
            job.signals.finished.connect(end_additive)
            job.signals.failed.connect(lambda _: end_additive(None))
            
            self.main_window.job_manager.submit_job(job)
        except Exception as e:
            logging.error(f"Failed to start background additive load: {e}")

    def load_path(self, path):
        """Load files from a given path using Task Center"""
        if not path or not os.path.exists(path):
            return
        
        self._update_recent_paths(path)
        
        try:
            from fm_dicom.jobs.file_operation_jobs import FileLoadJob
            job = FileLoadJob(path, self)
            
            def start_replace():
                self._loading_additive = False
            
            job.signals.started.connect(start_replace)
            self.main_window.job_manager.submit_job(job)
        except Exception as e:
            logging.error(f"Failed to start background load: {e}")

    def load_paths(self, paths):
        """Load several file selections in one batch using Task Center"""
        valid_paths = [p for p in paths if p and os.path.exists(p)]
        if not valid_paths:
            return

        self.load_path(valid_paths[0])
        for path in valid_paths[1:]:
            self.load_path_additive(path)

    def load_paths_additive(self, paths):
        """Append several selections in one batch using Task Center"""
        for path in paths:
            self.load_path_additive(path)

    def _load_path_internal(self, path, progress_callback=None, job=None):
        """Internal loading logic for background jobs."""
        self.loading_started.emit()
        try:
            import pydicom
            if os.path.isfile(path):
                if path.lower().endswith('.zip'):
                    self._load_zip_file_internal(path, progress_callback, job)
                else:
                    # Single DICOM file
                    ds = pydicom.dcmread(path, stop_before_pixels=True)
                    files = [(path, ds)]
                    if self._loading_additive:
                        self.files_to_append.emit(files)
                    else:
                        self.files_loaded.emit(files)
            elif os.path.isdir(path):
                self._scan_directory_internal(path, progress_callback, job)
        finally:
            self.loading_finished.emit()

    def _scan_directory_internal(self, dir_path, progress_callback=None, job=None):
        """Internal directory scan with progress support."""
        import pydicom
        all_dicom_files = []
        
        all_files = []
        for root, _, filenames in os.walk(dir_path):
            if job and job.is_cancelled(): return
            for f in filenames:
                all_files.append(os.path.join(root, f))
        
        total = len(all_files)
        for i, file_path in enumerate(all_files):
            if job and job.is_cancelled(): return
            
            if progress_callback and (i % 10 == 0 or i == total - 1):
                progress_callback(i + 1, total, f"Scanning: {os.path.basename(file_path)}")
            
            if file_path.upper().endswith('DICOMDIR'):
                try:
                    dicomdir_reader = DicomdirReader()
                    dicom_files = dicomdir_reader.read_dicomdir(file_path)
                    all_dicom_files.extend(dicom_files)
                except Exception: pass
                continue
                
            try:
                ds = pydicom.dcmread(file_path, stop_before_pixels=True)
                all_dicom_files.append((file_path, ds))
            except Exception: pass
            
        if all_dicom_files:
            if self._loading_additive:
                self.files_to_append.emit(all_dicom_files)
            else:
                self.files_loaded.emit(all_dicom_files)

    def _load_zip_file_internal(self, zip_path, progress_callback=None, job=None):
        """Internal ZIP loading logic."""
        import zipfile
        temp_dir = tempfile.mkdtemp(prefix="fm_dicom_")
        self.temp_dirs.append(temp_dir)
        
        with zipfile.ZipFile(zip_path, 'r') as zf:
            filenames = zf.namelist()
            total = len(filenames)
            for i, name in enumerate(filenames):
                if job and job.is_cancelled(): return
                if progress_callback:
                    progress_callback(i + 1, total, f"Extracting: {name}")
                zf.extract(name, temp_dir)
        
        self._scan_directory_internal(temp_dir, progress_callback, job)

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
    
    def _update_recent_paths(self, path):
        """Update recent paths in config"""
        if not path:
            return
        recent = self.config.get("recent_paths", [])
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        recent = recent[:10]
        self.config["recent_paths"] = recent
        from fm_dicom.config.config_manager import save_config
        save_config(self.config)
