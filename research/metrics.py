"""
research/metrics.py — Metric Logging Infrastructure
Thread-safe, append-only JSONL metric logger with performance and accuracy decorators.
"""

import os
import time
import json
import functools
import threading
import logging

logger = logging.getLogger(__name__)

LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "logs")
METRICS_FILE = os.path.join(LOGS_DIR, "metrics.jsonl")

_file_lock = threading.Lock()

class MetricLogger:
    @staticmethod
    def log(metric_name: str, value: float | int | dict | str, context: dict | None = None):
        """Appends metric entry to metrics.jsonl."""
        os.makedirs(LOGS_DIR, exist_ok=True)
        payload = {
            "timestamp": time.time(),
            "datetime": time.strftime("%Y-%m-%d %H:%M:%S"),
            "metric": metric_name,
            "value": value,
            "context": context or {}
        }
        with _file_lock:
            with open(METRICS_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload) + "\n")

def log_metric(metric_name: str, value: float | int | dict | str, context: dict | None = None):
    """Utility wrapper for logging metrics."""
    MetricLogger.log(metric_name, value, context)

def log_latency(metric_name: str):
    """Decorator to log function wall-clock execution latency in seconds."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                res = func(*args, **kwargs)
                latency = time.time() - start
                MetricLogger.log(f"{metric_name}_latency", latency, {"status": "success", "function": func.__name__})
                return res
            except Exception as e:
                latency = time.time() - start
                MetricLogger.log(f"{metric_name}_latency", latency, {"status": "error", "error": str(e), "function": func.__name__})
                raise
        return wrapper
    return decorator

def log_success_rate(metric_name: str):
    """Decorator to log success/failure outcome for a function call."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                res = func(*args, **kwargs)
                MetricLogger.log(f"{metric_name}_success", 1.0, {"function": func.__name__})
                return res
            except Exception as e:
                MetricLogger.log(f"{metric_name}_success", 0.0, {"function": func.__name__, "error": str(e)})
                raise
        return wrapper
    return decorator
