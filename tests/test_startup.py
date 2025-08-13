#!/usr/bin/env python3

print("🔍 === DIAGNOSTYKA STARTU APLIKACJI ===")

import sys
import os
print(f"🐍 Python: {sys.executable}")
print(f"📁 Katalog: {os.getcwd()}")
print(f"📋 Python path: {sys.path}")

# Test importów
print("\n📦 Test importów:")
modules = [
    'time', 'logging', 'sys', 'signal', 'json', 'os', 
    'threading', 'requests', 'datetime', 'traceback', 'psutil'
]

for module in modules:
    try:
        __import__(module)
        print(f"✅ {module}")
    except ImportError as e:
        print(f"❌ {module}: {e}")

# Test własnych modułów
print("\n🔧 Test własnych modułów:")
own_modules = [
    'config', 'email_handler', 'sheets_handler', 
    'graceful_shutdown', 'rate_limiter', 'health_check'
]

for module in own_modules:
    try:
        __import__(module)
        print(f"✅ {module}")
    except ImportError as e:
        print(f"❌ {module}: {e}")
    except Exception as e:
        print(f"⚠️ {module}: {e}")

print("\n🏥 Test health check server:")
try:
    from health_check import start_health_server
    import threading
    thread = threading.Thread(target=start_health_server, args=(8080,), daemon=True)
    thread.start()
    print("✅ Health check server uruchomiony")
    
    import time
    time.sleep(2)
    
    import requests
    response = requests.get('http://localhost:8080', timeout=5)
    print(f"✅ Health check odpowiada: {response.status_code}")
    print(f"📊 Response: {response.json()}")
    
except Exception as e:
    print(f"❌ Health check błąd: {e}")

print("\n✅ Diagnostyka zakończona")