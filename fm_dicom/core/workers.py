import logging
import os
import shutil
import zipfile
import numpy as np
import pydicom

from PyQt6.QtCore import QThread, pyqtSignal

from pynetdicom import AE, AllStoragePresentationContexts
from pynetdicom.sop_class import Verification

from fm_dicom.core.dicomdir import DicomdirReader, DicomPathGenerator, DicomdirBuilder

VERIFICATION_SOP_CLASS = Verification
STORAGE_CONTEXTS = AllStoragePresentationContexts


class ZipExtractionWorker(QThread):
    """Worker thread for ZIP extraction with progress updates"""
    progress_updated = pyqtSignal(int, int, str)  # current, total, filename
    extraction_complete = pyqtSignal(str, list)  # temp_dir, extracted_files
    extraction_failed = pyqtSignal(str)  # error_message

    def __init__(self, zip_path, temp_dir):
        super().__init__()
        self.zip_path = zip_path
        self.temp_dir = temp_dir

    def run(self):
        try:
            with zipfile.ZipFile(self.zip_path, 'r') as zip_ref:
                file_list = zip_ref.namelist()
                total_files = len(file_list)
                extracted_files = []

                for i, filename in enumerate(file_list):
                    # Emit progress update
                    self.progress_updated.emit(i + 1, total_files, filename)

                    # Extract individual file
                    zip_ref.extract(filename, self.temp_dir)
                    extracted_path = os.path.join(self.temp_dir, filename)
                    extracted_files.append(extracted_path)

                    # Allow thread to be interrupted
                    if self.isInterruptionRequested():
                        break

                self.extraction_complete.emit(self.temp_dir, extracted_files)

        except Exception as e:
            error_msg = f"Failed to extract ZIP file: {str(e)}"
            self.extraction_failed.emit(error_msg)


class DicomdirScanWorker(QThread):
    """Worker thread for scanning DICOMDIR files"""
    progress_updated = pyqtSignal(int, int, str)  # current, total, current_file
    scan_complete = pyqtSignal(list)  # list of DICOM file paths
    scan_failed = pyqtSignal(str)  # error message

    def __init__(self, extracted_files):
        super().__init__()
        self.extracted_files = extracted_files

    def run(self):
        try:
            # First, find all DICOMDIR files
            dicomdir_files = []
            for file_path in self.extracted_files:
                if os.path.basename(file_path).upper() == 'DICOMDIR':
                    dicomdir_files.append(file_path)

            if not dicomdir_files:
                self.scan_failed.emit("No DICOMDIR files found in extracted archive")
                return

            # Process each DICOMDIR
            all_dicom_files = []
            reader = DicomdirReader()

            for idx, dicomdir_path in enumerate(dicomdir_files):
                self.progress_updated.emit(idx + 1, len(dicomdir_files),
                                         f"Reading {os.path.basename(dicomdir_path)}")

                file_paths = reader.read_dicomdir(dicomdir_path)
                all_dicom_files.extend(file_paths)

                if self.isInterruptionRequested():
                    break

            # Remove duplicates and verify files exist
            unique_files = []
            seen_files = set()

            for file_path in all_dicom_files:
                if file_path not in seen_files and os.path.exists(file_path):
                    unique_files.append(file_path)
                    seen_files.add(file_path)

            self.scan_complete.emit(unique_files)

        except Exception as e:
            self.scan_failed.emit(f"DICOMDIR scanning failed: {str(e)}")


class ExportWorker(QThread):
    """Background worker for file export operations"""
    progress_updated = pyqtSignal(int, int, str)  # current, total, current_operation
    stage_changed = pyqtSignal(str)  # stage_description
    export_complete = pyqtSignal(str, dict)  # output_path, statistics
    export_failed = pyqtSignal(str)  # error_message

    def __init__(self, filepaths, export_type, output_path, temp_dir=None):
        super().__init__()
        self.filepaths = filepaths
        self.export_type = export_type  # "directory", "zip", "zip_with_dicomdir"
        self.output_path = output_path
        self.temp_dir = temp_dir
        self.cancelled = False

    def run(self):
        try:
            if self.export_type == "directory":
                self._export_directory()
            elif self.export_type == "zip":
                self._export_zip()
            elif self.export_type == "zip_with_dicomdir":  # Fixed: changed from "dicomdir_zip"
                self._export_dicomdir_zip()
            else:
                raise ValueError(f"Unknown export type: {self.export_type}")

        except Exception as e:
            logging.error(f"Export worker failed: {e}", exc_info=True)
            self.export_failed.emit(str(e))

    def cancel(self):
        """Cancel the export operation"""
        self.cancelled = True

    def _export_directory(self):
        """Export files to directory"""
        self.stage_changed.emit("Exporting files to directory...")

        exported_count = 0
        errors = []
        total_files = len(self.filepaths)

        for idx, fp in enumerate(self.filepaths):
            if self.cancelled:
                return

            try:
                out_path = os.path.join(self.output_path, os.path.basename(fp))
                shutil.copy2(fp, out_path)
                exported_count += 1

                # Emit progress
                self.progress_updated.emit(idx + 1, total_files, f"Copying {os.path.basename(fp)}")

            except Exception as e:
                errors.append(f"Failed to export {os.path.basename(fp)}: {e}")
                logging.error(f"Failed to copy {fp}: {e}")

        # Calculate statistics
        stats = {
            'exported_count': exported_count,
            'total_files': total_files,
            'errors': errors,
            'export_type': 'Directory'
        }

        self.export_complete.emit(self.output_path, stats)

    def _export_zip(self):
        """Export files to ZIP archive"""
        self.stage_changed.emit("Creating ZIP archive...")

        zipped_count = 0
        errors = []
        total_files = len(self.filepaths)

        try:
            with zipfile.ZipFile(self.output_path, 'w', compression=zipfile.ZIP_DEFLATED) as zipf:
                for idx, fp in enumerate(self.filepaths):
                    if self.cancelled:
                        return

                    try:
                        zipf.write(fp, arcname=os.path.basename(fp))
                        zipped_count += 1

                        # Emit progress
                        self.progress_updated.emit(idx + 1, total_files, f"Adding {os.path.basename(fp)}")

                    except Exception as e:
                        errors.append(f"Failed to add {os.path.basename(fp)}: {e}")
                        logging.error(f"Failed to add to ZIP {fp}: {e}")

        except Exception as e:
            self.export_failed.emit(f"Failed to create ZIP: {e}")
            return

        # Calculate statistics
        stats = {
            'exported_count': zipped_count,
            'total_files': total_files,
            'errors': errors,
            'export_type': 'ZIP'
        }

        self.export_complete.emit(self.output_path, stats)

    def _export_dicomdir_zip(self):
        """Export files as ZIP with DICOMDIR"""
        # Use the output path that was already determined in the main thread
        out_zip_path = self.output_path

        if not out_zip_path.lower().endswith('.zip'):
            out_zip_path += '.zip'
            self.output_path = out_zip_path  # Update the stored path

        # Ensure we have a temporary directory
        if self.temp_dir is None:
            import tempfile
            self.temp_dir = tempfile.mkdtemp()
            cleanup_temp = True
        else:
            cleanup_temp = False

        try:
            # Step 1: Analyze files (10%)
            self.stage_changed.emit("Analyzing DICOM files...")
            self.progress_updated.emit(10, 100, "Analyzing file structure...")

            if self.cancelled:
                return

            path_generator = DicomPathGenerator()
            file_mapping = path_generator.generate_paths(self.filepaths)

            if not file_mapping:
                raise Exception("No valid DICOM files found for export")

            # Step 2: Copy files to structure (20-70%)
            self.stage_changed.emit("Creating DICOM directory structure...")
            copied_mapping = self._copy_files_to_dicom_structure(file_mapping)

            if self.cancelled:
                return

            # Step 3: Generate DICOMDIR (70-80%)
            self.stage_changed.emit("Generating DICOMDIR...")
            self.progress_updated.emit(75, 100, "Creating DICOMDIR file...")

            builder = DicomdirBuilder("DICOM_EXPORT")
            builder.add_dicom_files(copied_mapping)
            dicomdir_path = os.path.join(self.temp_dir, "DICOMDIR")
            builder.generate_dicomdir(dicomdir_path)

            if self.cancelled:
                return

            # Step 4: Create ZIP (80-100%)
            self.stage_changed.emit("Creating ZIP archive...")
            self._create_zip_from_temp_directory()

            # Calculate statistics
            total_size = sum(os.path.getsize(f) for f in self.filepaths if os.path.exists(f))
            stats = {
                'exported_count': len(file_mapping),
                'total_files': len(self.filepaths),
                'total_size_mb': total_size / (1024 * 1024),
                'patients': len(set(self._extract_patient_ids())),
                'errors': [],
                'export_type': 'DICOMDIR ZIP'
            }

            self.export_complete.emit(self.output_path, stats)

        except Exception as e:
            self.export_failed.emit(f"DICOMDIR ZIP export failed: {e}")
        finally:
            # Clean up temporary directory if we created it
            if cleanup_temp and self.temp_dir and os.path.exists(self.temp_dir):
                import shutil
                shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _copy_files_to_dicom_structure(self, file_mapping):
        """Copy files to DICOM standard structure with progress updates"""
        copied_mapping = {}
        total_files = len(file_mapping)

        for idx, (original_path, dicom_path) in enumerate(file_mapping.items()):
            if self.cancelled:
                break

            full_target_path = os.path.join(self.temp_dir, dicom_path)

            try:
                # Create directory structure
                os.makedirs(os.path.dirname(full_target_path), exist_ok=True)

                # Copy file
                shutil.copy2(original_path, full_target_path)
                copied_mapping[original_path] = full_target_path

            except Exception as e:
                logging.error(f"Failed to copy {original_path}: {e}")
                continue

            # Update progress (20% to 70% range)
            file_progress = 20 + int((idx + 1) / total_files * 50)
            self.progress_updated.emit(file_progress, 100, f"Copying {os.path.basename(original_path)}")

        return copied_mapping

    def _create_zip_from_temp_directory(self):
        """Create ZIP from temporary directory with progress"""
        # Get all files in temp directory
        all_files = []
        for root, dirs, files in os.walk(self.temp_dir):
            for file in files:
                all_files.append(os.path.join(root, file))

        total_files = len(all_files)

        with zipfile.ZipFile(self.output_path, 'w', compression=zipfile.ZIP_DEFLATED) as zipf:
            for idx, file_path in enumerate(all_files):
                if self.cancelled:
                    break

                arcname = os.path.relpath(file_path, self.temp_dir)
                zipf.write(file_path, arcname)

                # Update progress (80% to 100% range)
                zip_progress = 80 + int((idx + 1) / total_files * 20)
                self.progress_updated.emit(zip_progress, 100, f"Adding {os.path.basename(file_path)} to ZIP")

    def _extract_patient_ids(self):
        """Extract unique patient IDs from file list"""
        patient_ids = []
        for fp in self.filepaths:
            try:
                ds = pydicom.dcmread(fp, stop_before_pixels=True)
                patient_id = str(getattr(ds, 'PatientID', 'UNKNOWN'))
                patient_ids.append(patient_id)
            except:
                pass
        return patient_ids


class DicomSendWorker(QThread):
    """Background worker for DICOM sending with auto-conversion on format rejection"""
    progress_updated = pyqtSignal(int, int, int, int, str)  # current, success, warnings, failed, current_file
    send_complete = pyqtSignal(int, int, int, list, int)  # success, warnings, failed, error_details, converted_count
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

    def run(self):
        try:
            logging.info("DicomSendWorker: Starting run() method")

            # First attempt: try with original formats
            self.association_status.emit("Testing server compatibility...")
            logging.info("DicomSendWorker: About to attempt initial send")

            result = self._attempt_send_with_formats(self.filepaths, test_mode=True)
            logging.info(f"DicomSendWorker: Initial send result: {result is not None}")

            if result is None:  # Cancelled
                logging.info("DicomSendWorker: Send was cancelled")
                return

            success, warnings, failed, error_details, incompatible_files = result
            logging.info(f"DicomSendWorker: Initial results - Success: {success}, Failed: {failed}, Incompatible: {len(incompatible_files)}")

            # If some files failed due to format issues, try converting them
            if incompatible_files:
                logging.info(f"DicomSendWorker: Converting {len(incompatible_files)} incompatible files")
                self.association_status.emit(f"Converting {len(incompatible_files)} incompatible files...")
                converted_files = self._convert_incompatible_files(incompatible_files)
                logging.info(f"DicomSendWorker: Conversion complete, got {len(converted_files)} converted files")

                if converted_files and not self.cancelled:
                    # Retry with converted files
                    logging.info("DicomSendWorker: Retrying with converted files")
                    self.association_status.emit("Retrying with converted files...")
                    retry_result = self._attempt_send_with_formats(converted_files, test_mode=False)

                    if retry_result:
                        retry_success, retry_warnings, retry_failed, retry_errors, _ = retry_result
                        success += retry_success
                        warnings += retry_warnings
                        failed += retry_failed
                        error_details.extend(retry_errors)
                        logging.info(f"DicomSendWorker: Retry complete - Total success: {success}")

            logging.info("DicomSendWorker: About to emit send_complete signal")
            # Send completion signal
            self.send_complete.emit(success, warnings, failed, error_details, self.converted_count)
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
            except:
                pass

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

    def _convert_incompatible_files(self, filepaths):
        """Convert incompatible files to standard uncompressed format with validation"""
        converted_files = []
        total_files = len(filepaths)

        for idx, filepath in enumerate(filepaths):
            if self.cancelled:
                break

            # Emit conversion progress
            self.conversion_progress.emit(idx, total_files, os.path.basename(filepath))

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

                # Create new dataset for conversion
                ds_converted = pydicom.Dataset()

                # Copy all non-pixel data elements
                for elem in ds_original:
                    if elem.tag != (0x7fe0, 0x0010):  # Skip PixelData for now
                        ds_converted[elem.tag] = elem

                # Handle pixel data conversion
                try:
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
                    except:
                        pass
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
