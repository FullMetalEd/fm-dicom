"""
Multi-threaded DICOM file processor for improved performance with large datasets.

This module provides threaded processing capabilities to handle thousands of DICOM files
efficiently, reducing loading time and maintaining UI responsiveness.
"""

import os
import logging
import queue
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional, Callable, Dict, Any

import pydicom
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QMutex, QMutexLocker


class DicomProcessingResult:
    """Container for DICOM processing results"""
    def __init__(self, file_path: str, success: bool, dataset=None, error=None, metadata=None):
        self.file_path = file_path
        self.success = success
        self.dataset = dataset
        self.error = error
        self.metadata = metadata or {}


class ThreadedDicomProcessor(QObject):
    """Multi-threaded DICOM file processor with Qt signal integration"""

    # Signals
    progress_updated = pyqtSignal(int, int, str)  # current, total, current_file
    file_processed = pyqtSignal(object)  # DicomProcessingResult
    batch_completed = pyqtSignal(list)   # List[DicomProcessingResult]
    processing_finished = pyqtSignal()   # All processing complete
    processing_error = pyqtSignal(str)   # Error message

    def __init__(self, max_workers: int = 4, batch_size: int = 50):
        super().__init__()
        self.max_workers = max_workers
        self.batch_size = batch_size
        self.is_cancelled = False
        self.processed_count = 0
        self.total_files = 0
        self.results_queue = queue.Queue()
        self.mutex = QMutex()

        # Timer for periodic result processing
        self.result_timer = QTimer()
        self.result_timer.timeout.connect(self._process_queued_results)

    def process_files(self, file_paths: List[str],
                     read_pixels: bool = False,
                     required_tags: Optional[List[str]] = None) -> None:
        """
        Process DICOM files in parallel threads

        Args:
            file_paths: List of file paths to process
            read_pixels: Whether to read pixel data (default: False for headers only)
            required_tags: List of DICOM tags to extract (None = extract common hierarchy tags)
        """
        self.is_cancelled = False
        self.processed_count = 0
        self.total_files = len(file_paths)

        # Default required tags for hierarchy building
        if required_tags is None:
            required_tags = [
                'PatientID', 'PatientName',
                'StudyInstanceUID', 'StudyDescription',
                'SeriesInstanceUID', 'SeriesDescription',
                'SOPInstanceUID', 'InstanceNumber',
                'Modality'
            ]

        logging.info(f"Starting threaded processing of {self.total_files} files with {self.max_workers} workers")

        # Start result processing timer
        self.result_timer.start(100)  # Process results every 100ms

        # Process files in background thread to avoid blocking UI
        threading.Thread(
            target=self._process_files_threaded,
            args=(file_paths, read_pixels, required_tags),
            daemon=True
        ).start()

    def cancel_processing(self):
        """Cancel ongoing processing"""
        with QMutexLocker(self.mutex):
            self.is_cancelled = True
        logging.info("DICOM processing cancellation requested")

    def _process_files_threaded(self, file_paths: List[str], read_pixels: bool, required_tags: List[str]):
        """Background thread processing method"""
        try:
            # Split files into batches for progressive updates
            batches = [file_paths[i:i + self.batch_size] for i in range(0, len(file_paths), self.batch_size)]

            for batch_idx, batch in enumerate(batches):
                if self.is_cancelled:
                    logging.info("Processing cancelled during batch processing")
                    return

                # Process batch with thread pool
                batch_results = self._process_batch(batch, read_pixels, required_tags)

                # Queue results for UI thread processing
                self.results_queue.put(('batch', batch_results))

                logging.debug(f"Completed batch {batch_idx + 1}/{len(batches)}")

            # Signal completion
            self.results_queue.put(('complete', None))

        except Exception as e:
            logging.error(f"Error in threaded processing: {e}", exc_info=True)
            self.results_queue.put(('error', str(e)))

    def _process_batch(self, file_paths: List[str], read_pixels: bool, required_tags: List[str]) -> List[DicomProcessingResult]:
        """Process a batch of files using thread pool"""
        results = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all files in batch
            future_to_path = {
                executor.submit(self._process_single_file, path, read_pixels, required_tags): path
                for path in file_paths
            }

            # Collect results as they complete
            for future in as_completed(future_to_path):
                if self.is_cancelled:
                    break

                file_path = future_to_path[future]
                try:
                    result = future.result()
                    results.append(result)

                    # Update progress
                    with QMutexLocker(self.mutex):
                        self.processed_count += 1

                    # Queue individual result for immediate UI feedback
                    self.results_queue.put(('file', result))

                except Exception as e:
                    error_result = DicomProcessingResult(file_path, False, error=str(e))
                    results.append(error_result)
                    logging.warning(f"Error processing {file_path}: {e}")

        return results

    def _process_single_file(self, file_path: str, read_pixels: bool, required_tags: List[str]) -> DicomProcessingResult:
        """Process a single DICOM file"""
        try:
            # Fast pre-check: verify file exists and has reasonable size
            if not os.path.exists(file_path):
                return DicomProcessingResult(file_path, False, error="File not found")

            file_size = os.path.getsize(file_path)
            if file_size < 128:  # DICOM files should be at least 128 bytes
                return DicomProcessingResult(file_path, False, error="File too small to be DICOM")

            # Read DICOM file
            ds = pydicom.dcmread(file_path, stop_before_pixels=not read_pixels)

            # Extract metadata for hierarchy building
            metadata = {}
            for tag in required_tags:
                if hasattr(ds, tag):
                    metadata[tag] = str(getattr(ds, tag, ''))

            # Add file size and basic info
            metadata['file_size'] = file_size
            metadata['file_path'] = file_path

            return DicomProcessingResult(file_path, True, dataset=ds, metadata=metadata)

        except pydicom.errors.InvalidDicomError:
            return DicomProcessingResult(file_path, False, error="Not a valid DICOM file")
        except Exception as e:
            return DicomProcessingResult(file_path, False, error=str(e))

    def _process_queued_results(self):
        """Process results from the queue in UI thread"""
        try:
            while True:
                try:
                    result_type, data = self.results_queue.get_nowait()

                    if result_type == 'file':
                        # Single file processed
                        self.file_processed.emit(data)
                        current_file = os.path.basename(data.file_path) if data.success else "Error"
                        self.progress_updated.emit(self.processed_count, self.total_files, current_file)

                    elif result_type == 'batch':
                        # Batch completed
                        self.batch_completed.emit(data)

                    elif result_type == 'complete':
                        # All processing complete
                        self.result_timer.stop()
                        self.processing_finished.emit()
                        logging.info(f"Threaded processing completed: {self.processed_count}/{self.total_files} files")
                        break

                    elif result_type == 'error':
                        # Processing error
                        self.result_timer.stop()
                        self.processing_error.emit(data)
                        break

                except queue.Empty:
                    break

        except Exception as e:
            logging.error(f"Error processing queued results: {e}", exc_info=True)


class FastDicomScanner:
    """Fast DICOM file detection without full parsing"""

    @staticmethod
    def is_likely_dicom(file_path: str) -> bool:
        """Quick check if file is likely a DICOM file without full parsing"""
        try:
            # Check file size
            if os.path.getsize(file_path) < 128:
                return False

            # Check for DICOM magic numbers and common extensions
            if file_path.lower().endswith(('.dcm', '.dicom')):
                return True

            # Check file header for DICOM signature
            with open(file_path, 'rb') as f:
                # Skip preamble (128 bytes) and check for 'DICM' prefix
                f.seek(128)
                magic = f.read(4)
                if magic == b'DICM':
                    return True

                # Some DICOM files don't have preamble, check for common tags at start
                f.seek(0)
                header = f.read(256)
                # Look for common DICOM patterns
                return (b'\x08\x00' in header or  # Group 0008 tags
                        b'\x10\x00' in header or  # Group 0010 tags
                        b'\x20\x00' in header)    # Group 0020 tags

        except (OSError, IOError):
            return False

        return False

    @staticmethod
    def filter_dicom_files(file_paths: List[str]) -> List[str]:
        """Filter list to only include likely DICOM files"""
        logging.info(f"Pre-filtering {len(file_paths)} files for DICOM content")

        dicom_files = []
        for file_path in file_paths:
            if FastDicomScanner.is_likely_dicom(file_path):
                dicom_files.append(file_path)

        logging.info(f"Pre-filtering found {len(dicom_files)} potential DICOM files")
        return dicom_files