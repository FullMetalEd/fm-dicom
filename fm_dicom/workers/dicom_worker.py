import os
from PyQt6.QtCore import QThread, pyqtSignal
from fm_dicom.core.dicomdir_reader import DicomdirReader


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