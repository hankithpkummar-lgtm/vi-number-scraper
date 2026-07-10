"""
Core scraping logic for Vi mobile number search.
"""

import asyncio
import logging
import random
import re
import time
from typing import Callable, List, Optional

from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.config import settings
from app.scraper.session import SessionManager
from app.services.number_validator import NumberValidator
from app.utils.retry import async_retry

validator = NumberValidator()

logger = logging.getLogger(__name__)


class ScraperEngine:
    """Core scraping engine for Vi mobile number search."""

    def __init__(
        self,
        browser_page_getter: Callable,
        session_manager: SessionManager,
        number_callback: Optional[Callable] = None,
    ) -> None:
        """
        Initialize ScraperEngine.

        Args:
            browser_page_getter: Async callable returning a Playwright Page
            session_manager: SessionManager instance
            number_callback: Async callback for found numbers
        """
        self._get_page = browser_page_getter
        self._session = session_manager
        self._callback = number_callback
        self._is_running = False
        self._should_stop = False
        self._search_count = 0
        self._total_found = 0
        self._last_refresh = 0
        self._start_time: float = 0

    async def start(self) -> None:
        """Start the scraping engine."""
        if self._is_running:
            logger.warning("Scraper is already running")
            return

        self._is_running = True
        self._should_stop = False
        self._start_time = time.time()
        logger.info("Scraper engine started")

    async def stop(self) -> None:
        """Stop the scraping engine."""
        self._should_stop = True
        logger.info("Stopping scraper engine...")

    async def scrape_cycle(self) -> dict:
        """
        Run a single scrape cycle.

        Returns:
            Dict with:
                'raw_numbers': List[dict] — ALL numbers found on the page
                'saved_numbers': List[dict] — Only validated numbers that were saved
                Each entry: {number, saved (bool), root, compound}
        """
        found_numbers = []  # Validated numbers that were saved
        all_numbers = []    # ALL raw numbers from the page (including invalid)
        saved_set = set()   # Track which numbers were saved
        consecutive_empty = 0
        MAX_EMPTY_BEFORE_REFRESH = 3

        try:
            # Session is optional — search page is publicly accessible
            try:
                await self._session.refresh_session()
            except Exception:
                pass

            page = await self._get_page()
            await self._navigate_to_search(page)
            await self._fill_form(page)
            await self._select_free_number_tab(page)

            patterns = self._generate_search_patterns()
            logger.info(f"Generated {len(patterns)} search patterns to scan")

            for i, pattern in enumerate(patterns):
                if self._should_stop:
                    break

                try:
                    results = await self._search_pattern(page, pattern)
                    valid_numbers = self._validate_numbers(results)

                    # Track ALL raw numbers from page
                    for num in results:
                        all_numbers.append({
                            "number": num,
                            "saved": False,
                            "root": "?",
                            "compound": "?",
                        })

                    if valid_numbers:
                        logger.info(f"Pattern '{pattern}': {len(results)} raw, {len(valid_numbers)} valid")
                        consecutive_empty = 0
                    else:
                        consecutive_empty += 1
                        if consecutive_empty >= MAX_EMPTY_BEFORE_REFRESH:
                            logger.warning(f"{consecutive_empty} consecutive empty results — refreshing page")
                            await self._refresh_page(page)
                            consecutive_empty = 0

                    for number_data in valid_numbers:
                        num = number_data["number"]
                        saved_set.add(num)
                        if self._callback:
                            await self._callback(number_data)
                        found_numbers.append(number_data)
                        self._total_found += 1

                    self._search_count += 1

                    # Click next page if available
                    try:
                        await page.click('span.next')
                    except Exception:
                        pass
                    await asyncio.sleep(0.3)

                    if self._search_count % settings.PAGE_REFRESH_EVERY == 0:
                        await self._refresh_page(page)

                    await asyncio.sleep(settings.SEARCH_COOLDOWN_SECONDS)

                except PlaywrightTimeout:
                    logger.warning(f"Timeout searching pattern: {pattern}")
                    consecutive_empty += 1
                    continue
                except Exception as e:
                    logger.error(f"Error searching pattern {pattern}: {e}")
                    consecutive_empty += 1
                    continue

        except Exception as e:
            logger.error(f"Scrape cycle failed: {e}")

        # Mark which raw numbers were saved
        for entry in all_numbers:
            if entry["number"] in saved_set:
                entry["saved"] = True
                # Find matching validated data for root/compound
                for vn in found_numbers:
                    if vn["number"] == entry["number"]:
                        entry["root"] = vn.get("root", "?")
                        entry["compound"] = vn.get("compound", "?")
                        break

        # Keep raw numbers unique per cycle (same number may appear in multiple patterns)
        seen = set()
        unique_raw = []
        for entry in all_numbers:
            if entry["number"] not in seen:
                seen.add(entry["number"])
                unique_raw.append(entry)

        logger.info(
            f"Scrape cycle: {len(unique_raw)} raw numbers on page, "
            f"{len(found_numbers)} validated & saved"
        )
        return {
            "raw_numbers": unique_raw,
            "saved_numbers": found_numbers,
        }

    async def _navigate_to_search(self, page: Page) -> None:
        """Navigate to the search page."""
        await page.goto(
            settings.SCRAPER_URL,
            wait_until="domcontentloaded",
            timeout=settings.BROWSER_TIMEOUT,
        )
        await asyncio.sleep(2)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        await asyncio.sleep(1)

    async def _fill_form(self, page: Page) -> None:
        """Fill the search form with default values (matching JS scraper selectors)."""
        # P0 Fix: Use environment variables instead of hardcoded values
        # Pincode
        try:
            await page.fill('input#pinCode', settings.SCRAPER_PINCODE)
        except Exception:
            pass
        await asyncio.sleep(0.5)

        # Close popup if present
        try:
            popup = page.locator('img.close-icon, img[alt="store modal close"]')
            if await popup.count() > 0:
                await popup.first().click(timeout=2000)
        except Exception:
            pass

        # Mobile
        try:
            await page.fill('input#moNumber', settings.SCRAPER_MOBILE)
        except Exception:
            pass
        await asyncio.sleep(0.3)

        # Fullname
        try:
            await page.fill('input#fullname', settings.SCRAPER_FULLNAME)
        except Exception:
            pass
        await asyncio.sleep(0.3)

    async def _select_free_number_tab(self, page: Page) -> None:
        """Click on the Free Number tab (matching JS scraper selector)."""
        try:
            await page.click('a#freeNumber-tab')
            await asyncio.sleep(0.5)
            logger.debug("Free Number tab clicked via a#freeNumber-tab")
        except Exception:
            logger.debug("Free Number tab not found, continuing with current view")

    def _generate_search_patterns(self) -> List[str]:
        """Generate search patterns from approved digits (matching JS scraper)."""
        # P2 Fix: Use centralized GOOD_PAIRS from config
        good_pairs = settings.GOOD_PAIRS
        digits = ['1', '3', '5', '7', '9']
        patterns = []
        attempts = 0
        while len(patterns) < settings.MAX_SEARCH_CYCLES and attempts < settings.MAX_SEARCH_CYCLES * 3:
            attempts += 1
            s = ''
            while len(s) < settings.SEARCH_PATTERN_LENGTH:
                digit = random.choice(digits)
                temp = s + digit
                if len(temp) > 1:
                    pair = temp[-2:]
                    if pair == '77' or pair not in good_pairs:
                        continue
                if len(temp) > 2 and temp[-3] == temp[-2] == temp[-1]:
                    continue
                s = temp
            if s not in patterns:
                patterns.append(s)
        return patterns

    async def _search_pattern(self, page: Page, pattern: str) -> List[str]:
        """Search for a specific pattern on the page (matching JS scraper selectors)."""
        found_numbers = []

        # Fill search input (JS: input#cynNumber)
        try:
            await page.fill('input#cynNumber', pattern)
        except Exception:
            pass
        await asyncio.sleep(0.2)

        # Click search button (JS: button#SearchBtnCYN)
        try:
            await page.click('button#SearchBtnCYN')
        except Exception:
            pass

        # Wait for results
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        await asyncio.sleep(0.8)

        # Extract numbers from results (JS: div.num-inner-wrap > span.mo-no)
        try:
            results = await page.evaluate("""() => {
                const nodes = document.querySelectorAll('div.num-inner-wrap');
                return Array.from(nodes).map(node => {
                    const numEl = node.querySelector('span.mo-no');
                    const typeEl = node.querySelector('span.type');
                    return {
                        num: numEl ? numEl.innerText.replace(/\\D/g, '') : '',
                        type: typeEl ? typeEl.innerText.trim() : ''
                    };
                }).filter(item => item.num && item.num.length >= 6);
            }""")
            for item in results:
                if item.get('num'):
                    found_numbers.append(item['num'])
        except Exception as e:
            logger.debug(f"Result extraction error: {e}")

        return found_numbers

    def _extract_numbers_from_text(self, text: str) -> List[str]:
        """Extract 10-digit numbers from text."""
        import re
        numbers = re.findall(r'\b\d{10}\b', text)
        return [num for num in numbers if num.startswith(('6', '7', '8', '9'))]

    def _validate_numbers(self, numbers: List[str]) -> List[dict]:
        """
        Validate found numbers using NumberValidator (exact GAS v6 rules).

        Args:
            numbers: List of phone numbers to validate

        Returns:
            List of validated number dictionaries
        """
        validated = []

        for number in numbers:
            result = validator.pre_validate(number)
            if result["valid"]:
                clean = re.sub(r'\D', '', str(number))
                number_data = {
                    "number": number,
                    "root": result["root"],
                    "compound": result["compound"],
                    "type": result["classification"],
                    "priority": self._calculate_priority(number, result["root"]),
                    "found_at": time.time(),
                }
                validated.append(number_data)

        return validated

    def _calculate_priority(self, number: str, root: int = None) -> int:
        """Calculate priority score for the number."""
        score = 0

        for i, prefix in enumerate(settings.PRIORITY_PREFIXES):
            if number.startswith(prefix):
                score += (len(settings.PRIORITY_PREFIXES) - i) * 10
                break

        for substring in settings.PRIORITY_SUBSTRINGS:
            if substring in number:
                score += 20
                break

        if root is None:
            s = re.sub(r'\D', '', str(number))
            root = sum(int(d) for d in s)
            while root > 9:
                root = sum(int(d) for d in str(root))

        if root in [1, 3, 5, 6, 9]:
            score += 15

        total = sum(int(d) for d in re.sub(r'\D', '', str(number)))
        if total in [1, 2, 3, 5, 6, 8, 9, 10, 11]:
            score += 10

        return score

    async def _refresh_page(self, page: Page) -> None:
        """Refresh the page to avoid session issues (matching JS scraper)."""
        try:
            await page.goto(
                settings.SCRAPER_URL,
                wait_until="domcontentloaded",
                timeout=settings.BROWSER_TIMEOUT,
            )
            await asyncio.sleep(1.5)
            # P0 Fix: Use environment variables instead of hardcoded values
            await page.fill('input#pinCode', settings.SCRAPER_PINCODE)
            await asyncio.sleep(0.3)
            # Close popup
            try:
                popup = page.locator('img.close-icon, img[alt="store modal close"]')
                if await popup.count() > 0:
                    await popup.first().click(timeout=2000)
            except Exception:
                pass
            await page.fill('input#moNumber', settings.SCRAPER_MOBILE)
            await asyncio.sleep(0.2)
            await page.fill('input#fullname', settings.SCRAPER_FULLNAME)
            await asyncio.sleep(0.2)
            await page.click('a#freeNumber-tab')
            await asyncio.sleep(0.3)
            self._last_refresh = time.time()
            logger.debug("Page refreshed and form refilled")
        except Exception as e:
            logger.warning(f"Page refresh failed: {e}")

    def get_stats(self) -> dict:
        """Get scraper statistics."""
        return {
            "is_running": self._is_running,
            "search_count": self._search_count,
            "total_found": self._total_found,
            "uptime": time.time() - self._start_time if self._start_time else 0,
            "last_refresh": self._last_refresh,
        }

    async def check_number_availability(self, page: Page, full_number: str) -> dict:
        """
        Check if a specific number is available on VI website.

        Args:
            page: Playwright page instance
            full_number: 10-digit phone number to check

        Returns:
            {available: bool, number: str, status: str, found_at: float}
        """
        try:
            # Navigate to VI search page
            await page.goto(
                settings.SCRAPER_URL,
                wait_until="domcontentloaded",
                timeout=settings.BROWSER_TIMEOUT,
            )
            await asyncio.sleep(2)

            # Fill form with default values
            await page.fill('input#pinCode', settings.SCRAPER_PINCODE)
            await asyncio.sleep(0.5)

            # Close popup if present
            try:
                popup = page.locator('img.close-icon, img[alt="store modal close"]')
                if await popup.count() > 0:
                    await popup.first().click(timeout=2000)
            except Exception:
                pass

            await page.fill('input#moNumber', settings.SCRAPER_MOBILE)
            await asyncio.sleep(0.3)

            await page.fill('input#fullname', settings.SCRAPER_FULLNAME)
            await asyncio.sleep(0.3)

            # Click Free Number tab
            try:
                await page.click('a#freeNumber-tab')
                await asyncio.sleep(0.5)
            except Exception:
                pass

            # Fill search with FULL number (not pattern)
            await page.fill('input#cynNumber', full_number)
            await asyncio.sleep(0.2)

            # Click search
            await page.click('button#SearchBtnCYN')
            await asyncio.sleep(0.8)

            # Wait for results
            try:
                await page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass

            # Check if the exact number appears in results
            results = await page.evaluate("""() => {
                const nodes = document.querySelectorAll('div.num-inner-wrap');
                return Array.from(nodes).map(node => {
                    const numEl = node.querySelector('span.mo-no');
                    return numEl ? numEl.innerText.replace(/\\D/g, '') : '';
                }).filter(item => item.length >= 6);
            }""")

            available = full_number in results

            return {
                "available": available,
                "number": full_number,
                "status": "Available" if available else "Not Available",
                "found_at": time.time(),
            }

        except Exception as e:
            logger.error(f"Availability check error for {full_number}: {e}")
            return {
                "available": False,
                "number": full_number,
                "status": f"Error: {str(e)}",
                "found_at": time.time(),
            }


async def check_and_remove_unavailable(
    page: Page, 
    number: str, 
    storage: 'StorageManager'
) -> dict:
    """
    Check availability and auto-remove from backup if unavailable.
    
    Args:
        page: Playwright page instance
        number: Phone number to check
        storage: StorageManager instance for database operations
        
    Returns:
        {available: bool, number: str, status: str, found_at: float}
    """
    try:
        # Create a temporary scraper engine for availability check
        async def page_getter():
            return page
        
        from app.scraper.session import SessionManager
        session_manager = SessionManager(page_getter)
        temp_scraper = ScraperEngine(
            browser_page_getter=page_getter,
            session_manager=session_manager,
        )
        
        result = await temp_scraper.check_number_availability(page, number)
        
        if not result["available"]:
            # Remove from local SQLite
            storage.delete_number(number)
            logger.info(f"Auto-removed unavailable number: {number}")
        
        return result
        
    except Exception as e:
        logger.error(f"Check and remove failed for {number}: {e}")
        return {
            "available": False,
            "number": number,
            "status": f"Error: {str(e)}",
            "found_at": time.time(),
        }


async def batch_check_availability(
    numbers: List[str], 
    storage: 'StorageManager',
    get_page_callback: Callable
) -> List[dict]:
    """
    Check availability for multiple numbers and auto-remove unavailable ones.
    
    Args:
        numbers: List of phone numbers to check
        storage: StorageManager instance for database operations
        get_page_callback: Async callable that returns a Playwright Page
        
    Returns:
        List of availability check results
    """
    results = []
    
    for number in numbers:
        if len(number) != 10 or not number.isdigit():
            results.append({
                "number": number,
                "available": False,
                "status": "Invalid format",
                "found_at": time.time()
            })
            continue
        
        try:
            page = await get_page_callback()
            if not page:
                results.append({
                    "number": number,
                    "available": False,
                    "status": "No browser available",
                    "found_at": time.time()
                })
                continue
            
            result = await check_and_remove_unavailable(page, number, storage)
            results.append(result)
            
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
    
    return results
