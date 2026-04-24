"""
DICOM Send related jobs for Task Center.
"""

import logging
import os
import pydicom
from fm_dicom.managers.job_manager import BaseJob

class SendTreePopulateJob(BaseJob):
    """Background job for populating the DICOM Send selection tree."""
    
    def __init__(self, loaded_files, hierarchy_data, memory_items=None):
        super().__init__("Preparing Send Selection")
        self.loaded_files = loaded_files
        self.hierarchy_data = hierarchy_data
        self.memory_items = memory_items or {}
        self.results = None

    def run(self):
        self.start_timer()
        try:
            # Reusing AsyncTreePopulator logic but as a Job
            if self.hierarchy_data:
                self.signals.progress.emit(0, 100, "Converting hierarchy data...")
                hierarchy = self._convert_hierarchy_data(self.hierarchy_data)
                self.signals.progress.emit(100, 100, "Hierarchy converted")
            else:
                self.signals.progress.emit(0, 100, "Building hierarchy from files...")
                hierarchy = self._build_hierarchy_from_loaded_files()
                self.signals.progress.emit(100, 100, "Hierarchy built")
            
            self.stop_timer()
            if self.is_cancelled():
                return
            
            self.results = hierarchy
            self.signals.finished.emit(hierarchy)
            
        except Exception as e:
            self.stop_timer()
            logging.error(f"SendTreePopulateJob failed: {e}", exc_info=True)
            self.signals.failed.emit(str(e))

    def _convert_hierarchy_data(self, hierarchy_data):
        """Convert TreeManager hierarchy format to selection dialog format"""
        converted_hierarchy = {}
        for patient_label, patient_data in hierarchy_data.items():
            if self.is_cancelled(): break
            for study_label, study_data in patient_data.items():
                for series_label, series_data in study_data.items():
                    for instance_label, instance_data in series_data.items():
                        # Extract simple path
                        path = instance_data['filepath']
                        
                        # Use simplified labels for selection tree
                        # Patient -> Study -> Series
                        patient = patient_label
                        study = study_label
                        series = series_label
                        
                        converted_hierarchy.setdefault(patient, {}).setdefault(
                            study, {}).setdefault(series, {})[instance_label] = path
        return converted_hierarchy

    def _build_hierarchy_from_loaded_files(self):
        """Build hierarchy from raw loaded files list"""
        hierarchy = {}
        total = len(self.loaded_files)
        
        for idx, file_info in enumerate(self.loaded_files):
            if self.is_cancelled(): break
            
            filepath = file_info[0] if isinstance(file_info, tuple) else file_info
            self.signals.progress.emit(idx + 1, total, f"Reading: {os.path.basename(filepath)}")
            
            try:
                if filepath in self.memory_items:
                    ds = self.memory_items[filepath]
                else:
                    ds = pydicom.dcmread(filepath, stop_before_pixels=True)
                
                patient = f"{getattr(ds, 'PatientName', 'Unknown')} ({getattr(ds, 'PatientID', 'Unknown')})"
                study = f"{getattr(ds, 'StudyDescription', 'No Study')} [{getattr(ds, 'StudyInstanceUID', 'Unknown')}]"
                series = f"{getattr(ds, 'SeriesDescription', 'No Series')} [{getattr(ds, 'SeriesInstanceUID', 'Unknown')}]"
                instance = f"Instance {getattr(ds, 'InstanceNumber', '0')} [{getattr(ds, 'SOPInstanceUID', os.path.basename(filepath))}]"
                
                hierarchy.setdefault(patient, {}).setdefault(
                    study, {}).setdefault(series, {})[instance] = filepath
            except Exception:
                continue
        return hierarchy
