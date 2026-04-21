import imaplib
import email
from email.header import decode_header
import re
from datetime import datetime, timedelta
import config
import logging
import json
import os
import time
from openai_handler import OpenAIHandler
import pytz
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

class EmailHandler:
    def __init__(self):
        """Inicjalizacja obsługi email"""
        self.mappings_file = "user_mappings.json"
        self.last_check_time = time.time() - (3600 * 24)  # 24 godziny wstecz
        self.openai_handler = OpenAIHandler()

        # Ulepszony słownik bazujący na końcówkach (domenach) maila
        self.email_sources = {
            'gmail.com': {'imap_server': 'imap.gmail.com', 'port': 993},
            'interia.pl': {'imap_server': 'poczta.interia.pl', 'port': 993},
            'o2.pl': {'imap_server': 'poczta.o2.pl', 'port': 993},
            'wp.pl': {'imap_server': 'imap.wp.pl', 'port': 993}
        }
        
        # Wczytujemy mapowania
        self.user_mappings = self._load_mappings()

        # Inicjalizacja handlerów danych
        from carriers_data_handlers import AliexpressDataHandler, InPostDataHandler, DHLDataHandler, DPDDataHandler, GLSDataHandler, PocztaPolskaDataHandler
        self.data_handlers = [
            PocztaPolskaDataHandler(self),
            GLSDataHandler(self),           
            InPostDataHandler(self),        
            DHLDataHandler(self),           
            AliexpressDataHandler(self),    
            DPDDataHandler(self),           
        ]
        
        self.local_tz = pytz.timezone('Europe/Warsaw')

    def _load_mappings(self):
        """Wczytuje zapisane mapowania z pliku i normalizuje klucze"""
        if os.path.exists(self.mappings_file):
            try:
                with open(self.mappings_file, 'r', encoding='utf-8') as f:
                    raw_data = json.load(f)
                    # Normalizacja przy odczycie (wymuś małe litery)
                    normalized_data = {}
                    for key, value in raw_data.items():
                        normalized_key = key.lower().strip()
                        # Migracja: usuń artefakt "__tombstones__" jeśli kiedykolwiek został zapisany
                        if normalized_key == '__tombstones__':
                            continue
                        normalized_data[normalized_key] = value

                    # jeśli coś usunęliśmy, zapisz z powrotem (żeby nie zostawało w pliku)
                    if '__tombstones__' in raw_data:
                        try:
                            with open(self.mappings_file, 'w', encoding='utf-8') as wf:
                                json.dump(normalized_data, wf, indent=2, ensure_ascii=False)
                            logging.info("🧹 Usunięto '__tombstones__' z user_mappings.json (migracja)")
                        except Exception:
                            pass

                    return normalized_data
            except Exception as e:
                logging.error(f"Błąd podczas ładowania mapowań: {e}")
        return {}
    
    def _save_mappings(self):
        """Zapisuje mapowania użytkowników do pliku JSON z ładnym formatowaniem."""
        try:
            with open(self.mappings_file, 'w', encoding='utf-8') as f:
                json.dump(self.user_mappings, f, indent=2, ensure_ascii=False)
            logging.info(f"Zapisano mapowania do {self.mappings_file}")
        except Exception as e:
            logging.error(f"Błąd podczas zapisywania mapowań: {e}")

    def _save_user_order_mapping(self, user_key, order_number):
        """Zapisuje powiązanie użytkownika z numerem zamówienia."""
        if not user_key or not order_number:
            return

        user_key = user_key.lower()
        order_number = str(order_number).strip()

        if "refund_orders" not in self.user_mappings[user_key]:
         self.user_mappings[user_key]["refund_orders"] = []


        if user_key not in self.user_mappings:
            self.user_mappings[user_key] = {
                "order_numbers": [], 
                "package_numbers": [],
                "last_email_date": None
            }
        
        if "order_numbers" not in self.user_mappings[user_key]:
            self.user_mappings[user_key]["order_numbers"] = []
        
        if "last_email_date" not in self.user_mappings[user_key]:
            self.user_mappings[user_key]["last_email_date"] = None
            
        if order_number not in self.user_mappings[user_key]["order_numbers"]:
            self.user_mappings[user_key]["order_numbers"].append(order_number)
            logging.info(f"Zapisano powiązanie: użytkownik '{user_key}' -> zamówienie {order_number}")
            self._save_mappings()

    def _save_user_package_mapping(self, user_key, package_number):
        """Zapisuje powiązanie użytkownika z numerem paczki."""
        if not user_key or not package_number:
            return

        user_key = user_key.lower()
        package_number = str(package_number).strip()


        if user_key not in self.user_mappings:
            self.user_mappings[user_key] = {
                "order_numbers": [], 
                "package_numbers": [],
                "last_email_date": None
            }
        
        if "package_numbers" not in self.user_mappings[user_key]:
            self.user_mappings[user_key]["package_numbers"] = []
            
        if "last_email_date" not in self.user_mappings[user_key]:
            self.user_mappings[user_key]["last_email_date"] = None
            
        if package_number not in self.user_mappings[user_key]["package_numbers"]:
            self.user_mappings[user_key]["package_numbers"].append(package_number)
            logging.info(f"Zapisano powiązanie: użytkownik '{user_key}' -> paczka {package_number}")
            self._save_mappings()
    
    def _save_refund(self, user_key, order_number=None):
        """Zapisuje informację o zwrocie/banie dla użytkownika."""
        if not user_key:
            return
            
        user_key = user_key.lower()

        # Jeśli użytkownika nie ma w bazie (bo np. dopiero złożył zamówienie), tworzymy go
        if user_key not in self.user_mappings:
            self.user_mappings[user_key] = {
                "order_numbers": [], 
                "package_numbers": [],
                "last_email_date": None
            }

        user_data = self.user_mappings[user_key]

        # 1. Zapisujemy globalną flagę dla usera (łatwe do odpytania z zewnątrz)
        user_data["has_refund"] = True

        if "refund_orders" not in user_data:
            user_data["refund_orders"] = []

        # 2. Jeśli mail zawierał numer zamówienia, dodajemy go do listy
        if order_number and order_number not in user_data["refund_orders"]:
            user_data["refund_orders"].append(order_number)
            
        logging.info(f"💸 Zapisano refund/ban dla: {user_key} (Zamówienie: {order_number or 'Nieznane'})")
        self._save_mappings()

    def remove_user_mapping(self, user_key, package_number=None, order_number=None):
        """
        Usuwa powiązania zamówień/paczek. Jeśli brak numerów - usuwa cały rekord.
        """
        if not user_key:
            return False

        clean_key = str(user_key).lower().strip()
        
        if clean_key not in self.user_mappings:
            return False

        user_data = self.user_mappings[clean_key]
        changed = False
        
        # Sprawdzamy czy podano konkretne dane (paczka/zamówienie)
        has_specific_data = (package_number and str(package_number).strip()) or \
                            (order_number and str(order_number).strip())

        # Tryb PEŁNY (Nuklearny) - używany przy archiwizacji
        if not has_specific_data:
            del self.user_mappings[clean_key]
            self._save_mappings()
            logging.info(f"❌ Użytkownik {clean_key} usunięty z monitoringu JSON.")
            return True

        # Tryb CHIRURGICZNY (usuwanie konkretnej paczki)
        if package_number and "package_numbers" in user_data:
            if package_number in user_data["package_numbers"]:
                user_data["package_numbers"].remove(package_number)
                changed = True

        if order_number and "order_numbers" in user_data:
            order_str = str(order_number)
            if order_str in user_data["order_numbers"]:
                user_data["order_numbers"].remove(order_str)
                changed = True

        # Jeśli po usunięciu paczki user jest pusty - usuń go całkowicie
        if not user_data.get("package_numbers", []) and not user_data.get("order_numbers", []):
            del self.user_mappings[clean_key]
            logging.info(f"❌ Konto {clean_key} puste - usuwam całkowicie.")
            self._save_mappings()
            return True 

        if changed:
            self._save_mappings()
            
        return False

    def fetch_new_emails(self, email_configs_override=None):
        """
        Pobiera wiadomości e-mail z kont skonfigurowanych w config.py.
        Uproszczona logika: CHECK_ONLY_UNSEEN decyduje o filtrze (Nowe vs Wszystkie).
        """
        all_emails = []
        
        # Ustawienia z configu (z bezpiecznymi fallbackami)
        configs = email_configs_override if email_configs_override is not None else config.ALL_EMAIL_CONFIGS
        check_settings = getattr(config, 'EMAIL_CHECK_SETTINGS', {})
        
        days_back = check_settings.get('days_back', 14)
        max_emails = check_settings.get('max_emails_per_account', 100)
        mark_as_read = check_settings.get('mark_as_read', True)
        
        # JEDNA ZMIENNA DECYDUJĄCA (Uproszczenie PROCESS_READ_EMAILS + CHECK_ONLY_UNSEEN)
        # Jeśli CHECK_ONLY_UNSEEN = True -> szukamy tylko (UNSEEN)
        # Jeśli CHECK_ONLY_UNSEEN = False -> szukamy wszystkich (nawet przeczytanych)
        scan_only_new = getattr(config, 'CHECK_ONLY_UNSEEN', True)
        
        # Obliczanie daty granicznej (IMAP wymaga formatu: DD-Mon-YYYY)
        cutoff_date = datetime.now() - timedelta(days=days_back)
        date_string = cutoff_date.strftime('%d-%b-%Y')
        
        if scan_only_new:
            logging.info(f"🕵️ Tryb skanowania: Tylko NOWE (nieprzeczytane) od {date_string}")
        else:
            logging.warning(f"⚠️ Tryb skanowania: WSZYSTKIE (również przeczytane) od {date_string}")

        for email_config in configs:
            source = email_config.get('source', 'unknown')
            email_addr = email_config.get('email')
            
            if not email_addr or not email_config.get('password'):
                logging.warning(f"Pomijanie {source}: brak kompletnych danych logowania")
                continue
            
            logging.info(f"🔍 Łączenie z {source}: {email_addr}")
            client = self.connect_to_email_account(email_config)
            
            if not client:
                continue
            
            emails_to_mark_read = []
                
            try:
                client.select("INBOX")
                
                # Budowanie kryteriów wyszukiwania
                criteria = [f'SINCE "{date_string}"']
                if scan_only_new:
                    criteria.append('UNSEEN')
                
                search_criteria = f"({' '.join(criteria)})" if len(criteria) > 1 else criteria[0]
                
                status, messages = client.search(None, search_criteria)
                
                if status == "OK" and messages[0]:
                    msg_list = messages[0].split()
                    total_found = len(msg_list)
                    
                    # Specyficzny limit dla O2 (częste timeouty przy dużej ilości)
                    actual_limit = 50 if source.lower() == 'o2' else max_emails
                    
                    if total_found > actual_limit:
                        logging.info(f"📧 {source}: Znaleziono {total_found}. Ograniczam do {actual_limit} najnowszych.")
                        msg_list = msg_list[-actual_limit:]
                    else:
                        logging.info(f"📧 {source}: Znaleziono {total_found} wiadomości.")

                    # Sortowanie: najpierw najnowsze (wyższe ID w IMAP)
                    msg_list.sort(key=lambda x: int(x.decode()), reverse=True)
                    
                    for num in msg_list:
                        res, msg_data = client.fetch(num, "(RFC822 INTERNALDATE)")
                        if res != "OK": continue
                        
                        # msg_data zwykle: [(b'...INTERNALDATE "..." RFC822 {..}', b'raw_bytes'), b')']
                        raw_email = msg_data[0][1]
                        meta = msg_data[0][0]
                        email_message = email.message_from_bytes(raw_email)

                        # Zapisz INTERNALDATE jako nagłówek pomocniczy (fallback dla brakującego Date)
                        try:
                            internaldate_match = re.search(rb'INTERNALDATE\s+"([^"]+)"', meta)
                            if internaldate_match:
                                internaldate_str = internaldate_match.group(1).decode('utf-8', errors='replace')
                                email_message['X-IMAP-INTERNALDATE'] = internaldate_str
                        except Exception:
                            pass
                        
                        # Pobieranie daty maila do weryfikacji
                        email_date_str = self.extract_email_date(email_message)
                        subject = self.decode_email_subject(email_message.get('Subject', 'Brak tematu'))

                        if email_date_str:
                            email_dt = datetime.strptime(email_date_str, '%Y-%m-%d %H:%M:%S')
                            if email_dt < cutoff_date:
                                logging.info(f"⏭️ Pomijam (starszy niż zakres): {subject}")
                                # Oznaczamy jako przeczytane, żeby nie wracał w następnej pętli
                                if scan_only_new: emails_to_mark_read.append(num)
                                continue

                        logging.info(f"✅ Pobrano: {subject}")
                        all_emails.append((source, email_message))
                        
                        # Dodaj do listy do oznaczenia jako przeczytane
                        if mark_as_read:
                            emails_to_mark_read.append(num)
                else:
                    logging.info(f"📭 Brak nowych wiadomości w {source}")
                    
            except Exception as e:
                logging.error(f"❌ Błąd podczas pracy z {source} ({email_addr}): {e}")
                    
            finally:
                # Oznaczanie jako przeczytane (Bulk operation)
                if emails_to_mark_read:
                    try:
                        logging.info(f"📖 Oznaczanie {len(emails_to_mark_read)} emaili jako przeczytane w {source}")
                        for num in emails_to_mark_read:
                            client.store(num, '+FLAGS', '\\Seen')
                        client.expunge()
                    except:
                        pass
                
                try:
                    client.logout()
                except:
                    pass
        
        logging.info(f"📊 FINAŁ: Pobrano łącznie {len(all_emails)} wiadomości do analizy AI.")
        return all_emails
    
    def get_email_body(self, email_message):
        """
        Wydobycie treści e-maila. 
        Priorytet: text/plain -> text/html (parsowany na tekst).
        """
        body_text = ""
        body_html = ""
        
        try:
            if email_message.is_multipart():
                for part in email_message.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition"))
                    
                    if content_type.startswith("multipart/"):
                       continue

                    if "attachment" in content_disposition:
                        continue
                        
                    # Pobieramy payload i dekodujemy charset
                    try:
                        payload = part.get_payload(decode=True)

                        if payload is None:
                            continue

                        charset = part.get_content_charset()
                        
                        decoded_part = ""
                        if charset:
                            try:
                                decoded_part = payload.decode(charset, errors="replace")
                            except (LookupError, UnicodeDecodeError):
                                # Fallbacki dla polskich kodowań
                                try: decoded_part = payload.decode("utf-8")
                                except: decoded_part = payload.decode("iso-8859-2", errors="replace")
                        else:
                            # Brak info o kodowaniu - zgadujemy
                            try: decoded_part = payload.decode("utf-8")
                            except: 
                                try: decoded_part = payload.decode("iso-8859-2")
                                except: decoded_part = payload.decode("windows-1250", errors="replace")
                        
                        if content_type == "text/plain":
                            body_text += decoded_part
                        elif content_type == "text/html":
                            body_html += decoded_part
                            
                    except Exception as e:
                        logging.warning(f"Błąd dekodowania części maila: {e}")
            else:
                # Nie jest multipart
                payload = email_message.get_payload(decode=True)
                charset = email_message.get_content_charset()
                
                # ... (analogiczna logika dekodowania jak wyżej) ...
                try:
                    if charset:
                        body_text = payload.decode(charset, errors="replace")
                    else:
                        body_text = payload.decode("utf-8", errors="replace")
                except:
                    body_text = str(payload)

            # Finał: zwracamy tekst lub przetworzony HTML
            if body_text.strip():
                return body_text
            elif body_html.strip():
                return self._html_to_text(body_html)
            else:
                return ""
                
        except Exception as e:
            logging.error(f"Krytyczny błąd pobierania treści maila: {e}")
            return ""
    
    def extract_email_date(self, email_message):
        """Wyciąga datę z nagłówka emaila.

        Zwraca czas w strefie Europe/Warsaw jako string 'YYYY-MM-DD HH:MM:SS'.

        Dlaczego to bywa ważne:
        - część maili ma nagłówek Date bez strefy czasowej (naive datetime)
        - część ma nietypowy format, który `parsedate_to_datetime` może odrzucić

        W takich przypadkach stosujemy bezpieczne fallbacki.
        """
        try:
            date_header = email_message.get('Date')
            if not date_header:
                # Fallback: część serwerów/wiadomości potrafi mieć pusty/missing Date.
                # Próbujemy kilku alternatywnych nagłówków oraz Received.

                debug_email_dates = getattr(config, 'DEBUG_EMAIL_DATES', False)

                # 0) Diagnostyka: jakie nagłówki w ogóle są dostępne
                if debug_email_dates:
                    try:
                        header_names = [k for (k, _) in email_message.items()]
                        logging.info(f"🧾 EMAIL_DATE_DEBUG | Missing Date header. Available headers: {header_names}")
                    except Exception:
                        pass

                # 1) Alternatywne nagłówki daty spotykane u providerów
                #    X-IMAP-INTERNALDATE jest ustawiany przez nas przy fetchu z IMAP (najbardziej wiarygodne fallback źródło)
                alt_date_headers = ['X-IMAP-INTERNALDATE', 'Delivery-date', 'Resent-Date', 'X-Original-Date', 'X-Received', 'Received-Date']
                for hname in alt_date_headers:
                    try:
                        val = email_message.get(hname)
                        if val:
                            dt = parsedate_to_datetime(val)
                            if dt:
                                dt_local = self.local_tz.localize(dt) if dt.tzinfo is None else dt.astimezone(self.local_tz)
                                logging.warning(f"⚠️ Brak Date. Używam fallbacku z {hname}: '{val}' -> {dt_local}")
                                return dt_local.strftime('%Y-%m-%d %H:%M:%S')
                    except Exception:
                        continue

                # 2) Received: w praktyce najczęściej zawiera datę po ostatnim średniku
                received_headers = []
                try:
                    received_headers = email_message.get_all('Received') or []
                except Exception:
                    received_headers = []

                import re
                for received in reversed(received_headers):
                    try:
                        # Złap to, co jest po ostatnim ';' (obsługuje też folded headers)
                        m = re.search(r';\s*(.+?)\s*$', str(received).replace('\r', '').replace('\n', ' '))
                        if not m:
                            continue
                        candidate = m.group(1).strip()
                        dt = parsedate_to_datetime(candidate)
                        if dt:
                            dt_local = self.local_tz.localize(dt) if dt.tzinfo is None else dt.astimezone(self.local_tz)
                            logging.warning(
                                f"⚠️ Brak Date. Używam fallbacku z Received: '{candidate}' -> {dt_local}"
                            )
                            return dt_local.strftime('%Y-%m-%d %H:%M:%S')
                    except Exception:
                        continue

                logging.warning("Brak nagłówka Date w emailu (i nie udało się wyciągnąć z alt headers ani Received)")
                return None

            # 1) Główny parser (najlepszy, gdy format jest poprawny)
            dt = parsedate_to_datetime(date_header)
            if not dt:
                raise ValueError("parsedate_to_datetime zwróciło None")

            # 2) Jeśli brak tzinfo (naive datetime), przyjmij lokalną strefę (Warsaw)
            #    zamiast wywalać wyjątek na astimezone().
            if dt.tzinfo is None:
                try:
                    dt_local = self.local_tz.localize(dt)
                except Exception:
                    # super-awaryjnie: przypnij tz bez lokalize (gorsze dla DST, ale lepsze niż None)
                    dt_local = dt.replace(tzinfo=self.local_tz)
            else:
                dt_local = dt.astimezone(self.local_tz)

            return dt_local.strftime('%Y-%m-%d %H:%M:%S')

        except Exception as e:
            # 3) Fallback: starsza metoda z parsedate_tz + mktime_tz
            #    Często działa, gdy parser "nowy" nie daje rady.
            try:
                import email.utils
                date_header = email_message.get('Date')
                date_tuple = email.utils.parsedate_tz(date_header) if date_header else None
                if date_tuple:
                    ts = email.utils.mktime_tz(date_tuple)
                    dt_local = datetime.fromtimestamp(ts, tz=self.local_tz)
                    logging.warning(
                        f"⚠️ Fallback daty (parsedate_tz) dla nagłówka Date='{date_header}' -> {dt_local}"
                    )
                    return dt_local.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass

            logging.error(f"Błąd podczas wyciągania daty z emaila. Date='{email_message.get('Date')}'. Error={e}")
            return None
    
    def should_update_based_on_date(self, new_email_date, existing_email_date):
        """Sprawdza czy należy zaktualizować dane na podstawie porównania dat"""
        try:
            if not new_email_date:
                logging.warning("Brak daty nowego emaila - pomijam aktualizację")
                return False
                
            if not existing_email_date:
                logging.info("Brak daty w arkuszu - aktualizuję")
                return True
            
            # Zabezpieczenie przed błędem formatu daty
            try:
                new_dt = datetime.strptime(new_email_date, '%Y-%m-%d %H:%M:%S')
                existing_dt = datetime.strptime(existing_email_date, '%Y-%m-%d %H:%M:%S')
                should_update = new_dt > existing_dt # TO CHANGE SIGN
            except ValueError:
                logging.warning(f"Błąd formatu daty przy porównaniu: {new_email_date} vs {existing_email_date}. Aktualizuję dla bezpieczeństwa.")
                return True
            
            if should_update:
                logging.info(f"Nowy email ({new_email_date}) jest nowszy niż istniejący ({existing_email_date}) - aktualizuję")
            else:
                logging.info(f"Nowy email ({new_email_date}) jest starszy niż istniejący ({existing_email_date}) - pomijam")
                
            return should_update
            
        except Exception as e:
            logging.error(f"Błąd podczas porównywania dat: {e}")
            return True

    def process_emails(self, sheets_handler=None):
        """Przetwarzanie nowych e-maili"""
        all_configs = config.ALL_EMAIL_CONFIGS
        configs_to_check = []

        mode = getattr(config, 'EMAIL_TRACKING_MODE', 'CONFIG')
        
        # Pobieramy ustawienie kierunku (Domyślnie True = Najnowsze)
        newest_first = getattr(config, 'PROCESS_FROM_NEWEST', True)

        # --- 1. WYBÓR ŹRÓDŁA KONT ---
        if mode == 'ACCOUNTS' and sheets_handler:
            logging.info("🔄 Tryb pracy: ACCOUNTS (Pobieranie emaili z arkusza Google Sheets)")
            from carriers_sheet_handlers import EmailAvailabilityManager
            email_manager = EmailAvailabilityManager(sheets_handler)
            email_configs = email_manager.get_emails_from_accounts_sheet()
            
            if email_configs:
                configs_to_check = email_configs
                logging.info(f"✅ Wybrano {len(configs_to_check)} kont do sprawdzenia (z Accounts)")
            else:
                logging.warning("⚠️ Arkusz Accounts jest pusty lub niedostępny. Kończę pracę w tym cyklu.")
                return [] 
        else:
            if mode == 'ACCOUNTS' and not sheets_handler:
                 logging.warning("⚠️ Tryb ACCOUNTS wymaga sheets_handler, ale go brak. Używam trybu CONFIG.")
            
            logging.info("🔄 Tryb pracy: CONFIG (Wszystkie maile z pliku)")
            configs_to_check = all_configs

        # --- 2. POBIERANIE I SORTOWANIE ---
        emails = self.fetch_new_emails(email_configs_override=configs_to_check)
        processed_data = []
        
        emails_with_dates = []
        debug_email_dates = getattr(config, 'DEBUG_EMAIL_DATES', False)
        for email_source, email_msg in emails:
            raw_date_header = email_msg.get('Date')
            email_date = self.extract_email_date(email_msg)
            if debug_email_dates:
                logging.info(
                    f"🕒 EMAIL_DATE_DEBUG | source={email_source} | Date='{raw_date_header}' | parsed='{email_date}'"
                )
            emails_with_dates.append((email_source, email_msg, email_date))
        
        # ✅ LOGIKA SORTOWANIA Z CONFIGA
        # reverse=True -> Najnowsze pierwsze (Data malejąco)
        # reverse=False -> Najstarsze pierwsze (Data rosnąco)
        emails_with_dates.sort(key=lambda x: x[2] if x[2] else "1900-01-01 00:00:00", reverse=newest_first)
        
        sort_info = "NAJNOWSZYCH do najstarszych" if newest_first else "NAJSTARSZYCH do najnowszych"
        logging.info(f"📧 Przetwarzanie {len(emails_with_dates)} emaili od {sort_info}")
        
        processed_users = set() 

        for email_source, email_msg, email_date in emails_with_dates:
            try:
                logging.info(f"🕐 Przetwarzanie emaila z daty: {email_date}")
                
                try:
                    raw_subject = email_msg.get("Subject", "Brak tematu")
                    subject = self.decode_email_subject(raw_subject)
                except Exception as e:
                    logging.warning(f"⚠️ Błąd dekodowania: {e}")
                    subject = str(email_msg.get("Subject", "Brak tematu"))
                
                body = self.get_email_body(email_msg)
                to_header = email_msg.get("To", "")
                
                email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', to_header)
                recipient = email_match.group(0).lower() if email_match else None
                recipient_name = self.extract_recipient_name(to_header)

                if not recipient:
                    name_match = re.search(r"Witaj,\s*([\w\s]+)\s*user", body)
                    if name_match:
                        user_name = name_match.group(1).strip().lower()
                        recipient = f"{user_name}@gmail.com"
                    else:
                        if email_source == "gmail": recipient = config.GMAIL_EMAIL.lower()
                        else: recipient = config.INTERIA_EMAIL.lower()

                user_key = recipient.split('@')[0].lower() if recipient else "unknown"
                logging.info(f"Użyto klucza użytkownika: {user_key}")

                # --- 3. LOGIKA POMIJANIA ---
                # Pomijamy TYLKO wtedy, gdy idziemy od Najnowszych (żeby nie nadpisać nowych starymi).
                # Jeśli idziemy od Najstarszych, przetwarzamy wszystko, żeby w arkuszu został stan końcowy (najnowszy).
                if newest_first and user_key in processed_users:
                    logging.info(f"⏭️ Pomijam starszy email dla użytkownika {user_key} (Nowszy już przetworzony)")
                    continue

                if not email_date:
                    logging.warning("Brak daty w nagłówku emaila - pomijam")
                    continue  
                    
                logging.info(f"📧 Analiza: {email_date} | {user_key} | {subject[:30]}...")
                
                processed = self.analyze_email(
                    subject, body, recipient, email_source, 
                    recipient_name, email_message=email_msg, email_date=email_date
                )
                
                if processed:
                    processed["email_date"] = email_date
                    processed["user_key"] = user_key

                    
                    processed_data.append(processed)
                    
                    logging.info(f"✅ Przetworzono email z {email_date}: {subject[:50]}")
                    
                    # Zapamiętujemy usera
                    processed_users.add(user_key)
                        
                else:
                    logging.info(f"⏭️ Email z {email_date} pominięty (starszy lub nieobsługiwany)")
                    
            except Exception as e:
                logging.error(f"❌ Błąd podczas przetwarzania e-maila z {email_date}: {e}")
        
        logging.info(f"📊 PODSUMOWANIE: Przetworzono {len(processed_data)} z {len(emails_with_dates)} emaili")
        return processed_data

    def extract_recipient_name(self, header):
        """Wyciąga nazwę odbiorcy z nagłówka To/From"""
        name_pattern = re.search(r'"?([^"<]+)"?\s*<', header)
        if name_pattern:
            return name_pattern.group(1).strip()
        return None

    def analyze_email(self, subject, body, recipient, email_source, recipient_name=None, email_message=None, email_date=None, force_process=False):
        """Analiza treści e-maila z priorytetem dla AI jeśli włączone"""
        
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
            "user_key": recipient.split('@')[0].lower() if recipient and '@' in recipient else "unknown",
            "available_hours": None,
            "item_link": None,
            "carrier": None,
            "package_number": None,
            "shipping_date": None,
            "delivery_date": None,
            "expected_delivery_date": None,
            "qr_code": None,
            "info": None,   
            "email_date": email_date,
            "refund_detected": None               
        }
        
        use_ai = getattr(config, 'USE_OPENAI_API', False) 
        
        
        for handler in self.data_handlers:
            if handler.can_handle(subject, body):
                logging.info(f"Wykryto email obsługiwany przez {handler.name}")
                
                # --- ZMODYFIKOWANA LOGIKA: Sprawdzenie daty z obsługą IGNORE_LAST_EMAIL_DATE_CHECK ---
                if email_date and not force_process:
                    user_key = recipient.split('@')[0].lower() if recipient and '@' in recipient else None
                    if user_key:
                        existing_email_date = self._get_user_last_email_date(user_key)
                        
                        # Pobierz flagę z konfiguracji
                        ignore_date_check = getattr(config, 'IGNORE_LAST_EMAIL_DATE_CHECK', False)
                        
                        # Sprawdzamy, czy mail jest nowszy
                        is_newer = not existing_email_date or self.should_update_based_on_date(email_date, existing_email_date)
                        
                        if is_newer:
                            logging.info(f"✅ Przetwarzam najnowszy email dla {user_key}")
                            self._update_user_last_email_date(user_key, email_date)
                        elif ignore_date_check:
                            # Tryb FORCE: Przetwarzamy maila, ale logujemy ostrzeżenie
                            logging.warning(f"⚠️ TRYB FORCE: Przetwarzam maila z {email_date} dla {user_key}, mimo że ostatni był {existing_email_date}")
                        else:
                            # Standardowy tryb: Pomijamy stary email
                            logging.info(f"⏭️ Pomijam starszy email dla {user_key}")
                            return None
                elif force_process:
                     user_key = recipient.split('@')[0].lower() if recipient else None
                     if user_key:
                         self._update_user_last_email_date(user_key, email_date)
                # -----------------------------------------------------------------------------------

                normalized_subject = str(subject or "").strip().lower()

                if normalized_subject == "przetworzono zwrot za anulowane zakupy":
                    data["refund_detected"] = True

                    order_number = data.get("order_number")

                   
                    self._save_refund(user_key, order_number)

                    logging.info(f"Status refund_detected: {data['refund_detected']}")
                    return data

                # 1. PRIORYTET: AI
                if use_ai:
                    logging.info(f"🤖 Uruchamiam analizę AI dla {handler.name} (Priorytet AI)...")
                    try:
                        openai_data = self.openai_handler.general_extract_carrier_notification_data(
                            body, subject, handler.name, recipient, email_date=email_date
                        )
                        if openai_data:
                            if not openai_data.get("carrier"):
                                openai_data["carrier"] = handler.name
                            logging.info("🤖 AI zwróciło dane - pomijam Regexy.")
                            return {**data, **openai_data}
                    except Exception as e:
                        logging.error(f"❌ Błąd AI: {e}. Przełączam na tryb awaryjny (Regex).")

                # 2. SZYBKI REGEX (Tylko statusy z tematu)
                result = handler.parse_delivery_status(subject, recipient, body, handler.name)
                if result:
                    logging.info(f"⚡ Szybki Regex znalazł status: {result.get('status')}")
                    return {**data, **result}
                
                if handler.name == "AliExpress":
                    result = handler.parse_transit_status(subject, recipient, handler.name)
                    if result:
                        return {**data, **result}
                
                # 3. ZAAWANSOWANY REGEX (Pełna analiza treści)
                logging.info(f"🔍 Uruchamiam handler.process (Pełny Regex) dla {handler.name}")
                try:
                    processed_data = handler.process(subject, body, recipient, email_source, recipient_name, email_message)
                except TypeError:
                    processed_data = handler.process(subject, body, recipient, email_source, recipient_name)
                
                if processed_data:
                    if not processed_data.get("carrier"):
                        processed_data["carrier"] = handler.name
                    logging.info(f"✅ Dane wyciągnięte Regexpem")
                    return {**data, **processed_data}
    
        logging.info(f"Mail nie został zakwalifikowany do żadnej kategorii: {subject}")
        return None

    # Wklej to wewnątrz klasy EmailHandler w pliku email_handler.py

    def sync_mappings_from_sheets(self, sheets_handler):
        """
        Pobiera dane z arkusza i aktualizuje lokalną bazę mapowań.
        Naprawia błędy formatowania i duplikaty.
        """
        logging.info("📥 Rozpoczynam synchronizację mapowań z arkusza...")
        
        # Sprawdzenie połączenia (korzystamy z przekazanego obiektu)
        if not sheets_handler.connected and not sheets_handler.connect():
            return
        
        try:
            # Zakładamy kolumny: A=Email (0), M=Order (12), O=Package (14)
            all_values = sheets_handler.worksheet.get_all_values()
            updates_count = 0
            
            # Pomiń nagłówek
            for row in all_values[1:]:
                if len(row) >= 15:  
                    email_full = row[0].strip()
                    # Usuń apostrofy, które Excel/Sheets czasem dodają
                    order_number = row[12].replace("'", "").strip()
                    package_number = row[14].replace("'", "").strip()
                    
                    if email_full and (order_number or package_number):
                        # 1. Wyciągnij klucz użytkownika (przed @)
                        if "@" in email_full:
                            user_key = email_full.split('@')[0].lower()
                        else:
                            user_key = email_full.lower()
                        
                        # 2. Inicjalizacja struktury
                        if user_key not in self.user_mappings:
                            self.user_mappings[user_key] = {
                                "order_numbers": [],
                                "package_numbers": [],
                                "last_email_date": None
                            }
                        
                        user_data = self.user_mappings[user_key]
                        
                        # Zabezpieczenie struktury (gdyby istniała, ale była stara/błędna)
                        if "order_numbers" not in user_data: user_data["order_numbers"] = []
                        if "package_numbers" not in user_data: user_data["package_numbers"] = []
                        if "last_email_date" not in user_data: user_data["last_email_date"] = None

                        # 3. Aktualizacja danych (bez duplikatów)
                        if order_number and order_number not in user_data["order_numbers"]:
                            user_data["order_numbers"].append(order_number)
                            updates_count += 1
                        
                        if package_number and package_number not in user_data["package_numbers"]:
                            user_data["package_numbers"].append(package_number)
                            updates_count += 1
            
            if updates_count > 0:
                self._save_mappings()
                logging.info(f"✅ Zaktualizowano mapowania z arkusza ({updates_count} nowych wpisów)")
            else:
                logging.info("Mapowania lokalne są zgodne z arkuszem.")
                
        except Exception as e:
            logging.error(f"❌ Błąd synchronizacji mapowań z arkusza: {e}")
            # Nie crashujemy programu, po prostu nie zaktualizowano danych
            
    def _get_user_last_email_date(self, user_key):
        """Zwraca datę ostatniego emaila dla użytkownika z jego zamówień/paczek"""
        try:
            if not user_key:
                return None
                
            if user_key not in self.user_mappings:
                logging.info(f"Użytkownik {user_key} nie istnieje w mapowaniach - pierwsza aktualizacja")
                return None
            
            user_data = self.user_mappings[user_key]
            last_email_date = None
            
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
        """Aktualizuje datę ostatniego emaila dla użytkownika - BEZ TWORZENIA ZOMBIE"""
        try:
            if not user_key or not email_date:
                return
                
            # ✅ POPRAWKA: Jeśli użytkownika nie ma w bazie, NIE TWÓRZ GO.
            # Użytkownik zostanie utworzony dopiero, gdy znajdziemy konkretny numer zamówienia/paczki.
            if user_key not in self.user_mappings:
                # logging.debug(f"Pominięto aktualizację daty dla nieistniejącego (lub usuniętego) użytkownika: {user_key}")
                return
            
            # Dodatkowe zabezpieczenie: nie aktualizuj pustych kont (bez zamówień i paczek)
            user_data = self.user_mappings[user_key]
            if not user_data.get("order_numbers") and not user_data.get("package_numbers"):
                 # To jest sytuacja "Zombie" - puste konto. Nie reanimuj go samą datą.
                 return

            self.user_mappings[user_key]["last_email_date"] = email_date
            
            logging.info(f"Zaktualizowano datę ostatniego emaila dla {user_key}: {email_date}")
            self._save_mappings()
            
        except Exception as e:
            logging.error(f"Błąd podczas zapisywania daty emaila użytkownika {user_key}: {e}")

    def connect_to_email_account(self, email_config):
        """Łączy się z kontem email na podstawie domeny i zwraca klienta IMAP"""
        try:
            email_addr = email_config.get('email', '')
            password = email_config.get('password', '')
            
            if not email_addr or not password:
                logging.error("❌ Brak adresu email lub hasła w konfiguracji!")
                return None

            # 1. Wyodrębnienie domeny z adresu email (np. wp.pl, interia.pl)
            domena = email_addr.split('@')[-1].lower()
            
            # 2. Szukanie serwera w naszym słowniku
            server_info = self.email_sources.get(domena)
            
            if not server_info:
                logging.error(f"❌ Nieobsługiwana domena email: {domena}. Dodaj ją do self.email_sources!")
                return None
                
            imap_server = server_info['imap_server']
            port = server_info['port']
            
            logging.info(f"🔗 Łączenie z {imap_server}:{port} dla {email_addr}")
            
            # 3. Dynamiczne ustawienie timeoutu w zależności od domeny
            timeout_settings = {'o2.pl': 60, 'interia.pl': 45, 'gmail.com': 30, 'wp.pl': 45}
            timeout = timeout_settings.get(domena, 30)
            
            client = imaplib.IMAP4_SSL(imap_server, port, timeout=timeout)
            client.login(email_addr.lower(), password)
            
            logging.info(f"✅ Połączono z serwerem dla: {email_addr}")
            return client
            
        except imaplib.IMAP4.error as e:
            logging.error(f"❌ Błąd IMAP dla {email_addr}: {e}")
            return None
        except OSError as e:
            logging.error(f"❌ Błąd połączenia dla {email_addr}: {e}")
            return None
        except Exception as e:
            logging.error(f"❌ Błąd ogólny podczas logowania do {email_addr}: {e}")
            return None
        
    def decode_email_subject(self, subject):
        """Dekoduje temat emaila z różnych encodingów"""
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
                        try:
                            decoded_part = part.decode('utf-8')
                            decoded_parts.append(decoded_part)
                        except UnicodeDecodeError:
                            decoded_part = part.decode('utf-8', errors='ignore')
                            decoded_parts.append(decoded_part)
                else:
                    decoded_parts.append(str(part))
            
            return ''.join(decoded_parts)
            
        except Exception as e:
            logging.warning(f"⚠️ Błąd dekodowania tematu: {e}")
            return subject
        
    def fetch_specific_account_history(self, target_email, days_back=30):
        """
        Pobiera historię maili dla konkretnego konta.
        Jeśli nie znajdzie configu, używa danych domyślnych (FALLBACK).
        """
        target_email = target_email.strip().lower()
        all_emails = []
        
        found_config = None
        if hasattr(config, 'ALL_EMAIL_CONFIGS'):
            for cfg in config.ALL_EMAIL_CONFIGS:
                if cfg['email'].strip().lower() == target_email:
                    found_config = cfg
                    break
        
        # --- SEKCJA FALLBACK ---
        if not found_config:
            logging.warning(f"⚠️ Nie znaleziono jawnej konfiguracji dla {target_email} w config.py")
            
            if hasattr(config, 'DEFAULT_EMAIL_PASSWORD') and config.DEFAULT_EMAIL_PASSWORD:
                logging.info(f"🔧 Uruchamiam FALLBACK: Używam domyślnego hasła i serwera Interia.")
                found_config = {
                    'email': target_email,
                    'password': config.DEFAULT_EMAIL_PASSWORD,
                    'server': 'poczta.interia.pl',
                    'source': 'interia'
                }
            else:
                logging.error(f"❌ Brak konfiguracji ORAZ brak 'DEFAULT_EMAIL_PASSWORD' w config.py dla {target_email}")
                return []

        cutoff_date = datetime.now() - timedelta(days=days_back)
        date_string = cutoff_date.strftime('%d-%b-%Y')
        
        source = found_config.get('source', 'unknown')
        logging.info(f"🔄 REPROCESS: Łączenie z {target_email} ({source})...")
        
        client = self.connect_to_email_account(found_config)
        if not client:
            return []

        try:
            client.select("INBOX")
            
            search_criteria = f'(SINCE "{date_string}")'
            logging.info(f"📅 Kryteria reprocess: {search_criteria}")
            
            status, messages = client.search(None, search_criteria)
            
            if status == "OK" and messages[0]:
                msg_ids = messages[0].split()
                logging.info(f"📧 Znaleziono łącznie {len(msg_ids)} wiadomości.")
                
                # Sortowanie od najstarszych
                msg_ids.sort(key=lambda x: int(x.decode()), reverse=False)
                
                for num in msg_ids:
                    res, msg_data = client.fetch(num, "(RFC822 INTERNALDATE)")
                    if res == "OK":
                        raw_email = msg_data[0][1]
                        meta = msg_data[0][0]
                        try:
                            msg = email.message_from_bytes(raw_email)
                            # Zapisz INTERNALDATE jako nagłówek pomocniczy (fallback dla brakującego Date)
                            try:
                                internaldate_match = re.search(rb'INTERNALDATE\s+"([^"]+)"', meta)
                                if internaldate_match:
                                    internaldate_str = internaldate_match.group(1).decode('utf-8', errors='replace')
                                    msg['X-IMAP-INTERNALDATE'] = internaldate_str
                            except Exception:
                                pass
                        except:
                            try:
                                msg = email.message_from_string(raw_email.decode('utf-8', errors='ignore'))
                            except:
                                continue
                        
                        all_emails.append((source, msg))
            else:
                logging.warning("📭 Nie znaleziono wiadomości w tym okresie.")

        except Exception as e:
            logging.error(f"❌ Błąd podczas pobierania historii: {e}")
        finally:
            try:
                client.close()
                client.logout()
            except:
                pass
                
        return all_emails
    
    def _html_to_text(self, html):
        """Konwertuje HTML na czysty tekst (Metoda pomocnicza)"""
        if not html:
            return ""
            
        class HTMLToText(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text = []
                self.skip = False
                
            def handle_starttag(self, tag, attrs):
                if tag in ['script', 'style', 'head']:
                    self.skip = True
                elif tag == 'br':
                    self.text.append('\n')
                elif tag in ['p', 'div', 'tr']:
                    self.text.append('\n')
                    
            def handle_endtag(self, tag):
                if tag in ['script', 'style', 'head']:
                    self.skip = False
                elif tag in ['p', 'div', 'tr', 'td']:
                    self.text.append('\n')
                    
            def handle_data(self, data):
                if not self.skip:
                    text = data.strip()
                    if text:
                        self.text.append(text)
        
        parser = HTMLToText()
        try:
            parser.feed(html)
            text = ' '.join(parser.text)
            # Usuń wielokrotne spacje i puste linie
            text = re.sub(r' +', ' ', text)
            text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
            return text.strip()
        except:
            # Fallback - usuń tagi HTML regexem (jeśli parser zawiedzie)
            text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', '', html)
            text = re.sub(r'\s+', ' ', text)
            return text.strip()