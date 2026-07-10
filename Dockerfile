# VI Number Scraper — Hugging Face Space
# Auto-scrapes VI numbers 24/7 with Playwright + Chromium

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Playwright/Chromium
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    ca-certificates \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxcb1 \
    libxkbcommon0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium only, smaller)
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy application code
COPY . .

# Create needed directories
RUN mkdir -p data backups logs cookies

# Hugging Face Spaces injects PORT env var — default 7860
ENV PORT=7860
ENV HEADLESS=true
ENV AUTO_START_WORKERS=true
ENV NUM_WORKERS=12
ENV MAX_WORKERS=24

# Expose port
EXPOSE 7860

# Start the app — uses PORT env var (HF Spaces injects this)
CMD ["sh", "-c", "python3 -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
