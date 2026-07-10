"""
Monitoring service for tracking application metrics.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

import psutil

logger = logging.getLogger(__name__)


@dataclass
class Metrics:
    """Application metrics container."""

    total_records: int = 0
    duplicates_blocked: int = 0
    failed_inserts: int = 0

    login_status: str = "unknown"
    scraper_status: str = "stopped"
    browser_status: str = "unknown"

    start_time: float = field(default_factory=time.time)
    last_sync_time: float = 0
    last_scrape_time: float = 0
    last_health_check: float = 0

    gas_uploads: int = 0
    gas_failures: int = 0
    session_refreshes: int = 0


class MetricsCollector:
    """Collects and manages application metrics."""

    def __init__(self) -> None:
        self._metrics = Metrics()
        self._start_time = time.time()

    def record_number_found(self) -> None:
        """Record a new number found."""
        self._metrics.total_records += 1

    def record_duplicate_blocked(self) -> None:
        """Record a duplicate number blocked."""
        self._metrics.duplicates_blocked += 1

    def record_failed_insert(self) -> None:
        """Record a failed database insert."""
        self._metrics.failed_inserts += 1

    def set_login_status(self, status: str) -> None:
        """Set the login status."""
        self._metrics.login_status = status

    def set_scraper_status(self, status: str) -> None:
        """Set the scraper status."""
        self._metrics.scraper_status = status

    def set_browser_status(self, status: str) -> None:
        """Set the browser status."""
        self._metrics.browser_status = status

    def record_sync(self) -> None:
        """Record a successful sync."""
        self._metrics.last_sync_time = time.time()
        self._metrics.gas_uploads += 1

    def record_sync_failure(self) -> None:
        """Record a failed sync."""
        self._metrics.gas_failures += 1

    def record_scrape(self) -> None:
        """Record a scrape action."""
        self._metrics.last_scrape_time = time.time()

    def record_session_refresh(self) -> None:
        """Record a session refresh."""
        self._metrics.session_refreshes += 1

    def get_metrics(self) -> dict:
        """Get current metrics as dictionary."""
        return {
            "total_records": self._metrics.total_records,
            "duplicates_blocked": self._metrics.duplicates_blocked,
            "failed_inserts": self._metrics.failed_inserts,
            "login_status": self._metrics.login_status,
            "scraper_status": self._metrics.scraper_status,
            "browser_status": self._metrics.browser_status,
            "uptime_seconds": time.time() - self._start_time,
            "last_sync_time": self._metrics.last_sync_time,
            "last_scrape_time": self._metrics.last_scrape_time,
            "gas_uploads": self._metrics.gas_uploads,
            "gas_failures": self._metrics.gas_failures,
            "session_refreshes": self._metrics.session_refreshes,
        }

    def get_health(self) -> dict:
        """Get health status."""
        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            cpu_percent = process.cpu_percent(interval=0.1)

            return {
                "status": "healthy",
                "memory_mb": round(memory_info.rss / 1024 / 1024, 2),
                "cpu_percent": cpu_percent,
                "uptime_seconds": round(time.time() - self._start_time, 2),
                "pid": os.getpid(),
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def get_prometheus_metrics(self) -> str:
        """Get metrics in Prometheus format."""
        metrics = self.get_metrics()
        lines = [
            "# HELP vi_scraper_total_records Total numbers found",
            "# TYPE vi_scraper_total_records counter",
            f"vi_scraper_total_records {metrics['total_records']}",
            "",
            "# HELP vi_scraper_duplicates_blocked Duplicates blocked",
            "# TYPE vi_scraper_duplicates_blocked counter",
            f"vi_scraper_duplicates_blocked {metrics['duplicates_blocked']}",
            "",
            "# HELP vi_scraper_failed_inserts Failed inserts",
            "# TYPE vi_scraper_failed_inserts counter",
            f"vi_scraper_failed_inserts {metrics['failed_inserts']}",
            "",
            "# HELP vi_scraper_uptime_seconds Uptime in seconds",
            "# TYPE vi_scraper_uptime_seconds gauge",
            f"vi_scraper_uptime_seconds {metrics['uptime_seconds']}",
            "",
            "# HELP vi_scraper_gas_uploads GAS uploads",
            "# TYPE vi_scraper_gas_uploads counter",
            f"vi_scraper_gas_uploads {metrics['gas_uploads']}",
            "",
            "# HELP vi_scraper_gas_failures GAS failures",
            "# TYPE vi_scraper_gas_failures counter",
            f"vi_scraper_gas_failures {metrics['gas_failures']}",
        ]

        health = self.get_health()
        if "memory_mb" in health:
            lines.extend([
                "",
                "# HELP vi_scraper_memory_mb Memory usage in MB",
                "# TYPE vi_scraper_memory_mb gauge",
                f"vi_scraper_memory_mb {health['memory_mb']}",
                "",
                "# HELP vi_scraper_cpu_percent CPU usage percent",
                "# TYPE vi_scraper_cpu_percent gauge",
                f"vi_scraper_cpu_percent {health['cpu_percent']}",
            ])

        return "\n".join(lines)


metrics_collector = MetricsCollector()
