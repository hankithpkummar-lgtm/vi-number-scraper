"""
Health check endpoints and health monitoring.
"""

import logging
import time
from typing import Any, Dict, Optional

from app.services.monitoring import metrics_collector

logger = logging.getLogger(__name__)


class HealthChecker:
    """Aggregates health data from all components."""

    def __init__(self) -> None:
        self._browser_healthy = False
        self._database_healthy = False
        self._gas_healthy = False
        self._scraper_running = False
        self._logged_in = False
        self._records_count = 0
        self._start_time = time.time()

    def set_browser_health(self, healthy: bool) -> None:
        """Set browser health status."""
        self._browser_healthy = healthy

    def set_database_health(self, healthy: bool) -> None:
        """Set database health status."""
        self._database_healthy = healthy

    def set_gas_health(self, healthy: bool) -> None:
        """Set GAS health status."""
        self._gas_healthy = healthy

    def set_scraper_running(self, running: bool) -> None:
        """Set scraper running status."""
        self._scraper_running = running

    def set_logged_in(self, logged_in: bool) -> None:
        """Set login status."""
        self._logged_in = logged_in

    def set_records_count(self, count: int) -> None:
        """Set total records count."""
        self._records_count = count

    def get_health(self) -> Dict[str, Any]:
        """
        Get basic health status.

        Returns:
            Health status dictionary
        """
        overall_status = "healthy"
        if not self._browser_healthy or not self._database_healthy:
            overall_status = "degraded"
        if not self._browser_healthy and not self._database_healthy:
            overall_status = "unhealthy"

        return {
            "status": overall_status,
            "logged_in": self._logged_in,
            "database": "connected" if self._database_healthy else "disconnected",
            "scraper": "running" if self._scraper_running else "stopped",
            "browser": "healthy" if self._browser_healthy else "unhealthy",
            "records": self._records_count,
            "uptime": round(time.time() - self._start_time, 2),
        }

    def get_detailed_status(self) -> Dict[str, Any]:
        """
        Get detailed status with all metrics.

        Returns:
            Detailed status dictionary
        """
        basic_health = self.get_health()
        metrics = metrics_collector.get_metrics()
        health = metrics_collector.get_health()

        return {
            **basic_health,
            "metrics": metrics,
            "system": health,
            "components": {
                "browser": {
                    "status": "healthy" if self._browser_healthy else "unhealthy",
                },
                "database": {
                    "status": "connected" if self._database_healthy else "disconnected",
                },
                "gas": {
                    "status": "healthy" if self._gas_healthy else "unhealthy",
                },
                "scraper": {
                    "status": "running" if self._scraper_running else "stopped",
                },
            },
        }

    def get_prometheus_metrics(self) -> str:
        """
        Get Prometheus-compatible metrics.

        Returns:
            Prometheus metrics string
        """
        return metrics_collector.get_prometheus_metrics()


health_checker = HealthChecker()
