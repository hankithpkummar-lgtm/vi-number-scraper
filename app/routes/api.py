"""
FastAPI routes for Vi Scraper API.
"""

import asyncio
import csv
import io
import logging
import time
from typing import AsyncGenerator, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Header, Request
from fastapi.responses import PlainTextResponse, StreamingResponse

from app.config import settings
from app.health import health_checker
from app.auth.dashboard_auth import require_auth, optional_auth

logger = logging.getLogger(__name__)

router = APIRouter()

_scraper_engine = None
_storage_manager = None
_gas_sync_service = None
_session_manager = None
_browser_manager = None
_worker_manager = None


def init_routes(
    scraper_engine,
    storage_manager,
    gas_sync_service,
    session_manager,
    browser_manager,
    worker_manager=None,
) -> None:
    """Initialize routes with service dependencies."""
    global _scraper_engine, _storage_manager, _gas_sync_service, _session_manager, _browser_manager, _worker_manager
    _scraper_engine = scraper_engine
    _storage_manager = storage_manager
    _gas_sync_service = gas_sync_service
    _session_manager = session_manager
    _browser_manager = browser_manager
    _worker_manager = worker_manager


def verify_api_key(x_api_key: Optional[str] = Header(None)) -> bool:
    """Verify API key for protected endpoints."""
    # If no API key is configured, allow all (backward compatibility)
    if not settings.SCRAPER_API_KEY:
        return True
    # If API key is configured, require it
    return x_api_key == settings.SCRAPER_API_KEY


@router.get("/health")
async def health_endpoint() -> dict:
    """Health check endpoint."""
    return health_checker.get_health()


@router.get("/status")
async def status_endpoint() -> dict:
    """Detailed status endpoint."""
    return health_checker.get_detailed_status()


@router.get("/metrics")
async def metrics_endpoint() -> PlainTextResponse:
    """Prometheus-compatible metrics endpoint."""
    return PlainTextResponse(
        content=health_checker.get_prometheus_metrics(),
        media_type="text/plain",
    )


@router.post("/start")
async def start_scraper(
    auth_payload: dict = Depends(require_auth),
) -> dict:
    """Start the scraper — launches browsers and begins scraping. (Protected)"""
    if _worker_manager is None:
        raise HTTPException(status_code=503, detail="Worker manager not initialized")

    if _worker_manager._is_running:
        return {"message": "Scraper is already running", "status": "running"}

    asyncio.create_task(_worker_manager.start())
    logger.info(f"Scraper started by user: {auth_payload.get('sub')}")
    return {"message": "Scraper started", "status": "starting"}


@router.post("/stop")
async def stop_scraper(
    auth_payload: dict = Depends(require_auth),
) -> dict:
    """Stop the scraper and all workers. (Protected)"""
    if _worker_manager and _worker_manager._is_running:
        await _worker_manager.stop()
        logger.info(f"Scraper stopped by user: {auth_payload.get('sub')}")
        return {"message": "Scraper stopped", "status": "stopped"}
    return {"message": "Scraper is not running", "status": "stopped"}


@router.get("/numbers")
async def list_numbers(
    auth_payload: dict = Depends(require_auth),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """List found numbers. (Protected)"""
    if _storage_manager is None:
        raise HTTPException(status_code=503, detail="Storage not initialized")

    numbers = _storage_manager.get_numbers(limit=limit, offset=offset)
    stats = _storage_manager.get_stats()
    return {"numbers": numbers, "total": stats.get("total_numbers", 0)}


@router.get("/numbers.csv")
async def export_csv(
    auth_payload: dict = Depends(require_auth),
) -> StreamingResponse:
    """Export numbers as CSV. (Protected)"""
    if _storage_manager is None:
        raise HTTPException(status_code=503, detail="Storage not initialized")

    numbers = _storage_manager.get_numbers(limit=10000)

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["number", "root", "compound", "type", "priority", "found_at"],
    )
    writer.writeheader()
    for num in numbers:
        writer.writerow({
            "number": num.get("number"),
            "root": num.get("root"),
            "compound": num.get("compound"),
            "type": num.get("type"),
            "priority": num.get("priority"),
            "found_at": num.get("found_at"),
        })

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=numbers.csv"},
    )


@router.post("/config")
async def update_config(
    config: dict,
    auth_payload: dict = Depends(require_auth),
) -> dict:
    """Update configuration. (Protected)"""
    
    # Security: Only allow modifying safe settings (P0 Fix)
    SAFE_SETTINGS = {
        "COOLDOWN_MINUTES", "NUM_WORKERS", "SEARCH_COOLDOWN_SECONDS",
        "MAX_SEARCH_CYCLES", "PAGE_REFRESH_EVERY", "HEADLESS",
        "SCRAPER_FULLNAME", "SCRAPER_MOBILE", "SCRAPER_PINCODE",
    }
    
    updated_fields = []
    rejected_fields = []
    
    for key, value in config.items():
        key_upper = key.upper()
        if key_upper in SAFE_SETTINGS and hasattr(settings, key_upper):
            # Enforce minimum 12 workers
            if key_upper == "NUM_WORKERS":
                value = max(12, int(value))
            setattr(settings, key_upper, value)
            updated_fields.append(key)
        else:
            rejected_fields.append(key)
    
    result = {"message": "Configuration updated", "updated_fields": updated_fields}
    if "NUM_WORKERS" in [k.upper() for k in config.keys()]:
        result["note"] = "NUM_WORKERS minimum is 12 (auto-enforced)"
    if rejected_fields:
        result["rejected_fields"] = rejected_fields
        result["note"] = "Sensitive settings cannot be modified via API"
    
    return result


@router.post("/backup")
async def trigger_backup(
    auth_payload: dict = Depends(require_auth),
) -> dict:
    """Trigger a database backup. (Protected)"""
    
    if _storage_manager is None:
        raise HTTPException(status_code=503, detail="Storage not initialized")

    backup_path = _storage_manager.backup()
    if backup_path:
        # Security: Don't expose full filesystem path (P0 Fix)
        import os
        backup_filename = os.path.basename(backup_path)
        return {"message": "Backup created", "filename": backup_filename}
    else:
        raise HTTPException(status_code=500, detail="Backup failed")


@router.get("/events")
async def sse_events() -> StreamingResponse:
    """Server-Sent Events endpoint for real-time updates."""
    async def event_generator() -> AsyncGenerator[str, None]:
        while True:
            data = health_checker.get_health()
            yield f"data: {data}\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/")
async def root(auth_payload: Optional[dict] = Depends(optional_auth)) -> dict:
    """Root endpoint — shows API info."""
    return {
        "name": "Vi Scraper API",
        "version": "3.0.0",
        "authenticated": auth_payload is not None,
        "dashboard": "/dashboard",
        "login": "/login",
        "endpoints": {
            "dashboard": "/dashboard",
            "login": "/login",
            "health": "/health",
            "status": "/status",
            "metrics": "/metrics",
            "gas_status": "/gas-status",
            "workers": "/workers",
            "start": "POST /start",
            "stop": "POST /stop",
            "numbers": "/numbers (auth)",
            "export": "/numbers.csv (auth)",
            "config": "POST /config (auth)",
            "backup": "POST /backup (auth)",
            "events": "/events",
            "check_availability": "/check-availability/{number} (auth)",
            "batch_check": "POST /check-availability-batch (auth)",
            "sync_status": "/sync/status (auth)",
            "root_breakdown": "/api/dashboard/root-breakdown (auth)",
            "reset_failed_sync": "POST /sync/reset-failed (auth)",
            "pull_from_sheet": "POST /sync/pull-from-sheet (auth)",
        },
    }


@router.get("/gas-status")
async def gas_status_endpoint() -> dict:
    """Check GAS sync configuration and connectivity."""
    from app.config import settings

    gas_url = settings.GAS_URL
    if not gas_url:
        return {
            "configured": False,
            "status": "not_configured",
            "message": "GAS_URL environment variable not set",
        }

    # Try a health check
    if _gas_sync_service:
        health = await _gas_sync_service.health_check()
        stats = _gas_sync_service.get_stats()
        return {
            "configured": True,
            "url": gas_url[:50] + "..." if len(gas_url) > 50 else gas_url,
            "health": health,
            "stats": stats,
        }

    return {
        "configured": True,
        "url": gas_url[:50] + "..." if len(gas_url) > 50 else gas_url,
        "status": "service_not_initialized",
    }


@router.get("/workers")
async def workers_endpoint() -> dict:
    """Get worker manager statistics."""
    if _worker_manager is None:
        return {"status": "not_initialized", "message": "Worker manager not running"}

    return _worker_manager.get_stats()


@router.get("/check-availability/{number}")
async def check_availability(
    number: str,
    auth_payload: dict = Depends(require_auth),
) -> dict:
    """
    Check if a specific number is available on VI website.
    
    Args:
        number: 10-digit phone number to check
        
    Returns:
        {available: bool, number: str, status: str, found_at: float}
    """
    # Validate input
    if len(number) != 10 or not number.isdigit():
        raise HTTPException(
            status_code=400, 
            detail="Number must be exactly 10 digits"
        )
    
    # Check if worker manager is available
    if _worker_manager is None or not _worker_manager._is_running:
        raise HTTPException(
            status_code=503, 
            detail="Scraper workers not available"
        )
    
    # Get an available page from workers
    page = None
    for worker in _worker_manager._workers:
        if worker._is_running and worker._page and not worker._page.is_closed():
            page = worker._page
            break
    
    if not page:
        raise HTTPException(
            status_code=503, 
            detail="No available browser pages"
        )
    
    # Check availability using the scraper engine
    try:
        from app.scraper.scraper import ScraperEngine
        
        # Create a temporary scraper engine for availability check
        async def page_getter():
            return page
        
        session_manager = _session_manager or type('SessionManager', (), {'refresh_session': lambda self: asyncio.sleep(0)})()
        temp_scraper = ScraperEngine(
            browser_page_getter=page_getter,
            session_manager=session_manager,
        )
        
        result = await temp_scraper.check_number_availability(page, number)
        return result
        
    except Exception as e:
        logger.error(f"Availability check failed for {number}: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Availability check failed: {str(e)}"
        )


@router.post("/check-availability-batch")
async def check_availability_batch(
    numbers: List[str],
    auth_payload: dict = Depends(require_auth),
) -> dict:
    """
    Batch check availability for multiple numbers.
    Automatically removes unavailable numbers from backup.
    
    Args:
        numbers: List of 10-digit phone numbers to check
        
    Returns:
        {results: List[dict], removed: int}
    """
    
    if _worker_manager is None or not _worker_manager._is_running:
        raise HTTPException(
            status_code=503, 
            detail="Scraper workers not available"
        )
    
    if _storage_manager is None:
        raise HTTPException(
            status_code=503, 
            detail="Storage not initialized"
        )
    
    results = []
    removed = 0
    
    for number in numbers:
        if len(number) != 10 or not number.isdigit():
            results.append({
                "number": number,
                "available": False,
                "status": "Invalid format",
                "found_at": time.time()
            })
            continue
        
        # Get an available page
        page = None
        for worker in _worker_manager._workers:
            if worker._is_running and worker._page and not worker._page.is_closed():
                page = worker._page
                break
        
        if not page:
            results.append({
                "number": number,
                "available": False,
                "status": "No browser available",
                "found_at": time.time()
            })
            continue
        
        try:
            from app.scraper.scraper import ScraperEngine
            
            async def page_getter():
                return page
            
            session_manager = _session_manager or type('SessionManager', (), {'refresh_session': lambda self: asyncio.sleep(0)})()
            temp_scraper = ScraperEngine(
                browser_page_getter=page_getter,
                session_manager=session_manager,
            )
            
            result = await temp_scraper.check_number_availability(page, number)
            results.append(result)
            
            # Auto-remove unavailable numbers from backup
            if not result["available"]:
                _storage_manager.delete_number(number)
                removed += 1
                logger.info(f"Auto-removed unavailable number: {number}")
            
            # Rate limit between checks
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Batch check failed for {number}: {e}")
            results.append({
                "number": number,
                "available": False,
                "status": f"Error: {str(e)}",
                "found_at": time.time()
            })
    
    return {
        "results": results,
        "total_checked": len(numbers),
        "available": sum(1 for r in results if r.get("available")),
        "removed": removed,
    }


@router.post("/sync/reset-failed")
async def reset_failed_sync(
    auth_payload: dict = Depends(require_auth),
    number: Optional[str] = None,
) -> dict:
    """
    Reset failed sync status for numbers.
    If number is provided, resets just that number.
    Otherwise resets ALL failed numbers.
    
    Args:
        number: Optional specific number to reset
        
    Returns:
        {reset: int, message: str}
    """
    if _storage_manager is None:
        raise HTTPException(status_code=503, detail="Storage not initialized")
    
    try:
        import sqlite3
        
        if number:
            # Reset specific number
            with sqlite3.connect(_storage_manager._db_path) as conn:
                cursor = conn.execute(
                    """
                    UPDATE numbers 
                    SET fail_count = 0, last_error = '', uploaded = 0
                    WHERE number = ?
                    """,
                    (number,),
                )
                conn.commit()
                reset_count = cursor.rowcount
        else:
            # Reset ALL failed numbers
            with sqlite3.connect(_storage_manager._db_path) as conn:
                cursor = conn.execute(
                    """
                    UPDATE numbers 
                    SET fail_count = 0, last_error = '', uploaded = 0
                    WHERE uploaded = 0 AND fail_count > 0
                    """
                )
                conn.commit()
                reset_count = cursor.rowcount
        
        logger.info(f"Reset {reset_count} failed sync records (user: {auth_payload.get('sub')})")
        return {
            "reset": reset_count,
            "message": f"Reset {reset_count} failed sync records",
        }
        
    except Exception as e:
        logger.error(f"Error resetting failed sync: {e}")
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")


@router.post("/sync/pull-from-sheet")
async def pull_from_sheet(
    auth_payload: dict = Depends(require_auth),
) -> dict:
    """
    Pull all numbers from Google Sheet into local database.
    
    Fetches ALL numbers from the sheet, inserts any that don't exist locally,
    and marks them as uploaded=1 (since they're already in the sheet).
    
    This is a one-way import: Sheet → Local DB (never the reverse).
    
    Returns:
        {imported: int, skipped_existing: int, total_in_sheet: int, message: str}
    """
    if _storage_manager is None:
        raise HTTPException(status_code=503, detail="Storage not initialized")
    if _gas_sync_service is None:
        raise HTTPException(status_code=503, detail="GAS sync not initialized")

    logger.info(f"Pull-from-sheet triggered by user: {auth_payload.get('sub')}")

    try:
        # 1. Fetch all numbers from the sheet
        sheet_numbers = await _gas_sync_service.fetch_all_numbers()
        if not sheet_numbers:
            return {
                "imported": 0,
                "skipped_existing": 0,
                "total_in_sheet": 0,
                "message": "No numbers found in sheet or GAS URL not configured",
            }

        # 2. Import them into local DB (only new ones)
        result = _storage_manager.import_numbers_from_sheet(sheet_numbers)

        msg = (
            f"Sheet → Local: {result['imported']} new numbers imported, "
            f"{result['skipped_existing']} already existed "
            f"(out of {result['total_in_sheet']} total in sheet)"
        )
        logger.info(msg)

        return {
            **result,
            "message": msg,
        }

    except Exception as e:
        logger.error(f"Pull-from-sheet error: {e}")
        raise HTTPException(status_code=500, detail=f"Pull from sheet failed: {str(e)}")


@router.get("/sync/status")
async def sync_status(
    auth_payload: dict = Depends(require_auth),
) -> dict:
    """
    Get detailed sync status including pending, failed, and uploaded counts.
    
    Returns:
        {total, uploaded, pending, failed, permanently_failed}
    """
    if _storage_manager is None:
        raise HTTPException(status_code=503, detail="Storage not initialized")
    
    try:
        import sqlite3
        
        with sqlite3.connect(_storage_manager._db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM numbers").fetchone()[0]
            uploaded = conn.execute(
                "SELECT COUNT(*) FROM numbers WHERE uploaded = 1"
            ).fetchone()[0]
            pending = conn.execute(
                "SELECT COUNT(*) FROM numbers WHERE uploaded = 0 AND fail_count = 0"
            ).fetchone()[0]
            failed = conn.execute(
                "SELECT COUNT(*) FROM numbers WHERE uploaded = 0 AND fail_count > 0 AND fail_count < 5"
            ).fetchone()[0]
            permanently_failed = conn.execute(
                "SELECT COUNT(*) FROM numbers WHERE uploaded = 0 AND fail_count >= 5"
            ).fetchone()[0]
        
        return {
            "total": total,
            "uploaded": uploaded,
            "pending": pending,
            "failed": failed,
            "permanently_failed": permanently_failed,
            "gas_configured": bool(settings.GAS_URL),
        }
        
    except Exception as e:
        logger.error(f"Error getting sync status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/dashboard/numbers")
async def dashboard_numbers(
    auth_payload: dict = Depends(require_auth),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    search: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None),
) -> dict:
    """
    Enhanced numbers list for dashboard with search and filtering.
    
    Args:
        limit: Max results
        offset: Pagination offset
        search: Optional search term (searches number field)
        status_filter: Filter by 'pending', 'uploaded', 'failed', 'permanent'
        
    Returns:
        {numbers: List[dict], total: int, filtered_total: int}
    """
    if _storage_manager is None:
        raise HTTPException(status_code=503, detail="Storage not initialized")
    
    try:
        import sqlite3
        
        with sqlite3.connect(_storage_manager._db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Build query with filters
            where_clauses = []
            params = []
            
            if search:
                where_clauses.append("number LIKE ?")
                params.append(f"%{search}%")
            
            if status_filter == "pending":
                where_clauses.append("uploaded = 0 AND fail_count = 0")
            elif status_filter == "uploaded":
                where_clauses.append("uploaded = 1")
            elif status_filter == "failed":
                where_clauses.append("uploaded = 0 AND fail_count > 0 AND fail_count < 5")
            elif status_filter == "permanent":
                where_clauses.append("uploaded = 0 AND fail_count >= 5")
            
            where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
            
            # Get total count
            total = conn.execute("SELECT COUNT(*) FROM numbers").fetchone()[0]
            filtered_total = conn.execute(
                f"SELECT COUNT(*) FROM numbers {where_sql}", params
            ).fetchone()[0]
            
            # Get numbers
            query = f"""
                SELECT id, number, root, compound, type, priority, 
                       uploaded, fail_count, last_error, 
                       found_at, created_at
                FROM numbers 
                {where_sql}
                ORDER BY priority DESC, found_at DESC
                LIMIT ? OFFSET ?
            """
            cursor = conn.execute(query, params + [limit, offset])
            numbers = [dict(row) for row in cursor.fetchall()]
            
            # Format numbers for display
            for num in numbers:
                # Determine status
                if num["uploaded"] == 1:
                    num["sync_status"] = "synced"
                    num["sync_label"] = "✅ Synced"
                elif num["fail_count"] >= 5:
                    num["sync_status"] = "permanent"
                    num["sync_label"] = "❌ Failed (max)"
                elif num["fail_count"] > 0:
                    num["sync_status"] = "failed"
                    num["sync_label"] = f"⚠️ Failed ({num['fail_count']}/5)"
                else:
                    num["sync_status"] = "pending"
                    num["sync_label"] = "⏳ Pending"
                
                # Format found_at
                if num.get("found_at"):
                    from datetime import datetime
                    num["found_at_display"] = datetime.fromtimestamp(
                        num["found_at"]
                    ).strftime("%Y-%m-%d %H:%M:%S")
                else:
                    num["found_at_display"] = "-"
                
                # Root planet
                PLANET_MAP = {1: "Sun", 2: "Moon", 3: "Jupiter", 4: "Rahu", 
                             5: "Mercury", 6: "Venus", 7: "Ketu", 8: "Saturn", 9: "Mars"}
                root = num.get("root", 0)
                num["planet"] = PLANET_MAP.get(root, "?")
            
            return {
                "numbers": numbers,
                "total": total,
                "filtered_total": filtered_total,
                "limit": limit,
                "offset": offset,
            }
            
    except Exception as e:
        logger.error(f"Error fetching dashboard numbers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/dashboard/root-breakdown")
async def dashboard_root_breakdown(
    auth_payload: dict = Depends(require_auth),
) -> dict:
    """
    Get per-root breakdown: how many numbers found vs saved for each root digit.
    
    Returns:
        {breakdown: [{root, total, uploaded, pending}], total_all: int}
    """
    if _storage_manager is None:
        raise HTTPException(status_code=503, detail="Storage not initialized")

    try:
        rows = _storage_manager.get_root_breakdown()
        total_all = sum(r.get("total", 0) for r in rows)
        return {"breakdown": rows, "total_all": total_all}
    except Exception as e:
        logger.error(f"Root breakdown error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/dashboard/gas-data")
async def dashboard_gas_data(
    auth_payload: dict = Depends(require_auth),
) -> dict:
    """
    Fetch numbers directly from Google Sheet via GAS URL.
    Shows what's currently in the sheet vs what's in local DB.
    
    Returns:
        {gas_numbers: List[dict], gas_count: int, local_count: int, 
         synced: int, not_in_gas: int}
    """
    if not settings.GAS_URL:
        return {
            "configured": False,
            "message": "GAS_URL not configured",
            "gas_numbers": [],
            "gas_count": 0,
        }
    
    try:
        import httpx
        
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # Fetch numbers from GAS
            response = await client.get(
                settings.GAS_URL,
                params={"action": "getNumbers"},
            )
            
            if response.status_code != 200:
                return {
                    "configured": True,
                    "error": f"GAS returned status {response.status_code}",
                    "gas_numbers": [],
                    "gas_count": 0,
                }
            
            data = response.json()
            gas_numbers = data.get("numbers", [])
            gas_count = len(gas_numbers)
            
            # Get local count
            local_count = 0
            not_in_gas = 0
            
            if _storage_manager:
                stats = _storage_manager.get_stats()
                local_count = stats.get("total_numbers", 0)
                
                # Count numbers not in GAS
                if local_count > 0:
                    gas_number_set = {n.get("number") for n in gas_numbers}
                    local_numbers = _storage_manager.get_numbers(limit=10000)
                    not_in_gas = sum(
                        1 for n in local_numbers 
                        if n.get("number") not in gas_number_set
                    )
            
            return {
                "configured": True,
                "gas_numbers": gas_numbers[:100],  # Return first 100 for display
                "gas_count": gas_count,
                "local_count": local_count,
                "not_in_gas": not_in_gas,
                "synced": gas_count,
            }
            
    except Exception as e:
        logger.error(f"Error fetching GAS data: {e}")
        return {
            "configured": True,
            "error": str(e),
            "gas_numbers": [],
            "gas_count": 0,
        }
