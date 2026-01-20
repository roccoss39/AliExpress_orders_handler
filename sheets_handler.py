import gspread
from oauth2client.service_account import ServiceAccountCredentials
import config
import logging
import re
import time
from datetime import datetime, timedelta  # ✅ DODANO IMPORT
from carriers_sheet_handlers import InPostCarrier, DHLCarrier, AliExpressCarrier, DPDCarrier, GLSCarrier, PocztaPolskaCarrier

class SheetsHandler:
    _instance = None
    _spreadsheet = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SheetsHandler, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, credentials_file=None):
        if self._initialized:
            return
            
        # Inicjalizacja tylko raz
        self._credentials_file = credentials_file
        self._client = None
        self._initialized = True
        
        logging.debug("Wejście do funkcji: __init__()")
        self.spreadsheet = None
        self.worksheet = None
        self.connected = False
        self.carriers = {}  # Słownik przewoźników
        self.last_mapping_refresh = 0
    
    def connect(self):
        """Łączy z arkuszem Google Sheets"""
        if SheetsHandler._spreadsheet is not None:
            # Użyj istniejącego połączenia
            logging.debug("Używam zapisanego połączenia z arkuszem")
            return SheetsHandler._spreadsheet
            
        logging.debug("Wejście do funkcji: connect()")
        try:
            # Definiujemy zakres uprawnień
            scope = ['https://spreadsheets.google.com/feeds',
                     'https://www.googleapis.com/auth/drive']
            
            # Ładujemy poświadczenia z pliku
            credentials = ServiceAccountCredentials.from_json_keyfile_name('service_account.json', scope)
            
            # Autoryzujemy klienta
            client = gspread.authorize(credentials)
            
            # Otwieramy arkusz
            self.spreadsheet = client.open_by_key(config.SPREADSHEET_ID)
            
            # Pobieramy odpowiednią zakładkę
            self.worksheet = self.spreadsheet.worksheet(config.SHEET_NAME)
            
            # Inicjalizacja przewoźników
            self.carriers["InPost"] = InPostCarrier(self)
            self.carriers["DHL"] = DHLCarrier(self)
            self.carriers["AliExpress"] = AliExpressCarrier(self)
            self.carriers["DPD"] = DPDCarrier(self)
            self.carriers["GLS"] = GLSCarrier(self)
            self.carriers["PocztaPolska"] = PocztaPolskaCarrier(self)
            
            self.connected = True
            
            # Zapisz połączenie w cache
            SheetsHandler._spreadsheet = self.spreadsheet
            
            return True
        except Exception as e:
            print(f"Błąd połączenia z Google Sheets: {e}")
            self.connected = False
            return False

    def check_and_archive_delivered_orders(self):
        """
        STARTUP: Archiwizuje, usuwa luki, usuwa konta I MAPOWANIA.
        """
        logging.info("🧹 STARTUP: Pełne czyszczenie zakończonych zamówień...")
        if not self.connected and not self.connect():
            return

        try:
            all_values = self.worksheet.get_all_values()
            rows_to_archive = []

            for i, row in enumerate(all_values):
                if i == 0: continue
                if len(row) > 8:
                    status = str(row[8]).lower()
                    keywords = ['dostarczona', 'odebrana', 'zwrócona', 'delivered', 'picked up']
                    
                    if any(key in status for key in keywords):
                        email = row[0]
                        rows_to_archive.append((i + 1, email))

            if rows_to_archive:
                logging.info(f"Znaleziono {len(rows_to_archive)} zamówień do archiwizacji.")
                
                for row_num, email in reversed(rows_to_archive):
                    logging.info(f"📦 Przetwarzanie wiersza {row_num} (Email: {email})")
                    
                    # 1. Archiwizacja
                    success = self.move_row_to_delivered(row_num)
                    
                    if success:
                        if email:
                            # 2. Usuń konto
                            self.remove_account_from_list(email)
                            # 3. Usuń mapowanie (NOWOŚĆ)
                            self.remove_user_mapping(email)

                        # 4. Usuń wiersz z Ali_orders
                        try:
                            self.worksheet.delete_rows(row_num)
                            logging.info(f"🗑️ Usunięto wiersz {row_num}.")
                            time.sleep(1.5)
                        except Exception as del_err:
                            logging.error(f"❌ Błąd usuwania wiersza: {del_err}")
            else:
                logging.info("Brak starych zamówień do archiwizacji.")

        except Exception as e:
            logging.error(f"Błąd podczas startowego czyszczenia: {e}")
    
    def format_phone_number(self, phone):
        """Formatuje numer telefonu: usuwa +48 i dodaje spacje co 3 cyfry"""
        logging.debug(f"Wejście do funkcji: format_phone_number(phone={phone})")
        if not phone:
            return ""
            
        digits_only = re.sub(r'\D', '', phone)
        
        if len(digits_only) > 9:
            digits_only = digits_only[-9:]
        
        if len(digits_only) == 9:
            formatted = f"{digits_only[0:3]}-{digits_only[3:6]}-{digits_only[6:9]}"
        else:
            chunks = [digits_only[i:i+3] for i in range(0, len(digits_only), 3)]
            formatted = "-".join(chunks)
        
        return formatted
    
    def find_order_row(self, order_number):
        """Znajduje wiersz z podanym numerem zamówienia"""
        logging.debug(f"Wejście do funkcji: find_order_row(order_number={order_number})")
        if not order_number:
            logging.warning("Próba znalezienia wiersza bez podanego numeru zamówienia")
            return None
            
        if not self.connected and not self.connect():
            return None
        
        try:
            # Szukaj w kolumnie M (indeks 13, ale w find używamy 1-based index jeśli gspread < 6.0,
            # w nowych wersjach find szuka w całym zakresie. 
            # Domyślnie w kodzie 'create_row' numer zamówienia jest w kolumnie M (13) lub wcześniej w H (8).
            # Spróbujmy znaleźć gdziekolwiek.
            
            cells = self.worksheet.findall(order_number)
            if cells:
                logging.info(f"Znaleziono {len(cells)} wystąpień zamówienia {order_number} w arkuszu")
                return cells[0].row
                
            logging.info(f"Nie znaleziono zamówienia {order_number} w arkuszu")
            return None
        except Exception as e:
            logging.error(f"Błąd przy szukaniu zamówienia: {e}")
            return None
    
    def find_package_row(self, package_number):
        """Znajduje wiersz z podanym numerem paczki"""
        logging.debug(f"Wejście do funkcji: find_package_row(package_number={package_number})")
        if not package_number:
            logging.warning("Próba znalezienia wiersza bez podanego numeru paczki")
            return None
        
        if not self.connected and not self.connect():
            return None
        
        try:
            cells = self.worksheet.findall(package_number)
            if cells and len(cells) > 0:
                return cells[0].row
                
            return None
        except Exception as e:
            logging.error(f"Błąd przy szukaniu paczki: {e}")
            return None
    
    def update_confirmed_order(self, order_data):
        """Aktualizuje arkusz po potwierdzeniu zamówienia"""
        logging.debug(f"Wejście do funkcji: update_confirmed_order(order_data={order_data})")
        if not self.connected and not self.connect():
            return False
        
        try:
            logging.info(f"Aktualizacja zamówienia dla: {order_data.get('customer_name', order_data.get('email'))}")
            order_number = order_data.get("order_number")
            
            if not order_number:
                logging.error("Brak numeru zamówienia w danych")
                return False
                
            row = self.find_order_row(order_number)
            
            if row:
                logging.info(f"Znaleziono zamówienie {order_number} w wierszu {row} - aktualizuję")
                if order_data.get("product_name"):
                    self.worksheet.update_cell(row, 2, order_data["product_name"])
                
                if order_data.get("delivery_address"):
                    self.worksheet.update_cell(row, 3, order_data["delivery_address"])
                    
                if order_data.get("phone_number"):
                    self.worksheet.update_cell(row, 4, order_data["phone_number"])
                
                if order_data.get("item_link"):
                    normal_link = order_data.get("item_link")
                    # ✅ ZMIANA: Link w kolumnie P (16), nie K (11)
                    self.worksheet.update_cell(row, 16, normal_link)
                    
                return True
            
            logging.info(f"Nie znaleziono zamówienia {order_number} w arkuszu - tworzę nowy wiersz")
            
            # ✅ ZMIANA: Obsługa daty zamówienia
            email_date_str = order_data.get("email_date", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            est_delivery = ""
            try:
                # Prosta próba obliczenia +10 dni
                dt_obj = datetime.strptime(email_date_str[:10], '%Y-%m-%d')
                est_delivery = (dt_obj + timedelta(days=10)).strftime('%Y-%m-%d')
            except: pass

            # ✅ ZMIANA: Struktura 16 kolumn
            row_data = [
                order_data.get("customer_name", order_data.get("email", "")), # A
                order_data.get("product_name", ""),                           # B
                order_data.get("delivery_address", ""),                       # C
                order_data.get("phone_number", ""),                           # D
                "",                                                           # E
                order_data.get("delivery_date", ""),                          # F
                "",                                                           # G
                email_date_str,                                               # H
                "Zamówienie potwierdzone",                                    # I
                email_date_str,                                               # J (Data zam)
                est_delivery,                                                 # K (Est)
                "",                                                           # L
                order_data.get("order_number", ""),                           # M
                "",                                                           # N
                "",                                                           # O
                order_data.get("item_link", "")                               # P (Link)
            ]
            
            self.worksheet.append_row(row_data)
            
            logging.info(f"Utworzono nowy wiersz dla zamówienia {order_number}")
            return True
        except Exception as e:
            logging.error(f"Błąd podczas aktualizacji potwierdzonego zamówienia: {e}")
            return False
    
    def update_delivered_order(self, order_data):
        """Aktualizuje status, archiwizuje, USUWA KONTO i USUWA MAPOWANIE"""
        logging.debug(f"Wejście do funkcji: update_delivered_order")
        if not self.connected and not self.connect(): return False
        
        try:
            package_number = order_data.get("package_number", "")
            user_key = order_data.get("user_key")
            order_number = order_data.get("order_number", "")
            
            row = None
            if package_number:
                row = self.find_package_row(package_number)
            if not row and order_number:
                try:
                    cells = self.worksheet.findall(order_number)
                    if cells: row = cells[0].row
                except: pass
            if not row and user_key:
                user_rows = self.find_user_rows(user_key)
                if user_rows: row = user_rows[-1]
            
            carrier_name = order_data.get("carrier", "InPost")
            if carrier_name not in self.carriers: carrier_name = "InPost"
            carrier = self.carriers[carrier_name]
            
            if row:
                # 1. Aktualizuj status
                success = carrier.update_delivered(row, order_data)
                
                if success:
                    logging.info(f"✅ Status zaktualizowany. Rozpoczynam pełne czyszczenie...")
                    
                    # Pobierz email zanim usuniemy wiersz
                    try:
                        email_in_sheet = self.worksheet.cell(row, 1).value
                    except:
                        email_in_sheet = order_data.get('email')

                    # 2. Przenieś do archiwum Delivered
                    move_success = self.move_row_to_delivered(row, order_data)
                    
                    if move_success:
                        # 3. Usuń konto z Accounts
                        self.remove_account_from_list(email_in_sheet)
                        
                        # 4. Usuń mapowanie z Użytkownicy (NOWOŚĆ)
                        self.remove_user_mapping(email_in_sheet)

                        # 5. Usuń wiersz z głównego arkusza (usuń lukę)
                        self.worksheet.delete_rows(row)
                        logging.info(f"🗑️ Usunięto wiersz {row} i wyczyszczono wszystkie dane.")
                    
                return success
            else:
                logging.warning(f"Nie znaleziono wiersza dla paczki {package_number}")
                return False
                
        except Exception as e:
            logging.error(f"Błąd podczas aktualizacji dostarczonej paczki: {e}")
            return False
    
    def update_canceled_order(self, order_data):
        """Aktualizuje arkusz po anulowaniu zamówienia"""
        logging.debug(f"Wejście do funkcji: update_canceled_order(order_data={order_data})")
        if not self.connected and not self.connect():
            return False
        
        try:
            if not order_data.get("order_number"):
                logging.warning("Brak numeru zamówienia w anulowanym zamówieniu. Pomijam.")
                return False
                
            row = self.find_order_row(order_data["order_number"])
            
            if row:
                self.worksheet.format(f"A{row}:P{row}", { # Zakres do P
                    "backgroundColor": config.COLORS["canceled"]
                })
                
                email = self.worksheet.cell(row, 1).value
                if email:
                    self.worksheet.update_cell(row, 9, email)
                    self.worksheet.format(f"I{row}", {
                        "backgroundColor": config.COLORS["available_email"]
                    })
                
                return True
            else:
                logging.warning(f"Nie znaleziono zamówienia o numerze {order_data['order_number']}")
                return False
        except Exception as e:
            logging.error(f"Błąd podczas aktualizacji anulowanego zamówienia: {e}")
            return False

    def process_pickup_notification(self, order_data):
        """Usuwa zamówienie z arkusza po powiadomieniu o odebranej paczce"""
        logging.debug(f"Wejście do funkcji: process_pickup_notification(order_data={order_data})")
        if not self.connected and not self.connect():
            return False
            
        try:
            logging.info(f"Usuwanie zamówienia po odbiorze dla: {order_data.get('email')}")
            user_rows = self.find_user_rows(order_data["user_key"])
            
            if user_rows and len(user_rows) > 0:
                row_to_delete = user_rows[-1]
                self.worksheet.delete_rows(row_to_delete)
                logging.info(f"Usunięto zamówienie z wiersza {row_to_delete} dla {order_data['user_key']}")
                return True
            else:
                logging.warning(f"Nie znaleziono zamówienia do usunięcia dla użytkownika {order_data['user_key']}")
                return False
                
        except Exception as e:
            logging.error(f"Błąd podczas usuwania zamówienia po odbiorze: {e}")
            return False

    def find_user_rows(self, user_key):
        """Znajduje numery wierszy dla danego użytkownika"""
        if not self.connected and not self.connect():
            return []
            
        found_rows = []
        try:
            user_key = user_key.lower().strip()
            emails_col = self.worksheet.col_values(1)
            
            for i, email_val in enumerate(emails_col):
                if not email_val: continue
                
                clean_email = str(email_val).lower().strip()
                clean_key_from_email = clean_email.split('@')[0]
                
                if user_key == clean_email or user_key == clean_key_from_email:
                    found_rows.append(i + 1)
                    
            return found_rows
        except Exception as e:
            logging.error(f"Błąd szukania wierszy użytkownika: {e}")
            return []

    def create_new_order_from_pickup(self, order_data):
        """Tworzy nowy wiersz zamówienia na podstawie danych o odbiorze paczki"""
        logging.debug(f"Wejście do funkcji: create_new_order_from_pickup(order_data={order_data})")
        if not self.connected and not self.connect():
            return False
        
        try:
            user_key = order_data.get("user_key") or order_data.get("customer_name", "").split('@')[0]
            logging.info(f"Tworzenie nowego wiersza dla użytkownika {user_key}")
            
            email = order_data.get("customer_name") or ""
            if "@" not in email and user_key:
                email = f"{user_key}@gmail.com"
                
            available_hours = order_data.get("available_hours")
            if not available_hours:
                available_hours = "PN-ND 24/7"
            
            qr_data = ""
            if order_data.get("qr_code"):
                if order_data.get("qr_code_in_attachment") and order_data.get("pickup_code"):
                    qr_data = f'=IMAGE("https://chart.googleapis.com/chart?chs=150x150&cht=qr&chl={order_data["pickup_code"]}")'
                else:
                    qr_data = order_data["qr_code"]

            # ✅ ZMIANA: 16 kolumn, daty
            email_date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            row_data = [
                email,                                          # A
                "Nieznany",                                     # B
                order_data.get("pickup_location", ""),          # C
                order_data.get("phone_number", ""),             # D
                order_data.get("pickup_code", ""),              # E
                order_data.get("pickup_deadline", ""),          # F
                available_hours,                                # G
                email_date_str,                                 # H
                "Gotowe do odbioru",                            # I
                email_date_str,                                 # J (Data)
                "",                                             # K (Est)
                qr_data,                                        # L
                "",                                             # M
                "",                                             # N
                "",                                             # O
                ""                                              # P
            ]
            
            self.worksheet.append_row(row_data)
            next_row = len(self.worksheet.get_all_values())
            
            try:
                self.worksheet.format(f"A{next_row}:P{next_row}", {
                    "backgroundColor": {"red": 1.0, "green": 0.95, "blue": 0.8}
                })
            except Exception as format_error:
                logging.error(f"Błąd podczas formatowania: {format_error}")
            
            logging.info(f"Utworzono nowy wiersz zamówienia w wierszu {next_row}")
            return True
        except Exception as e:
            logging.error(f"Błąd podczas tworzenia nowego wiersza zamówienia: {e}")
            return False

    def _direct_create_row(self, order_data):
        """
        Tworzy nowy wiersz bezpośrednio w arkuszu (Fallback).
        Zaktualizowana wersja obsługująca 16 kolumn (A-P) i daty.
        """
        try:
            # Pobierz dane podstawowe
            email = order_data.get("email") or f"{order_data.get('user_key', 'unknown')}@gmail.com"
            order_num = order_data.get("order_number", "")
            pkg_num = order_data.get("package_number", "")
            status = order_data.get("status", "unknown")
            
            # --- DATY ---
            # 1. Data zamówienia (z maila lub dzisiaj)
            email_date_str = order_data.get("email_date", "")
            if not email_date_str:
                email_date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 2. Przewidywana dostawa (+10 dni)
            est_delivery = ""
            try:
                # Próbuj parsować datę (różne formaty)
                dt_obj = None
                if len(email_date_str) > 10:
                    dt_obj = datetime.strptime(email_date_str, '%Y-%m-%d %H:%M:%S')
                else:
                    dt_obj = datetime.strptime(email_date_str, '%Y-%m-%d')
                
                if dt_obj:
                    est_delivery = (dt_obj + timedelta(days=10)).strftime('%Y-%m-%d')
            except Exception as e:
                logging.warning(f"Nie udało się obliczyć daty dostawy w _direct_create_row: {e}")

            # Budujemy wiersz (16 elementów)
            row_data = [
                email,                                      # A (0): Email
                order_data.get("product_name", ""),         # B (1): Nazwa produktu
                order_data.get("delivery_address", ""),     # C (2): Adres
                order_data.get("phone_number", ""),         # D (3): Tel
                order_data.get("pickup_code", ""),          # E (4): Kod odbioru
                order_data.get("pickup_deadline", ""),      # F (5): Deadline
                order_data.get("available_hours", ""),      # G (6): Godziny
                email_date_str,                             # H (7): Data maila
                f"{status} ({order_data.get('carrier', 'Unknown')})", # I (8): Status
                email_date_str,                             # J (9): Data zamówienia (NOWA)
                est_delivery,                               # K (10): Przewidywana dostawa (NOWA)
                order_data.get("qr_code", ""),              # L (11): QR
                f"'{order_num}" if order_num else "",       # M (12): Nr zamówienia
                order_data.get("info", ""),                 # N (13): Info
                f"'{pkg_num}" if pkg_num else "",           # O (14): Nr paczki
                order_data.get("item_link", "")             # P (15): Link (NOWA LOKALIZACJA)
            ]
            
            # Dodaj wiersz
            self.worksheet.append_row(row_data)
            
            # Pobierz numer nowo dodanego wiersza
            new_row_idx = len(self.worksheet.get_all_values())
            
            # Formatuj na szaro (neutralny kolor dla direct create)
            try:
                self.worksheet.format(f"A{new_row_idx}:P{new_row_idx}", {
                    "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95}
                })
            except: pass
            
            logging.info(f"✅ Utworzono wiersz {new_row_idx} (Direct) dla {email}")

            # =================================================================
            # 5. ✅ NOWE: AUTOMATYCZNA ARCHIWIZACJA JEŚLI DOSTARCZONA
            # =================================================================
            if status == "delivered":
                logging.info(f"📦 Nowy wiersz ma status 'delivered'. Przenoszę natychmiast do archiwum...")
                
                # Przenieś do zakładki Delivered
                self.move_row_to_delivered(new_row_idx, order_data)
                
                # Spróbuj wyczyścić mapowanie
                if hasattr(self, 'email_handler') and self.email_handler:
                    self.email_handler.remove_user_mapping(
                        order_data.get("user_key"),
                        pkg_num,
                        order_num
                    )
                    logging.info("🧹 Wyczyszczono mapowanie po natychmiastowej archiwizacji.")

            return True
            
        except Exception as e:
            logging.error(f"❌ Błąd w _direct_create_row: {e}")
            import traceback
            traceback.print_exc()
            return False

    def load_user_mappings_from_sheets(self):
        """Ładuje mapowania użytkowników z arkusza Google Sheets"""
        logging.debug("Wejście do funkcji: load_user_mappings_from_sheets()")
        try:
            mapping_sheet = self.spreadsheet.worksheet("Użytkownicy")
            mappings = mapping_sheet.get_all_records()
            
            email_to_user = {}
            name_variants = {}
            
            for row in mappings:
                if row.get("email") and row.get("user_key"):
                    email_to_user[row["email"]] = row["user_key"]
                
                if row.get("name_variant") and row.get("user_key"):
                    name_variants[row["name_variant"]] = row["user_key"]
            
            return email_to_user, name_variants
            
        except Exception as e:
            logging.error(f"Błąd podczas ładowania mapowań użytkowników: {e}")
            return {}, {}

    def get_user_key(self, recipient_email=None, recipient_name=None, body=None):
        """Wyciąga klucz użytkownika z dostępnych danych"""
        logging.debug(f"Wejście do funkcji: get_user_key(recipient_email={recipient_email})")
        current_time = time.time()
        if not hasattr(self, 'last_mapping_refresh') or current_time - self.last_mapping_refresh > 3600:
            self.email_to_user, self.name_variants = self.load_user_mappings_from_sheets()
            self.last_mapping_refresh = current_time
        
        if recipient_email and "@" in recipient_email:
            username = recipient_email.split('@')[0].lower()
            return username
            
        return "unknown"

    def update_pickup_status(self, order_data):
        """Aktualizuje informacje o paczce gotowej do odbioru"""
        logging.debug(f"Wejście do funkcji: update_pickup_status(order_data={order_data})")
        if not self.connected and not self.connect():
            return False
        
        try:
            package_number = order_data.get("package_number", "")
            user_key = order_data.get("user_key")
            
            logging.info(f"Aktualizacja informacji o odbiorze dla: {user_key}, paczka: {package_number}")
            
            row = None
            
            if user_key:
                user_rows = self.find_user_rows(user_key)
                if user_rows:
                    row = user_rows[0]
                
            if not row and package_number:
                row = self.find_package_row(package_number)
                    
            carrier_name = order_data.get("carrier", "InPost")
            carrier = self.carriers.get(carrier_name, self.carriers["InPost"])
            
            if row:
                return carrier.update_pickup(row, order_data)
            else:
                return carrier.create_pickup_row(order_data)
                
        except Exception as e:
            logging.error(f"Błąd podczas aktualizacji informacji o odbiorze: {e}")
            return False

    def update_package_transit(self, package_number, order_data):
        """Aktualizuje informacje o paczce w transporcie"""
        logging.debug(f"Wejście do funkcji: update_package_transit(package_number={package_number})")
        if not self.connected and not self.connect():
            return False
        
        try:
            row = None
            
            if package_number:
                row = self.find_package_row(package_number)
            
            if not row and order_data.get("user_key"):
                user_rows = self.find_user_rows(order_data["user_key"])
                if user_rows:
                    row = user_rows[-1]
            
            carrier_name = order_data.get("carrier", "InPost")
            
            if carrier_name not in self.carriers:
                carrier_name = "InPost"
                
            carrier = self.carriers[carrier_name]
            
            if row:
                return carrier.update_transit(row, order_data)
            else:
                if hasattr(carrier, 'create_transit_row'):
                    return carrier.create_transit_row(order_data)
                else:
                    return False
                
        except Exception as e:
            logging.error(f"Błąd podczas aktualizacji paczki w transporcie: {e}")
            return False
        
    def move_row_to_delivered(self, row_number, order_data=None):
        """
        Deleguje przeniesienie wiersza do DeliveredOrdersManager.
        Fixes the error: 'SheetsHandler' object has no attribute 'move_row_to_delivered'
        """
        try:
            from carriers_sheet_handlers import DeliveredOrdersManager
            
            manager = DeliveredOrdersManager(self)
            return manager.move_delivered_order(row_number)
        except Exception as e:
            logging.error(f"❌ Błąd w move_row_to_delivered: {e}")
            return False
        
    def remove_account_from_list(self, email):
        """
        Usuwa podany email z zakładki 'Accounts' (bo zamówienie zakończone).
        """
        if not email: return
        
        logging.info(f"🗑️ Próba usunięcia konta {email} z zakładki Accounts...")
        try:
            # Otwieramy zakładkę Accounts
            accounts_sheet = self.spreadsheet.worksheet("Accounts")
            
            # Szukamy komórki z tym mailem
            # Używamy find, żeby znaleźć konkretny wiersz
            cell = accounts_sheet.find(email)
            
            if cell:
                accounts_sheet.delete_rows(cell.row)
                logging.info(f"✅ Usunięto konto {email} z listy Accounts (wiersz {cell.row}).")
            else:
                logging.warning(f"⚠️ Nie znaleziono maila {email} w zakładce Accounts.")
                
        except Exception as e:
            logging.error(f"❌ Błąd podczas usuwania konta z Accounts: {e}")

    def remove_user_mapping(self, email):
        """
        Usuwa powiązanie emaila z użytkownikiem z zakładki 'Użytkownicy'.
        """
        if not email: return
        
        logging.info(f"🗑️ Próba usunięcia mapowania dla {email}...")
        try:
            # Otwieramy zakładkę z mapowaniami (sprawdź czy nazwa to 'Użytkownicy' czy 'Users')
            mapping_sheet = self.spreadsheet.worksheet("Użytkownicy")
            
            # Szukamy maila w kolumnie A (lub B, zależy jak masz ustawione)
            # find szuka w całym arkuszu, co jest bezpieczne
            cell = mapping_sheet.find(email)
            
            if cell:
                mapping_sheet.delete_rows(cell.row)
                logging.info(f"✅ Usunięto mapowanie dla {email} (wiersz {cell.row}).")
            else:
                logging.warning(f"⚠️ Nie znaleziono mapowania dla {email}.")
                
        except Exception as e:
            # Często arkusz może nie istnieć lub nie mieć wpisu - nie chcemy tu crashować bota
            logging.warning(f"Informacja: Nie udało się usunąć mapowania (może nie istniało): {e}")