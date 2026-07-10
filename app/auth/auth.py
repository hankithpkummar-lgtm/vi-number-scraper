"""
Authentication module for Vi Scraper.
Manages credentials securely from environment variables.
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


class CredentialError(Exception):
    """Raised when credentials are missing or invalid."""
    pass


@dataclass
class Credentials:
    """Secure credentials container."""

    username: str
    password: str

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> bool:
        """Validate that credentials are present and properly formatted."""
        if not self.username or not self.username.strip():
            raise CredentialError("Username cannot be empty")
        if not self.password or not self.password.strip():
            raise CredentialError("Password cannot be empty")
        if len(self.username) < 3:
            raise CredentialError("Username appears too short")
        if len(self.password) < 4:
            raise CredentialError("Password appears too short")
        return True

    def get_masked_username(self) -> str:
        """Return masked version of username for logging."""
        if len(self.username) <= 4:
            return "***"
        return self.username[:2] + "***" + self.username[-2:]

    def __repr__(self) -> str:
        return f"Credentials(username='{self.get_masked_username()}', password='***')"


_credentials: Optional[Credentials] = None


def get_credentials() -> Credentials:
    """
    Get or create credentials from environment variables.

    Returns:
        Validated Credentials instance

    Raises:
        CredentialError: If credentials are not set or invalid
    """
    global _credentials

    if _credentials is not None:
        return _credentials

    username = os.getenv("SCRAPER_USERNAME", "")
    password = os.getenv("SCRAPER_PASSWORD", "")

    if not username:
        raise CredentialError(
            "SCRAPER_USERNAME environment variable is not set. "
            "Please set it in your .env file or environment."
        )

    if not password:
        raise CredentialError(
            "SCRAPER_PASSWORD environment variable is not set. "
            "Please set it in your .env file or environment."
        )

    _credentials = Credentials(username=username, password=password)
    logger.info(f"Credentials loaded for user: {_credentials.get_masked_username()}")
    return _credentials


def validate_credentials_on_startup() -> bool:
    """
    Validate credentials during application startup.

    Returns:
        True if credentials are valid

    Raises:
        CredentialError: If credentials are invalid
    """
    try:
        creds = get_credentials()
        logger.info("Credential validation passed")
        return True
    except CredentialError as e:
        logger.critical(f"Credential validation failed: {e}")
        raise


def clear_credentials() -> None:
    """Clear cached credentials (for logout scenarios)."""
    global _credentials
    _credentials = None
    logger.info("Credentials cleared from cache")
