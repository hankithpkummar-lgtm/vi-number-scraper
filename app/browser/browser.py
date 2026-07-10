"""
Playwright browser management with anti-detection and session persistence.
"""

import asyncio
import logging
import os
import random
import time
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from app.config import settings
from app.utils.retry import CircuitBreaker

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

BLOCKED_RESOURCE_TYPES = {
    "image",
    "media",
    "font",
}

BLOCKED_DOMAINS = {
    "google-analytics.com",
    "googletagmanager.com",
    "doubleclick.net",
    "googlesyndication.com",
    "googleadservices.com",
    "facebook.com",
    "connect.facebook.net",
    "twitter.com",
    "analytics.twitter.com",
    "hotjar.com",
    "sentry.io",
    "newrelic.com",
    "chartbeat.com",
}


class BrowserManager:
    """Manages Playwright browser lifecycle with anti-detection measures."""

    def __init__(self) -> None:
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=3, recovery_timeout=120
        )
        self._last_health_check: float = 0
        self._is_healthy: bool = False
        self._launch_lock = asyncio.Lock()

    async def launch_browser(self) -> Page:
        """
        Launch browser with anti-detection measures.

        Returns:
            Active page instance
        """
        async with self._launch_lock:
            if self._page and not self._page.is_closed():
                return self._page

            try:
                self._playwright = await async_playwright().start()

                cookie_dir = Path(settings.COOKIE_DIR)
                cookie_dir.mkdir(parents=True, exist_ok=True)

                user_agent = random.choice(USER_AGENTS)
                viewport = {
                    "width": random.randint(1280, 1920),
                    "height": random.randint(720, 1080),
                }

                self._context = await self._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(cookie_dir),
                    headless=settings.HEADLESS,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-extensions",
                        "--disable-infobars",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-web-security",
                        "--disable-features=VizDisplayCompositor",
                    ],
                    user_agent=user_agent,
                    viewport=viewport,
                    locale="en-IN",
                    timezone_id="Asia/Kolkata",
                    permissions=["geolocation"],
                    ignore_https_errors=True,
                )

                await self._context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en']
                    });
                    window.chrome = {
                        runtime: {}
                    };
                """)

                self._context.on("page", lambda page: asyncio.ensure_future(self._handle_new_page(page)))

                self._page = await self._context.new_page()

                await self._setup_route_blocking()

                self._is_healthy = True
                self._last_health_check = time.time()
                await self._circuit_breaker.record_success()

                logger.info(f"Browser launched successfully with UA: {user_agent[:50]}...")
                return self._page

            except Exception as e:
                self._is_healthy = False
                await self._circuit_breaker.record_failure()
                logger.error(f"Failed to launch browser: {e}")
                raise

    async def _handle_new_page(self, page: Page) -> None:
        """Handle newly opened pages."""
        await self._setup_route_blocking_for_page(page)

    async def _setup_route_blocking(self) -> None:
        """Set up route blocking for the main page."""
        if self._page:
            await self._setup_route_blocking_for_page(self._page)

    async def _setup_route_blocking_for_page(self, page: Page) -> None:
        """Set up resource blocking for a specific page."""
        async def block_resources(route) -> None:
            request = route.request
            if request.resource_type in BLOCKED_RESOURCE_TYPES:
                await route.abort()
                return
            for domain in BLOCKED_DOMAINS:
                if domain in request.url:
                    await route.abort()
                    return
            await route.continue_()

        await page.route("**/*", block_resources)

    async def close_browser(self) -> None:
        """Close the browser and clean up resources."""
        try:
            if self._page and not self._page.is_closed():
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")
        finally:
            self._page = None
            self._context = None
            self._playwright = None
            self._browser = None
            self._is_healthy = False
            logger.info("Browser closed")

    async def restart_browser(self) -> Page:
        """Restart the browser (close and relaunch)."""
        logger.info("Restarting browser...")
        await self.close_browser()
        await asyncio.sleep(2)
        return await self.launch_browser()

    async def get_page(self) -> Page:
        """Get the current page, launching browser if needed."""
        if self._page is None or self._page.is_closed():
            return await self.launch_browser()
        return self._page

    async def health_check(self) -> dict:
        """
        Perform browser health check.

        Returns:
            Dictionary with health status
        """
        try:
            if not self._page or self._page.is_closed():
                self._is_healthy = False
                return {"status": "unhealthy", "reason": "No active page"}

            await self._page.evaluate("() => document.readyState")
            self._last_health_check = time.time()
            self._is_healthy = True
            return {
                "status": "healthy",
                "url": self._page.url,
                "title": await self._page.title(),
                "last_check": self._last_health_check,
            }
        except Exception as e:
            self._is_healthy = False
            return {"status": "unhealthy", "error": str(e)}

    @property
    def is_healthy(self) -> bool:
        """Check if browser is in healthy state."""
        return self._is_healthy

    @property
    def is_running(self) -> bool:
        """Check if browser is running."""
        return self._page is not None and not self._page.is_closed()
