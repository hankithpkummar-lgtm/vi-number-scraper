"""
Multi-worker scraper manager for concurrent number scraping.
"""

import asyncio
import logging
import os
import random
import time
from pathlib import Path
from typing import Callable, List, Optional

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from app.config import settings
from app.scraper.scraper import ScraperEngine
from app.scraper.session import SessionManager
from app.dashboard import add_log

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}
BLOCKED_DOMAINS = {
    "google-analytics.com", "googletagmanager.com", "doubleclick.net",
    "googlesyndication.com", "googleadservices.com", "facebook.com",
    "connect.facebook.net", "twitter.com", "analytics.twitter.com",
    "hotjar.com", "sentry.io", "newrelic.com", "chartbeat.com",
}


class ScraperWorker:
    """Individual scraper worker with its own browser context."""

    def __init__(
        self,
        worker_id: int,
        playwright: Playwright,
        number_callback: Callable,
        gas_url: str = "",
    ) -> None:
        self.worker_id = worker_id
        self._pw = playwright
        self._callback = number_callback
        self._gas_url = gas_url

        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._scraper: Optional[ScraperEngine] = None
        self._session: Optional[SessionManager] = None

        self._is_running = False
        self._stats = {
            "numbers_found": 0,
            "cycles_completed": 0,
            "errors": 0,
            "start_time": 0,
            "last_cycle_time": 0,
        }
        # Track last activity for live dashboard display
        self._last_activity = "⏳ Starting..."
        self._last_activity_time = 0

    async def start(self) -> None:
        """Start this worker."""
        if self._is_running:
            return

        self._is_running = True
        self._stats["start_time"] = time.time()

        try:
            await self._launch_browser()
            await self._setup_scraper()
            logger.info(f"Worker {self.worker_id} started successfully")
        except Exception as e:
            logger.error(f"Worker {self.worker_id} failed to start: {e}")
            self._is_running = False
            raise

    async def _launch_browser(self) -> None:
        """Launch a separate browser for this worker."""
        user_agent = random.choice(USER_AGENTS)
        viewport = {"width": random.randint(1280, 1920), "height": random.randint(720, 1080)}

        cookie_dir = Path(settings.COOKIE_DIR) / f"worker_{self.worker_id}"
        cookie_dir.mkdir(parents=True, exist_ok=True)

        self._context = await self._pw.chromium.launch_persistent_context(
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
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)

        self._page = await self._context.new_page()

        # Block resources
        async def block_resources(route):
            request = route.request
            if request.resource_type in BLOCKED_RESOURCE_TYPES:
                await route.abort()
                return
            for domain in BLOCKED_DOMAINS:
                if domain in request.url:
                    await route.abort()
                    return
            await route.continue_()

        await self._page.route("**/*", block_resources)

        logger.debug(f"Worker {self.worker_id}: Browser launched with UA: {user_agent[:30]}...")

    async def _setup_scraper(self) -> None:
        """Setup scraper engine and session for this worker."""
        async def page_getter():
            return self._page

        self._session = SessionManager(page_getter)
        self._scraper = ScraperEngine(
            browser_page_getter=page_getter,
            session_manager=self._session,
            number_callback=self._callback,
        )

    async def run_cycle(self) -> dict:
        """
        Run a single scrape cycle.
        
        Returns:
            {'raw_numbers': [...], 'saved_numbers': [...], 'raw_count': int, 'saved_count': int}
        """
        if not self._is_running or not self._scraper:
            return {"raw_numbers": [], "saved_numbers": [], "raw_count": 0, "saved_count": 0}

        try:
            result = await self._scraper.scrape_cycle()
            raw_nums = result.get("raw_numbers", [])
            saved_nums = result.get("saved_numbers", [])
            
            self._stats["numbers_found"] += len(saved_nums)
            self._stats["cycles_completed"] += 1
            self._stats["last_cycle_time"] = time.time()

            if saved_nums:
                logger.info(
                    f"Worker {self.worker_id}: {len(saved_nums)} saved "
                    f"(total: {self._stats['numbers_found']})"
                )

            return {
                "raw_numbers": raw_nums,
                "saved_numbers": saved_nums,
                "raw_count": len(raw_nums),
                "saved_count": len(saved_nums),
            }

        except Exception as e:
            logger.error(f"Worker {self.worker_id}: Cycle error: {e}")
            self._stats["errors"] += 1
            return {"raw_numbers": [], "saved_numbers": [], "raw_count": 0, "saved_count": 0}

    async def stop(self) -> None:
        """Stop this worker."""
        self._is_running = False
        try:
            if self._page and not self._page.is_closed():
                await self._page.close()
            if self._context:
                await self._context.close()
        except Exception as e:
            logger.warning(f"Worker {self.worker_id}: Error closing browser: {e}")

        logger.info(f"Worker {self.worker_id} stopped")

    def set_activity(self, msg: str) -> None:
        """Update last activity message for live dashboard display."""
        self._last_activity = msg
        self._last_activity_time = time.time()

    def get_stats(self) -> dict:
        """Get worker statistics."""
        return {
            "worker_id": self.worker_id,
            "is_running": self._is_running,
            "uptime": time.time() - self._stats["start_time"] if self._stats["start_time"] else 0,
            "last_activity": self._last_activity,
            "last_activity_time": self._last_activity_time,
            **self._stats,
        }


class WorkerManager:
    """Manages multiple scraper workers."""

    def __init__(
        self,
        num_workers: int,
        number_callback: Callable,
    ) -> None:
        self.num_workers = num_workers
        self._callback = number_callback
        self._workers: List[ScraperWorker] = []
        self._playwright: Optional[Playwright] = None
        self._tasks: List[asyncio.Task] = []
        self._is_running = False

    async def start(self) -> None:
        """Start all workers."""
        if self._is_running:
            logger.warning("WorkerManager already running")
            return

        self._is_running = True
        self._playwright_cm = async_playwright()
        self._playwright = await self._playwright_cm.start()

        logger.info(f"Starting {self.num_workers} scraper workers...")
        add_log("info", f"🚀 Launching {self.num_workers} workers (staggered)...")

        for i in range(self.num_workers):
            worker_id = i + 1
            worker = ScraperWorker(
                worker_id=worker_id,
                playwright=self._playwright,
                number_callback=self._callback,
                gas_url=settings.GAS_URL,
            )
            try:
                await worker.start()
                self._workers.append(worker)
                add_log("success", f"✅ Worker #{worker_id}: Browser launched")
                # Stagger starts to avoid simultaneous login attempts
                if i < self.num_workers - 1:
                    await asyncio.sleep(random.uniform(3, 8))
            except Exception as e:
                logger.error(f"Failed to start worker {i + 1}: {e}")
                add_log("error", f"❌ Worker #{worker_id}: Failed to start — {str(e)[:80]}")

        logger.info(f"Started {len(self._workers)}/{self.num_workers} workers")
        add_log("info", f"📊 {len(self._workers)}/{self.num_workers} workers active")

        # Start worker loops
        for worker in self._workers:
            task = asyncio.create_task(self._worker_loop(worker))
            self._tasks.append(task)

    async def _worker_loop(self, worker: ScraperWorker) -> None:
        """Main loop for a single worker."""
        cycle_count = 0
        while self._is_running and worker._is_running:
            try:
                cycle_count += 1
                worker_id = worker.worker_id
                
                # Log cycle start
                worker.set_activity(f"🔁 Cycle #{cycle_count} starting...")
                logger.info(f"Worker {worker_id}: Starting cycle #{cycle_count}")
                add_log("info", f"🔁 Worker #{worker_id}: Cycle #{cycle_count} starting...")
                
                # Run the scrape cycle
                result = await worker.run_cycle()
                raw_nums = result.get("raw_numbers", [])
                saved_nums = result.get("saved_numbers", [])
                raw_count = result.get("raw_count", 0)
                saved_count = result.get("saved_count", 0)
                
                # Record the full search cycle — all numbers found + which were saved
                if raw_nums:
                    from app.dashboard import record_scrape_cycle
                    record_scrape_cycle(raw_nums, saved_nums, worker_id)
                
                if saved_count > 0:
                    worker.set_activity(f"🎯 Found {saved_count} numerology-valid numbers")
                    logger.info(f"Worker {worker_id}: Cycle #{cycle_count} — {raw_count} raw, {saved_count} saved")
                    # Show up to 5 saved numbers in the log line
                    saved_preview = ", ".join(n["number"] for n in saved_nums[:5])
                    preview = f" (e.g., {saved_preview})" if saved_count <= 5 and saved_preview else f" ({saved_count} numbers)"
                    add_log("success", 
                        f"🎯 Worker #{worker_id}: Found {saved_count} valid! {raw_count} total on page{preview}"
                    )
                else:
                    if raw_count > 0:
                        worker.set_activity(f"👀 Scanned {raw_count} numbers — none numerology-valid")
                        # Show raw numbers on page even if none saved
                        if cycle_count % 3 == 1:
                            preview = ", ".join(n["number"] for n in raw_nums[:5])
                            add_log("info", 
                                f"👀 Worker #{worker_id}: {raw_count} numbers on page — "
                                f"none numerology-valid (e.g., {preview})"
                            )
                    else:
                        worker.set_activity(f"👀 Scanned page — no numbers found")
                        if cycle_count % 5 == 1:
                            add_log("info", 
                                f"👀 Worker #{worker_id}: Cycle #{cycle_count} — no numbers on page"
                            )

                # Random cooldown between cycles (30-90 seconds)
                cooldown = random.randint(30, 90)
                worker.set_activity(f"⏳ Cooldown {cooldown}s (found {worker._stats['numbers_found']} total)")
                logger.debug(f"Worker {worker_id}: Cooldown {cooldown}s")
                
                # Log cooldown every 3rd cycle to show heartbeat
                if cycle_count % 3 == 0:
                    add_log("info", 
                        f"⏳ Worker #{worker_id}: Waiting {cooldown}s before next cycle "
                        f"(cycle #{cycle_count}, found: {worker._stats['numbers_found']} total)"
                    )
                
                await asyncio.sleep(cooldown)

            except asyncio.CancelledError:
                worker.set_activity(f"⏹️ Stopped after {cycle_count} cycles")
                add_log("info", f"⏹️ Worker #{worker.worker_id}: Stopped after {cycle_count} cycles")
                break
            except Exception as e:
                worker.set_activity(f"❌ Error: {str(e)[:60]}")
                logger.error(f"Worker {worker.worker_id} loop error: {e}")
                add_log("error", f"❌ Worker #{worker.worker_id}: Error — {str(e)[:80]}")
                await asyncio.sleep(60)

    async def stop(self) -> None:
        """Stop all workers."""
        self._is_running = False
        add_log("info", "⏹️ Shutting down all workers...")

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

        # Stop all workers
        for worker in self._workers:
            await worker.stop()

        # Close playwright
        if self._playwright:
            await self._playwright.stop()

        logger.info("All workers stopped")
        add_log("info", "✅ All workers shut down")

    def get_stats(self) -> dict:
        """Get all worker statistics."""
        return {
            "total_workers": self.num_workers,
            "active_workers": sum(1 for w in self._workers if w._is_running),
            "total_numbers_found": sum(w._stats["numbers_found"] for w in self._workers),
            "total_cycles": sum(w._stats["cycles_completed"] for w in self._workers),
            "total_errors": sum(w._stats["errors"] for w in self._workers),
            "workers": [w.get_stats() for w in self._workers],
        }
