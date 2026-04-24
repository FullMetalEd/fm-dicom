"""
DICOM Send Job for background execution in Task Center.
"""

import logging
import pydicom
import os
from fm_dicom.managers.job_manager import BaseJob
from fm_dicom.workers.dicom_send_worker import DicomSendWorker

class DicomSendJob(BaseJob):
    """A background job for sending DICOM files to a remote PACS."""
    
    def __init__(self, selected_files, send_params, memory_items=None):
        super().__init__(f"Send to {send_params[1]}@{send_params[2]}")
        self.selected_files = selected_files
        self.send_params = send_params
        self.memory_items = memory_items or {}
        self.worker = None

    def run(self):
        self.signals.started.emit()
        try:
            # 1. Analyze files to get unique SOP classes
            unique_sop_classes = set()
            for filepath in self.selected_files:
                if self.is_cancelled(): return
                try:
                    ds = self.memory_items.get(filepath) or pydicom.dcmread(filepath, stop_before_pixels=True)
                    if hasattr(ds, 'SOPClassUID'):
                        unique_sop_classes.add(ds.SOPClassUID)
                except Exception:
                    continue
            
            if not unique_sop_classes:
                self.signals.failed.emit("No valid DICOM files found.")
                return

            # 2. Create and connect the existing worker
            self.worker = DicomSendWorker(
                self.selected_files, 
                self.send_params, 
                list(unique_sop_classes), 
                self.memory_items
            )
            
            # Use a list to capture results from the signal in this scope
            results = []
            def capture_results(*args):
                results.append(args)

            # Connect worker signals to Job signals
            self.worker.progress_updated.connect(self._on_worker_progress)
            self.worker.association_status.connect(self._on_worker_status)
            self.worker.conversion_progress.connect(self._on_worker_conversion)
            self.worker.send_complete.connect(capture_results)
            
            # Run the worker's logic directly in this thread
            self.worker.run()
            
            # Final result handling
            if results:
                success, warnings, failed, error_details, converted_count, timing_info = results[0]
                self.results = {
                    "success_count": success,
                    "warning_count": warnings,
                    "failed_count": failed,
                    "error_details": error_details,
                    "converted_count": converted_count
                }
                if failed > 0:
                     self.signals.failed.emit(f"Failed to send {failed} files. Check logs for details.")
                else:
                     self.signals.finished.emit(self.results)
            else:
                 self.signals.failed.emit("Send completed but no result summary was received.")

        except Exception as e:
            logging.error(f"DicomSendJob failed: {e}", exc_info=True)
            self.error = str(e)
            self.signals.failed.emit(self.error)

    def view_results(self):
        """Show summary of DICOM send results"""
        from fm_dicom.widgets.focus_aware import FocusAwareMessageBox
        
        if hasattr(self, 'results') and self.results:
            msg = (
                f"DICOM Send Results:\n\n"
                f"• Successfully sent: {self.results['success_count']}\n"
                f"• Files converted: {self.results['converted_count']}\n"
                f"• Failed: {self.results['failed_count']}"
            )
            if self.results['failed_count'] > 0:
                msg += f"\n\nFirst error: {self.results['error_details'][0] if self.results['error_details'] else 'Unknown'}"
            FocusAwareMessageBox.information(None, "Send Results", msg)
        elif self.error:
            FocusAwareMessageBox.critical(None, "Send Error", f"The DICOM send operation failed:\n\n{self.error}")
        else:
            FocusAwareMessageBox.warning(None, "No Results", "No result details are available for this task.")

    def cancel(self):
        super().cancel()
        if self.worker:
            self.worker.cancel()

    def _on_worker_progress(self, current, success, warnings, failed, current_file):
        total = len(self.selected_files)
        msg = f"Sending: {current_file} ({current}/{total})"
        self.signals.progress.emit(current, total, msg)

    def _on_worker_status(self, status):
        self.signals.progress.emit(0, 0, status)

    def _on_worker_conversion(self, current, total, message):
        self.signals.progress.emit(current, total, message)
