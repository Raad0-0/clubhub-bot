#!/usr/bin/env bash
# ClubHub automated setup script for Google Cloud Always-Free e2-micro VM

set -e

echo "=================================================="
echo "🚀 Setting up ClubHub Bot on Google Cloud VM"
echo "=================================================="

# 1. Install system prerequisites
echo "📦 Updating packages and installing Python 3..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git

# 2. Setup Virtual Environment
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "🐍 Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

echo "📥 Installing dependencies from requirements.txt..."
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 3. Setup Configuration and .env
if [ ! -f "config.yaml" ] && [ -f "config.example.yaml" ]; then
    cp config.example.yaml config.yaml
    echo "📄 Created config.yaml from template."
fi

if [ ! -f ".env" ]; then
    echo ""
    echo "🔑 Discord Bot Token Setup:"
    read -p "Enter your DISCORD_TOKEN: " token
    echo "DISCORD_TOKEN=$token" > .env
    echo "ENVIRONMENT=production" >> .env
    chmod 600 .env
    echo "✅ Created .env securely."
fi

# 4. Create and start systemd 24/7 service
CURRENT_USER=$(whoami)
SERVICE_FILE="/etc/systemd/system/clubhub.service"

echo "⚙️ Configuring 24/7 systemd background service..."
sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=ClubHub Discord Bot (24/7 Service)
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$DIR
ExecStart=$DIR/venv/bin/python main.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

echo "🔄 Reloading systemd and starting ClubHub..."
sudo systemctl daemon-reload
sudo systemctl enable --now clubhub

echo "=================================================="
echo "🎉 ClubHub is now running 24/7 on Google Cloud!"
echo "=================================================="
sudo systemctl status clubhub --no-pager
echo ""
echo "Useful commands:"
echo "  View live logs:   journalctl -u clubhub -f"
echo "  Restart bot:      sudo systemctl restart clubhub"
echo "  Stop bot:         sudo systemctl stop clubhub"
