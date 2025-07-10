"""
DICOM Send Worker Module

This module contains the DicomSendWorker class which handles DICOM network sending operations
with auto-conversion capabilities for incompatible formats.
"""

import os
import time
import tempfile
import logging

import numpy as np
import pydicom
from pydicom.uid import generate_uid

from PyQt6.QtCore import QThread, pyqtSignal

from pynetdicom import AE, AllStoragePresentationContexts
from pynetdicom.sop_class import Verification

# Constants
VERIFICATION_SOP_CLASS = Verification
STORAGE_CONTEXTS = AllStoragePresentationContexts


class DicomSendWorker(QThread):
    """Background worker for DICOM sending with auto-conversion on format rejection"""
    progress_updated = pyqtSignal(int, int, int, int, str)  # current, success, warnings, failed, current_file
    send_complete = pyqtSignal(int, int, int, list, int, dict)  # success, warnings, failed, error_details, converted_count, timing_info
    send_failed = pyqtSignal(str)  # error message
    association_status = pyqtSignal(str)  # status messages
    conversion_progress = pyqtSignal(int, int, str)  # current, total, filename
    
    def __init__(self, filepaths, send_params, unique_sop_classes):
        super().__init__()
        self.filepaths = filepaths
        self.calling_ae, self.remote_ae, self.host, self.port = send_params
        self.unique_sop_classes = unique_sop_classes
        self.cancelled = False
        self.temp_files = []  # Track temp files for cleanup
        self.converted_count = 0
        self.timing_info = {}  # Track timing for each step
        
    def run(self):
        try:
            import time
            start_time = time.time()
            logging.info("DicomSendWorker: Starting run() method")
            
            # First, extract unique transfer syntaxes from selected files for optimized compatibility checking
            self.association_status.emit("Analyzing file transfer syntaxes...")
            analysis_start = time.time()
            unique_transfer_syntaxes = self._extract_unique_transfer_syntaxes(self.filepaths)
            self.timing_info['analysis_time'] = time.time() - analysis_start
            logging.info(f"DicomSendWorker: Found {len(unique_transfer_syntaxes)} unique transfer syntaxes")
            
            # Optimized compatibility check: only test the transfer syntaxes actually used
            self.association_status.emit("Testing server compatibility...")
            logging.info("DicomSendWorker: About to attempt optimized compatibility check")
            
            compatibility_start = time.time()
            incompatible_transfer_syntaxes = self._test_transfer_syntax_compatibility(unique_transfer_syntaxes)
            self.timing_info['compatibility_check_time'] = time.time() - compatibility_start
            logging.info(f"DicomSendWorker: {len(incompatible_transfer_syntaxes)} incompatible transfer syntaxes found")
            
            # Identify which files need conversion based on compatibility results
            files_needing_conversion = []
            if incompatible_transfer_syntaxes:
                files_needing_conversion = self._identify_files_needing_conversion(self.filepaths, incompatible_transfer_syntaxes)
                logging.info(f"DicomSendWorker: {len(files_needing_conversion)} files need conversion")
            
            # Convert incompatible files if needed
            files_to_send = self.filepaths.copy()
            if files_needing_conversion:
                logging.info(f"DicomSendWorker: Converting {len(files_needing_conversion)} incompatible files")
                self.association_status.emit(f"Converting {len(files_needing_conversion)} incompatible files...")
                
                conversion_start = time.time()
                converted_files = self._convert_incompatible_files(files_needing_conversion)
                self.timing_info['conversion_time'] = time.time() - conversion_start
                logging.info(f"DicomSendWorker: Conversion complete, got {len(converted_files)} converted files")
                
                # Replace original files with converted ones in the send list
                if converted_files:
                    for i, original_file in enumerate(files_to_send):
                        if original_file in files_needing_conversion:
                            converted_index = files_needing_conversion.index(original_file)
                            if converted_index < len(converted_files):
                                files_to_send[i] = converted_files[converted_index]
            else:
                self.timing_info['conversion_time'] = 0
            
            # Now send all files (original + converted)
            self.association_status.emit("Sending files to server...")
            send_start = time.time()
            result = self._attempt_send_with_formats(files_to_send, test_mode=False)
            self.timing_info['send_time'] = time.time() - send_start
            
            if result is None:  # Cancelled
                logging.info("DicomSendWorker: Send was cancelled")
                return
                
            success, warnings, failed, error_details, _ = result
            logging.info(f"DicomSendWorker: Send complete - Success: {success}, Warnings: {warnings}, Failed: {failed}")
            
            # Calculate total time
            self.timing_info['total_time'] = time.time() - start_time
            
            logging.info("DicomSendWorker: About to emit send_complete signal")
            # Send completion signal with timing info
            self.send_complete.emit(success, warnings, failed, error_details, self.converted_count, self.timing_info)
            logging.info("DicomSendWorker: send_complete signal emitted")
            
        except Exception as e:
            logging.error(f"DicomSendWorker: Exception in run(): {e}", exc_info=True)
            self.send_failed.emit(f"DICOM send failed: {str(e)}")
        finally:
            logging.info("DicomSendWorker: Cleaning up temp files")
            # Cleanup temp files
            self._cleanup_temp_files()
            logging.info("DicomSendWorker: run() method complete")
    
    def _attempt_send_with_formats(self, filepaths, test_mode=False):
        """Attempt to send files and identify format incompatibilities"""
        try:
            logging.info(f"DicomSendWorker: _attempt_send_with_formats called with {len(filepaths)} files, test_mode={test_mode}")
            
            # Create AE instance
            ae_instance = AE(ae_title=self.calling_ae)
            logging.info("DicomSendWorker: Created AE instance")
            
            # Add presentation contexts
            for sop_uid in self.unique_sop_classes:
                ae_instance.add_requested_context(sop_uid)
            ae_instance.add_requested_context(VERIFICATION_SOP_CLASS)
            logging.info(f"DicomSendWorker: Added {len(self.unique_sop_classes)} presentation contexts")
            
            # Establish association
            if test_mode:
                self.association_status.emit("Testing server compatibility...")
            else:
                self.association_status.emit("Sending files to server...")
            
            logging.info(f"DicomSendWorker: Attempting association to {self.host}:{self.port}")
            assoc = ae_instance.associate(self.host, self.port, ae_title=self.remote_ae)
            
            if not assoc.is_established:
                logging.error(f"DicomSendWorker: Association failed: {assoc}")
                if test_mode:
                    self.send_failed.emit(f"Failed to establish association with {self.host}:{self.port}")
                    return None
                else:
                    return 0, 0, len(filepaths), [f"Association failed for all {len(filepaths)} files"], []
            
            logging.info("DicomSendWorker: Association established successfully")
            
            # Set timeout
            assoc.dimse_timeout = 120
            
            # C-ECHO verification
            logging.info("DicomSendWorker: Performing C-ECHO")
            echo_status = assoc.send_c_echo()
            if echo_status and getattr(echo_status, 'Status', None) == 0x0000:
                logging.info("DicomSendWorker: C-ECHO verification successful.")
            else:
                logging.warning(f"DicomSendWorker: C-ECHO failed or status not 0x0000. Status: {echo_status}")
            
            # Send files
            logging.info(f"DicomSendWorker: Starting to send {len(filepaths)} files")
            sent_ok = 0
            sent_warning = 0
            failed_send = 0
            failed_details_list = []
            incompatible_files = []
            
            for idx, fp_send in enumerate(filepaths):
                if self.cancelled:
                    break
                
                try:
                    # Check association
                    if not assoc.is_established:
                        assoc = ae_instance.associate(self.host, self.port, ae_title=self.remote_ae)
                        if not assoc.is_established:
                            failed_details_list.append(f"{os.path.basename(fp_send)}: Could not re-establish association")
                            failed_send += 1
                            continue
                        assoc.dimse_timeout = 120
                    
                    # Read file
                    ds_send = pydicom.dcmread(fp_send)
                    
                    # Check SOP class support
                    if not any(ctx.abstract_syntax == ds_send.SOPClassUID and ctx.result == 0x00 for ctx in assoc.accepted_contexts):
                        err_msg = f"{os.path.basename(fp_send)}: SOP Class not accepted"
                        failed_details_list.append(err_msg)
                        failed_send += 1
                        
                        # This might be a format issue - add to incompatible list
                        if test_mode:
                            incompatible_files.append(fp_send)
                        
                        # UPDATE PROGRESS EVEN IN TEST MODE
                        if test_mode:
                            self.progress_updated.emit(idx + 1, sent_ok, sent_warning, failed_send, f"Testing {os.path.basename(fp_send)}")
                        else:
                            self.progress_updated.emit(idx + 1, sent_ok, sent_warning, failed_send, os.path.basename(fp_send))
                        continue
                    
                    # Send C-STORE
                    status = assoc.send_c_store(ds_send)
                    
                    # Process result
                    if status:
                        status_code = getattr(status, "Status", -1)
                        if status_code == 0x0000:
                            sent_ok += 1
                            logging.info(f"Successfully sent {os.path.basename(fp_send)}")
                        elif status_code in [0xB000, 0xB006, 0xB007]:
                            sent_warning += 1
                            warn_msg = f"{os.path.basename(fp_send)}: Warning 0x{status_code:04X}"
                            failed_details_list.append(warn_msg)
                        else:
                            failed_send += 1
                            err_msg = f"{os.path.basename(fp_send)}: Failed 0x{status_code:04X}"
                            failed_details_list.append(err_msg)
                            
                            # Check if this is a format-related failure
                            if test_mode and self._is_format_error(status_code):
                                incompatible_files.append(fp_send)
                    else:
                        failed_send += 1
                        failed_details_list.append(f"{os.path.basename(fp_send)}: No status returned")
                        if test_mode:
                            incompatible_files.append(fp_send)
                    
                    # UPDATE PROGRESS FOR BOTH TEST AND NORMAL MODE
                    if test_mode:
                        self.progress_updated.emit(idx + 1, sent_ok, sent_warning, failed_send, f"Testing {os.path.basename(fp_send)}")
                    else:
                        self.progress_updated.emit(idx + 1, sent_ok, sent_warning, failed_send, os.path.basename(fp_send))
                    
                except Exception as e:
                    error_str = str(e)
                    failed_send += 1
                    err_msg = f"{os.path.basename(fp_send)}: {error_str}"
                    failed_details_list.append(err_msg)
                    
                    # Check if this is a format/compression error
                    if test_mode and self._is_format_exception(error_str):
                        incompatible_files.append(fp_send)
                        logging.info(f"Detected format incompatibility for {os.path.basename(fp_send)}: {error_str}")
                    
                    # UPDATE PROGRESS FOR BOTH TEST AND NORMAL MODE
                    if test_mode:
                        self.progress_updated.emit(idx + 1, sent_ok, sent_warning, failed_send, f"Testing {os.path.basename(fp_send)}")
                    else:
                        self.progress_updated.emit(idx + 1, sent_ok, sent_warning, failed_send, os.path.basename(fp_send))
            
            # Close association
            try:
                assoc.release()
            except Exception as e:
                logging.warning(f"Error releasing association: {e}")
            
            return sent_ok, sent_warning, failed_send, failed_details_list, incompatible_files
            
        except Exception as e:
            logging.error(f"DicomSendWorker: Exception in _attempt_send_with_formats: {e}", exc_info=True)
            raise
    
    def _is_format_error(self, status_code):
        """Check if status code indicates a format/transfer syntax error"""
        # Common DICOM status codes for format/transfer syntax issues
        format_error_codes = [
            0x0122,  # SOP Class not supported
            0x0124,  # Not authorized
            0xA900,  # Dataset does not match SOP Class
            0xC000,  # Cannot understand
        ]
        return status_code in format_error_codes
    
    def _is_format_exception(self, error_str):
        """Check if exception indicates a format/compression issue"""
        format_keywords = [
            'presentation context',
            'transfer syntax',
            'compression',
            'jpeg',
            'jpeg2000',
            'not accepted',
            'not supported',
            'cannot decompress',
            'no suitable presentation context'
        ]
        error_lower = error_str.lower()
        return any(keyword in error_lower for keyword in format_keywords)
    
    def _extract_unique_transfer_syntaxes(self, filepaths):
        """Extract unique transfer syntaxes from the selected files"""
        unique_syntaxes = set()
        
        for filepath in filepaths:
            if self.cancelled:
                break
                
            try:
                # Read DICOM file header to get transfer syntax
                ds = pydicom.dcmread(filepath, stop_before_pixels=True)
                if hasattr(ds, 'file_meta') and hasattr(ds.file_meta, 'TransferSyntaxUID'):
                    transfer_syntax = str(ds.file_meta.TransferSyntaxUID)
                    unique_syntaxes.add(transfer_syntax)
                    logging.debug(f"File {os.path.basename(filepath)}: Transfer syntax {transfer_syntax}")
                else:
                    # Default to Implicit VR Little Endian if not specified
                    unique_syntaxes.add('1.2.840.10008.1.2')
                    logging.debug(f"File {os.path.basename(filepath)}: No transfer syntax found, assuming Implicit VR Little Endian")
                    
            except Exception as e:
                logging.warning(f"Could not read transfer syntax from {os.path.basename(filepath)}: {e}")
                # Assume default transfer syntax
                unique_syntaxes.add('1.2.840.10008.1.2')
        
        # Convert to list and log the results
        syntax_list = list(unique_syntaxes)
        logging.info(f"Found {len(syntax_list)} unique transfer syntaxes: {syntax_list}")
        return syntax_list
    
    def _test_transfer_syntax_compatibility(self, transfer_syntaxes):
        """Test which transfer syntaxes are not supported by the server"""
        incompatible_syntaxes = []
        
        try:
            # Create AE instance
            ae_instance = AE(ae_title=self.calling_ae)
            
            # Add presentation contexts with the specific transfer syntaxes
            for sop_uid in self.unique_sop_classes:
                # Add contexts with specific transfer syntaxes
                for ts in transfer_syntaxes:
                    ae_instance.add_requested_context(sop_uid, ts)
                    
            # Also add verification context
            ae_instance.add_requested_context(VERIFICATION_SOP_CLASS)
            
            # Establish association
            logging.info(f"Testing compatibility for {len(transfer_syntaxes)} transfer syntaxes")
            assoc = ae_instance.associate(self.host, self.port, ae_title=self.remote_ae)
            
            if not assoc.is_established:
                logging.error("Could not establish association for compatibility testing")
                # If we can't establish association, assume all syntaxes are incompatible
                return transfer_syntaxes
            
            # Check which transfer syntaxes were rejected
            for ts in transfer_syntaxes:
                ts_supported = False
                for sop_uid in self.unique_sop_classes:
                    # Check if any context with this transfer syntax was accepted
                    for ctx in assoc.accepted_contexts:
                        if ctx.abstract_syntax == sop_uid and ctx.transfer_syntax[0] == ts and ctx.result == 0x00:
                            ts_supported = True
                            break
                    if ts_supported:
                        break
                
                if not ts_supported:
                    incompatible_syntaxes.append(ts)
                    logging.info(f"Transfer syntax {ts} is not supported by the server")
                else:
                    logging.info(f"Transfer syntax {ts} is supported by the server")
            
            # Close association
            try:
                assoc.release()
            except Exception as e:
                logging.warning(f"Error releasing association: {e}")
                
        except Exception as e:
            logging.error(f"Error during transfer syntax compatibility testing: {e}")
            # If testing fails, assume all syntaxes might be incompatible
            return transfer_syntaxes
        
        return incompatible_syntaxes
    
    def _identify_files_needing_conversion(self, filepaths, incompatible_syntaxes):
        """Identify which files need conversion based on incompatible transfer syntaxes"""
        files_needing_conversion = []
        
        for filepath in filepaths:
            if self.cancelled:
                break
                
            try:
                # Read DICOM file header to get transfer syntax
                ds = pydicom.dcmread(filepath, stop_before_pixels=True)
                if hasattr(ds, 'file_meta') and hasattr(ds.file_meta, 'TransferSyntaxUID'):
                    transfer_syntax = str(ds.file_meta.TransferSyntaxUID)
                else:
                    # Default to Implicit VR Little Endian if not specified
                    transfer_syntax = '1.2.840.10008.1.2'
                
                # Check if this file's transfer syntax is incompatible
                if transfer_syntax in incompatible_syntaxes:
                    files_needing_conversion.append(filepath)
                    logging.info(f"File {os.path.basename(filepath)} needs conversion (transfer syntax: {transfer_syntax})")
                    
            except Exception as e:
                logging.warning(f"Could not check transfer syntax for {os.path.basename(filepath)}: {e}")
                # If we can't read the file, assume it needs conversion
                files_needing_conversion.append(filepath)
        
        return files_needing_conversion
    
    def _convert_incompatible_files(self, filepaths):
        """Convert incompatible files to standard uncompressed format with validation"""
        converted_files = []
        total_files = len(filepaths)
        
        for idx, filepath in enumerate(filepaths):
            if self.cancelled:
                break
            
            # Emit conversion progress with detailed status
            self.conversion_progress.emit(idx + 1, total_files, f"Converting {os.path.basename(filepath)} ({idx + 1}/{total_files})")
            
            try:
                # Read original file
                ds_original = pydicom.dcmread(filepath)
                original_ts = str(ds_original.file_meta.TransferSyntaxUID)
                
                # Check if conversion is needed
                compressed_syntaxes = [
                    '1.2.840.10008.1.2.4.90',  # JPEG 2000 Lossless
                    '1.2.840.10008.1.2.4.91',  # JPEG 2000
                    '1.2.840.10008.1.2.4.50',  # JPEG Baseline
                    '1.2.840.10008.1.2.4.51',  # JPEG Extended
                    '1.2.840.10008.1.2.4.57',  # JPEG Lossless
                    '1.2.840.10008.1.2.4.70',  # JPEG Lossless SV1
                    '1.2.840.10008.1.2.4.80',  # JPEG-LS Lossless
                    '1.2.840.10008.1.2.4.81',  # JPEG-LS Lossy
                ]
                
                if original_ts not in compressed_syntaxes:
                    # No conversion needed
                    logging.info(f"No conversion needed for {os.path.basename(filepath)}: {original_ts}")
                    converted_files.append(filepath)
                    continue
                
                logging.info(f"Converting {os.path.basename(filepath)} from {original_ts}")
                
                # Update progress with conversion details
                self.conversion_progress.emit(idx + 1, total_files, f"Converting {os.path.basename(filepath)} - decompressing ({idx + 1}/{total_files})")
                
                # Create new dataset for conversion
                ds_converted = pydicom.Dataset()
                
                # Copy all non-pixel data elements
                for elem in ds_original:
                    if elem.tag != (0x7fe0, 0x0010):  # Skip PixelData for now
                        ds_converted[elem.tag] = elem
                
                # Handle pixel data conversion
                try:
                    # Update progress for pixel data processing
                    self.conversion_progress.emit(idx + 1, total_files, f"Converting {os.path.basename(filepath)} - processing pixels ({idx + 1}/{total_files})")
                    
                    # Force decompression by accessing pixel_array
                    pixel_array = ds_original.pixel_array
                    logging.info(f"Pixel array shape: {pixel_array.shape}, dtype: {pixel_array.dtype}")
                    
                    # Convert pixel array back to bytes in the correct format
                    if pixel_array.dtype != np.uint16 and ds_original.BitsAllocated == 16:
                        # Convert to uint16 if needed
                        pixel_array = pixel_array.astype(np.uint16)
                    elif pixel_array.dtype != np.uint8 and ds_original.BitsAllocated == 8:
                        # Convert to uint8 if needed
                        pixel_array = pixel_array.astype(np.uint8)
                    
                    # Convert back to bytes
                    pixel_bytes = pixel_array.tobytes()
                    
                    # Set the uncompressed pixel data
                    ds_converted.PixelData = pixel_bytes
                    
                    logging.info(f"Converted pixel data: {len(pixel_bytes)} bytes")
                    
                except Exception as e:
                    logging.error(f"Failed to convert pixel data for {filepath}: {e}")
                    converted_files.append(filepath)  # Use original
                    continue
                
                # Create proper file meta information for uncompressed format
                file_meta = pydicom.Dataset()
                
                # Copy essential file meta elements
                if hasattr(ds_original, 'file_meta'):
                    for elem in ds_original.file_meta:
                        if elem.tag != (0x0002, 0x0010):  # Skip TransferSyntaxUID
                            file_meta[elem.tag] = elem
                
                # Set transfer syntax to Explicit VR Little Endian (most compatible)
                file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
                file_meta.MediaStorageSOPClassUID = ds_converted.SOPClassUID
                file_meta.MediaStorageSOPInstanceUID = ds_converted.SOPInstanceUID
                
                # Ensure required file meta elements
                if not hasattr(file_meta, 'FileMetaInformationVersion'):
                    file_meta.FileMetaInformationVersion = b'\x00\x01'
                if not hasattr(file_meta, 'ImplementationClassUID'):
                    file_meta.ImplementationClassUID = pydicom.uid.PYDICOM_IMPLEMENTATION_UID
                if not hasattr(file_meta, 'ImplementationVersionName'):
                    file_meta.ImplementationVersionName = 'PYDICOM ' + pydicom.__version__
                
                # Assign file meta to dataset
                ds_converted.file_meta = file_meta
                
                # Update transfer syntax related elements in main dataset
                ds_converted.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
                
                # Create temp file
                temp_filepath = filepath + "_converted_explicit_vr.dcm"
                
                # Update progress for saving
                self.conversion_progress.emit(idx + 1, total_files, f"Converting {os.path.basename(filepath)} - saving ({idx + 1}/{total_files})")
                
                # Save the converted file
                ds_converted.save_as(temp_filepath, enforce_file_format=True)
                
                # Validate the converted file
                if self._validate_converted_file(temp_filepath, filepath):
                    converted_files.append(temp_filepath)
                    self.temp_files.append(temp_filepath)
                    self.converted_count += 1
                    logging.info(f"Successfully converted and validated {os.path.basename(filepath)}")
                else:
                    logging.warning(f"Converted file failed validation: {os.path.basename(filepath)}")
                    # Clean up failed conversion
                    try:
                        os.remove(temp_filepath)
                    except Exception as e:
                        logging.warning(f"Could not remove failed conversion file {temp_filepath}: {e}")
                    converted_files.append(filepath)  # Use original
                    
            except Exception as e:
                logging.error(f"Failed to convert {filepath}: {e}", exc_info=True)
                converted_files.append(filepath)  # Use original
        
        # Signal conversion complete
        self.conversion_progress.emit(total_files, total_files, "Conversion complete")
        
        return converted_files

    def _validate_converted_file(self, converted_path, original_path):
        """Validate that the converted file is readable and has correct pixel data"""
        try:
            # Read the converted file
            ds_converted = pydicom.dcmread(converted_path)
            ds_original = pydicom.dcmread(original_path)
            
            # Check basic DICOM validity
            if not hasattr(ds_converted, 'SOPInstanceUID'):
                logging.error("Converted file missing SOPInstanceUID")
                return False
            
            # Check transfer syntax
            converted_ts = str(ds_converted.file_meta.TransferSyntaxUID)
            if converted_ts != pydicom.uid.ExplicitVRLittleEndian:
                logging.error(f"Converted file has wrong transfer syntax: {converted_ts}")
                return False
            
            # Check pixel data accessibility
            try:
                pixel_array_converted = ds_converted.pixel_array
                pixel_array_original = ds_original.pixel_array
                
                # Check dimensions match
                if pixel_array_converted.shape != pixel_array_original.shape:
                    logging.error(f"Pixel array shapes don't match: {pixel_array_converted.shape} vs {pixel_array_original.shape}")
                    return False
                
                # Check data types are reasonable
                if pixel_array_converted.dtype not in [np.uint8, np.uint16, np.int16]:
                    logging.error(f"Unexpected pixel data type: {pixel_array_converted.dtype}")
                    return False
                
                logging.info(f"Validation passed: {pixel_array_converted.shape}, {pixel_array_converted.dtype}")
                return True
                
            except Exception as e:
                logging.error(f"Cannot access pixel data in converted file: {e}")
                return False
                
        except Exception as e:
            logging.error(f"Cannot read converted file {converted_path}: {e}")
            return False
    
    def _cleanup_temp_files(self):
        """Clean up temporary files"""
        for temp_file in self.temp_files:
            try:
                os.remove(temp_file)
                logging.info(f"Cleaned up temp file: {os.path.basename(temp_file)}")
            except Exception as e:
                logging.warning(f"Could not remove temp file {temp_file}: {e}")
    
    def cancel(self):
        """Cancel the sending operation"""
        self.cancelled = True