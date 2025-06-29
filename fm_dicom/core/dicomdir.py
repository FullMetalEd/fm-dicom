import logging
import os
import pydicom
from pydicom.uid import generate_uid


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
                        logging.debug(f"DEBUG: Joined path components {list(file_id)} -> {relative_path}")
                    else:
                        relative_path = str(file_id)
                        logging.debug(f"DEBUG: Used string conversion: {relative_path}")

                    # Convert to absolute path
                    full_path = os.path.join(self.base_directory, relative_path)

                    # Normalize path separators for current OS
                    full_path = os.path.normpath(full_path)

                    logging.debug(f"DEBUG: Final path: {full_path}")

                    # Check if file exists
                    if os.path.exists(full_path):
                        return full_path
                    else:
                        logging.warning(f"DICOMDIR references missing file: {full_path}")

        except Exception as e:
            logging.warning(f"Failed to extract file path from directory record: {e}")

        return None


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


class DicomdirBuilder:
    """Build valid DICOMDIR files using DICOM standard"""

    def __init__(self, file_set_id="DICOM_EXPORT"):
        self.file_set_id = file_set_id
        self.patients = {}
        self.studies = {}
        self.series = {}
        self.images = []

    def debug_dicomdir_structure(self, file_mapping):
        """Debug the DICOMDIR structure to see what patients/studies/series we have"""

        logging.info("=== DICOMDIR STRUCTURE DEBUG ===")

        # Analyze the original files to see patient distribution
        patient_analysis = {}

        for original_path, copied_path in file_mapping.items():
            try:
                ds = pydicom.dcmread(original_path, stop_before_pixels=True)
                patient_id = str(getattr(ds, 'PatientID', 'UNKNOWN'))
                patient_name = str(getattr(ds, 'PatientName', 'UNKNOWN'))
                study_uid = str(getattr(ds, 'StudyInstanceUID', 'UNKNOWN'))

                if patient_id not in patient_analysis:
                    patient_analysis[patient_id] = {
                        'name': patient_name,
                        'studies': set(),
                        'file_count': 0
                    }

                patient_analysis[patient_id]['studies'].add(study_uid)
                patient_analysis[patient_id]['file_count'] += 1

            except Exception as e:
                logging.warning(f"Could not analyze file {original_path}: {e}")

        logging.info(f"Found {len(patient_analysis)} unique patients in source files:")
        for patient_id, info in patient_analysis.items():
            logging.info(f"  Patient '{patient_id}' ({info['name']}): {info['file_count']} files, {len(info['studies'])} studies")

        # Now check our internal structure
        logging.info(f"DicomdirBuilder internal structure:")
        logging.info(f"  Patients: {len(self.patients)}")
        for patient_id, patient_info in self.patients.items():
            study_count = len(patient_info.get('studies', []))
            logging.info(f"    Patient '{patient_id}': {study_count} studies")

        logging.info(f"  Studies: {len(self.studies)}")
        logging.info(f"  Series: {len(self.series)}")
        logging.info(f"  Images: {len(self.images)}")

        logging.info("=== END DEBUG ===")

    def add_dicom_files(self, file_mapping):
        """
        Analyze copied files and build directory structure
        file_mapping: dict of {original_path: copied_path}
        """
        logging.info(f"Building DICOMDIR structure for {len(file_mapping)} files")

        # Reset structures to avoid accumulation from previous calls
        self.patients = {}
        self.studies = {}
        self.series = {}
        self.images = []

        for original_path, copied_path in file_mapping.items():
            try:
                ds = pydicom.dcmread(original_path, stop_before_pixels=True)

                # Extract metadata with proper defaults
                patient_id = str(getattr(ds, 'PatientID', 'UNKNOWN'))
                patient_name = str(getattr(ds, 'PatientName', 'UNKNOWN'))
                study_uid = str(getattr(ds, 'StudyInstanceUID', generate_uid()))
                study_desc = str(getattr(ds, 'StudyDescription', ''))
                study_date = str(getattr(ds, 'StudyDate', ''))
                study_time = str(getattr(ds, 'StudyTime', ''))
                study_id = str(getattr(ds, 'StudyID', ''))
                series_uid = str(getattr(ds, 'SeriesInstanceUID', generate_uid()))
                series_desc = str(getattr(ds, 'SeriesDescription', ''))
                series_number = str(getattr(ds, 'SeriesNumber', '1'))
                modality = str(getattr(ds, 'Modality', 'OT'))
                sop_class_uid = str(getattr(ds, 'SOPClassUID', ''))
                sop_instance_uid = str(getattr(ds, 'SOPInstanceUID', generate_uid()))
                transfer_syntax = str(getattr(ds.file_meta, 'TransferSyntaxUID', '1.2.840.10008.1.2'))
                instance_number = str(getattr(ds, 'InstanceNumber', '1'))

                logging.debug(f"Processing file: PatientID='{patient_id}', StudyUID='{study_uid[:8]}...', SeriesUID='{series_uid[:8]}...' ")

                # Store patient info (create if doesn't exist)
                if patient_id not in self.patients:
                    self.patients[patient_id] = {
                        'PatientID': patient_id,
                        'PatientName': patient_name,
                        'studies': []
                    }
                    logging.debug(f"Created new patient: {patient_id}")

                # Store study info (create if doesn't exist)
                study_key = f"{patient_id}#{study_uid}"
                if study_key not in self.studies:
                    self.studies[study_key] = {
                        'StudyInstanceUID': study_uid,
                        'StudyDescription': study_desc,
                        'StudyDate': study_date,
                        'StudyTime': study_time,
                        'StudyID': study_id,
                        'PatientID': patient_id,
                        'series': []
                    }
                    # Link study to patient
                    if study_key not in self.patients[patient_id]['studies']:
                        self.patients[patient_id]['studies'].append(study_key)
                    logging.debug(f"Created new study: {study_key}")

                # Store series info (create if doesn't exist)
                series_key = f"{study_key}#{series_uid}"
                if series_key not in self.series:
                    self.series[series_key] = {
                        'SeriesInstanceUID': series_uid,
                        'SeriesDescription': series_desc,
                        'SeriesNumber': series_number,
                        'Modality': modality,
                        'StudyInstanceUID': study_uid,
                        'PatientID': patient_id,
                        'images': []
                    }
                    # Link series to study
                    if series_key not in self.studies[study_key]['series']:
                        self.studies[study_key]['series'].append(series_key)
                    logging.debug(f"Created new series: {series_key}")

                # Convert file path to DICOMDIR-relative path
                base_dir = os.path.dirname(copied_path)
                while not os.path.basename(base_dir) or os.path.basename(base_dir) != 'DICOM':
                    parent_dir = os.path.dirname(base_dir)
                    if parent_dir == base_dir:  # Reached root
                        break
                    base_dir = parent_dir

                # Create relative path from DICOMDIR location to image file
                dicomdir_base = os.path.dirname(base_dir)  # Parent of DICOM folder
                rel_path = os.path.relpath(copied_path, dicomdir_base)

                # Convert to DICOM file ID format (array of path components)
                path_components = rel_path.replace('\\', '/').split('/')

                # Store image info
                image_info = {
                    'ReferencedFileID': path_components,
                    'ReferencedSOPClassUIDInFile': sop_class_uid,
                    'ReferencedSOPInstanceUIDInFile': sop_instance_uid,
                    'ReferencedTransferSyntaxUIDInFile': transfer_syntax,
                    'InstanceNumber': instance_number,
                    'SeriesInstanceUID': series_uid,
                    'StudyInstanceUID': study_uid,
                    'PatientID': patient_id,
                    'copied_path': copied_path
                }

                self.images.append(image_info)
                # Link image to series
                self.series[series_key]['images'].append(image_info)

            except Exception as e:
                logging.warning(f"Could not process file {original_path} for DICOMDIR: {e}")
                continue

        # Debug the final structure
        self.debug_dicomdir_structure(file_mapping)

        logging.info(f"DICOMDIR structure: {len(self.patients)} patients, {len(self.studies)} studies, {len(self.series)} series, {len(self.images)} images")

    def generate_dicomdir(self, output_path):
        """Generate valid DICOMDIR file"""
        logging.info(f"Generating DICOMDIR at {output_path}")

        try:
            # Create base DICOMDIR dataset
            ds = self._create_base_dataset()

            # Build directory record sequence with proper linking
            ds.DirectoryRecordSequence = self._build_directory_records()

            # Set file set information
            ds.OffsetOfTheFirstDirectoryRecordOfTheRootDirectoryEntity = 0
            ds.OffsetOfTheLastDirectoryRecordOfTheRootDirectoryEntity = 0

            # Save DICOMDIR
            ds.save_as(output_path, enforce_file_format=True)
            logging.info("DICOMDIR created successfully")

        except Exception as e:
            logging.error(f"Failed to generate DICOMDIR: {e}")
            raise

    def _create_base_dataset(self):
        """Create base DICOMDIR dataset with all required elements"""
        ds = pydicom.Dataset()

        # File Meta Information
        ds.file_meta = pydicom.Dataset()
        ds.file_meta.MediaStorageSOPClassUID = "1.2.840.10008.1.3.10"  # Media Storage Directory Storage
        ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
        ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
        ds.file_meta.ImplementationClassUID = pydicom.uid.PYDICOM_IMPLEMENTATION_UID
        ds.file_meta.ImplementationVersionName = f"PYDICOM {pydicom.__version__}"
        ds.file_meta.FileMetaInformationVersion = b'\x00\x01'

        # Sanitize FileSetID for CS VR (Code String)
        # CS VR only allows: A-Z, 0-9, space, underscore
        sanitized_file_set_id = self._sanitize_for_cs_vr(self.file_set_id)

        # Required main dataset elements
        ds.FileSetID = sanitized_file_set_id[:16]  # Limit to 16 characters max
        ds.FileSetDescriptorFileID = ""  # No descriptor file
        ds.SpecificCharacterSet = "ISO_IR 100"
        ds.FileSetConsistencyFlag = 0x0000  # No known inconsistencies

        # Remove the invalid FileSetGroupLength attribute
        # This is not a standard DICOM attribute

        return ds

    def _sanitize_for_cs_vr(self, value):
        """
        Sanitize string for Code String (CS) VR
        CS VR allows only: A-Z, 0-9, space, underscore
        """
        if not value:
            return "DICOM_EXPORT"

        # Convert to uppercase
        sanitized = value.upper()

        # Replace invalid characters with underscore
        valid_chars = []
        for char in sanitized:
            if char.isalnum() or char in ' _':
                valid_chars.append(char)
            else:
                valid_chars.append('_')

        result = ''.join(valid_chars)

        # Ensure it's not empty and doesn't start/end with spaces
        result = result.strip()
        if not result:
            result = "DICOM_EXPORT"

        # Replace multiple consecutive underscores with single underscore
        while '__' in result:
            result = result.replace('__', '_')

        logging.debug(f"Sanitized FileSetID: '{value}' -> '{result}'")
        return result

    def _build_directory_records(self):
        """Build properly linked directory records"""
        records = []

        # Sort patients for consistent ordering
        sorted_patients = sorted(self.patients.items())

        logging.info(f"Building directory records for {len(sorted_patients)} patients")

        for patient_id, patient_info in sorted_patients:
            logging.debug(f"Processing patient: {patient_id}")

            # Create PATIENT record
            patient_record = self._create_patient_record(patient_info)
            records.append(patient_record)

            # Get studies for this patient
            study_keys = patient_info.get('studies', [])
            logging.debug(f"  Patient {patient_id} has {len(study_keys)} studies")

            sorted_studies = sorted([(k, self.studies[k]) for k in study_keys],
                                key=lambda x: x[1].get('StudyDate', ''))

            for study_key, study_info in sorted_studies:
                logging.debug(f"  Processing study: {study_info['StudyInstanceUID'][:8]}...")

                # Create STUDY record
                study_record = self._create_study_record(study_info)
                records.append(study_record)

                # Get series for this study
                series_keys = study_info.get('series', [])
                logging.debug(f"    Study has {len(series_keys)} series")

                sorted_series = sorted([(k, self.series[k]) for k in series_keys],
                                    key=lambda x: int(x[1].get('SeriesNumber', '0')))

                for series_key, series_info in sorted_series:
                    logging.debug(f"    Processing series: {series_info['SeriesInstanceUID'][:8]}...")

                    # Create SERIES record
                    series_record = self._create_series_record(series_info)
                    records.append(series_record)

                    # Get images for this series
                    images = series_info.get('images', [])
                    logging.debug(f"      Series has {len(images)} images")

                    sorted_images = sorted(images, key=lambda x: int(x.get('InstanceNumber', '0')))

                    for image_info in sorted_images:
                        # Create IMAGE record
                        image_record = self._create_image_record(image_info)
                        records.append(image_record)

        logging.info(f"Built {len(records)} directory records total")
        return records

    def _create_patient_record(self, patient_info):
        """Create PATIENT directory record"""
        record = pydicom.Dataset()
        record.OffsetOfTheNextDirectoryRecord = 0
        record.RecordInUseFlag = 0xFFFF
        record.OffsetOfReferencedLowerLevelDirectoryEntity = 0
        record.DirectoryRecordType = "PATIENT"

        # Required PATIENT level attributes
        record.PatientID = patient_info['PatientID'][:64]  # Limit length
        record.PatientName = patient_info['PatientName'][:320]  # Limit length

        return record

    def _create_study_record(self, study_info):
        """Create STUDY directory record"""
        record = pydicom.Dataset()
        record.OffsetOfTheNextDirectoryRecord = 0
        record.RecordInUseFlag = 0xFFFF
        record.OffsetOfReferencedLowerLevelDirectoryEntity = 0
        record.DirectoryRecordType = "STUDY"

        # Required STUDY level attributes
        record.StudyInstanceUID = study_info['StudyInstanceUID']

        # Optional but recommended STUDY attributes
        if study_info.get('StudyDate'):
            record.StudyDate = study_info['StudyDate'][:8]  # YYYYMMDD format
        if study_info.get('StudyTime'):
            record.StudyTime = study_info['StudyTime'][:16]  # HHMMSS.FFFFFF format
        if study_info.get('StudyDescription'):
            record.StudyDescription = study_info['StudyDescription'][:64]
        if study_info.get('StudyID'):
            record.StudyID = study_info['StudyID'][:16]

        return record

    def _create_series_record(self, series_info):
        """Create SERIES directory record"""
        record = pydicom.Dataset()
        record.OffsetOfTheNextDirectoryRecord = 0
        record.RecordInUseFlag = 0xFFFF
        record.OffsetOfReferencedLowerLevelDirectoryEntity = 0
        record.DirectoryRecordType = "SERIES"

        # Required SERIES level attributes
        record.SeriesInstanceUID = series_info['SeriesInstanceUID']
        record.Modality = series_info['Modality'][:16]  # Limit length

        # Optional but recommended SERIES attributes
        if series_info.get('SeriesNumber'):
            record.SeriesNumber = series_info['SeriesNumber'][:12]
        if series_info.get('SeriesDescription'):
            record.SeriesDescription = series_info['SeriesDescription'][:64]

        return record

    def _create_image_record(self, image_info):
        """Create IMAGE directory record"""
        record = pydicom.Dataset()
        record.OffsetOfTheNextDirectoryRecord = 0
        record.RecordInUseFlag = 0xFFFF
        record.OffsetOfReferencedLowerLevelDirectoryEntity = 0
        record.DirectoryRecordType = "IMAGE"

        # Required IMAGE level attributes
        record.ReferencedFileID = image_info['ReferencedFileID']
        record.ReferencedSOPClassUIDInFile = image_info['ReferencedSOPClassUIDInFile']
        record.ReferencedSOPInstanceUIDInFile = image_info['ReferencedSOPInstanceUIDInFile']
        record.ReferencedTransferSyntaxUIDInFile = image_info['ReferencedTransferSyntaxUIDInFile']

        # Optional but recommended IMAGE attributes
        if image_info.get('InstanceNumber'):
            record.InstanceNumber = image_info['InstanceNumber'][:12]

        return record
