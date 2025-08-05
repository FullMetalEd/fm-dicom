import os
import shutil
import zipfile
import logging
import pydicom
from PyQt6.QtCore import QThread, pyqtSignal
from fm_dicom.core.path_generator import DicomPathGenerator
from fm_dicom.core.dicomdir_builder import DicomdirBuilder


class ExportWorker(QThread):
    """Background worker for file export operations"""
    progress_updated = pyqtSignal(int, int, str)  # current, total, current_operation
    stage_changed = pyqtSignal(str)  # stage_description
    export_complete = pyqtSignal(str, dict)  # output_path, statistics
    export_failed = pyqtSignal(str)  # error_message
    
    def __init__(self, filepaths, export_type, output_path, temp_dir=None):
        super().__init__()
        self.filepaths = filepaths
        self.export_type = export_type  # "directory", "zip", "dicomdir_zip"
        self.output_path = output_path
        self.temp_dir = temp_dir
        self.cancelled = False
        
    def run(self):
        try:
            if self.export_type == "directory":
                self._export_directory()
            elif self.export_type == "zip":
                self._export_zip()
            elif self.export_type == "dicomdir_zip":
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
            except Exception as e:
                import logging
                logging.debug(f"Could not read patient ID from {fp}: {e}")
                patient_ids.append('UNKNOWN')
        return patient_ids