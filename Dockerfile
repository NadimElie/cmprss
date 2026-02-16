FROM python:3.11-slim-bookworm

# NIST State Containment: Prevent Python from writing unpredictable .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
# Enforce explicit stderr/stdout logging without buffering
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Hardened OS Dependencies: Added libmagic1 for strict MIME validation
RUN apt-get update && apt-get install -y --no-install-recommends \
    ghostscript \
    gsfonts \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "main:app"]
