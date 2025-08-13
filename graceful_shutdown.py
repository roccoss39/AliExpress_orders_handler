import signal
import sys
import json
import os
import logging
from datetime import datetime
import atexit

class GracefulShutdown:
    """
    Klasa do obsługi graceful shutdown aplikacji
    """
    
    def __init__(self):
        self.shutdown_in_progress = False
        self.app_start_time = datetime.now()
        self.processed_emails_count = 0
        self.total_iterations = 0
        self.handlers_registered = False
        
        # Zmienne do przechowywania referencji do głównych obiektów
        self.email_handler = None
        self.sheets_handler = None
        self.main_loop_running = False
        
    def register_handlers(self):
        """Rejestruje obsługę sygnałów systemowych"""
        if not self.handlers_registered:
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            
            # Rejestruj funkcję do wywołania przy wyjściu
            atexit.register(self._cleanup_on_exit)
            
            self.handlers_registered = True
            logging.info('🔧 Zarejestrowano obsługę sygnałów zamknięcia (SIGINT, SIGTERM)')
    
    def _signal_handler(self, sig, frame):
        """Obsługa sygnałów zamknięcia systemu"""
        if self.shutdown_in_progress:
            logging.warning('⚠️ Ponowny sygnał zamknięcia - wymuszanie wyjścia')
            sys.exit(1)
            
        signal_name = "SIGINT (Ctrl+C)" if sig == signal.SIGINT else "SIGTERM"
        logging.info(f'🛑 Otrzymano sygnał {signal_name} - rozpoczynam graceful shutdown...')
        
        self.shutdown_in_progress = True
        self._perform_shutdown()
    
    def _cleanup_on_exit(self):
        """Funkcja sprzątająca wywoływana przy wyjściu z aplikacji"""
        if not self.shutdown_in_progress:
            logging.info('🧹 Wykonuję sprzątanie przy wyjściu z aplikacji')
            self._save_final_state()
    
    def _perform_shutdown(self):
        """Wykonuje graceful shutdown"""
        try:
            logging.info('💾 Zapisuję stan aplikacji przed zamknięciem...')
            self._save_final_state()
            
            logging.info('🔌 Zamykam połączenia...')
            self._close_connections()
            
            logging.info('📊 Wyświetlam statystyki końcowe...')
            self._print_final_stats()
            
            logging.info('✅ Graceful shutdown zakończony pomyślnie')
            
        except Exception as e:
            logging.error(f'❌ Błąd podczas graceful shutdown: {e}')
        finally:
            sys.exit(0)
    
    def set_handlers(self, email_handler=None, sheets_handler=None):
        """Ustawia referencje do głównych handlerów"""
        self.email_handler = email_handler
        self.sheets_handler = sheets_handler
        logging.debug('🔗 Ustawiono referencje do handlerów')
    
    def increment_processed_emails(self, count=1):
        """Zwiększa licznik przetworzonych emaili"""
        self.processed_emails_count += count
        logging.debug(f"📧 DEBUG: processed_emails_count = {self.processed_emails_count}")
    
    def increment_iterations(self):
        """Zwiększa licznik iteracji głównej pętli"""
        self.total_iterations += 1
        logging.info(f"🔧 DEBUG increment_iterations: total_iterations={self.total_iterations}")
    
    def set_main_loop_running(self, running=True):
        """Ustawia flagę działania głównej pętli"""
        self.main_loop_running = running
        logging.info(f"🔧 DEBUG: main_loop_running = {running}")
    
    def is_shutdown_requested(self):
        """Sprawdza czy zostało zażądane zamknięcie"""
        return self.shutdown_in_progress
    
    def _close_connections(self):
        """Zamyka połączenia z zewnętrznymi serwisami"""
        try:
            # Zamknij połączenia email
            if self.email_handler and hasattr(self.email_handler, 'close_connections'):
                logging.info('📧 Zamykam połączenia email...')
                self.email_handler.close_connections()
            
            # Zamknij połączenie Google Sheets
            if self.sheets_handler and hasattr(self.sheets_handler, 'close'):
                logging.info('📊 Zamykam połączenie Google Sheets...')
                self.sheets_handler.close()
            
        except Exception as e:
            logging.error(f'❌ Błąd podczas zamykania połączeń: {e}')
    
    def _save_final_state(self):
        """Zapisuje końcowy stan aplikacji"""
        try:
            uptime = datetime.now() - self.app_start_time
            
            state = {
                "app_info": {
                    "name": "AliExpress Order Tracker",
                    "version": "1.0",
                    "shutdown_type": "graceful" if not self.shutdown_in_progress else "forced"
                },
                "timing": {
                    "start_time": self.app_start_time.isoformat(),
                    "shutdown_time": datetime.now().isoformat(),
                    "uptime_seconds": uptime.total_seconds(),
                    "uptime_formatted": str(uptime)
                },
                "counters": {
                    "processed_emails": self.processed_emails_count,
                    "total_iterations": self.total_iterations,
                    "emails_per_hour": self._calculate_emails_per_hour(uptime)
                },
                "status": {
                    "main_loop_was_running": self.main_loop_running,
                    "handlers_registered": self.handlers_registered,
                    "clean_shutdown": True
                }
            }
            
            # Zapisz do pliku
            with open('app_state.json', 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            
            logging.info(f'💾 Stan aplikacji zapisany do app_state.json')
            logging.debug(f'📊 Przetworzono {self.processed_emails_count} emaili w {self.total_iterations} iteracjach')
            
        except Exception as e:
            logging.error(f'❌ Błąd podczas zapisywania stanu: {e}')
    
    def _calculate_emails_per_hour(self, uptime):
        """Oblicza liczbę emaili na godzinę"""
        if uptime.total_seconds() > 0:
            return round(self.processed_emails_count / (uptime.total_seconds() / 3600), 2)
        return 0
    
    def _print_final_stats(self):
        """Wyświetla końcowe statystyki"""
        uptime = datetime.now() - self.app_start_time
        
        print("\n" + "="*50)
        print("📊 STATYSTYKI KOŃCOWE")
        print("="*50)
        print(f"⏰ Czas działania: {uptime}")
        print(f"📧 Przetworzonych emaili: {self.processed_emails_count}")
        print(f"🔄 Iteracji głównej pętli: {self.total_iterations}")
        print(f"📈 Emaili na godzinę: {self._calculate_emails_per_hour(uptime)}")
        print(f"🕐 Start: {self.app_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🏁 Koniec: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*50)
    
    def load_previous_state(self):
        """Wczytuje poprzedni stan aplikacji"""
        try:
            if os.path.exists('app_state.json'):
                with open('app_state.json', 'r', encoding='utf-8') as f:
                    previous_state = json.load(f)
                
                # Wyświetl info o poprzednim uruchomieniu
                if 'timing' in previous_state:
                    last_shutdown = previous_state['timing'].get('shutdown_time', 'nieznany')
                    uptime = previous_state['timing'].get('uptime_formatted', 'nieznany')
                    processed = previous_state['counters'].get('processed_emails', 0)
                    
                    logging.info(f'📚 Poprzednie uruchomienie:')
                    logging.info(f'   • Zakończone: {last_shutdown}')
                    logging.info(f'   • Czas działania: {uptime}')
                    logging.info(f'   • Przetworzonych emaili: {processed}')
                
                return previous_state
            else:
                logging.info('📚 Brak poprzedniego stanu - pierwsze uruchomienie aplikacji')
                return {}
                
        except Exception as e:
            logging.error(f'❌ Błąd podczas wczytywania poprzedniego stanu: {e}')
            return {}
    
    def save_periodic_state(self):
        """Zapisuje stan aplikacji okresowo (do wywołania co jakiś czas)"""
        try:
            uptime = datetime.now() - self.app_start_time
            
            state = {
                "app_info": {
                    "name": "AliExpress Order Tracker",
                    "version": "1.0",
                    "status": "running"
                },
                "timing": {
                    "start_time": self.app_start_time.isoformat(),
                    "last_update": datetime.now().isoformat(),
                    "uptime_seconds": uptime.total_seconds(),
                    "uptime_formatted": str(uptime)
                },
                "counters": {
                    "processed_emails": self.processed_emails_count,
                    "total_iterations": self.total_iterations,
                    "emails_per_hour": self._calculate_emails_per_hour(uptime)
                },
                "status": {
                    "main_loop_running": self.main_loop_running,
                    "handlers_registered": self.handlers_registered,
                    "last_health_check": datetime.now().isoformat()
                }
            }
            
            with open('app_state.json', 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            
            logging.debug(f'💾 Stan aplikacji zaktualizowany (emaile: {self.processed_emails_count}, iteracje: {self.total_iterations})')
            
        except Exception as e:
            logging.error(f'❌ Błąd podczas okresowego zapisywania stanu: {e}')
    
    def get_current_stats(self):
        """Zwraca aktualne statystyki aplikacji"""
        uptime = datetime.now() - self.app_start_time
        
        return {
            "uptime": str(uptime),
            "uptime_seconds": uptime.total_seconds(),
            "processed_emails": self.processed_emails_count,
            "total_iterations": self.total_iterations,
            "emails_per_hour": self._calculate_emails_per_hour(uptime),
            "start_time": self.app_start_time.isoformat(),
            "running": self.main_loop_running,
            "shutdown_requested": self.shutdown_in_progress,
            "iterations": self.total_iterations  # ✅ DODANE dla health check
        }


# Globalny singleton
_shutdown_manager = None

def get_shutdown_manager():
    """Zwraca globalny singleton shutdown managera"""
    global _shutdown_manager
    if _shutdown_manager is None:
        _shutdown_manager = GracefulShutdown()
    return _shutdown_manager

def init_graceful_shutdown():
    """Inicjalizuje graceful shutdown i zwraca manager + poprzedni stan"""
    manager = get_shutdown_manager()
    
    # Zarejestruj handlery sygnałów
    manager.register_handlers()
    
    # Wczytaj poprzedni stan
    previous_state = manager.load_previous_state()
    
    logging.info('🚀 Graceful shutdown zainicjalizowany')
    
    return manager, previous_state

# Funkcje pomocnicze dla łatwego użycia
def set_handlers(email_handler=None, sheets_handler=None):
    """Ustawia referencje do handlerów"""
    get_shutdown_manager().set_handlers(email_handler, sheets_handler)

def increment_processed_emails(count=1):
    """Zwiększa licznik przetworzonych emaili"""
    get_shutdown_manager().increment_processed_emails(count)

def increment_iterations():
    """Zwiększa licznik iteracji"""
    manager = get_shutdown_manager()
    manager.increment_iterations()

def save_periodic_state():
    """Zapisuje stan aplikacji"""
    get_shutdown_manager().save_periodic_state()

def is_shutdown_requested():
    """Sprawdza czy zażądano zamknięcia"""
    return get_shutdown_manager().is_shutdown_requested()

def set_main_loop_running(running=True):
    """Ustawia flagę działania głównej pętli"""
    get_shutdown_manager().set_main_loop_running(running)

def get_stats():
    """Zwraca aktualne statystyki"""
    return get_shutdown_manager().get_current_stats()