#!/bin/bash

# --- KONFIGURACJA ---
REMOTE_USER="dawid"
REMOTE_HOST="malina"
REMOTE_DIR="~/aliexpress_orders"
SERVICE_NAME="ali-tracker.service"

echo "🚀 DEPLOYMENT: AliExpress & Multi-Carrier Order Tracker"
echo "--------------------------------------------------------"

# 1. Przesyłanie plików z laptopa na Malinkę
echo "📦 Kopiuję pliki na Raspberry Pi ($REMOTE_HOST)..."
scp *.md *.sh *.py .env config.py requirements.txt service_account.json $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/

if [ $? -eq 0 ]; then
    echo "✅ Pliki dostarczone."
else
    echo "❌ Błąd połączenia! Sprawdź czy Malinka jest w sieci."
    exit 1
fi

# 2. Zdalne operacje na Malince (venv + restart)
echo "⚙️  Aktualizuję biblioteki i restartuję bota..."
ssh $REMOTE_USER@$REMOTE_HOST << EOF
    cd $REMOTE_DIR
    source venv/bin/activate
    pip install -r requirements.txt
    sudo systemctl restart $SERVICE_NAME
    exit
EOF

if [ $? -eq 0 ]; then
    echo "--------------------------------------------------------"
    echo "✨ SUKCES! Bot działa z nowym kodem."
    echo "📊 Status:"
    ssh $REMOTE_USER@$REMOTE_HOST "sudo systemctl status $SERVICE_NAME | grep Active"
else
    echo "❌ Coś poszło nie tak podczas restartu na Malince."
    exit 1
fi
