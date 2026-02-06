FROM python:3.11-slim

# CRITICAL: Force English locale (C) for correct decimal math
# This fixes the bug where Ghostscript writes commas (0,5) instead of dots (0.5)
ENV LC_ALL=C

# Install Ghostscript + Basic Fonts
RUN apt-get update && apt-get install -y \
    ghostscript \
    gsfonts \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
