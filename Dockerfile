FROM mcr.microsoft.com/playwright/python:v1.57.0-noble

WORKDIR /app

# Install xvfb and dbus for virtual display (needed for headed Chromium)
RUN apt-get update && apt-get install -y xvfb dbus dbus-x11 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Cache buster - change this to force rebuild
ARG CACHE_BUST=2026-01-20-v11-perf
RUN echo "Cache bust: $CACHE_BUST"

COPY . .

EXPOSE 8080

# Set up virtual display environment
ENV DISPLAY=:99

# Create startup script that starts Xvfb and then gunicorn
COPY <<EOF /app/start.sh
#!/bin/bash
echo "Starting Xvfb on display :99..."
Xvfb :99 -screen 0 1280x800x24 &
sleep 2
echo "Xvfb started, launching gunicorn..."
exec gunicorn api:app --bind 0.0.0.0:8080 --timeout 120
EOF
RUN chmod +x /app/start.sh

CMD ["/bin/bash", "/app/start.sh"]