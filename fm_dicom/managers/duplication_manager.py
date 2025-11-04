"""
DICOM Duplication Manager

This module provides functionality for creating memory-based copies of DICOM data
at Patient, Study, Series, or Instance levels. Supports configurable UID handling
for maintaining or regenerating DICOM relationships.
"""

import os
import copy
import logging
import uuid
from typing import Dict, List, Tuple, Optional, Any
from enum import Enum
from dataclasses import dataclass

import pydicom
from PyQt6.QtCore import QObject, pyqtSignal


class UIDHandlingMode(Enum):
    """Modes for handling UIDs during duplication"""
    KEEP_ALL = "keep_all"  # Keep all original UIDs
    REGENERATE_ALL = "regenerate_all"  # Generate new UIDs for all levels
    REGENERATE_INSTANCE_ONLY = "regenerate_instance_only"  # Only regenerate SOPInstanceUID
    REGENERATE_SERIES_AND_INSTANCE = "regenerate_series_and_instance"  # Regenerate SeriesInstanceUID and SOPInstanceUID
    USER_CONFIGURED = "user_configured"  # User specifies which UIDs to regenerate


@dataclass
class UIDConfiguration:
    """Configuration for UID handling during duplication"""
    regenerate_patient_id: bool = False
    regenerate_study_uid: bool = False
    regenerate_series_uid: bool = False
    regenerate_instance_uid: bool = True

    # Advanced options
    preserve_relationships: bool = True  # Maintain parent-child relationships
    add_derived_suffix: bool = False  # Add suffix like "_COPY" to descriptions


@dataclass
class DuplicatedItem:
    """Container for a duplicated DICOM item"""
    original_path: str
    duplicated_dataset: pydicom.Dataset
    duplication_level: str  # "patient", "study", "series", "instance"
    original_uids: Dict[str, str]  # Original UIDs for reference
    new_uids: Dict[str, str]  # New UIDs assigned
    is_modified: bool = False  # Track if dataset has been modified


class DuplicationManager(QObject):
    """Manager for DICOM data duplication with configurable UID handling"""

    # Signals
    duplication_started = pyqtSignal(str, int)  # level, count
    duplication_progress = pyqtSignal(int, int)  # current, total
    duplication_completed = pyqtSignal(list)  # List of DuplicatedItem
    duplication_error = pyqtSignal(str)  # Error message

    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self.duplicated_items: List[DuplicatedItem] = []
        self.uid_mappings: Dict[str, str] = {}  # original_uid -> new_uid mapping

    def duplicate_items(self,
                       selected_items: List[Tuple[str, str]],
                       uid_config: UIDConfiguration) -> List[DuplicatedItem]:
        """
        Duplicate selected items from the tree hierarchy

        Args:
            selected_items: List of (tree_path, file_path) tuples
            uid_config: Configuration for UID handling

        Returns:
            List of DuplicatedItem objects
        """
        try:
            logging.info(f"Starting duplication of {len(selected_items)} items")
            self.duplication_started.emit("mixed", len(selected_items))

            duplicated_items = []

            for idx, (tree_path, file_path) in enumerate(selected_items):
                self.duplication_progress.emit(idx + 1, len(selected_items))

                try:
                    # Determine duplication level from tree path
                    level = self._determine_duplication_level(tree_path)

                    # Load and duplicate the DICOM file
                    original_dataset = pydicom.dcmread(file_path, force=True)
                    duplicated_dataset = self._duplicate_dataset(
                        original_dataset, level, uid_config
                    )

                    # Create duplication record
                    duplicated_item = DuplicatedItem(
                        original_path=file_path,
                        duplicated_dataset=duplicated_dataset,
                        duplication_level=level,
                        original_uids=self._extract_uids(original_dataset),
                        new_uids=self._extract_uids(duplicated_dataset)
                    )

                    duplicated_items.append(duplicated_item)

                except Exception as e:
                    logging.error(f"Failed to duplicate {file_path}: {e}")
                    continue

            self.duplicated_items.extend(duplicated_items)
            self.duplication_completed.emit(duplicated_items)

            logging.info(f"Successfully duplicated {len(duplicated_items)} items")
            return duplicated_items

        except Exception as e:
            error_msg = f"Duplication failed: {e}"
            logging.error(error_msg, exc_info=True)
            self.duplication_error.emit(error_msg)
            return []

    def duplicate_patient(self, patient_files: List[str], uid_config: UIDConfiguration) -> List[DuplicatedItem]:
        """Duplicate entire patient with all studies/series/instances"""
        return self._duplicate_at_level(patient_files, "patient", uid_config)

    def duplicate_study(self, study_files: List[str], uid_config: UIDConfiguration) -> List[DuplicatedItem]:
        """Duplicate entire study with all series/instances"""
        return self._duplicate_at_level(study_files, "study", uid_config)

    def duplicate_series(self, series_files: List[str], uid_config: UIDConfiguration) -> List[DuplicatedItem]:
        """Duplicate entire series with all instances"""
        return self._duplicate_at_level(series_files, "series", uid_config)

    def duplicate_instances(self, instance_files: List[str], uid_config: UIDConfiguration) -> List[DuplicatedItem]:
        """Duplicate individual instances"""
        return self._duplicate_at_level(instance_files, "instance", uid_config)

    def _duplicate_at_level(self,
                          file_paths: List[str],
                          level: str,
                          uid_config: UIDConfiguration) -> List[DuplicatedItem]:
        """Duplicate files at a specific hierarchy level"""
        try:
            logging.info(f"Duplicating {len(file_paths)} files at {level} level")
            self.duplication_started.emit(level, len(file_paths))

            duplicated_items = []

            # Generate consistent UIDs for the duplication level
            level_uids = self._generate_level_uids(level, uid_config)

            for idx, file_path in enumerate(file_paths):
                self.duplication_progress.emit(idx + 1, len(file_paths))

                try:
                    # Load original dataset
                    original_dataset = pydicom.dcmread(file_path, force=True)

                    # Create deep copy
                    duplicated_dataset = copy.deepcopy(original_dataset)

                    # Apply UID modifications
                    self._apply_uid_modifications(
                        duplicated_dataset, level, uid_config, level_uids
                    )

                    # Apply other modifications (descriptions, etc.)
                    self._apply_other_modifications(duplicated_dataset, uid_config)

                    # Create duplication record
                    duplicated_item = DuplicatedItem(
                        original_path=file_path,
                        duplicated_dataset=duplicated_dataset,
                        duplication_level=level,
                        original_uids=self._extract_uids(original_dataset),
                        new_uids=self._extract_uids(duplicated_dataset)
                    )

                    duplicated_items.append(duplicated_item)

                except Exception as e:
                    logging.error(f"Failed to duplicate {file_path}: {e}")
                    continue

            self.duplicated_items.extend(duplicated_items)
            self.duplication_completed.emit(duplicated_items)

            logging.info(f"Successfully duplicated {len(duplicated_items)} items at {level} level")
            return duplicated_items

        except Exception as e:
            error_msg = f"Duplication at {level} level failed: {e}"
            logging.error(error_msg, exc_info=True)
            self.duplication_error.emit(error_msg)
            return []

    def _duplicate_dataset(self,
                          original_dataset: pydicom.Dataset,
                          level: str,
                          uid_config: UIDConfiguration) -> pydicom.Dataset:
        """Create a duplicate of a DICOM dataset with UID modifications"""
        # Create deep copy to avoid modifying original
        duplicated = copy.deepcopy(original_dataset)

        # Apply UID modifications based on level and configuration
        level_uids = self._generate_level_uids(level, uid_config)
        self._apply_uid_modifications(duplicated, level, uid_config, level_uids)

        # Apply other modifications
        self._apply_other_modifications(duplicated, uid_config)

        return duplicated

    def _determine_duplication_level(self, tree_path: str) -> str:
        """Determine the duplication level from tree hierarchy path"""
        # Simple heuristic based on tree path structure
        # This could be enhanced based on the actual tree structure
        path_parts = tree_path.split('/')
        if len(path_parts) <= 1:
            return "patient"
        elif len(path_parts) <= 2:
            return "study"
        elif len(path_parts) <= 3:
            return "series"
        else:
            return "instance"

    def _generate_level_uids(self, level: str, uid_config: UIDConfiguration) -> Dict[str, str]:
        """Generate new UIDs for the specified level"""
        level_uids = {}

        if level == "patient" and uid_config.regenerate_patient_id:
            level_uids['PatientID'] = f"PAT_{uuid.uuid4().hex[:8].upper()}"

        if level in ["patient", "study"] and uid_config.regenerate_study_uid:
            level_uids['StudyInstanceUID'] = pydicom.uid.generate_uid()

        if level in ["patient", "study", "series"] and uid_config.regenerate_series_uid:
            level_uids['SeriesInstanceUID'] = pydicom.uid.generate_uid()

        if uid_config.regenerate_instance_uid:
            level_uids['SOPInstanceUID'] = pydicom.uid.generate_uid()

        return level_uids

    def _apply_uid_modifications(self,
                                dataset: pydicom.Dataset,
                                level: str,
                                uid_config: UIDConfiguration,
                                level_uids: Dict[str, str]):
        """Apply UID modifications to a dataset"""

        # Apply Patient ID changes
        if 'PatientID' in level_uids:
            if hasattr(dataset, 'PatientID'):
                old_id = str(dataset.PatientID)
                dataset.PatientID = level_uids['PatientID']
                self.uid_mappings[old_id] = level_uids['PatientID']

        # Apply Study UID changes
        if 'StudyInstanceUID' in level_uids:
            if hasattr(dataset, 'StudyInstanceUID'):
                old_uid = str(dataset.StudyInstanceUID)
                dataset.StudyInstanceUID = level_uids['StudyInstanceUID']
                self.uid_mappings[old_uid] = level_uids['StudyInstanceUID']

        # Apply Series UID changes
        if 'SeriesInstanceUID' in level_uids:
            if hasattr(dataset, 'SeriesInstanceUID'):
                old_uid = str(dataset.SeriesInstanceUID)
                dataset.SeriesInstanceUID = level_uids['SeriesInstanceUID']
                self.uid_mappings[old_uid] = level_uids['SeriesInstanceUID']

        # Apply Instance UID changes
        if 'SOPInstanceUID' in level_uids:
            if hasattr(dataset, 'SOPInstanceUID'):
                old_uid = str(dataset.SOPInstanceUID)
                dataset.SOPInstanceUID = level_uids['SOPInstanceUID']
                self.uid_mappings[old_uid] = level_uids['SOPInstanceUID']

        # Update MediaStorageSOPInstanceUID if present (for files)
        if 'SOPInstanceUID' in level_uids and hasattr(dataset, 'file_meta'):
            if hasattr(dataset.file_meta, 'MediaStorageSOPInstanceUID'):
                dataset.file_meta.MediaStorageSOPInstanceUID = level_uids['SOPInstanceUID']

    def _apply_other_modifications(self, dataset: pydicom.Dataset, uid_config: UIDConfiguration):
        """Apply non-UID modifications like adding suffixes to descriptions"""
        if uid_config.add_derived_suffix:
            # Add suffix to various description fields
            description_fields = [
                'StudyDescription', 'SeriesDescription',
                'PatientName', 'ProtocolName'
            ]

            for field in description_fields:
                if hasattr(dataset, field):
                    original_value = str(getattr(dataset, field))
                    if not original_value.endswith('_COPY'):
                        setattr(dataset, field, f"{original_value}_COPY")

    def _extract_uids(self, dataset: pydicom.Dataset) -> Dict[str, str]:
        """Extract relevant UIDs from a DICOM dataset"""
        uids = {}

        uid_fields = [
            'PatientID', 'StudyInstanceUID',
            'SeriesInstanceUID', 'SOPInstanceUID'
        ]

        for field in uid_fields:
            if hasattr(dataset, field):
                uids[field] = str(getattr(dataset, field))

        return uids

    def get_duplicated_items(self) -> List[DuplicatedItem]:
        """Get list of all duplicated items"""
        return self.duplicated_items.copy()

    def get_modified_items(self) -> List[DuplicatedItem]:
        """Get list of items that have been modified after duplication"""
        return [item for item in self.duplicated_items if item.is_modified]

    def mark_item_modified(self, item: DuplicatedItem):
        """Mark a duplicated item as modified"""
        item.is_modified = True

    def clear_duplicated_items(self):
        """Clear all duplicated items from memory"""
        self.duplicated_items.clear()
        self.uid_mappings.clear()
        logging.info("Cleared all duplicated items from memory")

    def save_duplicated_items(self,
                            items: List[DuplicatedItem],
                            output_directory: str) -> List[str]:
        """
        Save duplicated items to disk

        Args:
            items: List of DuplicatedItem to save
            output_directory: Directory to save files to

        Returns:
            List of saved file paths
        """
        saved_paths = []

        try:
            os.makedirs(output_directory, exist_ok=True)

            for item in items:
                # Generate output filename
                original_name = os.path.basename(item.original_path)
                name_parts = os.path.splitext(original_name)
                output_name = f"{name_parts[0]}_copy{name_parts[1]}"
                output_path = os.path.join(output_directory, output_name)

                # Ensure unique filename
                counter = 1
                while os.path.exists(output_path):
                    output_name = f"{name_parts[0]}_copy_{counter}{name_parts[1]}"
                    output_path = os.path.join(output_directory, output_name)
                    counter += 1

                # Save the duplicated dataset
                item.duplicated_dataset.save_as(output_path, write_like_original=False)
                saved_paths.append(output_path)

                logging.info(f"Saved duplicated item to {output_path}")

            return saved_paths

        except Exception as e:
            logging.error(f"Failed to save duplicated items: {e}", exc_info=True)
            raise

    def get_uid_mappings(self) -> Dict[str, str]:
        """Get the UID mapping dictionary (original -> new)"""
        return self.uid_mappings.copy()