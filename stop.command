#!/bin/bash
# ═══════════════════════════════════════════
# VI Number Scraper — Stop
# ═══════════════════════════════════════════
echo "🛑 Stopping VI Number Scraper..."
PID=$(lsof -ti:7861 2>/dev/null)
if [ -n "$PID" ]; then
    kill -15 $PID 2>/dev/null
    sleep 2
    kill -9 $PID 2>/dev/null
    echo "✅ Stopped (PID: $PID)"
else
    echo "⚠️  Not running"
fi
