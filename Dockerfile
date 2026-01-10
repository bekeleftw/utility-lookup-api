FROM mcr.microsoft.com/playwright/python:v1.57.0-noble

WORKDIR /app

# Install xvfb for virtual display (needed for headed Chromium)
RUN apt-get update && apt-get install -y xvfb && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# Use xvfb-run to provide virtual display for headed browser
CMD ["xvfb-run", "--auto-servernum", "--server-args=-screen 0 1280x800x24", "gunicorn", "api:app", "--bind", "0.0.0.0:8080", "--timeout", "120"]