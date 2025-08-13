import imaplib
import email
from email.header import decode_header
import re
from datetime import datetime, timedelta
import config
import logging
import json
import os
import time  # Dodaj ten import
from openai_handler import OpenAIHandler
import pytz  # DODAJ TO
from email.utils import parsedate_to_datetime

class EmailHandler:
    def __init__(self):
        """Inicjalizacja obsługi email"""
        self.mappings_file = "user_mappings.json"
        self.user_mappings = {}
        self.last_check_time = time.time() - (3600 * 24)  # 24 godziny wstecz
        self.openai_handler = OpenAIHandler()

        self.email_sources = {
            'gmail': {
                'imap_server': 'imap.gmail.com',
                'port': 993
            },
            'interia': {
                'imap_server': 'poczta.interia.pl',
                'port': 993
            },
            'o2': {  # ✅ DODAJ O2
                'imap_server': 'poczta.o2.pl',
                'port': 993
            }
        }
        
        try:
            with open(self.mappings_file, 'r') as f:
                self.user_mappings = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.user_mappings = {}

        # Inicjalizacja handlerów danych - ✅ POPRAWIONA KOLEJNOŚĆ
        from carriers_data_handlers import AliexpressDataHandler, InPostDataHandler, DHLDataHandler, DPDDataHandler, GLSDataHandler
        self.data_handlers = [
            GLSDataHandler(self),           # ✅ GLS NAJPIERW!
            InPostDataHandler(self),        # InPost ma specyficzne wzorce
            DHLDataHandler(self),           # DHL ma specyficzne wzorce
            AliexpressDataHandler(self),    # AliExpress
            DPDDataHandler(self),           # ✅ DPD NA KOŃCU (najogólniejszy)
        ]
        
        self.local_tz = pytz.timezone('Europe/Warsaw')  # DODAJ TO

    def _load_mappings(self):
        """Wczytuje zapisane mapowania z pliku"""
        if os.path.exists(self.mappings_file):
            try:
                with open(self.mappings_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Błąd podczas ładowania mapowań: {e}")
        return {}
    
    def _save_mappings(self):
        """Zapisuje mapowania użytkowników do pliku JSON z ładnym formatowaniem"""
        try:
            with open(self.mappings_file, 'w', encoding='utf-8') as f:
                # ✅ DODAJ indent=2 dla czytelności
                json.dump(self.user_mappings, f, indent=2, ensure_ascii=False)
            logging.info(f"Zapisano mapowania do {self.mappings_file}")
        except Exception as e:
            logging.error(f"Błąd podczas zapisywania mapowań: {e}")
    
    def _save_user_order_mapping(self, user_key, order_number):
        """Zapisuje powiązanie użytkownika z numerem zamówienia - tylko jedno aktywne"""
        if not user_key or not order_number:
            return
            
        if user_key not in self.user_mappings:
            self.user_mappings[user_key] = {"order_numbers": [], "package_numbers": []}
        
        if "order_numbers" not in self.user_mappings[user_key]:
            self.user_mappings[user_key]["order_numbers"] = []
            
        # Jeśli użytkownik już ma zamówienia, dodaj nowe tylko jeśli jest unikalne
        if order_number not in self.user_mappings[user_key]["order_numbers"]:
            # Jedna uwaga: skoro w danym czasie użytkownik może mieć tylko jedno zamówienie,
            # możemy zresetować listę i dodać tylko najnowsze, ale zachowamy historię dla bezpieczeństwa
            self.user_mappings[user_key]["order_numbers"].append(order_number)
            logging.info(f"Zapisano powiązanie: użytkownik '{user_key}' -> zamówienie {order_number}")
            self._save_mappings()
        
    def _save_user_package_mapping(self, user_key, package_number):
        """Zapisuje powiązanie użytkownika z numerem paczki"""
        if not user_key or not package_number:
            return
            
        if user_key not in self.user_mappings:
            self.user_mappings[user_key] = {"order_numbers": [], "package_numbers": []}
        
        if "package_numbers" not in self.user_mappings[user_key]:
            self.user_mappings[user_key]["package_numbers"] = []
            
        if package_number not in self.user_mappings[user_key]["package_numbers"]:
            self.user_mappings[user_key]["package_numbers"].append(package_number)
            logging.info(f"Zapisano powiązanie: użytkownik '{user_key}' -> paczka {package_number}")
            self._save_mappings()
        
    
    
    def fetch_new_emails(self):
        """Pobieranie NIEPRZECZYTANYCH e-maili z ostatnich X dni ze wszystkich kont"""
        all_emails = []
            
        # ✅ UŻYJ KONFIGURACJI Z config.py
        from config import EMAIL_CHECK_SETTINGS
        days_back = EMAIL_CHECK_SETTINGS.get('days_back', 14)
        fallback_limit = EMAIL_CHECK_SETTINGS.get('fallback_limit', 50)
        max_emails = EMAIL_CHECK_SETTINGS.get('max_emails_per_account', 100)
        mark_as_read = EMAIL_CHECK_SETTINGS.get('mark_as_read', True)  # ✅ NOWA OPCJA
        
        # ✅ OBLICZ DATĘ GRANICZNĄ (X DNI WSTECZ)
        from datetime import datetime, timedelta
        cutoff_date = datetime.now() - timedelta(days=days_back)
        date_string = cutoff_date.strftime('%d-%b-%Y')  # Format: "15-May-2025"
        
        logging.info(f"📅 Sprawdzanie NIEPRZECZYTANYCH emaili od {date_string} ({days_back} dni wstecz)")
        
        for email_config in config.ALL_EMAIL_CONFIGS:
            source = email_config.get('source', 'gmail')
            email_addr = email_config.get('email')
            password = email_config.get('password')
            
            if not email_addr or not password:
                logging.warning(f"Pomijanie {source}: brak kompletnej konfiguracji")
                continue
            
            logging.info(f"🔍 Sprawdzanie NIEPRZECZYTANYCH emaili {source}: {email_addr}")
            
            client = self.connect_to_email_account(email_config)
            if not client:
                continue
            
            # ✅ LISTA EMAILI DO OZNACZENIA JAKO PRZECZYTANE
            emails_to_mark_read = []
                
            try:
                client.select("INBOX")
                
                # ✅ KOMBINUJ KRYTERIA: UNSEEN + SINCE (NIEPRZECZYTANE Z OSTATNICH X DNI)
                if source.lower() == 'o2':
                    logging.info(f"🔍 O2: Zastosowanie specjalnych limitów - max 50 NIEPRZECZYTANYCH emaili od {date_string}")
                    
                    # ✅ KOMBINUJ UNSEEN + SINCE DLA O2
                    search_criteria = f'(UNSEEN SINCE "{date_string}")'
                    status, messages = client.search(None, search_criteria)
                    
                    if status == "OK" and messages[0]:
                        all_unread_list = messages[0].split()
                        total_unread = len(all_unread_list)
                        
                        logging.info(f"📧 O2: Znaleziono {total_unread} nieprzeczytanych emaili z ostatnich {days_back} dni")
                        
                        # Weź maksymalnie 50 najnowszych
                        if total_unread > 50:
                            messages_to_process = all_unread_list[-50:]  # 50 najnowszych
                            logging.info(f"📧 O2: Ograniczenie do 50 najnowszych z {total_unread}")
                        else:
                            messages_to_process = all_unread_list
                        
                        messages = [b' '.join(messages_to_process)]
                        status = "OK"
                    else:
                        messages = [b'']
                        status = "OK"
                        logging.info(f"📭 O2: Brak nieprzeczytanych emaili od {date_string}")
                
                else:
                    # ✅ DLA INNYCH KONT - KOMBINUJ UNSEEN + SINCE
                    search_criteria = f'(UNSEEN SINCE "{date_string}")'
                    logging.info(f"📅 {source}: Szukanie NIEPRZECZYTANYCH emaili od {date_string}")
                    status, messages = client.search(None, search_criteria)
                
                # ✅ PRZETWARZANIE WYNIKÓW
                if status == "OK" and messages[0]:
                    all_msg_list = messages[0].split()
                    
                    # Dodatkowe ograniczenie bezpieczeństwa dla wszystkich kont
                    if len(all_msg_list) > max_emails:
                        messages_to_process = all_msg_list[-max_emails:]  # Najnowsze
                        logging.info(f"⚠️ Dodatkowe ograniczenie {source}: {len(all_msg_list)} → {max_emails} najnowszych z ostatnich {days_back} dni")
                    else:
                        messages_to_process = all_msg_list
                    
                    logging.info(f"📧 Przetwarzanie {len(messages_to_process)} NIEPRZECZYTANYCH emaili z ostatnich {days_back} dni z {source}")
                    
                    # ✅ SORTUJ EMAILE PO ID (NAJNOWSZE PIERWSZE!)
                    messages_to_process.sort(key=lambda x: int(x.decode()), reverse=True)
                    
                    for num in messages_to_process:
                        status, msg_data = client.fetch(num, "(RFC822)")
                        if status == "OK":
                            raw_email = msg_data[0][1]
                            
                            try:
                                email_message = email.message_from_bytes(raw_email)
                            except UnicodeDecodeError:
                                try:
                                    decoded_content = raw_email.decode('iso-8859-2')
                                    email_message = email.message_from_string(decoded_content)
                                except Exception:
                                    decoded_content = raw_email.decode('utf-8', errors='ignore')
                                    email_message = email.message_from_string(decoded_content)
                            
                            # ✅ SPRAWDŹ DATĘ EMAILA PRZED DODANIEM
                            email_date = self.extract_email_date(email_message)

                            # ✅ DEKODUJ TEMAT PRZED LOGOWANIEM
                            try:
                                raw_subject = email_message.get('Subject', 'Brak tematu')
                                logging.debug(f"🔍 RAW subject: {raw_subject}")
                                
                                # ✅ UŻYJ NOWEJ FUNKCJI
                                email_subject = self.decode_email_subject(raw_subject)
                                logging.debug(f"🔍 DEKODOWANY TEMAT: '{email_subject}'")
                                
                            except Exception as e:
                                logging.error(f"❌ Błąd podczas dekodowania tematu: {e}")
                                email_subject = str(email_message.get('Subject', 'Brak tematu'))

                            # ✅ TERAZ LOGUJ Z DEKODOWANYM TEMATEM
                            logging.info(f"📧 Email ID {num.decode()}: {email_date} | {email_subject}")

                            # ✅ DODATKOWA WERYFIKACJA DATY (PODWÓJNE SPRAWDZENIE)
                            if email_date:
                                email_dt = datetime.strptime(email_date, '%Y-%m-%d %H:%M:%S')
                                if email_dt < cutoff_date:
                                    logging.info(f"⏭️ Email z {email_date} starszy niż {days_back} dni - pomijam")
                                    # ✅ DODAJ DO LISTY DO OZNACZENIA JAKO PRZECZYTANE (NAWET JEŚLI POMIJAMY)
                                    emails_to_mark_read.append(num)
                                    continue

                            all_emails.append((source, email_message))
                            # ✅ DODAJ EMAIL DO LISTY DO OZNACZENIA JAKO PRZECZYTANE
                            emails_to_mark_read.append(num)
                else:
                    logging.info(f"📭 Brak nieprzeczytanych emaili z ostatnich {days_back} dni w {source}")
                    
            except Exception as e:
                logging.warning(f"⚠️ Błąd wyszukiwania nieprzeczytanych z zakresu dat dla {source}: {e}")
                # W przypadku błędu, nie oznaczaj emaili jako przeczytane
                emails_to_mark_read = []
                    
            finally:
                # ✅ OZNACZ EMAILE JAKO PRZECZYTANE PRZED ZAMKNIĘCIEM POŁĄCZENIA
                if mark_as_read and emails_to_mark_read:
                    try:
                        logging.info(f"📖 Oznaczanie {len(emails_to_mark_read)} emaili jako przeczytane w {source}")
                        
                        for num in emails_to_mark_read:
                            try:
                                # Oznacz email jako przeczytany
                                client.store(num, '+FLAGS', '\\Seen')
                                logging.debug(f"✅ Email {num.decode()} oznaczony jako przeczytany")
                            except Exception as e:
                                logging.warning(f"⚠️ Nie udało się oznaczyć emaila {num.decode()} jako przeczytany: {e}")
                        
                        # Zapisz zmiany na serwerze
                        client.expunge()
                        logging.info(f"✅ Zapisano zmiany dla {len(emails_to_mark_read)} emaili w {source}")
                        
                    except Exception as e:
                        logging.error(f"❌ Błąd podczas oznaczania emaili jako przeczytane w {source}: {e}")
                
                try:
                    client.close()
                    client.logout()
                except:
                    pass
        
        logging.info(f"📧 Łącznie pobrano {len(all_emails)} NIEPRZECZYTANYCH emaili z ostatnich {days_back} dni ze wszystkich kont")
        return all_emails
    
    def get_email_body(self, email_message):
        """Wydobycie treści e-maila"""
        body = ""
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain" or content_type == "text/html":
                    try:
                        body_part = part.get_payload(decode=True).decode()
                        body += body_part
                    except Exception:
                        pass
        else:
            try:
                body = email_message.get_payload(decode=True).decode()
            except Exception:
                pass
        return body
    
    def extract_email_date(self, email_message):
        """
        Wyciąga datę z nagłówka emaila i zwraca w formacie string
        
        Args:
            email_message: Obiekt email message
            
        Returns:
            str: Data w formacie 'YYYY-MM-DD HH:MM:SS' lub None
        """
        try:
            date_header = email_message.get('Date')
            if date_header:
                # Parsuj datę z nagłówka
                
                dt_with_tz = parsedate_to_datetime(date_header)
                
                # Konwertuj do lokalnej strefy czasowej
                dt_local = dt_with_tz.astimezone(self.local_tz)
                
                # Zwróć jako string
                return dt_local.strftime('%Y-%m-%d %H:%M:%S')
            else:
                logging.warning("Brak nagłówka Date w emailu")
                return None
                
        except Exception as e:
            logging.error(f"Błąd podczas wyciągania daty z emaila: {e}")
            return None
    
    def should_update_based_on_date(self, new_email_date, existing_email_date):
        """
        Sprawdza czy należy zaktualizować dane na podstawie porównania dat
        
        Args:
            new_email_date: Data nowego emaila (string)
            existing_email_date: Data istniejącego emaila w arkuszu (string)
            
        Returns:
            bool: True jeśli należy zaktualizować, False w przeciwnym razie
        """
        try:
            if not new_email_date:
                logging.warning("Brak daty nowego emaila - pomijam aktualizację")
                return False
                
            if not existing_email_date:
                logging.info("Brak daty w arkuszu - aktualizuję")
                return True
            
            # Konwertuj stringi na datetime
            new_dt = datetime.strptime(new_email_date, '%Y-%m-%d %H:%M:%S')
            existing_dt = datetime.strptime(existing_email_date, '%Y-%m-%d %H:%M:%S')
            
            # Aktualizuj tylko jeśli nowy email jest nowszy
            should_update = new_dt > existing_dt
            
            if should_update:
                logging.info(f"Nowy email ({new_email_date}) jest nowszy niż istniejący ({existing_email_date}) - aktualizuję")
            else:
                logging.info(f"Nowy email ({new_email_date}) jest starszy niż istniejący ({existing_email_date}) - pomijam")
                
            return should_update
            
        except Exception as e:
            logging.error(f"Błąd podczas porównywania dat: {e}")
            # W przypadku błędu, aktualizuj żeby nie blokować procesu
            return True

    def process_emails(self):
        """Przetwarzanie wszystkich nowych e-maili Z DATAMI - OD NAJNOWSZYCH"""
        emails = self.fetch_new_emails()
        processed_data = []
        
        # ✅ SORTUJ EMAILE PO DATACH (NAJNOWSZE PIERWSZE!)
        emails_with_dates = []
        for email_source, email_msg in emails:
            email_date = self.extract_email_date(email_msg)
            emails_with_dates.append((email_source, email_msg, email_date))
        
        # Sortuj po datach - NAJNOWSZE PIERWSZE
        emails_with_dates.sort(key=lambda x: x[2] if x[2] else "1900-01-01 00:00:00", reverse=True)
        
        logging.info(f"📧 Przetwarzanie {len(emails_with_dates)} emaili od NAJNOWSZYCH do najstarszych")
        
        for email_source, email_msg, email_date in emails_with_dates:
            try:
                # ✅ LOGUJ DATĘ NA POCZĄTKU
                logging.info(f"🕐 Przetwarzanie emaila z daty: {email_date} (najnowsze pierwsze)")
                
                try:
                    raw_subject = email_msg.get("Subject", "Brak tematu")
                    subject = self.decode_email_subject(raw_subject)
                    logging.debug(f"✅ Dekodowano temat w process_emails: {subject}")
                except Exception as e:
                    logging.warning(f"⚠️ Błąd podczas dekodowania tematu: {e}")
                    subject = str(email_msg.get("Subject", "Brak tematu"))
                
                # Pobieranie treści
                body = self.get_email_body(email_msg)
                
                # Wyciągnij adres email z nagłówka To
                to_header = email_msg.get("To", "")
                email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', to_header)
                recipient = email_match.group(0) if email_match else None
                recipient_name = self.extract_recipient_name(to_header)

                # Jeśli nie znaleziono adresu email w To, spróbuj go wyciągnąć z treści
                if not recipient:
                    # Szukaj wzorców typu "Witaj, solisqaz user,"
                    name_match = re.search(r"Witaj,\s*([\w\s]+)\s*user", body)
                    if name_match:
                        user_name = name_match.group(1).strip().lower()
                        logging.info(f"Znaleziono nazwę użytkownika w treści: {user_name}")
                        recipient = f"{user_name}@gmail.com"
                    else:
                        # Ostatecznie użyj domyślnego konta
                        if email_source == "gmail":
                            recipient = config.GMAIL_EMAIL
                        else:
                            recipient = config.INTERIA_EMAIL
                        logging.info(f"Użyto domyślnego adresu: {recipient}")

                # Pozyskanie ustandaryzowanej nazwy użytkownika (bez hardcodowania)
                user_key = None
                if recipient:
                    # Użyj części przed @ jako klucza użytkownika
                    user_key = recipient.split('@')[0]
                    logging.info(f"Użyto klucza użytkownika: {user_key}")

                if not email_date:
                    logging.warning("Brak daty w nagłówku emaila - pomijam")
                    continue  
                    
                # ✅ LOGUJ DANE PRZED ANALIZĄ
                logging.info(f"📧 Analiza NAJNOWSZEGO: {email_date} | {user_key} | {subject[:30]}...")
                
                # DODAJ DATĘ DO ANALIZY
                processed = self.analyze_email(
                    subject, body, recipient, email_source, 
                    recipient_name, email_message=email_msg, email_date=email_date
                )
                
                if processed:
                    # DODAJ DATĘ EMAILA DO WYNIKÓW
                    processed["email_date"] = email_date
                    processed["user_key"] = user_key
                    processed_data.append(processed)
                    
                    logging.info(f"✅ Przetworzono NAJNOWSZY email z {email_date}: {subject[:50]}")
                    
                    # ✅ OPCJONALNE: PRZERWIJ PO PIERWSZYM PRZETWORZONYM EMAILU DLA UŻYTKOWNIKA
                    # Jeśli chcesz tylko najnowszy email dla każdego użytkownika
                    processed_users = set()
                    if user_key not in processed_users:
                        processed_users.add(user_key)
                    else:
                        logging.info(f"⏭️ Pomijam starszy email dla użytkownika {user_key}")
                        continue
                        
                else:
                    logging.info(f"⏭️ Email z {email_date} pominięty (starszy lub nieobsługiwany)")
                    
            except Exception as e:
                logging.error(f"❌ Błąd podczas przetwarzania e-maila z {email_date}: {e}")
        
        logging.info(f"📊 PODSUMOWANIE: Przetworzono {len(processed_data)} z {len(emails_with_dates)} emaili (najnowsze pierwsze)")
        return processed_data

    def extract_recipient_name(self, header):
        """Wyciąga nazwę odbiorcy z nagłówka To/From"""
        # Wzorzec dla formatu "Imię Nazwisko <email@domain.com>"
        name_pattern = re.search(r'"?([^"<]+)"?\s*<', header)
        if name_pattern:
            return name_pattern.group(1).strip()
        return None


    def analyze_email(self, subject, body, recipient, email_source, recipient_name=None, email_message=None, email_date=None):
        """Analiza treści e-maila z uwzględnieniem daty"""
        
        # Podstawowe dane dla każdego maila
        data = {
            "email": recipient,
            "email_source": email_source,
            "status": None,
            "order_number": None,
            "product_name": None,
            "delivery_address": None,
            "phone_number": None,
            "pickup_location": None,
            "pickup_deadline": None,
            "pickup_code": None,
            "customer_name": recipient_name,
            "user_key": recipient.split('@')[0] if recipient and '@' in recipient else "unknown",
            "available_hours": None,
            "item_link": None,
            "carrier": None,                # Przewoźnik (DPD, InPost, DHL, AliExpress)
            "package_number": None,         # Numer paczki przewoźnika
            "shipping_date": None,          # Data nadania przesyłki
            "delivery_date": None,          # Data doręczenia
            "expected_delivery_date": None, # Planowana data doręczenia
            "qr_code": None,                # Link do kodu QR
            "info": None,   
            "email_date": email_date                       
        }
        
        # Sprawdź wszystkie handlery czy któryś może obsłużyć ten email
        for handler in self.data_handlers:
            if handler.can_handle(subject, body):
                logging.info(f"Wykryto email obsługiwany przez {handler.name}")
                
                if email_date:
                    user_key = recipient.split('@')[0] if recipient and '@' in recipient else None
                    
                    if user_key:
                        existing_email_date = self._get_user_last_email_date(user_key)
                        logging.info(f"Sprawdzanie dat dla użytkownika {user_key}: nowy={email_date}, istniejący={existing_email_date}")
                        
                        # ZAWSZE AKTUALIZUJ JEŚLI EMAIL JEST NOWSZY LUB BRAK DATY
                        if not existing_email_date or self.should_update_based_on_date(email_date, existing_email_date):
                            logging.info(f"✅ Przetwarzam najnowszy email dla {user_key}")
                            self._update_user_last_email_date(user_key, email_date)
                        else:
                            logging.info(f"⏭️ Pomijam starszy email dla {user_key}")
                            return None
                        
                result = handler.parse_delivery_status(subject, recipient, body, handler.name)
                if result:
                    return result
                
                if handler.name == "AliExpress":
                    result = handler.parse_transit_status(subject, recipient, handler.name)
                    if result:
                        return result
                
                if hasattr(handler, 'is_closed_order'):
                    is_closed = handler.is_closed_order(subject)
                    if is_closed:
                        logging.info(f"Email zakwalifikowany jako zamknięte zamówienie przez {handler.name}")
                        data["status"] = "closed"
                        data["carrier"] = handler.name
                        return data

                logging.info(f"EMAIL NIE ZAKWALIFIKOWANY JAKO ZAMKNIĘTE ZAMÓWIENIE PRZEZ {handler.name}")        
                # SPRAWDŹ DATĘ PRZED KONTYNUOWANIEM

                # Kontynuuj z AI i standardowym przetwarzaniem
                openai_data = self.openai_handler.general_extract_carrier_notification_data(
                    body, subject, handler.name, recipient
                )

                # Dodaj sprawdzenie czy AI zwróciło dane
                if openai_data:
                    # Ustaw przewoźnika na podstawie handlera, jeśli AI go nie zwróciło
                    if not openai_data.get("carrier"):
                        openai_data["carrier"] = handler.name
                    return openai_data

                # Jesli AI nie zwróciło danych, użyj domyślnej metody przetwarzania
                processed_data = handler.process(subject, body, recipient, email_source, recipient_name, email_message=email_message)
                if processed_data:
                    if not processed_data.get("carrier"):
                        processed_data["carrier"] = handler.name
                        logging.info(f"Ustawiono carrier na {handler.name} na podstawie nazwy handlera")

                    # Połącz domyślne dane z danymi przetworzonymi przez handler
                    return {**data, **processed_data}
    
        # Żaden handler nie obsłużył tego emaila
        logging.info(f"Mail nie został zakwalifikowany do żadnej kategorii: {subject}")
        return None

    def _get_user_last_email_date(self, user_key):
        """
        Zwraca datę ostatniego emaila dla użytkownika z jego zamówień/paczek
        
        Args:
            user_key: Klucz użytkownika (część przed @ w emailu)
            
        Returns:
            str: Data ostatniego emaila w formacie 'YYYY-MM-DD HH:MM:SS' lub None
        """
        try:
            if not user_key:
                return None
                
            # Sprawdź czy użytkownik istnieje w mapowaniach
            if user_key not in self.user_mappings:
                logging.info(f"Użytkownik {user_key} nie istnieje w mapowaniach - pierwsza aktualizacja")
                return None
            
            user_data = self.user_mappings[user_key]
            last_email_date = None
            
            # Sprawdź czy użytkownik ma zapisaną datę ostatniego emaila
            if "last_email_date" in user_data:
                last_email_date = user_data["last_email_date"]
                logging.info(f"Znaleziono ostatnią datę emaila dla {user_key}: {last_email_date}")
            else:
                logging.info(f"Brak zapisanej daty emaila dla użytkownika {user_key}")
            
            return last_email_date
            
        except Exception as e:
            logging.error(f"Błąd podczas pobierania daty emaila użytkownika {user_key}: {e}")
            return None

    def _update_user_last_email_date(self, user_key, email_date):
        """
        Aktualizuje datę ostatniego emaila dla użytkownika
        
        Args:
            user_key: Klucz użytkownika
            email_date: Data emaila do zapisania
        """
        try:
            if not user_key or not email_date:
                return
                
            # Upewnij się że użytkownik istnieje w mapowaniach
            if user_key not in self.user_mappings:
                self.user_mappings[user_key] = {
                    "order_numbers": [], 
                    "package_numbers": [],
                    "last_email_date": None
                }
            
            # Aktualizuj datę ostatniego emaila
            self.user_mappings[user_key]["last_email_date"] = email_date
            
            logging.info(f"Zaktualizowano datę ostatniego emaila dla {user_key}: {email_date}")
            
            # Zapisz do pliku
            self._save_mappings()
            
        except Exception as e:
            logging.error(f"Błąd podczas zapisywania daty emaila użytkownika {user_key}: {e}")

    def _save_user_order_mapping(self, user_key, order_number):
        """Zapisuje powiązanie użytkownika z numerem zamówienia - ROZSZERZONA WERSJA"""
        if not user_key or not order_number:
            return
            
        if user_key not in self.user_mappings:
            self.user_mappings[user_key] = {
                "order_numbers": [], 
                "package_numbers": [],
                "last_email_date": None  # DODAJ POLE NA DATĘ
            }
        
        if "order_numbers" not in self.user_mappings[user_key]:
            self.user_mappings[user_key]["order_numbers"] = []
        
        # Dodaj last_email_date jeśli nie istnieje
        if "last_email_date" not in self.user_mappings[user_key]:
            self.user_mappings[user_key]["last_email_date"] = None
            
        # Jeśli użytkownik już ma zamówienia, dodaj nowe tylko jeśli jest unikalne
        if order_number not in self.user_mappings[user_key]["order_numbers"]:
            self.user_mappings[user_key]["order_numbers"].append(order_number)
            logging.info(f"Zapisano powiązanie: użytkownik '{user_key}' -> zamówienie {order_number}")
            self._save_mappings()

    def _save_user_package_mapping(self, user_key, package_number):
        """Zapisuje powiązanie użytkownika z numerem paczki - ROZSZERZONA WERSJA"""
        if not user_key or not package_number:
            return
            
        if user_key not in self.user_mappings:
            self.user_mappings[user_key] = {
                "order_numbers": [], 
                "package_numbers": [],
                "last_email_date": None  # DODAJ POLE NA DATĘ
            }
        
        if "package_numbers" not in self.user_mappings[user_key]:
            self.user_mappings[user_key]["package_numbers"] = []
            
        # Dodaj last_email_date jeśli nie istnieje
        if "last_email_date" not in self.user_mappings[user_key]:
            self.user_mappings[user_key]["last_email_date"] = None
            
        if package_number not in self.user_mappings[user_key]["package_numbers"]:
            self.user_mappings[user_key]["package_numbers"].append(package_number)
            logging.info(f"Zapisano powiązanie: użytkownik '{user_key}' -> paczka {package_number}")
            self._save_mappings()
        
    def connect_to_email_account(self, email_config):
            """
            Łączy się z kontem email i zwraca klienta IMAP
            
            Args:
                email_config: Konfiguracja konta email
                
            Returns:
                imaplib.IMAP4_SSL: Klient IMAP lub None w przypadku błędu
            """
            try:
                source = email_config.get('source', 'unknown')
                
                # Pobierz informacje o serwerze z email_sources
                server_info = self.email_sources.get(source, {})
                
                if not server_info:
                    logging.error(f"❌ Nieznane źródło email: {source}")
                    return None
                    
                imap_server = server_info['imap_server']
                port = server_info['port']
                email_addr = email_config['email']
                password = email_config['password']
                
                logging.info(f"🔗 Łączenie z {imap_server}:{port} dla {email_addr}")
                
                # Ustaw timeout dla różnych dostawców
                timeout_settings = {
                    'o2': 60,
                    'interia': 45,
                    'gmail': 30
                }
                timeout = timeout_settings.get(source, 30)
                
                # Połączenie z serwerem z timeout
                client = imaplib.IMAP4_SSL(imap_server, port, timeout=timeout)
                client.login(email_addr, password)
                
                logging.info(f"✅ Połączono z {source}: {email_addr}")
                return client
                
            except imaplib.IMAP4.error as e:
                logging.error(f"❌ Błąd IMAP dla {source}: {e}")
                return None
            except OSError as e:
                logging.error(f"❌ Błąd połączenia z {source}: {e}")
                return None
            except Exception as e:
                logging.error(f"❌ Błąd ogólny dla {source}: {e}")
                return None
    
    def get_unread_emails_in_date_range(self, account_config, days_back=14):
        """
        Pobiera NIEPRZECZYTANE emaile z określonego zakresu dat
        """
        try:
            # ✅ OBLICZ DATĘ GRANICZNĄ
            from datetime import datetime, timedelta
            cutoff_date = datetime.now() - timedelta(days=days_back)
            date_string = cutoff_date.strftime('%d-%b-%Y')  # Format: "15-May-2025"
            
            logging.info(f"📅 Szukanie NIEPRZECZYTANYCH emaili od {date_string} ({days_back} dni wstecz)")
            
            # ✅ KOMBINUJ KRYTERIA: UNSEEN + SINCE (NIEPRZECZYTANE Z OSTATNICH X DNI)
            if account_config['email_source'] == 'o2':
                # Dla O2 - specjalne ograniczenia
                max_emails = EMAIL_CHECK_SETTINGS.get('o2_email_limit', 50)
                search_criteria = f'(UNSEEN SINCE "{date_string}")'
                logging.info(f"🔍 O2: Szukanie NIEPRZECZYTANYCH emaili od {date_string} (limit: {max_emails})")
            else:
                # Dla innych kont
                max_emails = EMAIL_CHECK_SETTINGS.get('max_emails_per_account', 100)
                search_criteria = f'(UNSEEN SINCE "{date_string}")'
                logging.info(f"🔍 {account_config['email_source']}: Szukanie NIEPRZECZYTANYCH emaili od {date_string}")
            
            # ✅ WYSZUKAJ EMAILE (UNSEEN + SINCE = NIEPRZECZYTANE Z ZAKRESU DAT)
            status, message_numbers = self.mail.search(None, search_criteria)
            
            if status != 'OK':
                logging.error(f"❌ Błąd wyszukiwania emaili: {status}")
                return []
            
            message_ids = message_numbers[0].split()
            total_found = len(message_ids)
            
            if total_found == 0:
                logging.info(f"📭 Brak nieprzeczytanych emaili od {date_string}")
                return []
            
            # ✅ OGRANICZ DO NAJNOWSZYCH EMAILI
            if total_found > max_emails:
                message_ids = message_ids[-max_emails:]  # Najnowsze emaile
                logging.info(f"📧 Ograniczenie do {max_emails} najnowszych z {total_found} nieprzeczytanych")
            
            logging.info(f"📧 Znaleziono {len(message_ids)} NIEPRZECZYTANYCH emaili z ostatnich {days_back} dni")
            return message_ids
            
        except Exception as e:
            logging.error(f"❌ Błąd podczas pobierania emaili: {e}")
            return []
        
    def decode_email_subject(self, subject):
        """
        Dekoduje temat emaila z różnych encodingów
        
        Args:
            subject (str): Surowy temat emaila
            
        Returns:
            str: Dekodowany temat
        """
        if not subject or subject == 'Brak tematu':
            return subject or 'Brak tematu'
        
        try:
            decoded = decode_header(subject)
            decoded_parts = []
            
            for part, encoding in decoded:
                if isinstance(part, bytes):
                    if encoding:
                        try:
                            decoded_part = part.decode(encoding)
                            decoded_parts.append(decoded_part)
                        except (UnicodeDecodeError, LookupError):
                            # Fallback encodings
                            for fallback_encoding in ['iso-8859-2', 'iso-8859-1', 'utf-8']:
                                try:
                                    decoded_part = part.decode(fallback_encoding)
                                    decoded_parts.append(decoded_part)
                                    break
                                except UnicodeDecodeError:
                                    continue
                            else:
                                decoded_part = part.decode('utf-8', errors='ignore')
                                decoded_parts.append(decoded_part)
                    else:
                        # Brak encoding - użyj utf-8
                        try:
                            decoded_part = part.decode('utf-8')
                            decoded_parts.append(decoded_part)
                        except UnicodeDecodeError:
                            decoded_part = part.decode('utf-8', errors='ignore')
                            decoded_parts.append(decoded_part)
                else:
                    # Już jest stringiem
                    decoded_parts.append(str(part))
            
            return ''.join(decoded_parts)
            
        except Exception as e:
            logging.warning(f"⚠️ Błąd dekodowania tematu: {e}")
            return subject