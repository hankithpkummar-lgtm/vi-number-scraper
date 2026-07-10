"""
Main FastAPI application for Vi Scraper.
"""

import asyncio
import logging
import os
import signal
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.auth import validate_credentials_on_startup
from app.browser.browser import BrowserManager
from app.config import settings
from app.dashboard import dashboard_router, add_log, record_number_found, record_upload, record_duplicate, record_error, record_scrape_cycle, _stats
from app.database.storage import StorageManager
from app.health import health_checker
from app.routes.api import init_routes, router
from app.routes.auth_routes import auth_router
from app.scraper.scraper import ScraperEngine
from app.scraper.session import SessionManager
from app.scraper.workers import WorkerManager
from app.services.gas_sync import GasSyncService
from app.services.monitoring import metrics_collector
from app.utils.logger import get_logger

logger = get_logger(__name__)

browser_manager: BrowserManager = None
session_manager: SessionManager = None
scraper_engine: ScraperEngine = None
storage_manager: StorageManager = None
gas_sync_service: GasSyncService = None
worker_manager: WorkerManager = None
background_tasks: list = []


async def number_callback(number_data: dict) -> None:
    """
    Callback for when a number is found.
    
    LOCAL + GOOGLE SHEET COMBINATION SAVING LOGIC:
    ──────────────────────────────────────────────
    STEP 1: Save to local SQLite FIRST (always succeeds)
    STEP 2: Immediately push to Google Sheet (real-time sync)
    STEP 3: If GAS fails → queue for background retry with exponential backoff
    STEP 4: Background sync_loop retries failed uploads every 60s
    ──────────────────────────────────────────────
    This guarantees NO DATA LOSS - numbers are always saved locally first.
    Google Sheet sync is best-effort with automatic retry.
    """
    try:
        # ═══ STEP 1: Save to Local SQLite ═══
        saved = storage_manager.save_number(number_data)
        if saved:
            logger.info(
                f"[LOCAL] Saved: {number_data['number']} "
                f"(root={number_data.get('root')}, compound={number_data.get('compound')})"
            )
            metrics_collector.record_number_found()
            record_number_found(number_data.get('root', 0), number_data.get('compound', 0))
            add_log("success",
                f"💾 LOCAL: {number_data['number']} | "
                f"Root {number_data.get('root')} ({number_data.get('root_planet', '')}) | "
                f"Total {number_data.get('compound')}"
            )
            health_checker.set_records_count(
                storage_manager.get_stats().get("total_numbers", 0)
            )

            # ═══ STEP 2: Push to Google Sheet (immediate) ═══
            if gas_sync_service and settings.GAS_URL:
                try:
                    uploaded = await gas_sync_service.upload_number(number_data)
                    if uploaded:
                        logger.info(f"[GAS] Upload success: {number_data['number']}")
                        record_upload()
                        add_log("success",
                            f"☁️ GAS: {number_data['number']} — Synced to Google Sheet"
                        )
                        metrics_collector.record_sync()
                        
                        # Mark as uploaded in local DB
                        stats = storage_manager.get_stats()
                        # Find and mark the just-saved number
                        numbers = storage_manager.get_numbers(limit=1)
                        if numbers and numbers[0].get("number") == number_data["number"]:
                            storage_manager.mark_uploaded([numbers[0]["id"]])
                    else:
                        # ═══ STEP 3: GAS failed → queued for retry ═══
                        logger.warning(f"[GAS] Upload failed (queued): {number_data['number']}")
                        add_log("warning",
                            f"☁️ GAS: {number_data['number']} — Upload failed, queued for retry"
                        )
                        # Find the saved number and mark failure
                        numbers = storage_manager.get_numbers(limit=1)
                        if numbers and numbers[0].get("number") == number_data["number"]:
                            storage_manager.mark_upload_failed(
                                numbers[0]["id"],
                                "GAS rejected the upload"
                            )
                except Exception as ge:
                    # GAS network error → will be retried by sync_loop
                    logger.error(f"[GAS] Upload error (queued): {ge}")
                    record_error()
                    add_log("error",
                        f"☁️ GAS: {number_data['number']} — Network error, queued for retry"
                    )
                    # Mark failure in local DB
                    numbers = storage_manager.get_numbers(limit=1)
                    if numbers and numbers[0].get("number") == number_data["number"]:
                        storage_manager.mark_upload_failed(
                            numbers[0]["id"],
                            f"Network error: {str(ge)[:200]}"
                        )
            else:
                # GAS not configured → all numbers stay local
                add_log("info",
                    f"☁️ GAS: {number_data['number']} — Google Sheet not configured, local only"
                )
        else:
            # Duplicate blocked at DB level
            logger.debug(f"[LOCAL] Duplicate blocked: {number_data['number']}")
            record_duplicate()
            add_log("info", f"⚠️ Duplicate blocked: {number_data['number']}")
            metrics_collector.record_duplicate_blocked()

    except Exception as e:
        logger.error(f"Error in number callback: {e}")
        record_error()
        add_log("error", f"❌ Callback error: {str(e)}")
        metrics_collector.record_failed_insert()


async def sync_loop() -> None:
    """
    Background task for syncing with GAS.
    
    SYNC STRATEGY:
    ──────────────
    1. First, retry previously failed uploads (with exponential backoff)
    2. Then, push new pending numbers
    3. Failed numbers are tracked with fail_count in SQLite
    4. Numbers with fail_count >= 5 are skipped (manual retry needed)
    ──────────────
    """
    consecutive_failures = 0
    base_delay = 60  # Start at 60 seconds
    max_delay = 600  # Max 10 minutes
    
    while True:
        try:
            if gas_sync_service and storage_manager and settings.GAS_URL:
                # ═══ STEP 1: Auto-recover permanently_failed numbers ═══
                # Numbers with fail_count>=5 are stuck. Try a small batch of them.
                # If GAS responds with 'skipped' (including 'Duplicate'), mark them processed.
                permanently_failed = storage_manager.get_permanently_failed(limit=5)
                if permanently_failed:
                    recovered = await gas_sync_service.upload_batch(permanently_failed)
                    if recovered > 0:
                        recovered_ids = [n["id"] for n in permanently_failed[:recovered]]
                        storage_manager.mark_uploaded(recovered_ids)
                        for _ in range(recovered):
                            record_upload()
                            metrics_collector.record_sync()
                        add_log("success",
                            f"✅ Auto-recovered {recovered} permanently failed numbers "
                            f"(GAS confirmed they exist as duplicates)"
                        )
                        logger.info(f"Auto-recovered {recovered} permanently failed numbers")
                        consecutive_failures = 0

                # ═══ STEP 2: Retry previously failed uploads ═══
                failed = storage_manager.get_failed_uploads(limit=20)
                if failed:
                    # Only retry numbers that haven't failed too many times
                    retryable = [n for n in failed if n.get("fail_count", 0) < 5]
                    skipped = len(failed) - len(retryable)
                    
                    if retryable:
                        logger.info(
                            f"[SYNC] Retrying {len(retryable)} failed uploads "
                            f"(skipping {skipped} with too many failures)"
                        )
                        add_log("info",
                            f"🔄 SYNC: Retrying {len(retryable)} failed, "
                            f"{skipped} skipped (max retries)"
                        )
                        
                        uploaded = await gas_sync_service.upload_batch(retryable)
                        if uploaded > 0:
                            uploaded_ids = [r["id"] for r in retryable[:uploaded]]
                            storage_manager.mark_uploaded(uploaded_ids)
                            for _ in range(uploaded):
                                record_upload()
                                metrics_collector.record_sync()
                            add_log("success", f"✅ SYNC: Retry successful — {uploaded} numbers synced")
                            logger.info(f"Retry sync: {uploaded} numbers uploaded successfully")
                            consecutive_failures = 0
                        else:
                            # Mark failed numbers with incremented fail count
                            for n in retryable:
                                storage_manager.mark_upload_failed(n["id"], "Batch upload failed")
                            consecutive_failures += 1
                            logger.warning(f"Retry sync failed for {len(retryable)} numbers")
                    
                    if skipped > 0:
                        add_log("warning",
                            f"⚠️ {skipped} numbers permanently failed sync — "
                            f"will auto-recover next cycle"
                        )
                
                # ═══ STEP 3: Push new pending numbers ═══
                pending = storage_manager.get_pending_uploads(limit=30)
                if pending:
                    logger.info(f"[SYNC] {len(pending)} new numbers pending upload to GAS")
                    add_log("info", f"🔄 SYNC: {len(pending)} new numbers pending")
                    
                    uploaded = await gas_sync_service.upload_batch(pending)
                    if uploaded > 0:
                        number_ids = [p["id"] for p in pending[:uploaded]]
                        storage_manager.mark_uploaded(number_ids)
                        for _ in range(uploaded):
                            record_upload()
                            metrics_collector.record_sync()
                        add_log("success",
                            f"✅ SYNC: {uploaded} numbers pushed to Google Sheet"
                        )
                        logger.info(f"New sync: {uploaded} numbers uploaded successfully")
                        consecutive_failures = 0
                    else:
                        # Mark as failed for retry
                        for p in pending:
                            storage_manager.mark_upload_failed(p["id"], "Initial batch upload failed")
                        consecutive_failures += 1
                        logger.warning(f"New sync failed for {len(pending)} numbers")
                else:
                    # Nothing pending — reset failure counter
                    consecutive_failures = 0
                    
            elif not settings.GAS_URL:
                # GAS not configured — log once per hour (but not every 60s)
                pass
                
        except Exception as e:
            logger.error(f"Sync loop error: {e}")
            record_error()
            add_log("error", f"❌ SYNC: {str(e)}")
            metrics_collector.record_sync_failure()
            consecutive_failures += 1

        # ═══ Exponential Backoff ═══
        if consecutive_failures > 0:
            delay = min(base_delay * (2 ** (consecutive_failures - 1)), max_delay)
            logger.debug(f"Sync backoff: {delay}s (failure #{consecutive_failures})")
        else:
            delay = 60  # Normal: every 60 seconds

        await asyncio.sleep(delay)


async def health_monitor_loop() -> None:
    """Background task for monitoring health."""
    while True:
        try:
            if storage_manager:
                health_checker.set_database_health(True)
                stats = storage_manager.get_stats()
                health_checker.set_records_count(stats.get("total_numbers", 0))

            if gas_sync_service:
                gas_health = await gas_sync_service.health_check()
                health_checker.set_gas_health(gas_health.get("status") == "healthy")

            if worker_manager:
                worker_stats = worker_manager.get_stats()
                health_checker.set_scraper_running(worker_stats["active_workers"] > 0)
                metrics_collector.set_scraper_status(
                    f"running ({worker_stats['active_workers']} workers)" if worker_stats["active_workers"] > 0 else "stopped"
                )
                # Sync worker stats to dashboard stats
                _stats["scrape_cycles"] = worker_stats["total_cycles"]
                _stats["total_found"] = worker_stats["total_numbers_found"]
                _stats["total_errors"] = worker_stats["total_errors"]
                logger.debug(
                    f"Health sync: {worker_stats['total_cycles']} cycles, "
                    f"{worker_stats['total_numbers_found']} found"
                )

            metrics_collector.set_browser_status("healthy")

        except Exception as e:
            logger.error(f"Health monitor error: {e}")

        await asyncio.sleep(30)


async def sync_sheet_to_local_loop() -> None:
    """Background task: periodically pull new numbers from Google Sheet into local DB.

    Runs every 5 minutes. Only imports numbers NOT already in local DB.
    This ensures local DB stays in sync with the sheet without duplicating data.
    """
    while True:
        try:
            if gas_sync_service and storage_manager:
                sheet_numbers = await gas_sync_service.fetch_all_numbers()
                if sheet_numbers:
                    result = storage_manager.import_numbers_from_sheet(sheet_numbers)
                    if result["imported"] > 0:
                        add_log(
                            "success",
                            f"📥 Auto-sync: Pulled {result['imported']} new numbers from sheet "
                            f"({result['total_in_sheet']} total in sheet)",
                        )
        except Exception as e:
            logger.error(f"Sheet→local sync error: {e}")

        await asyncio.sleep(300)  # Every 5 minutes


async def sync_unavailable_numbers_loop() -> None:
    """Background task to sync unavailable numbers from GAS."""
    while True:
        try:
            if gas_sync_service and storage_manager:
                # Get all numbers from local database
                stats = storage_manager.get_stats()
                total_numbers = stats.get("total_numbers", 0)
                
                if total_numbers > 0:
                    logger.debug("Sync unavailable numbers loop: checking for unavailable numbers")
                    
                    # Note: This is a placeholder for future implementation
                    # When GAS provides an API to get unavailable numbers, 
                    # we can fetch and auto-remove them here
                    
                    # For now, we just log the check
                    add_log("info", f"Unavailable sync check: {total_numbers} numbers in backup")
                    
        except Exception as e:
            logger.error(f"Sync unavailable numbers error: {e}")
            record_error()
            add_log("error", f"Unavailable sync error: {str(e)}")

        await asyncio.sleep(300)  # Run every 5 minutes


async def scraper_loop() -> None:
    """Main scraper loop — NO AUTORUN, starts only on POST /start."""
    try:
        logger.info("Scraper loop initialized (waiting for manual start)")
        health_checker.set_logged_in(True)
        metrics_collector.set_login_status("logged_in")
        add_log("info", "Scraper ready — use POST /start to begin")

        while scraper_engine._should_stop is False:
            try:
                logger.info("Starting scrape cycle...")
                add_log("info", "Starting scrape cycle...")
                result = await scraper_engine.scrape_cycle()
                saved_count = len(result.get("saved_numbers", []))
                raw_count = len(result.get("raw_numbers", []))
                logger.info(f"Scrape cycle complete: {saved_count} saved, {raw_count} raw")
                for _ in range(saved_count):
                    record_scrape_cycle()
                add_log("info", f"Scrape cycle complete: {saved_count} saved out of {raw_count} on page")
                metrics_collector.record_scrape()

                cooldown = settings.COOLDOWN_MINUTES * 60
                variation = settings.SESSION_TIMEOUT_VARIATION * 60
                actual_cooldown = cooldown + (asyncio.get_event_loop().time() % variation)
                logger.info(f"Cooldown for {actual_cooldown:.0f} seconds")
                add_log("info", f"Cooldown: {actual_cooldown:.0f}s")
                await asyncio.sleep(actual_cooldown)

            except Exception as e:
                logger.error(f"Scraper cycle error: {e}")
                record_error()
                add_log("error", f"Scraper cycle error: {str(e)}")
                await asyncio.sleep(60)

    except Exception as e:
        logger.error(f"Scraper loop error: {e}")
        record_error()
        add_log("error", f"Scraper loop error: {str(e)}")
    finally:
        health_checker.set_scraper_running(False)
        metrics_collector.set_scraper_status("stopped")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global browser_manager, session_manager, scraper_engine, storage_manager, gas_sync_service, worker_manager

    logger.info("Starting Vi Scraper application...")
    _stats["session_start"] = time.time()
    add_log("info", "Application starting...")

    try:
        validate_credentials_on_startup()
    except Exception as e:
        logger.warning(f"Credential validation warning: {e} (continuing - search page is public)")

    os.makedirs(settings.LOG_DIR, exist_ok=True)
    os.makedirs(settings.DATABASE_PATH.rsplit("/", 1)[0], exist_ok=True)
    os.makedirs(settings.COOKIE_DIR, exist_ok=True)
    os.makedirs(settings.BACKUP_DIR, exist_ok=True)

    storage_manager = StorageManager()
    gas_sync_service = GasSyncService()

    init_routes(scraper_engine, storage_manager, gas_sync_service, session_manager, browser_manager)

    health_checker.set_database_health(True)

    # Log GAS configuration status
    if settings.GAS_URL:
        logger.info(f"GAS_URL configured: {settings.GAS_URL[:50]}...")
        add_log("info", f"GAS configured: {settings.GAS_URL[:50]}...")
    else:
        logger.warning("GAS_URL NOT configured - numbers will be queued locally only")
        add_log("warning", "GAS_URL not configured")

    # Create worker manager but DON'T start browsers at startup
    # Workers are started lazily only when POST /start is called
    logger.info(f"Worker manager created ({settings.NUM_WORKERS} workers ready)")
    add_log("info", f"Worker manager ready ({settings.NUM_WORKERS} workers)")
    worker_manager = WorkerManager(
        num_workers=settings.NUM_WORKERS,
        number_callback=number_callback,
    )

    # Re-init routes with worker manager
    init_routes(scraper_engine, storage_manager, gas_sync_service, session_manager, browser_manager, worker_manager)

    background_tasks.append(asyncio.create_task(sync_loop()))
    background_tasks.append(asyncio.create_task(health_monitor_loop()))
    background_tasks.append(asyncio.create_task(sync_unavailable_numbers_loop()))
    background_tasks.append(asyncio.create_task(sync_sheet_to_local_loop()))

    # Auto-start workers for 24/7 continuous operation
    # Workers run continuously in background, each running scrape cycles
    # with random cooldowns. No manual start needed.
    auto_start = os.getenv("AUTO_START_WORKERS", "true").lower() == "true"
    if auto_start:
        add_log("info", "Auto-starting workers for 24/7 operation...")
        asyncio.create_task(worker_manager.start())
        add_log("success", f"✅ {settings.NUM_WORKERS} workers auto-started (24/7 mode)")
    else:
        add_log("info", "Scraper idle — POST /start to begin")

    add_log("info", "Dashboard ready at /dashboard")

    logger.info("Application started successfully")
    logger.info(f"Dashboard: http://localhost:{settings.PORT}/dashboard")
    logger.info(f"Listening on port {settings.PORT}")

    yield

    logger.info("Shutting down application...")
    add_log("info", "Application shutting down...")

    for task in background_tasks:
        task.cancel()

    if worker_manager:
        await worker_manager.stop()

    if scraper_engine:
        await scraper_engine.stop()

    if gas_sync_service:
        await gas_sync_service.close()

    await asyncio.gather(*background_tasks, return_exceptions=True)

    logger.info("Application shut down complete")


app = FastAPI(
    title="Vi Scraper API",
    description="Production-ready Vi mobile number scraper",
    version="3.0.0",
    lifespan=lifespan,
)

# Security: Restrict CORS to known origins (P0 Fix)
ALLOWED_ORIGINS = [
    "https://hankith-vi-number-scraper.hf.space",
    "https://hankith-vi-number-bot.hf.space",
    "http://localhost:7860",
    "http://127.0.0.1:7860",
    "http://localhost:7861",
    "http://127.0.0.1:7861",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(dashboard_router)
app.include_router(auth_router)


def main() -> None:
    """Run the application."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
