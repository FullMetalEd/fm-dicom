"""
Progress dialog classes for DICOM file operations.

This module contains progress dialogs for ZIP extraction and DICOMDIR scanning operations.
"""

from PyQt6.QtWidgets import QProgressDialog, QApplication
from PyQt6.QtCore import Qt
import os
import tempfile
import shutil

from fm_dicom.workers.zip_worker import ZipExtractionWorker
from fm_dicom.workers.dicom_worker import DicomdirScanWorker
from fm_dicom.widgets.focus_aware import FocusAwareMessageBox, FocusAwareProgressDialog


class ZipExtractionDialog(FocusAwareProgressDialog):
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
            except Exception as e:
                import logging
                logging.warning(f"Could not remove temp directory {self.temp_dir}: {e}")
        self.reject()


class DicomdirScanDialog(FocusAwareProgressDialog):
    """Progress dialog for DICOM file scanning"""
    
    def __init__(self, extracted_files, parent=None):
        super().__init__("Searching for DICOM files...", "Cancel", 0, 100, parent)
        self.setWindowTitle("Scanning DICOM Files")
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
        self.setLabelText(f"Processing: {current_file}")
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