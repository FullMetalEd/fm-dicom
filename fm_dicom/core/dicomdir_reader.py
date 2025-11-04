import os
import logging
import pydicom


class DicomdirReader:
    """Reader for DICOMDIR files"""
    
    def __init__(self):
        self.dicomdir_path = None
        self.base_directory = None
        
    def find_dicomdir(self, search_path):
        """Recursively search for DICOMDIR files"""
        dicomdir_files = []
        
        for root, dirs, files in os.walk(search_path):
            for file in files:
                if file.upper() == 'DICOMDIR':
                    dicomdir_path = os.path.join(root, file)
                    dicomdir_files.append(dicomdir_path)
                    
        return dicomdir_files
        
    def read_dicomdir(self, dicomdir_path):
        """Read DICOMDIR and extract file references"""
        try:
            self.dicomdir_path = dicomdir_path
            self.base_directory = os.path.dirname(dicomdir_path)
            
            # Read the DICOMDIR file
            ds = pydicom.dcmread(dicomdir_path)
            
            # Extract file references from directory records
            file_paths = []
            
            if hasattr(ds, 'DirectoryRecordSequence'):
                for record in ds.DirectoryRecordSequence:
                    file_path = self._extract_file_path(record)
                    if file_path:
                        file_paths.append(file_path)
                        
            return file_paths
            
        except Exception as e:
            logging.error(f"Failed to read DICOMDIR {dicomdir_path}: {e}")
            return []
            
    def _extract_file_path(self, record):
        """Extract file path from a directory record"""
        try:
            # Check if this is an IMAGE record (actual DICOM file)
            if hasattr(record, 'DirectoryRecordType') and record.DirectoryRecordType == 'IMAGE':
                # Get the referenced file ID
                if hasattr(record, 'ReferencedFileID'):
                    file_id = record.ReferencedFileID
                    
                    # Convert file ID to actual path
                    # DICOM file IDs are typically arrays of path components
                    # Handle both regular lists/tuples AND pydicom MultiValue objects
                    if hasattr(file_id, '__iter__') and not isinstance(file_id, str):
                        # Join the path components (works for lists, tuples, and MultiValue)
                        relative_path = os.path.join(*file_id)
                    else:
                        relative_path = str(file_id)

                    # Convert to absolute path
                    full_path = os.path.join(self.base_directory, relative_path)

                    # Normalize path separators for current OS
                    full_path = os.path.normpath(full_path)
                    
                    # Check if file exists
                    if os.path.exists(full_path):
                        return full_path
                    else:
                        logging.warning(f"DICOMDIR references missing file: {full_path}")
                        
        except Exception as e:
            logging.warning(f"Failed to extract file path from directory record: {e}")
            
        return None