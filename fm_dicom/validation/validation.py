"""
DICOM Validation Framework
Provides comprehensive validation of DICOM files and collections.
"""

import os
import logging
import pydicom
from datetime import datetime
from collections import defaultdict, Counter
from typing import List, Dict, Any, Optional, Tuple
import re

class ValidationSeverity:
    ERROR = "Error"
    WARNING = "Warning" 
    INFO = "Info"

class ValidationIssue:
    def __init__(self, severity: str, category: str, message: str, tag: Optional[str] = None, 
                 file_path: Optional[str] = None, suggested_fix: Optional[str] = None):
        self.severity = severity
        self.category = category
        self.message = message
        self.tag = tag
        self.file_path = file_path
        self.suggested_fix = suggested_fix
        self.timestamp = datetime.now()

    def __str__(self):
        return f"[{self.severity}] {self.category}: {self.message}"

class ValidationResult:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.issues: List[ValidationIssue] = []
        self.is_valid_dicom = True
        self.dataset = None
        
    def add_issue(self, severity: str, category: str, message: str, tag: Optional[str] = None, 
                  suggested_fix: Optional[str] = None):
        issue = ValidationIssue(severity, category, message, tag, self.file_path, suggested_fix)
        self.issues.append(issue)
        
    def has_errors(self) -> bool:
        return any(issue.severity == ValidationSeverity.ERROR for issue in self.issues)
        
    def has_warnings(self) -> bool:
        return any(issue.severity == ValidationSeverity.WARNING for issue in self.issues)
        
    def get_issues_by_severity(self, severity: str) -> List[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == severity]

class CollectionValidationResult:
    def __init__(self):
        self.file_results: Dict[str, ValidationResult] = {}
        self.collection_issues: List[ValidationIssue] = []
        self.statistics = {}
        
    def add_file_result(self, result: ValidationResult):
        self.file_results[result.file_path] = result
        
    def add_collection_issue(self, severity: str, category: str, message: str, 
                           suggested_fix: Optional[str] = None):
        issue = ValidationIssue(severity, category, message, suggested_fix=suggested_fix)
        self.collection_issues.append(issue)
        
    def get_summary(self) -> Dict[str, int]:
        total_files = len(self.file_results)
        files_with_errors = sum(1 for result in self.file_results.values() if result.has_errors())
        files_with_warnings = sum(1 for result in self.file_results.values() if result.has_warnings())
        total_errors = sum(len(result.get_issues_by_severity(ValidationSeverity.ERROR)) 
                          for result in self.file_results.values()) + \
                      len([issue for issue in self.collection_issues 
                          if issue.severity == ValidationSeverity.ERROR])
        total_warnings = sum(len(result.get_issues_by_severity(ValidationSeverity.WARNING)) 
                           for result in self.file_results.values()) + \
                        len([issue for issue in self.collection_issues 
                            if issue.severity == ValidationSeverity.WARNING])
        
        return {
            'total_files': total_files,
            'files_with_errors': files_with_errors,
            'files_with_warnings': files_with_warnings,
            'total_errors': total_errors,
            'total_warnings': total_warnings,
            'valid_files': total_files - files_with_errors
        }

class ValidationRule:
    """Base class for validation rules"""
    def __init__(self, name: str, description: str, category: str):
        self.name = name
        self.description = description
        self.category = category
        
    def validate_dataset(self, dataset: pydicom.Dataset, file_path: str) -> List[ValidationIssue]:
        """Validate a single DICOM dataset - override in individual file rules"""
        return []  # Default: no issues for individual files
        
    def validate_collection(self, datasets: List[Tuple[pydicom.Dataset, str]]) -> List[ValidationIssue]:
        """Validate across multiple datasets - override in collection rules"""
        return []  # Default: no collection-level validation

class DicomValidator:
    def __init__(self):
        self.rules: List[ValidationRule] = []
        self.load_standard_rules()
        logging.info("DICOM Validator initialized with %d rules", len(self.rules))
        
    def load_standard_rules(self):
        """Load all standard validation rules"""
        # Required tags rules
        self.rules.append(RequiredTagsRule())
        self.rules.append(UIDFormatRule())
        self.rules.append(DateTimeFormatRule())
        self.rules.append(PersonNameFormatRule())
        self.rules.append(ValueRepresentationRule())
        
        # Collection-level rules
        self.rules.append(DuplicateUIDRule())
        self.rules.append(StudyConsistencyRule())
        self.rules.append(SeriesConsistencyRule())
        
        # Modality-specific rules
        self.rules.append(ModalitySpecificRule())
        
        # Data integrity rules
        self.rules.append(PixelDataRule())
        self.rules.append(TransferSyntaxRule())
        
    def add_rule(self, rule: ValidationRule):
        """Add a custom validation rule"""
        self.rules.append(rule)
        
    def validate_file(self, file_path: str) -> ValidationResult:
        """Validate a single DICOM file"""
        result = ValidationResult(file_path)
        
        # Check if file exists
        if not os.path.exists(file_path):
            result.add_issue(ValidationSeverity.ERROR, "File System", 
                        f"File does not exist: {file_path}")
            return result
            
        # Try to read as DICOM
        try:
            dataset = pydicom.dcmread(file_path, force=True)
            result.dataset = dataset
        except Exception as e:
            result.is_valid_dicom = False
            result.add_issue(ValidationSeverity.ERROR, "DICOM Format", 
                        f"Cannot read as DICOM file: {str(e)}",
                        suggested_fix="Verify file is valid DICOM format")
            return result
            
        # Apply only individual file validation rules (not collection rules)
        individual_rules = [
            rule for rule in self.rules 
            if not self._is_collection_rule(rule)
        ]
        
        for rule in individual_rules:
            try:
                issues = rule.validate_dataset(dataset, file_path)
                result.issues.extend(issues)
            except Exception as e:
                logging.error(f"Error applying rule {rule.name} to {file_path}: {e}")
                result.add_issue(ValidationSeverity.WARNING, "Validation Error",
                            f"Rule '{rule.name}' failed: {str(e)}")
                
        return result

    def _is_collection_rule(self, rule) -> bool:
        """Check if a rule is a collection-level rule"""
        collection_rule_types = [
            'DuplicateUIDRule',
            'StudyConsistencyRule', 
            'SeriesConsistencyRule'
        ]
        return rule.__class__.__name__ in collection_rule_types
        
    def validate_collection(self, file_paths: List[str]) -> CollectionValidationResult:
        """Validate a collection of DICOM files"""
        collection_result = CollectionValidationResult()
        valid_datasets = []
        
        # Validate individual files
        for file_path in file_paths:
            file_result = self.validate_file(file_path)
            collection_result.add_file_result(file_result)
            
            if file_result.dataset is not None:
                valid_datasets.append((file_result.dataset, file_path))
                
        # Apply only collection-level rules
        collection_rules = [
            rule for rule in self.rules 
            if self._is_collection_rule(rule)
        ]
        
        for rule in collection_rules:
            try:
                collection_issues = rule.validate_collection(valid_datasets)
                collection_result.collection_issues.extend(collection_issues)
            except Exception as e:
                logging.error(f"Error applying collection rule {rule.name}: {e}")
                
        # Generate statistics
        collection_result.statistics = self._generate_statistics(valid_datasets)
        
        return collection_result
        
    def _generate_statistics(self, datasets: List[Tuple[pydicom.Dataset, str]]) -> Dict[str, Any]:
        """Generate validation statistics"""
        stats = {}
        
        if not datasets:
            return stats
            
        # Modality distribution
        modalities = [ds.get('Modality', 'Unknown') for ds, _ in datasets]
        stats['modality_distribution'] = dict(Counter(modalities))
        
        # Tag completeness
        all_tags = set()
        for ds, _ in datasets:
            all_tags.update(ds.keys())
            
        tag_presence = {}
        for tag in all_tags:
            count = sum(1 for ds, _ in datasets if tag in ds)
            tag_presence[str(tag)] = {
                'present': count,
                'missing': len(datasets) - count,
                'percentage': (count / len(datasets)) * 100
            }
        stats['tag_completeness'] = tag_presence
        
        # Study/Series counts
        study_uids = set(ds.get('StudyInstanceUID', '') for ds, _ in datasets)
        series_uids = set(ds.get('SeriesInstanceUID', '') for ds, _ in datasets)
        patient_ids = set(str(ds.get('PatientID', '')) for ds, _ in datasets)
        
        stats['collection_summary'] = {
            'total_instances': len(datasets),
            'unique_patients': len([p for p in patient_ids if p]),
            'unique_studies': len([s for s in study_uids if s]),
            'unique_series': len([s for s in series_uids if s])
        }
        
        return stats

# Validation Rules Implementation

class RequiredTagsRule(ValidationRule):
    def __init__(self):
        super().__init__("Required Tags", "Check for required DICOM tags", "Compliance")
        
        # Core required tags for all DICOM files
        self.required_tags = {
            (0x0008, 0x0016): "SOP Class UID",
            (0x0008, 0x0018): "SOP Instance UID", 
            (0x0010, 0x0020): "Patient ID",
            (0x0020, 0x000D): "Study Instance UID",
            (0x0020, 0x000E): "Series Instance UID"
        }
        
        # Modality-specific required tags
        self.modality_required = {
            'CT': [(0x0018, 0x0050)],  # Slice Thickness
            'MR': [(0x0018, 0x0080)],  # Repetition Time
            'US': [(0x0018, 0x6011)],  # Sequence of Ultrasound Regions
        }
        
    def validate_dataset(self, dataset: pydicom.Dataset, file_path: str) -> List[ValidationIssue]:
        issues = []
        
        # Check core required tags
        for tag, name in self.required_tags.items():
            if tag not in dataset:
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR, self.category,
                    f"Missing required tag: {name} {tag}",
                    tag=str(tag), file_path=file_path,
                    suggested_fix=f"Add {name} tag to DICOM header"
                ))
            elif not dataset[tag].value:
                issues.append(ValidationIssue(
                    ValidationSeverity.WARNING, self.category,
                    f"Required tag {name} is empty",
                    tag=str(tag), file_path=file_path,
                    suggested_fix=f"Provide value for {name}"
                ))
                
        # Check modality-specific tags
        modality = dataset.get('Modality', '')
        if modality in self.modality_required:
            for req_tag in self.modality_required[modality]:
                if req_tag not in dataset:
                    tag_name = pydicom.datadict.keyword_for_tag(req_tag)
                    issues.append(ValidationIssue(
                        ValidationSeverity.WARNING, self.category,
                        f"Missing {modality}-specific tag: {tag_name} {req_tag}",
                        tag=str(req_tag), file_path=file_path
                    ))
                    
        return issues

class UIDFormatRule(ValidationRule):
    def __init__(self):
        super().__init__("UID Format", "Validate UID format compliance", "Format")
        self.uid_pattern = re.compile(r'^[0-9]+(\.[0-9]+)*$')
        
    def validate_dataset(self, dataset: pydicom.Dataset, file_path: str) -> List[ValidationIssue]:
        issues = []
        
        uid_tags = [
            (0x0008, 0x0016, "SOP Class UID"),
            (0x0008, 0x0018, "SOP Instance UID"),
            (0x0020, 0x000D, "Study Instance UID"),
            (0x0020, 0x000E, "Series Instance UID")
        ]
        
        for tag, _, name in uid_tags:
            if tag in dataset:
                uid_value = str(dataset[tag].value)
                if not self.uid_pattern.match(uid_value):
                    issues.append(ValidationIssue(
                        ValidationSeverity.ERROR, self.category,
                        f"Invalid UID format for {name}: {uid_value}",
                        tag=str(tag), file_path=file_path,
                        suggested_fix="UID must contain only digits and periods"
                    ))
                elif len(uid_value) > 64:
                    issues.append(ValidationIssue(
                        ValidationSeverity.ERROR, self.category,
                        f"UID too long for {name} (max 64 chars): {len(uid_value)}",
                        tag=str(tag), file_path=file_path,
                        suggested_fix="Shorten UID to 64 characters or less"
                    ))
                    
        return issues

class DateTimeFormatRule(ValidationRule):
    def __init__(self):
        super().__init__("Date/Time Format", "Validate DA/TM format compliance", "Format")
        
    def validate_dataset(self, dataset: pydicom.Dataset, file_path: str) -> List[ValidationIssue]:
        issues = []
        
        # Check DA (Date) elements
        for elem in dataset:
            if elem.VR == 'DA' and elem.value:
                if not self._validate_date(str(elem.value)):
                    issues.append(ValidationIssue(
                        ValidationSeverity.ERROR, self.category,
                        f"Invalid date format in tag {elem.tag}: {elem.value}",
                        tag=str(elem.tag), file_path=file_path,
                        suggested_fix="Use YYYYMMDD format"
                    ))
                    
            elif elem.VR == 'TM' and elem.value:
                if not self._validate_time(str(elem.value)):
                    issues.append(ValidationIssue(
                        ValidationSeverity.ERROR, self.category,
                        f"Invalid time format in tag {elem.tag}: {elem.value}",
                        tag=str(elem.tag), file_path=file_path,
                        suggested_fix="Use HHMMSS.FFFFFF format"
                    ))
                    
        return issues
        
    def _validate_date(self, date_str: str) -> bool:
        """Validate DICOM DA format: YYYYMMDD"""
        if len(date_str) != 8:
            return False
        try:
            year = int(date_str[:4])
            month = int(date_str[4:6])
            day = int(date_str[6:8])
            datetime(year, month, day)
            return True
        except ValueError:
            return False
            
    def _validate_time(self, time_str: str) -> bool:
        """Validate DICOM TM format: HHMMSS.FFFFFF"""
        if not re.match(r'^\d{2}(\d{2}(\d{2}(\.\d{1,6})?)?)?$', time_str):
            return False
        return True

class PersonNameFormatRule(ValidationRule):
    def __init__(self):
        super().__init__("Person Name Format", "Validate PN format compliance", "Format")
        
    def validate_dataset(self, dataset: pydicom.Dataset, file_path: str) -> List[ValidationIssue]:
        issues = []
        
        for elem in dataset:
            if elem.VR == 'PN' and elem.value:
                pn_value = str(elem.value)
                # Check for control characters (except allowed ones)
                if any(ord(c) < 32 and c not in '\t\n\r' for c in pn_value):
                    issues.append(ValidationIssue(
                        ValidationSeverity.WARNING, self.category,
                        f"Person name contains control characters: {elem.tag}",
                        tag=str(elem.tag), file_path=file_path,
                        suggested_fix="Remove control characters from person name"
                    ))
                    
                # Check length (64 chars per component)
                components = pn_value.split('^')
                for i, component in enumerate(components):
                    if len(component) > 64:
                        issues.append(ValidationIssue(
                            ValidationSeverity.WARNING, self.category,
                            f"Person name component {i+1} too long (>64 chars): {elem.tag}",
                            tag=str(elem.tag), file_path=file_path,
                            suggested_fix="Shorten person name components to 64 chars or less"
                        ))
                        
        return issues

class ValueRepresentationRule(ValidationRule):
    def __init__(self):
        super().__init__("Value Representation", "Validate VR compliance", "Format")
        
    def validate_dataset(self, dataset: pydicom.Dataset, file_path: str) -> List[ValidationIssue]:
        issues = []
        
        for elem in dataset:
            try:
                # Check if VR is appropriate for the tag
                expected_vr = pydicom.datadict.dictionary_VR(elem.tag)
                if expected_vr and elem.VR != expected_vr:
                    # Some tags can have multiple valid VRs, so this might be too strict
                    issues.append(ValidationIssue(
                        ValidationSeverity.INFO, self.category,
                        f"Unexpected VR for tag {elem.tag}: found {elem.VR}, expected {expected_vr}",
                        tag=str(elem.tag), file_path=file_path
                    ))
            except:
                # Private tags or unknown tags
                pass
                
        return issues

class DuplicateUIDRule(ValidationRule):
    def __init__(self):
        super().__init__("Duplicate UIDs", "Check for duplicate UIDs in collection", "Integrity")
        
    def validate_collection(self, datasets: List[Tuple[pydicom.Dataset, str]]) -> List[ValidationIssue]:
        issues = []
        
        # Check for duplicate SOP Instance UIDs
        sop_uids = defaultdict(list)
        for ds, file_path in datasets:
            sop_uid = ds.get('SOPInstanceUID', '')
            if sop_uid:
                sop_uids[sop_uid].append(file_path)
                
        for uid, files in sop_uids.items():
            if len(files) > 1:
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR, self.category,
                    f"Duplicate SOP Instance UID found in {len(files)} files: {uid}",
                    suggested_fix="Ensure each DICOM instance has unique SOP Instance UID"
                ))
                
        return issues

class StudyConsistencyRule(ValidationRule):
    def __init__(self):
        super().__init__("Study Consistency", "Check study-level consistency", "Consistency")
        
    def validate_collection(self, datasets: List[Tuple[pydicom.Dataset, str]]) -> List[ValidationIssue]:
        issues = []
        
        # Group by Study Instance UID
        studies = defaultdict(list)
        for ds, file_path in datasets:
            study_uid = ds.get('StudyInstanceUID', '')
            if study_uid:
                studies[study_uid].append((ds, file_path))
                
        for study_uid, study_datasets in studies.items():
            if len(study_datasets) > 1:
                # Check Patient ID consistency within study
                patient_ids = set(str(ds.get('PatientID', '')) for ds, _ in study_datasets)
                if len(patient_ids) > 1:
                    issues.append(ValidationIssue(
                        ValidationSeverity.ERROR, self.category,
                        f"Inconsistent Patient IDs in study {study_uid}: {patient_ids}",
                        suggested_fix="All instances in a study must have the same Patient ID"
                    ))
                    
                # Check Study Date consistency
                study_dates = set(str(ds.get('StudyDate', '')) for ds, _ in study_datasets)
                if len(study_dates) > 1:
                    issues.append(ValidationIssue(
                        ValidationSeverity.WARNING, self.category,
                        f"Inconsistent Study Dates in study {study_uid}: {study_dates}",
                        suggested_fix="All instances in a study should have the same Study Date"
                    ))
                    
        return issues

class SeriesConsistencyRule(ValidationRule):
    def __init__(self):
        super().__init__("Series Consistency", "Check series-level consistency", "Consistency")
        
    def validate_collection(self, datasets: List[Tuple[pydicom.Dataset, str]]) -> List[ValidationIssue]:
        issues = []
        
        # Group by Series Instance UID
        series = defaultdict(list)
        for ds, file_path in datasets:
            series_uid = ds.get('SeriesInstanceUID', '')
            if series_uid:
                series[series_uid].append((ds, file_path))
                
        for series_uid, series_datasets in series.items():
            if len(series_datasets) > 1:
                # Check Modality consistency within series
                modalities = set(str(ds.get('Modality', '')) for ds, _ in series_datasets)
                if len(modalities) > 1:
                    issues.append(ValidationIssue(
                        ValidationSeverity.WARNING, self.category,
                        f"Inconsistent Modalities in series {series_uid}: {modalities}",
                        suggested_fix="All instances in a series should have the same Modality"
                    ))
                    
        return issues

class ModalitySpecificRule(ValidationRule):
    def __init__(self):
        super().__init__("Modality Specific", "Modality-specific validation", "Modality")
        
    def validate_dataset(self, dataset: pydicom.Dataset, file_path: str) -> List[ValidationIssue]:
        issues = []
        
        modality = dataset.get('Modality', '')
        
        if modality == 'CT':
            issues.extend(self._validate_ct(dataset, file_path))
        elif modality == 'MR':
            issues.extend(self._validate_mr(dataset, file_path))
        elif modality == 'US':
            issues.extend(self._validate_us(dataset, file_path))
            
        return issues
        
    def _validate_ct(self, dataset: pydicom.Dataset, file_path: str) -> List[ValidationIssue]:
        issues = []
        
        # Check for CT-specific required tags
        if 'SliceThickness' not in dataset:
            issues.append(ValidationIssue(
                ValidationSeverity.WARNING, self.category,
                "CT image missing Slice Thickness",
                tag="(0018,0050)", file_path=file_path
            ))
            
        if 'KVP' not in dataset:
            issues.append(ValidationIssue(
                ValidationSeverity.INFO, self.category,
                "CT image missing KVP (tube voltage)",
                tag="(0018,0060)", file_path=file_path
            ))
            
        return issues
        
    def _validate_mr(self, dataset: pydicom.Dataset, file_path: str) -> List[ValidationIssue]:
        issues = []
        
        # Check for MR-specific required tags
        if 'RepetitionTime' not in dataset:
            issues.append(ValidationIssue(
                ValidationSeverity.WARNING, self.category,
                "MR image missing Repetition Time",
                tag="(0018,0080)", file_path=file_path
            ))
            
        if 'EchoTime' not in dataset:
            issues.append(ValidationIssue(
                ValidationSeverity.WARNING, self.category,
                "MR image missing Echo Time", 
                tag="(0018,0081)", file_path=file_path
            ))
            
        return issues
        
    def _validate_us(self, dataset: pydicom.Dataset, file_path: str) -> List[ValidationIssue]:
        issues = []
        
        # Ultrasound-specific validation would go here
        return issues

class PixelDataRule(ValidationRule):
    def __init__(self):
        super().__init__("Pixel Data", "Validate pixel data integrity", "Image Data")
        
    def validate_dataset(self, dataset: pydicom.Dataset, file_path: str) -> List[ValidationIssue]:
        issues = []
        
        if 'PixelData' in dataset:
            # Check if required pixel data tags are present
            required_pixel_tags = [
                ('Rows', '(0028,0010)'),
                ('Columns', '(0028,0011)'),
                ('BitsAllocated', '(0028,0100)'),
                ('BitsStored', '(0028,0101)'),
                ('HighBit', '(0028,0102)'),
                ('PixelRepresentation', '(0028,0103)')
            ]
            
            for tag_name, tag_id in required_pixel_tags:
                if tag_name not in dataset:
                    issues.append(ValidationIssue(
                        ValidationSeverity.ERROR, self.category,
                        f"Missing required pixel tag: {tag_name} {tag_id}",
                        tag=tag_id, file_path=file_path,
                        suggested_fix=f"Add {tag_name} tag for proper pixel data interpretation"
                    ))
                    
            # Validate pixel data consistency
            if all(tag in dataset for tag, _ in required_pixel_tags):
                try:
                    rows = dataset.Rows
                    cols = dataset.Columns
                    bits_allocated = dataset.BitsAllocated
                    samples_per_pixel = dataset.get('SamplesPerPixel', 1)
                    
                    expected_size = rows * cols * (bits_allocated // 8) * samples_per_pixel
                    actual_size = len(dataset.PixelData)
                    
                    # Allow for some compression
                    if actual_size < expected_size * 0.1:  # Less than 10% of expected
                        issues.append(ValidationIssue(
                            ValidationSeverity.WARNING, self.category,
                            f"Pixel data size unusually small: {actual_size} bytes (expected ~{expected_size})",
                            file_path=file_path,
                            suggested_fix="Verify pixel data is not corrupted"
                        ))
                        
                except Exception as e:
                    issues.append(ValidationIssue(
                        ValidationSeverity.WARNING, self.category,
                        f"Cannot validate pixel data consistency: {str(e)}",
                        file_path=file_path
                    ))
                    
        return issues

class TransferSyntaxRule(ValidationRule):
    def __init__(self):
        super().__init__("Transfer Syntax", "Validate transfer syntax", "Encoding")
        
    def validate_dataset(self, dataset: pydicom.Dataset, file_path: str) -> List[ValidationIssue]:
        issues = []
        
        if hasattr(dataset, 'file_meta') and dataset.file_meta:
            transfer_syntax = dataset.file_meta.get('TransferSyntaxUID', '')
            if not transfer_syntax:
                issues.append(ValidationIssue(
                    ValidationSeverity.ERROR, self.category,
                    "Missing Transfer Syntax UID in file meta information",
                    tag="(0002,0010)", file_path=file_path,
                    suggested_fix="Add Transfer Syntax UID to file meta header"
                ))
            else:
                # Check if it's a known transfer syntax
                known_syntaxes = [
                    '1.2.840.10008.1.2',      # Implicit VR Little Endian
                    '1.2.840.10008.1.2.1',    # Explicit VR Little Endian
                    '1.2.840.10008.1.2.2',    # Explicit VR Big Endian
                    '1.2.840.10008.1.2.4.50', # JPEG Baseline
                    '1.2.840.10008.1.2.4.90', # JPEG 2000 Lossless
                    '1.2.840.10008.1.2.4.91', # JPEG 2000
                    '1.2.840.10008.1.2.5',    # RLE Lossless
                ]
                
                if transfer_syntax not in known_syntaxes:
                    issues.append(ValidationIssue(
                        ValidationSeverity.INFO, self.category,
                        f"Unknown or uncommon Transfer Syntax: {transfer_syntax}",
                        tag="(0002,0010)", file_path=file_path
                    ))
        else:
            issues.append(ValidationIssue(
                ValidationSeverity.WARNING, self.category,
                "Missing file meta information",
                file_path=file_path,
                suggested_fix="Add DICOM file meta header"
            ))
            
        return issues