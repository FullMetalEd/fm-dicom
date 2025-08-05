"""
Pytest configuration and fixtures for FM-Dicom tests.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pydicom
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from fm_dicom.config.config_manager import load_config


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication instance for testing GUI components."""
    if not QApplication.instance():
        app = QApplication([])
    else:
        app = QApplication.instance()
    yield app
    # Don't quit the app here as it might affect other tests


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_dicom_file(temp_dir):
    """Create a sample DICOM file for testing."""
    # Create a minimal DICOM dataset
    ds = pydicom.Dataset()
    ds.PatientName = "Test^Patient"
    ds.PatientID = "12345"
    ds.StudyInstanceUID = "1.2.3.4.5.6.7.8.9"
    ds.SeriesInstanceUID = "1.2.3.4.5.6.7.8.10"
    ds.SOPInstanceUID = "1.2.3.4.5.6.7.8.11"
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.2"  # CT Image Storage
    ds.Modality = "CT"
    ds.StudyDate = "20240101"
    ds.SeriesNumber = "1"
    ds.InstanceNumber = "1"
    
    # Add some basic image data
    ds.Rows = 512
    ds.Columns = 512
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    
    # Create minimal pixel data
    import numpy as np
    pixel_array = np.random.randint(0, 4095, (512, 512), dtype=np.uint16)
    ds.PixelData = pixel_array.tobytes()
    
    # Set required transfer syntax
    ds.file_meta = pydicom.Dataset()
    ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    ds.file_meta.ImplementationClassUID = "1.2.3.4.5.6.7.8.12"
    ds.file_meta.ImplementationVersionName = "TEST_1.0"
    ds.file_meta.FileMetaInformationVersion = b'\x00\x01'
    ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    
    file_path = os.path.join(temp_dir, "test.dcm")
    # Use write_like_original=False to ensure proper DICOM format
    ds.save_as(file_path, write_like_original=False)
    return file_path


@pytest.fixture
def sample_config():
    """Create a sample configuration for testing."""
    return {
        "log_path": "~/.local/share/fm-dicom/test.log",
        "log_level": "INFO",
        "show_image_preview": True,
        "file_picker_native": True,
        "window_size": [1200, 800],
        "theme": "light",
        "language": "en",
        "default_export_dir": "~/Downloads/fm-dicom/exports",
        "default_import_dir": "~/Downloads/fm-dicom/imports",
        "ae_title": "FM-DICOM-TEST",
        "destinations": [
            {
                "label": "Test PACS",
                "ae_title": "TESTPACS",
                "host": "127.0.0.1",
                "port": 11112
            }
        ]
    }


@pytest.fixture
def mock_main_window(qapp, sample_config):
    """Create a mock main window for testing manager classes."""
    mock_window = MagicMock()
    mock_window.config = sample_config
    
    # Mock UI components
    mock_window.tag_table = MagicMock()
    mock_window.search_bar = MagicMock()
    mock_window.image_label = MagicMock()
    mock_window.frame_selector = MagicMock()
    mock_window.tree_widget = MagicMock()
    mock_window.status_bar = MagicMock()
    
    return mock_window


@pytest.fixture
def multiple_dicom_files(temp_dir):
    """Create multiple DICOM files for testing."""
    files = []
    
    for i in range(3):
        ds = pydicom.Dataset()
        ds.PatientName = f"Test^Patient{i}"
        ds.PatientID = f"ID{i:03d}"
        ds.StudyInstanceUID = f"1.2.3.4.5.6.7.8.{i}"
        ds.SeriesInstanceUID = f"1.2.3.4.5.6.7.8.{i}.1"
        ds.SOPInstanceUID = f"1.2.3.4.5.6.7.8.{i}.1.1"
        ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
        ds.Modality = "CT"
        ds.StudyDate = f"202401{i+1:02d}"
        ds.SeriesNumber = str(i + 1)
        ds.InstanceNumber = "1"
        
        # Set file meta
        ds.file_meta = pydicom.Dataset()
        ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
        ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
        ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
        ds.file_meta.ImplementationClassUID = "1.2.3.4.5.6.7.8.12"
        ds.file_meta.ImplementationVersionName = "TEST_1.0"
        ds.file_meta.FileMetaInformationVersion = b'\x00\x01'
        
        file_path = os.path.join(temp_dir, f"test_{i}.dcm")
        ds.save_as(file_path, write_like_original=False)
        files.append(file_path)
    
    return files


@pytest.fixture
def temp_config_file(temp_dir, sample_config):
    """Create a temporary config file for testing."""
    import yaml
    config_path = os.path.join(temp_dir, "config.yml")
    
    with open(config_path, 'w') as f:
        yaml.dump(sample_config, f)
    
    return config_path