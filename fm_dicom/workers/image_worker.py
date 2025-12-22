"""
Worker for asynchronous DICOM image loading.
"""

import logging
import traceback
import sys
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, Qt
from PyQt6.QtGui import QImage
import pydicom
import numpy as np

class ImageWorkerSignals(QObject):
    """
    Defines the signals available from a running worker thread.
    Supported signals are:
    finished: No data
    error: tuple (exctype, value, traceback.format_exc() )
    result: object (QImage)
    """
    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)

class ImageLoaderWorker(QRunnable):
    """
    Worker thread for loading and processing DICOM images.
    """

    def __init__(self, file_path_or_ds, frame_index=0):
        super().__init__()
        self.file_path_or_ds = file_path_or_ds
        self.frame_index = frame_index
        self.signals = ImageWorkerSignals()
        self.is_cancelled = False

    def run(self):
        """
        Execute the image loading and processing.
        """
        try:
            if self.is_cancelled:
                return

            # Handle input type
            if isinstance(self.file_path_or_ds, str):
                ds = pydicom.dcmread(self.file_path_or_ds)
            else:
                ds = self.file_path_or_ds

            if self.is_cancelled:
                return

            # Check if dataset has pixel data
            if 'PixelData' not in ds:
                # No image data
                self.signals.result.emit(None)
                return

            # Get pixel array - this is the slow part (decompression)
            pixel_array = ds.pixel_array
            
            if self.is_cancelled:
                return

            # Handle multi-frame images
            if len(pixel_array.shape) > 2:
                # If we have frames, check index
                if self.frame_index < pixel_array.shape[0]:
                    pixel_array = pixel_array[self.frame_index]
                else:
                    pixel_array = pixel_array[0]

            if self.is_cancelled:
                return

            # Normalize pixel data to 0-255 range for display
            # Handle float or other high-bit-depth data
            if pixel_array.dtype != np.uint8:
                # Simple min-max normalization
                # Avoid division by zero
                p_min = pixel_array.min()
                p_max = pixel_array.max()
                
                if p_max > p_min:
                    pixel_array = ((pixel_array - p_min) * 255.0 / (p_max - p_min)).astype(np.uint8)
                else:
                    pixel_array = np.zeros_like(pixel_array, dtype=np.uint8)

            if self.is_cancelled:
                return

            # Create QImage
            # Ensure data is contiguous
            if not pixel_array.flags['C_CONTIGUOUS']:
                pixel_array = np.ascontiguousarray(pixel_array)

            height, width = pixel_array.shape
            
            # Create QImage. We must keep a reference to the data if we were passing the pointer,
            # but constructing with a copy or making sure the data persists is important.
            # QImage(data, width, height, bytesPerLine, format)
            # Warning: The data buffer must remain valid throughout the life of the QImage.
            # Since pixel_array is local, we need to be careful. 
            # Solution: .copy() to make it independent or let QImage take a copy.
            
            q_image = QImage(
                pixel_array.data, 
                width, 
                height, 
                width, # bytesPerLine (stride) - assumes 8-bit grayscale
                QImage.Format.Format_Grayscale8
            )
            
            # Deep copy to ensure it owns its data after the worker finishes
            q_image = q_image.copy()

            self.signals.result.emit(q_image)

        except Exception:
            if not self.is_cancelled:
                exctype, value = sys.exc_info()[:2]
                self.signals.error.emit((exctype, value, traceback.format_exc()))
        finally:
            self.signals.finished.emit()

    def cancel(self):
        """Cancel the operation"""
        self.is_cancelled = True
