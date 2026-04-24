"""
Validation Job for background execution in Task Center.
"""

import logging
import os
from fm_dicom.managers.job_manager import BaseJob
from fm_dicom.validation.validation_ui import ValidationWorker, ValidationResultsDialog

class ValidationJob(BaseJob):
    """A background job for validating DICOM files."""
    
    def __init__(self, file_paths, parent_window):
        super().__init__(f"Validation ({len(file_paths)} files)")
        self.file_paths = file_paths
        self.parent_window = parent_window
        self.worker = None
        self.result = None

    def run(self):
        self.signals.started.emit()
        try:
            self.worker = ValidationWorker(self.file_paths)
            
            # Connect worker signals to Job signals
            self.worker.progress_updated.connect(self._on_worker_progress)
            
            # Run the worker's logic directly
            self.worker.run()
            
            self.result = self.worker.collection_result
            
            if self.is_cancelled():
                return

            if self.result and (self.result.file_results or self.result.collection_issues):
                self.signals.finished.emit(self.result)
            else:
                self.signals.finished.emit(None) # No issues found

        except Exception as e:
            logging.error(f"ValidationJob failed: {e}", exc_info=True)
            self.signals.failed.emit(str(e))

    def cancel(self):
        super().cancel()
        if self.worker:
            self.worker.terminate() # ValidationWorker is a QThread

    def _on_worker_progress(self, current, current_file):
        total = len(self.file_paths)
        msg = f"Validating: {os.path.basename(current_file)} ({current}/{total})"
        self.signals.progress.emit(current, total, msg)

    def view_results(self):
        """Show the validation results dialog."""
        if self.result:
            dialog = ValidationResultsDialog(self.result, self.parent_window)
            dialog.exec()
