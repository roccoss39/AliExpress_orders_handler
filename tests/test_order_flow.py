import logging
import json
import re
from datetime import datetime

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(levelname)s - %(message)s')

# Utwórzmy mock OpenAIHandler dla testów
class MockOpenAIHandler:
    def extract_order_confirmation_data(self, body, subject, recipient=None):
        # Prosta implementacja dla testów
        if "3054169918883922" in subject or "3054169918883922" in body:
            return {
                "order_number": "3054169918883922",
                "product_name": "20 sztuk/partia JST PH 2.0 2/3/4/5/6P",
                "delivery_address": "Paczkomat SZC15APP przy wejściu do budynku, Żubrów 3, 71-617 Szczecin",
                "phone_number": "228 559 418",
                "customer_name": "lunaewsx@gmail.com"
            }
        return {}
    
    def extract_pickup_notification_data(self, body, subject, recipient=None):
        # Prosta implementacja dla testów
        if "Paczka już na Ciebie czeka" in subject:
            return {
                "pickup_code": "516465",
                "pickup_address": "Szczecin Żubrów 3 przy wejściu do budynku",
                "pickup_location_code": "SZC15APP",
                "pickup_deadline": "17/05/2025 11:21",
                "phone_number": "228 559 418",
                "available_hours": "do 17/05, 11:21"
            }
        return {}
    
    def emergency_extract_inpost_data(self, body, subject):
        # Prosta implementacja dla testów
        if "Paczka już na Ciebie czeka" in subject:
            return {
                "pickup_code": "516465",
                "pickup_location_code": "SZC15APP"
            }
        return {}

# Mock dla EmailHandler
class MockEmailHandler:
    def __init__(self):
        self.user_mappings = {}
        self.openai_handler = MockOpenAIHandler()
        
    def _save_user_order_mapping(self, user_key, order_number):
        if user_key not in self.user_mappings:
            self.user_mappings[user_key] = {"order_numbers": [], "package_numbers": []}
        
        if order_number not in self.user_mappings[user_key]["order_numbers"]:
            self.user_mappings[user_key]["order_numbers"].append(order_number)
            logging.info(f"Zapisano mapowanie użytkownika {user_key} -> zamówienie {order_number}")
    
    def _save_user_package_mapping(self, user_key, package_number):
        if user_key not in self.user_mappings:
            self.user_mappings[user_key] = {"order_numbers": [], "package_numbers": []}
        
        if package_number not in self.user_mappings[user_key]["package_numbers"]:
            self.user_mappings[user_key]["package_numbers"].append(package_number)
            logging.info(f"Zapisano mapowanie użytkownika {user_key} -> paczka {package_number}")

# Importujmy klasy z pliku carriers_data_handlers
from carriers_data_handlers import AliexpressDataHandler, InPostDataHandler

def run_test():
    logging.info("Rozpoczynam test cyklu zamówienia")
    
    # Utwórz mock EmailHandler
    email_handler = MockEmailHandler()
    
    # Utwórz handlery
    aliexpress_handler = AliexpressDataHandler(email_handler)
    inpost_handler = InPostDataHandler(email_handler)
    
    # Czas uruchomienia testu
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logging.info(f"Test uruchomiony: {current_time}")
    
    # 1. Email z potwierdzeniem zamówienia AliExpress
    logging.info("\n--- TEST 1: Potwierdzenie zamówienia AliExpress ---")
    
    subject1 = "Zamówienie 3054169918883922: zamówienie potwierdzone"
    body1 = """
Zamówienie jest przygotowywane
 ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌  ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌  ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌  ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌  ‌ ‌ ‌ ‌ ‌ ‌  ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌
    Szybka dostawa
    
    Darmowe zwroty produ...
.
Witaj, lunaewsx user,
Twoje zamówienie 3054169918883922 zostało potwierdzone. Kliknij poniżej, aby śledzić jego postępy. Możesz spać spokojnie, wiedząc, że otrzymasz aktualizacje dotyczące wszystkich etapów dostawy!
.
 
Śledzenie zamówienia
 
 

.
Potwierdzone	
.
Wysłane	
.
Dostarczone	
.
.
    
20 sztuk/partia JST PH 2.0 2/...
20Pcs 6P Length 30cm	x1
Całkowita kwota zamówienia	3,83zł
Zobacz szczegóły
 
.
Wysyłka do
Paczkomat SZC15APP przy wejściu do budynku, Żubrów 3, 71-617 Szczecin
Szczecin, Zachodniopomorskie
lunaewsx user (+48) 228559418
    """
    
    recipient1 = "lunaewsx@gmail.com"
    
    # Sprawdź czy handler może obsłużyć email
    if aliexpress_handler.can_handle(subject1, body1):
        logging.info("AliexpressDataHandler może obsłużyć ten email")
        
        # Przetwórz email
        result1 = aliexpress_handler.process(subject1, body1, recipient1, "gmail")
        
        # Wyświetl wyniki
        logging.info("Wyniki przetwarzania potwierdzenia zamówienia:")
        for key, value in result1.items():
            logging.info(f"  {key}: {value}")
        
        # Zapisz numer zamówienia do weryfikacji
        order_number = result1.get("order_number")
    else:
        logging.error("AliexpressDataHandler nie może obsłużyć emaila z potwierdzeniem zamówienia!")
    
    # 2. Email z powiadomieniem o paczce InPost
    logging.info("\n--- TEST 2: Powiadomienie o paczce InPost ---")
    
    subject2 = "Twój Appkomat: Paczka już na Ciebie czeka"
    body2 = """
InPost - Out of the Box
InPost	
Przyszło!
Twoja paczka od
Seller using Cainiao logistics services 999999999 dotarła do Appkomatu InPost
SZC15APP
Szczecin Żubrów 3 przy wejściu do budynku.
    
Zamówienie czeka w nowym Appkomacie InPost. Pamiętaj, aby mieć przy odbiorze aplikację lub kod QR!
Tylko dzięki nim odbierzesz paczkę!
Kod QR	
Planując odbiór paczki pamiętaj, że masz czas do
17/05/2025 11:21! Po upływie tego czasu paczka wróci do nadawcy.

To co, wpadasz?
Zobacz na mapie	Zobacz na mapie
Dlaczego do odbioru potrzebujesz aplikacji lub kodu QR?
Appkomat InPost to wyjątkowa maszyna, która nie posiada ekranu. Jest bardziej ekologiczna, zużywa mniej prądu i w ten sposób pozwala zredukować emisję CO2. Zależy nam, żeby świat wokół nas był bardziej zielony już dziś i w przyszłości, na którą wszyscy mamy wpływ.

Odkryj nasz nowy Appkomat InPost!
Czas na odbiór do:
17/05, godzina: 11:21
No chodź już, bo nie lubię być za długo w zamknięciu!
Numer paczki:
696320378571617018718686

Numer telefonu:
+48228559418

Kod odbioru:
516465
    """
    
    recipient2 = "lunaewsx@gmail.com"
    
    # Sprawdź czy handler może obsłużyć email
    if inpost_handler.can_handle(subject2, body2):
        logging.info("InPostDataHandler może obsłużyć ten email")
        
        # Przetwórz email
        result2 = inpost_handler.process(subject2, body2, recipient2, "gmail")
        
        # Wyświetl wyniki
        logging.info("Wyniki przetwarzania powiadomienia o paczce:")
        for key, value in result2.items():
            logging.info(f"  {key}: {value}")
        
        # Zapisz numer paczki do weryfikacji
        package_number = result2.get("package_number")
    else:
        logging.error("InPostDataHandler nie może obsłużyć emaila z powiadomieniem o paczce!")
    
    # 3. Email z potwierdzeniem dostarczenia paczki
    logging.info("\n--- TEST 3: Potwierdzenie dostarczenia paczki ---")
    
    subject3 = "Paczka 696320378571617018718686 została dostarczona"
    body3 = """
Mamy nadzieję, że podobają Ci się Twoje zakupy
 ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌  ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌  ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌  ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌  ‌ ‌ ‌ ‌ ‌ ‌  ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌ ‌
AliExpress
Dostarczono paczkę
Witaj, lunaewsx user,
Twoja paczka 696320378571617018718686 została pomyślnie dostarczona! Poinformuj nas o odbiorze paczki, klikając w tym celu przycisk poniżej. Mamy nadzieję, że podobają Ci się Twoje zakupy!
Zobacz szczegóły
.
.
Szczegóły paczki
.
    
20 sztuk/partia JST PH 2.0 2/3/4/5/6...
20Pcs 6P Length 30cm
x1
    .
.
.
Dostawa do
Paczkomat SZC15APP przy wejściu do budynku, Żubrów 3, 71-617 Szczecin
Szczecin, Zachodniopomorskie
lunaewsx user (+48) 228559418
    """
    
    recipient3 = "lunaewsx@gmail.com"
    
    # Sprawdź który handler może obsłużyć email
    handler_found = False
    
    if aliexpress_handler.can_handle(subject3, body3):
        logging.info("AliexpressDataHandler może obsłużyć ten email")
        result3 = aliexpress_handler.process(subject3, body3, recipient3, "gmail")
        handler_found = True
    
    if not handler_found and inpost_handler.can_handle(subject3, body3):
        logging.info("InPostDataHandler może obsłużyć ten email")
        result3 = inpost_handler.process(subject3, body3, recipient3, "gmail")
        handler_found = True
    
    if handler_found:
        # Wyświetl wyniki
        logging.info("Wyniki przetwarzania potwierdzenia dostarczenia:")
        for key, value in result3.items():
            logging.info(f"  {key}: {value}")
    else:
        logging.error("Żaden handler nie może obsłużyć emaila z potwierdzeniem dostarczenia!")
    
    # Sprawdź mapowania użytkowników
    logging.info("\n--- WYNIKI MAPOWANIA ---")
    logging.info(f"Mapowania użytkowników: {json.dumps(email_handler.user_mappings, indent=2)}")
    
    # Weryfikacja spójności danych
    try:
        user_key = "lunaewsx"
        if user_key in email_handler.user_mappings:
            if order_number in email_handler.user_mappings[user_key]["order_numbers"]:
                logging.info(f"✓ Numer zamówienia {order_number} został prawidłowo zapisany dla użytkownika {user_key}")
            else:
                logging.error(f"✗ Numer zamówienia {order_number} NIE został zapisany dla użytkownika {user_key}")
            
            if package_number in email_handler.user_mappings[user_key]["package_numbers"]:
                logging.info(f"✓ Numer paczki {package_number} został prawidłowo zapisany dla użytkownika {user_key}")
            else:
                logging.error(f"✗ Numer paczki {package_number} NIE został zapisany dla użytkownika {user_key}")
    except Exception as e:
        logging.error(f"Błąd podczas weryfikacji mapowań: {e}")
    
    logging.info("Test zakończony")

if __name__ == "__main__":
    run_test()