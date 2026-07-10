#!/bin/bash
# ═══════════════════════════════════════════
# VI Number Scraper — Start (Standalone CLI)
# ═══════════════════════════════════════════
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "🚀 VI Number Scraper"
echo "━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "❌ Python 3 not found. Install it from https://python.org"
    exit 1
fi

# Install deps if needed (skip if already done)
if [ ! -f ".installed" ]; then
    echo "📦 Installing dependencies..."
    pip3 install -q -r requirements.txt 2>&1 | tail -3
    python3 -m playwright install chromium 2>/dev/null
    touch ".installed"
    echo "✅ Dependencies installed"
fi

echo "🌐 Dashboard: http://localhost:${PORT:-7861}/dashboard"
echo "🔑 Login: hankith / arvind@2012"
echo "━━━━━━━━━━━━━━━━━━━━"
echo ""

python3 -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7861}
