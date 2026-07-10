#!/bin/bash
# ═══════════════════════════════════════════
# VI Number Scraper — Start (Standalone)
# ═══════════════════════════════════════════
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Activate venv if exists, else create
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --quiet -r requirements.txt
    playwright install chromium 2>/dev/null
else
    source venv/bin/activate
fi

echo "🚀 Starting VI Number Scraper..."
echo "   Dashboard: http://localhost:${PORT:-7861}/dashboard"
echo "   Login: hankith / arvind@2012"
echo ""

python3 -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7861}
