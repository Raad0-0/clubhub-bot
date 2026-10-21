# Deployment Guide

This document describes how to deploy ClubHub in production environments.

---

## 1. System Requirements
- Python 3.10+ (tested on Python 3.10, 3.11, 3.12, 3.13, 3.14)
- SQLite 3.30+
- Reliable 24/7 server (VPS, Raspberry Pi, Docker host, systemd on Linux, or Windows Service)

---

## 2. Google Cloud Always-Free VM (Recommended 24/7 Hosting)

Google Cloud offers an **Always Free** tier that includes **1 free `e2-micro` virtual machine** every month with persistent disk and 24/7 uptime.

### Step 1: Create the Free VM
1. Go to [Google Cloud Console](https://console.cloud.google.com/) -> **Compute Engine** -> **VM instances** -> **Create Instance**.
2. Configure with Always Free eligible settings:
   - **Region**: `us-central1` (Iowa), `us-east1` (South Carolina), or `us-west1` (Oregon).
   - **Series**: `E2`
   - **Machine type**: `e2-micro` (2 vCPU, 1 GB memory).
   - **Boot disk**: Change to **Ubuntu 22.04 LTS** or **24.04 LTS** (Standard Persistent Disk, up to 30 GB).
3. Click **Create**.

### Step 2: One-Command Deployment
1. Click the **SSH** button next to your VM instance to open the in-browser terminal.
2. Run this command:
   ```bash
   git clone https://github.com/Raad0-0/clubhub-bot.git
   cd clubhub-bot
   bash scripts/setup_gcp.sh
   ```
3. When prompted, enter your `DISCORD_TOKEN`.
4. Done! The bot will be installed, configured as a 24/7 `systemd` service, and started immediately.

---

## 3. Free Web Service Deployment on Render (+ UptimeRobot Keep-Alive)

Render provides a Free Tier for **Web Services** that run directly from your GitHub repository.

### Step 1: Deploy on Render
1. Go to [Render Dashboard](https://dashboard.render.com/) and click **New > Web Service** (or use **Blueprints** with `render.yaml`).
2. Connect your GitHub repository (`Raad0-0/clubhub-bot`).
3. Set the service configuration:
   - **Environment**: `Python 3`
   - **Region**: Choose any region (e.g., Oregon or Frankfurt).
   - **Branch**: `main`
   - **Build Command**: `pip install -r requirements.txt && pip install -e .`
   - **Start Command**: `python main.py`
   - **Instance Type**: `Free`
4. Under **Advanced / Health Check Path**:
   - Set Health Check Path to: `/health`
5. Under **Environment Variables**:
   - `DISCORD_TOKEN`: *(Paste your secret bot token)*
   - `ENVIRONMENT`: `production`
6. Click **Create Web Service**.

### Step 2: Prevent 15-Minute Idle Shutdown via UptimeRobot
Render's free tier spins down web services after 15 minutes of inactivity. To keep your bot running 24/7 without stopping:
1. Sign up for free at [UptimeRobot.com](https://uptimerobot.com/).
2. Click **Add New Monitor**:
   - **Monitor Type**: `HTTP(s)`
   - **Friendly Name**: `ClubHub Discord Bot`
   - **URL (or IP)**: `https://your-service-name.onrender.com/health` (or root `https://your-service-name.onrender.com/`)
   - **Monitoring Interval**: Every `5 minutes` (or `10 minutes`)
3. Click **Create Monitor**.
*UptimeRobot will ping your `/health` route every 5 minutes, keeping Render's container awake 24/7 so your Discord bot never disconnects!*

---

## 4. Alternative: Free 24/7 Hosting via Discloud

Discloud provides a free tier specifically designed for hosting Discord bots 24/7 with persistent storage and auto-restart.

### Setup Steps:
1. Log in to [Discloud Dashboard](https://discloudbot.com/) using your Discord account.
2. Ensure your bot files include:
   - `discloud.config` (pre-configured in the repository)
   - `main.py` (root launcher)
   - `requirements.txt`
   - `config.yaml`
   - `.env` (containing your `DISCORD_TOKEN`)
3. **Upload Method A: Web Dashboard (Zip)**
   - Compress the project files into a `.zip` file (excluding `venv/`).
   - Go to Discloud Dashboard -> **Upload App** -> Select your `.zip`.
4. **Upload Method B: GitHub Sync**
   - In Discloud Dashboard, connect your GitHub repository and trigger deployment.
5. Click **Start** — your bot will stay online 24/7 without requiring your local PC.

---

## 5. Linux Deployment via systemd

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

## 6. Docker Deployment

A minimal `Dockerfile` is provided for containerized deployments:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
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

## 7. Operational Backups
Operational data is stored in the SQLite database (`clubhub.db` or configured path).
Perform automated daily backups using standard SQLite backup or cron:
```bash
sqlite3 clubhub.db ".backup 'backups/clubhub_$(date +%F).db'"
```
In the event of a bot crash or host reboot, ClubHub automatically re-registers persistent buttons and runs a reconciliation pass to grant overdue tickets a configurable grace period before taking cleanup action.
