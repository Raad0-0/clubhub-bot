# Deployment Guide

This document describes how to deploy ClubHub in production environments.

---

## 1. System Requirements
- Python 3.10+ (tested on Python 3.10, 3.11, 3.12, 3.13, 3.14)
- SQLite 3.30+
- Reliable 24/7 server (VPS, Raspberry Pi, Docker host, systemd on Linux, or Windows Service)

---

## 2. Linux Deployment via systemd

1. Clone and set up the bot directory:
   ```bash
   sudo useradd -m -s /bin/bash clubhub
   sudo mkdir -p /opt/clubhub
   sudo chown clubhub:clubhub /opt/clubhub
   sudo -u clubhub git clone https://github.com/your-org/clubhub.git /opt/clubhub
   cd /opt/clubhub

   sudo -u clubhub python3 -m venv venv
   sudo -u clubhub ./venv/bin/pip install -r requirements.txt
   ```

2. Copy configuration:
   ```bash
   sudo -u clubhub cp .env.example .env
   sudo -u clubhub cp config.example.yaml config.yaml
   # Edit .env and config.yaml with production settings
   ```

3. Create a systemd service file `/etc/systemd/system/clubhub.service`:
   ```ini
   [Unit]
   Description=ClubHub Discord Bot
   After=network.target

   [Service]
   Type=simple
   User=clubhub
   WorkingDirectory=/opt/clubhub
   ExecStart=/opt/clubhub/venv/bin/python -m clubhub.main
   Restart=always
   RestartSec=10
   Environment=PYTHONUNBUFFERED=1

   [Install]
   WantedBy=multi-user.target
   ```

4. Enable and start:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now clubhub
   sudo systemctl status clubhub
   ```

---

## 3. Docker Deployment

A minimal `Dockerfile` is provided for containerized deployments:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-m", "clubhub.main"]
```

Build and run:
```bash
docker build -t clubhub .
docker run -d --name clubhub \
  --restart unless-stopped \
  -v $(pwd)/data:/app/data \
  --env-file .env \
  clubhub
```

---

## 4. Operational Backups
Operational data is stored in the SQLite database (`clubhub.db` or configured path).
Perform automated daily backups using standard SQLite backup or cron:
```bash
sqlite3 clubhub.db ".backup 'backups/clubhub_$(date +%F).db'"
```
In the event of a bot crash or host reboot, ClubHub automatically re-registers persistent buttons and runs a reconciliation pass to grant overdue tickets a configurable grace period before taking cleanup action.
