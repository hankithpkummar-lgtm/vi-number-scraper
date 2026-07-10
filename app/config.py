"""
Configuration module for Vi Scraper System.
Loads settings from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    """Main settings loaded from environment variables."""

    SCRAPER_USERNAME: str = os.getenv("SCRAPER_USERNAME", "")
    SCRAPER_PASSWORD: str = os.getenv("SCRAPER_PASSWORD", "")

    SCRAPER_URL: str = os.getenv(
        "SCRAPER_URL",
        "https://www.myvi.in/new-connection/choose-your-fancy-mobile-numbers-online",
    )
    GAS_URL: str = os.getenv("GAS_URL", "")
    PORT: int = int(os.getenv("PORT", "7860"))
    MAX_WORKERS: int = int(os.getenv("MAX_WORKERS", "24"))
    SESSION_TIMEOUT_MINUTES: int = int(os.getenv("SESSION_TIMEOUT_MINUTES", "60"))
    COOLDOWN_MINUTES: int = int(os.getenv("COOLDOWN_MINUTES", "10"))
    NUM_WORKERS: int = int(os.getenv("NUM_WORKERS", "12"))

    DATABASE_PATH: str = str(BASE_DIR / "data" / "numbers.db")
    BACKUP_DIR: str = str(BASE_DIR / "backups")
    LOG_DIR: str = str(BASE_DIR / "logs")
    COOKIE_DIR: str = str(BASE_DIR / "cookies")
    MAX_BACKUP_DAYS: int = 7

    SEARCH_DIGITS: List[int] = field(
        default_factory=lambda: [1, 3, 5, 7, 9]
    )
    SEARCH_PATTERN_LENGTH: int = 5
    SEARCH_COOLDOWN_SECONDS: int = 1
    MAX_SEARCH_CYCLES: int = 10
    PAGE_REFRESH_EVERY: int = 30
    SESSION_TIMEOUT_VARIATION: int = 10

    FORBIDDEN_DIGITS: List[int] = field(default_factory=lambda: [2, 4, 8])
    APPROVED_PAIRS: List[List[int]] = field(
        default_factory=lambda: [
            [1, 1], [1, 3], [1, 5], [1, 7], [1, 9],
            [3, 1], [3, 3], [3, 5], [3, 7], [3, 9],
            [5, 1], [5, 3], [5, 5], [5, 7], [5, 9],
            [7, 1], [7, 3], [7, 5], [7, 7], [7, 9],
            [9, 1], [9, 3], [9, 5], [9, 7], [9, 9],
        ]
    )
    VALID_TOTALS: List[int] = field(
        default_factory=lambda: [1, 3, 5, 6]
    )
    
    # Centralized good pairs list (used in pattern generation + validation)
    GOOD_PAIRS: List[str] = field(
        default_factory=lambda: [
            '11', '13', '31', '15', '51', '17', '71', '19', '91',
            '33', '35', '53', '37', '73', '39', '93',
            '55', '57', '75', '59', '95', '79', '97', '99'
        ]
    )

    PRIORITY_PREFIXES: List[str] = field(
        default_factory=lambda: ["7353", "9071", "9739"]
    )
    PRIORITY_SUBSTRINGS: List[str] = field(
        default_factory=lambda: [
            "13", "15", "171", "373", "969", "96", "75", "95",
            "91", "31", "313", "319", "159",
        ]
    )

    HEADLESS: bool = os.getenv("HEADLESS", "true").lower() == "true"
    BROWSER_TIMEOUT: int = int(os.getenv("BROWSER_TIMEOUT", "120000"))
    NAVIGATION_TIMEOUT: int = int(os.getenv("NAVIGATION_TIMEOUT", "30000"))

    RATE_LIMIT_REQUESTS: int = int(os.getenv("RATE_LIMIT_REQUESTS", "10"))
    RATE_LIMIT_WINDOW: int = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
    
    # Security: API Key for protected endpoints
    SCRAPER_API_KEY: str = os.getenv("SCRAPER_API_KEY", "")
    
    # Form defaults (moved from hardcoded values in scraper.py)
    SCRAPER_FULLNAME: str = os.getenv("SCRAPER_FULLNAME", "Hankith")
    SCRAPER_MOBILE: str = os.getenv("SCRAPER_MOBILE", "9071977078")
    SCRAPER_PINCODE: str = os.getenv("SCRAPER_PINCODE", "560100")

    def __post_init__(self) -> None:
        """Post-init validation and enforcement."""
        # Enforce minimum 1 worker (env var controls actual count per environment)
        if self.NUM_WORKERS < 1:
            self.NUM_WORKERS = 1
        if self.MAX_WORKERS < self.NUM_WORKERS:
            self.MAX_WORKERS = max(self.NUM_WORKERS, 2)
        # AUTO RAM: workers can scale up to MAX_WORKERS based on available RAM
        # The autoRAM logic in workers.py will handle dynamic scaling

    def validate(self) -> bool:
        """Validate that required settings are present."""
        if not self.SCRAPER_USERNAME or not self.SCRAPER_PASSWORD:
            raise ValueError(
                "SCRAPER_USERNAME and SCRAPER_PASSWORD must be set in environment variables"
            )
        return True

    @property
    def is_valid(self) -> bool:
        """Check if credentials are configured."""
        return bool(self.SCRAPER_USERNAME and self.SCRAPER_PASSWORD)


settings = Settings()
