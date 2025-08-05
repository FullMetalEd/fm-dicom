import os
import zipfile
from PyQt6.QtCore import QThread, pyqtSignal


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