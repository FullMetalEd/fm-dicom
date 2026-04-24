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
        self.result = None

    def run(self):
        self.start_timer()
        try:
            # We need to bridge the file_manager's internal loading logic
            # with our progress signals.
            
            def on_progress(current, total, msg):
                self.signals.progress.emit(current, total, msg)

            self.file_manager._load_path_internal(self.path, progress_callback=on_progress, job=self)
            
            self.stop_timer()
            if self.is_cancelled():
                return
            
            self.result = {"success": True, "path": self.path}
            self.signals.finished.emit(self.result)
        except Exception as e:
            self.stop_timer()
            logging.error(f"FileLoadJob failed: {e}", exc_info=True)
            self.error = str(e)
            self.signals.failed.emit(self.error)

    def view_results(self):
        """Show loading summary"""
        from fm_dicom.widgets.focus_aware import FocusAwareMessageBox
        if self.result:
            msg = f"Successfully loaded files from:\n{self.path}"
            FocusAwareMessageBox.information(self.file_manager.main_window, "Load Complete", msg)
        elif self.error:
            FocusAwareMessageBox.critical(self.file_manager.main_window, "Load Error", f"Failed to load files:\n\n{self.error}")
        else:
            FocusAwareMessageBox.warning(self.file_manager.main_window, "No Results", "No load details are available.")

class FileSaveJob(BaseJob):
    """Background job for saving modified DICOM files."""
    
    def __init__(self, files_to_save, dicom_manager):
        super().__init__(f"Saving {len(files_to_save)} files")
        self.files_to_save = files_to_save
        self.dicom_manager = dicom_manager
        self.result = None

    def run(self):
        self.start_timer()
        try:
            total = len(self.files_to_save)
            for i, (filepath, dataset) in enumerate(self.files_to_save.items()):
                if self.is_cancelled():
                    return
                
                self.signals.progress.emit(i + 1, total, f"Saving: {os.path.basename(filepath)}")
                
                # Use the dicom_manager's save logic
                self.dicom_manager._save_single_file(filepath, dataset)
            
            self.stop_timer()
            self.result = {"success": True, "count": total}
            self.signals.finished.emit(self.result)
        except Exception as e:
            self.stop_timer()
            logging.error(f"FileSaveJob failed: {e}", exc_info=True)
            self.error = str(e)
            self.signals.failed.emit(self.error)

    def view_results(self):
        """Show saving summary"""
        from fm_dicom.widgets.focus_aware import FocusAwareMessageBox
        if self.result:
            msg = f"Successfully saved {self.result['count']} modified files to disk."
            FocusAwareMessageBox.information(self.dicom_manager.main_window, "Save Complete", msg)
        elif self.error:
            FocusAwareMessageBox.critical(self.dicom_manager.main_window, "Save Error", f"Failed to save files:\n\n{self.error}")
        else:
            FocusAwareMessageBox.warning(self.dicom_manager.main_window, "No Results", "No save details are available.")
