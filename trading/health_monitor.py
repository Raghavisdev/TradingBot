import time
import threading
import logging
import os

import sys

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from config import HEALTH_LOG_INTERVAL, LOG_LEVEL
from database.database import database

logger = logging.getLogger("HealthMonitor")


def get_memory_usage_mb():
    if HAS_PSUTIL:
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / (1024 * 1024)
        except Exception:
            pass

    # Windows OS native API fallback (ctypes)
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return counters.WorkingSetSize / (1024 * 1024)
        except Exception:
            pass

    # POSIX fallback
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except Exception:
        pass

    return 0.0


class HealthMonitor:

    def __init__(self, tracker_manager, interval=HEALTH_LOG_INTERVAL):
        self.tracker_manager = tracker_manager
        self.interval = interval
        self.running = False
        self.thread = None
        self.start_time = time.time()

    def start(self):
        if self.running:
            return
        self.running = True
        self.start_time = time.time()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        logger.info("Health Monitor daemon started (logging status every %ds)", self.interval)

    def stop(self):
        self.running = False

    def log_status(self):
        uptime_sec = time.time() - self.start_time
        uptime_hours = uptime_sec / 3600.0

        try:
            signals = database.get_signals()
            snapshots = database.get_snapshots()
            outcomes = database.get_outcomes()
            signal_count = len(signals)
            snapshot_count = len(snapshots)
            outcome_count = len(outcomes)
        except Exception as e:
            logger.warning("Error fetching database stats for health log: %s", e)
            signal_count = snapshot_count = outcome_count = 0

        active_trackers = len(getattr(self.tracker_manager, "trackers", {}))
        mem_mb = get_memory_usage_mb()

        status_text = (
            "\n" + "=" * 45 + "\n"
            "RUNTIME HEALTH STATUS\n"
            + "=" * 45 + f"\n"
            f"  Uptime              : {uptime_hours:.2f}h ({int(uptime_sec)}s)\n"
            f"  Total Signals       : {signal_count}\n"
            f"  Active Trackers     : {active_trackers}\n"
            f"  Total Snapshots     : {snapshot_count}\n"
            f"  Completed Outcomes  : {outcome_count}\n"
            f"  Memory Usage        : {mem_mb:.2f} MB\n"
            f"  SQLite Journal Mode : WAL\n"
            + "=" * 45
        )
        logger.info(status_text)

    def run(self):
        while self.running:
            time.sleep(self.interval)
            if self.running:
                try:
                    self.log_status()
                except Exception as e:
                    logger.error("Error during health status log: %s", e)


health_monitor = None
