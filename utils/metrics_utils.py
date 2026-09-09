import os
import sys
import time
import shutil
import psutil

try:
    import resource
except ImportError:
    resource = None

class ResourceTracker:
    """Measures resource consumption (wall time, CPU time, peak RSS, swap, disk, output size) for render tasks."""
    
    def __init__(self, target_dir="."):
        self.target_dir = target_dir
        self.start_wall = 0.0
        self.start_cpu = 0.0
        self.swap_before_mb = 0.0
        self.disk_before_mb = 0.0

    def start(self):
        self.start_wall = time.time()
        self.start_cpu = time.process_time()
        try:
            self.swap_before_mb = round(psutil.swap_memory().used / (1024 * 1024), 2)
        except Exception:
            self.swap_before_mb = 0.0

        try:
            du = shutil.disk_usage(self.target_dir)
            self.disk_before_mb = round((du.total - du.free) / (1024 * 1024), 2)
        except Exception:
            self.disk_before_mb = 0.0
        return self

    def finish(self, output_path=None):
        wall_time = round(time.time() - self.start_wall, 2)
        cpu_time = round(time.process_time() - self.start_cpu, 2)

        # Peak RSS in MB
        peak_rss_mb = 0.0
        if resource:
            try:
                # On Linux ru_maxrss is in kilobytes
                peak_rss_mb = round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024.0, 2)
                if peak_rss_mb == 0:
                    peak_rss_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 2)
            except Exception:
                pass

        if peak_rss_mb == 0:
            try:
                peak_rss_mb = round(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024), 2)
            except Exception:
                peak_rss_mb = 0.0

        # Swap metrics
        try:
            swap_after_mb = round(psutil.swap_memory().used / (1024 * 1024), 2)
        except Exception:
            swap_after_mb = self.swap_before_mb

        swap_delta_mb = round(swap_after_mb - self.swap_before_mb, 2)

        # Disk metrics
        try:
            du = shutil.disk_usage(self.target_dir)
            disk_after_mb = round((du.total - du.free) / (1024 * 1024), 2)
        except Exception:
            disk_after_mb = self.disk_before_mb

        # Output file size
        output_size_mb = 0.0
        if output_path and os.path.exists(output_path):
            try:
                output_size_mb = round(os.path.getsize(output_path) / (1024 * 1024), 2)
            except Exception:
                output_size_mb = 0.0

        metrics = {
            "wall_time_sec": wall_time,
            "cpu_time_sec": cpu_time,
            "peak_rss_mb": peak_rss_mb,
            "swap_before_mb": self.swap_before_mb,
            "swap_after_mb": swap_after_mb,
            "swap_delta_mb": swap_delta_mb,
            "disk_before_mb": self.disk_before_mb,
            "disk_after_mb": disk_after_mb,
            "output_size_mb": output_size_mb
        }

        log_str = (
            f"📊 [Render Metrics] Wall: {wall_time}s | CPU: {cpu_time}s | Peak RSS: {peak_rss_mb} MB | "
            f"Swap Delta: {swap_delta_mb} MB | Output Size: {output_size_mb} MB"
        )

        return metrics, log_str
