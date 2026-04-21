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

import argparse
import os 
from health_check import stop_health_server
    
# ==========================================
# 🔧 KONFIGURACJA LOGOWANIA (Dynamiczna)
# ==========================================
log_handlers = []

# 1. Sprawdzenie czy logować do pliku
if getattr(config, 'LOG_TO_FILE', True):
    log_file = getattr(config, 'LOG_FILE_NAME', "aliexpress_tracker.log")
    log_handlers.append(logging.FileHandler(log_file, encoding='utf-8'))

# 2. Sprawdzenie czy wyświetlać na ekranie (konsoli)
if getattr(config, 'LOG_TO_CONSOLE', True):
    log_handlers.append(logging.StreamHandler(sys.stdout))

# 3. Jeśli obie opcje są wyłączone, dodajemy NullHandler, żeby program nie rzucał błędami
if not log_handlers:
    log_handlers.append(logging.NullHandler())

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=log_handlers
)

# Zapobiega wywalaniu błędów BrokenPipe na ekran
logging.raiseExceptions = False 
logging.getLogger('openai').setLevel(logging.WARNING)

def main_loop(single_user=None, subject_word=None):
    """Główna pętla programu"""
    
    # ==========================================
    # 🎯 TRYB POJEDYNCZEGO KONTO I FILTROWANIA (Wymuszenia)
    # ==========================================
    # Jeśli używamy jakiegokolwiek filtra (single_user lub word), wymuszamy głębokie skanowanie
    if single_user or subject_word:
        logging.info("=" * 60)
        logging.info("🎯 TRYB WYMUSZENIA (Filtrowanie aktywne)")
        
        # 1. Wymuszenie pobierania WSZYSTKICH wiadomości z serwera
        config.CHECK_ONLY_UNSEEN = False
        
        # 2. Ignorowanie blokady daty (żeby bot przetworzył nawet stare maile)
        config.IGNORE_LAST_EMAIL_DATE_CHECK = True

        # 3. Przetwarzanie od najstarszych do najnowszych (chronologicznie)
        config.PROCESS_FROM_NEWEST = False
        
        logging.info("⚙️ Wymuszono config.CHECK_ONLY_UNSEEN = False (Sprawdzam całą historię)")
        logging.info("⚙️ Wymuszono config.IGNORE_LAST_EMAIL_DATE_CHECK = True (Ignoruję blokadę daty)")
        logging.info("⚙️ Wymuszono config.PROCESS_FROM_NEWEST = False (Przetwarzam od najstarszych)")
        logging.info("=" * 60)

    # Filtr 1: Tylko konkretny użytkownik
    if single_user:
        logging.info(f"👤 Ograniczam pracę do konta: {single_user}")
        
        # Dynamiczne filtrowanie dla trybu ACCOUNTS
        original_get_emails = EmailAvailabilityManager.get_emails_from_accounts_sheet
        def filtered_get_emails(self_instance):
            configs = original_get_emails(self_instance)
            if configs:
                filtered = [e for e in configs if e.get('email', '').strip().lower() == single_user.lower()]
                if not filtered:
                    logging.warning(f"⚠️ Nie znaleziono konta {single_user} w arkuszu Accounts!")
                return filtered
            return configs
        EmailAvailabilityManager.get_emails_from_accounts_sheet = filtered_get_emails
        
        # Dynamiczne filtrowanie dla trybu CONFIG
        if hasattr(config, 'ALL_EMAIL_CONFIGS'):
            config.ALL_EMAIL_CONFIGS = [e for e in config.ALL_EMAIL_CONFIGS if e.get('email', '').strip().lower() == single_user.lower()]

    # Filtr 2: Tylko konkretne słowo w temacie
    if subject_word:
        logging.info(f"🔎 Szukam tylko maili zawierających słowo: '{subject_word}'")
        
        # Dynamiczne przechwycenie funkcji analyze_email
        original_analyze = EmailHandler.analyze_email
        def filtered_analyze(self_inst, subject, *args, **kwargs):
            if subject_word.lower() not in subject.lower():
                logging.info(f"⏭️ Pomijam (brak słowa '{subject_word}'): {subject[:40]}...")
                return None
            return original_analyze(self_inst, subject, *args, **kwargs)
        
        EmailHandler.analyze_email = filtered_analyze
    # ==========================================
    
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
                
                if order_data.get("refund_detected"):
                    telegram.send_cancellation_notice(order_data)
                    logging.info("ℹ️ Wykryto zwrot za anulowane zakupy - pomijam zapis do arkusza.")
                    continue
            
                # Dodatkowe powiadomienie mailowe dla odbioru
                if order_data.get("status") == "pickup":
                    send_pickup_notification(order_data)

                # ✅ GŁÓWNA AKTUALIZACJA ARKUSZA
                limiters.wait_for("sheets_write")
                sheets_handler.handle_order_update(order_data, telegram_notifier=telegram)

                # ✅ CZYSZCZENIE LOKALNEGO PLIKU JSON
                if order_data.get("status") == "delivered":
                    user_key = order_data.get("user_key")
                    logging.info(f"🧹 Status 'delivered'. Usuwam lokalne mapowanie dla {user_key}...")
                    
                    email_handler.remove_user_mapping(
                        user_key,
                        order_data.get("package_number"),
                        order_data.get("order_number")
                    )

            # 6. Aktualizacja kolorów w Accounts (tylko kosmetyka)
            if len(processed_emails) > 0 or first_run:
                limiters.wait_for("sheets_read")
                logging.info("🎨 Aktualizacja statusów kont w arkuszu...")
                try:
                    EmailAvailabilityManager(sheets_handler).check_email_availability()
                    logging.info("✅ Statusy odświeżone.")
                except Exception as e:
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

            # 8. INTELIGENTNE OCZEKIWANIE (Smart Sleep)
            sleep_minutes = getattr(config, 'CHECK_INTERVAL', 5)
            sleep_seconds = sleep_minutes * 60
            if getattr(config, 'QUICK_CHECK', False):
                sleep_seconds = getattr(config, 'TEST_INTERVAL', 300)
                
            logging.info(f"💤 Usypianie na {sleep_seconds}s (Naciśnij Ctrl+C aby przerwać)...")
            
            # Sprawdzamy co sekundę, czy nie ma żądania wyjścia
            for _ in range(int(sleep_seconds)):
                if is_shutdown_requested():
                    logging.info("🛑 Wykryto żądanie zamknięcia podczas drzemki.")
                    break
                time.sleep(1)
                
        except Exception as e:
            logging.error(f"🔥 Krytyczny błąd w pętli: {e}")
            logging.error(traceback.format_exc())
            telegram.send_error_message(f"Błąd pętli: {str(e)}")
            time.sleep(60)
    
    set_main_loop_running(False)
    from health_check import stop_health_server
    stop_health_server()
    
    logging.info('🏁 Bot zakończył pracę.')
    telegram.send_message("🛑 Bot wyłączony.")

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="AliExpress Order Tracker")
    parser.add_argument("--menu", action="store_true", help="Uruchom menu diagnostyczne")
    parser.add_argument("--reprocess-email", type=str, help="Wymuś ponowne przetworzenie maili dla podanego adresu")
    parser.add_argument("--limit", type=int, help="Maksymalna liczba maili do przetworzenia (dla trybu reprocess)")
    parser.add_argument(
        "--subject-contains",
        type=str,
        default="",
        help="(Reprocess) Przetwarzaj tylko maile, których temat zawiera podaną frazę (case-insensitive)."
    )
    
    parser.add_argument("--single-user", type=str, help="Uruchom główną pętlę TYLKO dla wybranego adresu email")
    # 🌟 NOWA FLAGA DODANA TUTAJ 🌟
    parser.add_argument("--word", type=str, help="Uruchom główną pętlę TYLKO dla maili zawierających to słowo w temacie")

    args = parser.parse_args()

    if args.menu:
        show_diagnostic_menu()
    
    elif args.reprocess_email:
        run_reprocess(args.reprocess_email, limit=args.limit, subject_contains=args.subject_contains)
        
    else:
        # Informacja o aktywnych filtrach w konsoli przed startem
        filters_info = []
        if args.single_user: filters_info.append(f"Konto: {args.single_user}")
        if args.word: filters_info.append(f"Słowo w temacie: '{args.word}'")
        
        if filters_info:
            print(f"Uruchamianie głównej pętli Z FILTRAMI ({', '.join(filters_info)}). Naciśnij Ctrl+C aby zatrzymać.")
        else:
            print("Uruchamianie standardowej głównej pętli. Naciśnij Ctrl+C aby zatrzymać.")
            
        try:
            # Przekazujemy argumenty do pętli
            main_loop(single_user=args.single_user, subject_word=args.word)
        except KeyboardInterrupt:
            logging.info("\n🛑 Wykryto Ctrl+C. Zamykanie...")
        except Exception as e:
            logging.error(f"🔥 Nieoczekiwany błąd krytyczny: {e}")
            traceback.print_exc()
        finally:
            logging.info("🔌 Sprzątanie po zamknięciu...")
            try:
                stop_health_server()
            except:
                pass
            logging.info("💀 WYMUSZENIE ZAMKNIĘCIA PROCESU (os._exit)")
            os._exit(0)