"""
Export jobs for Task Center.
"""

import logging
import os
import shutil
from fm_dicom.managers.job_manager import BaseJob
from fm_dicom.workers.export_worker import ExportWorker

class ExportJob(BaseJob):
    """Background job for exporting DICOM files."""
    
    def __init__(self, filepaths, export_type, output_path, temp_dir=None, memory_items=None):
        super().__init__(f"Exporting {len(filepaths)} files")
        self.filepaths = filepaths
        self.export_type = export_type
        self.output_path = output_path
        self.temp_dir = temp_dir
        self.memory_items = memory_items or {}
        self.worker = None

    def run(self):
        self.start_timer()
        try:
            self.worker = ExportWorker(
                self.filepaths, 
                self.export_type, 
                self.output_path, 
                self.temp_dir, 
                self.memory_items
            )
            
            def on_progress(current, total, message):
                self.signals.progress.emit(current, total, message)
            
            self.worker.progress_updated.connect(on_progress)
            
            # Run worker logic in current thread
            self.worker.run()
            
            self.stop_timer()
            if self.is_cancelled():
                return
                
            self.signals.finished.emit({"success": True, "count": len(self.filepaths)})
        except Exception as e:
            self.stop_timer()
            logging.error(f"ExportJob failed: {e}", exc_info=True)
            self.signals.failed.emit(str(e))
        finally:
            # Cleanup temp directory if it was created for this job
            if self.temp_dir and os.path.exists(self.temp_dir):
                try:
                    shutil.rmtree(self.temp_dir)
                    logging.info(f"Cleaned up ExportJob temp directory: {self.temp_dir}")
                except Exception as e:
                    logging.warning(f"Failed to cleanup ExportJob temp dir: {e}")

    def cancel(self):
        super().cancel()
        if self.worker:
            self.worker.cancel()
