"""
Session management for Vi website login and authentication.
"""

import asyncio
import logging
import time
from typing import Optional

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.auth.auth import get_credentials
from app.config import settings
from app.utils.retry import async_retry

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages login sessions for the Vi website."""

    def __init__(self, browser_page_getter) -> None:
        """
        Initialize SessionManager.

        Args:
            browser_page_getter: Async callable that returns a Playwright Page
        """
        self._get_page = browser_page_getter
        self._last_login_time: float = 0
        self._is_logged_in: bool = False
        self._session_start: float = 0

    async def login(self) -> bool:
        """
        Perform login to Vi website.

        Returns:
            True if login successful
        """
        try:
            page = await self._get_page()
            credentials = get_credentials()

            logger.info("Navigating to Vi website...")
            await page.goto(settings.SCRAPER_URL, wait_until="networkidle", timeout=settings.BROWSER_TIMEOUT)

            if await self.detect_login_page(page):
                logger.info("Login page detected, filling credentials...")
                await self._fill_login_form(page, credentials.username, credentials.password)
                await self._submit_login(page)
                await self._wait_for_dashboard(page)

                if await self.verify_dashboard(page):
                    self._is_logged_in = True
                    self._last_login_time = time.time()
                    self._session_start = time.time()
                    logger.info("Login successful")
                    return True
                else:
                    logger.error("Dashboard not found after login")
                    return False
            else:
                logger.info("Already on dashboard, no login needed")
                self._is_logged_in = True
                self._last_login_time = time.time()
                self._session_start = time.time()
                return True

        except PlaywrightTimeout:
            logger.error("Login timed out")
            return False
        except Exception as e:
            logger.warning(f"Login skipped — credentials not configured or login failed: {e}")
            return False

    async def detect_login_page(self, page: Page) -> bool:
        """
        Detect if the current page is a login page.

        Args:
            page: Playwright page instance

        Returns:
            True if login page is detected
        """
        try:
            login_indicators = [
                'input[type="password"]',
                'input[name="password"]',
                'input[placeholder*="password" i]',
                'input[placeholder*="Password"]',
                'button:has-text("Login")',
                'button:has-text("Sign In")',
                'button:has-text("Submit")',
                '.login-form',
                '#login-form',
                '[data-testid="login"]',
            ]

            for selector in login_indicators:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        logger.debug(f"Login indicator found: {selector}")
                        return True
                except Exception:
                    continue

            login_keywords = ["login", "signin", "sign-in", "authenticate", "credentials"]
            current_url = page.url.lower()
            for keyword in login_keywords:
                if keyword in current_url:
                    return True

            return False

        except Exception as e:
            logger.error(f"Error detecting login page: {e}")
            return False

    async def _fill_login_form(
        self, page: Page, username: str, password: str
    ) -> None:
        """Fill in the login form fields."""
        username_selectors = [
            'input[type="email"]',
            'input[name="email"]',
            'input[name="username"]',
            'input[name="userId"]',
            'input[placeholder*="email" i]',
            'input[placeholder*="username" i]',
            'input[placeholder*="mobile" i]',
            'input[id*="user"]',
            'input[id*="email"]',
        ]

        password_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[name="pwd"]',
            'input[placeholder*="password" i]',
            'input[id*="pass"]',
        ]

        for selector in username_selectors:
            try:
                element = await page.wait_for_selector(selector, timeout=2000)
                if element:
                    await element.fill(username)
                    logger.debug(f"Username filled using: {selector}")
                    break
            except PlaywrightTimeout:
                continue

        for selector in password_selectors:
            try:
                element = await page.wait_for_selector(selector, timeout=2000)
                if element:
                    await element.fill(password)
                    logger.debug(f"Password filled using: {selector}")
                    break
            except PlaywrightTimeout:
                continue

    async def _submit_login(self, page: Page) -> None:
        """Submit the login form."""
        submit_selectors = [
            'button[type="submit"]',
            'button:has-text("Login")',
            'button:has-text("Sign In")',
            'button:has-text("Submit")',
            'input[type="submit"]',
            'button:has-text("Continue")',
        ]

        for selector in submit_selectors:
            try:
                element = await page.wait_for_selector(selector, timeout=2000)
                if element:
                    await element.click()
                    logger.debug(f"Submit button clicked: {selector}")
                    return
            except PlaywrightTimeout:
                continue

        await page.keyboard.press("Enter")
        logger.debug("Enter key pressed for form submission")

    async def _wait_for_dashboard(self, page: Page) -> None:
        """Wait for the dashboard to load after login."""
        dashboard_selectors = [
            '.dashboard',
            '#dashboard',
            '[data-testid="dashboard"]',
            '.home-page',
            '.main-content',
            'nav',
            '.sidebar',
        ]

        for selector in dashboard_selectors:
            try:
                await page.wait_for_selector(selector, timeout=10000)
                logger.debug(f"Dashboard element found: {selector}")
                return
            except PlaywrightTimeout:
                continue

        await page.wait_for_load_state("networkidle", timeout=15000)

    async def verify_dashboard(self, page: Page) -> bool:
        """
        Verify that we are on the dashboard after login.

        Returns:
            True if dashboard is detected
        """
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)

            dashboard_indicators = [
                '.dashboard',
                '#dashboard',
                'nav',
                '.sidebar',
                '.user-menu',
                '.logout',
                'a:has-text("Logout")',
                'a:has-text("Sign Out")',
                'button:has-text("Logout")',
            ]

            for selector in dashboard_indicators:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        return True
                except Exception:
                    continue

            login_indicators = [
                'input[type="password"]',
                'button:has-text("Login")',
                '.login-form',
            ]
            for selector in login_indicators:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        return False
                except Exception:
                    continue

            return True

        except Exception as e:
            logger.error(f"Dashboard verification failed: {e}")
            return False

    async def is_logged_in(self) -> bool:
        """Check if the current session is still valid."""
        if not self._is_logged_in:
            return False

        session_duration = time.time() - self._session_start
        timeout_seconds = settings.SESSION_TIMEOUT_MINUTES * 60
        if session_duration > timeout_seconds:
            logger.info("Session expired due to timeout")
            self._is_logged_in = False
            return False

        try:
            page = await self._get_page()
            if await self.detect_login_page(page):
                self._is_logged_in = False
                return False
            return True
        except Exception:
            self._is_logged_in = False
            return False

    async def refresh_session(self) -> bool:
        """
        Refresh the current session by relogging if needed.

        Returns:
            True if session is valid after refresh
        """
        if await self.is_logged_in():
            return True
        return await self.login()

    def get_session_info(self) -> dict:
        """Get current session information."""
        return {
            "is_logged_in": self._is_logged_in,
            "last_login_time": self._last_login_time,
            "session_start": self._session_start,
            "session_duration": time.time() - self._session_start if self._session_start else 0,
        }
