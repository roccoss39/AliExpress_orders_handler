import logging
import re

class BaseDataHandler:
    """Bazowa klasa do obsługi danych z emaili od różnych przewoźników"""
    
    def __init__(self, email_handler):
        """
        Inicjalizacja obiektu handlera
        
        Args:
            email_handler: Referencja do głównego obiektu EmailHandler
            (potrzebna aby używać jego metod, np. _save_user_order_mapping)
        """
        self.email_handler = email_handler
        self.name = "Unknown"
    
    def can_handle(self, subject, body):
        """
        Sprawdza czy ten handler może obsłużyć dany email
        
        Args:
            subject: Temat emaila
            body: Treść emaila
            
        Returns:
            bool: True jeśli handler może obsłużyć email, False w przeciwnym wypadku
        """
        return False
    
    def process(self, subject, body, recipient, email_source, recipient_name=None, email_message=None):
        """
        Przetwarza email i zwraca wyodrębnione dane
        
        Args:
            subject: Temat emaila
            body: Treść emaila
            recipient: Adres email odbiorcy
            email_source: Źródło emaila (gmail, interia itp.)
            recipient_name: Nazwa odbiorcy (opcjonalna)
            
        Returns:
            dict: Słownik z wyodrębnionymi danymi lub None
        """
        # Bazowa implementacja, klasy potomne powinny nadpisać tę metodę
        return None
    
    def parse_delivery_status(self, subject, recipient, body, carrier):
        """
        Zwraca informacje o dostarczeniu przesyłki, jeśli dotyczy.

        Returns:
            dict|None: Słownik ze statusem i emailem lub None
        """
        logging.info(f"SPRAWDZANIE STATUSU DOSTARCZENIA DLA {carrier} w temacie: {subject}")
        keywords = [
            "została dostarczona",
            "doręczone",
            "została dostarczona",
            "zostaładostarczona"
        ]

        for keyword in keywords:
            if (keyword in subject.lower()) or (carrier.lower() == "dhl" and "została odebrana" in body.lower()):
                return {
                    "status": "delivered",
                    "email": recipient,
                    "carrier": carrier
                }
        return None


class AliexpressDataHandler(BaseDataHandler):
    """Klasa do obsługi danych z emaili od AliExpress"""
    
    def __init__(self, email_handler):
        """Inicjalizacja handlera AliExpress"""
        super().__init__(email_handler)
        self.name = "AliExpress"
    
    def can_handle(self, subject, body):
        """Sprawdza czy to email od AliExpress"""
        
        # ✅ TYLKO BARDZO SPECYFICZNE SŁOWA KLUCZOWE
        keywords = [
            "zamówienie potwierdzone",        # Potwierdzenie zamówienia
            "order confirmed",                # Order confirmation
            "potwierdzenie zakupu",          # Purchase confirmation
            "is closed",                     # Order closed
            "zamówienie zostało zamknięte",  # Order closed PL
            "order has been closed",         # Order closed EN
            "delivery notification",         # Delivery notification
            "zamówienie zakończone",         # Order completed
            "order completed",                # Order completed EN
            "zamówienie wysłane"
        ]
        
        # SPRAWDŹ TEMAT
        for keyword in keywords:
            if keyword.lower() in subject.lower():
                logging.info(f"✅ AliExpress: Znaleziono keyword '{keyword}' w temacie")
                return True
        
        # ✅ SPRAWDŹ TREŚĆ - TYLKO BARDZO SPECYFICZNE WSKAŹNIKI
        if body:
            body_sample = body[:1000].lower()
            
            # Sprawdź słowa kluczowe w treści
            for keyword in keywords:
                if keyword.lower() in body_sample:
                    logging.info(f" AliExpress: Znaleziono keyword '{keyword}' w treści emaila")
                    return True
            
        return False
    
    def parse_transit_status(self, subject, recipient, carrier):
        """
        Sprawdza czy to email o przesyłce w drodze
        
        Args:
            subject: Temat emaila
            
        Returns:
            bool: True jeśli to przesyłka w drodze, False w przeciwnym wypadku
        """
        transit_keywords = [
            "zamówienie wysłane"
        ]
        
        for keyword in transit_keywords:
            if keyword in subject.lower():
                logging.info(f"✅ AliExpress: Znaleziono keyword '{keyword}' w temacie. IN TRANSIT")
                return {
                    "status": "transit",
                    "email": recipient,
                    "carrier": carrier
                }
        return False
    def is_closed_order(self, subject):
        """
        Sprawdza czy to email o zamkniętym zamówieniu
        
        Args:
            subject: Temat emaila
            body: Treść emaila
            
        Returns:
            bool: True jeśli to zamknięte zamówienie, False w przeciwnym wypadku
        """
        closed_keywords = [
            "is closed",
            "zamówienie zostało zamknięte", 
            "order has been closed",
            "zamówienie zamknięte",
            "order closed",
            "zamknięto zamówienie",
            "dispute closed",  # Dodatkowe dla AliExpress
            "spór zamknięty"
        ]
        
        for keyword in closed_keywords:
            if keyword in subject.lower():
                return True
        return False
    
    def process(self, subject, body, recipient, email_source, recipient_name=None, email_message=None):
        """
        Przetwarza email od AliExpress używając REGEX (bez dzwonienia do OpenAI).
        Naprawia błąd limitów API i poprawnie wyciąga numer zamówienia.
        """
        import re
        import email.utils
        
        logging.debug(f"Wejscie do fun process AliExpress (Regex): {subject}")
        
        # 1. Wyciągnij datę z obiektu email (jeśli dostępny)
        email_date = None
        if email_message:
            try:
                date_tuple = email.utils.parsedate_tz(email_message.get('Date'))
                if date_tuple:
                    local_date = email.utils.mktime_tz(date_tuple)
                    from datetime import datetime
                    email_date = datetime.fromtimestamp(local_date).strftime('%Y-%m-%d %H:%M:%S')
            except Exception as e:
                logging.warning(f"Błąd daty w handlerze Ali: {e}")

        # 2. Wyciągnij klucz użytkownika
        user_key = recipient.split('@')[0].lower() if recipient and '@' in recipient else "unknown"

        # 3. Rozpoznaj status na podstawie słów kluczowych (lepsze niż sztywne "confirmed")
        status = "unknown"
        subject_lower = subject.lower()
        
        if "wysłane" in subject_lower or "shipped" in subject_lower:
            status = "transit"
        elif "dostarczon" in subject_lower or "delivered" in subject_lower:
            status = "delivered"
        elif "odbioru" in subject_lower or "pickup" in subject_lower:
            status = "pickup"
        elif "potwierdzone" in subject_lower or "confirmed" in subject_lower or "złożone" in subject_lower:
            status = "confirmed"
        elif "zamknięte" in subject_lower or "closed" in subject_lower:
            status = "closed"
        else:
            # Domyślny status dla tego handlera, jeśli nic innego nie pasuje
            status = "confirmed"

        # 4. Wyciągnij numer zamówienia (Order ID) - ULEPSZONY REGEX
        order_number = None
        
        # Wzorzec 1: Szukaj w temacie (np. "Zamówienie 3066686103006644")
        # Obsługuje dwukropek, spację, hash, lub nic między słowem a numerem
        match = re.search(r'(?:Zamówienie|Order|Order ID)[:\s#]+(\d{10,})', subject, re.IGNORECASE)
        if match:
            order_number = match.group(1)
        else:
            # Wzorzec 2: Szukaj w treści, jeśli nie ma w temacie
            if body:
                match_body = re.search(r'(?:Order ID|Order No\.|Numer zamówienia|Zamówienie)[:\s]+(\d{10,})', body, re.IGNORECASE)
                if match_body:
                    order_number = match_body.group(1)

        # Logowanie wyniku
        if order_number:
            logging.info(f"✅ AliExpress Regex sukces: Status={status}, Order={order_number}")
        else:
            logging.warning(f"⚠️ AliExpress Regex: Nie znaleziono numeru zamówienia w temacie: '{subject}'")

        # 5. Zwróć gotowe dane
        return {
            "email": recipient,
            "email_source": email_source,
            "status": status,
            "order_number": order_number,
            "product_name": None, # Regexem trudno wyciągnąć nazwę produktu pewnie, ale to nie jest krytyczne do trackingu
            "delivery_address": None,
            "phone_number": None,
            "customer_name": recipient_name,
            "user_key": user_key,
            "carrier": "AliExpress",
            "package_number": None,
            "email_date": email_date,
            "info": f"{status} (AliExpress)"
        }


class InPostDataHandler(BaseDataHandler):
    """Klasa do obsługi danych z emaili od InPost"""
    
    def __init__(self, email_handler):
        """Inicjalizacja handlera InPost"""
        super().__init__(email_handler)
        self.name = "InPost"
    
    def can_handle(self, subject, body):
        """Sprawdza czy to email od InPost"""
        # Słowa kluczowe związane z InPost
        keywords = [
            "inpost",
            "paczkomat",
            "appkomat",
            "paczka już na ciebie czeka",
            "paczka została odebrana",
            "paczka odebrana",
            "paczka została dostarczona",
            "została dostarczona",
            "zostaładostarczona"
        ]
        
        for keyword in keywords:
            if keyword in subject.lower():
                logging.info(f"✅ InPost: Znaleziono keyword '{keyword}' w temacie")
                return True
        return False
    
    def process(self, subject, body, recipient, email_source, recipient_name=None, email_message=None):
        """
        Przetwarza email od InPost używając Regex.
        Poprawiona logika statusów (rozróżnia Utworzenie od Odbioru).
        """
        import re
        import email.utils
        
        # 1. Data
        email_date = None
        if email_message:
            try:
                date_tuple = email.utils.parsedate_tz(email_message.get('Date'))
                if date_tuple:
                    local_date = email.utils.mktime_tz(date_tuple)
                    from datetime import datetime
                    email_date = datetime.fromtimestamp(local_date).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass

        subject_lower = subject.lower()
        body_lower = body.lower() if body else ""
        
        # 2. Precyzyjne wykrywanie statusu
        status = "unknown"
        
        if "dostarczona" in subject_lower or "odebrana" in subject_lower:
            status = "delivered"
        elif "czeka na odbiór" in subject_lower or "w paczkomacie" in subject_lower or "kod odbioru" in body_lower:
            # Tylko jeśli wyraźnie czeka w paczkomacie
            status = "pickup"
        elif "utworzenia paczki" in subject_lower or "przygotowana" in subject_lower or "nadana" in subject_lower:
            # ✅ POPRAWKA: Utworzenie to dopiero początek (shipment_sent)
            status = "shipment_sent"
        elif "kurier odebrał" in subject_lower or "w trasie" in subject_lower or "w drodze" in subject_lower:
            status = "transit"
        else:
            # Domyślnie, jeśli to InPost, ale nie wiemy co (bezpieczniej dać shipment_sent niż pickup)
            if "utworzenia" in subject_lower:
                 status = "shipment_sent"
            elif "odbioru" in subject_lower: # Np. "Gotowa do odbioru"
                 status = "pickup"

        # 3. Wyciąganie numeru paczki (24 cyfry)
        package_number = None
        # Szukamy 24 cyfr (standard InPost)
        match = re.search(r'(?<!\d)(\d{24})(?!\d)', body)
        if not match:
             # Czasem w temacie
             match = re.search(r'(?<!\d)(\d{24})(?!\d)', subject)
        
        if match:
            package_number = match.group(1)

        # 4. Wyciąganie kodu odbioru (tylko dla statusu pickup)
        pickup_code = None
        if status == "pickup":
            # Szukamy 6 cyfr kod odbioru
            code_match = re.search(r'(?:Kod odbioru|Kod|PIN)[:\s]+(\d{6})', body)
            if code_match:
                pickup_code = code_match.group(1)

        return {
            "carrier": "InPost",
            "status": status,
            "order_number": None, # InPost rzadko podaje nr zamówienia z Ali
            "package_number": package_number,
            "email": recipient,
            "email_source": email_source,
            "user_key": recipient.split('@')[0].lower() if recipient else "unknown",
            "pickup_code": pickup_code,
            "info": f"{status} (InPost)",
            "email_date": email_date
        }
    
    def _process_pickup_ready(self, subject, body, recipient, email_source, recipient_name, user_key):
        """
        Przetwarza powiadomienie o paczce gotowej do odbioru
        
        Implementuje logikę z sekcji "2. Powiadomienie InPost o paczce do odbioru" 
        z funkcji analyze_email
        """
        # Utwórz podstawowy słownik danych
        data = {
            "email": recipient,
            "email_source": email_source,
            "status": "pickup",  # Status dla paczki gotowej do odbioru
            "pickup_location": None,
            "pickup_deadline": None,
            "pickup_code": None,
            "phone_number": None,
            "customer_name": recipient_name,
            "user_key": user_key,
            "available_hours": None,
            "item_link": None,
            "carrier": "InPost"
        }
        
        # Użyj ChatGPT do ekstrakcji danych
        try:
            openai_data = self.email_handler.openai_handler.extract_pickup_notification_data_inpost(body, subject)
            
            # Wypełnij dane z ekstrakcji
            if openai_data.get("pickup_location"):
                data["pickup_location"] = openai_data["pickup_location"]
                data["delivery_address"] = openai_data["pickup_location"]
                
            if openai_data.get("pickup_deadline"):
                data["pickup_deadline"] = openai_data["pickup_deadline"]
                
            if openai_data.get("pickup_code"):
                data["pickup_code"] = openai_data["pickup_code"]
                
            if openai_data.get("phone_number"):
                data["phone_number"] = openai_data["phone_number"]
                
            if openai_data.get("sender"):
                data["sender"] = openai_data["sender"]

            if openai_data.get("available_hours"):
                data["available_hours"] = openai_data["available_hours"]

            if openai_data.get("item_link"):
                data["item_link"] = openai_data["item_link"]
                
            # Wyciągnij numer paczki InPost (długi ciąg numeryczny)
            package_match = re.search(r'(\d{20,30})', body)
            if package_match:
                package_number = package_match.group(1)
                logging.info(f"Wykryto numer przesyłki InPost: {package_number}")
                data["package_number"] = package_number

            logging.info(f"Wyciągnięte dane z powiadomienia o odbiorze: {openai_data}")
            
        except Exception as e:
            logging.error(f"Błąd podczas przetwarzania powiadomienia o odbiorze przez ChatGPT: {e}")
            
            # Awaryjne wyciągnięcie kodu odbioru za pomocą regex
            code_match = re.search(r"Kod odbioru:\s*(\d+)", body)
            if code_match:
                data["pickup_code"] = code_match.group(1)
                
            # Awaryjne wyciągnięcie numeru paczki
            package_match = re.search(r'(\d{20,30})', body)
            if package_match:
                package_number = package_match.group(1)
                logging.info(f"Wykryto numer przesyłki InPost: {package_number}")
                data["package_number"] = package_number
        
        return data
    
    def _process_picked_up(self, subject, body, recipient, email_source, recipient_name, user_key):
        """
        Przetwarza powiadomienie o odebranej paczce
        
        Implementuje logikę z sekcji "3. Paczka została odebrana" z funkcji analyze_email
        """
        data = {
            "email": recipient,
            "email_source": email_source,
            "status": "picked_up",  # Status dla paczki odebranej
            "customer_name": recipient_name,
            "user_key": user_key,
            "carrier": "InPost"
        }
        
        # Wyciągnij numer paczki InPost (długi ciąg numeryczny)
        package_match = re.search(r'(\d{20,30})', body)
        if package_match:
            package_number = package_match.group(1)
            logging.info(f"Wykryto numer przesyłki InPost: {package_number}")
            data["package_number"] = package_number
        
        return data
    
    def _process_delivered(self, subject, body, recipient, email_source, recipient_name, user_key):
        """
        Przetwarza powiadomienie o dostarczonej paczce
        
        Implementuje logikę z sekcji "4. Paczka została dostarczona" z funkcji analyze_email
        """
        data = {
            "email": recipient,
            "email_source": email_source,
            "status": "delivered",  # Status dla paczki dostarczonej
            "customer_name": recipient_name,
            "user_key": user_key,
            "carrier": "InPost"
        }
        
        # Wyciągnij numer paczki z tematu
        package_match = re.search(r'[Pp]aczka\s+(\d+)', subject)
        if package_match:
            package_number = package_match.group(1)
            data["package_number"] = package_number
            # Zapisz mapowanie użytkownik-paczka
            self.email_handler._save_user_package_mapping(user_key, package_number)
        
        # Wyciągnij numer paczki InPost (długi ciąg numeryczny)
        long_package_match = re.search(r'(\d{20,30})', body)
        if long_package_match and not package_match:
            package_number = long_package_match.group(1)
            logging.info(f"Wykryto numer przesyłki InPost: {package_number}")
            data["package_number"] = package_number
            # Zapisz mapowanie użytkownik-paczka
            self.email_handler._save_user_package_mapping(user_key, package_number)
        
        # Wyciągnij numer zamówienia z treści (jeśli jest)
        order_match = re.search(r'tradeOrderId=(\d+)', body)
        if order_match:
            order_number = order_match.group(1)
            data["order_number"] = order_number
            self.email_handler._save_user_order_mapping(user_key, order_number)
        
        logging.info(f"Wykryto powiadomienie o dostarczeniu paczki: {data}")
        return data
    
# Dodaj na końcu pliku po klasie InPostDataHandler

class DHLDataHandler(BaseDataHandler):
    """Klasa do obsługi danych z emaili od DHL"""
    
    def __init__(self, email_handler):
        """Inicjalizacja handlera DHL"""
        
        super().__init__(email_handler)
        self.name = "DHL"
    
    def can_handle(self, subject, body):
        """Sprawdza czy to email od DHL"""
        # Sprawdź, czy temat zawiera "Powiadomienie o przesylce" wraz z numerem JJD
        if "Powiadomienie o przesylce" in subject and ("JJD" in subject or "JJD" in body[:500]):
            return True
            
        # Dodatkowe sprawdzenie dla innych formatów maili DHL
        dhl_keywords = [
            "dhl",
            "dhl box",
            "automat dhl",
            "dhl ecommerce"
        ]
        
        # Jeśli temat nie jest typowy, sprawdź treść dla dodatkowej weryfikacji
        for keyword in dhl_keywords:
            if keyword.lower() in subject.lower() or keyword.lower() in body.lower()[:500]:
                logging.info(f"✅ DHL: Znaleziono keyword '{keyword}' w temacie")
                return True
                
        return False
    
    def process(self, subject, body, recipient, email_source, recipient_name=None, email_message=None):
        """
        Przetwarza email od DHL
        
        Określa jaki to typ wiadomości DHL na podstawie treści
        """
        logging.debug(f"WEJSCIE DO FUNKCJI PROCESS DHL: {subject}")
        # Wyciągnij klucz użytkownika z adresu email
        user_key = recipient.split('@')[0] if recipient and '@' in recipient else "unknown"
        
        # Sprawdź statusy na podstawie treści (nie tytułu)
        if "już do Ciebie jedzie" in body or "jest w drodze" in body or "planowane doręczenie" in body.lower():
            # To powiadomienie o nadaniu/przesyłce w drodze
            return self._process_shipment_sent(subject, body, recipient, email_source, 
                                              recipient_name, user_key)
        
        elif "jest już w wybranym automacie" in body or "odbierz ją do" in body.lower() or "twój pin do odbioru" in body.lower():
            # To powiadomienie o paczce do odbioru
            return self._process_pickup(subject, body, recipient, email_source, 
                                                 recipient_name, user_key)
        
        elif "Dziękujemy za skorzystanie z usług DHL" in body or "Z przyjemnością doręczymy Ci następną paczkę." in body:
            # To powiadomienie o dostarczeniu/odebraniu
            return self._process_delivered(subject, body, recipient, email_source, 
                                          recipient_name, user_key)
        
        # Domyślnie traktuj jako powiadomienie o przesyłce w drodze
        return self._process_shipment_sent(subject, body, recipient, email_source, 
                                         recipient_name, user_key)
    
    def _process_shipment_sent(self, subject, body, recipient, email_source, recipient_name, user_key):
        """Przetwarza powiadomienie o nadanej przesyłce DHL"""
        logging.debug(f"Wejscie do fun _process_shipment_sent DHL: {subject}")
        # Podstawowe dane
        data = {
            "email": recipient,
            "email_source": email_source,
            "status": "shipment_sent",  # Status dla nadanej przesyłki
            "customer_name": recipient_name,
            "user_key": user_key,
            "carrier": "DHL",
            "package_number": None,
            "expected_delivery_date": None,
            "sender": None,
            "shipping_date": None,
            "carrier_package_number": None,
            "delivery_date": None,

        }
        
        # Użyj OpenAI do ekstrakcji danych
        try:
            openai_data = self.email_handler.openai_handler.extract_dhl_notification_data(body, subject)
            
            # Wypełnij dane z ekstrakcji
            if openai_data:
                # Aktualizuj dane z odpowiedzi OpenAI
                for key, value in openai_data.items():
                    if value and key in data:
                        data[key] = value
                                          
                    
            # Awaryjne wyciąganie numeru przesyłki
            if not data.get("package_number"):
                # Format numeru DHL: JJD + długi ciąg cyfr
                jjd_match = re.search(r'(JJD\d+)', body)
                if jjd_match:
                    data["package_number"] = jjd_match.group(1)
                    logging.info(f"Wykryto numer przesyłki DHL (JJD): {data['package_number']}")
                
                # Drugi format numeru przesyłki: 8-15 cyfr w nawiasach
                secondary_match = re.search(r'przesyłki\s+(\d{8,15})', body)
                if secondary_match:
                    data["secondary_package_number"] = secondary_match.group(1)
                    logging.info(f"Wykryto dodatkowy numer przesyłki DHL: {data['secondary_package_number']}")
                    
            # Wyciągnij datę planowanego doręczenia
            if not data.get("expected_delivery_date"):
                date_match = re.search(r'planowane doręczenie[^\d]+([\d]{1,2}-[\d]{1,2}-[\d]{4})', body, re.IGNORECASE)
                if date_match:
                    data["expected_delivery_date"] = date_match.group(1)
                    
            # Wyciągnij nadawcę przesyłki
            if not data.get("sender"):
                sender_match = re.search(r'paczkę od ([^?]+)\?', body)
                if sender_match:
                    data["sender"] = sender_match.group(1).strip()
                
            logging.info(f"Wykryto powiadomienie o nadanej przesyłce DHL: {data}")
            
        except Exception as e:
            logging.error(f"Błąd podczas przetwarzania powiadomienia DHL: {e}")
            
            # Awaryjne wyciąganie numeru przesyłki
            jjd_match = re.search(r'(JJD\d+)', body)
            if jjd_match:
                data["package_number"] = jjd_match.group(1)
                logging.info(f"Awaryjnie wykryto numer przesyłki DHL: {data['package_number']}")
        
        return data
    
    def _process_pickup(self, subject, body, recipient, email_source, recipient_name, user_key):
        """
        Przetwarza powiadomienie o paczce gotowej do odbioru od DHL
        """
        logging.debug(f"Wejscie do fun _process_pickup DHL: {subject}")
        data = {
            "email": recipient,
            "email_source": email_source,
            "status": "pickup",  # Status dla paczki gotowej do odbioru
            "pickup_location": None,
            "pickup_deadline": None,
            "customer_name": recipient_name,
            "user_key": user_key,
            "carrier": "DHL",
            "package_number": None,
            "available_hours": None,
            "pickup_code": None  # Kod odbioru (PIN)
        }
        
        # Użyj OpenAI do ekstrakcji danych
        try:
            openai_data = self.email_handler.openai_handler.extract_dhl_notification_data(body, subject)
            
            # Wypełnij dane z ekstrakcji
            if openai_data:
                # Aktualizuj dane z odpowiedzi OpenAI
                for key, value in openai_data.items():
                    if value and key in data:
                        data[key] = value
                        
                # Dodatkowe dane specyficzne dla DHL
                if openai_data.get("secondary_package_number"):
                    data["secondary_package_number"] = openai_data["secondary_package_number"]
            
            # Awaryjne wyciąganie numeru przesyłki
            if not data.get("package_number"):
                jjd_match = re.search(r'(JJD\d+)', body)
                if jjd_match:
                    data["package_number"] = jjd_match.group(1)
                    logging.info(f"Wykryto numer przesyłki DHL (JJD): {data['package_number']}")
                    # Zapisz mapowanie użytkownik-przesyłka
                    self.email_handler._save_user_package_mapping(user_key, data["package_number"])
            
            # Wyciągnij PIN do odbioru
            if not data.get("pickup_code"):
                pin_patterns = [
                    r'podając PIN (\d{6})',
                    r'PIN do odbioru[^:]*:\s*(\d{6})',
                    r'PIN:\s*(\d{6})'
                ]
                
                for pattern in pin_patterns:
                    pin_match = re.search(pattern, body, re.IGNORECASE)
                    if pin_match:
                        data["pickup_code"] = pin_match.group(1)
                        break
            
            # Wyciągnij termin odbioru
            if not data.get("pickup_deadline"):
                deadline_match = re.search(r'odbierz ją do (\d{2}-\d{2}-\d{4})', body, re.IGNORECASE)
                if deadline_match:
                    data["pickup_deadline"] = deadline_match.group(1)
            
            # Wyciągnij lokalizację automatu
            if not data.get("pickup_location"):
                location_patterns = [
                    r'DHL BOX[^A-Z0-9]*([A-Za-z0-9\s,.]+\d{5}\s[A-Za:z]+)',
                    r'AUTOMAT[^A-Z0-9]*([A-Za-z0-9\s,.]+\d{5}\s[A-Za:z]+)'
                ]
                
                for pattern in location_patterns:
                    location_match = re.search(pattern, body, re.IGNORECASE)
                    if location_match:
                        data["pickup_location"] = location_match.group(1).strip()
                        break
            
            # Wyciągnij godziny otwarcia
            if not data.get("available_hours"):
                hours_match = re.search(r'Godziny otwarcia:(.*?)(?:\n\n|\r\n\r\n|$)', body, re.DOTALL)
                if hours_match:
                    hours_text = hours_match.group(1).strip()
                    data["available_hours"] = hours_text.replace('\n', ' ')
                
            logging.info(f"Wykryto powiadomienie o paczce DHL do odbioru: {data}")
            
        except Exception as e:
            logging.error(f"Błąd podczas przetwarzania powiadomienia DHL o odbiorze: {e}")
            
            # Awaryjne wyciąganie danych
            jjd_match = re.search(r'(JJD\d+)', body)
            if jjd_match:
                data["package_number"] = jjd_match.group(1)
                logging.info(f"Awaryjnie wykryto numer przesyłki DHL: {data['package_number']}")
                # Zapisz mapowanie użytkownik-przesyłka
                self.email_handler._save_user_package_mapping(user_key, data["package_number"])
        
        return data
    
    def _process_delivered(self, subject, body, recipient, email_source, recipient_name, user_key):
        """
        Przetwarza powiadomienie o dostarczeniu/odebraniu przesyłki DHL
        """
        logging.debug(f"Wejscie do fun _process_delivered DHL: {subject}")
        data = {
            "email": recipient,
            "email_source": email_source,
            "status": "delivered",  # Status dla dostarczonej/odebranej przesyłki
            "customer_name": recipient_name,
            "user_key": user_key,
            "carrier": "DHL",
            "package_number": None,
            "delivery_date": None
        }
        
        # Użyj OpenAI do ekstrakcji danych
        try:
            openai_data = self.email_handler.openai_handler.extract_dhl_notification_data(body, subject)
            
            # Wypełnij dane z ekstrakcji
            if openai_data:
                # Aktualizuj dane z odpowiedzi OpenAI
                for key, value in openai_data.items():
                    if value and key in data:
                        data[key] = value
                
                # Dodatkowe dane specyficzne dla DHL
                if openai_data.get("secondary_package_number"):
                    data["secondary_package_number"] = openai_data["secondary_package_number"]
            
            # Awaryjne wyciąganie numeru przesyłki
            if not data.get("package_number"):
                jjd_match = re.search(r'o numerze (JJD\d+)', body)
                if jjd_match:
                    data["package_number"] = jjd_match.group(1)
                    logging.info(f"Wykryto numer przesyłki DHL: {data['package_number']}")
                    # Zapisz mapowanie użytkownik-przesyłka
                    self.email_handler._save_user_package_mapping(user_key, data["package_number"])
                
            # Wyciągnij datę dostarczenia
            if not data.get("delivery_date"):
                # Data może być w różnych formatach, szukamy najpierw bezpośrednio wymienionej daty
                date_match = re.search(r'w dniu (\d{2}-\d{2}-\d{4})', body)
                if date_match:
                    data["delivery_date"] = date_match.group(1)
                else:
                    # Alternatywnie, możemy użyć dzisiejszej daty, skoro przesyłka została odebrana
                    from datetime import datetime
                    today = datetime.now().strftime('%d-%m-%Y')
                    data["delivery_date"] = today
                
            logging.info(f"Wykryto powiadomienie o odebranej przesyłce DHL: {data}")
            
        except Exception as e:
            logging.error(f"Błąd podczas przetwarzania powiadomienia DHL o dostarczeniu: {e}")
            
            # Awaryjne wyciąganie numeru przesyłki
            jjd_match = re.search(r'o numerze (JJD\d+)', body)
            if jjd_match:
                data["package_number"] = jjd_match.group(1)
                logging.info(f"Awaryjnie wykryto numer przesyłki DHL: {data['package_number']}")
                # Zapisz mapowanie użytkownik-przesyłka
                self.email_handler._save_user_package_mapping(user_key, data["package_number"])
        
        return data
    
class DPDDataHandler(BaseDataHandler):
    """Klasa do obsługi danych z emaili od DPD"""
    
    def __init__(self, email_handler):
        """Inicjalizacja handlera DPD"""
        
        super().__init__(email_handler)
        self.name = "DPD"
    
    def can_handle(self, subject, body):
        """Sprawdza czy email może być obsłużony przez DPD handler"""
        
        
        # ✅ UNIKAJ KOLIZJI Z GLS
        # Jeśli w temacie jest wyraźnie "GLS", to nie jest DPD
        if re.search(r'\bGLS\b', subject, re.IGNORECASE):
            return False
        
        # Sprawdź wzorce DPD
        dpd_patterns = [
            r'\bDPD\b',
            r'dpd\..*\.pl',
            # inne wzorce DPD
        ]
        
        for pattern in dpd_patterns:
            if re.search(pattern, subject + " " + (body or ""), re.IGNORECASE):
                logging.info(f"✅ DPD: Znaleziono keyword  w temacie")
                return True
        
        return False
    
    def process(self, subject, body, recipient, email_source, recipient_name=None, email_message=None):
        """
        Przetwarza email od DPD
        
        Określa jaki to typ wiadomości DPD na podstawie treści
        """
        logging.debug(f"Wejscie do fun process DPD: {subject}")
        # Wyciągnij klucz użytkownika z adresu email
        user_key = recipient.split('@')[0] if recipient and '@' in recipient else "unknown"
        
        # Sprawdź statusy na podstawie treści
        if "Twoja przesyłka została nadana - " in subject or "Za pośrednictwem DPD Polska" in body:
            # To powiadomienie o nadaniu/przesyłce w drodze
            return self._process_shipment_sent(subject, body, recipient, email_source, 
                                              recipient_name, user_key)
        
        elif "Uzgodnij z kurierem najbezpieczniejszy dla Ciebie sposób dostawy." in body or "Dziś doręczamy Twoją paczkę" in body.lower() or "Możesz ją odebrać bezpiecznie" in body.lower():
            # To powiadomienie o paczce do odbioru
            return self._process_pickup(subject, body, recipient, email_source, 
                                                 recipient_name, user_key)
        
        elif "Właśnie otrzymaliśmy potwierdzenie, że Twoja paczka o numerze" in body or "DPD Polska - doręczone!" in subject:
            # To powiadomienie o dostarczeniu/odebraniu
            return self._process_delivered(subject, body, recipient, email_source, 
                                          recipient_name, user_key)
        
        # Domyślnie traktuj jako powiadomienie o przesyłce w drodze
        return self._process_shipment_sent(subject, body, recipient, email_source, 
                                         recipient_name, user_key)
    
    def _process_pickup(self, subject, body, recipient, email_source, recipient_name, user_key):
        """
        Przetwarza powiadomienie o paczce gotowej do odbioru
        
        """
        # Utwórz podstawowy słownik danych
        data = {
            "email": recipient,
            "email_source": email_source,
            "status": "pickup",  # Status dla paczki gotowej do odbioru
            "pickup_location": None,
            "pickup_deadline": None,
            "pickup_code": None,
            "phone_number": None,
            "customer_name": recipient_name,
            "user_key": user_key,
            "available_hours": None,
            "item_link": None,
            "carrier": "DPD",
            "package_number": None,
            "carrier_package_number": None,
            "info": None
        }
        
        # Użyj ChatGPT do ekstrakcji danych
        try:
            openai_data = self.email_handler.openai_handler.extract_pickup_notification_data_dpd(body, subject)
            
            # Wypełnij dane z ekstrakcji
            if openai_data.get("pickup_location"):
                data["pickup_location"] = openai_data["pickup_location"]
                #data["delivery_address"] = openai_data["delivery_address"]

            if openai_data.get("email"):
                data["email"] = openai_data["email"]

            if openai_data.get("pickup_code"):
                data["pickup_code"] = openai_data["pickup_code"]

            if openai_data.get("QR_link"):
                data["qr_code"] = openai_data["QR_link"]

           # if openai_data.get("info"):
                data["info"] = openai_data["info"]

            # if openai_data.get("sender"):
            #     data["sender"] = openai_data["sender"]

            if openai_data.get("delivery_date"):
                data["available_hours"] = openai_data["delivery_date"]
 
            if openai_data.get("carrier_package_number"):
                data["carrier_package_number"] = openai_data["carrier_package_number"]


            logging.info(f"Wyciągnięte dane z powiadomienia o odbiorze: {openai_data}")
            
        except Exception as e:
            logging.error(f"Błąd podczas przetwarzania powiadomienia o odbiorze przez ChatGPT: {e}")
            
            # Awaryjne wyciągnięcie kodu odbioru za pomocą regex
            code_match = re.search(r"Kod odbioru:\s*(\d+)", body)
            if code_match:
                data["pickup_code"] = code_match.group(1)
                
            # Awaryjne wyciągnięcie numeru paczki
            package_match = re.search(r'(\d{20,30})', body)
            if package_match:
                package_number = package_match.group(1)
                logging.info(f"Wykryto numer przesyłki InPost: {package_number}")
                data["package_number"] = package_number
        
        return data
    
    def _process_shipment_sent(self, subject, body, recipient, email_source, recipient_name, user_key):
        """Przetwarza powiadomienie o nadanej przesyłce DPD"""
        try:
            # Podstawowe dane
            data = {
                "email": recipient,
                "email_source": email_source,
                "status": "shipment_sent",
                "customer_name": recipient_name,
                "user_key": user_key,
                "carrier": "DPD",
                "package_number": None,
                "expected_delivery_date": None,
                "sender": None,
                "shipping_date": None,
                "delivery_address": None
            }
            
            logging.info("PUNKT 1: Przed wywołaniem OpenAI dla DPD")
            
            # Użyj OpenAI do ekstrakcji danych
            openai_data = self.email_handler.openai_handler.extract_pickup_notification_data_dpd(body, subject)
            
            if openai_data:
                # Aktualizuj dane z odpowiedzi OpenAI
                for key, value in openai_data.items():
                    if value and key in data:
                        data[key] = value

            logging.info(f"PUNKT 2: Po wywołaniu OpenAI, otrzymano dane: {openai_data}")
            
            # Ręcznie mapuj pola z odpowiedzi AI
            if openai_data:
                logging.info(f"PUNKT 3: Przystępuję do mapowania danych z: {openai_data}")
                
                # Bezpośrednie przypisanie wartości dla kluczowych pól
                if "package_number" in openai_data:
                    data["package_number"] = openai_data["package_number"]
                    logging.info(f"PUNKT 4: Ustawiono package_number: {data['package_number']}")
                
                if "expected_delivery_date" in openai_data:
                    data["expected_delivery_date"] = openai_data["expected_delivery_date"]
                    logging.info(f"PUNKT 5: Ustawiono expected_delivery_date: {data['expected_delivery_date']}")
                
                if "delivery_address" in openai_data:
                    data["delivery_address"] = openai_data["delivery_address"]
                    logging.info(f"PUNKT 6: Ustawiono delivery_address: {data['delivery_address']}")
                
                if "sender" in openai_data:
                    data["sender"] = openai_data["sender"]
                    logging.info(f"PUNKT 7: Ustawiono sender: {data['sender']}")
                
                if "shipping_date" in openai_data:
                    data["shipping_date"] = openai_data["shipping_date"]
                    logging.info(f"PUNKT 8: Ustawiono shipping_date: {data['shipping_date']}")
                
                logging.info(f"PUNKT 9: Dane po mapowaniu: {data}")
            else:
                logging.warning("PUNKT 10: Otrzymano puste dane z OpenAI")
            
            logging.info(f"PUNKT 11: Zwracam dane: {data}")
            return data
        except Exception as e:
            logging.error(f"PUNKT 12: Błąd podczas przetwarzania powiadomienia DPD: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return data
    
    def _process_delivered(self, subject, body, recipient, email_source, recipient_name, user_key):
        """
        Przetwarza powiadomienie o dostarczeniu/odebraniu przesyłki DPD
        """
        logging.debug(f"Wejscie do fun _process_delivered DPD: {subject}")
        data = {
            "email": recipient,
            "email_source": email_source,
            "status": "delivered",  # Status dla dostarczonej/odebranej przesyłki
            "customer_name": recipient_name,
            "user_key": user_key,
            "carrier": "DPD",
            "package_number": None,
            "delivery_date": None
        }
        
        # Użyj OpenAI do ekstrakcji danych
        try:
            openai_data = self.email_handler.openai_handler.extract_pickup_notification_data_dpd(body, subject)
            
            # Wypełnij dane z ekstrakcji
            if openai_data:
                # Aktualizuj dane z odpowiedzi OpenAI
                for key, value in openai_data.items():
                    if value and key in data:
                        data[key] = value
            
            
            # Wyciągnij datę dostarczenia
            if not data.get("delivery_date"):
                # Data może być w różnych formatach, szukamy najpierw bezpośrednio wymienionej daty
                date_match = re.search(r'w dniu (\d{2}-\d{2}-\d{4})', body)
                if date_match:
                    data["delivery_date"] = date_match.group(1)
                else:
                    # Alternatywnie, możemy użyć dzisiejszej daty, skoro przesyłka została odebrana
                    from datetime import datetime
                    today = datetime.now().strftime('%d-%m-%Y')
                    data["delivery_date"] = today
                
            logging.info(f"Wykryto powiadomienie o odebranej przesyłce DPD: {data}")
            
        except Exception as e:
            logging.error(f"Błąd podczas przetwarzania powiadomienia DPD o dostarczeniu: {e}")
                 
        return data
    
class GLSDataHandler(BaseDataHandler):
    """Klasa do obsługi danych z emaili od GLS"""
    
    def __init__(self, email_handler):
        """Inicjalizacja handlera GLS"""
        super().__init__(email_handler)
        self.name = "GLS"
    
    def can_handle(self, subject, body):
        """Sprawdza czy email może być obsłużony przez GLS handler"""
        
        
        # ✅ BARDZO SILNE WZORCE GLS
        gls_definitive_patterns = [
            r'^GLS:',                         # Temat zaczyna się od "GLS:"
            r'^Kurier GLS',                   # ✅ MOCNIEJSZY - zaczyna się od "Kurier GLS"
            r'Kurier GLS',                    # ✅ WSZĘDZIE w temacie
            r'\bGLS\b.*przesyłka',           # "GLS" + "przesyłka" 
            r'przesyłka.*\bGLS\b',           # "przesyłka" + "GLS"
            r'\bGLS\b.*nadana',              # "GLS" + "nadana"
            r'\bGLS\b.*w drodze',            # ✅ NOWY - "GLS" + "w drodze"
            r'w drodze.*\bGLS\b',            # ✅ NOWY - "w drodze" + "GLS"
            r'General Logistics Systems',     # Pełna nazwa
            r'opcje dostawy.*GLS',           # ✅ NOWY - dla tego konkretnego przypadku
            r'GLS.*opcje dostawy',           # ✅ NOWY - odwrotnie
            r'^Twoja paczka od.* informacja o dostawie',
        ] 
        
        for pattern in gls_definitive_patterns:
            if re.search(pattern, subject, re.IGNORECASE):
                logging.info(f"✅ GLS can_handle: SILNY wzorzec '{pattern}' - DEFINITYWNIE GLS")
                return True
        
        # Sprawdź także treść
        if body:
            body_sample = body[:500].lower()
            for pattern in gls_definitive_patterns:
                if re.search(pattern, body_sample, re.IGNORECASE):
                    logging.info(f"✅ GLS can_handle: SILNY wzorzec '{pattern}' w treści")
                    return True
        
        return False
    
    def process(self, subject, body, recipient, email_source, recipient_name=None, email_message=None):
        """
        Przetwarza email od GLS
        
        Określa jaki to typ wiadomości GLS na podstawie treści
        """
        logging.debug(f"Wejście do funkcji process GLS: {subject}")
        # Wyciągnij klucz użytkownika z adresu email
        user_key = recipient.split('@')[0] if recipient and '@' in recipient else "unknown"
        
        # Sprawdź statusy na podstawie treści
        if any(phrase in body.lower() for phrase in [
            "przesyłka została nadana", 
            "jest w drodze", 
            "przekazana do transportu",
            "gls - nadanie przesyłki"
        ]):
            return self._process_shipment_sent(subject, body, recipient, email_source, 
                                              recipient_name, user_key)
        
        elif any(phrase in body.lower() for phrase in [
            "gotowa do odbioru", 
            "czeka w parcelshop", 
            "możesz odebrać",
            "dostępna w punkcie odbioru"
        ]):
            return self._process_pickup(subject, body, recipient, email_source, 
                                                 recipient_name, user_key)
        
        elif any(phrase in body.lower() for phrase in [
            "została dostarczona", 
            "doręczono", 
            "odebrano", 
            "przesyłka dostarczena"
        ]):
            return self._process_delivered(subject, body, recipient, email_source, 
                                          recipient_name, user_key)
        
        # Domyślnie traktuj jako powiadomienie o przesyłce w drodze
        return self._process_shipment_sent(subject, body, recipient, email_source, 
                                         recipient_name, user_key)
    
    def _process_shipment_sent(self, subject, body, recipient, email_source, recipient_name, user_key):
        """Przetwarza powiadomienie o nadanej przesyłce GLS"""
        data = {
            "email": recipient,
            "email_source": email_source,
            "status": "shipment_sent",
            "customer_name": recipient_name,
            "user_key": user_key,
            "carrier": "GLS",
            "package_number": None,
            "expected_delivery_date": None,
            "sender": None,
            "shipping_date": None,
            "delivery_address": None
        }
        
        try:
            # ✅ UŻYJ FUNKCJI GENERAL
            openai_data = self.email_handler.openai_handler.general_extract_carrier_notification_data(
                body, subject, "shipment_sent", recipient
            )
            
            # Wypełnij dane z ekstrakcji
            if openai_data:
                for key, value in openai_data.items():
                    if value and key in data:
                        data[key] = value
            
            # Awaryjne wyciąganie numeru przesyłki GLS
            if not data.get("package_number"):
                # Format numeru GLS: różne wzorce
                gls_patterns = [
                    r'(GL\d+)',                    # GL + cyfry
                    r'(\d{10,15})',               # 10-15 cyfr
                    r'przesyłki[:\s]+(\w+)',      # Po słowie "przesyłki"
                    r'numer[:\s]+(\w+)'           # Po słowie "numer"
                ]
                
                for pattern in gls_patterns:
                    match = re.search(pattern, body, re.IGNORECASE)
                    if match:
                        data["package_number"] = match.group(1)
                        logging.info(f"Wykryto numer przesyłki GLS: {data['package_number']}")
                        break
            
            logging.info(f"Wykryto powiadomienie o nadanej przesyłce GLS: {data}")
            
        except Exception as e:
            logging.error(f"Błąd podczas przetwarzania powiadomienia GLS: {e}")
        
        return data
    
    def _process_pickup(self, subject, body, recipient, email_source, recipient_name, user_key):
        """Przetwarza powiadomienie o paczce gotowej do odbioru od GLS"""
        data = {
            "email": recipient,
            "email_source": email_source,
            "status": "pickup",
            "pickup_location": None,
            "pickup_deadline": None,
            "pickup_code": None,
            "customer_name": recipient_name,
            "user_key": user_key,
            "carrier": "GLS",
            "package_number": None,
            "available_hours": None
        }
        
        try:
            # ✅ UŻYJ FUNKCJI GENERAL
            openai_data = self.email_handler.openai_handler.general_extract_carrier_notification_data(
                body, subject, "pickup", recipient
            )
            
            # Wypełnij dane z ekstrakcji
            if openai_data:
                for key, value in openai_data.items():
                    if value and key in data:
                        data[key] = value
            
            # Awaryjne wyciąganie danych
            if not data.get("package_number"):
                gls_patterns = [
                    r'(GL\d+)',
                    r'(\d{10,15})',
                    r'przesyłki[:\s]+(\w+)'
                ]
                
                for pattern in gls_patterns:
                    match = re.search(pattern, body, re.IGNORECASE)
                    if match:
                        data["package_number"] = match.group(1)
                        # Zapisz mapowanie użytkownik-przesyłka
                        self.email_handler._save_user_package_mapping(user_key, data["package_number"])
                        break
            
            logging.info(f"Wykryto powiadomienie o paczce GLS do odbioru: {data}")
            
        except Exception as e:
            logging.error(f"Błąd podczas przetwarzania powiadomienia GLS o odbiorze: {e}")
        
        return data
    
    def _process_delivered(self, subject, body, recipient, email_source, recipient_name, user_key):
        """Przetwarza powiadomienie o dostarczeniu przesyłki GLS"""
        data = {
            "email": recipient,
            "email_source": email_source,
            "status": "delivered",
            "customer_name": recipient_name,
            "user_key": user_key,
            "carrier": "GLS",
            "package_number": None,
            "delivery_date": None
        }
        
        try:
            # ✅ UŻYJ FUNKCJI GENERAL
            openai_data = self.email_handler.openai_handler.general_extract_carrier_notification_data(
                body, subject, "delivered", recipient
            )
            
            # Wypełnij dane z ekstrakcji
            if openai_data:
                for key, value in openai_data.items():
                    if value and key in data:
                        data[key] = value
            
            # Awaryjne wyciąganie numeru przesyłki
            if not data.get("package_number"):
                gls_patterns = [
                    r'(GL\d+)',
                    r'(\d{10,15})',
                    r'przesyłki[:\s]+(\w+)'
                ]
                
                for pattern in gls_patterns:
                    match = re.search(pattern, body, re.IGNORECASE)
                    if match:
                        data["package_number"] = match.group(1)
                        # Zapisz mapowanie użytkownik-przesyłka
                        self.email_handler._save_user_package_mapping(user_key, data["package_number"])
                        break
            
            # Dodaj dzisiejszą datę jako datę dostarczenia
            if not data.get("delivery_date"):
                from datetime import datetime
                today = datetime.now().strftime('%d-%m-%Y')
                data["delivery_date"] = today
            
            logging.info(f"Wykryto powiadomienie o dostarczonej przesyłce GLS: {data}")
            
        except Exception as e:
            logging.error(f"Błąd podczas przetwarzania powiadomienia GLS o dostarczeniu: {e}")
        
        return data

# Dodaj to na końcu pliku carriers_data_handlers.py

class PocztaPolskaDataHandler(BaseDataHandler):
    """Klasa do obsługi danych z emaili od Poczty Polskiej / Pocztex"""
    
    def __init__(self, email_handler):
        super().__init__(email_handler)
        self.name = "PocztaPolska"
    
    def can_handle(self, subject, body):
        """Sprawdza czy email pochodzi od Poczty Polskiej"""
        keywords = [
            "poczta polska", 
            "pocztex", 
            "e-info",
            "informacja@poczta-polska.pl",
            "przesyłka o numerze px",
        ]
        
        subject_lower = subject.lower()
        body_lower = body.lower()[:1000] 
        
        for keyword in keywords:
            if keyword in subject_lower or keyword in body_lower:
                logging.info(f"✅ Poczta Polska: Znaleziono keyword '{keyword}'")
                return True
        return False
    
    def process(self, subject, body, recipient, email_source, recipient_name=None, email_message=None):
        """
        Przetwarza email od Poczty Polskiej (Tryb Czysty Regex)
        """
        import re
        
        # Dane domyślne
        data = {
            "email": recipient,
            "email_source": email_source,
            "status": "transit", 
            "customer_name": recipient_name,
            "user_key": recipient.split('@')[0] if recipient else "unknown",
            "carrier": "PocztaPolska",
            "package_number": None,
            "pickup_code": None,      
            "courier_phone": None,
            "info": None
        }

        # 1. Wyciąganie Numeru Przesyłki (Najważniejsze!)
        # Obsługuje formaty: PX123456789PL oraz (00)123456...
        # Radzi sobie z HTML np. "numerze <strong>PX..." lub linkami "numer=PX..."
        pkg_match = re.search(r'(?:numerze|numer=)\s*(?:<strong>|<b>|&nbsp;)?\s*([A-Z]{2}\d{9,}[A-Z]{0,2}|00\d{18})', body)
        
        if pkg_match:
            data["package_number"] = pkg_match.group(1)
        else:
            # Fallback: szukaj po prostu formatu PX na początku słowa
            fallback_match = re.search(r'\b(PX\d{9,}[A-Z]{0,2})\b', body)
            if fallback_match:
                data["package_number"] = fallback_match.group(1)

        # 2. Wyciąganie Kodu PIN (Odbiór w punkcie/skrytce)
        pin_match = re.search(r'(?:Kod|PIN)[:\s]+(\d{6})', body, re.IGNORECASE)
        if pin_match:
            data["pickup_code"] = pin_match.group(1)
            data["status"] = "pickup"

        # 3. Telefon kuriera
        phone_match = re.search(r'Telefon do kuriera:?\s*(\d{3}[\s-]?\d{3}[\s-]?\d{3})', body)
        if phone_match:
            raw_phone = phone_match.group(1).replace(" ", "").replace("-", "")
            data["courier_phone"] = raw_phone

        # 4. Określanie statusu na podstawie treści
        body_lower = body.lower()
        subject_lower = subject.lower()

        # Priorytetyzacja statusów
        if "dziękujemy za odbiór" in body_lower or "doręczona" in body_lower or "odebrana" in body_lower:
            data["status"] = "delivered"
        elif "wydana do doręczenia" in body_lower:
            data["status"] = "pickup" # Kurier jedzie
            data["info"] = "Wydana do doręczenia"
        elif "awizo" in body_lower or "w placówce" in body_lower or "gotowa do odbioru" in body_lower:
            data["status"] = "pickup"
        elif "została do ciebie nadana" in body_lower or "nadana" in body_lower:
            data["status"] = "shipment_sent"
            # Sprawdź czy to Cainiao
            if "cainiao" in body_lower:
                data["info"] = "Nadano (Cainiao)"
        
        # 5. Budowanie pola Info
        info_parts = []
        if data.get("info"):
            info_parts.append(data["info"])
        if data.get("courier_phone"):
            info_parts.append(f"Kurier: {data['courier_phone']}")
        if "cainiao" in body_lower and "cainiao" not in str(data.get("info", "")).lower():
            info_parts.append("AliExpress/Cainiao")
            
        if info_parts:
            data["info"] = " | ".join(info_parts)

        return data