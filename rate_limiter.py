import time
import logging
from datetime import datetime, timedelta

class SimpleRateLimiter:
    """
    Prosty rate limiter do ograniczania liczby wywołań API w określonym czasie
    """
    
    def __init__(self, max_calls=50, time_window=60, name="API"):
        """
        Args:
            max_calls (int): Maksymalna liczba wywołań w oknie czasowym
            time_window (int): Okno czasowe w sekundach
            name (str): Nazwa limitera (do logowania)
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.name = name
        self.calls = []
        
        logging.info(f"🚦 Utworzono rate limiter '{name}': {max_calls} wywołań na {time_window}s")
    
    def wait_if_needed(self):
        """
        Sprawdza czy można wykonać wywołanie, jeśli nie - czeka
        """
        now = datetime.now()
        
        # Usuń stare wywołania (starsze niż time_window)
        cutoff = now - timedelta(seconds=self.time_window)
        old_count = len(self.calls)
        self.calls = [call for call in self.calls if call > cutoff]
        
        if len(self.calls) < old_count:
            logging.debug(f"🧹 {self.name}: Usunięto {old_count - len(self.calls)} starych wywołań")
        
        # Sprawdź czy przekroczono limit
        if len(self.calls) >= self.max_calls:
            # Oblicz ile trzeba czekać
            oldest_call = min(self.calls)
            sleep_time = self.time_window - (now - oldest_call).total_seconds()
            
            if sleep_time > 0:
                logging.warning(f"🕐 {self.name} Rate limit! Czekam {sleep_time:.1f}s (wywołania: {len(self.calls)}/{self.max_calls})")
                time.sleep(sleep_time)
                
                # Odśwież listę po oczekiwaniu
                now = datetime.now()
                cutoff = now - timedelta(seconds=self.time_window)
                self.calls = [call for call in self.calls if call > cutoff]
        
        # Zapisz obecne wywołanie
        self.calls.append(now)
        logging.debug(f"📊 {self.name}: {len(self.calls)}/{self.max_calls} wywołań w oknie {self.time_window}s")
    
    def get_stats(self):
        """
        Zwraca statystyki rate limitera
        """
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.time_window)
        current_calls = [call for call in self.calls if call > cutoff]
        
        return {
            "name": self.name,
            "max_calls": self.max_calls,
            "time_window": self.time_window,
            "current_calls": len(current_calls),
            "remaining_calls": max(0, self.max_calls - len(current_calls)),
            "calls_percentage": (len(current_calls) / self.max_calls) * 100
        }
    
    def reset(self):
        """
        Resetuje wszystkie wywołania (przydatne do testów)
        """
        old_count = len(self.calls)
        self.calls = []
        logging.info(f"🔄 {self.name}: Reset - usunięto {old_count} wywołań")


class MultiRateLimiter:
    """
    Zarządza wieloma rate limiterami naraz
    """
    
    def __init__(self):
        self.limiters = {}
    
    def add_limiter(self, name, max_calls, time_window):
        """
        Dodaje nowy rate limiter
        """
        self.limiters[name] = SimpleRateLimiter(max_calls, time_window, name)
        logging.info(f"➕ Dodano limiter: {name}")
    
    def wait_for(self, limiter_name):
        """
        Czeka na określony limiter
        """
        if limiter_name in self.limiters:
            self.limiters[limiter_name].wait_if_needed()
        else:
            logging.warning(f"⚠️ Nieznany limiter: {limiter_name}")
    
    def get_all_stats(self):
        """
        Zwraca statystyki wszystkich limiterów
        """
        stats = {}
        for name, limiter in self.limiters.items():
            stats[name] = limiter.get_stats()
        return stats
    
    def print_stats(self):
        """
        Wypisuje statystyki wszystkich limiterów
        """
        print("\n=== STATYSTYKI RATE LIMITERÓW ===")
        for name, limiter in self.limiters.items():
            stats = limiter.get_stats()
            print(f"🚦 {name}:")
            print(f"   Wywołania: {stats['current_calls']}/{stats['max_calls']} ({stats['calls_percentage']:.1f}%)")
            print(f"   Pozostało: {stats['remaining_calls']}")
            print(f"   Okno: {stats['time_window']}s")


# Funkcja pomocnicza do szybkiego tworzenia limiterów
def create_api_limiters():
    """
    Tworzy standardowe rate limitery dla różnych API
    """
    limiters = MultiRateLimiter()
    
    # Google Sheets API limits
    limiters.add_limiter("sheets_read", max_calls=80, time_window=100)    # 80 odczytów na 100s
    limiters.add_limiter("sheets_write", max_calls=50, time_window=100)   # 50 zapisów na 100s
    
    # OpenAI API limits (konserwatywne)
    limiters.add_limiter("openai", max_calls=40, time_window=60)          # 40 wywołań na minutę
    
    # IMAP connections (bardzo konserwatywne)
    limiters.add_limiter("imap", max_calls=10, time_window=60)            # 10 połączeń na minutę
    
    return limiters


# Test rate limitera
def test_rate_limiter():
    """
    Funkcja testowa dla rate limitera
    """
    print("🧪 Test rate limitera...")
    
    # Stwórz limiter: 3 wywołania na 10 sekund
    limiter = SimpleRateLimiter(max_calls=3, time_window=10, name="TEST")
    
    # Wykonaj 5 wywołań
    for i in range(5):
        print(f"Wywołanie {i+1}...")
        start_time = time.time()
        limiter.wait_if_needed()
        elapsed = time.time() - start_time
        print(f"  Czas oczekiwania: {elapsed:.2f}s")
        
        # Symuluj pracę API
        time.sleep(0.5)
    
    print("✅ Test zakończony")


if __name__ == "__main__":
    """Uruchomienie testów bezpośrednio"""
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_rate_limiter()
    else:
        print("Użycie:")
        print("  python3 rate_limiter.py test  - uruchom test")
        print("")
        print("Przykład użycia w kodzie:")
        print("  from rate_limiter import SimpleRateLimiter, create_api_limiters")
        print("  limiter = SimpleRateLimiter(max_calls=50, time_window=60)")
        print("  limiter.wait_if_needed()  # przed wywołaniem API")