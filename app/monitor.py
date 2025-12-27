import json
import logging
import shutil
import subprocess
import threading
import time

import psutil

from app.logging_setup import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

class HardwareMonitor:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(HardwareMonitor, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.latest_stats = {
            "gpu_usage": 0.0,
            "gpu_power": 0.0,
            "gpu_temp": 0.0,
            "cpu_usage": 0.0,
            "ram_usage": 0.0,
            "soc_temp": 0.0
        }
        self.running = False
        self._check_dependencies()
        self._start_background_thread()
        self._initialized = True

    def _check_dependencies(self):
        """Check if macmon is installed"""
        if not shutil.which("macmon"):
            logger.info("macmon not found. GPU stats will be 0.")
            logger.info("Run: brew install vladkens/tap/macmon")
            self.has_macmon = False
        else:
            self.has_macmon = True

    def _start_background_thread(self):
        self.running = True
        thread = threading.Thread(target=self._monitor_loop, daemon=True)
        thread.start()

    def _coerce_float(self, value) -> float:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return 0.0
        if isinstance(value, (list, tuple)):
            if not value:
                return 0.0
            values = [self._coerce_float(item) for item in value]
            return sum(values) / len(values) if values else 0.0
        if isinstance(value, dict):
            for key in ("value", "avg", "average", "mean"):
                if key in value:
                    return self._coerce_float(value[key])
            values = [self._coerce_float(item) for item in value.values()]
            return sum(values) / len(values) if values else 0.0
        return 0.0

    def _monitor_loop(self):
        """Reads stream from macmon and updates stats"""
        process = None
        if self.has_macmon:
            # Run macmon in pipe mode to get JSON stream
            process = subprocess.Popen(
                ["macmon", "pipe"], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True, 
                bufsize=1
            )

        while self.running:
            try:
                # Get Standard Stats (CPU/RAM) via psutil
                self.latest_stats["cpu_usage"] = psutil.cpu_percent(interval=None)
                self.latest_stats["ram_usage"] = psutil.virtual_memory().percent

                # Get Apple Silicon Stats via macmon
                if process and process.stdout:
                    line = process.stdout.readline()
                    if line:
                        data = json.loads(line)
                        # Extract relevant keys (macmon keys may vary slightly by version)
                        self.latest_stats["gpu_usage"] = self._coerce_float(data.get("gpu_usage", 0))
                        self.latest_stats["gpu_power"] = self._coerce_float(data.get("gpu_power", 0)) / 1000.0 # mW -> W
                        self.latest_stats["gpu_temp"] = self._coerce_float(data.get("gpu_temp_avg", 0))
                        self.latest_stats["soc_temp"] = self._coerce_float(data.get("soc_temp", 0))

                time.sleep(0.5) # Update 2x per second
            except Exception:
                logger.critical("Monitor error", exc_info=True)
                time.sleep(1)

    def get_snapshot(self):
        """Returns the current stats"""
        return self.latest_stats.copy()

# Global Singleton
monitor = HardwareMonitor()
