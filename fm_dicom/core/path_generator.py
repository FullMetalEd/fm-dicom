import logging
import pydicom


class DicomPathGenerator:
    """Generate DICOM standard file paths and structure"""
    
    @staticmethod
    def generate_paths(filepaths):
        """
        Generate DICOM standard file paths from input files
        Returns: dict mapping {original_path: "DICOM/PAT00001/STU00001/SER00001/IMG00001"}
        """
        logging.info(f"Generating DICOM standard paths for {len(filepaths)} files")
        
        # Analyze files to build hierarchy
        hierarchy = {}
        
        for filepath in filepaths:
            try:
                ds = pydicom.dcmread(filepath, stop_before_pixels=True)
                
                patient_id = str(getattr(ds, 'PatientID', 'UNKNOWN'))
                patient_name = str(getattr(ds, 'PatientName', 'UNKNOWN'))
                study_uid = str(getattr(ds, 'StudyInstanceUID', 'UNKNOWN'))
                study_desc = str(getattr(ds, 'StudyDescription', 'UNKNOWN'))
                series_uid = str(getattr(ds, 'SeriesInstanceUID', 'UNKNOWN'))
                series_desc = str(getattr(ds, 'SeriesDescription', 'UNKNOWN'))
                instance_uid = str(getattr(ds, 'SOPInstanceUID', 'UNKNOWN'))
                instance_number = getattr(ds, 'InstanceNumber', 1)
                
                # Create hierarchy key
                patient_key = f"{patient_id}^{patient_name}"
                study_key = f"{study_uid}^{study_desc}"
                series_key = f"{series_uid}^{series_desc}"
                
                # Build hierarchy
                if patient_key not in hierarchy:
                    hierarchy[patient_key] = {}
                if study_key not in hierarchy[patient_key]:
                    hierarchy[patient_key][study_key] = {}
                if series_key not in hierarchy[patient_key][study_key]:
                    hierarchy[patient_key][study_key][series_key] = []
                
                hierarchy[patient_key][study_key][series_key].append({
                    'filepath': filepath,
                    'instance_uid': instance_uid,
                    'instance_number': instance_number
                })
                
            except Exception as e:
                logging.warning(f"Could not read DICOM file {filepath}: {e}")
                continue
        
        # Generate sequential IDs and paths
        file_mapping = {}
        patient_counter = 1
        
        for patient_key, studies in hierarchy.items():
            patient_dir = f"PAT{patient_counter:05d}"
            study_counter = 1
            
            for study_key, series_dict in studies.items():
                study_dir = f"STU{study_counter:05d}"
                series_counter = 1
                
                for series_key, instances in series_dict.items():
                    series_dir = f"SER{series_counter:05d}"
                    
                    # Sort instances by instance number
                    instances.sort(key=lambda x: x['instance_number'])
                    
                    for instance_idx, instance_info in enumerate(instances):
                        instance_file = f"IMG{instance_idx + 1:05d}"
                        
                        dicom_path = f"DICOM/{patient_dir}/{study_dir}/{series_dir}/{instance_file}"
                        file_mapping[instance_info['filepath']] = dicom_path
                    
                    series_counter += 1
                study_counter += 1
            patient_counter += 1
        
        logging.info(f"Generated {len(file_mapping)} DICOM standard paths")
        return file_mapping