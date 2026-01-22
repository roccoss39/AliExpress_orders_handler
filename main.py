import time
import logging
import sys
import threading
from datetime import datetime
import traceback

# Moduły projektu
from email_handler import EmailHandler
from sheets_handler import SheetsHandler
from notification import send_pickup_notification
from carriers_sheet_handlers import EmailAvailabilityManager
from log_cleaner import auto_cleanup_logs
from rate_limiter import create_api_limiters
from graceful_shutdown import init_graceful_shutdown, set_handlers, increment_processed_emails, increment_iterations, save_periodic_state, is_shutdown_requested, set_main_loop_running, get_stats
from telegram_notifier import TelegramNotifier
import config

# Importy z modułów pomocniczych
from diagnostic_menu import show_diagnostic_menu
from reprocess_manager import run_reprocess

# ==========================================
# 🔧 KONFIGURACJA LOGOWANIA
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("aliexpress_tracker.log"), # Zapis do pliku
        logging.StreamHandler(sys.stdout)              # ✅ Zapis na ekran
    ]
)
# Zapobiega wywalaniu błędów BrokenPipe na ekran
logging.raiseExceptions = False 
logging.getLogger('openai').setLevel(logging.WARNING)

def main_loop():
    """Główna pętla programu"""
    
    # Inicjalizacja systemów
    init_graceful_shutdown()
    auto_cleanup_logs(3, 50)
    limiters = create_api_limiters()
    
    # Telegram
    telegram = TelegramNotifier()
    telegram.send_startup_message()
    
    email_handler = EmailHandler()
    sheets_handler = SheetsHandler()
    
    # 🔌 Wstrzyknięcie email_handler do sheets_handler
    # Pozwala to arkuszowi czyścić lokalne mapowania przy archiwizacji
    sheets_handler.email_handler = email_handler
    
    set_handlers(email_handler, sheets_handler)
    set_main_loop_running(True)
    
    # Health Check Server (w tle)
    try:
        from health_check import start_health_server
        health_thread = threading.Thread(target=start_health_server, args=(8081,), daemon=True)
        health_thread.start()
        logging.info('🏥 Uruchomiono health check server na porcie 8081')
    except Exception as e:
        logging.warning(f'⚠️ Nie udało się uruchomić health check: {e}')
        
    logging.info("🚀 Bot wystartował (Tryb PROSTY: 1 Email = 1 Wiersz).")

    first_run = True
    last_duplicate_check = 0 

    # Czyszczenie na start (archiwizowane starych zamówień)
    sheets_handler.check_and_archive_delivered_orders()

    while not is_shutdown_requested():
        try:
            # 1. Usuwanie duplikatów (raz na 24h)
            if time.time() - last_duplicate_check > 86400:
                sheets_handler.remove_duplicates()
                last_duplicate_check = time.time()

            logging.info(f"--- NOWY CYKL: {datetime.now().strftime('%H:%M:%S')} ---")
            
            # 2. Połączenie z arkuszem
            limiters.wait_for("sheets_read")
            if not sheets_handler.connect():
                logging.error("Nie można połączyć się z arkuszem Google.")
                telegram.send_error_message("Błąd połączenia z Google Sheets API")
                time.sleep(300)
                continue

            # 3. Synchronizacja mapowań z arkusza
            limiters.wait_for("sheets_read")
            email_handler.sync_mappings_from_sheets(sheets_handler)
            
            # 4. Pobieranie emaili
            limiters.wait_for("imap")
            processed_emails = email_handler.process_emails(sheets_handler=sheets_handler)
            
            if processed_emails:
                increment_processed_emails(len(processed_emails))
                logging.info(f"Przetworzono {len(processed_emails)} nowych e-maili")
            
            # 5. Przetwarzanie wyników
            for order_data in processed_emails:
                if is_shutdown_requested(): break
                
                # Powiadomienie na Telegram
                telegram.send_new_package_alert(order_data)
                
                # Dodatkowe powiadomienie mailowe dla odbioru
                if order_data.get("status") == "pickup":
                    send_pickup_notification(order_data)

                # ✅ GŁÓWNA AKTUALIZACJA ARKUSZA
                # Teraz sheets_handler robi wszystko: tworzy, aktualizuje, archiwizuje, czyści konta.
                limiters.wait_for("sheets_write")
                sheets_handler.handle_order_update(order_data)

                # ✅ CZYSZCZENIE LOKALNEGO PLIKU JSON
                # SheetsHandler czyści arkusz, a my tutaj doczyszczamy pamięć bota
                if order_data.get("status") == "delivered":
                    user_key = order_data.get("user_key")
                    logging.info(f"🧹 Status 'delivered'. Usuwam lokalne mapowanie dla {user_key}...")
                    
                    email_handler.remove_user_mapping(
                        user_key,
                        order_data.get("package_number"),
                        order_data.get("order_number")
                    )
                    # UWAGA: Usunięto stąd free_up_account, bo SheetsHandler robi to automatycznie

            # 6. Aktualizacja kolorów w Accounts (tylko kosmetyka)
            if len(processed_emails) > 0 or first_run:
                limiters.wait_for("sheets_read")
                logging.info("🎨 Aktualizacja statusów kont w arkuszu...")
                try:
                    EmailAvailabilityManager(sheets_handler).check_email_availability()
                    logging.info("✅ Statusy odświeżone.")
                except Exception as e:
                    # Ignorujemy błędy tutaj, żeby nie zatrzymywać bota
                    pass
                
                first_run = False
            
            # 7. Statystyki i zapis stanu
            increment_iterations()
            save_periodic_state()
            
            # Logowanie statystyk co 100 cykli
            loop_counter = getattr(main_loop, 'counter', 0)
            main_loop.counter = loop_counter + 1
            if loop_counter % 100 == 0:
                logging.info(f"📊 STATYSTYKI: {get_stats()}")

            # 8. Oczekiwanie
            sleep_time = getattr(config, 'CHECK_INTERVAL', 5) * 60
            if getattr(config, 'QUICK_CHECK', False):
                sleep_time = getattr(config, 'TEST_INTERVAL', 300)
                
            logging.info(f"💤 Usypianie na {sleep_time}s...")
            time.sleep(sleep_time)
                
        except Exception as e:
            # Obsługa błędów krytycznych
            logging.error(f"🔥 Krytyczny błąd w pętli: {e}")
            logging.error(traceback.format_exc())
            telegram.send_error_message(f"Błąd pętli: {str(e)}")
            time.sleep(60)
    
    set_main_loop_running(False)
    logging.info('🏁 Bot zakończył pracę.')
    telegram.send_message("🛑 Bot wyłączony.")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="AliExpress Order Tracker")
    parser.add_argument("--menu", action="store_true", help="Uruchom menu diagnostyczne")
    parser.add_argument("--reprocess-email", type=str, help="Wymuś ponowne przetworzenie maili dla podanego adresu")
    parser.add_argument("--limit", type=int, help="Maksymalna liczba maili do przetworzenia (dla trybu reprocess)")

    args = parser.parse_args()

    if args.menu:
        show_diagnostic_menu()
    
    elif args.reprocess_email:
        run_reprocess(args.reprocess_email, limit=args.limit)
        
    else:
        print("Uruchamianie głównej pętli. Naciśnij Ctrl+C aby zatrzymać.")
        main_loop()