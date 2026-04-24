"""
Analysis and Performance testing jobs for Task Center.
"""

import logging
import os
import time
import pydicom
from fm_dicom.managers.job_manager import BaseJob
from fm_dicom.dialogs.results_dialogs import FileAnalysisResultsDialog, PerformanceResultsDialog

class AnalysisJob(BaseJob):
    """Background job for analyzing DICOM files."""
    
    def __init__(self, loaded_files, parent_window):
        super().__init__("Analyzing Metadata")
        self.loaded_files = loaded_files
        self.parent_window = parent_window
        self.results = None

    def run(self):
        self.start_timer()
        try:
            total = len(self.loaded_files)
            file_details = []
            unique_patients = set()
            unique_dimensions = set()
            transfer_syntaxes = {}
            large_files = []

            for idx, file_info in enumerate(self.loaded_files):
                if self.is_cancelled():
                    return
                
                # Handle different file_info formats
                if isinstance(file_info, tuple):
                    filepath, ds = file_info
                else:
                    filepath = file_info
                    ds = pydicom.dcmread(filepath, stop_before_pixels=True)

                self.signals.progress.emit(idx + 1, total, f"Analyzing: {os.path.basename(filepath)}")

                # Extraction logic
                patient_id = getattr(ds, "PatientID", "UNKNOWN")
                unique_patients.add(patient_id)
                
                # Resolution and bits
                rows = getattr(ds, "Rows", 0)
                cols = getattr(ds, "Columns", 0)
                dims = f"{rows}x{cols}"
                unique_dimensions.add(dims)
                
                bits = getattr(ds, "BitsAllocated", 0)
                photo = getattr(ds, "PhotometricInterpretation", "UNKNOWN")
                
                ts_uid = ds.file_meta.TransferSyntaxUID if hasattr(ds, 'file_meta') and 'TransferSyntaxUID' in ds.file_meta else "Unknown"
                ts_name = "Unknown"
                try:
                    if ts_uid != "Unknown":
                        ts_name = pydicom.uid.UID(ts_uid).name
                except Exception: pass
                
                transfer_syntaxes[ts_name] = transfer_syntaxes.get(ts_name, 0) + 1
                
                file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
                
                # Uncompressed size estimation
                samples = getattr(ds, "SamplesPerPixel", 1)
                uncompressed_bytes = rows * cols * (bits // 8 if bits > 0 else 1) * samples
                if uncompressed_bytes > 10 * 1024 * 1024:
                    large_files.append({
                        'filename': os.path.basename(filepath),
                        'dimensions': dims,
                        'uncompressed_mb': uncompressed_bytes / (1024*1024)
                    })
                
                file_details.append({
                    'filename': os.path.basename(filepath),
                    'patient_id': patient_id,
                    'dimensions': dims,
                    'bits': bits,
                    'photometric': photo,
                    'transfer_syntax_name': ts_name,
                    'uncompressed_mb': uncompressed_bytes / (1024*1024),
                    'file_size_mb': file_size / (1024*1024),
                    'compression_ratio': (uncompressed_bytes / file_size) if file_size > 0 else 1.0,
                    'estimated_uncompressed': uncompressed_bytes
                })

            self.stop_timer()
            
            if not file_details:
                self.signals.failed.emit("No files could be analyzed.")
                return

            sizes = [f['estimated_uncompressed'] for f in file_details]
            size_range = f"{min(sizes)/(1024*1024):.1f}MB to {max(sizes)/(1024*1024):.1f}MB"
            
            self.results = {
                'files': file_details,
                'unique_patients': list(unique_patients),
                'unique_dimensions': list(unique_dimensions),
                'transfer_syntaxes': transfer_syntaxes,
                'large_files': large_files,
                'size_range': size_range
            }
            self.signals.finished.emit(self.results)
            
        except Exception as e:
            self.stop_timer()
            logging.error(f"AnalysisJob failed: {e}", exc_info=True)
            self.signals.failed.emit(str(e))

    def view_results(self):
        """Show detailed results dialog"""
        try:
            if self.results:
                # Import here to avoid circular imports if any
                from fm_dicom.dialogs.results_dialogs import FileAnalysisResultsDialog, PerformanceResultsDialog
                
                if isinstance(self, AnalysisJob):
                    dialog = FileAnalysisResultsDialog(self.results, self.parent_window)
                else:
                    dialog = PerformanceResultsDialog(self.results, self.parent_window)
                dialog.exec()
            else:
                logging.warning("No results to view for job")
        except Exception as e:
            logging.error(f"Error showing results dialog: {e}", exc_info=True)

class PerformanceTestJob(BaseJob):
    """Background job for testing DICOM loading performance."""
    
    def __init__(self, loaded_files, parent_window):
        super().__init__("Performance Testing")
        self.loaded_files = loaded_files
        self.parent_window = parent_window
        self.results = None

    def run(self):
        self.start_timer()
        try:
            total = len(self.loaded_files)
            results = []
            
            for idx, file_info in enumerate(self.loaded_files):
                if self.is_cancelled():
                    return
                
                filepath = file_info[0] if isinstance(file_info, tuple) else file_info
                self.signals.progress.emit(idx + 1, total, f"Testing: {os.path.basename(filepath)}")

                try:
                    # Test loading time
                    t0 = time.time()
                    ds = pydicom.dcmread(filepath)
                    load_time = time.time() - t0
                    
                    # Test pixel access
                    t0 = time.time()
                    if hasattr(ds, 'pixel_array'):
                        _ = ds.pixel_array
                    pixel_time = time.time() - t0
                    
                    results.append({
                        'filename': os.path.basename(filepath),
                        'load_time': load_time,
                        'pixel_time': pixel_time,
                        'total_time': load_time + pixel_time
                    })
                except Exception as e:
                    logging.warning(f"Performance test failed for {filepath}: {e}")

            self.stop_timer()
            
            if not results:
                self.signals.failed.emit("No files could be tested.")
                return

            slow_files = [r for r in results if r['total_time'] > 0.5]
            fastest_file = min(results, key=lambda x: x['total_time'])
            slowest_file = max(results, key=lambda x: x['total_time'])

            self.results = {
                'files': results,
                'slow_files': slow_files,
                'fastest_file': fastest_file,
                'slowest_file': slowest_file
            }
            self.signals.finished.emit(self.results)
            
        except Exception as e:
            self.stop_timer()
            logging.error(f"PerformanceTestJob failed: {e}", exc_info=True)
            self.signals.failed.emit(str(e))

    def view_results(self):
        """Show detailed performance results dialog"""
        try:
            if self.results:
                from fm_dicom.dialogs.results_dialogs import PerformanceResultsDialog
                dialog = PerformanceResultsDialog(self.results, self.parent_window)
                dialog.exec()
            else:
                logging.warning("No performance results to view")
        except Exception as e:
            logging.error(f"Error showing performance results: {e}", exc_info=True)
