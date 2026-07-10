"""
Dashboard module for Vi Scraper - Shows logs, stats, and controls.
"""

import asyncio
import time
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.dashboard_auth import require_auth, optional_auth

dashboard_router = APIRouter()

# In-memory log buffer (last 500 entries)
_log_buffer: List[Dict] = []
_max_logs = 500

# Stats tracking
_stats = {
    "total_found": 0,
    "total_uploaded": 0,
    "total_duplicates": 0,
    "total_errors": 0,
    "session_start": None,
    "last_number_found": None,
    "last_upload": None,
    "scrape_cycles": 0,
    "numbers_by_root": {},
    "numbers_by_total": {},
}

# Scrape cycle buffer — groups ALL numbers found per search, with saved markers
# Each cycle entry: {cycle_id, worker_id, timestamp, numbers[{number,saved,root,compound}], raw_count, saved_count}
_scrape_cycles: List[Dict] = []
_max_cycles = 30
_cycle_counter = 0


def add_log(level: str, message: str, details: Optional[Dict] = None) -> None:
    """Add a log entry to the buffer."""
    global _log_buffer
    entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "message": message,
        "details": details or {},
    }
    _log_buffer.append(entry)
    if len(_log_buffer) > _max_logs:
        _log_buffer = _log_buffer[-_max_logs:]


def record_number_found(root: int, total: int) -> None:
    """Record a number being found."""
    _stats["total_found"] += 1
    _stats["last_number_found"] = datetime.now().isoformat()
    _stats["numbers_by_root"][str(root)] = _stats["numbers_by_root"].get(str(root), 0) + 1
    _stats["numbers_by_total"][str(total)] = _stats["numbers_by_total"].get(str(total), 0) + 1


def record_upload() -> None:
    """Record a successful upload."""
    _stats["total_uploaded"] += 1
    _stats["last_upload"] = datetime.now().isoformat()


def record_duplicate() -> None:
    """Record a duplicate being blocked."""
    _stats["total_duplicates"] += 1


def record_error() -> None:
    """Record an error."""
    _stats["total_errors"] += 1


def record_scrape_cycle() -> None:
    """Record a scrape cycle completion."""
    _stats["scrape_cycles"] += 1


def get_stats() -> Dict:
    """Get current statistics."""
    return _stats.copy()


def get_logs(limit: int = 100) -> List[Dict]:
    """Get recent logs."""
    return _log_buffer[-limit:]


def record_scrape_cycle(raw_numbers: list, saved_numbers: list, worker_id: int) -> None:
    """
    Record a full scrape cycle — all raw numbers found + which ones were selected/saved.
    Groups numbers by cycle so users can see exactly what VI returned per search.
    
    Args:
        raw_numbers: All numbers from the VI search page
        saved_numbers: Subset that passed numerology validation and were saved
        worker_id: Worker that performed this search
    """
    global _scrape_cycles, _cycle_counter
    _cycle_counter += 1
    now = time.time()
    
    # Build a set of saved numbers for fast lookup
    saved_set = {n["number"] for n in saved_numbers}
    
    numbers = []
    for n in raw_numbers:
        is_saved = n["number"] in saved_set
        numbers.append({
            "number": n["number"],
            "saved": is_saved,
            "root": n.get("root", "?"),
            "compound": n.get("compound", "?"),
        })
    
    cycle_entry = {
        "cycle_id": _cycle_counter,
        "worker_id": worker_id,
        "timestamp": now,
        "numbers": numbers,
        "raw_count": len(raw_numbers),
        "saved_count": len(saved_numbers),
    }
    
    _scrape_cycles.append(cycle_entry)
    if len(_scrape_cycles) > _max_cycles:
        _scrape_cycles = _scrape_cycles[-_max_cycles:]


@dashboard_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> str:
    """Serve the dashboard HTML page. (Protected)"""
    auth = await optional_auth(request)
    if not auth:
        return LOGIN_REDIRECT_HTML
    return DASHBOARD_HTML


@dashboard_router.get("/api/dashboard/stats")
async def dashboard_stats(
    auth_payload: dict = Depends(require_auth),
) -> Dict:
    """Get dashboard statistics. (Protected)"""
    return {
        "stats": _stats,
        "uptime": time.time() - (_stats.get("session_start") or time.time()),
    }


@dashboard_router.get("/api/dashboard/logs")
async def dashboard_logs(
    auth_payload: dict = Depends(require_auth),
    limit: int = 100,
) -> Dict:
    """Get dashboard logs. (Protected)"""
    return {"logs": get_logs(limit), "total": len(_log_buffer)}


@dashboard_router.get("/api/dashboard/latest-scrape")
async def dashboard_latest_scrape(
    auth_payload: dict = Depends(require_auth),
    limit: int = 50,
) -> Dict:
    """Get latest scrape results as flat list (all raw numbers found, with saved status).
    
    Derives from the cycle buffer for backward compatibility."""
    # Flatten cycles into individual entries
    flat = []
    for c in _scrape_cycles:
        for n in c["numbers"]:
            flat.append({
                "number": n["number"],
                "worker_id": c["worker_id"],
                "saved": n["saved"],
                "root": n["root"],
                "compound": n["compound"],
                "timestamp": c["timestamp"],
            })
    return {
        "numbers": flat[-limit:],
        "total": len(flat),
    }


@dashboard_router.get("/api/dashboard/scrape-cycles")
async def dashboard_scrape_cycles(
    auth_payload: dict = Depends(require_auth),
    limit: int = 20,
) -> Dict:
    """Get scrape cycles — each cycle shows ALL numbers found in that search,
    with saved ones highlighted. Shows exactly what VI returned per search
    and which number was selected."""
    return {
        "cycles": _scrape_cycles[-limit:],
        "total": len(_scrape_cycles),
    }


@dashboard_router.get("/api/dashboard/logs/stream")
async def dashboard_logs_stream(
    auth_payload: dict = Depends(require_auth),
):
    """Server-Sent Events for live log streaming. (Protected)"""
    from fastapi.responses import StreamingResponse

    async def event_generator():
        last_idx = len(_log_buffer)
        while True:
            if len(_log_buffer) > last_idx:
                new_logs = _log_buffer[last_idx:]
                for log in new_logs:
                    yield f"data: {log}\n\n"
                last_idx = len(_log_buffer)
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


LOGIN_REDIRECT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Redirecting...</title>
    <style>
        body { background: #0f172a; color: #94a3b8; display: flex; align-items: center; justify-content: center; height: 100vh; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
        .msg { text-align: center; }
        .spinner { width: 32px; height: 32px; border: 3px solid #334155; border-top-color: #3b82f6; border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto 16px; }
        @keyframes spin { to { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="msg">
        <div class="spinner"></div>
        <p>Redirecting to login...</p>
    </div>
    <script>window.location.href = '/login';</script>
</body>
</html>"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VI Number Scraper — Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}
.header{background:linear-gradient(135deg,#1e293b,#0f172a);border-bottom:1px solid #334155;padding:12px 24px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100}
.header .left{display:flex;align-items:center;gap:12px}
.header .left h1{font-size:18px;color:#f8fafc}
.header .left .dot{width:8px;height:8px;border-radius:50%;background:#22c55e;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
.header .right{display:flex;align-items:center;gap:12px}
.header .right .time{font-size:12px;color:#64748b;font-variant-numeric:tabular-nums}
.btn{display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border-radius:8px;font-size:12px;font-weight:500;cursor:pointer;border:none;transition:all .15s;text-decoration:none}
.btn-sm{padding:4px 10px;font-size:11px}
.btn-primary{background:#3b82f6;color:#fff}
.btn-primary:hover{background:#2563eb}
.btn-danger{background:#ef4444;color:#fff}
.btn-danger:hover{background:#dc2626}
.btn-ghost{background:#334155;color:#94a3b8}
.btn-ghost:hover{background:#475569;color:#e2e8f0}
.btn-success{background:#059669;color:#fff}
.btn-success:hover{background:#047857}
.btn-success{background:#16a34a;color:#fff}
.btn-success:hover{background:#15803d}
.btn:disabled{opacity:.5;cursor:not-allowed}
.container{max-width:1400px;margin:0 auto;padding:16px 20px}

/* ── Stats ── */
.stats-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:16px}
.stat-box{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px 16px;text-align:center}
.stat-box .num{font-size:26px;font-weight:700;font-variant-numeric:tabular-nums}
.stat-box .lbl{font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px;margin-top:2px}
.stat-box.green .num{color:#22c55e}
.stat-box.blue .num{color:#3b82f6}
.stat-box.yellow .num{color:#f59e0b}
.stat-box.red .num{color:#ef4444}
.stat-box.purple .num{color:#a855f7}

/* Root Breakdown Grid */
.root-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-bottom:16px}
.root-card{border-radius:12px;padding:16px 18px;display:flex;flex-direction:column;gap:8px}
.root-card .root-hdr{display:flex;align-items:center;gap:10px}
.root-card .root-digit{font-size:28px;font-weight:800;width:44px;height:44px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.root-card .root-name{font-size:13px;color:#94a3b8;text-transform:uppercase;letter-spacing:.3px}
.root-card .root-bars{display:flex;gap:10px}
.root-card .root-bar-wrap{flex:1}
.root-card .root-bar-label{font-size:10px;color:#64748b;margin-bottom:2px;display:flex;justify-content:space-between}
.root-card .root-bar-track{height:6px;border-radius:3px;background:rgba(255,255,255,.08);overflow:hidden}
.root-card .root-bar-fill{height:100%;border-radius:3px;transition:width .5s ease}
.root-card .root-totals{display:flex;gap:12px;margin-top:2px;font-size:12px}
.root-card .root-totals span{display:flex;align-items:center;gap:4px}

/* ── Tabs ── */
.tabs{display:flex;gap:2px;margin-bottom:14px;background:#1e293b;border:1px solid #334155;border-radius:10px;padding:3px;overflow-x:auto}
.tab-btn{padding:8px 18px;border:none;border-radius:8px;font-size:12px;font-weight:500;cursor:pointer;background:transparent;color:#64748b;white-space:nowrap;transition:all .15s}
.tab-btn:hover{color:#e2e8f0;background:#334155}
.tab-btn.active{background:#3b82f6;color:#fff}
.tab-btn .badge{display:inline-block;background:rgba(255,255,255,.15);padding:0 6px;border-radius:4px;font-size:10px;margin-left:4px}
.tab-btn.active .badge{background:rgba(255,255,255,.2)}
.tab-content{display:none}
.tab-content.active{display:block}

/* ── Numbers Table ── */
.table-toolbar{display:flex;gap:10px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
.search-box{flex:1;min-width:180px;padding:8px 12px;background:#0f172a;border:1px solid #334155;border-radius:8px;color:#e2e8f0;font-size:13px;outline:none}
.search-box:focus{border-color:#3b82f6}
.filter-group{display:flex;gap:4px;flex-wrap:wrap}
.filter-btn{padding:6px 12px;border:1px solid #334155;border-radius:6px;font-size:11px;cursor:pointer;background:#1e293b;color:#64748b;transition:all .1s}
.filter-btn:hover{border-color:#475569;color:#e2e8f0}
.filter-btn.active{background:#3b82f6;border-color:#3b82f6;color:#fff}
.table-wrap{overflow-x:auto;border:1px solid #334155;border-radius:10px;background:#1e293b}
table.numbers{width:100%;border-collapse:collapse;font-size:13px}
table.numbers th{text-align:left;padding:10px 12px;background:#1e293b;color:#94a3b8;font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid #334155;white-space:nowrap;position:sticky;top:0;cursor:pointer;user-select:none}
table.numbers th:hover{color:#e2e8f0}
table.numbers td{padding:9px 12px;border-bottom:1px solid #1e293b;white-space:nowrap}
table.numbers tr:hover td{background:rgba(59,130,246,.05)}
table.numbers tr:last-child td{border-bottom:none}
table.numbers .num-cell{font-family:'SF Mono','Fira Code',monospace;font-size:14px;font-weight:600;color:#f8fafc;letter-spacing:1px}
table.numbers .planet{font-size:10px;color:#64748b;margin-left:4px}
.sync-badge{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:500}
.sync-badge.synced{background:#14532d;color:#4ade80}
.sync-badge.pending{background:#1e3a5f;color:#60a5fa}
.sync-badge.failed{background:#713f12;color:#fbbf24}
.sync-badge.permanent{background:#7f1d1d;color:#f87171}
.pagination{display:flex;align-items:center;justify-content:center;gap:8px;padding:12px;border-top:1px solid #334155}
.pagination .page-btn{padding:4px 10px;border:1px solid #334155;border-radius:6px;font-size:12px;cursor:pointer;background:#1e293b;color:#94a3b8;transition:all .1s}
.pagination .page-btn:hover{background:#334155;color:#e2e8f0}
.pagination .page-btn:disabled{opacity:.3;cursor:not-allowed}
.pagination .info{font-size:12px;color:#64748b}
.empty-state{text-align:center;padding:40px;color:#64748b;font-size:14px}
.empty-state .icon{font-size:36px;margin-bottom:8px}

/* ── Panels ── */
.panels-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:1000px){.panels-grid{grid-template-columns:1fr}}
.panel{background:#1e293b;border:1px solid #334155;border-radius:10px;overflow:hidden}
.panel-hd{padding:12px 16px;border-bottom:1px solid #334155;display:flex;justify-content:space-between;align-items:center}
.panel-hd h3{font-size:13px;color:#f8fafc;font-weight:600}
.panel-hd .badge{background:#334155;color:#94a3b8;padding:2px 8px;border-radius:6px;font-size:10px}
.panel-body{padding:12px 16px}

/* ── GAS Panel ── */
.gas-stats{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px}
.gas-stat{background:#0f172a;border-radius:8px;padding:10px;text-align:center}
.gas-stat .val{font-size:20px;font-weight:700;color:#f8fafc}
.gas-stat .lbl{font-size:10px;color:#64748b;margin-top:2px}
.gas-progress{background:#0f172a;border-radius:6px;height:8px;overflow:hidden;margin:8px 0}
.gas-progress .bar{height:100%;border-radius:6px;background:linear-gradient(90deg,#22c55e,#16a34a);transition:width .5s}
.gas-list{max-height:200px;overflow-y:auto}
#resultsTable tbody tr{transition:background .2s}
#resultsTable tbody tr:hover{background:rgba(59,130,246,.12)!important}
.gas-item{display:flex;justify-content:space-between;padding:4px 0;font-size:12px;border-bottom:1px solid #1e293b}
.gas-item:last-child{border-bottom:none}
.gas-item .num{font-family:monospace;color:#e2e8f0}
.gas-item .status{font-size:10px}
.gas-item .status.avail{color:#22c55e}
.gas-item .status.taken{color:#ef4444}

/* ── Logs ── */
.log-box{height:320px;overflow-y:auto;padding:8px;font-family:'SF Mono','Fira Code',monospace;font-size:11px}
.log-line{padding:4px 8px;border-radius:4px;margin-bottom:2px;display:flex;gap:8px;align-items:flex-start}
.log-line:hover{background:#334155}
.log-line .t{color:#64748b;white-space:nowrap;min-width:65px}
.log-line .lvl{padding:1px 5px;border-radius:3px;font-size:9px;font-weight:600;text-transform:uppercase;min-width:42px;text-align:center}
.log-line .lvl.info{background:#1e3a5f;color:#60a5fa}
.log-line .lvl.success{background:#14532d;color:#4ade80}
.log-line .lvl.warning{background:#713f12;color:#fbbf24}
.log-line .lvl.error{background:#7f1d1d;color:#f87171}
.log-line .msg{color:#cbd5e1;word-break:break-word}

/* ── Scrape Cycles ── */
.cycle-card{transition:border-color .2s}
.cycle-card:hover{border-color:#3b82f6!important}
.cyc-numbers{display:flex;flex-wrap:wrap;gap:4px}
.cyc-num{display:flex;align-items:center;gap:6px;padding:4px 8px;border-radius:4px;font-size:11px;min-width:0;flex:1 1 auto}
.cyc-num:hover{background:rgba(255,255,255,.03)}
.cyc-num.cyc-saved{background:rgba(34,197,94,.08)}
.cyc-num-val{font-family:'SF Mono','Fira Code',monospace;font-size:12px;font-weight:600;color:#e2e8f0;white-space:nowrap}
.cyc-num.cyc-saved .cyc-num-val{color:#4ade80;font-weight:700}
.cyc-num-meta{font-size:10px;color:#64748b;white-space:nowrap}
.cyc-badge{font-size:9px;font-weight:600;padding:1px 5px;border-radius:3px;white-space:nowrap}
.cyc-badge-saved{background:#14532d;color:#4ade80}
.cyc-badge-skip{background:#1e293b;color:#64748b}

/* ── Worker Cards ── */
.worker-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;padding:10px}
.worker-card{background:#0f172a;border-radius:8px;padding:10px;border:1px solid #334155;transition:all .2s}
.worker-card.worker-running{border-color:#1a4a3a}
.worker-card.worker-stopped{opacity:.6}
.worker-card:hover{border-color:#3b82f6}
.worker-hd{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.worker-id{font-size:12px;font-weight:700;color:#f8fafc}
.worker-status{font-size:10px;font-weight:600}
.worker-status.green{color:#4ade80}
.worker-status.red{color:#f87171}
.worker-metrics{display:flex;gap:10px;font-size:10px;color:#94a3b8;margin-bottom:5px}
.worker-metrics span{display:flex;align-items:center;gap:3px;cursor:default}
.worker-activity{font-size:11px;color:#e2e8f0;padding:3px 6px;background:#1e293b;border-radius:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.worker-activity-time{font-size:9px;color:#64748b;margin-top:3px;text-align:right}

/* ── Worker Filter Buttons ── */
.worker-filter{padding:3px 8px!important;font-size:10px!important;min-width:0!important;border-radius:4px!important}

/* ── Toast / Notification ── */
.toast{position:fixed;bottom:20px;right:20px;padding:12px 20px;border-radius:10px;font-size:13px;z-index:999;animation:slideIn .3s;max-width:350px}
.toast.success{background:#14532d;color:#4ade80;border:1px solid #22c55e}
.toast.error{background:#7f1d1d;color:#f87171;border:1px solid #ef4444}
.toast.info{background:#1e3a5f;color:#60a5fa;border:1px solid #3b82f6}
@keyframes slideIn{from{transform:translateY(20px);opacity:0}to{transform:translateY(0);opacity:1}}
</style>
</head>
<body>

<div class="header">
  <div class="left">
    <div class="dot"></div>
    <h1>VI Number Scraper</h1>
  </div>
  <div class="right">
    <span class="time" id="headerTime"></span>
    <a href="/logout" class="btn btn-ghost btn-sm">Logout</a>
  </div>
</div>

<div class="container">

  <!-- Stats -->
  <div class="stats-row" id="statsRow">
    <div class="stat-box green"><div class="num" id="statTotal">0</div><div class="lbl">Total Numbers</div></div>
    <div class="stat-box blue"><div class="num" id="statSynced">0</div><div class="lbl">Synced to GAS</div></div>
    <div class="stat-box yellow"><div class="num" id="statPending">0</div><div class="lbl">Pending Sync</div></div>
    <div class="stat-box red"><div class="num" id="statFailed">0</div><div class="lbl">Sync Failed</div></div>
    <div class="stat-box purple"><div class="num" id="statGAS">0</div><div class="lbl">In Google Sheet</div></div>
    <div class="stat-box"><div class="num" id="statFound">0</div><div class="lbl">Session Found</div></div>
    <div class="stat-box"><div class="num" id="statCycles">0</div><div class="lbl">Scrape Cycles</div></div>
    <div class="stat-box"><div class="num" id="statErrors" style="color:#ef4444">0</div><div class="lbl">Errors</div></div>
  </div>

  <!-- Root Breakdown -->
  <div class="root-grid" id="rootGrid"></div>

  <!-- Tabs -->
  <div class="tabs" id="tabBar">
    <button class="tab-btn active" data-tab="numbers" onclick="switchTab('numbers')">📊 Numbers <span class="badge" id="tabCountNumbers">0</span></button>
    <button class="tab-btn" data-tab="sync" onclick="switchTab('sync')">☁️ GAS Sync</button>
    <button class="tab-btn" data-tab="results" onclick="switchTab('results')">🔍 Scrape Results <span class="badge" id="tabCountResults">0</span></button>
    <button class="tab-btn" data-tab="logs" onclick="switchTab('logs')">📋 Live Logs <span class="badge" id="tabCountLogs">0</span></button>
  </div>

  <!-- ════ Tab: Numbers ════ -->
  <div class="tab-content active" id="tab-numbers">
    <div class="table-toolbar">
      <input class="search-box" id="searchBox" placeholder="Search number..." oninput="debouncedSearch()">
      <div class="filter-group" id="filterGroup">
        <button class="filter-btn active" data-filter="all" onclick="setFilter('all')">All</button>
        <button class="filter-btn" data-filter="pending" onclick="setFilter('pending')">⏳ Pending</button>
        <button class="filter-btn" data-filter="uploaded" onclick="setFilter('uploaded')">✅ Synced</button>
        <button class="filter-btn" data-filter="failed" onclick="setFilter('failed')">⚠️ Failed</button>
        <button class="filter-btn" data-filter="permanent" onclick="setFilter('permanent')">❌ Stuck</button>
      </div>
    </div>
    <div class="table-wrap">
      <table class="numbers">
        <thead><tr>
          <th onclick="sortBy('number')"># Number</th>
          <th onclick="sortBy('root')">Root</th>
          <th onclick="sortBy('compound')">Compound</th>
          <th onclick="sortBy('priority')">Priority</th>
          <th onclick="sortBy('uploaded')">Sync Status</th>
          <th onclick="sortBy('found_at')">Found At</th>
          <th>Actions</th>
        </tr></thead>
        <tbody id="numbersBody">
          <tr><td colspan="7"><div class="empty-state"><div class="icon">📭</div>Loading numbers...</div></td></tr>
        </tbody>
      </table>
      <div class="pagination" id="pagination">
        <button class="page-btn" id="prevPage" onclick="changePage(-1)" disabled>← Prev</button>
        <span class="info" id="pageInfo">Page 1</span>
        <button class="page-btn" id="nextPage" onclick="changePage(1)" disabled>Next →</button>
      </div>
    </div>
  </div>

  <!-- ════ Tab: GAS Sync ════ -->
  <div class="tab-content" id="tab-sync">
    <div class="panels-grid">
      <div class="panel">
        <div class="panel-hd"><h3>☁️ Google Sheet Status</h3><span class="badge" id="gasStatusBadge">checking...</span></div>
        <div class="panel-body">
          <div class="gas-stats">
            <div class="gas-stat"><div class="val" id="gasCount">0</div><div class="lbl">Numbers in Sheet</div></div>
            <div class="gas-stat"><div class="val" id="gasLocalCount">0</div><div class="lbl">Numbers Local</div></div>
          </div>
          <div class="gas-stats">
            <div class="gas-stat"><div class="val" id="gasSynced">0</div><div class="lbl">Synced ✓</div></div>
            <div class="gas-stat"><div class="val" id="gasMissing" style="color:#f59e0b">0</div><div class="lbl">Not in Sheet</div></div>
          </div>
          <div id="gasProgressWrap">
            <div style="font-size:11px;color:#64748b;margin-bottom:4px">Sync Progress</div>
            <div class="gas-progress"><div class="bar" id="gasProgressBar" style="width:0%"></div></div>
          </div>
          <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
            <button class="btn btn-primary btn-sm" onclick="refreshGasData()">🔄 Refresh GAS</button>
            <button class="btn btn-ghost btn-sm" onclick="resetFailedSync()">🔄 Reset Failed</button>
            <button class="btn btn-success btn-sm" onclick="pullFromSheet()" id="pullFromSheetBtn">📥 Pull from Sheet</button>
          </div>
          <div id="pullFromSheetResult" style="margin-top:8px;font-size:13px;display:none"></div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-hd"><h3>📋 Recent GAS Numbers</h3><span class="badge" id="gasListCount">0</span></div>
        <div class="panel-body">
          <div class="gas-list" id="gasList">
            <div class="empty-state"><div class="icon">☁️</div><div>Loading GAS data...</div></div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ════ Tab: Scrape Results ════ -->
  <div class="tab-content" id="tab-results">
    <div class="panel">
      <div class="panel-hd">
        <h3>🔍 Per-Search Results — <span style="color:#22c55e">🟢 Selected</span> / <span style="color:#64748b">⚪ Skipped</span></h3>
        <span class="badge" id="resultsCountBadge">0 cycles</span>
      </div>
      <div class="panel-body" style="padding:0">
        <div id="cyclesWrap" style="max-height:600px;overflow-y:auto">
          <div class="empty-state" id="cyclesEmpty" style="padding:40px"><div class="icon">🔍</div><div>No cycles yet. Workers are scanning...</div></div>
          <div id="cyclesContainer" style="display:none"></div>
        </div>
      </div>
    </div>
  </div>

  <!-- ════ Tab: Live Logs ════ -->
  <div class="tab-content" id="tab-logs">
    <!-- Worker Activity Panel -->
    <div class="panel" style="margin-bottom:16px">
      <div class="panel-hd"><h3>🤖 Worker Activity</h3><span class="badge" id="workerCountBadge">0 / 0 active</span></div>
      <div class="worker-grid" id="workerGrid">
        <div class="empty-state"><div class="icon">⏳</div><div>Loading worker status...</div></div>
      </div>
    </div>

    <!-- Worker Filter -->
    <div class="panel">
      <div class="panel-hd">
        <h3>📋 Activity Log</h3>
        <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
          <button class="tab-btn worker-filter active" data-worker="all" onclick="setWorkerFilter('all')">All</button>
          <span id="workerFilterButtons"></span>
          <span class="badge" id="logCountBadge" style="margin-left:8px">0 entries</span>
        </div>
      </div>
      <div class="log-box" id="logBox"><div class="empty-state"><div class="icon">📭</div><div>No logs yet. Waiting for scraper activity...</div></div></div>
    </div>
  </div>

</div>

<script>
// ── State ──
const STATE = {
  currentTab: 'numbers',
  filter: 'all',
  workerFilter: 'all',
  search: '',
  sortField: 'found_at',
  sortDir: 'DESC',
  page: 0,
  pageSize: 25,
  totalFiltered: 0,
  total: 0,
  numbers: [],
  gasData: null,
  logs: [],
  statsInterval: null,
  numbersInterval: null,
  logsInterval: null,
};

const PLANET_MAP = {1:'Sun',2:'Moon',3:'Jupiter',4:'Rahu',5:'Mercury',6:'Venus',7:'Ketu',8:'Saturn',9:'Mars'};

// ── Tab Switching ──
function switchTab(tab) {
  STATE.currentTab = tab;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.toggle('active', c.id === 'tab-' + tab));
  if (tab === 'numbers') fetchNumbers();
  if (tab === 'sync') fetchGasData();
  if (tab === 'results') fetchScrapeResults();
  if (tab === 'logs') { fetchLogs(); fetchWorkers(); }
}

// ── Worker Filter ──
function setWorkerFilter(workerId) {
  STATE.workerFilter = workerId;
  document.querySelectorAll('.worker-filter').forEach(b => b.classList.toggle('active', b.dataset.worker === workerId));
  fetchLogs();
}

// ── Fetch Workers —─
async function fetchWorkers() {
  try {
    const res = await fetch('/workers');
    const data = await res.json();
    const workers = data.workers || [];
    const active = workers.filter(w => w.is_running).length;
    document.getElementById('workerCountBadge').textContent = `${active} / ${workers.length} active`;

    // Render worker cards
    const grid = document.getElementById('workerGrid');
    grid.innerHTML = workers.map(w => {
      const uptime = w.uptime ? Math.floor(w.uptime / 60) + 'm' : '—';
      const lastAct = w.last_activity || '⏳ Idle';
      const actTime = w.last_activity_time ? new Date(w.last_activity_time * 1000).toLocaleTimeString() : '';
      const statusClass = w.is_running ? 'worker-running' : 'worker-stopped';
      return `<div class="worker-card ${statusClass}">
        <div class="worker-hd">
          <span class="worker-id">#${w.worker_id}</span>
          <span class="worker-status ${w.is_running ? 'green' : 'red'}">${w.is_running ? '● Running' : '○ Stopped'}</span>
        </div>
        <div class="worker-metrics">
          <span title="Cycles">🔄 ${w.cycles_completed || 0}</span>
          <span title="Numbers found">🎯 ${w.numbers_found || 0}</span>
          <span title="Errors">❌ ${w.errors || 0}</span>
          <span title="Uptime">⏱ ${uptime}</span>
        </div>
        <div class="worker-activity">${lastAct}</div>
        <div class="worker-activity-time">${actTime}</div>
      </div>`;
    }).join('');

    // Update filter buttons
    const fb = document.getElementById('workerFilterButtons');
    fb.innerHTML = workers.map(w =>
      `<button class="tab-btn worker-filter ${STATE.workerFilter === String(w.worker_id) ? 'active' : ''}" ` +
      `data-worker="${w.worker_id}" onclick="setWorkerFilter('${w.worker_id}')">#${w.worker_id}</button>`
    ).join('');

  } catch(e) { console.error('Workers error:', e); }
}

// ── Filter & Search ──
function setFilter(f) {
  STATE.filter = f;
  STATE.page = 0;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.toggle('active', b.dataset.filter === f));
  fetchNumbers();
}

let searchTimer;
function debouncedSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    STATE.search = document.getElementById('searchBox').value;
    STATE.page = 0;
    fetchNumbers();
  }, 300);
}

function sortBy(field) {
  if (STATE.sortField === field) STATE.sortDir = STATE.sortDir === 'DESC' ? 'ASC' : 'DESC';
  else { STATE.sortField = field; STATE.sortDir = 'DESC'; }
  fetchNumbers();
}

function changePage(delta) {
  STATE.page += delta;
  if (STATE.page < 0) STATE.page = 0;
  fetchNumbers();
}

// ── Fetch Numbers ──
async function fetchNumbers() {
  try {
    const params = new URLSearchParams({
      limit: STATE.pageSize,
      offset: STATE.page * STATE.pageSize,
    });
    if (STATE.search) params.set('search', STATE.search);
    if (STATE.filter && STATE.filter !== 'all') params.set('status_filter', STATE.filter);

    const res = await fetch(`/api/dashboard/numbers?${params}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);

    STATE.numbers = data.numbers || [];
    STATE.total = data.total || 0;
    STATE.totalFiltered = data.filtered_total || 0;

    renderNumbers();
    renderPagination();
    document.getElementById('tabCountNumbers').textContent = STATE.total;
  } catch(e) {
    console.error('Numbers fetch error:', e);
  }
}

function renderNumbers() {
  const tbody = document.getElementById('numbersBody');
  if (STATE.numbers.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7"><div class="empty-state"><div class="icon">📭</div><div>No numbers found</div></div></td></tr>';
    return;
  }

  tbody.innerHTML = STATE.numbers.map(n => {
    const planet = PLANET_MAP[n.root] || '?';
    const syncClass = n.sync_status || 'pending';
    const syncLabel = n.sync_label || '⏳ Pending';
    const found = n.found_at_display || '-';
    return `<tr>
      <td><span class="num-cell">${n.number}</span></td>
      <td>${n.root} <span class="planet">${planet}</span></td>
      <td>${n.compound}</td>
      <td>${n.priority}</td>
      <td><span class="sync-badge ${syncClass}">${syncLabel}</span></td>
      <td style="font-size:12px;color:#64748b">${found}</td>
      <td>
        <button class="btn btn-ghost btn-sm" onclick="checkAvail('${n.number}')" title="Check availability on VI">🔍 Check</button>
        <button class="btn btn-ghost btn-sm" onclick="retrySync('${n.number}')" title="Retry GAS sync" ${n.uploaded === 1 ? 'disabled' : ''}>🔄 Retry</button>
      </td>
    </tr>`;
  }).join('');
}

function renderPagination() {
  const totalPages = Math.max(1, Math.ceil(STATE.totalFiltered / STATE.pageSize));
  const currentPage = STATE.page + 1;
  document.getElementById('pageInfo').textContent = `Page ${currentPage} of ${totalPages} (${STATE.totalFiltered} total)`;
  document.getElementById('prevPage').disabled = STATE.page <= 0;
  document.getElementById('nextPage').disabled = STATE.page >= totalPages - 1;
}

// ── Fetch Stats ──
async function fetchStats() {
  try {
    const [statsRes, syncRes] = await Promise.all([
      fetch('/api/dashboard/stats'),
      fetch('/sync/status'),
    ]);
    const stats = (await statsRes.json()).stats;
    const sync = await syncRes.json();

    document.getElementById('statFound').textContent = (stats.total_found || 0).toLocaleString();
    document.getElementById('statCycles').textContent = stats.scrape_cycles || 0;
    document.getElementById('statErrors').textContent = stats.total_errors || 0;
    document.getElementById('statTotal').textContent = (sync.total || 0).toLocaleString();
    document.getElementById('statSynced').textContent = (sync.uploaded || 0).toLocaleString();
    document.getElementById('statPending').textContent = (sync.pending || 0).toLocaleString();
    document.getElementById('statFailed').textContent = ((sync.failed || 0) + (sync.permanently_failed || 0)).toLocaleString();
    document.getElementById('statGAS').textContent = (sync.uploaded || 0).toLocaleString();

    // Update tab badge
    document.getElementById('tabCountLogs').textContent = stats.total_found || 0;

    // Fetch root breakdown alongside stats
    fetchRootBreakdown();

  } catch(e) { console.error('Stats error:', e); }
}

// ── Root Breakdown ──
const ROOT_COLORS = {
  1: {bg:'rgba(59,130,246,.15)', digit:'#3b82f6', bar:'#3b82f6', planet:'Sun'},
  2: {bg:'rgba(192,132,252,.15)', digit:'#c084fc', bar:'#c084fc', planet:'Moon'},
  3: {bg:'rgba(34,197,94,.15)', digit:'#22c55e', bar:'#22c55e', planet:'Jupiter'},
  4: {bg:'rgba(251,146,60,.15)', digit:'#fb923c', bar:'#fb923c', planet:'Rahu'},
  5: {bg:'rgba(250,204,21,.15)', digit:'#eab308', bar:'#eab308', planet:'Mercury'},
  6: {bg:'rgba(236,72,153,.15)', digit:'#ec4899', bar:'#ec4899', planet:'Venus'},
  7: {bg:'rgba(165,180,252,.15)', digit:'#a5b4fc', bar:'#a5b4fc', planet:'Ketu'},
  8: {bg:'rgba(239,68,68,.15)', digit:'#ef4444', bar:'#ef4444', planet:'Saturn'},
  9: {bg:'rgba(132,204,22,.15)', digit:'#84cc16', bar:'#84cc16', planet:'Mars'},
};

async function fetchRootBreakdown() {
  try {
    const res = await fetch('/api/dashboard/root-breakdown');
    const data = await res.json();
    const rows = data.breakdown || [];
    const grid = document.getElementById('rootGrid');
    if (!rows.length) { grid.innerHTML = ''; return; }

    grid.innerHTML = rows.map(r => {
      const root = r.root;
      const total = r.total || 0;
      const uploaded = r.uploaded || 0;
      const pending = r.pending || 0;
      const colors = ROOT_COLORS[root] || {bg:'#1e293b', digit:'#94a3b8', bar:'#94a3b8', planet:'?'};
      const pct = total > 0 ? (uploaded / total * 100) : 0;
      return `<div class="root-card" style="background:${colors.bg};border:1px solid ${colors.digit}33">
        <div class="root-hdr">
          <div class="root-digit" style="background:${colors.digit}22;color:${colors.digit}">${root}</div>
          <div>
            <div style="font-size:18px;font-weight:700;color:${colors.digit}">${total.toLocaleString()} <span style="font-size:12px;font-weight:400;color:#94a3b8">numbers</span></div>
            <div class="root-name">${colors.planet}</div>
          </div>
        </div>
        <div class="root-bars">
          <div class="root-bar-wrap">
            <div class="root-bar-label"><span>✅ Saved</span><span>${uploaded.toLocaleString()}</span></div>
            <div class="root-bar-track"><div class="root-bar-fill" style="width:${pct}%;background:${colors.bar}"></div></div>
          </div>
        </div>
        ${pending > 0 ? `<div class="root-totals"><span>⏳ Pending: ${pending}</span></div>` : ''}
      </div>`;
    }).join('');
  } catch(e) { console.error('Root breakdown error:', e); }
}

// ── Fetch Logs ──
async function fetchLogs() {
  try {
    const res = await fetch('/api/dashboard/logs?limit=150');
    const data = await res.json();
    STATE.logs = data.logs || [];
    const box = document.getElementById('logBox');

    // Filter by worker if active
    const wf = STATE.workerFilter;
    const filtered = wf === 'all'
      ? STATE.logs
      : STATE.logs.filter(log => {
          // Match "Worker #N" or "Worker N" or "worker_id":"N" in message
          const msg = (log.message || '') + (log.worker_id || '');
          return msg.includes(`#${wf}`) || msg.includes(`Worker ${wf}`);
        });

    if (filtered.length === 0) {
      box.innerHTML = '<div class="empty-state"><div class="icon">📭</div><div>No logs for this worker yet...</div></div>';
      return;
    }

    document.getElementById('logCountBadge').textContent = data.total + ' entries';

    const html = filtered.slice().reverse().map(log => {
      const time = new Date(log.timestamp).toLocaleTimeString();
      const lvl = log.level === 'success' ? 'success' : log.level;
      return `<div class="log-line"><span class="t">${time}</span><span class="lvl ${lvl}">${log.level}</span><span class="msg">${log.message}</span></div>`;
    }).join('');
    box.innerHTML = html;
    box.scrollTop = 0;
  } catch(e) { console.error('Logs error:', e); }
}

// ── Fetch GAS Data ──
async function fetchGasData() {
  try {
    const res = await fetch('/api/dashboard/gas-data');
    const data = await res.json();
    STATE.gasData = data;

    const badge = document.getElementById('gasStatusBadge');
    if (!data.configured) {
      badge.textContent = '⚠️ Not configured';
      badge.style.background = '#713f12';
      badge.style.color = '#fbbf24';
      return;
    }
    if (data.error) {
      badge.textContent = '❌ Error';
      badge.style.background = '#7f1d1d';
      badge.style.color = '#f87171';
      return;
    }

    badge.textContent = '✅ Connected';
    badge.style.background = '#14532d';
    badge.style.color = '#4ade80';

    document.getElementById('gasCount').textContent = data.gas_count || 0;
    document.getElementById('gasLocalCount').textContent = data.local_count || 0;
    
    const synced = data.gas_count || 0;
    const local = data.local_count || 0;
    const missing = data.not_in_gas || 0;
    document.getElementById('gasSynced').textContent = synced;
    document.getElementById('gasMissing').textContent = missing;

    // Progress bar
    const pct = local > 0 ? Math.min(100, Math.round((synced / local) * 100)) : 0;
    document.getElementById('gasProgressBar').style.width = pct + '%';

    // Recent GAS numbers
    const gasList = document.getElementById('gasList');
    const nums = data.gas_numbers || [];
    document.getElementById('gasListCount').textContent = nums.length;

    if (nums.length === 0) {
      gasList.innerHTML = '<div class="empty-state"><div class="icon">☁️</div><div>No data in Google Sheet</div></div>';
      return;
    }

    gasList.innerHTML = nums.slice(0, 30).map(n => {
      const status = n.status === 'available' ? 'avail' : 'taken';
      return `<div class="gas-item"><span class="num">${n.number}</span><span class="status ${status}">${n.status || '-'}</span></div>`;
    }).join('');

  } catch(e) { console.error('GAS data error:', e); }
}

function refreshGasData() {
  fetchGasData();
  showToast('Refreshing GAS data...', 'info');
}

// ── Fetch Scrape Cycles ──
async function fetchScrapeResults() {
  try {
    const res = await fetch('/api/dashboard/scrape-cycles?limit=20');
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail);
    
    const cycles = data.cycles || [];
    document.getElementById('tabCountResults').textContent = cycles.length;
    document.getElementById('resultsCountBadge').textContent = cycles.length + ' cycles';
    
    const container = document.getElementById('cyclesContainer');
    const empty = document.getElementById('cyclesEmpty');
    
    if (cycles.length === 0) {
      container.style.display = 'none';
      empty.style.display = 'block';
      return;
    }
    
    container.style.display = '';
    empty.style.display = 'none';
    
    // Render cycles in reverse order (newest first)
    container.innerHTML = cycles.slice().reverse().map(c => {
      const time = new Date(c.timestamp * 1000).toLocaleTimeString();
      const date = new Date(c.timestamp * 1000).toLocaleDateString();
      const pct = c.raw_count > 0 ? Math.round(c.saved_count / c.raw_count * 100) : 0;
      const hasSaved = c.saved_count > 0;
      
      // Render each number in this cycle
      const numbersHtml = c.numbers.map(n => {
        const isSaved = n.saved;
        const cls = isSaved ? 'cyc-saved' : 'cyc-skipped';
        const lbl = isSaved ? '🟢 SELECTED' : '⚪ Skipped';
        const bg = isSaved ? 'style="background:rgba(34,197,94,0.10);border-left:3px solid #22c55e"' : '';
        return `<div class="cyc-num ${cls}" ${bg}>
          <span class="cyc-num-val">${n.number}</span>
          <span class="cyc-num-meta">Root ${n.root} / ${n.compound}</span>
          <span class="cyc-badge ${isSaved ? 'cyc-badge-saved' : 'cyc-badge-skip'}">${lbl}</span>
        </div>`;
      }).join('');
      
      return `<div class="cycle-card" style="border:1px solid ${hasSaved ? '#1a4a3a' : '#334155'};border-radius:8px;margin-bottom:10px;overflow:hidden">
        <div class="cycle-hd" style="display:flex;justify-content:space-between;align-items:center;padding:10px 14px;background:#0f172a;border-bottom:1px solid #1e293b">
          <div style="display:flex;align-items:center;gap:10px">
            <span style="font-size:12px;font-weight:700;color:#f8fafc">🔁 Cycle #${c.cycle_id}</span>
            <span style="font-size:10px;color:#64748b">Worker #${c.worker_id}</span>
          </div>
          <div style="display:flex;align-items:center;gap:10px;font-size:11px">
            <span style="color:#94a3b8">📄 ${c.raw_count} numbers</span>
            ${hasSaved ? `<span style="color:#4ade80">✅ ${c.saved_count} selected</span>` : `<span style="color:#64748b">0 selected</span>`}
            <span style="color:#64748b">${date} ${time}</span>
          </div>
        </div>
        <div class="cyc-numbers" style="padding:6px 10px;background:#1e293b">
          ${numbersHtml}
        </div>
      </div>`;
    }).join('');
    
  } catch(e) { console.error('Scrape cycles error:', e); }
}

// ── Actions ──
async function checkAvail(number) {
  try {
    const res = await fetch(`/check-availability/${number}`);
    if (!res.ok) throw new Error((await res.json()).detail);
    const data = await res.json();
    if (data.available) {
      showToast(`✅ ${number} is AVAILABLE on VI`, 'success');
    } else {
      showToast(`❌ ${number} is NOT available on VI`, 'error');
    }
  } catch(e) {
    showToast(`⚠️ Check failed: ${e.message}`, 'error');
  }
}

async function retrySync(number) {
  try {
    // Reset fail count for this number so sync_loop picks it up
    const res = await fetch('/sync/reset-failed', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({number: number}),
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`🔄 ${number} queued for retry`, 'success');
      fetchNumbers();
    } else {
      showToast(`⚠️ ${data.detail || 'Failed'}`, 'error');
    }
  } catch(e) {
    showToast(`⚠️ Error: ${e.message}`, 'error');
  }
}

async function resetFailedSync() {
  try {
    const res = await fetch('/sync/reset-failed', { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      showToast(`✅ Reset ${data.reset} failed records`, 'success');
      fetchNumbers();
      fetchGasData();
    } else {
      showToast(`⚠️ ${data.detail || 'Failed'}`, 'error');
    }
  } catch(e) {
    showToast(`⚠️ Error: ${e.message}`, 'error');
  }
}

// ── Pull from Sheet ──
async function pullFromSheet() {
  const btn = document.getElementById('pullFromSheetBtn');
  const resultDiv = document.getElementById('pullFromSheetResult');
  btn.disabled = true;
  btn.textContent = '⏳ Pulling...';
  resultDiv.style.display = 'block';
  resultDiv.innerHTML = '<span style="color:#fbbf24">⏳ Fetching numbers from Google Sheet...</span>';
  try {
    const res = await fetch('/sync/pull-from-sheet', { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      const msg = data.imported > 0
        ? `✅ Pulled ${data.imported} NEW numbers from sheet! (${data.skipped_existing} already existed)`
        : `ℹ️ ${data.skipped_existing} numbers already in local DB. Nothing new to import.`;
      resultDiv.innerHTML = `<span style="color:#22c55e">${msg}</span>`;
      showToast(msg, 'success');
      fetchNumbers();
      fetchGasData();
    } else {
      resultDiv.innerHTML = `<span style="color:#ef4444">⚠️ ${data.detail || 'Failed'}</span>`;
      showToast(`⚠️ ${data.detail || 'Pull failed'}`, 'error');
    }
  } catch(e) {
    resultDiv.innerHTML = `<span style="color:#ef4444">⚠️ Error: ${e.message}</span>`;
    showToast(`⚠️ Error: ${e.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '📥 Pull from Sheet';
  }
}

// ── Toast ──
function showToast(msg, type = 'info') {
  const existing = document.querySelector('.toast');
  if (existing) existing.remove();
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity .3s'; setTimeout(() => t.remove(), 300); }, 3000);
}

// ── Auto-refresh ──
function startAutoRefresh() {
  // Stats: every 5s
  STATE.statsInterval = setInterval(fetchStats, 5000);
  // Numbers: every 15s (if on numbers tab)
  STATE.numbersInterval = setInterval(() => {
    if (STATE.currentTab === 'numbers') fetchNumbers();
  }, 15000);
  // Logs + Workers: every 8s (if on logs tab)
  STATE.logsInterval = setInterval(() => {
    if (STATE.currentTab === 'logs') { fetchLogs(); fetchWorkers(); }
  }, 8000);
  // GAS: every 30s
  setInterval(() => {
    if (STATE.currentTab === 'sync') fetchGasData();
  }, 30000);
  // Scrape results: every 10s
  setInterval(() => {
    if (STATE.currentTab === 'results') fetchScrapeResults();
  }, 10000);
}

// ── Clock ──
function updateClock() {
  document.getElementById('headerTime').textContent = new Date().toLocaleString();
}
setInterval(updateClock, 1000);
updateClock();

// ── Init ──
startAutoRefresh();
fetchStats();
fetchNumbers();
fetchGasData();
fetchLogs();
fetchScrapeResults();
</script>
</body>
</html>"""
