"""
Google Apps Script synchronization service.
"""

import asyncio
import logging
import time
from collections import deque
from typing import Dict, List, Optional

import httpx

from app.config import settings
from app.services.number_validator import NumberValidator
from app.utils.retry import async_retry

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple rate limiter for API calls."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._timestamps: deque = deque()

    async def acquire(self) -> None:
        """Wait until a request slot is available."""
        now = time.time()
        while self._timestamps and self._timestamps[0] < now - self.window_seconds:
            self._timestamps.popleft()

        if len(self._timestamps) >= self.max_requests:
            wait_time = self._timestamps[0] + self.window_seconds - now
            if wait_time > 0:
                logger.debug(f"Rate limit reached, waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)

        self._timestamps.append(time.time())


class GasSyncService:
    """Service for syncing numbers with Google Apps Script."""

    # P1 Fix: Maximum queue size to prevent memory leaks
    MAX_QUEUE_SIZE = 1000

    def __init__(self) -> None:
        self._gas_url = settings.GAS_URL
        self._resolved_url: Optional[str] = None
        self._rate_limiter = RateLimiter(
            max_requests=settings.RATE_LIMIT_REQUESTS,
            window_seconds=settings.RATE_LIMIT_WINDOW,
        )
        self._client: Optional[httpx.AsyncClient] = None
        self._upload_queue: List[dict] = []
        self._failed_uploads: List[dict] = []
        self._last_sync_time: float = 0
        self._total_uploaded: int = 0
        self._total_failed: int = 0

    def _add_to_queue(self, queue: list, item: dict) -> None:
        """Add item to queue with size limit (P1 Fix)."""
        if len(queue) >= self.MAX_QUEUE_SIZE:
            queue.pop(0)  # Evict oldest
        queue.append(item)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={"Content-Type": "application/json"},
                follow_redirects=True,
            )
        return self._client

    async def _resolve_gas_url(self) -> str:
        """Resolve the GAS URL by following redirects to get the actual execution URL."""
        if self._resolved_url:
            return self._resolved_url
        
        if not self._gas_url:
            return ""
        
        try:
            client = await self._get_client()
            # Make a GET request to follow redirects and get the final URL
            response = await client.get(self._gas_url)
            self._resolved_url = str(response.url)
            logger.info(f"GAS URL resolved: {self._resolved_url[:80]}...")
            return self._resolved_url
        except Exception as e:
            logger.warning(f"Failed to resolve GAS URL: {e}, using original")
            return self._gas_url

    async def upload_number(self, number_data: dict) -> bool:
        """
        Upload a single number to Google Apps Script via GET.

        Args:
            number_data: Number data dictionary

        Returns:
            True if upload successful
        """
        if not self._gas_url:
            logger.warning("GAS_URL not configured, queuing upload")
            self._add_to_queue(self._upload_queue, number_data)
            return False

        await self._rate_limiter.acquire()

        try:
            client = await self._get_client()
            params = {
                "action": "addNumber",
                "number": number_data["number"],
                "root": str(number_data.get("root", 0)),
                "compound": str(number_data.get("compound", 0)),
                "source": "scraper",
                "plan": number_data.get("plan", "---"),
            }

            logger.debug(f"Uploading number {number_data['number']} to GAS via GET...")
            response = await client.get(self._gas_url, params=params)

            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    self._total_uploaded += 1
                    self._last_sync_time = time.time()
                    logger.info(f"GAS upload success: {number_data['number']}")
                    return True
                else:
                    logger.warning(f"GAS upload rejected: {result}")
                    self._add_to_queue(self._failed_uploads, number_data)
                    self._total_failed += 1
                    return False
            else:
                logger.warning(
                    f"GAS upload failed with status {response.status_code}"
                )
                self._add_to_queue(self._failed_uploads, number_data)
                self._total_failed += 1
                return False

        except httpx.RequestError as e:
            logger.error(f"GAS upload network error: {e}")
            self._add_to_queue(self._failed_uploads, number_data)
            self._total_failed += 1
            return False
        except Exception as e:
            logger.error(f"GAS upload error: {e}")
            self._add_to_queue(self._failed_uploads, number_data)
            self._total_failed += 1
            return False

    async def upload_batch(self, numbers: List[dict]) -> int:
        """
        Upload multiple numbers to Google Apps Script via GET.
        Pre-validates each number via NumberValidator before sending to GAS.

        Args:
            numbers: List of number data dictionaries

        Returns:
            Count of successfully uploaded numbers
        """
        if not self._gas_url:
            logger.warning("GAS_URL not configured, queuing batch")
            for num in numbers:
                self._add_to_queue(self._upload_queue, num)
            return 0

        # Pre-validate all numbers via NumberValidator before upload
        filtered = []
        skipped_pre = 0
        for num in numbers:
            raw = num.get("number", "")
            result = NumberValidator.pre_validate(raw)
            if result["valid"]:
                filtered.append(num)
            else:
                skipped_pre += 1
                logger.debug(f"Skipping pre-upload validation failure: {raw} — {result['reason']}")

        if skipped_pre > 0:
            logger.warning(f"Pre-upload validation skipped {skipped_pre}/{len(numbers)} numbers")

        if not filtered:
            logger.info("All numbers filtered out by pre-upload validation")
            return 0

        await self._rate_limiter.acquire()

        try:
            import json as json_mod
            client = await self._get_client()
            batch_data = [
                {
                    "number": num["number"],
                    "root": num.get("root", 0),
                    "compound": num.get("compound", 0),
                    "source": "scraper",
                    "plan": num.get("plan", "---"),
                }
                for num in filtered
            ]
            params = {
                "action": "addNumbersBatch",
                "numbers": json_mod.dumps(batch_data),
            }

            logger.info(f"Batch uploading {len(filtered)} numbers to GAS via GET (filtered from {len(numbers)})...")
            response = await client.get(self._gas_url, params=params)

            if response.status_code == 200:
                result = response.json()
                uploaded_count = result.get("added", 0)
                skipped_count = result.get("skipped", 0)
                self._total_uploaded += uploaded_count
                self._last_sync_time = time.time()

                # GAS returns skipped when numbers don't pass its own numerology validation.
                # That's still a successful delivery — the number was sent to GAS successfully,
                # even if GAS chose not to add it. Count it as "processed" not "failed".
                processed_count = uploaded_count + skipped_count

                logger.info(
                    f"GAS batch upload: {uploaded_count} added, {skipped_count} skipped "
                    f"(processed: {processed_count}/{len(numbers)})"
                )
                return processed_count
            else:
                logger.warning(
                    f"GAS batch upload failed with status {response.status_code}"
                )
                for num in numbers:
                    self._add_to_queue(self._failed_uploads, num)
                self._total_failed += len(numbers)
                return 0

        except Exception as e:
            logger.error(f"GAS batch upload error: {e}")
            for num in numbers:
                self._add_to_queue(self._failed_uploads, num)
            self._total_failed += len(numbers)
            return 0

    async def sync_pending(self) -> int:
        """
        Sync all pending uploads from the queue.

        Returns:
            Count of synced numbers
        """
        if not self._upload_queue:
            return 0

        total_synced = 0
        batch_size = 10

        while self._upload_queue:
            batch = self._upload_queue[:batch_size]
            self._upload_queue = self._upload_queue[batch_size:]

            synced = await self.upload_batch(batch)
            total_synced += synced

            if synced < len(batch):
                self._upload_queue.extend(batch[synced:])

            await asyncio.sleep(1)

        return total_synced

    async def retry_failed(self) -> int:
        """
        Retry all failed uploads.

        Returns:
            Count of successfully retried uploads
        """
        if not self._failed_uploads:
            return 0

        retried = self._failed_uploads.copy()
        self._failed_uploads.clear()

        total_synced = await self.upload_batch(retried)
        return total_synced

    async def check_number_exists_in_gas(self, number: str) -> Optional[bool]:
        """
        Check if a specific number already exists in the Google Sheet.

        Tries to add the number — if GAS says 'Duplicate', it exists.
        If it fails for another reason, returns None (unknown).

        Args:
            number: Phone number string

        Returns:
            True if number exists in sheet,
            False if it doesn't,
            None if we couldn't determine (API error)
        """
        if not self._gas_url:
            return None

        await self._rate_limiter.acquire()

        try:
            client = await self._get_client()
            params = {
                "action": "addNumber",
                "number": number,
                "root": "0",
                "compound": "0",
                "source": "check",
                "plan": "check",
            }
            response = await client.get(self._gas_url, params=params)

            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    skipped_reason = result.get("reason", "")
                    if "Duplicate" in skipped_reason or "duplicate" in skipped_reason:
                        return True
                    # Number was accepted (added or skipped for other reason)
                    # If it was added, it didn't exist before
                    if result.get("skipped") and "Duplicate" not in str(result.get("reason", "")):
                        return None  # Can't determine
                    return False
            return None
        except Exception as e:
            logger.debug(f"Error checking number {number} in GAS: {e}")
            return None

    async def fetch_all_numbers(self) -> List[dict]:
        """
        Fetch ALL numbers from the Google Sheet via GAS URL.

        Returns:
            List of number dicts from the sheet (each has: number, root, compound, plan, price, status...)
            Empty list on failure.
        """
        if not self._gas_url:
            logger.warning("GAS_URL not configured — cannot fetch from sheet")
            return []

        await self._rate_limiter.acquire()

        try:
            client = await self._get_client()
            params = {"action": "getNumbers"}
            response = await client.get(self._gas_url, params=params)

            if response.status_code != 200:
                logger.warning(f"GAS fetch returned status {response.status_code}")
                return []

            data = response.json()
            numbers = data.get("numbers", [])
            logger.info(f"Fetched {len(numbers)} numbers from Google Sheet")
            return numbers

        except Exception as e:
            logger.error(f"Error fetching numbers from GAS: {e}")
            return []

    async def health_check(self) -> dict:
        """
        Check GAS connectivity.

        Returns:
            Health status dictionary
        """
        if not self._gas_url:
            return {
                "status": "not_configured",
                "message": "GAS_URL not set",
            }

        try:
            client = await self._get_client()
            params = {"action": "healthCheck"}
            response = await client.get(self._gas_url, params=params)

            if response.status_code == 200:
                return {"status": "healthy", "last_sync": self._last_sync_time}
            else:
                return {
                    "status": "unhealthy",
                    "status_code": response.status_code,
                }

        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def get_stats(self) -> dict:
        """Get sync service statistics."""
        return {
            "gas_configured": bool(self._gas_url),
            "total_uploaded": self._total_uploaded,
            "total_failed": self._total_failed,
            "pending_queue_size": len(self._upload_queue),
            "failed_queue_size": len(self._failed_uploads),
            "last_sync_time": self._last_sync_time,
        }

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
