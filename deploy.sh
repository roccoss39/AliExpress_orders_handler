#!/bin/bash
echo "🚀 DEPLOYMENT ALIEXPRESS TRACKER"

# Sprawdź zależności
python3 -c "import requests, psutil, gspread" 2>/dev/null || {
    echo "Instaluję zależności..."
    pip3 install --user requests psutil gspread google-auth-oauthlib google-auth
}

# Instaluj service
sudo cp aliexpress-tracker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable aliexpress-tracker
sudo systemctl restart aliexpress-tracker

echo "✅ Deployment zakończony!"
echo "📊 Status: sudo systemctl status aliexpress-tracker"
