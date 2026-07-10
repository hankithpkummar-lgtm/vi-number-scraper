"""
Authentication routes for Vi Scraper Dashboard.
Provides login, logout, and session verification endpoints.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.auth.dashboard_auth import (
    authenticate,
    create_token,
    optional_auth,
    require_auth,
    verify_token,
)

logger = logging.getLogger(__name__)

auth_router = APIRouter(tags=["auth"])


@auth_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """
    Serve the login page.
    If already authenticated, redirect to dashboard.
    """
    # Check if already authenticated
    auth = await optional_auth(request)
    if auth:
        return RedirectResponse(url="/dashboard", status_code=303)

    return LOGIN_PAGE_HTML


@auth_router.post("/api/auth/login")
async def api_login(
    username: str = Form(...),
    password: str = Form(...),
):
    """
    API login endpoint. Accepts form data and returns JWT token.

    Sets HTTP-only cookie and returns token in response body.
    """
    token = authenticate(username, password)
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    response = JSONResponse(
        content={
            "success": True,
            "token": token,
            "message": "Login successful",
        }
    )

    # Set HTTP-only cookie (secure flag only in production)
    response.set_cookie(
        key="dashboard_token",
        value=token,
        max_age=86400,  # 24 hours
        httponly=True,
        samesite="lax",
        path="/",
    )

    return response


@auth_router.get("/api/auth/verify")
async def verify_session(auth_payload: dict = __import__('fastapi').Depends(require_auth)):
    """Verify the current session is valid."""
    return {
        "authenticated": True,
        "username": auth_payload.get("sub"),
        "role": auth_payload.get("role"),
    }


@auth_router.post("/api/auth/logout")
async def api_logout():
    """Logout by clearing the auth cookie."""
    response = JSONResponse(
        content={"success": True, "message": "Logged out"}
    )
    response.delete_cookie(key="dashboard_token", path="/")
    return response


@auth_router.get("/logout")
async def logout_redirect():
    """Logout and redirect to login page."""
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="dashboard_token", path="/")
    return response


LOGIN_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login — VI Number Scraper</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #e2e8f0;
        }
        .login-card {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 16px;
            padding: 40px;
            width: 100%;
            max-width: 400px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }
        .login-card .logo {
            text-align: center;
            margin-bottom: 8px;
            font-size: 48px;
        }
        .login-card h1 {
            text-align: center;
            font-size: 20px;
            color: #f8fafc;
            margin-bottom: 4px;
        }
        .login-card .subtitle {
            text-align: center;
            font-size: 13px;
            color: #64748b;
            margin-bottom: 28px;
        }
        .form-group {
            margin-bottom: 18px;
        }
        .form-group label {
            display: block;
            font-size: 13px;
            color: #94a3b8;
            margin-bottom: 6px;
            font-weight: 500;
        }
        .form-group input {
            width: 100%;
            padding: 12px 14px;
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 10px;
            color: #f8fafc;
            font-size: 15px;
            outline: none;
            transition: border-color 0.2s;
        }
        .form-group input:focus {
            border-color: #3b82f6;
            box-shadow: 0 0 0 3px rgba(59,130,246,0.15);
        }
        .form-group input::placeholder {
            color: #475569;
        }
        .btn-login {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #3b82f6, #2563eb);
            border: none;
            border-radius: 10px;
            color: white;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: opacity 0.2s, transform 0.1s;
        }
        .btn-login:hover { opacity: 0.9; }
        .btn-login:active { transform: scale(0.98); }
        .btn-login:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        .error-msg {
            background: #7f1d1d;
            border: 1px solid #991b1b;
            color: #fca5a5;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 13px;
            margin-bottom: 16px;
            display: none;
        }
        .error-msg.visible { display: block; }
        .footer {
            text-align: center;
            margin-top: 20px;
            font-size: 12px;
            color: #475569;
        }
        .spinner {
            display: inline-block;
            width: 16px;
            height: 16px;
            border: 2px solid rgba(255,255,255,0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 0.6s linear infinite;
            vertical-align: middle;
            margin-right: 6px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="login-card">
        <div class="logo">🔐</div>
        <h1>Dashboard Login</h1>
        <p class="subtitle">VI Number Scraper — Admin Panel</p>

        <div class="error-msg" id="errorMsg"></div>

        <form id="loginForm" onsubmit="handleLogin(event)">
            <div class="form-group">
                <label for="username">Username</label>
                <input
                    type="text"
                    id="username"
                    name="username"
                    placeholder="Enter your username"
                    required
                    autocomplete="username"
                    autofocus
                />
            </div>
            <div class="form-group">
                <label for="password">Password</label>
                <input
                    type="password"
                    id="password"
                    name="password"
                    placeholder="Enter your password"
                    required
                    autocomplete="current-password"
                />
            </div>
            <button type="submit" class="btn-login" id="loginBtn">
                Sign In
            </button>
        </form>

        <div class="footer">
            VI Number Scraper v3.0
        </div>
    </div>

    <script>
        async function handleLogin(event) {
            event.preventDefault();
            
            const username = document.getElementById('username').value.trim();
            const password = document.getElementById('password').value;
            const btn = document.getElementById('loginBtn');
            const errorMsg = document.getElementById('errorMsg');
            
            if (!username || !password) {
                showError('Please enter both username and password');
                return;
            }
            
            // Show loading state
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span> Signing in...';
            errorMsg.classList.remove('visible');
            
            try {
                const formData = new URLSearchParams();
                formData.append('username', username);
                formData.append('password', password);
                
                const res = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: formData.toString(),
                });
                
                const data = await res.json();
                
                if (res.ok && data.success) {
                    // Store token in localStorage as backup
                    localStorage.setItem('dashboard_token', data.token);
                    // Redirect to dashboard
                    window.location.href = '/dashboard';
                } else {
                    showError(data.detail || 'Invalid credentials');
                }
            } catch (err) {
                showError('Connection error. Is the server running?');
            } finally {
                btn.disabled = false;
                btn.innerHTML = 'Sign In';
            }
        }
        
        function showError(msg) {
            const el = document.getElementById('errorMsg');
            el.textContent = msg;
            el.classList.add('visible');
        }
        
        // Check if already logged in on page load
        (async function() {
            try {
                const res = await fetch('/api/auth/verify');
                if (res.ok) {
                    window.location.href = '/dashboard';
                }
            } catch(e) {}
        })();
    </script>
</body>
</html>"""
