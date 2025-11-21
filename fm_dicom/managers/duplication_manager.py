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

    def duplicate_items(
        self,
        selected_items: List[Tuple[str, str]],
        uid_config: UIDConfiguration,
    ) -> List[DuplicatedItem]:
        """Compat helper to duplicate arbitrary item list at instance level."""
        instances = []
        seen = set()
        for _, file_path in selected_items:
            if file_path in seen:
                continue
            seen.add(file_path)
            instances.append({"path": file_path})

        selection = {"instances": instances}
        return self.duplicate_by_hierarchy(selection, "instance", uid_config)

    def duplicate_by_hierarchy(
        self,
        selection: Dict[str, Any],
        duplication_level: str,
        uid_config: UIDConfiguration,
    ) -> List[DuplicatedItem]:
        """Duplicate selections using hierarchy-aware logic."""
        target_level = duplication_level if duplication_level in {"patient", "study", "series", "instance"} else "instance"
        instances = selection.get("instances") or []
        if not instances:
            return []

        hierarchy = self._build_hierarchy(instances)
        total_instances = self._count_instances(hierarchy)

        logging.info(
            "Starting hierarchy duplication at %s level (%d instances)",
            target_level,
            total_instances,
        )
        self.duplication_started.emit(target_level, total_instances)

        duplicated_items: List[DuplicatedItem] = []

        try:
            for patient_node in hierarchy.values():
                if target_level == "patient":
                    duplicated_items.extend(self._duplicate_patient_node(patient_node, uid_config))
                else:
                    for study_node in patient_node["studies"].values():
                        if target_level == "study":
                            duplicated_items.extend(
                                self._duplicate_study_node(patient_node, study_node, uid_config)
                            )
                        else:
                            for series_node in study_node["series"].values():
                                if target_level == "series":
                                    duplicated_items.extend(
                                        self._duplicate_series_node(
                                            patient_node,
                                            study_node,
                                            series_node,
                                            uid_config,
                                        )
                                    )
                                else:
                                    duplicated_items.extend(
                                        self._duplicate_instance_list(
                                            series_node["instances"],
                                            uid_config,
                                        )
                                    )

            self.duplicated_items.extend(duplicated_items)
            self.duplication_completed.emit(duplicated_items)
            logging.info("Successfully duplicated %d items", len(duplicated_items))
            return duplicated_items

        except Exception as exc:
            error_msg = f"Hierarchy duplication failed: {exc}"
            logging.error(error_msg, exc_info=True)
            self.duplication_error.emit(error_msg)
            return []

    def _load_dataset(self, file_path: str) -> pydicom.Dataset:
        """Load dataset from file path, checking memory items first

        Args:
            file_path: Path to DICOM file (may be virtual for memory items)

        Returns:
            pydicom.Dataset: Loaded dataset

        Raises:
            Exception: If dataset cannot be loaded from either memory or disk
        """
        try:
            # Check if this is a memory item (duplicated item) first
            if (self.main_window and
                hasattr(self.main_window, 'tree_manager') and
                hasattr(self.main_window.tree_manager, 'memory_items') and
                file_path in self.main_window.tree_manager.memory_items):

                logging.debug(f"Loading dataset from memory: {file_path}")
                return self.main_window.tree_manager.memory_items[file_path]

            # Otherwise, try to read from disk
            elif os.path.exists(file_path):
                logging.debug(f"Loading dataset from disk: {file_path}")
                return pydicom.dcmread(file_path, force=True)

            else:
                raise FileNotFoundError(f"Dataset not found in memory or on disk: {file_path}")

        except Exception as e:
            logging.error(f"Failed to load dataset from {file_path}: {e}")
            raise

    def _build_hierarchy(self, instance_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build hierarchical representation of selected instances."""
        hierarchy: Dict[str, Any] = {}

        for entry in instance_entries:
            path = entry["path"]
            dataset = self._load_dataset(path)
            patient_id = getattr(dataset, "PatientID", "UNKNOWN_PATIENT")
            patient_name = getattr(dataset, "PatientName", "Unknown")
            study_uid = getattr(dataset, "StudyInstanceUID", f"STUDY_{uuid.uuid4().hex}")
            series_uid = getattr(dataset, "SeriesInstanceUID", f"SERIES_{uuid.uuid4().hex}")

            patient_node = hierarchy.setdefault(
                patient_id,
                {
                    "patient_id": patient_id,
                    "patient_name": patient_name,
                    "dataset": dataset,
                    "studies": {},
                },
            )

            study_node = patient_node["studies"].setdefault(
                study_uid,
                {
                    "study_uid": study_uid,
                    "dataset": dataset,
                    "series": {},
                },
            )

            series_node = study_node["series"].setdefault(
                series_uid,
                {
                    "series_uid": series_uid,
                    "dataset": dataset,
                    "instances": [],
                },
            )

            series_node["instances"].append(
                {
                    "path": path,
                    "dataset": dataset,
                }
            )

        return hierarchy

    def _count_instances(self, hierarchy: Dict[str, Any]) -> int:
        """Count total instances in hierarchy."""
        total = 0
        for patient_node in hierarchy.values():
            for study_node in patient_node["studies"].values():
                for series_node in study_node["series"].values():
                    total += len(series_node["instances"])
        return total

    def _duplicate_patient_node(self, patient_node: Dict[str, Any], uid_config: UIDConfiguration) -> List[DuplicatedItem]:
        duplicated_items: List[DuplicatedItem] = []
        new_patient_id = self._new_patient_id(patient_node["dataset"], uid_config)

        for study_node in patient_node["studies"].values():
            duplicated_items.extend(
                self._duplicate_study_node(
                    patient_node,
                    study_node,
                    uid_config,
                    patient_override=new_patient_id,
                )
            )
        return duplicated_items

    def _duplicate_study_node(
        self,
        patient_node: Dict[str, Any],
        study_node: Dict[str, Any],
        uid_config: UIDConfiguration,
        patient_override: Optional[str] = None,
    ) -> List[DuplicatedItem]:
        duplicated_items: List[DuplicatedItem] = []
        new_patient_id = patient_override if patient_override is not None else self._new_patient_id(patient_node["dataset"], uid_config)
        new_study_uid = self._new_study_uid(study_node["dataset"], uid_config)

        for series_node in study_node["series"].values():
            duplicated_items.extend(
                self._duplicate_series_node(
                    patient_node,
                    study_node,
                    series_node,
                    uid_config,
                    patient_override=new_patient_id,
                    study_override=new_study_uid,
                )
            )
        return duplicated_items

    def _duplicate_series_node(
        self,
        patient_node: Dict[str, Any],
        study_node: Dict[str, Any],
        series_node: Dict[str, Any],
        uid_config: UIDConfiguration,
        patient_override: Optional[str] = None,
        study_override: Optional[str] = None,
    ) -> List[DuplicatedItem]:
        duplicated_items: List[DuplicatedItem] = []
        new_patient_id = patient_override if patient_override is not None else self._new_patient_id(patient_node["dataset"], uid_config)
        new_study_uid = study_override if study_override is not None else self._new_study_uid(study_node["dataset"], uid_config)
        new_series_uid = self._new_series_uid(series_node["dataset"], uid_config)

        overrides = {
            "PatientID": new_patient_id,
            "StudyInstanceUID": new_study_uid,
            "SeriesInstanceUID": new_series_uid,
        }

        duplicated_items.extend(
            self._duplicate_instance_list(
                series_node["instances"],
                uid_config,
                overrides=overrides,
            )
        )

        return duplicated_items

    def _duplicate_instance_list(
        self,
        instance_list: List[Dict[str, Any]],
        uid_config: UIDConfiguration,
        overrides: Optional[Dict[str, Optional[str]]] = None,
    ) -> List[DuplicatedItem]:
        duplicated_items: List[DuplicatedItem] = []

        for entry in instance_list:
            dataset = entry["dataset"]
            path = entry["path"]
            duplicated_dataset = copy.deepcopy(dataset)

            applied_uids: Dict[str, str] = {}

            if overrides and overrides.get("PatientID") is not None:
                patient_id = overrides["PatientID"]
            else:
                patient_id = self._new_patient_id(dataset, uid_config)
            if patient_id and patient_id != getattr(dataset, "PatientID", None):
                applied_uids["PatientID"] = patient_id

            if overrides and overrides.get("StudyInstanceUID") is not None:
                study_uid = overrides["StudyInstanceUID"]
            else:
                study_uid = self._new_study_uid(dataset, uid_config)
            if study_uid and study_uid != getattr(dataset, "StudyInstanceUID", None):
                applied_uids["StudyInstanceUID"] = study_uid

            if overrides and overrides.get("SeriesInstanceUID") is not None:
                series_uid = overrides["SeriesInstanceUID"]
            else:
                series_uid = self._new_series_uid(dataset, uid_config)
            if series_uid and series_uid != getattr(dataset, "SeriesInstanceUID", None):
                applied_uids["SeriesInstanceUID"] = series_uid

            if overrides and overrides.get("SOPInstanceUID") is not None:
                sop_uid = overrides["SOPInstanceUID"]
            else:
                sop_uid = self._new_instance_uid(dataset, uid_config)
            if sop_uid and sop_uid != getattr(dataset, "SOPInstanceUID", None):
                applied_uids["SOPInstanceUID"] = sop_uid

            if applied_uids:
                self._apply_uid_modifications(duplicated_dataset, "instance", uid_config, applied_uids)

            self._apply_other_modifications(duplicated_dataset, uid_config)

            duplicated_item = DuplicatedItem(
                original_path=path,
                duplicated_dataset=duplicated_dataset,
                duplication_level="instance",
                original_uids=self._extract_uids(dataset),
                new_uids=self._extract_uids(duplicated_dataset),
            )
            duplicated_items.append(duplicated_item)

        return duplicated_items

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

    def _should_regenerate(self, uid_config: UIDConfiguration, field: str) -> bool:
        mapping = {
            "PatientID": uid_config.regenerate_patient_id,
            "StudyInstanceUID": uid_config.regenerate_study_uid,
            "SeriesInstanceUID": uid_config.regenerate_series_uid,
            "SOPInstanceUID": uid_config.regenerate_instance_uid,
        }
        return mapping.get(field, False)

    def _new_patient_id(self, dataset: pydicom.Dataset, uid_config: UIDConfiguration) -> Optional[str]:
        if self._should_regenerate(uid_config, "PatientID"):
            return f"PAT_{uuid.uuid4().hex[:8].upper()}"
        value = getattr(dataset, "PatientID", None)
        return str(value) if value is not None else None

    def _new_study_uid(self, dataset: pydicom.Dataset, uid_config: UIDConfiguration) -> Optional[str]:
        if self._should_regenerate(uid_config, "StudyInstanceUID"):
            return pydicom.uid.generate_uid()
        value = getattr(dataset, "StudyInstanceUID", None)
        return str(value) if value is not None else None

    def _new_series_uid(self, dataset: pydicom.Dataset, uid_config: UIDConfiguration) -> Optional[str]:
        if self._should_regenerate(uid_config, "SeriesInstanceUID"):
            return pydicom.uid.generate_uid()
        value = getattr(dataset, "SeriesInstanceUID", None)
        return str(value) if value is not None else None

    def _new_instance_uid(self, dataset: pydicom.Dataset, uid_config: UIDConfiguration) -> Optional[str]:
        if self._should_regenerate(uid_config, "SOPInstanceUID"):
            return pydicom.uid.generate_uid()
        value = getattr(dataset, "SOPInstanceUID", None)
        return str(value) if value is not None else None

    def _apply_uid_modifications(self,
                                dataset: pydicom.Dataset,
                                level: str,
                                uid_config: UIDConfiguration,
                                level_uids: Dict[str, str]):
        """Apply UID modifications to a dataset"""

        logging.info(f"[UID DEBUG] Applying UID modifications for level: {level}")
        logging.info(f"[UID DEBUG] level_uids to apply: {level_uids}")

        # Apply Patient ID changes
        if 'PatientID' in level_uids:
            if hasattr(dataset, 'PatientID'):
                old_id = str(dataset.PatientID)
                dataset.PatientID = level_uids['PatientID']
                self.uid_mappings[old_id] = level_uids['PatientID']
                logging.info(f"[UID DEBUG] Applied PatientID: {old_id} -> {level_uids['PatientID']}")
            else:
                logging.warning(f"[UID DEBUG] Dataset does not have PatientID attribute")

        # Apply Study UID changes
        if 'StudyInstanceUID' in level_uids:
            if hasattr(dataset, 'StudyInstanceUID'):
                old_uid = str(dataset.StudyInstanceUID)
                dataset.StudyInstanceUID = level_uids['StudyInstanceUID']
                self.uid_mappings[old_uid] = level_uids['StudyInstanceUID']
                logging.info(f"[UID DEBUG] Applied StudyInstanceUID: {old_uid} -> {level_uids['StudyInstanceUID']}")
            else:
                logging.warning(f"[UID DEBUG] Dataset does not have StudyInstanceUID attribute")

        # Apply Series UID changes
        if 'SeriesInstanceUID' in level_uids:
            if hasattr(dataset, 'SeriesInstanceUID'):
                old_uid = str(dataset.SeriesInstanceUID)
                dataset.SeriesInstanceUID = level_uids['SeriesInstanceUID']
                self.uid_mappings[old_uid] = level_uids['SeriesInstanceUID']
                logging.info(f"[UID DEBUG] Applied SeriesInstanceUID: {old_uid} -> {level_uids['SeriesInstanceUID']}")
            else:
                logging.warning(f"[UID DEBUG] Dataset does not have SeriesInstanceUID attribute")

        # Apply Instance UID changes
        if 'SOPInstanceUID' in level_uids:
            if hasattr(dataset, 'SOPInstanceUID'):
                old_uid = str(dataset.SOPInstanceUID)
                dataset.SOPInstanceUID = level_uids['SOPInstanceUID']
                self.uid_mappings[old_uid] = level_uids['SOPInstanceUID']
                logging.info(f"[UID DEBUG] Applied SOPInstanceUID: {old_uid} -> {level_uids['SOPInstanceUID']}")
            else:
                logging.warning(f"[UID DEBUG] Dataset does not have SOPInstanceUID attribute")

        # Update MediaStorageSOPInstanceUID if present (for files)
        if 'SOPInstanceUID' in level_uids and hasattr(dataset, 'file_meta'):
            if hasattr(dataset.file_meta, 'MediaStorageSOPInstanceUID'):
                dataset.file_meta.MediaStorageSOPInstanceUID = level_uids['SOPInstanceUID']
                logging.info(f"[UID DEBUG] Applied MediaStorageSOPInstanceUID: {level_uids['SOPInstanceUID']}")

        logging.info(f"[UID DEBUG] Final dataset Study UID: {getattr(dataset, 'StudyInstanceUID', 'NONE')}")
        logging.info(f"[UID DEBUG] Final dataset Series UID: {getattr(dataset, 'SeriesInstanceUID', 'NONE')}")
        logging.info(f"[UID DEBUG] Final dataset Instance UID: {getattr(dataset, 'SOPInstanceUID', 'NONE')}")

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
