FROM mcr.microsoft.com/playwright/python:v1.57.0-noble

WORKDIR /app

# Install xvfb and dbus for virtual display (needed for headed Chromium)
RUN apt-get update && apt-get install -y xvfb dbus dbus-x11 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# Set up virtual display environment
ENV DISPLAY=:99

# Create startup script that starts Xvfb and then gunicorn
RUN echo '#!/bin/bash\n\
Xvfb :99 -screen 0 1280x800x24 &\n\
sleep 1\n\
exec gunicorn api:app --bind 0.0.0.0:8080 --timeout 120\n\
' > /app/start.sh && chmod +x /app/start.sh

CMD ["/app/start.sh"]