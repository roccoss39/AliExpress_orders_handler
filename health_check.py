import json
import threading
import logging
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import signal

class HealthCheckHandler(BaseHTTPRequestHandler):
    """Handler dla endpoint health check"""
    
    def do_GET(self):
        """Obsługa żądań GET na endpoint /health"""
        try:
            # Sprawdź stan aplikacji
            status = self.get_app_status()
            
            # Ustaw odpowiedź
            if status["status"] == "healthy":
                self.send_response(200)
            else:
                self.send_response(503)  # Service Unavailable
            
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            # Wyślij JSON
            response = json.dumps(status, indent=2)
            self.wfile.write(response.encode())
            
        except Exception as e:
            self.send_error(500, f"Health check error: {e}")
    
    def get_app_status(self):
        """Sprawdza aktualny stan aplikacji"""
        try:
            # ✅ DODAJ DEBUG - graceful shutdown stats
            try:
                from graceful_shutdown import get_stats
                graceful_stats = get_stats()
                logging.info(f"🔍 DEBUG Health check - Graceful shutdown stats:")
                logging.info(f"  - running: {graceful_stats.get('running', False)}")
                logging.info(f"  - uptime: {graceful_stats.get('uptime', 'None')}")
                logging.info(f"  - iterations: {graceful_stats.get('iterations', 0)}")
                logging.info(f"  - processed_emails: {graceful_stats.get('processed_emails', 0)}")
                logging.info(f"  - shutdown_requested: {graceful_stats.get('shutdown_requested', False)}")
            except Exception as e:
                logging.warning(f"⚠️ Nie można pobrać stats z graceful_shutdown: {e}")
                graceful_stats = {}
            
            # Wczytaj stan z pliku
            app_state = {}
            if os.path.exists('app_state.json'):
                with open('app_state.json', 'r') as f:
                    app_state = json.load(f)
                logging.info(f"🔍 DEBUG Health check - App state z pliku:")
                logging.info(f"  - last_run: {app_state.get('last_run', 'None')}")
                logging.info(f"  - processed_count: {app_state.get('processed_count', 0)}")
                logging.info(f"  - total_iterations: {app_state.get('total_iterations', 0)}")
            else:
                logging.info(f"🔍 DEBUG Health check - Brak pliku app_state.json")
            
            # ✅ UŻYJ GRACEFUL SHUTDOWN STATS JAKO GŁÓWNE ŹRÓDŁO
            if graceful_stats.get('running', False):
                # Aplikacja działa - użyj stats z graceful_shutdown
                is_healthy = True
                uptime = graceful_stats.get('start_time')
                processed_emails = graceful_stats.get('processed_emails', 0)
                iterations = graceful_stats.get('iterations', 0)
                last_activity = datetime.now().isoformat()
                version = "1.0"
                
                logging.info(f"✅ DEBUG Health check - Status: HEALTHY (graceful_shutdown aktywny)")
                
            elif app_state.get('last_run'):
                # Sprawdź czy aplikacja działa (ostatnia aktualizacja < 5 minut)
                last_run = datetime.fromisoformat(app_state['last_run'])
                time_diff = (datetime.now() - last_run).total_seconds()
                is_healthy = time_diff < 300  # 5 minut
                
                uptime = app_state.get('uptime_start')
                processed_emails = app_state.get('processed_count', 0)
                iterations = app_state.get('total_iterations', 0)
                last_activity = app_state.get('last_run')
                version = app_state.get('version', 'unknown')
                
                logging.info(f"🔍 DEBUG Health check - Status: {'HEALTHY' if is_healthy else 'UNHEALTHY'} (z app_state.json, last_run: {time_diff:.1f}s ago)")
                
            else:
                # Brak danych o działaniu aplikacji
                is_healthy = False
                uptime = None
                processed_emails = 0
                iterations = 0
                last_activity = None
                version = "unknown"
                
                logging.info(f"❌ DEBUG Health check - Status: UNHEALTHY (brak danych o działaniu)")
            
            # Sprawdź logi
            log_status = "unknown"
            if os.path.exists('aliexpress_tracker.log'):
                log_size = os.path.getsize('aliexpress_tracker.log') / (1024 * 1024)  # MB
                log_status = f"{log_size:.1f}MB"
            
            result = {
                "status": "healthy" if is_healthy else "unhealthy",
                "timestamp": datetime.now().isoformat(),
                "uptime": uptime,
                "processed_emails": processed_emails,
                "iterations": iterations,
                "last_activity": last_activity,
                "log_size": log_status,
                "version": version
            }
            
            logging.info(f"📊 DEBUG Health check - Final result: {result}")
            return result
            
        except Exception as e:
            logging.error(f"❌ DEBUG Health check - Exception: {e}")
            return {
                "status": "error",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
    
    def log_message(self, format, *args):
        """Wyłącz domyślne logowanie HTTP requestów"""
        pass

def start_health_server(port=8080):
    """Uruchamia serwer health check w osobnym wątku"""
    try:
        server = HTTPServer(('localhost', port), HealthCheckHandler)
        logging.info(f'🏥 Health check server uruchomiony na porcie {port}')
        logging.info(f'🔗 Test: curl http://localhost:{port}')
        server.serve_forever()
    except Exception as e:
        logging.error(f'❌ Błąd health check server: {e}')

def test_health_check():
    """Test health check endpoint"""
    import requests
    try:
        response = requests.get('http://localhost:8080', timeout=5)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Błąd: {e}")

def signal_handler(sig, frame):
    """Obsługuje sygnały zamknięcia aplikacji"""
    logging.info('🔌 Otrzymano sygnał zamknięcia, kończenie pracy...')
    # Tutaj można dodać kod do czyszczenia zasobów, zapisywania stanu itp.
    os._exit(0)

def main_loop():
    """Główna pętla programu"""
    
    # ✅ REJESTRUJ OBSŁUGĘ SYGNAŁÓW
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    logging.info('🔧 Zarejestrowano obsługę sygnałów zamknięcia')
    
    # ✅ URUCHOM HEALTH CHECK SERVER
    try:
        from health_check import start_health_server
        health_thread = threading.Thread(target=start_health_server, args=(8080,), daemon=True)
        health_thread.start()
        logging.info('🏥 Uruchomiono health check server na porcie 8080')
    except Exception as e:
        logging.warning(f'⚠️ Nie udało się uruchomić health check: {e}')
    
    # ...reszta istniejącego kodu...

if __name__ == "__main__":
    # Test health check
    test_health_check()