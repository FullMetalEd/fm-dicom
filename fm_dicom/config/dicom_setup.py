import sys
import logging


def setup_gdcm_integration():
    """Force pydicom to recognize GDCM is available"""
    try:
        import python_gdcm
        sys.modules['gdcm'] = python_gdcm
        
        # Force set the HAVE_GDCM flag
        from pydicom.pixel_data_handlers import gdcm_handler
        gdcm_handler.HAVE_GDCM = True
        
        logging.info("GDCM integration successfully enabled")
    except ImportError:
        logging.warning("GDCM not available - some DICOM formats may not be supported")
    except Exception as e:
        logging.error(f"Failed to set up GDCM integration: {e}")