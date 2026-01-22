import http.server
import socketserver
import logging
import json
import time

# Zmienna globalna do przechowywania instancji serwera
_httpd = None

class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {
                'status': 'ok',
                'timestamp': time.time()
            }
            try:
                self.wfile.write(json.dumps(response).encode())
            except Exception:
                pass # Ignoruj błędy zapisu (np. klient się rozłączył)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # Wyłączamy domyślne logowanie HTTP na konsolę, żeby nie śmiecić
        pass

def start_health_server(port=8081):
    global _httpd
    try:
        # Klasa pozwalająca na szybkie odzyskanie portu (SO_REUSEADDR)
        class ReusableTCPServer(socketserver.TCPServer):
            allow_reuse_address = True

        _httpd = ReusableTCPServer(("", port), HealthCheckHandler)
        logging.info(f"🏥 Health check server listening on port {port}")
        
        # To jest pętla blokująca, dlatego uruchamiamy ją w wątku
        _httpd.serve_forever()
        
    except OSError as e:
        if e.errno == 98:
            logging.error(f"❌ Port {port} jest zajęty! Health check nie wystartował.")
        else:
            logging.error(f"❌ Błąd serwera health check: {e}")
    except Exception as e:
        logging.error(f"❌ Nieoczekiwany błąd serwera health check: {e}")
    finally:
        if _httpd:
            _httpd.server_close()

def stop_health_server():
    """Bezpiecznie zatrzymuje serwer HTTP"""
    global _httpd
    if _httpd:
        logging.info("🛑 Zamykanie serwera health check...")
        # shutdown() przerywa pętlę serve_forever()
        # Musi być wywołane z innego wątku niż serve_forever!
        _httpd.shutdown()
        _httpd.server_close()
        _httpd = None
        logging.info("✅ Serwer health check zamknięty.")