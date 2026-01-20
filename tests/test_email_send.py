import logging
import config
# Zakładam, że funkcja send_pickup_notification jest w pliku notification.py
# Jeśli jest w main.py, musisz dostosować import lub wkleić funkcję tutaj.
from notification import send_pickup_notification 

# Konfiguracja logowania, żeby widzieć co się dzieje
logging.basicConfig(level=logging.INFO)

def run_test():
    print("📧 Rozpoczynam test wysyłania maila...")
    print(f"⚙️ Konfiguracja: OD={config.GMAIL_EMAIL} -> DO={config.NOTIFICATION_EMAIL}")

    # Przykładowe dane, jakie normalnie wyciągnąłby bot z maila
    mock_order_data = {
        'package_number': 'TEST-12345-XYZ',
        'receive_code': '888-999',
        'time_to_receive': '2026-01-20 18:00',
        'phone_number': '500 123 456',
        'delivery_address': 'Paczkomat WAW22M, ul. Testowa 1',
        'carrier': 'InPost'
    }

    try:
        success = send_pickup_notification(mock_order_data)
        
        if success:
            print("\n✅ SUKCES! Mail został wysłany.")
            print("Sprawdź skrzynkę odbiorczą (i folder SPAM).")
        else:
            print("\n❌ PORAŻKA. Funkcja zwróciła False.")
            
    except Exception as e:
        print(f"\n❌ BŁĄD KRYTYCZNY: {e}")
        print("Wskazówka: Sprawdź czy w config.py masz Hasło do Aplikacji, a nie zwykłe hasło.")

if __name__ == "__main__":
    run_test()