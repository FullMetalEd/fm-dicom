"""
Background DICOM Storage SCP service for receiving studies.
"""

from __future__ import annotations

import os
import threading
import logging
from pathlib import Path
from typing import Dict

from PyQt6.QtCore import QObject, pyqtSignal

try:
    from pynetdicom import AE, evt, StoragePresentationContexts
except ImportError:  # pragma: no cover - optional dependency
    AE = None  # type: ignore


class DicomReceiveService(QObject):
    """Listens for inbound C-STORE requests and stores them to disk."""

    study_progress = pyqtSignal(dict)
    study_completed = pyqtSignal(dict)
    study_failed = pyqtSignal(dict, str)

    def __init__(self, config: dict, logger: logging.Logger | None = None):
        super().__init__()
        self.config = config or {}
        self._server = None
        self._ae = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._studies: Dict[str, dict] = {}
        self._logger = logger or logging.getLogger("fm_dicom.receive")
        self._configure_logger()

        receive_dir = Path(self.config.get("receive_dir", ".")).expanduser()
        receive_dir.mkdir(parents=True, exist_ok=True)
        self.receive_dir = receive_dir

        self.enabled = bool(self.config.get("enabled", True)) and AE is not None
        if AE is None:
            self._logger.warning("pynetdicom is not available; DICOM receive service disabled.")

    def _configure_logger(self):
        log_path = self.config.get("log_path")
        if not log_path:
            return
        log_path = os.path.expanduser(log_path)
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        if not any(isinstance(h, logging.FileHandler) and getattr(h, "_fm_receive", False) for h in self._logger.handlers):
            handler = logging.FileHandler(log_path, encoding="utf-8")
            handler._fm_receive = True  # type: ignore[attr-defined]
            handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            self._logger.addHandler(handler)
            self._logger.setLevel(logging.INFO)
            self._logger.propagate = False

    def start(self):
        if not self.enabled or self._thread:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._server:
            self._server.shutdown()
            self._server = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    # pylint: disable=too-many-locals
    def _run_server(self):
        try:
            ae = AE(ae_title=str(self.config.get("ae_title", "FM_DICOM")).encode("utf-8"))
            for context in StoragePresentationContexts:
                ae.add_supported_context(context.abstract_syntax, context.transfer_syntaxes)

            handlers = [
                (evt.EVT_C_STORE, self._handle_store),
                (evt.EVT_CONN_OPEN, self._handle_conn_open),
                (evt.EVT_CONN_CLOSE, self._handle_conn_close),
            ]

            bind_address = self.config.get("bind_address", "0.0.0.0")
            port = int(self.config.get("port", 11112))
            self._logger.info("Starting DICOM receiver on %s:%s", bind_address, port)
            self._server = ae.start_server(
                (bind_address, port),
                block=False,
                evt_handlers=handlers,
            )
            self._ae = ae
            while not self._stop_event.is_set():
                self._stop_event.wait(0.25)
        except Exception as exc:  # pragma: no cover - background service
            self._logger.error("Receive service failed: %s", exc, exc_info=True)
            self.study_failed.emit({}, str(exc))

    def _handle_conn_open(self, event):
        self._logger.info("Association opened from %s (AE: %s)", event.address, event.assoc.requestor.ae_title.decode().strip())

    def _handle_conn_close(self, event):
        assoc_id = id(event.assoc)
        closing = [uid for uid, info in self._studies.items() if info.get("assoc_id") == assoc_id]
        for study_uid in closing:
            info = self._studies.pop(study_uid, None)
            if not info:
                continue
            self._logger.info(
                "Study %s completed (%s instances)", study_uid, info["instance_count"]
            )
            payload = {
                "study_uid": study_uid,
                "patient_label": info["patient_label"],
                "study_description": info["study_description"],
                "study_dir": str(info["study_dir"]),
                "file_paths": info["files"],
            }
            self.study_completed.emit(payload)

    def _is_authorized(self, event) -> bool:
        allowed_hosts = self.config.get("allowed_hosts") or []
        allowed_aes = self.config.get("allowed_ae_titles") or []
        host_ok = True
        ae_ok = True
        if allowed_hosts:
            host_ok = event.requestor.address in allowed_hosts
        if allowed_aes:
            ae_title = event.requestor.ae_title.decode().strip()
            ae_ok = ae_title in allowed_aes
        return host_ok and ae_ok

    # pylint: disable=unused-argument
    def _handle_store(self, event):
        if not self._is_authorized(event):
            self._logger.warning(
                "Rejected C-STORE from %s (AE: %s)",
                event.requestor.address,
                event.requestor.ae_title.decode().strip(),
            )
            return 0xA700

        ds = event.dataset
        ds.file_meta = event.file_meta
        study_uid = getattr(ds, "StudyInstanceUID", None)
        if not study_uid:
            self._logger.warning("Incoming instance missing StudyInstanceUID; rejected")
            return 0xA900

        patient_name = getattr(ds, "PatientName", "Unknown")
        patient_id = getattr(ds, "PatientID", "Unknown ID")
        study_desc = getattr(ds, "StudyDescription", "Study")

        study_dir = self.receive_dir / study_uid
        series_dir = study_dir / getattr(ds, "SeriesInstanceUID", "unknown_series")
        series_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{getattr(ds, 'SOPInstanceUID', 'unknown')}.dcm"
        file_path = series_dir / filename
        ds.save_as(file_path, write_like_original=False)

        assoc_id = id(event.assoc)
        info = self._studies.setdefault(
            study_uid,
            {
                "assoc_id": assoc_id,
                "patient_label": f"{patient_name} ({patient_id})",
                "study_description": study_desc,
                "study_dir": study_dir,
                "files": [],
                "instance_count": 0,
            },
        )
        info["files"].append(str(file_path))
        info["instance_count"] += 1

        payload = {
            "study_uid": study_uid,
            "patient_label": info["patient_label"],
            "study_description": study_desc,
            "instance_count": info["instance_count"],
        }
        self.study_progress.emit(payload)
        return 0x0000
