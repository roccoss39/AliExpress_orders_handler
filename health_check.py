import http.server
import socketserver  # <--- THIS WAS MISSING
import logging
import json
import os
from datetime import datetime

class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
    """Handler for the health check endpoint"""
    
    def do_GET(self):
        """Handle GET requests on the /health endpoint"""
        try:
            if self.path == '/' or self.path == '/health':
                # Check application status
                status = self.get_app_status()
                
                # Set response code
                if status.get("status") == "healthy":
                    self.send_response(200)
                else:
                    self.send_response(503)  # Service Unavailable
                
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                
                # Send JSON
                response = json.dumps(status, indent=2)
                self.wfile.write(response.encode('utf-8'))
            else:
                self.send_response(404)
                self.end_headers()
            
        except Exception as e:
            # In case of catastrophic failure in handler, try to send 500
            try:
                self.send_error(500, f"Health check error: {str(e)}")
            except:
                pass
    
    def log_message(self, format, *args):
        """Disable default HTTP request logging to console"""
        pass

    def get_app_status(self):
        """Checks the current application state"""
        try:
            # 1. Try to get stats from graceful_shutdown module if available
            graceful_stats = {}
            try:
                from graceful_shutdown import get_stats
                graceful_stats = get_stats()
            except ImportError:
                pass
            except Exception as e:
                logging.debug(f"Could not get graceful stats: {e}")

            # 2. Try to load state from file
            app_state = {}
            if os.path.exists('app_state.json'):
                try:
                    with open('app_state.json', 'r') as f:
                        app_state = json.load(f)
                except:
                    pass

            # Determine Health
            is_healthy = False
            uptime = None
            
            # Logic: If graceful_shutdown says it's running, we are healthy
            if graceful_stats.get('running', False):
                is_healthy = True
                uptime = graceful_stats.get('start_time')
            # Fallback: Check app_state file timestamp
            elif app_state.get('last_run'):
                last_run = datetime.fromisoformat(app_state['last_run'])
                time_diff = (datetime.now() - last_run).total_seconds()
                is_healthy = time_diff < 300  # Considered healthy if updated in last 5 mins

            # Check log size
            log_status = "unknown"
            if os.path.exists('aliexpress_tracker.log'):
                log_size = os.path.getsize('aliexpress_tracker.log') / (1024 * 1024)
                log_status = f"{log_size:.1f}MB"

            return {
                "status": "healthy" if is_healthy else "unhealthy",
                "timestamp": datetime.now().isoformat(),
                "uptime": uptime,
                "log_size": log_status,
                "service": "aliexpress_tracker"
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

def start_health_server(port=8080):
    """Starts a simple HTTP server for health checks with Address Reuse enabled"""
    try:
        # Define a custom class to enable address reuse (Fixes [Errno 98])
        class ReusableTCPServer(socketserver.TCPServer):
            allow_reuse_address = True 

        # Create the server using the custom class
        with ReusableTCPServer(("", port), HealthCheckHandler) as httpd:
            logging.info(f"🏥 Health check server listening on port {port}")
            httpd.serve_forever()
            
    except OSError as e:
        if e.errno == 98: # Address already in use
            logging.warning(f"⚠️ Port {port} is busy. Health check did not start (this is not critical).")
        else:
            logging.error(f"❌ Health check server error: {e}")
    except Exception as e:
        logging.error(f"❌ Unexpected health check error: {e}")

if __name__ == "__main__":
    # Allow running this file directly for testing
    logging.basicConfig(level=logging.INFO)
    start_health_server()