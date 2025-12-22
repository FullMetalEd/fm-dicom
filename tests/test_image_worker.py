"""
Tests for the asynchronous image loader worker.
"""

import unittest
import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileDataset
from PyQt6.QtCore import QThreadPool
from PyQt6.QtGui import QImage
from fm_dicom.workers.image_worker import ImageLoaderWorker

class TestImageLoaderWorker(unittest.TestCase):
    def setUp(self):
        # Create a dummy DICOM dataset with pixel data
        self.ds = FileDataset(None, {}, file_meta=Dataset(), preamble=b"\0"*128)
        self.ds.file_meta.TransferSyntaxUID = pydicom.uid.ImplicitVRLittleEndian
        self.ds.is_little_endian = True
        self.ds.is_implicit_VR = True
        self.ds.Rows = 100
        self.ds.Columns = 100
        self.ds.BitsAllocated = 8
        self.ds.BitsStored = 8
        self.ds.HighBit = 7
        self.ds.SamplesPerPixel = 1
        self.ds.PhotometricInterpretation = "MONOCHROME2"
        self.ds.PixelRepresentation = 0  # unsigned
        
        # Create a gradient image
        self.pixel_array = np.linspace(0, 255, 100*100, dtype=np.uint8).reshape(100, 100)
        self.ds.PixelData = self.pixel_array.tobytes()

    def test_worker_run(self):
        """Test that the worker processes image and emits signal"""
        worker = ImageLoaderWorker(self.ds)
        
        # Capture signals
        results = []
        errors = []
        worker.signals.result.connect(lambda img: results.append(img))
        worker.signals.error.connect(lambda err: errors.append(err))
        
        # Run directly (synchronously for test)
        worker.run()
        
        if errors:
            self.fail(f"Worker failed with error: {errors[0][1]}\nTraceback: {errors[0][2]}")
        
        self.assertEqual(len(results), 1)
        q_image = results[0]
        if q_image:
            self.assertIsInstance(q_image, QImage)
            self.assertEqual(q_image.width(), 100)
            self.assertEqual(q_image.height(), 100)
        else:
            self.fail("Worker returned None")

    def test_worker_16bit_normalization(self):
        """Test normalization of 16-bit data"""
        self.ds.BitsAllocated = 16
        self.ds.BitsStored = 16
        self.ds.HighBit = 15
        
        # Create 16-bit array
        pixel_array = np.linspace(0, 65535, 100*100, dtype=np.uint16).reshape(100, 100)
        self.ds.PixelData = pixel_array.tobytes()
        
        worker = ImageLoaderWorker(self.ds)
        results = []
        worker.signals.result.connect(lambda img: results.append(img))
        worker.run()
        
        self.assertEqual(len(results), 1)
        q_image = results[0]
        if q_image:
            self.assertEqual(q_image.format(), QImage.Format.Format_Grayscale8)
        else:
            self.fail("Worker returned None")

    def test_worker_cancellation(self):
        """Test cancellation"""
        worker = ImageLoaderWorker(self.ds)
        worker.cancel()
        
        results = []
        worker.signals.result.connect(lambda img: results.append(img))
        worker.signals.finished.connect(lambda: results.append("finished"))
        
        worker.run()
        
        # Should finish but produce no result
        self.assertNotIn(QImage, [type(r) for r in results])
        self.assertIn("finished", results)

if __name__ == "__main__":
    unittest.main()
