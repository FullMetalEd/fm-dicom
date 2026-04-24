"""
Job management infrastructure for background task execution.
"""

import logging
import time
from typing import Optional, Callable
from PyQt6.QtCore import QObject, QThread, pyqtSignal, QThreadPool, QRunnable, pyqtSlot

class JobSignals(QObject):
    """Signals for communicating job status to the UI."""
    started = pyqtSignal()
    progress = pyqtSignal(int, int, str)  # current, total, status
    finished = pyqtSignal(object)         # result data
    failed = pyqtSignal(str)              # error message
    cancelled = pyqtSignal()

class BaseJob(QRunnable):
    """Base class for all background jobs."""
    def __init__(self, title: str):
        super().__init__()
        self.title = title
        self.signals = JobSignals()
        self._is_cancelled = False
        self.start_time = None
        self.end_time = None
        self.setAutoDelete(True)

    def cancel(self):
        """Request job cancellation."""
        self._is_cancelled = True
        self.signals.cancelled.emit()

    def is_cancelled(self) -> bool:
        """Check if the job has been cancelled."""
        return self._is_cancelled

    def run(self):
        """To be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement run()")

    def start_timer(self):
        """Mark the start time of the job."""
        self.start_time = time.time()
        self.signals.started.emit()

    def stop_timer(self):
        """Mark the end time of the job."""
        self.end_time = time.time()

    def get_duration(self) -> float:
        """Return the duration of the job in seconds."""
        if self.start_time is None:
            return 0.0
        end = self.end_time if self.end_time else time.time()
        return end - self.start_time

    def view_results(self):
        """Optionally show detailed results for this job. Subclasses should override."""
        pass

class JobManager(QObject):
    """Central manager for dispatching and tracking background jobs."""
    
    job_added = pyqtSignal(object)  # Emitted when a new job is submitted
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread_pool = QThreadPool.globalInstance()
        self.active_jobs = []
        logging.info(f"JobManager initialized with max threads: {self.thread_pool.maxThreadCount()}")

    def submit_job(self, job: BaseJob):
        """Submit a job for execution."""
        logging.info(f"Submitting background job: {job.title}")
        self.active_jobs.append(job)
        
        # Connect to cleanup
        job.signals.finished.connect(lambda _: self._cleanup_job(job))
        job.signals.failed.connect(lambda _: self._cleanup_job(job))
        job.signals.cancelled.connect(lambda: self._cleanup_job(job))
        
        self.job_added.emit(job)
        self.thread_pool.start(job)

    def _cleanup_job(self, job: BaseJob):
        """Remove job from active list once finished."""
        if job in self.active_jobs:
            self.active_jobs.remove(job)
            logging.debug(f"Job cleaned up: {job.title}")

class DummyJob(BaseJob):
    """A simple job for testing the Task Center."""
    def __init__(self, title: str, duration_sec: int = 5):
        super().__init__(title)
        self.duration_sec = duration_sec

    def run(self):
        import time
        self.start_timer()
        try:
            for i in range(self.duration_sec + 1):
                if self.is_cancelled():
                    return
                
                progress = int((i / self.duration_sec) * 100)
                self.signals.progress.emit(i, self.duration_sec, f"Step {i} of {self.duration_sec}...")
                time.sleep(1)
            
            self.stop_timer()
            self.signals.finished.emit({"status": "success"})
        except Exception as e:
            self.stop_timer()
            self.signals.failed.emit(str(e))
