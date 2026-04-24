"""
Tree operations jobs for background execution in Task Center.
"""

import logging
import os
from fm_dicom.managers.job_manager import BaseJob
from fm_dicom.utils.threaded_processor import ThreadedDicomProcessor, FastDicomScanner

class TreePopulateJob(BaseJob):
    """Background job for populating the DICOM tree."""
    
    def __init__(self, file_paths, tree_manager, append=False):
        super().__init__(f"Building Tree ({len(file_paths)} files)")
        self.file_paths = file_paths
        self.tree_manager = tree_manager
        self.append = append
        self.result = None

    def run(self):
        self.start_timer()
        try:
            # Pre-filter files
            filtered_paths = FastDicomScanner.filter_dicom_files(self.file_paths)
            
            processor = ThreadedDicomProcessor(
                max_workers=self.tree_manager.max_workers,
                batch_size=self.tree_manager.batch_size
            )
            
            # Default tags for hierarchy building
            required_tags = [
                'PatientID', 'PatientName',
                'StudyInstanceUID', 'StudyDescription',
                'SeriesInstanceUID', 'SeriesDescription',
                'SOPInstanceUID', 'InstanceNumber',
                'Modality'
            ]

            final_hierarchy = {}
            
            def on_progress(current, total, current_file):
                if self.is_cancelled():
                    processor.cancel_processing()
                else:
                    self.signals.progress.emit(current, total, f"Scanning: {os.path.basename(current_file)}")
            
            processor.progress_updated.connect(on_progress)
            
            # Run internal processing method in our current background thread.
            processor._process_files_threaded(filtered_paths, read_pixels=False, required_tags=required_tags)
            
            # Wait for results to be processed from the queue
            import queue
            metadata_map = {}
            while True:
                if self.is_cancelled():
                    break
                try:
                    msg_type, data = processor.results_queue.get(timeout=0.1)
                    if msg_type == 'file':
                        labels = self.tree_manager._add_to_progressive_hierarchy(data, target_hierarchy=final_hierarchy)
                        if labels:
                            metadata_map[data.file_path] = labels
                    elif msg_type == 'complete':
                        break
                    elif msg_type == 'error':
                        logging.error(f"Processing error: {data}")
                except queue.Empty:
                    continue

            self.stop_timer()
            if self.is_cancelled():
                return
            
            self.result = {
                "hierarchy": final_hierarchy,
                "append": self.append,
                "file_paths": self.file_paths,
                "metadata": metadata_map
            }
            self.signals.finished.emit(self.result)
            
        except Exception as e:
            self.stop_timer()
            logging.error(f"TreePopulateJob failed: {e}", exc_info=True)
            self.signals.failed.emit(str(e))

    def view_results(self):
        """Show hierarchy building summary"""
        from fm_dicom.widgets.focus_aware import FocusAwareMessageBox
        if not self.result: return
        
        count = len(self.result['file_paths'])
        patient_count = len(self.result['hierarchy'])
        msg = f"Tree built successfully.\n\nTotal files: {count}\nUnique patients found: {patient_count}"
        FocusAwareMessageBox.information(self.tree_manager.main_window, "Tree Ready", msg)

class DuplicationJob(BaseJob):
    """Background job for duplicating DICOM items."""
    
    def __init__(self, selection, level, uid_config, duplication_manager):
        super().__init__(f"Duplicating {level.title()}")
        self.selection = selection
        self.level = level
        self.uid_config = uid_config
        self.duplication_manager = duplication_manager
        self.result = None

    def run(self):
        self.start_timer()
        try:
            # Connect manager signals to our job signals
            def on_progress(current, total):
                self.signals.progress.emit(current, total, f"Duplicating: {current}/{total}")
            
            self.duplication_manager.duplication_progress.connect(on_progress)
            
            # Perform duplication
            results = self.duplication_manager.duplicate_by_hierarchy(
                self.selection, self.level, self.uid_config
            )
            
            self.stop_timer()
            if self.is_cancelled():
                return
                
            if results:
                self.result = results
                self.signals.finished.emit(results)
            else:
                self.signals.failed.emit("Duplication failed or produced no items.")
                
        except Exception as e:
            self.stop_timer()
            logging.error(f"DuplicationJob failed: {e}", exc_info=True)
            self.signals.failed.emit(str(e))

    def view_results(self):
        """Show duplication results summary"""
        from fm_dicom.widgets.focus_aware import FocusAwareMessageBox
        if not self.result: return
        count = len(self.result)
        msg = f"Successfully duplicated {count} items in memory.\n\nNote: Changes must be saved to disk to be permanent."
        FocusAwareMessageBox.information(self.duplication_manager.main_window, "Duplication Complete", msg)
