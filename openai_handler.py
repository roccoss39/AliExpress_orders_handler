from openai import OpenAI
import logging
import json
import config
import re
import time

class OpenAIHandler:
    def __init__(self):
        self.api_key = config.OPENAI_API_KEY
        self.last_request_time = 0
        self.min_request_interval = 3  # 3 sekundy między requestami
        self.daily_request_count = 0
        self.daily_limit = 45  # Limit 45 requestów dziennie (zostawiamy margines)
        self.current_day = time.localtime().tm_yday
    
        # Konfiguracja zgodna z działającym przykładem
        self.client = OpenAI(
            base_url="https://models.inference.ai.azure.com",
            api_key=self.api_key,
            timeout=30.0
        )

    def _rate_limit(self):
        """Ograniczenie częstotliwości requestów i reset dzienny"""
        current_time = time.time()
        
        # 1. SPRAWDZANIE CZY NASTAŁ NOWY DZIEŃ
        # tm_yday zwraca numer dnia w roku (np. dzisiaj jest 111 dzień roku)
        today = time.localtime(current_time).tm_yday
        
        # Jeśli dzień się zmienił, zerujemy licznik
        if not hasattr(self, 'current_day'):
            self.current_day = today
            
        if today != self.current_day:
            logging.info(f"🌅 Nowy dzień ({today})! Resetuję licznik OpenAI.")
            self.daily_request_count = 0
            self.current_day = today

        # 2. SPRAWDZANIE LIMITU DZIENNEGO
        if self.daily_request_count >= self.daily_limit:
            logging.warning(f"🚫 Osiągnięto dzienny limit requestów OpenAI ({self.daily_limit})")
            return False

        # 3. SPRAWDZANIE ODSTĘPU (Rate Limit - min. 3 sekundy)
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            logging.info(f"⏱️ Zbyt szybkie zapytanie. Czekam {sleep_time:.1f}s...")
            time.sleep(sleep_time)

        # Aktualizacja statystyk
        self.last_request_time = time.time()
        self.daily_request_count += 1
        logging.info(f"📊 Request OpenAI: {self.daily_request_count}/{self.daily_limit}")
        return True
        
    def _clean_json_response(self, response_text):
        """Czyści odpowiedź API z formatowania Markdown i innych elementów"""
        # Usuń znaczniki Markdown dla bloków kodu
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*$', '', response_text)
        response_text = re.sub(r'^```\s*', '', response_text)
        
        # Usuń inne potencjalne problemy
        response_text = response_text.strip()
        
        logging.info(f"Wycyszczona odpowiedź JSON: {response_text}")
        return response_text
        
    def extract_order_confirmation_data(self, email_body, subject, recipient_email=None):
        """Wyciąga dane z maila potwierdzającego zamówienie w AliExpress"""
        try:
            # Dodaj informację o nagłówku To:
            to_header = f"Adres email odbiorcy (To:): {recipient_email}" if recipient_email else "Brak informacji o odbiorcy"
            
            # Skróć treść wiadomości, jeśli jest za długa
            max_body_length = 8000  # Zmniejszony limit dla API
            if len(email_body) > max_body_length:
                logging.info(f"Treść maila jest bardzo duża ({len(email_body)} znaków). Wykonuję celowaną ekstrakcję.")
                
                # Najpierw znajdź numer zamówienia (potrzebny do ukierunkowanej ekstrakcji)
                order_match = re.search(r'[Oo]rder(?:\s+|\s*[:#]\s*)(\d+)|[Zz]amów[^\d]+(\d+)', subject + " " + email_body[:1000])
                order_number = None
                if order_match:
                    order_number = order_match.group(1) or order_match.group(2)
                
                # Użyj zaawansowanej ekstrakcji kluczowych sekcji
                email_body = self._extract_key_sections(email_body, order_number)
                logging.info(f"Po celowanej ekstrakcji rozmiar tekstu: {len(email_body)} znaków")
            
            # Kontynuuj z oryginalnym procesem
            prompt = f"""
            Wyciągnij następujące informacje z tego maila potwierdzającego zamówienie AliExpress:
            1. Numer zamówienia
            2. Nazwa produktu
            3. Adres dostawy
            4. Numer telefonu
            5. Adres email odbiorcy
            6. Link do zamówienia lub produktu (zaczynający się od https://www.aliexpress.com/)

            Nagłówek To: {to_header}
            Temat maila: {subject}

            Treść maila (może być skrócona):
            {email_body}

             WAŻNE: 
             - Format daty powinien być zawsze DD.MM.YYYY (np. 18.05.2025)
             - W polu customer_name umieść pełny adres email odbiorcy (z nagłówka To:), nie tylko nazwę użytkownika.
             - Jeśli nie możesz znaleźć niektórych danych, zostaw te pola puste.
             - Szukaj linku do zamówienia zaczynającego się od https://www.aliexpress.com/
             
             Odpowiedź sformatuj jako obiekt JSON z kluczami: order_number, product_name, delivery_address, phone_number, customer_name, item_link
            """
            
            response = self._call_openai_api(prompt)
            
            if response is None:
                logging.warning("Treść maila przekracza limit tokenów. Używam awaryjnej ekstrakcji.")
                return self.general_fallback_extraction(subject, email_body, recipient_email)
            
            # Obsługa potencjalnych błędów JSON
            try:
                data = response
                
                # Jeśli OpenAI nie znalazło linku, spróbuj wyciągnąć go ręcznie
                if not data.get("item_link"):
                    link = self._extract_aliexpress_link(email_body)
                    if link:
                        data["item_link"] = link
                
                # Upewnij się, że customer_name zawiera pełny adres email
                if recipient_email and not data.get("customer_name"):
                    data["customer_name"] = recipient_email
                
                # Formatowanie numeru telefonu
                if data.get("phone_number"):
                    data["phone_number"] = self._format_phone_for_display(data["phone_number"])
                    
            except json.JSONDecodeError as e:
                logging.error(f"Błąd parsowania JSON: {e}")
                # Awaryjne wyciąganie danych za pomocą regex
                data = self.general_fallback_extraction(subject, email_body, recipient_email)
                
            return data
            
        except Exception as e:
            logging.error(f"Błąd podczas ekstrakcji danych z maila potwierdzającego zamówienie: {e}")
            # Awaryjne wyciąganie danych
            result = {"customer_name": recipient_email}
            
            # Spróbuj wyciągnąć numer zamówienia z tematu lub treści
            order_match = re.search(r'[Oo]rder(?:\s+|\s*[:#]\s*)(\d+)|[Zz]amów[^\d]+(\d+)', subject + " " + email_body[:500])
            if order_match:
                result["order_number"] = order_match.group(1) or order_match.group(2)
                
            # Spróbuj wyciągnąć link do zamówienia 
            link_match = re.search(r'(https://www\.aliexpress\.com/p/order/detail\.html\?orderId=\d+[^\s"<>]+)', email_body[:2000])
            if link_match:
                result["item_link"] = link_match.group(1)
                
            return result
    
    def extract_pickup_notification_data_dpd(self, email_body, subject=None, recipient_email=None):
        """Wyciąga dane z powiadomienia o paczce DPD"""
        try:
            # Skróć treść wiadomości, jeśli jest za długa
            max_body_length = 8000  # Zmniejszony limit dla API
            if len(email_body) > max_body_length:
                logging.info(f"Treść maila DPD jest bardzo duża ({len(email_body)} znaków). Wykonuję celowaną ekstrakcję.")
                
                # Użyj zaawansowanej ekstrakcji kluczowych sekcji
                email_body = self._extract_key_sections(email_body)
                logging.info(f"Po celowanej ekstrakcji rozmiar tekstu: {len(email_body)} znaków")
        
            prompt = f"""
            Przeanalizuj poniższy email od firmy kurierskiej DPD Polska. Email może dotyczyć jednego z trzech etapów dostawy:

            1. NADANIE PRZESYŁKI - Email zawiera informację o nadaniu paczki z tematem "Twoja przesyłka została nadana" lub zawierający tekst "Za pośrednictwem DPD Polska, nadana została".
            Z tego typu maila wyciągnij:
            - Numer przesyłki od Aliexpress jeśli jest (package_number)
            - Data nadania (shipping_date)
            - Planowany termin doręczenia (expected_delivery_date)
            - Adres dostawy (delivery_address)
            - Nadawcę (sender)
            - email odbiorcy
            - Numer paczki od danego przewoźnika DPD, DHL, INPOST(carrier_package_number):
                DPD: zazwyczaj 13 cyfr + 1 litera	np 0000363570900W
                DHL: 3S / JVGL / JJD + cyfry	np. 3S1234567890
                InPost: zazwyczaj składa się z 24 cyfr np: 520000012680041086770098

            2. DOSTAWA DZIŚ - Email informujący, że kurier jest w drodze z przesyłką, z tematem "Bezpieczne doręczenie Twojej paczki" lub zawierający tekst "Dziś doręczamy Twoją paczkę".
            Z tego typu maila wyciągnij:
            - Adres dostawy (pickup_location)
            - Imię kuriera (courier_name)
            - Telefon kuriera (courier_phone)
            - Numer paczki od danego przewoźnika DPD, DHL, INPOST(carrier_package_number):
                DPD: zazwyczaj 13 cyfr + 1 litera	np 0000363570900W
                DHL: 3S / JVGL / JJD + cyfry	np. 3S1234567890
                InPost: zazwyczaj składa się z 24 cyfr np: 520000012680041086770098
            - Informacje o płatności (payment_info)
            - email odbiorcy paczki
            - Planowany termin doręczenia (expected_delivery_date)
            - jeśli to paczkomat lub punkt odbioru: link do QR w polu QR_link (WYŁĄCZNIE pełny URL zaczynający się od http:// lub https://; jeśli brak URL — zostaw jako pusty string ""; NIE wpisuj "załącznik", "brak" ani żadnego opisu)

            3. DORĘCZONO - Email potwierdzający dostarczenie paczki, z tematem "DPD Polska - doręczone!" lub zawierający tekst "Właśnie otrzymaliśmy potwierdzenie".
            Z tego typu maila wyciągnij:
            - Numer przesyłki od Aliexpress jeśli jest (package_number)
            - Data doręczenia (delivery_date) - może być dzisiejsza data, jeśli nie podano w mailu
            - email odbiorcy
            - Numer referencyjny (carrier_package_number)
        

            Temat maila: {subject}

            Treść maila:
            {email_body}

            WAŻNE: 
            - Format daty powinien być zawsze DD.MM.YYYY (np. 18.05.2025)
            - W polu email umieść adres email odbiorcy (z nagłówka To:)
            - Jeśli nie możesz znaleźć niektórych danych, pozostaw te pola puste
            - W polu info połącz informacje o kurierze oraz shipping_date (np. "Kurier: Jakub | Tel: 506575068 | Shipping date:..")
            

            Odpowiedź sformatuj jako obiekt JSON z kluczami: 
            carrier_package_number, email, QR_link, shipping_date, delivery_date, expected_delivery_date, pickup_location, courier_name, courier_phone, sender, payment_info, info
            """
            
            response = self._call_openai_api(prompt)
            
            if response is None:
                logging.warning("Treść maila przekracza limit tokenów. Używam awaryjnej ekstrakcji.")
                return self.general_fallback_extraction(subject, email_body, recipient_email)
            
            # Obsługa potencjalnych błędów JSON
            try:
                data = response
                
                # Upewnij się, że customer_name zawiera pełny adres email
                if recipient_email and not data.get("customer_name"):
                    data["customer_name"] = recipient_email  
                
                # Dodaj jednoznaczne określenie przewoźnika
                data["carrier"] = "DPD"

                # Walidacja i formatowanie numeru telefonu
                if data.get("phone_number"):
                    data["phone_number"] = self._format_phone_for_display(data["phone_number"])
                
                # Zwróć dane z OpenAI
                return data
            
            except json.JSONDecodeError as e:
                logging.error(f"Błąd parsowania JSON: {e}")
                data = {"customer_name": recipient_email} if recipient_email else {}
                return data
    
        except Exception as e:
            logging.error(f"Błąd podczas ekstrakcji danych z powiadomienia o odbiorze: {e}")
            # Zwróć podstawowe informacje
            result = {
                "user_key": recipient_email.split('@')[0] if recipient_email else None,
                "customer_name": recipient_email,
                "available_hours": "PN-SB 06-20",
                "pickup_code": "",
                "pickup_location_code": "",
                "pickup_address": "",
                "pickup_deadline": "",
                "carrier": "DPD",  # Dodaj oznaczenie przewoźnika
                "info": "Nie można wyodrębnić danych z powiadomienia DPD"
            }
            return result  # Zwracaj wewnątrz bloku except
    
    def extract_pickup_notification_data_inpost(self, email_body, subject=None, recipient_email=None, email_date=None):
        """Wyciąga dane z powiadomienia o paczce w paczkomacie"""
        try:
                    # ✅ DODAJ DEBUG ORYGINALNEGO EMAILA
            logging.debug(f"📧 Subject: {subject}")
            logging.debug(f"📧 ORYGINALNY EMAIL INPOST:")
            logging.debug(f"📧 Recipient: {recipient_email}")
            logging.debug(f"📧 Rozmiar body: {len(email_body)} znaków")
            logging.debug("="*50 + " ORYGINALNY BODY " + "="*50)
            logging.debug(email_body)  # ✅ CAŁY ORYGINALNY EMAIL
            logging.debug("="*120)

            # Bardziej elastyczne skracanie tekstu - limit 8000 znaków (około 2000-3000 tokenów)
            max_chars = 8000  # Zwiększ z 5000 do 8000 znaków
            
            if len(email_body) > max_chars:
                logging.info(f"Treść maila InPost jest bardzo duża ({len(email_body)} znaków). Wykonuję celowaną ekstrakcję.")
                
                # Bardziej celowana ekstrakcja tylko najważniejszych fragmentów
                important_sections = []
                
                # 1. Najpierw wyciągnij kluczowe dane z rozszerzonymi kontekstami
                
                # Wyciągnij fragment z kodem odbioru (zwiększenie kontekstu z 200 do 500)
                code_patterns = ["Kod odbioru", "kod\\s+\\d{6}", "kod:", "Numer\\s+telefonu.*Kod\\s+odbioru"]
                for pattern in code_patterns:
                    code_section = self._extract_section(email_body, pattern, 500)
                    if code_section:
                        important_sections.append(code_section)
                        break
                
                # Wyciągnij fragment z kodem paczkomatu (3 litery, 2 cyfry, 3-4 litery)
                location_code_match = re.search(r'([A-Z]{3}\d{2}[A-Z]{3,4})', email_body)
                if location_code_match:
                    location_code = location_code_match.group(1)
                    # Znajdź większy kontekst wokół kodu paczkomatu
                    location_index = email_body.find(location_code)
                    if location_index > 0:
                        start = max(0, location_index - 500)
                        end = min(len(email_body), location_index + 1000)
                        location_context = email_body[start:end]
                        important_sections.append(location_context)
                        logging.info(f"Znaleziono kod paczkomatu: {location_code}")
                        
                # Wyciągnij fragment z adresem paczkomatu (zwiększenie kontekstu z 300 do 800)
                location_patterns = ["Paczkomat", "Appkomat", "lokalizacja", "przy wejściu", "adres paczkomatu"]
                for pattern in location_patterns:
                    location_section = self._extract_section(email_body, pattern, 800)
                    if location_section:
                        important_sections.append(location_section)
                        break
                
                # Wyciągnij fragment z terminem odbioru (zwiększenie kontekstu z 200 do 500)
                deadline_patterns = ["Termin odbioru", "Czas na odbiór", "masz czas do", "odbiór do", "Planując odbiór"]
                for pattern in deadline_patterns:
                    deadline_section = self._extract_section(email_body, pattern, 500)
                    if deadline_section:
                        important_sections.append(deadline_section)
                        break
                
                # Wyciągnij fragment z godzinami dostępności (zwiększenie kontekstu z 150 do 400)
                hours_patterns = ["Godziny otwarcia", "godzina:", "godziny dostępności", "czynne"]
                for pattern in hours_patterns:
                    hours_section = self._extract_section(email_body, pattern, 400)
                    if hours_section:
                        important_sections.append(hours_section)
                        break
                
                # 2. Jeśli nie znaleziono wszystkich potrzebnych sekcji, dodaj więcej tekstu
                
                # Połącz wyciągnięte fragmenty
                extracted_body = "\n\n".join(important_sections)
                
                # Jeśli mamy mało tekstu, dodaj więcej
                if len(extracted_body) < 1500:
                    # Dodaj pierwsze 3000 znaków z oryginalnego maila
                    if len(email_body) > 3000:
                        extracted_body += "\n\n--- DODATKOWY TEKST ---\n\n" + email_body[:3000]
                    else:
                        extracted_body += "\n\n--- DODATKOWY TEKST ---\n\n" + email_body
                
                # Jeśli nadal mamy za mało tekstu lub nic nie znaleziono
                if len(extracted_body) < 500 or not important_sections:
                    # Użyj większych fragmentów z początku i końca
                    extracted_body = email_body[:4000] + "\n...\n" + email_body[-4000:]
                    
                email_body = extracted_body
                logging.info(f"Po celowanej ekstrakcji rozmiar tekstu: {len(email_body)} znaków")
                # Ogranicz logowanie do pierwszych 150 znaków
                logging.info(f"Treść email_body (początek): {email_body[200]}")

            # Wyznacz rok z daty maila (żeby AI nie zgadywał)
            from datetime import datetime
            if email_date:
                try:
                    email_year = datetime.strptime(email_date[:10], '%Y-%m-%d').year
                except Exception:
                    email_year = datetime.now().year
            else:
                email_year = datetime.now().year

            prompt = f"""
            Wyciągnij następujące informacje z powiadomienia InPost o paczce gotowej do odbioru:
            1. Kod odbioru paczki (4-6 cyfr)
            2. Adres paczkomatu (np. "Szczecin, ul. Przykładowa 1")
            3. Kod paczkomatu (np. "SZC123")
            4. Termin odbioru (zwykle data lub liczba dni)
            5. Numer telefonu adresata
            6. Adres email adresata
            7. Godziny dostępności paczkomatu (np. "PN-SB 10-22")
            8. Link QR do odbioru paczki (jeśli istnieje w treści maila)

            Temat maila: {subject}
            Data wysłania maila: {email_date or 'nieznana'} (rok: {email_year})
            
            Treść maila (może być skrócona):
            {email_body}
            
            WAŻNE: 
            - W polu 'qr_code' wpisz WYŁĄCZNIE dane w formacie "P|numer_telefonu|kod_odbioru" (bez cudzysłowów, bez spacji), np. P|720133912|663493.
            - Numer telefonu bierz z pola "Numer telefonu" w mailu (9 cyfr bez +48), kod odbioru z pola "Kod odbioru" (6 cyfr).
            - NIE buduj sam URL-a do qrserver.com — system zrobi to automatycznie na podstawie wartości P|...|...
            - Jeśli w mailu nie ma numeru telefonu ani kodu odbioru, zostaw pole 'qr_code' jako pusty string "".
            - NIE wpisuj słów takich jak "załącznik", "attachment", "brak" ani żadnego opisu tekstowego.
            - Jeśli nie możesz znaleźć innych danych, zostaw te pola jako pusty string "".
            - Format daty powinien być zawsze DD.MM.YYYY (np. 18.05.{email_year})
            - WAŻNE: Jeśli w mailu podana jest data bez roku (np. "25.02" lub "Środa 25.02"), ZAWSZE użyj roku {email_year} (roku wysłania maila). NIE zgaduj roku!
            
            Odpowiedź sformatuj jako obiekt JSON z kluczami: pickup_code, pickup_address, pickup_location_code, pickup_deadline, phone_number, customer_name, available_hours, qr_code
            """
            
            response = self._call_openai_api(prompt)
            
            if response is None:
                logging.warning("Treść maila przekracza limit tokenów. Używam awaryjnej ekstrakcji.")
                
                # Użyj specjalizowanej funkcji dla InPost
                if "appkomat" in subject.lower() or "paczkomat" in subject.lower() or "inpost" in subject.lower():
                    # Przekaż poprawnie recipient_email
                    result = self._fallback_extraction_pickup(email_body, subject, recipient_email)
                    
                    # Dodatkowe sprawdzenie i uzupełnienie user_key i customer_name
                    if recipient_email:
                        result["user_key"] = recipient_email
                        result["customer_name"] = recipient_email
                        
                    # Pokaż w logu całą strukturę wyników dla diagnostyki
                    logging.info(f"Kompletne dane z awaryjnej ekstrakcji: {json.dumps(result)}")
                    return result
                else:
                    return self.general_fallback_extraction(subject, email_body, recipient_email)
            
            # Wyczyść i sparsuj odpowiedź
            
            try:
                data = response
                # Zachowaj kompatybilność wsteczną - utworzenie pojedynczego pola pickup_location
                if data.get("pickup_location_code") and data.get("pickup_address"):
                    data["pickup_location"] = f"{data['pickup_location_code']}: {data['pickup_address']}"
                
                            
                # Ustaw domyślne godziny otwarcia jeśli nie zostały podane
                if not data.get("available_hours"):
                    data["available_hours"] = "PN-SB 06-20" 
                
                # Dodaj email jako customer_name jeśli brakuje
                if recipient_email and not data.get("customer_name"):
                    data["customer_name"] = recipient_email
                
                # Dodaj user_key dla wyszukiwania zamówień w arkuszu
                if recipient_email:
                    data["user_key"] = recipient_email.split('@')[0]
                
                # Formatowanie numeru telefonu
                if data.get("phone_number"):
                    data["phone_number"] = self._format_phone_for_display(data["phone_number"])
                
                # Walidacja pola qr_code — akceptujemy URL lub payload P|telefon|kod lub pusty string
                if 'qr_code' in data:
                    qr_data = str(data.get('qr_code') or '').strip()
                    if qr_data.startswith(('http://', 'https://')):
                        data['qr_code'] = qr_data  # OK — to URL
                    elif qr_data.startswith('P|') and qr_data.count('|') == 2:
                        data['qr_code'] = qr_data  # OK — payload InPost, Python zakoduje | jako %7C
                    else:
                        # AI zwróciło tekst (np. "załącznik", "brak", "null") — czyścimy
                        if qr_data:
                            logging.warning(f"⚠️ AI zwróciło nieprawidłową wartość qr_code: '{qr_data}' — czyszczę do ''")
                        data['qr_code'] = ''
                
            except json.JSONDecodeError as e:
                logging.error(f"Błąd parsowania JSON: {e}")
                data = {"customer_name": recipient_email} if recipient_email else {}
            
            # Sprawdź czy w mailu są informacje o godzinach otwarcia, ale tylko jeśli AI nie znalazło
            if not data.get("available_hours"):
                hours_pattern = re.search(r'Godziny.+?(\d{1,2}-\d{1,2})|(\d{1,2}:\d{2}.+?\d{1,2}:\d{2})', email_body)
                if hours_pattern:
                    data["available_hours"] = hours_pattern.group(0)
                elif "24/7" in email_body or "24 godz" in email_body:
                    data["available_hours"] = "24/7"
            
            return data
            
        except Exception as e:
            logging.error(f"Błąd podczas ekstrakcji danych z powiadomienia o odbiorze: {e}")
            # Zwróć podstawowe informacje
            result = {
                "user_key": recipient_email.split('@')[0] if recipient_email else None,
                "customer_name": recipient_email,
                "available_hours": "PN-SB 06-20",
                "pickup_code": "",
                "pickup_location_code": "",
                "pickup_address": "",
                "pickup_deadline": ""
            }
            
            # Próbuj wyciągnąć kod paczkomatu nawet w przypadku błędu
            try:
                import re as regex_fallback
                location_match = regex_fallback.search(r'([A-Z]{3}\d{2}[A-Z]{3,4})', email_body)
                if location_match:
                    result["pickup_location_code"] = location_match.group(1)
            except:
                pass
                
            return result

    def _format_phone_for_display(self, phone_number):
        """Formatuje numer telefonu do wyświetlenia: usuwa +48 i dodaje spacje co 3 cyfry"""
        if not phone_number:
            return ""
            
        # Usuń wszystko poza cyframi
        digits_only = re.sub(r'\D', '', phone_number)
        
        # Jeśli numer ma prefiks kraju (np. 48xxxxxxxxx), usuń go aby zostało 9 cyfr
        if len(digits_only) > 9:
            digits_only = digits_only[-9:]  # Zostaw tylko ostatnie 9 cyfr
        
        # Dodaj spacje co 3 cyfry: XXX XXX XXX
        if len(digits_only) == 9:
            formatted = f"{digits_only[0:3]} {digits_only[3:6]} {digits_only[6:9]}"
        else:
            # Jeśli numer jest krótszy, podziel go najlepiej jak się da
            chunks = [digits_only[i:i+3] for i in range(0, len(digits_only), 3)]
            formatted = " ".join(chunks)
            
        return formatted

    def _extract_aliexpress_link(self, email_body):
        """Wyciąga link do zamówienia AliExpress z treści maila"""
        import re
        link_pattern = re.search(r'https://www\.aliexpress\.com/p/order/detail\.html\?orderId=\d+[^"\s<>]+', email_body)
        if link_pattern:
            return link_pattern.group(0)
        return None

    def _extract_key_sections(self, email_body, order_number=None):
        """Ekstrahuje tylko kluczowe sekcje z dużego maila HTML"""
        import re
        from bs4 import BeautifulSoup
        
        # Jeśli to nie jest HTML, zwróć oryginalny tekst
        if not ("<html" in email_body or "<body" in email_body):
            return email_body[:15000]
            
        try:
            # Parsuj HTML
            soup = BeautifulSoup(email_body, 'html.parser')
            
            # Przygotuj kontener na istotne sekcje
            important_parts = []
            extracted_text = []
            
            # 1. Szukaj tabeli z informacjami o zamówieniu (typowa struktura AliExpress)
            order_tables = soup.find_all('table', width=re.compile(r'(100%|600|650)'))
            for table in order_tables[:3]:  # Weź tylko pierwsze 3 tabele
                if table.get_text() and (
                    'zamówienie' in table.get_text().lower() or 
                    'order' in table.get_text().lower() or
                    'produkt' in table.get_text().lower()
                ):
                    important_parts.append(str(table))
            
            # 2. Szukaj konkretnych fragmentów związanych z zamówieniem
            if order_number:
                order_elements = soup.find_all(string=re.compile(order_number))
                for elem in order_elements:
                    # Znajdź rodzica tego elementu
                    parent = elem.parent
                    if parent:
                        important_parts.append(str(parent))
            
            # 3. Szukaj adresu dostawy
            address_keywords = ['adres', 'dostawa', 'shipping', 'address']
            for keyword in address_keywords:
                address_elements = soup.find_all(string=re.compile(keyword, re.IGNORECASE))
                for elem in address_elements[:2]:  # Ogranicz do pierwszych 2 wyników
                    parent = elem.parent
                    for _ in range(3):  # Idź 3 poziomy wyżej, aby złapać pełną sekcję
                        if parent:
                            parent = parent.parent
                    if parent:
                        important_parts.append(str(parent))
            
            # 4. Szukaj informacji o produkcie
            product_keywords = ['produkt', 'item', 'towar']
            for keyword in product_keywords:
                product_elements = soup.find_all(string=re.compile(keyword, re.IGNORECASE))
                for elem in product_elements[:2]:
                    parent = elem.parent
                    for _ in range(2):
                        if parent:
                            parent = parent.parent
                    if parent:
                        important_parts.append(str(parent))
            
            # 5. Szukaj linku do zamówienia
            links = soup.find_all('a', href=re.compile(r'aliexpress\.com/p/order/detail'))
            for link in links[:2]:
                important_parts.append(str(link))
                
            # Wyodrębnij tekst z sekcji HTML
            for part in important_parts:
                part_soup = BeautifulSoup(part, 'html.parser')
                text = part_soup.get_text(separator=' ', strip=True)
                extracted_text.append(text)
                
            # Dodaj nagłówki
            extracted_text.insert(0, "=== POCZĄTEK ISTOTNYCH DANYCH ===")
            extracted_text.append("=== KONIEC ISTOTNYCH DANYCH ===")
            
            result = '\n\n'.join(extracted_text)
            
            # Jeśli wynik jest zbyt mały, dodaj część oryginalnego tekstu
            if len(result) < 1000:
                plain_text = soup.get_text(separator=' ', strip=True)
                result += "\n\n=== DODATKOWY TEKST ===\n\n" + plain_text[:10000]
                
            return result
                
        except Exception as e:
            logging.error(f"Błąd podczas ekstrakcji kluczowych sekcji: {e}")
            # Awaryjnie zwróć początek tekstu
            return email_body[:15000]

    def _fallback_extraction_pickup(self, email_body, subject, recipient_email=None):
        """Awaryjne wyciąganie danych z powiadomień InPost o paczkach do odbioru"""
        import re  # Dodaj lokalny import
        
        # Ustaw domyślne wartości
        result = {
            "customer_name": recipient_email,
            "user_key": recipient_email,
            "pickup_code": "",  # Puste wartości domyślne dla kluczowych pól
            "pickup_location_code": "",
            "pickup_address": "",
            "pickup_deadline": "",
            "available_hours": "PN-SB 06-20"  # Domyślna wartość dla godzin
        }
        
        try:
            logging.info(f"Rozpoczynam awaryjną ekstrakcję InPost dla adresu: {recipient_email}")
            
            # Szukaj kodu odbioru (różne formaty w mailach InPost)
            pickup_code_patterns = [
                # Pattern 1: Standardowy format "Kod odbioru: 123456"
                r'[Kk]od\s+odbioru[:=\s]*[\s<>]*(\d{6})[\s<>]*',
                # Pattern 2: Format HTML z ozdobnikami
                r'<[^>]*>Kod\s+odbioru<[^>]*>[^<]*<[^>]*>(\d{6})<',
                # Pattern 3: Format w tytule lub nagłówku
                r'Twój kod[^\d]*(\d{6})',
                # Pattern 4: W elemencie <b> lub <strong>
                r'<(?:b|strong)[^>]*>(\d{6})<\/(?:b|strong)>',
                # Pattern 5: Po frazie "kod paczki" lub "kod przesyłki"
                r'(?:kod\s+(?:paczki|przesyłki|do\s+odbioru))[^\d<>]*(\d{6})'
            ]
            
            # Spróbuj znaleźć kod odbioru przy użyciu różnych wzorców
            for pattern in pickup_code_patterns:
                match = re.search(pattern, email_body, re.IGNORECASE)
                if match and match.group(1) and len(match.group(1)) == 6:
                    result["pickup_code"] = match.group(1)
                    logging.info(f"Znaleziono kod odbioru: {match.group(1)} przy użyciu wzorca: {pattern}")
                    break
            
            # Wyciągnij lokalizację paczkomatu (format XXX00XXX)
            location_match = re.search(r'([A-Z]{3}\d{2}[A-Z]{3,4})', email_body)
            if location_match:
                location_code = location_match.group(1)
                result["pickup_location_code"] = location_code
                
                # Szukaj adresu paczkomatu z różnymi wzorcami
                address_patterns = [
                    # Pattern 1: Adres po kodzie paczkomatu z niewielką odległością
                    rf'{location_code}[^<>\n]*?([^<>\n]{{10,100}}(?:ul\.|ulica|aleja|al\.|plac|[0-9]{{1,3}})[^<>\n]{{5,100}})',
                    # Pattern 2: Po konkretnych frazach
                    r'(?:adres|miejsce|znajduje się|lokalizacja)[^<>\n:]*:?[^<>\n]*?([^<>\n]{10,100}(?:ul\.|ulica|aleja|al\.|plac|[0-9]{1,3})[^<>\n]{5,100})',
                    # Pattern 3: "na stacji" lub "przy"
                    r'(?:na stacji|przy)[^<>\n]*?([^<>\n]{5,100})'
                ]
                
                for pattern in address_patterns:
                    address_match = re.search(pattern, email_body, re.IGNORECASE)
                    if address_match:
                        # Oczyść tekst adresu
                        address = address_match.group(1).strip()
                        # Usuń zbędne HTML tagi
                        address = re.sub(r'<[^>]+>', ' ', address)
                        # Oczyść wielokrotne spacje
                        address = re.sub(r'\s+', ' ', address).strip()
                        
                        # Sprawdź czy adres jest sensownej długości
                        if len(address) > 5 and len(address) < 150:
                            result["pickup_address"] = address
                            result["pickup_location"] = f"{location_code}: {address}"
                            logging.info(f"Znaleziono adres: {address[:30]}...")
                            break
            
            # Wyciągnij termin odbioru
            deadline_patterns = [
                r'[Cc]zas na odbi[óo]r\s+do[:\s]*[^<]*?(\d{1,2}[/-]\d{1,2}).*?(\d{1,2}:\d{2})',
                r'[Tt]ermin\s+odbioru[:\s]*[^<]*?(\d{1,2}[/-]\d{1,2})'
            ]
            
            for pattern in deadline_patterns:
                deadline_match = re.search(pattern, email_body)
                if deadline_match:
                    result["pickup_deadline"] = deadline_match.group(1).replace("/", ".")
                    # Jeśli znaleziono również godzinę
                    if len(deadline_match.groups()) > 1 and deadline_match.group(2):
                        result["available_hours"] = f"do {deadline_match.group(2)}"
                    break
            
            # Wyciągnij numer telefonu
            phone_match = re.search(r'(?:telefon|phone|tel)[^<>:\d]*[:<>]*\s*([+]?[\d\s\-]{7,15})', email_body, re.IGNORECASE)
            if phone_match:
                phone = self._format_phone_for_display(phone_match.group(1))
                result["phone_number"] = phone
            
            # Dodaj kompletność dla diagnostyki
            missing_fields = []
            for field in ["pickup_code", "pickup_location_code", "pickup_address", "pickup_deadline"]:
                if field not in result or not result[field]:
                    missing_fields.append(field)
            
            if missing_fields:
                logging.warning(f"Brakujące pola po awaryjnej ekstrakcji InPost: {', '.join(missing_fields)}")
            
            logging.info(f"Wyciągnięte dane z awaryjnej ekstrakcji InPost: {result}")
            
        except Exception as e:
            logging.error(f"Błąd w awaryjnej ekstrakcji InPost: {e}")
        
        return result

    def _extract_section(self, text, section_marker, chars_after=300):
        """Wyciąga fragment tekstu zaczynający się od określonego markera"""
        import re
    
        if isinstance(section_marker, str):
            flexible_marker = section_marker.replace(" ", "\\s+")
            patterns = [
                # ZWIĘKSZ KONTEKST - więcej znaków przed i po
                f"(.{{0,200}}{section_marker}.{{0,{chars_after}}})",  # ZWIĘKSZ KONTEKST PRZED
                f"(.{{0,200}}{flexible_marker}.{{0,{chars_after}}})",
                f"(<[^>]*>{section_marker}[^<]*</[^>]*>.{{0,{chars_after}}})"
            ]
        else:
            patterns = [
                f"(.{{0,200}}{section_marker}.{{0,{chars_after}}})"
            ]
    
        for pattern in patterns:
            try:
                match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                if match:
                    return match.group(1)
            except Exception as e:
                logging.error(f"Błąd w _extract_section dla wzorca {pattern}: {e}")
    
        return None

    def _call_openai_api(self, prompt):
        prompt_size = len(prompt)
        estimated_tokens = prompt_size / 4
        
        # ✅ DODAJ PEŁNY DEBUG PROMPTU
        logging.info(f"📝 PEŁNY PROMPT WYSYŁANY DO AI:")
        logging.info(f"📏 Rozmiar promptu: {prompt_size} znaków ({estimated_tokens:.0f} tokenów)")
        logging.info("="*80)
        logging.info(prompt)  # ✅ CAŁKOWITY PROMPT
        logging.info("="*80)
    
        # Sprawdź rozmiar przed wysłaniem
        if estimated_tokens > 7600:
            logging.warning(f"Prompt przekracza limit tokenów ({estimated_tokens:.0f} > 8000). Przerwanie przetwarzania.")
            # Zwróć None lub rzuć wyjątek, aby przerwać normalne przetwarzanie
            return None
            
        # Kontynuuj tylko jeśli prompt jest odpowiedniego rozmiaru    
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Jesteś pomocnikiem, który wyciąga strukturalne dane z maili."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            
            response_text = response.choices[0].message.content
            
            # ✅ ROZSZERZ DEBUG ODPOWIEDZI
            logging.info(f"🤖 SUROWA ODPOWIEDŹ Z OPENAI:")
            logging.info(f"📏 Rozmiar odpowiedzi: {len(response_text)} znaków")
            logging.info("="*80)
            logging.info(response_text)  # ✅ CAŁA ODPOWIEDŹ
            logging.info("="*80)
            
            cleaned_response = self._clean_json_response(response_text)
            
            try:
                parsed_json = json.loads(cleaned_response)
                logging.info(f"✅ SPARSOWANY JSON: {json.dumps(parsed_json, indent=2, ensure_ascii=False)}")
                return parsed_json
            except json.JSONDecodeError as e:
                logging.error(f"❌ Błąd parsowania JSON: {e}")
                logging.error(f"❌ Problematyczny tekst: {cleaned_response}")
                return None
                
        except Exception as e:
            if "413" in str(e) or "tokens_limit_reached" in str(e):
                logging.warning(f"Treść maila przekracza limit tokenów OpenAI. Rozmiar: {len(prompt)} znaków. Używam awaryjnej ekstrakcji.")
            else:
                logging.error(f"Błąd podczas wywoływania OpenAI API: {e}")
            return None

    def extract_dhl_notification_data(self, email_body, subject=None, recipient_email=None):
        """Wyciąga dane z powiadomień DHL o różnych statusach przesyłki"""
        try:
            max_chars = 25000  # Zwiększ z 5000 do 13000 znaków
            
            if len(email_body) > max_chars:
                logging.info(f"Treść maila DHL jest bardzo duża ({len(email_body)} znaków). Wykonuję celowaną ekstrakcję.")
                
                # Znajdź i wyodrębnij najważniejsze fragmenty
                important_sections = []
                
                # 1. Numer przesyłki (format DHL: JJD + ciąg cyfr)
                tracking_patterns = ["numer przesyłki", "nr przesyłki", "tracking number", "JJD\\d+", "numer paczki"]
                for pattern in tracking_patterns:
                    tracking_section = self._extract_section(email_body, pattern, 400)
                    if tracking_section:
                        important_sections.append(tracking_section)
                        break
                
                # 2. Wyciągnij fragment z adresem punktu odbioru
                location_patterns = ["automat dhl box", "dhl box", "doręczenie do automatu", "teofila firlika", "szczecin"]
                for pattern in location_patterns:
                    location_section = self._extract_section(email_body, pattern, 600)
                    if location_section:
                        important_sections.append(location_section)
                        break
                
                # 3. Termin odbioru
                deadline_patterns = ["Odbierz ją do", "odbierz do", "do dnia", "termin", "planowane doręczenie"]
                for pattern in deadline_patterns:
                    deadline_section = self._extract_section(email_body, pattern, 400)
                    if deadline_section:
                        important_sections.append(deadline_section)
                        break
                        
                # 4. Godziny dostępności
                hours_patterns = ["godziny otwarcia", "punkt czynny", "godziny pracy", "pon-pt", "sob-niedz"]
                for pattern in hours_patterns:
                    hours_section = self._extract_section(email_body, pattern, 400)
                    if hours_section:
                        important_sections.append(hours_section)
                        break
                
                # 5. Kod odbioru (PIN)
                code_patterns = ["PIN", "kod odbioru", "pin do odbioru", "odbierz.*podając"]
                for pattern in code_patterns:
                    code_section = self._extract_section(email_body, pattern, 400)
                    if code_section:
                        important_sections.append(code_section)
                        break

                # 6. Nadanie
                code_patterns = [ "czekasz na paczkę od CAINIAO", "już do Ciebie jedzie!"]
                for pattern in code_patterns:
                    code_section = self._extract_section(email_body, pattern, 400)
                    if code_section:
                        important_sections.append(code_section)
                        break

                # Połącz wyciągnięte fragmenty
                extracted_body = "\n\n".join(important_sections)
                
                # Jeśli mamy mało tekstu, dodaj więcej
                if len(extracted_body) < 10000:
                    # Dodaj pierwsze 3000 znaków z oryginalnego maila
                    extracted_body += "\n\n--- DODATKOWY TEKST ---\n\n" + email_body[:10000]
                
                email_body = extracted_body
                logging.info(f"Po celowanej ekstrakcji rozmiar tekstu: {len(email_body)} znaków")
            
            # Przygotuj prompt dla ChatGPT
            prompt = f"""
Wyodrębnij następujące dane z poniższego e-maila od DHL (zwróć tylko dane w formacie JSON):
- carrier_package_number: główny numer przesyłki DHL (format JJD lub 3S lub JVGL + cyfry, np. JJD000030185064000048049759) - lecz nie zawsze
- pickup_location: dokładny adres automatu DHL BOX (jeśli występuje)
- pickup_deadline: termin odbioru przesyłki (jeśli występuje, format DD-MM-RRRR)
- available_hours: godziny otwarcia automatu (jeśli występuje)
- pickup_code: PIN do odbioru przesyłki (jeśli występuje, 6 cyfr)
- expected_delivery_date: przewidywana data dostawy (jeśli występuje, format DD-MM-RRRR)
- delivery_date: faktyczna data dostarczenia (jeśli występuje, format DD-MM-RRRR)
- sender: nadawca przesyłki (jeśli występuje, np. CAINIAO)

Temat e-maila: {subject}

Treść e-maila:
{email_body}

Zwróć TYLKO JSON w następującym formacie (puste pola pozostaw jako puste stringi):
{{
  "carrier_package_number": "",
  "pickup_location": "",
  "pickup_deadline": "",
  "available_hours": "",
  "pickup_code": "",
  "expected_delivery_date": "",
  "delivery_date": "",
  "sender": ""
}}
"""
            
            # Wywołaj API OpenAI
            response = self._call_openai_api(prompt)
            
            if response:
                # Zawsze dodaj informację o przewoźniku
                response["carrier"] = "DHL"
                return response
            else:
                # Brak odpowiedzi z OpenAI - użyj awaryjnej metody
                return self._fallback_extraction_dhl(email_body, subject)
                
        except Exception as e:
            logging.error(f"Błąd podczas ekstrakcji danych DHL: {e}")
            return self._fallback_extraction_dhl(email_body, subject)
            
    def _fallback_extraction_dhl(self, email_body, subject=None):
        """Awaryjna ekstrakcja danych DHL za pomocą wyrażeń regularnych"""
        result = {"carrier": "DHL"}
        
        # Wyciągnij numer przesyłki JJD
        jjd_match = re.search(r'(JJD\d+)', email_body)
        if jjd_match:
            result["package_number"] = jjd_match.group(1)
        
        # Wyciągnij numer przesyłki w nawiasie
        secondary_match = re.search(r'przesyłki\s+(\d{8,15})', email_body)
        if secondary_match:
            result["secondary_package_number"] = secondary_match.group(1)
        
        # Wyciągnij PIN do odbioru
        pin_match = re.search(r'PIN\s+(\d{6})', email_body)
        if pin_match:
            result["pickup_code"] = pin_match.group(1)
        
        # Wyciągnij termin odbioru
        deadline_match = re.search(r'odbierz ją do (\d{2}-\d{2}-\d{4})', email_body)
        if deadline_match:
            result["pickup_deadline"] = deadline_match.group(1)
        
        # Wyciągnij adres automatu
        location_match = re.search(r'AUTOMAT[^A-Z0-9]*([A-Za-z\s,.]+\d{1,5},\s*\d{5}\s[A-Załż]+)', email_body, re.IGNORECASE)
        if location_match:
            result["pickup_location"] = location_match.group(1).strip()
        
        # Wyciągnij godziny otwarcia
        hours_match = re.search(r'Godziny otwarcia:(.*?)(?:\n\n|\r\n\r\n|$)', email_body, re.DOTALL)
        if hours_match:
            result["available_hours"] = hours_match.group(1).strip().replace('\n', ' ')
        
        # Wyciągnij nadawcę
        sender_match = re.search(r'paczk[aę] od ([A-Z]+)[?]', email_body)
        if sender_match:
            result["sender"] = sender_match.group(1)
        
        return result
    
    def general_extract_carrier_notification_data(self, email_body, subject, carrier_name, recipient_email, email_date=None):
        """
        Uniwersalna funkcja ekstrakcji danych z powiadomień przewoźników
        
        Args:
            carrier_name: Nazwa przewoźnika (DPD, InPost, DHL, AliExpress)
            email_body: Treść wiadomości email
            subject: Temat wiadomości
            recipient_email: Email odbiorcy (z nagłówka To:)
            
        Returns:
            dict: Słownik z wyodrębnionymi danymi
        """
    
        try:
            
            if not self._rate_limit():
                logging.warning("⚠️ Skipping OpenAI request - rate limit exceeded")
                return None
        
            to_header = f"Adres email odbiorcy (To:): {recipient_email}" if recipient_email else "Brak informacji o odbiorcy"

            # Oblicz rok z daty maila — AI używa go gdy mail nie zawiera pełnej daty
            from datetime import datetime as _dt
            if email_date and hasattr(email_date, 'year'):
                email_year = email_date.year
                email_date_str = email_date.strftime('%d.%m.%Y')
            elif isinstance(email_date, str) and email_date:
                try:
                    _parsed = _dt.fromisoformat(email_date)
                    email_year = _parsed.year
                    email_date_str = _parsed.strftime('%d.%m.%Y')
                except Exception:
                    email_year = _dt.now().year
                    email_date_str = email_date
            else:
                email_year = _dt.now().year
                email_date_str = 'nieznana'
                     
            # ZMIEŃ LIMIT Z 25000 NA 15000 - bo template promptu też zajmuje miejsce
            if len(email_body) > 15000: 
                
                if hasattr(self, 'general_extract_carrier_content'):
                    email_body = self.general_extract_carrier_content(email_body, carrier_name)
                    logging.info(f"Po ekstrakcji: {len(email_body)} znaków")
                else:
                    email_body = email_body[:12000] + "\n[SKRÓCONO - BRAK FUNKCJI]"
            else:
                logging.info(f"Email {carrier_name} w limicie: {len(email_body)} znaków")
            
            # DODAJ SPRAWDZENIE PRZED UTWORZENIEM PROMPTU
            estimated_prompt_size = len(email_body) + 7000  # +7000 na template promptu
            if estimated_prompt_size > 28000:
                logging.warning(f"Przewidywany rozmiar promptu za duży ({estimated_prompt_size}). Dodatkowe skrócenie.")
                email_body = email_body[:12000] + "\n[SKRÓCONO PRZED PROMPTEM]"
            
        
            # Reszta kodu z promptem pozostaje bez zmian...
            prompt = f"""
            Przeanalizuj poniższy email od {carrier_name}. Email może dotyczyć jednego z etapów przesyłki:

            1. NADANIE PRZESYŁKI - Email zawiera informację o nadaniu paczki (np. słowa "Poszło!", "wyruszyła w podróż"). Ustaw ten status, nawet jeśli w mailu podany jest docelowy adres paczkomatu, ale paczka jeszcze tam nie dotarła. Tylko gdy paczka dotrze do POLSKI i zostanie przekaza dla kuriera jak INPOST, DPD, DHL, POCZTA POLSKA. Jeśli to Aliexpress - nigdy dla niego nie ustawiaj statusu shipment_sent.
            Z tego typu maila wyciągnij:
            - Ustaw status przesyłki: "shipment_sent" (OBOWIĄZKOWO)
            - Numer przesyłki od danego przewoźnika (package_number) - różne formaty:
                DPD: zazwyczaj 13 cyfr + 1 litera, np. 0000363570900W
                DHL: JJD/3S/JVGL + cyfry, np. JJD000030185064000048049759 
                InPost: zazwyczaj 24 cyfry, np. 520000012680041086770098
                GLS: rózne formaty
                Poczta Polska: np. PX1945096838, zaczyna sie zazywczaj od PX

            - Data nadania (shipping_date) - format DD.MM.YYYY
            - Planowany termin doręczenia (expected_delivery_date) - format DD.MM.YYYY
            - Adres dostawy (delivery_address)
            - Email odbiorcy (email)
            - Pamiętaj że jeśli to email od aliexpress to nie ustawiaj statusu shipment_sent - 
              to status tylko dla lokalnych przewozników. Dla Aliexpress może być in transit o czym mowa dalej.

            2. DOSTAWA DZIŚ / GOTOWE DO ODBIORU - Email informujący, że paczka czeka już fizycznie w punkcie/paczkomacie LUB kurier dostarczy ją dzisiaj pod drzwi. Ustaw status "pickup", jeśli w mailu znajduje się kod odbioru (dla automatów/punktów) LUB jest wyraźna informacja, że paczka jest w doręczeniu i kurier przyjedzie z nią DZISIAJ. Jeśli paczka dopiero wyruszyła od nadawcy i nie ma mowy o dostawie na "dziś", to jest to NADANIE (shipment_sent). Możliwa zmiana magazynu (paczkomatu) - to także pickup.
            Z tego typu maila wyciągnij:
            - Ustaw status przesyłki: "pickup" (OBOWIĄZKOWO)
            - Numer przesyłki (package_number)
            - Miejsce odbioru (pickup_location) - punkt DHL, paczkomat InPost itd., adres doręczenia
            - Kod odbioru (pickup_code) - PIN, kod odbioru
            - Termin odbioru (pickup_deadline) - format DD.MM.YYYY
            - Godziny dostępności (available_hours) - godziny otwarcia punktu odbioru, np. "PN-SB 06-20"
            - Imię kuriera (courier_name)
            - Telefon kuriera (courier_phone)
            - Telefon do odboru (phone_number) - jeśli dostępny
            - Link do kodu QR (qr_code) dla dhl np. https://ccs-image.dhl.com/barcodes/e845cbd1-eac1-4a2a-ab05-d039c8b9ce78.jpg
              lub dla Inpost "P|phone|pickup_code" czyli np. "P|908009092|464714" (bez spacji) i wstaw do szalbonu https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=QR_CONTENT czyli https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=P|908009092|464714
            - Pamietaj, dLa kodu qr nie pomijaj przedrostka https://

            3. DORĘCZONO - Email potwierdzający dostarczenie paczki.
            Z tego typu maila wyciągnij:
            - Ustaw status przesyłki: "delivered" (OBOWIĄZKOWO)
            - Numer przesyłki (package_number)
            - Data doręczenia (delivery_date) - format DD.MM.YYYY
            - Email odbiorcy (email)
            
            4. POTWIERDZENIE ZAMÓWIENIA - Potwierdzenie zakupu w sklepie internetowym Aliexpress.
            Z tego typu maila wyciągnij:
            - Ustaw status przesyłki: "confirmed" (OBOWIĄZKOWO) 
            - Numer zamówienia (order_number)
            - Data zamówienia (order_date) - format DD.MM.YYYY
            - Nazwa produktu (product_name)
            - Adres dostawy (delivery_address)
            - Numer telefonu (phone_number)
            - Email zamawiającego (email)
            - Link do zamówienia (item_link)
            - Przewidywany czas dostawy (estimated_delivery)

            5. TRANSIT - paczka po potwierdzeniu wyruszyla do Polski (mail od Aliexpress)
            - Ustaw status przesyłki: "transit" (OBOWIĄZKOWO) 

            6. Utworznie paczki przez inpost (nie nadanie!)
            - Ustaw status przesyłki: "created_by_inpost" (OBOWIĄZKOWO) 

            Nagłówek To: {to_header}
            Temat maila: {subject}
            Data wysłania maila: {email_date_str} — WAŻNE: jeśli w treści maila brak roku, użyj roku {email_year} z tej daty!

            Treść maila:
            {email_body}

            WAŻNE: 
            - OBOWIĄZKOWO zwróć odpowiedni status w polu "status" dla typu powiadomienia:
              * "shipment_sent" - dla powiadomienia o nadaniu - JESLI ZNASZ PRZEWOZNIKA I NIE JEST NIM ALIEXPRESS
              * "pickup" - TYLKO jeśli paczka fizycznie czeka na odbiór w skrytce/punkcie (szukaj wtedy kodu PIN/QR) LUB gdy mail mówi, że kurier doręczy ją DZISIAJ pod wskazany adres.
              * "delivered" - dla powiadomienia o dostarczeniu 
              * "confirmed" - dla potwierdzenia zamówienia
              * "transit" - dla informacji o przesyłce w transporcie - TYLKO JESLI MAIL OD ALIEXPRESS - czyli paczka wyruszyla do Poslki po potwierdzeniu zamowienia.
            - Format daty powinien być zawsze DD.MM.YYYY (np. 18.05.2025)
            - W polu email umieść adres email odbiorcy z nagłówka To
            - Jeśli nie możesz znaleźć niektórych danych, pozostaw te pola puste
            - W polu info połącz dodatkowe informacje (np. o kurierze, czasie dostawy)
            - Na podstawie treści zdecyduj jakiego typu jest to powiadomienie (1, 2, 3 czy 4)
            - Zwróć typy danych charakterystyczne dla danego typu powiadomienia (np. pickup_code tylko dla odbioru)
            - Pamiętaj, że "available_hours" oznacza godziny otwarcia punktu odbioru
            - Telefon podawaj po 3 cyfry, np. 506 575 068
            - Zwróć uwagę czy dana paczka została już dostarczona do automatu czy dopiero została do niego wysłana. Np zwróc uwagę na słowa: Poinformujemy Cię ponownie, gdy paczka dotrze do automatu DHL BOX. Czy dopiero została wysłana!!!
            - PRZEANALIZUJ DOKŁADNIE CZY PACZKA Z DHL JEST DOPIERO WYSŁANA CZY JUŻ DO ODBIORU i ustal odpowiednio status
            - ZWRÓĆ TYLKO JSON z danymi, nie dodawaj żadnych dodatkowych informacji ani komentarzy
            - Dla GLS format może się róznić - tylko dla niego sam oceń
            - Jeśli numer zawiera prefiks +48, usuń go i podaj tylko właściwe 9 cyfr numeru polskiego. Np. +48720191029 to numer: 720 191 029 (BEZ +48!)

            Jeśli dostałeś przypadkowy mail to zwróć pusty JSON: {{}}, jedynie w info i status zwróć "unknown" i "unknown" jako status.

            Odpowiedź sformatuj JEDYNIE jako obiekt JSON z wszystkimi możliwymi kluczami dla danego typu powiadomienia.
            
            Poniżej dokładna przykładowa struktura odpowiedzi JSON dla każdego typu powiadomienia:
            
            1. NADANIE PRZESYŁKI:
            {{
              "package_number": "0000363570900W",
              "shipping_date": "24.05.2025",
              "expected_delivery_date": "28.05.2025",
              "delivery_address": "ul. Matejki 10/1, 71-614 Szczecin",
              "email": "{recipient_email}",
              "carrier": "{carrier_name}",
              "status": "shipment_sent"
              "info": "Nadano paczkę do punktu odbioru. Przewidywany czas dostawy: 28.05.2025."
            }}
            
            2. DOSTAWA DZIŚ / GOTOWE DO ODBIORU:
            {{
              "package_number": "0000363570900W",
              "pickup_location": "Paczkomat SZC01M, ul. Bazarowa 10, 71-614 Szczecin",
              "pickup_location_code": "SZC01M",
              "pickup_code": "123456",
              "pickup_deadline": "28.05.2025",
              "available_hours": "PN-SB 06-20",
              "courier_name": "Jakub",
              "courier_phone": "506 575 068",
              "phone_number": "502 575 068",
              "qr_code": "https://link-do-qr.pl/123456",
              "email": "{recipient_email}",
              "carrier": "{carrier_name}",
              "status": "pickup"
              "info": "Kurier Jakub dostarczy paczkę dzisiaj. Jego tel: 412512123."
            }}
            
            3. DORĘCZONO:
            {{
              "package_number": "0000363570900W",
              "delivery_date": "24.05.2025",
              "email": "{recipient_email}",
              "recipient_info": "Przesyłka odebrana osobiście przez adresata",
              "carrier": "{carrier_name}",
              "status": "delivered"
            }}
            
            4. POTWIERDZENIE ZAMÓWIENIA:
            {{
              "order_number": "8041215699357896",
              "order_date": "20.05.2025",
              "product_name": "Słuchawki bezprzewodowe Xiaomi",
              "delivery_address": "ul. Matejki 10/1, 71-614 Szczecin",
              "phone_number": "506 575 068",
              "email": "{recipient_email}",
              "item_link": "https://www.aliexpress.com/p/order/detail.html?orderId=8041215699357896",
              "estimated_delivery": "10.06.2025 - 25.06.2025",
              "carrier": "{carrier_name}",
              "status": "confirmed"
            }}

            5. TRANSIT:
            {{
            "status": "transit"
            }}

            6. Created_by_inpost
            {{
            "status": "created_by_inpost"
            }}
            """

            # Dostosuj prompt dla AliExpress
            if carrier_name.lower() == "aliexpress":
                prompt += """
                Dodatkowo zwróć szczególną uwagę na:
                - Numer zamówienia (format: liczba 10+ cyfr)
                - Link do zamówienia (zaczynający się od https://www.aliexpress.com/)
                - Dane produktu - nazwa, cena, ilość
                - Przewidywany czas dostawy
                - CZY JUZ ZOSTALA WYSLANA - WTEDY ZMIANIASZ TYLKO STATUS NA TRANSIT
                """
        
            # Dostosuj prompt dla InPost
            elif carrier_name.lower() == "inpost":
                prompt += """
                Dodatkowo zwróć szczególną uwagę na:
                - Kod paczkomatu (format: XXX00XXX, np. POZ01M)
                - Kod odbioru (6 cyfr)
                - Adres paczkomatu
                - Link do kodu QR lub informację o załączniku zawierającym kod QR
                - Godziny otwarcia paczkomatu
                """

            elif carrier_name.lower() == "pocztapolska":
                prompt += """
                Specyficzne instrukcje dla Poczty Polskiej / Pocztex:
                1. STATUSY:
                   - Jeśli treść zawiera "została do Ciebie nadana" -> ustaw status "shipment_sent"
                   - Jeśli treść zawiera "została wydana do doręczenia" -> ustaw status "pickup" (ponieważ kurier jedzie i wymaga PINu)
                   - Jeśli treść zawiera "awizo" lub "do odbioru w placówce" -> ustaw status "pickup"
                   - Jeśli treść zawiera "dziękujemy za odbiór" -> ustaw status "delivered"
                
                2. DANE DO WYCIĄGNIĘCIA:
                   - Numer przesyłki: często format PX + cyfry (np. PX1945096838) lub (00)...
                   - Kod odbioru: szukaj frazy "Kod PIN" (np. 849938) -> wpisz to w polu "pickup_code"
                   - Telefon kuriera: szukaj frazy "Telefon do kuriera" -> wpisz w "courier_phone"
                   - W polu "info" połącz telefon kuriera i nadawcę (np. "Kurier tel: 887850473 | Od: CAINIAO")
                """

            # Wywołaj OpenAI API
            response = self._call_openai_api(prompt)
            
            if response is None:
                logging.warning(f"Brak odpowiedzi z API dla {carrier_name}. Używam awaryjnej ekstrakcji.")
                return self.general_fallback_extraction(email_body, subject, carrier_name, recipient_email)
            
            # Dalsze przetwarzanie odpowiedzi...
            response["carrier"] = carrier_name
            if recipient_email and not response.get("email"):
                response["email"] = recipient_email
            if recipient_email:
                response["user_key"] = recipient_email.split('@')[0]
            if not response.get("customer_name") and recipient_email:
                response["customer_name"] = recipient_email
            
            logging.info(f"Wyciągnięte dane z powiadomienia {carrier_name}: {response}")
            return response
    
        except Exception as e:
            logging.error(f"Błąd podczas ekstrakcji danych z powiadomienia {carrier_name}: {e}")
            return self.general_fallback_extraction(email_body, subject, carrier_name, recipient_email)
            
    def _standardize_date(self, date_string):
        """Konwertuje różne formaty dat na DD.MM.YYYY"""
        try:
            # Zamień różne separatory na "."
            normalized = re.sub(r'[-/]', '.', date_string)
            
            # Sprawdź format daty
            parts = normalized.split('.')
            if len(parts) != 3:
                return date_string  # nie można znormalizować
                
            # Jeśli format YYYY.MM.DD, zmień na DD.MM.YYYY
            if len(parts[0]) == 4:  # pierwszy element to rok (YYYY)
                return f"{parts[2]}.{parts[1]}.{parts[0]}"
                
            # Jeśli już jest w formacie DD.MM.YYYY, zwróć
            return normalized
            
        except Exception:
            return date_string  # w razie błędu zwróć oryginalny ciąg
        

    def general_extract_carrier_content(self, email_body, carrier_name):
        """
        Uniwersalna funkcja ekstrakcji kluczowych informacji z maili różnych przewoźników.
        Ogranicza rozmiar treści dla dalszego przetwarzania przez API.
        
        Args:
            email_body: Pełna treść emaila
            carrier_name: Nazwa przewoźnika (DHL, InPost, DPD, AliExpress)
            
        Returns:
            str: Wyekstrahowane kluczowe sekcje treści
        """
        try:
            logging.debug(f"PEŁNA TREŚĆ EMAILA ({len(email_body)} znaków):\n{email_body}")

            logging.info(f"Treść maila {carrier_name} jest zbyt duża ({len(email_body)} znaków). Wykonuję ekstrakcję kluczowych sekcji.")

            # Usuń informacje o przekazywaniu wiadomości
            email_body = self._remove_forward_headers(email_body)
            logging.info(f"Po usunięciu nagłówków Forward: {len(email_body)} znaków")
            
            max_chars = 20000
            
            if len(email_body) <= max_chars:
                return email_body
            
            logging.info(f"Treść maila {carrier_name} jest bardzo duża ({len(email_body)} znaków). Wykonuję celowaną ekstrakcję.")
            
            important_sections = []
            
            if carrier_name.lower() == "dhl":
                logging.info("Rozpoczynam ekstrakcję dla DHL...")
                
                # 1. Numer przesyłki DHL (JJD, 3S, JVGL) - DODAJ DEBUGGING
                tracking_patterns = ["JJD\\d{18,25}", "3S\\d{10,15}", "JVGL\\d{10,15}"]
                for pattern in tracking_patterns:
                    section = self._extract_section(email_body, pattern, 1500)
                    if section:
                        logging.info(f"Znaleziono sekcję tracking dla wzorca {pattern}: {len(section)} znaków")
                        important_sections.append(section)
                        break
                    else:
                        logging.info(f"Nie znaleziono sekcji dla wzorca tracking: {pattern}")
                
                # 2. Status przesyłki - DODAJ DEBUGGING
                status_patterns = ["czekasz na paczkę", "już do Ciebie jedzie", "poinformujemy cię ponownie", 
                                "czeka na ciebie w automacie", "przesyłka dotarła", "PIN", "odbierz ją do"]
                for pattern in status_patterns:
                    section = self._extract_section(email_body, pattern, 2000)
                    if section:
                        logging.info(f"Znaleziono sekcję status dla wzorca {pattern}: {len(section)} znaków")
                        important_sections.append(section)
                    else:
                        logging.info(f"Nie znaleziono sekcji dla wzorca status: {pattern}")
                
                # 3. Lokalizacja - DODAJ DEBUGGING  
                location_patterns = ["automat dhl", "dhl box", "lokalizacja automatu", "adres automatu", "punkt odbioru"]
                for pattern in location_patterns:
                    section = self._extract_section(email_body, pattern, 2000)
                    if section:
                        logging.info(f"Znaleziono sekcję lokalizacji dla wzorca {pattern}: {len(section)} znaków")
                        important_sections.append(section)
                    else:
                        logging.info(f"Nie znaleziono sekcji dla wzorca lokalizacji: {pattern}")
                
                # 4. PIN i kod odbioru - DODAJ DEBUGGING
                pin_patterns = ["PIN", "kod odbioru", "\\d{6}", "odbierz.*podając"]
                for pattern in pin_patterns:
                    section = self._extract_section(email_body, pattern, 1000)
                    if section:
                        logging.info(f"Znaleziono sekcję PIN dla wzorca {pattern}: {len(section)} znaków")
                        important_sections.append(section)
                    else:
                        logging.info(f"Nie znaleziono sekcji dla wzorca PIN: {pattern}")
                
                # 5. Termin odbioru - DODAJ DEBUGGING
                deadline_patterns = ["odbierz ją do", "termin odbioru", "dostępna do", "planowane doręczenie"]
                for pattern in deadline_patterns:
                    section = self._extract_section(email_body, pattern, 1000)
                    if section:
                        logging.info(f"Znaleziono sekcję terminu dla wzorca {pattern}: {len(section)} znaków")
                        important_sections.append(section)
                    else:
                        logging.info(f"Nie znaleziono sekcji dla wzorca terminu: {pattern}")
                
                # 6. DODAJ WIĘCEJ WZORCÓW DLA DHL
                additional_patterns = ["godziny otwarcia", "nadawca", "CAINIAO", "przedmiot", "uwagi"]
                for pattern in additional_patterns:
                    section = self._extract_section(email_body, pattern, 800)
                    if section:
                        logging.info(f"Znaleziono dodatkową sekcję dla wzorca {pattern}: {len(section)} znaków")
                        important_sections.append(section)
                    else:
                        logging.info(f"Nie znaleziono dodatkowej sekcji dla wzorca: {pattern}")
                        
            elif carrier_name.lower() == "inpost":
                logging.info("Rozpoczynam ekstrakcję dla InPost...")
                
                # 1. Numer przesyłki InPost
                tracking_patterns = ["\\d{20}", "numer przesyłki", "nr przesyłki"]
                for pattern in tracking_patterns:
                    section = self._extract_section(email_body, pattern, 1000)
                    if section:
                        logging.info(f"Znaleziono sekcję tracking InPost: {len(section)} znaków")
                        important_sections.append(section)
                        break
                
                # 2. Kod paczkomatu i lokalizacja
                location_patterns = ["[A-Z]{3}\\d{2}[A-Z]{2,4}", "paczkomat", "appkomat", "lokalizacja"]
                for pattern in location_patterns:
                    section = self._extract_section(email_body, pattern, 2000)
                    if section:
                        logging.info(f"Znaleziono sekcję lokalizacji InPost: {len(section)} znaków")
                        important_sections.append(section)
                
                # 3. Kod odbioru
                code_patterns = ["kod odbioru", "\\d{6}", "zeskanuj kod QR"]
                for pattern in code_patterns:
                    section = self._extract_section(email_body, pattern, 1200)
                    if section:
                        logging.info(f"Znaleziono sekcję kodu InPost: {len(section)} znaków")
                        important_sections.append(section)
                
                # 4. Status przesyłki
                status_patterns = ["została nadana", "czeka na ciebie", "została dostarczona", 
                                "potwierdzenie nadania", "paczka już na ciebie czeka"]
                for pattern in status_patterns:
                    section = self._extract_section(email_body, pattern, 1500)
                    if section:
                        logging.info(f"Znaleziono sekcję statusu InPost: {len(section)} znaków")
                        important_sections.append(section)
                        
            elif carrier_name.lower() == "dpd":
                logging.info("Rozpoczynam ekstrakcję dla DPD...")
                
                # 1. Numer przesyłki DPD
                tracking_patterns = ["\\d{13}[A-Z]", "numer przesyłki", "nr paczki"]
                for pattern in tracking_patterns:
                    section = self._extract_section(email_body, pattern, 1000)
                    if section:
                        logging.info(f"Znaleziono sekcję tracking DPD: {len(section)} znaków")
                        important_sections.append(section)
                        break
                
                # 2. Status dostawy
                status_patterns = ["została nadana", "bezpieczne doręczenie", "doręczone", 
                                "kurier doręczy", "oceń jakość dostawy"]
                for pattern in status_patterns:
                    section = self._extract_section(email_body, pattern, 1500)
                    if section:
                        logging.info(f"Znaleziono sekcję statusu DPD: {len(section)} znaków")
                        important_sections.append(section)
                
                # 3. Informacje o kurierze
                courier_patterns = ["kurier", "data doręczenia", "godzina doręczenia"]
                for pattern in courier_patterns:
                    section = self._extract_section(email_body, pattern, 1200)
                    if section:
                        logging.info(f"Znaleziono sekcję kuriera DPD: {len(section)} znaków")
                        important_sections.append(section)
                
                # 4. Adres dostawy
                address_patterns = ["adres dostawy", "doręczamy pod adres"]
                for pattern in address_patterns:
                    section = self._extract_section(email_body, pattern, 1200)
                    if section:
                        logging.info(f"Znaleziono sekcję adresu DPD: {len(section)} znaków")
                        important_sections.append(section)
                        
            elif carrier_name.lower() == "aliexpress":
                logging.info("Rozpoczynam ekstrakcję dla AliExpress...")
                
                # 1. Numer zamówienia
                order_patterns = ["zamówienie \\d+", "order \\d+", "\\d{13,16}"]
                for pattern in order_patterns:
                    section = self._extract_section(email_body, pattern, 1200)
                    if section:
                        logging.info(f"Znaleziono sekcję zamówienia AliExpress: {len(section)} znaków")
                        important_sections.append(section)
                        break
                
                # 2. Status zamówienia
                status_patterns = ["zamówienie potwierdzone", "order confirmed", "payment received"]
                for pattern in status_patterns:
                    section = self._extract_section(email_body, pattern, 1000)
                    if section:
                        logging.info(f"Znaleziono sekcję statusu AliExpress: {len(section)} znaków")
                        important_sections.append(section)
                        break
                
                # 3. Szczegóły produktu
                product_patterns = ["szczegóły zamówienia", "order details", "produkt"]
                for pattern in product_patterns:
                    section = self._extract_section(email_body, pattern, 1500)
                    if section:
                        logging.info(f"Znaleziono sekcję produktu AliExpress: {len(section)} znaków")
                        important_sections.append(section)
                        break
                
                # 4. Adres dostawy
                address_patterns = ["adres dostawy", "shipping address", "dostawa"]
                for pattern in address_patterns:
                    section = self._extract_section(email_body, pattern, 1000)
                    if section:
                        logging.info(f"Znaleziono sekcję adresu AliExpress: {len(section)} znaków")
                        important_sections.append(section)
                        break
                    
            elif carrier_name.lower() == "pocztapolska":
                logging.info("Rozpoczynam ekstrakcję dla Poczty Polskiej...")
                
                # 1. Numer przesyłki (PX... lub (00)...)
                tracking_patterns = ["PX\\d{10,}", "\\(00\\)\\d{18}", "numer przesyłki", "nr przesyłki"]
                for pattern in tracking_patterns:
                    section = self._extract_section(email_body, pattern, 1000)
                    if section:
                        logging.info(f"Znaleziono sekcję tracking Poczty: {len(section)} znaków")
                        important_sections.append(section)
                        break

                # 2. Kod PIN / Odbiór
                pickup_patterns = ["Kod PIN", "kod odbioru", "do odbioru w placówce", "awizo"]
                for pattern in pickup_patterns:
                    section = self._extract_section(email_body, pattern, 800)
                    if section:
                        logging.info(f"Znaleziono sekcję pickup Poczty: {len(section)} znaków")
                        important_sections.append(section)

                # 3. Statusy
                status_patterns = ["została do Ciebie nadana", "wydana do doręczenia", "doręczona", "odebrana"]
                for pattern in status_patterns:
                    section = self._extract_section(email_body, pattern, 1000)
                    if section:
                        logging.info(f"Znaleziono sekcję statusu Poczty: {len(section)} znaków")
                        important_sections.append(section)

            else:
                logging.info(f"Nieznany przewoźnik {carrier_name}, używam ogólnej strategii...")
                # Dla nieznanych przewoźników - użyj ogólnej strategii
                order_match = re.search(r'[Oo]rder(?:\s+|\s*[:#]\s*)(\d+)|[Zz]amów[^\d]+(\d+)', 
                                    email_body[:1000])
                order_number = None
                if order_match:
                    order_number = order_match.group(1) or order_match.group(2)
                
                return self._extract_key_sections(email_body, order_number)
            
            # Połącz wyekstrahowane części
            extracted_body = "\n\n".join(important_sections)
            logging.info(f"Połączono {len(important_sections)} sekcji, razem: {len(extracted_body)} znaków")
            
            # ZWIĘKSZ PRÓG I DODAJ WIĘCEJ TEKSTU
            if len(extracted_body) < 12000:
                logging.info(f"Za mało tekstu ({len(extracted_body)} znaków), dodaję więcej...")
                # Dodaj pierwsze 15000 znaków z oryginalnego maila
                additional_text = email_body[:10000]
                extracted_body += "\n\n--- DODATKOWY TEKST ---\n\n" + additional_text
                logging.info(f"Po dodaniu dodatkowego tekstu: {len(extracted_body)} znaków")
            
            # JEŚLI NADAL ZA MAŁO
            if len(extracted_body) < 10000:
                logging.info(f"Nadal za mało ({len(extracted_body)} znaków), dodaję środek emaila...")
                middle_start = len(email_body) // 3
                middle_text = email_body[middle_start:middle_start + 8000]
                extracted_body += "\n\n--- ŚRODEK TEKSTU ---\n\n" + middle_text
                logging.info(f"Po dodaniu środka tekstu: {len(extracted_body)} znaków")
            
            logging.info(f"FINAL: Po celowanej ekstrakcji rozmiar tekstu: {len(extracted_body)} znaków")
            logging.debug(f"PEŁNA TREŚĆ EMAILA PO EXTRAKCJI ({len(extracted_body)} znaków):\n{extracted_body}")

            return extracted_body
                
        except Exception as e:
            logging.error(f"Błąd podczas ekstrakcji treści {carrier_name}: {e}")
            return email_body[:15000]
        
    def _remove_forward_headers(self, email_body):
        """
        Usuwa nagłówki przekazywania wiadomości (Forward headers) z treści emaila.
        POPRAWIONA WERSJA - mniej agresywna
        """
        try:
            # ZMIEŃ WZORCE - bardziej precyzyjne
            forward_patterns = [
                r'---------- Forwarded message ---------',  # USUŃ .*?(?=\n\n|\r\n\r\n)
                r'^From:.*?<.*?>.*?$',  # DODAJ ^ i $ dla całej linii
                r'^Date:.*?\d{4}.*?$',
                r'^Subject: Fwd:.*?$',  # Tylko linia z Fwd:
                r'^To:.*?<.*?>.*?$',
                # USUŃ te wzorce - są zbyt agresywne:
                # r'Fwd:.*?(?=\n)',
                # r'Inbox\s*(?=\n)',
                # r'.*?<.*?@.*?>\s*(?=\n)',
                # r'.*?\(\d+ days? ago\)\s*(?=\n)',
                # r'to me\s*(?=\n)'
            ]
            
            cleaned_body = email_body
            
            for pattern in forward_patterns:
                cleaned_body = re.sub(pattern, '', cleaned_body, flags=re.MULTILINE | re.IGNORECASE)
            
            # Usuń nadmiarowe puste linie
            cleaned_body = re.sub(r'\n{3,}', '\n\n', cleaned_body)
            cleaned_body = cleaned_body.strip()
            
            # DODAJ SPRAWDZENIE - jeśli usunęło za dużo, zwróć oryginalny tekst
            if len(cleaned_body) < len(email_body) * 0.3:  # Jeśli zostało mniej niż 30% tekstu
                logging.warning(f"_remove_forward_headers usunęło za dużo tekstu ({len(email_body)} -> {len(cleaned_body)}). Zwracam oryginalny tekst.")
                return email_body
            
            logging.info(f"_remove_forward_headers: {len(email_body)} -> {len(cleaned_body)} znaków")
            return cleaned_body
            
        except Exception as e:
            logging.error(f"Błąd podczas usuwania nagłówków Forward: {e}")
            return email_body
    
    def general_fallback_extraction(self, email_body, subject, carrier_name, recipient_email=None):
        """
        SCALONA FUNKCJA AWARYJNA (FALLBACK).
        Łączy logikę general_fallback_extraction i general_fallback_extraction.
        Używa wyrażeń regularnych, gdy AI zawiedzie.
        """
        import re
        
        # 1. Wstępne czyszczenie
        try:
            email_body = self._remove_forward_headers(email_body)
        except: pass

        # 2. Przygotuj podstawowy obiekt wyniku
        result = {
            "carrier": carrier_name,
            "email": recipient_email,
            "customer_name": recipient_email,
            "user_key": recipient_email.split('@')[0] if recipient_email else None,
            "status": "unknown",
            "info": "Dane wyodrębnione awaryjnie (Regex)"
        }
        
        carrier_lower = carrier_name.lower()
        
        try:
            # =================================================================
            # OBSŁUGA DHL
            # =================================================================
            if "dhl" in carrier_lower:
                # Numer przesyłki (JJD / 3S / JVGL)
                tracking_match = re.search(r'(JJD\d{18,25}|3S\d{10,15}|JVGL\d{10,15})', email_body)
                if tracking_match:
                    result["package_number"] = tracking_match.group(1)
                
                # PIN do odbioru
                pin_match = re.search(r'PIN\s*(\d{6})', email_body, re.IGNORECASE)
                if pin_match:
                    result["pickup_code"] = pin_match.group(1)
                    result["status"] = "pickup"

                # Termin odbioru
                deadline_match = re.search(r'odbierz ją do (\d{2}-\d{2}-\d{4})', email_body)
                if deadline_match:
                    result["pickup_deadline"] = deadline_match.group(1)

                # Wykrywanie statusu po słowach kluczowych
                body_lower = email_body.lower()
                if "już do ciebie jedzie" in body_lower or "przekazana kurierowi" in body_lower:
                    result["status"] = "transit"
                elif "czeka na ciebie" in body_lower or "gotowa do odbioru" in body_lower:
                    result["status"] = "pickup"
                elif "doręczona" in body_lower or "dostarczona" in body_lower:
                    result["status"] = "delivered"
                elif "nadana" in body_lower:
                    result["status"] = "shipment_sent"

            # =================================================================
            # OBSŁUGA INPOST
            # =================================================================
            elif "inpost" in carrier_lower:
                # Numer przesyłki (24 cyfry)
                tracking_match = re.search(r'(\d{24})', email_body)
                if tracking_match:
                    result["package_number"] = tracking_match.group(1)
                
                # Kod paczkomatu (np. POZ01M)
                locker_match = re.search(r'([A-Z]{3}\d{2}[A-Z]{2,4})', email_body)
                if locker_match:
                    result["pickup_location_code"] = locker_match.group(1)
                
                # Kod odbioru (6 cyfr)
                code_match = re.search(r'(?:kod odbioru|kodem|kod)[:\s]*(\d{6})', email_body, re.IGNORECASE)
                if code_match:
                    result["pickup_code"] = code_match.group(1)
                    result["status"] = "pickup"

                # Wykrywanie statusu
                body_lower = email_body.lower()
                if "została nadana" in body_lower:
                    result["status"] = "transit" # Lub shipment_sent, ale transit bezpieczniejszy dla InPost
                elif "czeka na ciebie" in body_lower or "gotowa do odbioru" in body_lower:
                    result["status"] = "pickup"
                elif "została dostarczona" in body_lower or "odebrana" in body_lower:
                    result["status"] = "delivered"
                elif "potwierdzenie utworzenia paczki" in body_lower:
                    result["status"] = "created_by_inpost"

            # =================================================================
            # OBSŁUGA DPD
            # =================================================================
            elif "dpd" in carrier_lower:
                # Numer przesyłki (13 cyfr + litera)
                tracking_match = re.search(r'(\d{13}[A-Z]?)', email_body)
                if tracking_match:
                    result["package_number"] = tracking_match.group(1)
                
                # Numer referencyjny
                ref_match = re.search(r'Numer\s+referencyjny[^:]*:\s*([A-Z0-9]+)', email_body)
                if ref_match:
                    result["reference_number"] = ref_match.group(1)

                # Wykrywanie statusu
                body_lower = email_body.lower()
                if "została nadana" in body_lower:
                    result["status"] = "shipment_sent"
                elif "doręczy" in body_lower or "w drodze" in body_lower:
                    result["status"] = "transit"
                elif "doręczone" in body_lower or "dostarczona" in body_lower:
                    result["status"] = "delivered"
                elif "gotowa" in body_lower and "punkt" in body_lower:
                    result["status"] = "pickup"

            # =================================================================
            # OBSŁUGA ALIEXPRESS
            # =================================================================
            elif "aliexpress" in carrier_lower or "cainiao" in carrier_lower:
                # Numer zamówienia
                order_match = re.search(r'[Oo]rder(?:\s+|\s*[:#]\s*)(\d{10,})|[Zz]amów[^\d]+(\d{10,})', subject + " " + email_body[:1000])
                if order_match:
                    result["order_number"] = order_match.group(1) or order_match.group(2)
                
                # Link do zamówienia
                link_match = re.search(r'(https://www\.aliexpress\.com/p/order/detail\.html\?orderId=\d+[^\s"<>]+)', email_body)
                if link_match:
                    result["item_link"] = link_match.group(1)

                # Wykrywanie statusu (uwzględnij temat!)
                body_lower = email_body.lower()
                subj_lower = subject.lower() # To już masz
                
                # Łączymy body i temat dla pewności
                combined_text = body_lower + " " + subj_lower 
                
                if "potwierdzone" in combined_text or "confirmed" in combined_text:
                    result["status"] = "confirmed"
                elif "wysłane" in combined_text or "shipped" in combined_text or "transit" in combined_text:
                    result["status"] = "transit"
                elif "dostarczon" in combined_text or "delivered" in combined_text:
                    result["status"] = "delivered"
                elif "closed" in combined_text or "zamknięte" in combined_text:
                    result["status"] = "closed"
                    
            # =================================================================
            # OBSŁUGA POCZTY POLSKIEJ
            # =================================================================
            elif "poczta" in carrier_lower:
                # Numer przesyłki (PX... lub (00)...)
                tracking_match = re.search(r'(PX\d{10,})|(\(00\)\d{18})', email_body)
                if tracking_match:
                    result["package_number"] = tracking_match.group(1) or tracking_match.group(2)

                # Status
                body_lower = email_body.lower()
                if "nadana" in body_lower: result["status"] = "shipment_sent"
                elif "wydana do doręczenia" in body_lower: result["status"] = "transit"
                elif "awizo" in body_lower or "placówce" in body_lower: result["status"] = "pickup"
                elif "doręczona" in body_lower or "odebrana" in body_lower: result["status"] = "delivered"

            # =================================================================
            # EKSTRAKCJA DAT (Wspólna dla wszystkich)
            # =================================================================
            date_patterns = [
                r'(\d{2}[.-]\d{2}[.-]\d{4})', # DD.MM.YYYY
                r'(\d{4}-\d{2}-\d{2})',       # YYYY-MM-DD
                r'(\d{2}/\d{2}/\d{4})'        # DD/MM/YYYY
            ]
            
            for pattern in date_patterns:
                date_match = re.search(pattern, email_body)
                if date_match:
                    found_date = self._standardize_date(date_match.group(1))
                    
                    # Logika przypisania daty
                    if result.get("status") == "delivered":
                        result["delivery_date"] = found_date
                    elif result.get("status") == "shipment_sent":
                        result["shipping_date"] = found_date
                    elif result.get("status") == "pickup" and "pickup_deadline" not in result:
                        # Czasami data w mailu o odbiorze to deadline
                        pass 
                    break

            logging.info(f"⚡ Awaryjna ekstrakcja ({carrier_name}): Status={result.get('status')}, Nr={result.get('package_number') or result.get('order_number')}")
            return result
            
        except Exception as e:
            logging.error(f"Błąd w general_fallback_extraction dla {carrier_name}: {e}")
            # Zwróć chociaż minimum danych, żeby nie wysypać programu
            return result