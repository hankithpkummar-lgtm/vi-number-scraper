"""
Dashboard authentication module for Vi Scraper.
Handles JWT-based login for the dashboard UI.
"""

import hashlib
import hmac
import json
import logging
import time
from typing import Optional

from fastapi import Cookie, HTTPException, Request
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)

# ── Hardcoded credentials for dashboard access ──
DASHBOARD_USERNAME = "hankith"
DASHBOARD_PASSWORD = "arvind@2012"

# JWT secret derived from a known secret (NOT for crypto security, just session management)
# In production, this would come from an env var
_JWT_SECRET = "vi-dashboard-secret-hankith-2026"
_JWT_ALGORITHM = "HS256"
_TOKEN_EXPIRY_SECONDS = 86400  # 24 hours


def _base64url_encode(data: bytes) -> str:
    """Base64 URL-safe encoding without padding."""
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _base64url_decode(s: str) -> bytes:
    """Base64 URL-safe decoding with padding restored."""
    import base64
    s = s + '=' * (4 - len(s) % 4) if len(s) % 4 else s
    return base64.urlsafe_b64decode(s)


def _hmac_sha256_sign(payload: str, secret: str) -> str:
    """Create HMAC-SHA256 signature."""
    sig = hmac.new(
        secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).digest()
    return _base64url_encode(sig)


def create_token(username: str) -> str:
    """
    Create a JWT-like token for dashboard access.

    Args:
        username: The authenticated username

    Returns:
        JWT token string
    """
    header = json.dumps({"alg": _JWT_ALGORITHM, "typ": "JWT"})
    payload = json.dumps({
        "sub": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + _TOKEN_EXPIRY_SECONDS,
        "role": "admin",
    })

    header_b64 = _base64url_encode(header.encode('utf-8'))
    payload_b64 = _base64url_encode(payload.encode('utf-8'))

    signing_input = f"{header_b64}.{payload_b64}"
    signature = _hmac_sha256_sign(signing_input, _JWT_SECRET)

    return f"{signing_input}.{signature}"


def verify_token(token: str) -> Optional[dict]:
    """
    Verify a JWT token and return the payload if valid.

    Args:
        token: JWT token string

    Returns:
        Decoded payload dict if valid, None otherwise
    """
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None

        header_b64, payload_b64, signature_b64 = parts

        # Verify signature
        signing_input = f"{header_b64}.{payload_b64}"
        expected_sig = _hmac_sha256_sign(signing_input, _JWT_SECRET)

        # Constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(signature_b64, expected_sig):
            return None

        # Decode payload
        payload_bytes = _base64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode('utf-8'))

        # Check expiry
        if payload.get("exp", 0) < time.time():
            logger.debug("Token expired")
            return None

        return payload

    except Exception as e:
        logger.debug(f"Token verification failed: {e}")
        return None


def authenticate(username: str, password: str) -> Optional[str]:
    """
    Authenticate dashboard credentials.

    Args:
        username: Dashboard username
        password: Dashboard password

    Returns:
        JWT token string if credentials valid, None otherwise
    """
    # Constant-time comparison to prevent timing attacks
    user_match = hmac.compare_digest(
        username.lower().strip(),
        DASHBOARD_USERNAME.lower().strip()
    )
    pass_match = hmac.compare_digest(
        password,
        DASHBOARD_PASSWORD
    )

    if user_match and pass_match:
        token = create_token(username)
        logger.info(f"Dashboard login successful: {username}")
        return token

    logger.warning(f"Dashboard login failed: {username}")
    return None


# ── FastAPI Dependency ──

async def require_auth(request: Request) -> dict:
    """
    FastAPI dependency that requires a valid auth token.
    Checks cookies first, then Authorization header.

    Returns:
        Token payload dict if authenticated

    Raises:
        HTTPException 401 if not authenticated
    """
    token = None

    # Check cookie
    cookie_token = request.cookies.get("dashboard_token")
    if cookie_token:
        token = cookie_token

    # Check Authorization header (fallback for API clients)
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        # Check if it's a JSON body request with token
        try:
            body = await request.json()
            if "token" in body:
                token = body["token"]
        except Exception:
            pass

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


async def optional_auth(request: Request) -> Optional[dict]:
    """
    FastAPI dependency that optionally checks auth.
    Returns payload if valid, None otherwise (no error raised).

    For endpoints that work both authenticated and unauthenticated.
    """
    token = None

    cookie_token = request.cookies.get("dashboard_token")
    if cookie_token:
        token = cookie_token

    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        return None

    return verify_token(token)


def redirect_if_not_auth(auth_payload: Optional[dict]) -> Optional[RedirectResponse]:
    """Redirect to login page if not authenticated. For HTML page routes."""
    if auth_payload is None:
        return RedirectResponse(url="/login", status_code=303)
    return None
