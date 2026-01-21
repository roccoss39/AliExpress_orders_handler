import logging
import json
import time
import requests
import psutil
from rate_limiter import create_api_limiters
from graceful_shutdown import get_stats
from log_cleaner import cleanup_old_logs, get_log_info
from email_handler import EmailHandler
from sheets_handler import SheetsHandler

def print_mappings(sheets_handler, email_handler):
    """Wyświetla obecne mapowania w konsoli"""
    print("\n--- OBECNIE ZAPISANE MAPOWANIA ---")
    if hasattr(sheets_handler, 'user_to_orders'):
        print(f"\nUżytkownik -> Zamówienia ({len(sheets_handler.user_to_orders)}):")
        for k, v in sheets_handler.user_to_orders.items():
            print(f"  {k}: {v}")
    
    if hasattr(email_handler, 'user_mappings'):
        print(f"\nUser Mappings JSON ({len(email_handler.user_mappings)}):")
        print(json.dumps(email_handler.user_mappings, indent=2, ensure_ascii=False))
    print("\n--- KONIEC MAPOWAŃ ---\n")

def test_single_run():
    """Funkcja do lokalnego testowania"""
    print("🧪 Aby uruchomić test, użyj opcji 3 (Główna Pętla) i przerwij ją Ctrl+C po jednym cyklu.")

def show_diagnostic_menu():
    """Interaktywne menu diagnostyczne"""
    print("🔌 Łączenie z serwisami...")
    email_handler = EmailHandler()
    sheets_handler = SheetsHandler()
    try:
        sheets_handler.connect()
    except:
        print("⚠️ Nie udało się połączyć z arkuszem przy starcie menu.")
    
    while True:
        print("\n" + "="*50)
        print("🔧 MENU DIAGNOSTYCZNE - AliExpress Tracker")
        print("="*50)
        print("1. Wyświetl mapowania")
        print("2. Info o teście")
        print("3. Uruchom główną pętlę (Start Bota)")
        print("4. Wyczyść stare logi (3 dni)")
        print("5. Informacje o logach")
        print("6. Statystyki rate limiterów")
        print("7. Status graceful shutdown")
        print("8. Sprawdź health check")
        print("9. Test zasobów systemowych")
        print("10. Test OpenAI API")
        print("0. Wyjście")
        print("="*50)
        
        choice = input("🎯 Wybierz opcję: ").strip()
        
        if choice == '0':
            print("👋 Do widzenia!")
            break
        elif choice == '3':
            # Importujemy tutaj, żeby uniknąć pętli importów
            from main import main_loop
            print("🚀 Uruchamianie głównej pętli...")
            main_loop()
            return
        
        try:
            if choice == '1': print_mappings(sheets_handler, email_handler)
            elif choice == '2': test_single_run()
            elif choice == '4': 
                res = cleanup_old_logs(3)
                print(res)
            elif choice == '5': print(get_log_info())
            elif choice == '6': create_api_limiters().print_stats()
            elif choice == '7': print(get_stats())
            elif choice == '8':
                try: print(requests.get('http://localhost:8081', timeout=2).json())
                except: print("❌ Health check server nie odpowiada")
            elif choice == '9':
                print(f"🧠 RAM: {psutil.virtual_memory().percent}%")
                print(f"💾 DISK: {psutil.disk_usage('/').percent}%")
            elif choice == '10':
                from openai_handler import OpenAIHandler
                print("⏳ Testowanie OpenAI...")
                handler = OpenAIHandler()
                print(f"✅ Klient utworzony. Base URL: {handler.client.base_url}")
                
        except Exception as e:
            print(f"❌ Błąd: {e}")
            time.sleep(1)