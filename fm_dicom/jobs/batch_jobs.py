"""
Batch operation jobs for Task Center.
"""

import logging
import os
from fm_dicom.managers.job_manager import BaseJob

class BatchTagEditJob(BaseJob):
    """Background job for batch editing DICOM tags."""
    
    def __init__(self, file_paths, tag_info, new_value, dicom_manager):
        super().__init__(f"Batch Edit: {tag_info['name']}")
        self.file_paths = file_paths
        self.tag_info = tag_info
        self.new_value = new_value
        self.dicom_manager = dicom_manager
        self.results = None

    def run(self):
        self.start_timer()
        try:
            updated_count = 0
            failed_files = []
            total = len(self.file_paths)
            
            # Prepare the edit info
            edits = [{
                'tag': self.tag_info['tag'],
                'value_str': self.new_value,
                'original_elem': self.tag_info['elem']
            }]
            
            for idx, filepath in enumerate(self.file_paths):
                if self.is_cancelled(): return
                self.signals.progress.emit(idx + 1, total, f"Editing: {os.path.basename(filepath)}")
                
                try:
                    # Reuse the internal tag apply logic
                    success = self.dicom_manager._apply_tags_to_file(filepath, edits, "Batch Edit")
                    if success: updated_count += 1
                except Exception as e:
                    failed_files.append(f"{os.path.basename(filepath)}: {str(e)}")
            
            self.stop_timer()
            self.results = {
                "success": True, 
                "updated": updated_count, 
                "failed": len(failed_files),
                "failed_details": failed_files
            }
            self.signals.finished.emit(self.results)
            
        except Exception as e:
            self.stop_timer()
            logging.error(f"BatchTagEditJob failed: {e}", exc_info=True)
            self.signals.failed.emit(str(e))

    def view_results(self):
        """Show summary of batch edit results"""
        if not self.results: return
        from fm_dicom.widgets.focus_aware import FocusAwareMessageBox
        msg = f"Batch edit complete.\n\nUpdated: {self.results.get('updated', 0)}\nFailed: {self.results.get('failed', 0)}"
        if self.results.get('failed_details'):
            msg += "\n\nFailures (first 5):\n" + "\n".join(self.results['failed_details'][:5])
        FocusAwareMessageBox.information(None, "Batch Edit Results", msg)

class MergeJob(BaseJob):
    """Background job for merging patients, studies, or series."""
    
    def __init__(self, target_info, source_files, level, dicom_manager):
        super().__init__(f"Merging {level.title()}")
        self.target_info = target_info
        self.source_files = source_files
        self.level = level
        self.dicom_manager = dicom_manager
        self.results = None

    def run(self):
        self.start_timer()
        try:
            success_count = 0
            failed_files = []
            total = len(self.source_files)
            
            for idx, filepath in enumerate(self.source_files):
                if self.is_cancelled(): return
                self.signals.progress.emit(idx + 1, total, f"Merging: {os.path.basename(filepath)}")
                
                try:
                    # Load dataset
                    import pydicom
                    is_memory = False
                    if hasattr(self.dicom_manager.main_window, 'tree_manager'):
                         if filepath in self.dicom_manager.main_window.tree_manager.memory_items:
                             ds = self.dicom_manager.main_window.tree_manager.memory_items[filepath]
                             is_memory = True
                    
                    if not is_memory:
                        ds = pydicom.dcmread(filepath)
                    
                    # Apply move metadata
                    self.dicom_manager.main_window.tree_manager._apply_move_metadata(
                        ds, self.level, self.target_info
                    )
                    
                    # Save
                    if not is_memory:
                        ds.save_as(filepath, write_like_original=False)
                    
                    success_count += 1
                except Exception as e:
                    failed_files.append(f"{os.path.basename(filepath)}: {str(e)}")
            
            self.stop_timer()
            self.results = {
                "success": True,
                "updated": success_count,
                "failed": len(failed_files),
                "failed_details": failed_files
            }
            self.signals.finished.emit(self.results)
            
        except Exception as e:
            self.stop_timer()
            logging.error(f"MergeJob failed: {e}", exc_info=True)
            self.signals.failed.emit(str(e))

    def view_results(self):
        """Show summary of merge results"""
        if not self.results: return
        from fm_dicom.widgets.focus_aware import FocusAwareMessageBox
        msg = f"Merge complete.\n\nSuccessfully updated: {self.results.get('updated', 0)}\nFailed: {self.results.get('failed', 0)}"
        if self.results.get('failed_details'):
            msg += "\n\nFailures (first 5):\n" + "\n".join(self.results['failed_details'][:5])
        FocusAwareMessageBox.information(None, "Merge Results", msg)
