"""
Anonymization Job for background execution in Task Center.
"""

import logging
import os
from fm_dicom.managers.job_manager import BaseJob
from fm_dicom.anonymization.anonymization_ui import AnonymizationWorker, AnonymizationResultsDialog

class AnonymizationJob(BaseJob):
    """A background job for anonymizing DICOM files."""
    
    def __init__(self, template, file_paths, parent_window):
        super().__init__(f"Anonymization ({len(file_paths)} files)")
        self.template = template
        self.file_paths = file_paths
        self.parent_window = parent_window
        self.worker = None
        self.result = None

    def run(self):
        self.signals.started.emit()
        try:
            self.worker = AnonymizationWorker(self.template, self.file_paths)
            
            # Connect worker signals to Job signals
            self.worker.progress_updated.connect(self._on_worker_progress)
            
            # Use a list to capture results from the signal in this scope
            results = []
            def capture_results(res):
                results.append(res)
            
            self.worker.anonymization_complete.connect(capture_results)
            
            # Run the worker's logic directly
            self.worker.run()
            
            if self.is_cancelled():
                return

            if results:
                self.result = results[0]
                self.signals.finished.emit(self.result)
                
                # Refresh tree if needed? The caller should handle this via finished signal
            else:
                 self.signals.failed.emit("Anonymization completed but no result was received.")

        except Exception as e:
            logging.error(f"AnonymizationJob failed: {e}", exc_info=True)
            self.signals.failed.emit(str(e))

    def cancel(self):
        super().cancel()
        if self.worker:
            self.worker.terminate()

    def _on_worker_progress(self, current, current_file):
        total = len(self.file_paths)
        msg = f"Anonymizing: {os.path.basename(current_file)} ({current}/{total})"
        self.signals.progress.emit(current, total, msg)

    def view_results(self):
        """Show the anonymization results dialog."""
        if self.result:
            dialog = AnonymizationResultsDialog(self.result, self.parent_window)
            dialog.exec()
