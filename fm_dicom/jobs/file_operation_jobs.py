"""
File operation jobs (Load/Save) for background execution in Task Center.
"""

import os
import logging
from fm_dicom.managers.job_manager import BaseJob

class FileLoadJob(BaseJob):
    """Background job for loading DICOM files or directories."""
    
    def __init__(self, path, file_manager):
        super().__init__(f"Loading {os.path.basename(path) or path}")
        self.path = path
        self.file_manager = file_manager

    def run(self):
        self.signals.started.emit()
        try:
            # We need to bridge the file_manager's internal loading logic
            # with our progress signals.
            
            def on_progress(current, total, msg):
                self.signals.progress.emit(current, total, msg)

            # This assumes we refactor FileManager slightly to accept a progress callback
            self.file_manager._load_path_internal(self.path, progress_callback=on_progress, job=self)
            
            if self.is_cancelled():
                return
                
            self.signals.finished.emit({"success": True})
        except Exception as e:
            logging.error(f"FileLoadJob failed: {e}", exc_info=True)
            self.signals.failed.emit(str(e))

class FileSaveJob(BaseJob):
    """Background job for saving modified DICOM files."""
    
    def __init__(self, files_to_save, dicom_manager):
        super().__init__(f"Saving {len(files_to_save)} files")
        self.files_to_save = files_to_save
        self.dicom_manager = dicom_manager

    def run(self):
        self.signals.started.emit()
        try:
            total = len(self.files_to_save)
            for i, (filepath, dataset) in enumerate(self.files_to_save.items()):
                if self.is_cancelled():
                    return
                
                self.signals.progress.emit(i + 1, total, f"Saving: {os.path.basename(filepath)}")
                
                # Use the dicom_manager's save logic
                self.dicom_manager._save_single_file(filepath, dataset)
            
            self.signals.finished.emit({"success": True, "count": total})
        except Exception as e:
            logging.error(f"FileSaveJob failed: {e}", exc_info=True)
            self.signals.failed.emit(str(e))
