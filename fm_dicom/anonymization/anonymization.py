"""
Advanced DICOM Anonymization Engine
Provides template-based anonymization with consistent UID mapping and date shifting.
"""

import os
import logging
import pydicom
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple, Set
import hashlib
import json
import re
from pydicom.uid import generate_uid
from pydicom.dataelem import DataElement

class AnonymizationAction:
    """Defines different anonymization actions"""
    REMOVE = "remove"
    BLANK = "blank"
    REPLACE = "replace"
    HASH = "hash"
    KEEP = "keep"
    DATE_SHIFT = "date_shift"
    UID_REMAP = "uid_remap"

class AnonymizationRule:
    """Defines how to anonymize a specific tag"""
    def __init__(self, tag: str, action: str, replacement_value: str = "", 
                 description: str = ""):
        self.tag = tag  # Tag in format "(0010,0010)" or keyword like "PatientName"
        self.action = action
        self.replacement_value = replacement_value
        self.description = description
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            'tag': self.tag,
            'action': self.action,
            'replacement_value': self.replacement_value,
            'description': self.description
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AnonymizationRule':
        return cls(
            tag=data['tag'],
            action=data['action'],
            replacement_value=data.get('replacement_value', ''),
            description=data.get('description', '')
        )

class AnonymizationTemplate:
    """Template defining a complete anonymization strategy"""
    def __init__(self, name: str, description: str = "", version: str = "1.0"):
        self.name = name
        self.description = description
        self.version = version
        self.rules: List[AnonymizationRule] = []
        self.date_shift_days: Optional[int] = None
        self.preserve_relationships = True
        self.remove_private_tags = False
        self.remove_curves = False
        self.remove_overlays = False
        self.created_date = datetime.now()
        self.modified_date = datetime.now()
        
    def add_rule(self, rule: AnonymizationRule):
        """Add an anonymization rule"""
        self.rules.append(rule)
        self.modified_date = datetime.now()
        
    def remove_rule(self, tag: str):
        """Remove rule for a specific tag"""
        self.rules = [rule for rule in self.rules if rule.tag != tag]
        self.modified_date = datetime.now()
        
    def get_rule(self, tag: str) -> Optional[AnonymizationRule]:
        """Get rule for a specific tag"""
        for rule in self.rules:
            if rule.tag == tag:
                return rule
        return None
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'description': self.description,
            'version': self.version,
            'rules': [rule.to_dict() for rule in self.rules],
            'date_shift_days': self.date_shift_days,
            'preserve_relationships': self.preserve_relationships,
            'remove_private_tags': self.remove_private_tags,
            'remove_curves': self.remove_curves,
            'remove_overlays': self.remove_overlays,
            'created_date': self.created_date.isoformat(),
            'modified_date': self.modified_date.isoformat()
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AnonymizationTemplate':
        template = cls(
            name=data['name'],
            description=data.get('description', ''),
            version=data.get('version', '1.0')
        )
        
        template.rules = [AnonymizationRule.from_dict(rule_data) 
                         for rule_data in data.get('rules', [])]
        template.date_shift_days = data.get('date_shift_days')
        template.preserve_relationships = data.get('preserve_relationships', True)
        template.remove_private_tags = data.get('remove_private_tags', False)
        template.remove_curves = data.get('remove_curves', False)
        template.remove_overlays = data.get('remove_overlays', False)
        
        if 'created_date' in data:
            template.created_date = datetime.fromisoformat(data['created_date'])
        if 'modified_date' in data:
            template.modified_date = datetime.fromisoformat(data['modified_date'])
            
        return template

class UIDMapper:
    """Maintains consistent UID mapping across anonymization"""
    def __init__(self):
        self.uid_map: Dict[str, str] = {}
        
    def get_mapped_uid(self, original_uid: str) -> str:
        """Get consistent mapped UID"""
        if original_uid not in self.uid_map:
            self.uid_map[original_uid] = generate_uid()
        return self.uid_map[original_uid]
        
    def clear(self):
        """Clear all mappings"""
        self.uid_map.clear()

class DateShifter:
    """Handles consistent date shifting"""
    def __init__(self, shift_days: int):
        self.shift_days = shift_days
        self.shift_delta = timedelta(days=shift_days)
        
    def shift_date(self, date_str: str) -> str:
        """Shift a DICOM date (DA format: YYYYMMDD)"""
        try:
            if len(date_str) == 8:
                original_date = datetime.strptime(date_str, '%Y%m%d')
                shifted_date = original_date + self.shift_delta
                return shifted_date.strftime('%Y%m%d')
        except ValueError:
            pass
        return date_str
        
    def shift_datetime(self, datetime_str: str) -> str:
        """Shift a DICOM datetime (DT format)"""
        try:
            # Handle various DT formats
            if len(datetime_str) >= 14:
                original_dt = datetime.strptime(datetime_str[:14], '%Y%m%d%H%M%S')
                shifted_dt = original_dt + self.shift_delta
                result = shifted_dt.strftime('%Y%m%d%H%M%S')
                if len(datetime_str) > 14:
                    result += datetime_str[14:]  # Preserve fractional seconds and timezone
                return result
        except ValueError:
            pass
        return datetime_str
        
    def shift_time(self, time_str: str) -> str:
        """Time (TM) doesn't need shifting, return as-is"""
        return time_str

class AnonymizationResult:
    """Results of anonymization operation"""
    def __init__(self):
        self.processed_files: List[str] = []
        self.failed_files: Dict[str, str] = {}  # file_path: error_message
        self.anonymized_count = 0
        self.skipped_count = 0
        self.uid_mappings: Dict[str, str] = {}
        self.date_shift_applied = False
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        
    def add_success(self, file_path: str):
        """Record successful anonymization"""
        self.processed_files.append(file_path)
        self.anonymized_count += 1
        
    def add_failure(self, file_path: str, error_message: str):
        """Record failed anonymization"""
        self.failed_files[file_path] = error_message
        
    def add_skip(self, file_path: str, reason: str):
        """Record skipped file"""
        self.failed_files[file_path] = f"Skipped: {reason}"
        self.skipped_count += 1
        
    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics"""
        total_files = self.anonymized_count + len(self.failed_files)
        duration = None
        if self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()
            
        return {
            'total_files': total_files,
            'anonymized_count': self.anonymized_count,
            'failed_count': len(self.failed_files) - self.skipped_count,
            'skipped_count': self.skipped_count,
            'success_rate': (self.anonymized_count / total_files * 100) if total_files > 0 else 0,
            'duration_seconds': duration,
            'uid_mappings_count': len(self.uid_mappings),
            'date_shift_applied': self.date_shift_applied
        }

class AnonymizationEngine:
    """Main anonymization engine"""
    
    def __init__(self):
        self.uid_mapper = UIDMapper()
        self.date_shifter: Optional[DateShifter] = None
        self.current_template: Optional[AnonymizationTemplate] = None
        
    def anonymize_collection(self, template: AnonymizationTemplate, 
                           file_paths: List[str]) -> AnonymizationResult:
        """Anonymize a collection of DICOM files using a template"""
        result = AnonymizationResult()
        result.start_time = datetime.now()
        
        self.current_template = template
        
        # Setup date shifter if needed
        if template.date_shift_days is not None:
            self.date_shifter = DateShifter(template.date_shift_days)
            result.date_shift_applied = True
        else:
            self.date_shifter = None
            
        # Clear UID mapper for new collection
        if template.preserve_relationships:
            self.uid_mapper.clear()
            
        # Process each file
        for file_path in file_paths:
            try:
                self._anonymize_file(file_path, template, result)
            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                result.add_failure(file_path, error_msg)
                logging.error(f"Anonymization error for {file_path}: {e}", exc_info=True)
                
        # Store UID mappings in result
        result.uid_mappings = self.uid_mapper.uid_map.copy()
        result.end_time = datetime.now()
        
        return result
        
    def _anonymize_file(self, file_path: str, template: AnonymizationTemplate, 
                       result: AnonymizationResult):
        """Anonymize a single DICOM file"""
        # Check if file exists and is readable
        if not os.path.exists(file_path):
            result.add_failure(file_path, "File does not exist")
            return
            
        try:
            # Read DICOM file
            dataset = pydicom.dcmread(file_path, force=True)
        except Exception as e:
            result.add_failure(file_path, f"Cannot read DICOM file: {str(e)}")
            return
            
        # Apply anonymization rules
        try:
            self._apply_template_rules(dataset, template)
            
            # Additional cleanup based on template settings
            if template.remove_private_tags:
                dataset.remove_private_tags()
                
            if template.remove_curves:
                self._remove_curves(dataset)
                
            if template.remove_overlays:
                self._remove_overlays(dataset)
                
            # Save anonymized file
            dataset.save_as(file_path)
            result.add_success(file_path)
            
        except Exception as e:
            result.add_failure(file_path, f"Anonymization failed: {str(e)}")
            
    def _apply_template_rules(self, dataset: pydicom.Dataset, 
                            template: AnonymizationTemplate):
        """Apply all template rules to a dataset"""
        for rule in template.rules:
            try:
                self._apply_rule(dataset, rule)
            except Exception as e:
                logging.warning(f"Failed to apply rule {rule.tag}: {e}")
                
    def _apply_rule(self, dataset: pydicom.Dataset, rule: AnonymizationRule):
        """Apply a single anonymization rule"""
        # Convert tag to pydicom format
        tag = self._parse_tag(rule.tag)
        if tag is None:
            return
            
        # Check if tag exists in dataset
        if tag not in dataset:
            return
            
        element = dataset[tag]
        
        # Apply action based on rule
        if rule.action == AnonymizationAction.REMOVE:
            del dataset[tag]
            
        elif rule.action == AnonymizationAction.BLANK:
            self._blank_element(element)
            
        elif rule.action == AnonymizationAction.REPLACE:
            self._replace_element(element, rule.replacement_value)
            
        elif rule.action == AnonymizationAction.HASH:
            self._hash_element(element)
            
        elif rule.action == AnonymizationAction.DATE_SHIFT:
            self._shift_date_element(element)
            
        elif rule.action == AnonymizationAction.UID_REMAP:
            self._remap_uid_element(element)
            
        # KEEP action does nothing
        
    def _parse_tag(self, tag_str: str) -> Optional[pydicom.tag.BaseTag]:
        """Parse tag string to pydicom tag"""
        try:
            # Try as keyword first
            if not tag_str.startswith('('):
                return pydicom.tag.Tag(tag_str)
                
            # Parse as (group,element) format
            if tag_str.startswith('(') and tag_str.endswith(')'):
                tag_str = tag_str[1:-1]  # Remove parentheses
                parts = tag_str.split(',')
                if len(parts) == 2:
                    group = int(parts[0].strip(), 16)
                    element = int(parts[1].strip(), 16)
                    return pydicom.tag.Tag(group, element)
                    
        except Exception as e:
            logging.warning(f"Could not parse tag '{tag_str}': {e}")
            
        return None
        
    def _blank_element(self, element: DataElement):
        """Blank an element based on its VR"""
        if element.VR == 'DA':
            element.value = '19000101'  # Default date
        elif element.VR == 'TM':
            element.value = '000000'    # Default time
        elif element.VR == 'DT':
            element.value = '19000101000000'  # Default datetime
        elif element.VR in ['IS', 'DS']:
            element.value = '0'
        elif element.VR in ['US', 'SS', 'UL', 'SL']:
            element.value = 0
        elif element.VR in ['FL', 'FD']:
            element.value = 0.0
        else:
            element.value = ''  # String types
            
    def _replace_element(self, element: DataElement, replacement: str):
        """Replace element value with specified replacement"""
        if element.VR in ['US', 'SS', 'UL', 'SL']:
            try:
                element.value = int(replacement)
            except ValueError:
                element.value = 0
        elif element.VR in ['FL', 'FD']:
            try:
                element.value = float(replacement)
            except ValueError:
                element.value = 0.0
        else:
            element.value = replacement
            
    def _hash_element(self, element: DataElement):
        """Hash element value"""
        original_value = str(element.value)
        hash_value = hashlib.sha256(original_value.encode()).hexdigest()[:16]
        
        if element.VR == 'PN':
            # For person names, create a proper PN format
            element.value = f"HASH{hash_value}"
        else:
            element.value = hash_value
            
    def _shift_date_element(self, element: DataElement):
        """Shift date/time element"""
        if self.date_shifter is None:
            return
            
        if element.VR == 'DA':
            element.value = self.date_shifter.shift_date(str(element.value))
        elif element.VR == 'DT':
            element.value = self.date_shifter.shift_datetime(str(element.value))
        # TM (time) elements are not shifted
        
    def _remap_uid_element(self, element: DataElement):
        """Remap UID element to maintain relationships"""
        if element.VR == 'UI':
            original_uid = str(element.value)
            element.value = self.uid_mapper.get_mapped_uid(original_uid)
            
    def _remove_curves(self, dataset: pydicom.Dataset):
        """Remove curve data"""
        # Remove curve data (group 50xx)
        tags_to_remove = []
        for tag in dataset.keys():
            if tag.group & 0xFF00 == 0x5000:
                tags_to_remove.append(tag)
                
        for tag in tags_to_remove:
            del dataset[tag]
            
    def _remove_overlays(self, dataset: pydicom.Dataset):
        """Remove overlay data"""
        # Remove overlay data (group 60xx)
        tags_to_remove = []
        for tag in dataset.keys():
            if tag.group & 0xFF00 == 0x6000:
                tags_to_remove.append(tag)
                
        for tag in tags_to_remove:
            del dataset[tag]

class TemplateManager:
    """Manages anonymization templates"""
    
    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        self.templates_file = os.path.join(config_dir, "anonymization_templates.json")
        self.templates: Dict[str, AnonymizationTemplate] = {}
        self.load_templates()
        
    def load_templates(self):
        """Load templates from file"""
        # Load built-in templates first
        self._load_builtin_templates()
        
        # Load user templates
        if os.path.exists(self.templates_file):
            try:
                with open(self.templates_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                for template_data in data.get('templates', []):
                    template = AnonymizationTemplate.from_dict(template_data)
                    self.templates[template.name] = template
                    
                logging.info(f"Loaded {len(self.templates)} anonymization templates")
                
            except Exception as e:
                logging.error(f"Failed to load templates: {e}")
                
    def save_templates(self):
        """Save templates to file"""
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            
            data = {
                'templates': [template.to_dict() for template in self.templates.values()],
                'version': '1.0',
                'last_updated': datetime.now().isoformat()
            }
            
            with open(self.templates_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
            logging.info(f"Saved {len(self.templates)} anonymization templates")
            
        except Exception as e:
            logging.error(f"Failed to save templates: {e}")
            
    def add_template(self, template: AnonymizationTemplate):
        """Add a template"""
        self.templates[template.name] = template
        self.save_templates()
        
    def remove_template(self, name: str):
        """Remove a template"""
        if name in self.templates:
            del self.templates[name]
            self.save_templates()
            
    def get_template(self, name: str) -> Optional[AnonymizationTemplate]:
        """Get a template by name"""
        return self.templates.get(name)
        
    def get_template_names(self) -> List[str]:
        """Get list of template names"""
        return list(self.templates.keys())
        
    def _load_builtin_templates(self):
        """Load built-in anonymization templates"""
        # Research Standard Template
        research_template = AnonymizationTemplate(
            name="Research Standard",
            description="Remove all patient identifiers for research use",
            version="1.0"
        )
        
        # Patient identification tags
        patient_tags = [
            ("PatientName", AnonymizationAction.REPLACE, "RESEARCH_PATIENT"),
            ("PatientID", AnonymizationAction.HASH),
            ("PatientBirthDate", AnonymizationAction.BLANK),
            ("PatientSex", AnonymizationAction.KEEP),
            ("PatientAge", AnonymizationAction.KEEP),
            ("PatientWeight", AnonymizationAction.KEEP),
            ("PatientSize", AnonymizationAction.KEEP),
            ("OtherPatientNames", AnonymizationAction.REMOVE),
            ("OtherPatientIDs", AnonymizationAction.REMOVE),
            ("PatientBirthTime", AnonymizationAction.REMOVE),
            ("PatientComments", AnonymizationAction.REMOVE),
        ]
        
        for tag_data in patient_tags:
            if len(tag_data) == 3:
                tag, action, replacement = tag_data
            else:
                tag, action = tag_data
                replacement = ""
            research_template.add_rule(AnonymizationRule(tag, action, replacement))
            
        # Study/Series information - keep structure but anonymize dates
        study_tags = [
            ("StudyDate", AnonymizationAction.DATE_SHIFT),
            ("SeriesDate", AnonymizationAction.DATE_SHIFT),
            ("AcquisitionDate", AnonymizationAction.DATE_SHIFT),
            ("ContentDate", AnonymizationAction.DATE_SHIFT),
            ("StudyTime", AnonymizationAction.KEEP),
            ("SeriesTime", AnonymizationAction.KEEP),
            ("AcquisitionTime", AnonymizationAction.KEEP),
            ("ContentTime", AnonymizationAction.KEEP),
            ("StudyDescription", AnonymizationAction.KEEP),
            ("SeriesDescription", AnonymizationAction.KEEP),
            ("StudyInstanceUID", AnonymizationAction.UID_REMAP),
            ("SeriesInstanceUID", AnonymizationAction.UID_REMAP),
            ("SOPInstanceUID", AnonymizationAction.UID_REMAP),
        ]
        
        for tag, action in study_tags:
            research_template.add_rule(AnonymizationRule(tag, action))
            
        # Remove physician/operator information
        physician_tags = [
            ("ReferringPhysicianName", AnonymizationAction.REMOVE),
            ("PerformingPhysicianName", AnonymizationAction.REMOVE),
            ("OperatorsName", AnonymizationAction.REMOVE),
            ("PhysiciansOfRecord", AnonymizationAction.REMOVE),
        ]
        
        for tag, action in physician_tags:
            research_template.add_rule(AnonymizationRule(tag, action))
            
        research_template.date_shift_days = -365  # Shift back 1 year
        research_template.preserve_relationships = True
        research_template.remove_private_tags = True
        
        self.templates[research_template.name] = research_template
        
        # Clinical Review Template
        clinical_template = AnonymizationTemplate(
            name="Clinical Review",
            description="Remove patient identifiers but keep clinical information",
            version="1.0"
        )
        
        # More conservative anonymization for clinical use
        clinical_patient_tags = [
            ("PatientName", AnonymizationAction.REPLACE, "CLINICAL_PATIENT"),
            ("PatientID", AnonymizationAction.HASH),
            ("PatientBirthDate", AnonymizationAction.BLANK),
            ("PatientSex", AnonymizationAction.KEEP),
            ("PatientAge", AnonymizationAction.KEEP),
            ("PatientWeight", AnonymizationAction.KEEP),
            ("PatientSize", AnonymizationAction.KEEP),
        ]
        
        for tag_data in clinical_patient_tags:
            if len(tag_data) == 3:
                tag, action, replacement = tag_data
            else:
                tag, action = tag_data
                replacement = ""
            clinical_template.add_rule(AnonymizationRule(tag, action, replacement))
            
        # Keep all study/series information including dates
        clinical_study_tags = [
            ("StudyDate", AnonymizationAction.KEEP),
            ("SeriesDate", AnonymizationAction.KEEP),
            ("StudyDescription", AnonymizationAction.KEEP),
            ("SeriesDescription", AnonymizationAction.KEEP),
            ("StudyInstanceUID", AnonymizationAction.UID_REMAP),
            ("SeriesInstanceUID", AnonymizationAction.UID_REMAP),
            ("SOPInstanceUID", AnonymizationAction.UID_REMAP),
        ]
        
        for tag, action in clinical_study_tags:
            clinical_template.add_rule(AnonymizationRule(tag, action))
            
        clinical_template.preserve_relationships = True
        clinical_template.remove_private_tags = False
        
        self.templates[clinical_template.name] = clinical_template
        
        # Teaching Collection Template
        teaching_template = AnonymizationTemplate(
            name="Teaching Collection",
            description="Anonymize for educational/teaching purposes",
            version="1.0"
        )
        
        # Educational anonymization with teaching-friendly replacements
        teaching_patient_tags = [
            ("PatientName", AnonymizationAction.REPLACE, "TEACHING_CASE"),
            ("PatientID", AnonymizationAction.REPLACE, "EDU_001"),
            ("PatientBirthDate", AnonymizationAction.REPLACE, "19800101"),
            ("PatientSex", AnonymizationAction.KEEP),
            ("PatientAge", AnonymizationAction.KEEP),
        ]
        
        for tag_data in teaching_patient_tags:
            if len(tag_data) == 3:
                tag, action, replacement = tag_data
            else:
                tag, action = tag_data
                replacement = ""
            teaching_template.add_rule(AnonymizationRule(tag, action, replacement))
            
        # Keep study information but shift dates
        teaching_study_tags = [
            ("StudyDate", AnonymizationAction.DATE_SHIFT),
            ("SeriesDate", AnonymizationAction.DATE_SHIFT),
            ("StudyDescription", AnonymizationAction.KEEP),
            ("SeriesDescription", AnonymizationAction.KEEP),
            ("StudyInstanceUID", AnonymizationAction.UID_REMAP),
            ("SeriesInstanceUID", AnonymizationAction.UID_REMAP),
            ("SOPInstanceUID", AnonymizationAction.UID_REMAP),
        ]
        
        for tag, action in teaching_study_tags:
            teaching_template.add_rule(AnonymizationRule(tag, action))
            
        teaching_template.date_shift_days = -730  # Shift back 2 years
        teaching_template.preserve_relationships = True
        teaching_template.remove_private_tags = True
        
        self.templates[teaching_template.name] = teaching_template
        
        # Minimal Anonymization Template
        minimal_template = AnonymizationTemplate(
            name="Minimal Anonymization",
            description="Remove only essential patient identifiers",
            version="1.0"
        )
        
        minimal_tags = [
            ("PatientName", AnonymizationAction.HASH),
            ("PatientID", AnonymizationAction.HASH),
            ("PatientBirthDate", AnonymizationAction.BLANK),
        ]
        
        for tag, action in minimal_tags:
            minimal_template.add_rule(AnonymizationRule(tag, action))
            
        minimal_template.preserve_relationships = True
        minimal_template.remove_private_tags = False
        
        self.templates[minimal_template.name] = minimal_template
        
def create_anonymization_engine() -> AnonymizationEngine:
    """Factory function to create anonymization engine"""
    return AnonymizationEngine()