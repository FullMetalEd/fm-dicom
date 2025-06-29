import logging
import sys
import pydicom
from PyQt6.QtWidgets import QTreeWidgetItem


# Add depth method to QTreeWidgetItem
def depth(self):
    """Return the depth of the item in the tree."""
    depth_val = 0 # Renamed to avoid conflict if self is reused
    parent_item = self.parent() # Use a different variable name
    while parent_item:
        depth_val += 1
        parent_item = parent_item.parent()
    return depth_val


QTreeWidgetItem.depth = depth


# Force pydicom to recognize GDCM is available
def force_gdcm():
    try:
        import python_gdcm
        sys.modules['gdcm'] = python_gdcm

        # Force set the HAVE_GDCM flag
        from pydicom.pixel_data_handlers import gdcm_handler
        gdcm_handler.HAVE_GDCM = True

        if gdcm_handler.is_available():
            handlers = pydicom.config.pixel_data_handlers
            if gdcm_handler in handlers:
                handlers.remove(gdcm_handler)
                handlers.insert(0, gdcm_handler)
            logging.info("✅ GDCM forced available and prioritized")
        else:
            logging.error("❌ GDCM still not available")

    except Exception as e:
        logging.error(f"❌ Error forcing GDCM: {e}")
