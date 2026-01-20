import time
import logging
import sys
import signal
import json
import os
import threading
import requests
from datetime import datetime
from email_handler import EmailHandler
from sheets_handler import SheetsHandler
from notification import send_pickup_notification
import config
from carriers_sheet_handlers import EmailAvailabilityManager
from log_cleaner import cleanup_old_logs, auto_cleanup_logs, get_log_info
import traceback
import psutil
from rate_limiter import create_api_limiters
from graceful_shutdown import init_graceful_shutdown, set_handlers, increment_processed_emails, increment_iterations, save_periodic_state, is_shutdown_requested, set_main_loop_running, get_stats


# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("aliexpress_tracker.log"),
        logging.StreamHandler()
    ]
)
logging.getLogger('openai').setLevel(logging.WARNING)

def load_mappings_from_sheet(sheets_handler, email_handler):
    """Wczytuje mapowania na podstawie danych z arkusza"""
    if not sheets_handler.connected and not sheets_handler.connect():
        return
    
    try:
        # Pobierz wszystkie dane
        all_values = sheets_handler.worksheet.get_all_values()
        
        # Pomijamy nagłówek
        for row in all_values[1:]:
            # ✅ ZMIANA: Dostosowanie do nowych kolumn (M=12, O=14)
            if len(row) >= 15:  
                email = row[0]          # Kolumna A (0)
                order_number = row[12]  # Kolumna M (12) - Nr Zamówienia
                package_number = row[14] # Kolumna O (14) - Nr Paczki
                
                # Mapujemy email do numeru zamówienia i paczki
                if email and (order_number or package_number):
                    if email not in email_handler.user_mappings:
                        email_handler.user_mappings[email] = {}
                    
                    if order_number:
                        email_handler.user_mappings[email]["order_number"] = order_number
                    
                    if package_number:
                        email_handler.user_mappings[email]["package_number"] = package_number
        
        logging.info(f"Wczytano {len(email_handler.user_mappings)} mapowań z arkusza")
    except Exception as e:
        logging.error(f"Błąd podczas wczytywania mapowań z arkusza: {e}")

def main_loop():
    """Główna pętla programu"""
    
    # ✅ ZAINICJALIZUJ GRACEFUL SHUTDOWN
    shutdown_manager, previous_state = init_graceful_shutdown()
    logging.info('🔧 Graceful shutdown zainicjalizowany')
    
    # ✅ AUTOMATYCZNE CZYSZCZENIE LOGÓW PRZY STARCIE
    auto_cleanup_logs(max_days=3, max_size_mb=50)
    
    # ✅ STWÓRZ RATE LIMITERY
    limiters = create_api_limiters()
    logging.info("🚦 Zainicjalizowano rate limitery")
    
    email_handler = EmailHandler()
    sheets_handler = SheetsHandler()
    
    # ✅ USTAW REFERENCJE DO HANDLERÓW
    set_handlers(email_handler, sheets_handler)
    set_main_loop_running(True)
    
    # ✅ URUCHOM HEALTH CHECK SERVER
    try:
        from health_check import start_health_server
        health_thread = threading.Thread(target=start_health_server, args=(8081,), daemon=True)
        health_thread.start()
        logging.info('🏥 Uruchomiono health check server na porcie 8081')
    except Exception as e:
        logging.warning(f'⚠️ Nie udało się uruchomić health check: {e}')
        
    if getattr(config, 'EMAIL_TRACKING_MODE', 'CONFIG') == 'ACCOUNTS':
        logging.info("🚀 Uruchamianie w trybie ACCOUNTS: Kontrola przez Arkusz Google")
    else:
        logging.info("🚀 Uruchamianie w trybie CONFIG: Stała lista z pliku")

    first_run = True

    logging.info("--- Uruchamianie procedury czyszczenia zakończonych zamówień ---")
    sheets_handler.check_and_archive_delivered_orders()

    while True:
        # ✅ SPRAWDŹ CZY ZAŻĄDANO ZAMKNIĘCIA
        if is_shutdown_requested():
            logging.info('🛑 Wykryto żądanie zamknięcia - zatrzymuję główną pętlę')
            break
            
        try:
            logging.info(f"Sprawdzanie e-maili: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # ✅ RATE LIMIT PRZED POŁĄCZENIEM Z SHEETS
            limiters.wait_for("sheets_read")
            
            # Inicjalizuj połączenie z Google Sheets
            if not sheets_handler.connect():
                logging.error("Nie można połączyć się z arkuszem Google.")
                return

            email_availability_manager = EmailAvailabilityManager(sheets_handler)
            
            # ✅ RATE LIMIT PRZED WCZYTANIEM MAPOWAŃ
            limiters.wait_for("sheets_read")
            
            # Wczytaj istniejące mapowania
            load_mappings_from_sheet(sheets_handler, email_handler)
            
            # ✅ RATE LIMIT PRZED SPRAWDZANIEM EMAILI
            limiters.wait_for("imap")
            
            # Pobieranie nowych e-maili
            processed_emails = email_handler.process_emails(sheets_handler=sheets_handler)
            logging.info(f"Przetworzono {len(processed_emails)} nowych e-maili")
            
            # ✅ ZWIĘKSZ LICZNIK PRZETWORZONYCH EMAILI
            if processed_emails:
                increment_processed_emails(len(processed_emails))
            
            # Przetwarzanie otrzymanych danych
            for order_data in processed_emails:
                # ✅ SPRAWDŹ CZY ZAŻĄDANO ZAMKNIĘCIA (w środku pętli)
                if is_shutdown_requested():
                    logging.info('🛑 Przerwano przetwarzanie emaili - żądanie zamknięcia')
                    break
                
                # Pobierz przewoźnika
                carrier_name = order_data.get("carrier", "InPost")
                logging.info(f"PRZEWOZNIK TO: {carrier_name}")
                
                if carrier_name in sheets_handler.carriers:
                    carrier = sheets_handler.carriers[carrier_name]
                    
                    # ✅ RATE LIMIT PRZED AKTUALIZACJĄ SHEETS
                    limiters.wait_for("sheets_write")
                    
                    # Wywołaj process_notification dla przewoźników obsługujących tę metodę
                    if hasattr(carrier, 'process_notification'):
                        carrier.process_notification(order_data)
                        if order_data["status"] == "pickup":
                            send_pickup_notification(order_data)
                    else:
                        # Standardowa obsługa dla przewoźników bez metody process_notification
                        if order_data["status"] == "confirmed":
                            logging.info(f"Aktualizacja potwierdzonego zamówienia: {order_data.get('order_number')}")
                            sheets_handler.update_confirmed_order(order_data)
                        
                        elif order_data["status"] == "delivered":
                            logging.info(f"Aktualizacja dostarczonej paczki: {order_data.get('package_number')}")
                            sheets_handler.update_delivered_order(order_data)
                        
                        elif order_data["status"] == "canceled":
                            logging.info(f"Aktualizacja anulowanego zamówienia: {order_data.get('order_number')}")
                            sheets_handler.update_canceled_order(order_data)
                        
                        elif order_data["status"] == "pickup":
                            logging.info(f"Aktualizacja paczki gotowej do odbioru: {order_data.get('package_number')}")
                            if sheets_handler.update_pickup_status(order_data):
                                # Wysyłanie powiadomienia e-mail
                                send_pickup_notification(order_data)
                        
                        elif order_data["status"] == "transit":
                            logging.info(f"Aktualizacja paczki w transporcie: {order_data.get('package_number')}")
                            
                            # Szukamy zamówienia po numerze zamówienia
                            row = None
                            if order_data.get("order_number"):
                                row = sheets_handler.find_order_row(order_data["order_number"])
                            
                            # Jeśli nie znaleziono, szukamy po numerze paczki
                            if not row and order_data.get("package_number"):
                                row = sheets_handler.find_package_row(order_data["package_number"])
                            
                            # Jeśli znaleziono wiersz, aktualizujemy numer paczki
                            if row:
                                # ✅ ZMIANA: Aktualizuj numer paczki w kolumnie O (15)
                                sheets_handler.worksheet.update_cell(row, 15, order_data["package_number"])
                                logging.info(f"Zaktualizowano numer paczki dla zamówienia w wierszu {row}")
                            else:
                                logging.warning(f"Nie znaleziono pasującego zamówienia dla paczki {order_data.get('package_number')}")
                        
                        elif order_data["status"] == "shipment_sent":
                            logging.info(f"Aktualizacja nadanej przesyłki: {order_data.get('package_number')}")
                            
                            # Pobierz przewoźnika
                            carrier_name = order_data.get("carrier", "InPost")
                            if carrier_name in sheets_handler.carriers:
                                carrier = sheets_handler.carriers[carrier_name]
                                
                                # Szukaj wiersza po numerze przesyłki
                                row = None
                                package_number = order_data.get("package_number")
                                if package_number:
                                    # ✅ ZMIANA: Szukaj wiersza po numerze paczki (kolumna O = 15)
                                    cell = sheets_handler.worksheet.find(package_number, in_column=15)
                                    if cell:
                                        row = cell.row
                                        logging.info(f"Znaleziono przesyłkę {package_number} w wierszu {row}")
                                        
                                # Zaktualizuj wiersz lub utwórz nowy
                                if row:
                                    carrier.update_shipment_sent(row, order_data)
                                else:
                                    # Szukaj wiersza dla użytkownika
                                    user_key = order_data.get("user_key")
                                    if user_key:
                                        rows = sheets_handler.find_user_rows(user_key)
                                        if rows:
                                            row = rows[0]  # Użyj pierwszego znalezionego wiersza
                                            logging.info(f"Użyto wiersza użytkownika {user_key}: {row}")
                                            carrier.update_shipment_sent(row, order_data)
                                        else:
                                            # Utwórz nowy wiersz
                                            logging.info(f"Tworzenie nowego wiersza dla przesyłki {package_number}")
                                            carrier.create_shipment_row(order_data)
                                    else:
                                        logging.warning(f"Brak user_key dla przesyłki {package_number}")
                            else:
                                logging.warning(f"Nieznany przewoźnik: {carrier_name}")

                if order_data.get("status") == "delivered":
                    user_key = order_data.get("user_key")
                    logging.info(f"🧹 Status 'delivered'. Usuwam mapowanie dla {user_key}...")
                    
                    # Wywołaj usuwanie i sprawdź czy usunięto całego usera
                    user_deleted = email_handler.remove_user_mapping(
                        user_key,
                        order_data.get("package_number"),
                        order_data.get("order_number")
                    )
                    
                    # Jeśli użytkownik został całkowicie usunięty z JSONa (bo nie ma innych paczek)
                    if user_deleted:
                        logging.info(f"👤 Użytkownik {user_key} nie ma więcej paczek. Zwalniam konto w Accounts...")
                        
                        # Pobierz pełny email z danych zamówienia
                        email_address = order_data.get("email")
                        
                        # Użyj managera dostępności żeby wyczyścić arkusz
                        if email_address:
                            # Musisz utworzyć instancję managera, jeśli jej nie masz w tym miejscu
                            # W main_loop zazwyczaj jest 'email_availability_manager' zadeklarowany wyżej
                            if 'email_availability_manager' in locals():
                                email_availability_manager.free_up_account(email_address)
                            else:
                                # Fallback (tworzymy na chwilę)
                                temp_manager = EmailAvailabilityManager(sheets_handler)
                                temp_manager.free_up_account(email_address)

            # ✅ SPRAWDZAJ MAILE TYLKO GDY BYŁY ZMIANY
            if len(processed_emails) > 0 or first_run:
                limiters.wait_for("sheets_read")
                
                if first_run:
                    logging.info("🚀 PIERWSZE URUCHOMIENIE: Aktualizacja statusów kont i kolorów...")
                else:
                    logging.info("🔍 NOWE MAILE: Aktualizacja statusów kont...")

                try:
                    email_availability_manager.check_email_availability()
                    logging.info("✅ Statusy kont i kolory zostały odświeżone")
                except Exception as e:
                    logging.error(f"❌ Błąd podczas sprawdzania dostępności maili: {e}")
                
                # ✅ 3. Ważne: Wyłącz flagę po pierwszym wykonaniu
                first_run = False
            else:
                logging.debug("⏳ Brak nowych maili - pomijam odświeżanie arkusza Accounts")
            
            # ✅ OKRESOWE ZAPISYWANIE STANU I MONITORING
            loop_counter = getattr(main_loop, 'counter', 0)
            main_loop.counter = loop_counter + 1

            if loop_counter % 10 == 0:  # co 10 iteracji
                save_periodic_state()
                
            if loop_counter % 100 == 0:  # co 100 iteracji
                memory = psutil.virtual_memory().percent
                disk = psutil.disk_usage('/').percent
                stats = get_stats()
                
                logging.info(f"📊 STATYSTYKI - Iteracja: {loop_counter}, Emaile: {stats['processed_emails']}, Uptime: {stats['uptime']}")
                
                if memory > 80:
                    logging.warning(f"⚠️ Wysokie użycie RAM: {memory}%")
                if disk > 90:
                    logging.warning(f"⚠️ Wysokie użycie dysku: {disk}%")
            
            # ✅ DODAJ TUTAJ NA KOŃCU KAŻDEJ ITERACJI
            logging.info("🔧 DEBUG: Przed increment_iterations()")
            increment_iterations()
            logging.info("🔧 DEBUG: Po increment_iterations()")
            save_periodic_state()
            
            # Czekaj określoną ilość czasu
            if hasattr(config, 'QUICK_CHECK') and config.QUICK_CHECK:
                logging.info(f"Oczekiwanie {config.TEST_INTERVAL} sekund do następnego sprawdzenia")
                time.sleep(config.TEST_INTERVAL)
            else:
                logging.info(f"Oczekiwanie {config.CHECK_INTERVAL} minut do następnego sprawdzenia")
                time.sleep(config.CHECK_INTERVAL * 60)
                
        except Exception as e:
            logging.error(f"Błąd w głównej pętli: {e}")
            logging.error(f"Szczegóły: {traceback.format_exc()}")
            
            # ✅ DODAJ TUTAJ TEŻ (nawet przy błędzie)
            increment_iterations()
            save_periodic_state()
    
            # Różne czasy oczekiwania dla różnych błędów
            if "ConnectionError" in str(e) or "TimeoutError" in str(e):
                logging.warning("Błąd połączenia - czekam 60 sekund")
                time.sleep(60)
            elif "quota" in str(e).lower() or "limit" in str(e).lower():
                logging.warning("Błąd limitu API - czekam 300 sekund")
                time.sleep(300)
            else:
                time.sleep(30)
    
    # ✅ USTAW FLAGĘ ZAKOŃCZENIA DZIAŁANIA
    set_main_loop_running(False)
    logging.info('🏁 Główna pętla zakończona')

# Dodaj na końcu pliku main.py

def test_single_run():
    """Funkcja do lokalnego testowania - wykonuje tylko jedno sprawdzenie"""
    email_handler = EmailHandler()
    sheets_handler = SheetsHandler()
    
    # Inicjalizuj połączenie z Google Sheets
    if not sheets_handler.connect():
        logging.error("Nie można połączyć się z arkuszem Google. Sprawdź uprawnienia i połączenie internetowe.")
        return
    
    logging.info("Uruchomiono test systemu śledzenia zamówień AliExpress")
    
    # Przetwarzanie e-maili
    processed_emails = email_handler.process_emails()
    logging.info(f"Przetworzono {len(processed_emails)} nowych e-maili")
    
    # Uzupełniamy brakujące powiązania
    for order_data in processed_emails:
        # Jeśli mamy nazwę użytkownika, ale brakuje numeru zamówienia lub paczki
        if order_data.get("recipient_name"):
            # Uzupełnij numer zamówienia jeśli brakuje
            if not order_data.get("order_number"):
                order_number = email_handler._get_order_by_user(order_data["recipient_name"])
                if order_number:
                    order_data["order_number"] = order_number
                    logging.info(f"Uzupełniono numer zamówienia {order_number} dla użytkownika {order_data['recipient_name']}")
                    
            # Uzupełnij numer paczki jeśli brakuje
            if not order_data.get("package_number"):
                package_number = email_handler._get_package_by_user(order_data["recipient_name"])
                if package_number:
                    order_data["package_number"] = package_number
                    logging.info(f"Uzupełniono numer paczki {package_number} dla użytkownika {order_data['recipient_name']}")
    
    for order_data in processed_emails:
        logging.info(f"Przetworzono email ze statusem: {order_data['status']}")
        if order_data["status"] == "confirmed":
            logging.info(f"Aktualizacja potwierdzonego zamówienia: {order_data.get('order_number')}")
            sheets_handler.update_confirmed_order(order_data)
        
        elif order_data["status"] == "delivered":
            logging.info(f"Aktualizacja dostarczonej paczki: {order_data.get('package_number')}")
            sheets_handler.update_delivered_order(order_data)
        
        elif order_data["status"] == "canceled":
            logging.info(f"Aktualizacja anulowanego zamówienia: {order_data.get('order_number')}")
            sheets_handler.update_canceled_order(order_data)
        
        elif order_data["status"] == "pickup":
            logging.info(f"Aktualizacja paczki gotowej do odbioru: {order_data.get('package_number')}")
            sheets_handler.update_pickup_status(order_data)  # NOWA FUNKCJA
            if not config.TEST_MODE:
                send_pickup_notification(order_data)
        
        elif order_data["status"] == "transit":
            logging.info(f"Aktualizacja paczki w transporcie: {order_data.get('package_number')}")
            
            # Szukamy zamówienia po numerze zamówienia
            row = None
            if order_data.get("order_number"):
                row = sheets_handler.find_order_row(order_data["order_number"])
            
            # Jeśli nie znaleziono, szukamy po numerze paczki
            if not row and order_data.get("package_number"):
                row = sheets_handler.find_package_row(order_data["package_number"])
            
            # Jeśli znaleziono wiersz, aktualizujemy numer paczki
            if row:
                # ✅ ZMIANA: Aktualizuj numer paczki w kolumnie O (15)
                sheets_handler.worksheet.update_cell(row, 15, order_data["package_number"])
                logging.info(f"Zaktualizowano numer paczki dla zamówienia w wierszu {row}")
            else:
                logging.warning(f"Nie znaleziono pasującego zamówienia dla paczki {order_data.get('package_number')}")
    
    logging.info("Test zakończony")

def print_mappings(sheets_handler, email_handler):
    """Funkcja diagnostyczna do wyświetlania wszystkich mapowań"""
    print("\n--- OBECNIE ZAPISANE MAPOWANIA ---")
    
    # 1. Mapowania użytkowników do zamówień
    if hasattr(sheets_handler, 'user_to_orders'):
        print("\nMapowania użytkownik -> zamówienia:")
        print(f"Liczba mapowań: {len(sheets_handler.user_to_orders)}")
        for user_key, order_numbers in sheets_handler.user_to_orders.items():
            print(f"  {user_key}: {', '.join(order_numbers)}")
    else:
        print("\nBrak mapowań użytkownik -> zamówienia (atrybut nie istnieje)")
    
    # 2. Mapowania email -> user_key
    if hasattr(email_handler, 'email_to_user'):
        print("\nMapowania email -> user_key:")
        print(f"Liczba mapowań: {len(email_handler.email_to_user)}")
        for email, user in email_handler.email_to_user.items():
            print(f"  {email} -> {user}")
    else:
        print("\nBrak mapowań email -> user_key (atrybut nie istnieje)")
    
    # 3. Pokaż wszystkie wiersze w arkuszu
    try:
        print("\nWiersze z arkusza (numer zamówienia i email):")
        values = sheets_handler.worksheet.get_all_values()
        print(f"Arkusz zawiera {len(values)} wierszy (łącznie z nagłówkiem)")
        for i, row in enumerate(values):
            if i == 0:  # Nagłówek
                continue
            if len(row) >= 13:  # ✅ Upewnij się, że wiersz ma wystarczająco dużo kolumn
                email = row[0] if row[0] else "brak"
                order = row[12] if row[12] else "brak" # ✅ Kolumna M (12)
                print(f"  Wiersz {i+1}: Email: {email}, Zamówienie: {order}")
    except Exception as e:
        print(f"Błąd podczas pobierania danych z arkusza: {e}")
    
    print("\n--- KONIEC MAPOWAŃ ---\n")

def show_diagnostic_menu():
    email_handler = EmailHandler()
    sheets_handler = SheetsHandler()
    sheets_handler.connect()
    
    while True:
        print("\n" + "="*50)
        print("🔧 MENU DIAGNOSTYCZNE - AliExpress Tracker")
        print("="*50)
        print("📊 PODSTAWOWE:")
        print("1. Wyświetl mapowania")
        print("2. Testowe uruchomienie (single run)")
        print("3. Uruchom główną pętlę")
        print()
        print("🧹 ZARZĄDZANIE LOGAMI:")
        print("4. Wyczyść stare logi (3 dni)")
        print("5. Informacje o logach")
        print("6. Automatyczne czyszczenie logów")
        print()
        print("📈 STATYSTYKI I MONITORING:")
        print("7. Statystyki rate limiterów")
        print("8. Status graceful shutdown")
        print("9. Sprawdź health check")
        print("10. Test zasobów systemowych")
        print()
        print("🧪 TESTY:")
        print("11. Test rate limitera")
        print("12. Test graceful shutdown")
        print("13. Test health check endpoint")
        print()
        print("⚙️ KONFIGURACJA:")
        print("14. Pokaż aktualną konfigurację")
        print("15. Stan plików aplikacji")
        print()
        print("🤖 AI/API:")
        print("17. Test OpenAI/GitHub Models API")
        print()
        print("0. Wyjście")
        print("="*50)
        
        choice = input("🎯 Wybierz opcję: ").strip()
        
        # ✅ KONWERSJA NA INT I UŻYCIE MATCH-CASE
        try:
            option = int(choice)
        except ValueError:
            if choice.lower() == "q":
                option = 0
            else:
                print("❌ Nieprawidłowa opcja. Wprowadź numer.")
                continue
        
        match option:
            case 0:
                print("👋 Do widzenia!")
                break
                
            case 1:
                print("\n📋 === MAPOWANIA ===")
                print_mappings(sheets_handler, email_handler)
                
            case 2:
                print("\n🧪 === TESTOWE URUCHOMIENIE ===")
                test_single_run()
                
            case 3:
                print("\n🚀 === GŁÓWNA PĘTLA ===")
                try:
                    print("Uruchamianie głównej pętli. Wciśnij Ctrl+C aby przerwać.")
                    main_loop()
                except KeyboardInterrupt:
                    print("\n🛑 Przerwano działanie głównej pętli.")
                    
            case 4:
                print("\n🧹 === CZYSZCZENIE STARYCH LOGÓW ===")
                result = cleanup_old_logs(days=3)
                if result["status"] == "success":
                    print(f"✅ Wyczyszczono {result['removed_lines']} starych linii")
                    print(f"📊 Pozostało {result['remaining_lines']} linii")
                else:
                    print(f"❌ Błąd: {result['message']}")
                    
            case 5:
                print("\n📊 === INFORMACJE O LOGACH ===")
                info = get_log_info()
                if info["status"] == "success":
                    print(f"📁 Plik: {info['file']}")
                    print(f"📊 Rozmiar: {info['size_mb']} MB ({info['size_bytes']:,} bajtów)")
                    print(f"📄 Liczba linii: {info['total_lines']:,}")
                    print(f"📅 Najstarszy log: {info['oldest_log']}")
                    print(f"📅 Najnowszy log: {info['newest_log']}")
                    print(f"📝 Ostatnia modyfikacja: {info['modified']}")
                    if "oldest_age_days" in info:
                        print(f"⏰ Wiek najstarszego loga: {info['oldest_age_days']} dni")
                else:
                    print(f"❌ {info['message']}")
                    
            case 6:
                print("\n🤖 === AUTOMATYCZNE CZYSZCZENIE LOGÓW ===")
                result = auto_cleanup_logs(max_days=3, max_size_mb=50)
                if result["status"] == "success":
                    print(f"✅ Operacja zakończona pomyślnie")
                    if "removed_lines" in result:
                        print(f"📊 Usunięto {result['removed_lines']} linii")
                elif result["status"] == "ok":
                    print(f"✅ {result['message']}")
                else:
                    print(f"❌ Błąd: {result['message']}")
                    
            case 7:
                print("\n📈 === STATYSTYKI RATE LIMITERÓW ===")
                try:
                    limiters = create_api_limiters()
                    limiters.print_stats()
                except Exception as e:
                    print(f"❌ Błąd: {e}")
                    
            case 8:
                print("\n🛡️ === STATUS GRACEFUL SHUTDOWN ===")
                try:
                    from graceful_shutdown import get_stats
                    stats = get_stats()
                    print(f"⏰ Uptime: {stats['uptime']}")
                    print(f"📧 Przetworzonych emaili: {stats['processed_emails']}")
                    print(f"🔄 Iteracji: {stats['total_iterations']}")
                    print(f"📈 Emaili na godzinę: {stats['emails_per_hour']}")
                    print(f"🚀 Start: {stats['start_time']}")
                    print(f"🔄 Działanie: {'✅ TAK' if stats['running'] else '❌ NIE'}")
                    print(f"🛑 Zamknięcie: {'⚠️ TAK' if stats['shutdown_requested'] else '✅ NIE'}")
                except Exception as e:
                    print(f"❌ Błąd: {e}")
                    
            case 9:
                print("\n🏥 === SPRAWDZENIE HEALTH CHECK ===")
                try:
                    response = requests.get('http://localhost:8080', timeout=5)
                    print(f"📡 Status HTTP: {response.status_code}")
                    print(f"📊 Odpowiedź:")
                    print(json.dumps(response.json(), indent=2, ensure_ascii=False))
                except requests.exceptions.ConnectionError:
                    print("❌ Health check server nie działa na porcie 8080")
                    print("💡 Uruchom główną pętlę aby aktywować health check")
                except Exception as e:
                    print(f"❌ Błąd: {e}")
                    
            case 10:
                print("\n💻 === ZASOBY SYSTEMOWE ===")
                try:
                    memory = psutil.virtual_memory()
                    disk = psutil.disk_usage('/')
                    cpu_percent = psutil.cpu_percent(interval=1)
                    
                    print(f"🧠 RAM: {memory.percent:.1f}% ({memory.used/1024/1024/1024:.1f}GB / {memory.total/1024/1024/1024:.1f}GB)")
                    print(f"💾 Dysk: {disk.percent:.1f}% ({disk.used/1024/1024/1024:.1f}GB / {disk.total/1024/1024/1024:.1f}GB)")
                    print(f"⚡ CPU: {cpu_percent:.1f}%")
                    
                    # Ostrzeżenia kolorowe
                    warnings = []
                    if memory.percent > 80:
                        warnings.append(f"⚠️ Wysokie użycie RAM: {memory.percent:.1f}%")
                    if disk.percent > 90:
                        warnings.append(f"⚠️ Mało miejsca na dysku: {disk.percent:.1f}%")
                    if cpu_percent > 80:
                        warnings.append(f"⚠️ Wysokie użycie CPU: {cpu_percent:.1f}%")
                    
                    if warnings:
                        print("\n🚨 OSTRZEŻENIA:")
                        for warning in warnings:
                            print(f"  {warning}")
                    else:
                        print("\n✅ Wszystkie zasoby w normie")
                        
                except Exception as e:
                    print(f"❌ Błąd: {e}")
                    
            case 11:
                print("\n🧪 === TEST RATE LIMITERA ===")
                try:
                    from rate_limiter import SimpleRateLimiter
                    
                    print("Tworzę limiter: 3 wywołania na 5 sekund")
                    limiter = SimpleRateLimiter(max_calls=3, time_window=5, name="TEST")
                    
                    print("Wykonuję 5 testowych wywołań...")
                    for i in range(5):
                        start = time.time()
                        print(f"  {i+1}/5: Wywołanie...")
                        limiter.wait_if_needed()
                        elapsed = time.time() - start
                        if elapsed > 0.1:
                            print(f"    ⏱️ Czekano: {elapsed:.2f}s")
                        else:
                            print(f"    ✅ Bez oczekiwania")
                        time.sleep(0.2)
                        
                    print("✅ Test rate limitera zakończony")
                except Exception as e:
                    print(f"❌ Błąd: {e}")
                    
            case 12:
                print("\n🧪 === TEST GRACEFUL SHUTDOWN ===")
                try:
                    from graceful_shutdown import get_stats
                    
                    print("🔍 Sprawdzanie stanu graceful shutdown...")
                    stats = get_stats()
                    
                    if stats['shutdown_requested']:
                        print("⚠️ Graceful shutdown jest w trakcie wykonywania")
                    else:
                        print("✅ Graceful shutdown jest aktywny i gotowy")
                        
                    print("\n💡 Aby przetestować faktyczne zamknięcie:")
                    print("   1. Uruchom główną pętlę (opcja 3)")
                    print("   2. Naciśnij Ctrl+C")
                    print("   3. Obserwuj komunikaty graceful shutdown")
                    
                except Exception as e:
                    print(f"❌ Błąd: {e}")
                    
            case 13:
                print("\n🧪 === TEST HEALTH CHECK ENDPOINT ===")
                try:
                    # Sprawdź czy health server działa
                    try:
                        response = requests.get('http://localhost:8080', timeout=2)
                        print("✅ Health check server już działa")
                    except requests.exceptions.ConnectionError:
                        print("🚀 Uruchamiam health check server...")
                        from health_check import start_health_server
                        import threading
                        thread = threading.Thread(target=start_health_server, args=(8080,), daemon=True)
                        thread.start()
                        time.sleep(2)  # ✅ Teraz time jest dostępne
                    
                    # Test endpoint
                    print("📡 Testowanie endpoint...")
                    response = requests.get('http://localhost:8080', timeout=5)
                    
                    print(f"📊 Status: {response.status_code}")
                    print("📋 Odpowiedź:")
                    print(json.dumps(response.json(), indent=2, ensure_ascii=False))
                    print(f"\n🔗 Endpoint dostępny: http://localhost:8080")
                    
                except Exception as e:
                    print(f"❌ Błąd: {e}")
                    import traceback
                    print(f"🔍 Szczegóły: {traceback.format_exc()}")
                    
            case 14:
                print("\n⚙️ === AKTUALNA KONFIGURACJA ===")
                try:
                    import config
                    print(f"📧 Test mode: {getattr(config, 'TEST_MODE', '❌ undefined')}")
                    print(f"⏱️ Check interval: {getattr(config, 'CHECK_INTERVAL', '❌ undefined')} min")
                    print(f"🚀 Quick check: {getattr(config, 'QUICK_CHECK', '❌ undefined')}")
                    print(f"⚡ Test interval: {getattr(config, 'TEST_INTERVAL', '❌ undefined')} s")
                    
                    # OpenAI config (maskowanie klucza)
                    if hasattr(config, 'OPENAI_API_KEY'):
                        key = config.OPENAI_API_KEY
                        if len(key) > 12:
                            masked_key = f"{key[:8]}...{key[-4:]}"
                        else:
                            masked_key = "***"
                        print(f"🤖 OpenAI API: {masked_key}")
                    else:
                        print(f"🤖 OpenAI API: ❌ undefined")
                        
                    # Google Sheets
                    creds_exists = os.path.exists('credentials.json')
                    token_exists = os.path.exists('token.json')
                    print(f"📊 Google credentials: {'✅' if creds_exists else '❌'}")
                    print(f"📊 Google token: {'✅' if token_exists else '❌'}")
                    
                except Exception as e:
                    print(f"❌ Błąd: {e}")
                    
            case 15:
                print("\n📁 === STAN PLIKÓW APLIKACJI ===")
                files_to_check = [
                    ('app_state.json', 'Stan aplikacji'),
                    ('aliexpress_tracker.log', 'Logi główne'),
                    ('credentials.json', 'Google credentials'),
                    ('token.json', 'Google token'),
                    ('config.py', 'Konfiguracja'),
                    ('rate_limiter.py', 'Rate limiter'),
                    ('graceful_shutdown.py', 'Graceful shutdown'),
                    ('health_check.py', 'Health check'),
                    ('log_cleaner.py', 'Log cleaner')
                ]
                
                for filename, description in files_to_check:
                    if os.path.exists(filename):
                        size = os.path.getsize(filename)
                        mtime = datetime.fromtimestamp(os.path.getmtime(filename))
                        
                        # Formatowanie rozmiaru
                        if size < 1024:
                            size_str = f"{size} B"
                        elif size < 1024 * 1024:
                            size_str = f"{size/1024:.1f} KB"
                        else:
                            size_str = f"{size/1024/1024:.1f} MB"
                            
                        print(f"✅ {filename:<25} ({description})")
                        print(f"   📊 Rozmiar: {size_str}, 📅 Modyfikacja: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
                    else:
                        print(f"❌ {filename:<25} ({description}) - BRAK")
                        
            case 16:
                print("\n🧪 === TEST INCREMENT ITERATIONS ===")
                try:
                    from graceful_shutdown import get_stats, increment_iterations, save_periodic_state
                    
                    print("📊 Stan przed testem:")
                    stats_before = get_stats()
                    print(f"  Iteracje: {stats_before.get('iterations', 0)}")
                    print(f"  Total iteracje: {stats_before.get('total_iterations', 0)}")
                    
                    print("\n🔄 Wykonuję increment_iterations()...")
                    increment_iterations()
                    save_periodic_state()
                    
                    print("📊 Stan po teście:")
                    stats_after = get_stats()
                    print(f"  Iteracje: {stats_after.get('iterations', 0)}")
                    print(f"  Total iteracje: {stats_after.get('total_iterations', 0)}")
                    
                    if stats_after.get('iterations', 0) > stats_before.get('iterations', 0):
                        print("✅ increment_iterations() działa poprawnie!")
                    else:
                        print("❌ increment_iterations() nie zwiększa licznika!")
                        
                except Exception as e:
                    print(f"❌ Błąd: {e}")
                    import traceback
                    print(f"🔍 Szczegóły: {traceback.format_exc()}")

            case 17:
                print("\n🤖 === TEST OPENAI/GITHUB MODELS API ===")
                try:
                    from openai_handler import OpenAIHandler
                    
                    print("🔍 Inicjalizacja OpenAI Handler...")
                    openai_handler = OpenAIHandler()
                    
                    print(f"🔑 API Key: {openai_handler.api_key[:8]}...{openai_handler.api_key[-4:]}")
                    print(f"🌐 Base URL: {openai_handler.client.base_url}")
                    
                    print("\n📤 Wysyłam testowe zapytanie do API...")
                    print("   Prompt: 'Odpowiedz krótko: Czy API działa?'")
                    
                    test_response = openai_handler.client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": "Jesteś pomocnym asystentem. Odpowiadaj krótko."},
                            {"role": "user", "content": "Odpowiedz krótko: Czy API działa?"}
                        ],
                        max_tokens=50,
                        temperature=0.7
                    )
                    
                    response_text = test_response.choices[0].message.content
                    
                    print("\n✅ API DZIAŁA POPRAWNIE!")
                    print(f"📨 Odpowiedź: {response_text}")
                    print(f"🔢 Model: {test_response.model}")
                    print(f"💰 Tokens użyte: {test_response.usage.total_tokens}")
                    print(f"   - Prompt: {test_response.usage.prompt_tokens}")
                    print(f"   - Completion: {test_response.usage.completion_tokens}")
                    
                    print("\n🎯 Test pełnej analizy emaila InPost...")
                    test_subject = "Paczka 123456789 jest gotowa do odbioru w Paczkomacie"
                    test_body = """
                    Twoja paczka o numerze 123456789 czeka na odbiór w Paczkomacie POZ01M.
                    Adres: ul. Testowa 1, 60-123 Poznań
                    Kod odbioru: 123456
                    Termin odbioru: 15.01.2026
                    """
                    
                    print(f"   Temat: {test_subject}")
                    result = openai_handler.extract_pickup_notification_data_inpost(test_body, test_subject, "test@interia.pl")
                    
                    if result and result != {}:
                        print("\n✅ Analiza zakończona sukcesem!")
                        print("📊 Wynik analizy:")
                        print(json.dumps(result, indent=2, ensure_ascii=False))
                    else:
                        print("\n⚠️ API zwróciło pusty wynik")
                        
                except Exception as e:
                    print(f"\n❌ BŁĄD API: {e}")
                    import traceback
                    print(f"\n🔍 Szczegóły:")
                    print(traceback.format_exc())
                    
                    print("\n💡 Możliwe przyczyny:")
                    print("   1. Nieprawidłowy klucz API")
                    print("   2. Nieznany model (używaj 'gpt-4o' dla GitHub Models)")
                    print("   3. Przekroczony limit requestów")
                    print("   4. Problem z połączeniem internetowym")
            
            case _:  # default case
                print("❌ Nieprawidłowa opcja. Wybierz numer od 0 do 17.")
        
        input("\n⏎ Naciśnij Enter aby kontynuować...")


def run_reprocess(target_email, limit=None):
    # np. python3 main.py --reprocess-email znowu.ja1@interia.pl --limit 5
    logging.info(f"🛠️ URUCHAMIAM TRYB REPROCESS DLA: {target_email}")
    if limit:
        logging.info(f"🔢 Cel: Przetworzyć {limit} zamówień (zaczynając od najstarszych)")
    
    email_handler = EmailHandler()
    sheets_handler = SheetsHandler()
    
    if not sheets_handler.connect():
        logging.error("❌ Błąd połączenia z arkuszem.")
        return

    # 1. Pobierz WSZYSTKIE maile z okresu
    emails = email_handler.fetch_specific_account_history(target_email, days_back=60)
    
    if not emails:
        logging.warning("Brak maili do przetworzenia.")
        return

    logging.info(f"Pobrano {len(emails)} maili z serwera. Rozpoczynam filtrowanie i analizę...")
    processed_count = 0 
    
    # 2. Przetwarzaj maile
    for source, msg in emails:
        if limit and processed_count >= limit:
            logging.info(f"🛑 Osiągnięto limit {limit} przetworzonych zamówień. Kończę pracę.")
            break

        try:
            email_date = email_handler.extract_email_date(msg)
            raw_subject = msg.get("Subject", "")
            subject = email_handler.decode_email_subject(raw_subject)
            
            keywords = ["paczka", "zamówienie", "order", "delivery", "dostawa", "odbierz", "nadana", "status", "inpost", "dhl", "dpd", "gls", "poczta"]
            if not any(k in subject.lower() for k in keywords):
                continue

            body = email_handler.get_email_body(msg)
            
            to_header = msg.get("To", "")
            recipient = target_email 
            if to_header:
                import re
                email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', to_header)
                if email_match:
                    recipient = email_match.group(0)
            
            logging.info(f"🔍 Reprocess (Znaleziono {processed_count}/{limit if limit else '∞'}): {email_date} | {subject[:50]}...")
            
            order_data = email_handler.analyze_email(
                subject, body, recipient, source, 
                recipient_name=recipient, email_message=msg, email_date=email_date,
                force_process=True 
            )
            
            if order_data:
                if not order_data.get("email_date") and email_date:
                    order_data["email_date"] = email_date
                
                user_key = order_data.get("user_key")
                if user_key:
                    if order_data.get("order_number"):
                        email_handler._save_user_order_mapping(user_key, order_data["order_number"])
                    if order_data.get("package_number"):
                        email_handler._save_user_package_mapping(user_key, order_data["package_number"])

                carrier_name = order_data.get("carrier", "InPost")
                carrier = sheets_handler.carriers.get(carrier_name)
                
                if carrier:
                    carrier.process_notification(order_data)
                    processed_count += 1 
                else:
                    sheets_handler._direct_create_row(order_data)
                    processed_count += 1
                
        except Exception as e:
            logging.error(f"Błąd przy reprocess maila: {e}")

    # --- 🟢 NOWA SEKCJA: AKTUALIZACJA ZAKŁADKI ACCOUNTS ---
    try:
        logging.info("🎨 REPROCESS: Aktualizacja statusów i kolorów w zakładce Accounts...")
        from carriers_sheet_handlers import EmailAvailabilityManager
        availability_manager = EmailAvailabilityManager(sheets_handler)
        availability_manager.check_email_availability()
        logging.info("✅ Zakładka Accounts została zsynchronizowana z nowymi mapowaniami.")
    except Exception as e:
        logging.error(f"❌ Błąd podczas aktualizacji kolorów Accounts po reprocess: {e}")
    # ------------------------------------------------------
            
    logging.info(f"🏁 Zakończono reprocess. Przetworzono skutecznie: {processed_count} zamówień.")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="AliExpress Order Tracker")
    parser.add_argument("--menu", action="store_true", help="Uruchom menu diagnostyczne")
    parser.add_argument("--reprocess-email", type=str, help="Wymuś ponowne przetworzenie maili dla podanego adresu")
    parser.add_argument("--limit", type=int, help="Maksymalna liczba maili do przetworzenia (dla trybu reprocess)")

    args = parser.parse_args()

    if args.menu:
        # Uruchom menu diagnostyczne
        show_diagnostic_menu()
    
    elif args.reprocess_email:
        # ✅ URUCHOM TRYB NAPRAWCZY Z PRZEKAZANIEM LIMITU
        run_reprocess(args.reprocess_email, limit=args.limit)
        
    else:
        # Uruchom główną pętlę (standardowo)
        print("Uruchamianie głównej pętli. Naciśnij Ctrl+C aby zatrzymać.")
        main_loop()