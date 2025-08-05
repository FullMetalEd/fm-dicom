import os
import pydicom
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
                    
            if dicomdir_files:
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
            else:
                # No DICOMDIR found, scan individual files for DICOM content
                dicom_files = []
                total_files = len(self.extracted_files)
                
                for idx, file_path in enumerate(self.extracted_files):
                    if self.isInterruptionRequested():
                        break
                        
                    self.progress_updated.emit(idx + 1, total_files, 
                                             f"Scanning {os.path.basename(file_path)}")
                    
                    try:
                        # Try to read as DICOM
                        ds = pydicom.dcmread(file_path, stop_before_pixels=True)
                        dicom_files.append((file_path, ds))
                    except Exception:
                        # Not a DICOM file, skip silently
                        continue
                
                self.scan_complete.emit(dicom_files)
            
        except Exception as e:
            self.scan_failed.emit(f"DICOM scanning failed: {str(e)}")