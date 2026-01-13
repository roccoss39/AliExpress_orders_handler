import gspread
from oauth2client.service_account import ServiceAccountCredentials
import config
import logging
import re
import time
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
            self.carriers["GLS"] = GLSCarrier(self)  # Dodano GLS
            self.carriers["PocztaPolska"] = PocztaPolskaCarrier(self)
            
            self.connected = True
            
            # Zapisz połączenie w cache
            SheetsHandler._spreadsheet = self.spreadsheet
            
            return True
        except Exception as e:
            print(f"Błąd połączenia z Google Sheets: {e}")
            self.connected = False
            return False
    
    def format_phone_number(self, phone):
        """Formatuje numer telefonu: usuwa +48 i dodaje spacje co 3 cyfry"""
        logging.debug(f"Wejście do funkcji: format_phone_number(phone={phone})")
        if not phone:
            return ""
            
        # Usuń wszystkie znaki niebędące cyframi
        digits_only = re.sub(r'\D', '', phone)
        
        # Usuń prefiks kraju +48 (ostatnie 9 cyfr)
        if len(digits_only) > 9:
            digits_only = digits_only[-9:]
        
        # Dodaj myślniki co 3 cyfry w formacie XXX-XXX-XXX
        if len(digits_only) == 9:
            formatted = f"{digits_only[0:3]}-{digits_only[3:6]}-{digits_only[6:9]}"
        else:
            # Jeśli numer ma inną długość, podziel go co 3 cyfry
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
            # Szukamy komórki z numerem zamówienia (teraz kolumna H)
            cell = self.worksheet.find(order_number, in_column=8)
            if cell:
                logging.info(f"Znaleziono zamówienie {order_number} w wierszu {cell.row}")
                return cell.row
            
            # Dodatkowe wyszukiwanie - sprawdź cały arkusz
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
            # Szukamy numeru paczki w kolumnie H (package number)
            cell = self.worksheet.find(package_number, in_column=8)  # Zmienione z 4 na 8
            if cell:
                return cell.row
                
            # Jeśli nie znaleziono, przeszukaj cały arkusz (dla wstecznej kompatybilności)
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
                
            # Sprawdź czy zamówienie już istnieje w arkuszu
            row = self.find_order_row(order_number)
            
            # Jeśli zamówienie już istnieje, tylko zaktualizuj dane
            if row:
                logging.info(f"Znaleziono zamówienie {order_number} w wierszu {row} - aktualizuję")
                # Aktualizuj dane zamówienia
                if order_data.get("product_name"):
                    self.worksheet.update_cell(row, 2, order_data["product_name"])
                
                if order_data.get("delivery_address"):
                    self.worksheet.update_cell(row, 3, order_data["delivery_address"])
                    
                if order_data.get("phone_number"):
                    self.worksheet.update_cell(row, 4, order_data["phone_number"])
                
                # Zapisz link do zamówienia
                if order_data.get("item_link"):
                    logging.info(f"Zapisuję normalny link do AliExpress")
                    #simplified_link = "www.aliexpress.com"
                    normal_link = order_data.get("item_link")
                    self.worksheet.update_cell(row, 11, normal_link)
                    logging.info(f"Zapisano uproszczony link: {simplified_link}")
                    
                return True
            
            # Jeśli zamówienie nie istnieje, utwórz nowy wiersz
            logging.info(f"Nie znaleziono zamówienia {order_number} w arkuszu - tworzę nowy wiersz")
            
            # Przygotuj dane wiersza
            row_data = [
                order_data.get("customer_name", order_data.get("email", "")),  # A: email
                order_data.get("product_name", ""),  # B: product name
                order_data.get("delivery_address", ""),  # C: delivery address
                order_data.get("phone_number", ""),  # D: phone
                "",  # E: pickup code (puste na razie)
                order_data.get("delivery_date", ""),  # F: delivery date
                "",  # G: available hours (puste na razie)
                order_data.get("order_number", ""),  # H: order number
                "Zamówiono",  # I: status
                order_data.get("customer_name", order_data.get("email", ""))  # J: email
            ]
            
            # Dodaj nowy wiersz
            values = self.worksheet.get_all_values()
            next_row = len(values) + 1
            cell_range = f"A{next_row}:J{next_row}"
            self.worksheet.update(cell_range, [row_data])
            
            # Zapisz link do zamówienia w kolumnie K
            if order_data.get("item_link"):
                logging.info(f"Dodano nowy wiersz z linkiem do zamówienia: {order_data.get('item_link')[:30]}...")
                simplified_link = "www.aliexpress.com"
                self.worksheet.update_cell(next_row, 11, normal_link)
                logging.info(f"Zapisano uproszczony link: {normal_link}")
            
            logging.info(f"Utworzono nowy wiersz dla zamówienia {order_number} w wierszu {next_row}")
            return True
        except Exception as e:
            logging.error(f"Błąd podczas aktualizacji potwierdzonego zamówienia: {e}")
            return False
    
    def update_delivered_order(self, order_data):
        """Aktualizuje dane zamówienia które zostało dostarczone"""
        logging.debug(f"Wejście do funkcji: update_delivered_order(order_data={order_data})")
        if not self.connected and not self.connect():
            return False
        
        try:
            package_number = order_data.get("package_number", "")
            user_key = order_data.get("user_key")
            order_number = order_data.get("order_number", "")
            
            row = None
            
            # Znajdź wiersz - najpierw po numerze paczki
            if package_number:
                row = self.find_package_row(package_number)
                if row:
                    logging.info(f"Znaleziono wiersz {row} dla paczki {package_number}")
            
            # Jeśli nie znaleziono, szukaj po numerze zamówienia
            if not row and order_number:
                try:
                    cell = self.worksheet.find(order_number, in_column=8)  # Kolumna H
                    if cell:
                        row = cell.row
                        logging.info(f"Znaleziono wiersz {row} dla zamówienia {order_number}")
                except:
                    logging.warning(f"Nie znaleziono wiersza dla zamówienia {order_number}")
            
            # Jeśli nadal nie znaleziono, szukaj po użytkowniku
            if not row and user_key:
                user_rows = self.find_user_rows(user_key)
                if user_rows:
                    row = user_rows[-1]  # Użyj najnowszego wiersza
                    logging.info(f"Znaleziono wiersz {row} dla użytkownika {user_key}")
            
            # Pobierz przewoźnika
            carrier_name = order_data.get("carrier", "InPost")
            
            # Jeśli przewoźnik nie jest zarejestrowany, użyj domyślnego
            if carrier_name not in self.carriers:
                logging.warning(f"Nieznany przewoźnik: {carrier_name}, używam InPost")
                carrier_name = "InPost"
                
            carrier = self.carriers[carrier_name]
            
            # Aktualizuj wiersz jeśli znaleziono
            if row:
                return carrier.update_delivered(row, order_data)
            else:
                logging.warning(f"Nie znaleziono wiersza dla paczki {package_number} - nie można zaktualizować statusu")
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
            # Sprawdź, czy mamy numer zamówienia
            if not order_data.get("order_number"):
                logging.warning("Brak numeru zamówienia w anulowanym zamówieniu. Pomijam.")
                return False
                
            # Znajdujemy wiersz z numerem zamówienia
            row = self.find_order_row(order_data["order_number"])
            
            if row:
                # Oznaczamy jako anulowane (czerwone tło)
                self.worksheet.format(f"A{row}:I{row}", {
                    "backgroundColor": config.COLORS["canceled"]
                })
                
                # Oznaczamy email jako dostępny (fioletowy)
                email = self.worksheet.cell(row, 1).value
                if email:
                    self.worksheet.update_cell(row, 9, email)  # I: available emails
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
            
            # Znajdź wiersze użytkownika
            user_rows = self.find_user_rows(order_data["user_key"])
            
            if user_rows and len(user_rows) > 0:
                # Usuń najnowszy wiersz (zakładamy, że to jest zamówienie, które zostało odebrane)
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
        """
        Znajduje numery wierszy dla danego użytkownika (user_key lub email).
        Ignoruje wielkość liter.
        """
        if not self.connected and not self.connect():
            return []
            
        found_rows = []
        try:
            user_key = user_key.lower().strip()
            
            # Pobierz całą kolumnę A (maile)
            emails_col = self.worksheet.col_values(1)
            
            # Przeszukaj (indeksowanie w gspread od 1)
            for i, email_val in enumerate(emails_col):
                if not email_val: continue
                
                # Sprawdź czy to ten sam email (ignorując wielkość liter)
                clean_email = str(email_val).lower().strip()
                clean_key_from_email = clean_email.split('@')[0]
                
                # Porównaj pełny email LUB sam klucz użytkownika
                if user_key == clean_email or user_key == clean_key_from_email:
                    found_rows.append(i + 1) # +1 bo wiersze są od 1
                    
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
            logging.info(f"WAŻNE: Tworzenie nowego wiersza dla użytkownika {user_key}")
            logging.info(f"DEBUG: Dane wejściowe: {order_data}")  # Dodaj debugowanie
            
            # Podstawowe dane zamówienia
            email = order_data.get("customer_name") or ""
            if "@" not in email and user_key:
                email = f"{user_key}@gmail.com"  # Domyślna domena
                
            # Wyodrębnij godziny dostępności z dokładnym logowaniem
            available_hours = order_data.get("available_hours")
            logging.info(f"DEBUG: Wyciągnięte godziny dostępności: '{available_hours}'")
            
            if not available_hours:
                available_hours = "PN-ND 24/7"  # Wartość domyślna
                logging.info(f"DEBUG: Używam domyślnych godzin dostępności: '{available_hours}'")
            
            # Przygotuj dane QR
            qr_data = ""
            if order_data.get("qr_code"):
                if order_data.get("qr_code_in_attachment") and order_data.get("pickup_code"):
                    # Automatycznie wygeneruj kod QR na podstawie kodu odbioru
                    qr_data = f'=IMAGE("https://chart.googleapis.com/chart?chs=150x150&cht=qr&chl={order_data["pickup_code"]}")'
                    logging.info(f"Przygotowano formułę QR dla kodu odbioru: {order_data['pickup_code']}")
                else:
                    qr_data = order_data["qr_code"]

            # Przygotuj dane wiersza
            row_data = [
                email,  # A: email
                "Nieznany",  # B: product name
                order_data.get("pickup_location", ""),  # C: receive place
                order_data.get("phone_number", ""),  # D: phone
                order_data.get("pickup_code", ""),  # E: receive code
                order_data.get("pickup_deadline", ""),  # F: time to receive
                available_hours,  # G: available hours - POPRAWIONE
                "",  # H: order number - puste jeśli nie znamy
                "Gotowe do odbioru",  # I: status
                email,  # J: available emails
                "",  # K: aliexpress link (dodane wcześniej)
                qr_data  # L: QR kod
            ]
            
            logging.info(f"DEBUG: Dane wiersza przed zapisem: {row_data}")  # Dodaj debugowanie
            
            # Dodaj nowy wiersz - znajdź pierwszy pusty wiersz
            values = self.worksheet.get_all_values()
            next_row = len(values) + 1
            logging.info(f"Dodaję nowy wiersz na pozycji {next_row}")
            
            # Dodaj dane do arkusza
            cell_range = f"A{next_row}:L{next_row}"
            self.worksheet.update(cell_range, [row_data])
            logging.info(f"Zaktualizowano zakres {cell_range} z danymi: {row_data}")
            
            # Ustaw formatowanie
            try:
                self.worksheet.format(f"A{next_row}:J{next_row}", {
                    "backgroundColor": {
                        "red": 1.0,
                        "green": 0.95,
                        "blue": 0.8
                    }
                })
                logging.info("Zastosowano formatowanie")
            except Exception as format_error:
                logging.error(f"Błąd podczas formatowania: {format_error}")
            
            logging.info(f"Utworzono nowy wiersz zamówienia (z powiadomienia o odbiorze) w wierszu {next_row}")
            return True
        except Exception as e:
            logging.error(f"Błąd podczas tworzenia nowego wiersza zamówienia: {e}")
            logging.exception(e)  # Pełna informacja o błędzie
            return False

    def _direct_create_row(self, order_data):
        """
        Bezpośrednie tworzenie wiersza z obsługą WSZYSTKICH kolumn (Fix dla numeru zamówienia).
        """
        try:
            # 1. Znajdź pierwszy wolny wiersz (sprawdzając kolumnę A - Email)
            emails = self.worksheet.col_values(1)
            # Jeśli kolumna pusta (tylko nagłówek), first_empty = 2
            first_empty_row = len(emails) + 1
            
            # Zabezpieczenie: minimum 2
            if first_empty_row < 2: first_empty_row = 2

            logging.info(f"Tworzę nowy wiersz awaryjnie w pozycji {first_empty_row}")
            
            # 2. Przygotuj dane (lista 15 elementów - kolumny A-O)
            row_data = [""] * 15
            
            # Kolumna A: Email
            row_data[0] = order_data.get('email', '') or ""
            
            # Kolumna B: Nazwa produktu (zostawiamy puste lub bierzemy z danych)
            row_data[1] = order_data.get('product_name', '') or ""

            # Kolumna C: Adres
            row_data[2] = order_data.get('delivery_address', '') or ""
            
            # Kolumna H: Data maila (index 7)
            row_data[7] = order_data.get('email_date', '') or ""
            
            # Kolumna I: Status (index 8)
            status_map = {
                "shipment_sent": "Przesyłka nadana",
                "pickup": "Gotowa do odbioru",
                "delivered": "Dostarczona",
                "transit": "W transporcie",
                "confirmed": "Potwierdzone",
                "closed": "Zamknięte"
            }
            status_key = order_data.get('status', 'unknown')
            carrier_name = order_data.get('carrier', 'Unknown')
            # Ładny format statusu
            row_data[8] = f"{status_map.get(status_key, status_key)} ({carrier_name})" 
            
            # ✅ KOLUMNA M (Index 12): Numer zamówienia (TO TUTAJ BYŁ BRAK)
            order_num = order_data.get('order_number')
            if order_num:
                # Dodajemy apostrof, żeby Excel nie zamienił długiego numeru na format naukowy (3.06E+15)
                row_data[12] = f"'{order_num}" 
            
            # Kolumna N (Index 13): Info
            # Jeśli info jest takie samo jak status, to nie wpisuj, żeby nie dublować
            info_text = order_data.get('info', '') or ""
            if info_text == row_data[8]: 
                row_data[13] = "" # Puste, bo to samo co status
            else:
                row_data[13] = info_text

            # Kolumna O (Index 14): Numer paczki
            pkg = order_data.get('package_number', '')
            if pkg: 
                row_data[14] = f"'{pkg}" # Z apostrofem

            # 3. Zapisz jednym strzałem
            range_name = f"A{first_empty_row}:O{first_empty_row}"
            self.worksheet.update(range_name=range_name, values=[row_data])
            
            logging.info(f"Utworzono awaryjnie wiersz {first_empty_row}: Order={order_num}, Paczka={pkg}")
            try:
                # Pobierz obiekt przewoźnika, żeby znać jego kolory
                carrier_name = order_data.get('carrier', 'Unknown')
                carrier = self.carriers.get(carrier_name)
                
                # Jeśli nie ma przewoźnika, użyj domyślnego
                if not carrier: 
                     # Tymczasowa instancja BaseCarrier, żeby dostać domyślne kolory
                     from carriers_sheet_handlers import BaseCarrier
                     carrier = BaseCarrier(self)

                # Pobierz klucz statusu (np. 'shipment_sent')
                status_key = order_data.get('status', 'unknown')
                
                # Pobierz kolor z mapy kolorów przewoźnika
                color = carrier.colors.get(status_key, carrier.colors.get('unknown'))
                
                if color:
                    # Nałóż kolor na zakres A:O
                    self.worksheet.format(f"A{first_empty_row}:O{first_empty_row}", {
                        "backgroundColor": color,
                        "textFormat": {"foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0}}
                    })
                    logging.info(f"🎨 Pomalowano wiersz {first_empty_row} na kolor statusu {status_key}")
            except Exception as e:
                logging.warning(f"⚠️ Nie udało się pokolorować wiersza {first_empty_row}: {e}")

            return True
            
        except Exception as e:
            logging.error(f"Błąd _direct_create_row: {e}")
            return False

    def load_user_mappings_from_sheets(self):
        """Ładuje mapowania użytkowników z arkusza Google Sheets"""
        logging.debug("Wejście do funkcji: load_user_mappings_from_sheets()")
        try:
            # Otwórz odpowiednią zakładkę z mapowaniami
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
        logging.debug(f"Wejście do funkcji: get_user_key(recipient_email={recipient_email}, recipient_name={recipient_name})")
        # Automatycznie odśwież mapowania jeśli upłynął odpowiedni czas
        current_time = time.time()
        if not hasattr(self, 'last_mapping_refresh') or current_time - self.last_mapping_refresh > 3600:  # Co godzinę
            self.email_to_user, self.name_variants = self.load_user_mappings_from_sheets()
            self.last_mapping_refresh = current_time
        
        # Pozostała logika bez zmian...
        # Najpierw sprawdź w mapowaniach (teraz załadowanych z arkusza)
        # [...]
        
        # Jeśli nie znaleziono, użyj części przed @ jako klucza
        if recipient_email and "@" in recipient_email:
            username = recipient_email.split('@')[0].lower()  # Dodaj .lower() dla spójności
            logging.info(f"Używam nazwy użytkownika z adresu email: {username}")
            
            # Automatycznie dodaj nowe mapowanie do arkusza
            try:
                self.add_new_user_mapping(recipient_email, username)
            except:
                pass  # Ignoruj błędy przy dodawaniu
                
            return username

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
            
            # Znajdź wiersz dla tego użytkownika
            if user_key:
                user_rows = self.find_user_rows(user_key)
                if user_rows:
                    row = user_rows[0]  # Pierwszy znaleziony wiersz
                    logging.info(f"Znaleziono wiersz {row} dla użytkownika {user_key}")
                
            # Jeśli nie znaleziono wiersza, sprawdź po numerze paczki
            if not row and package_number:
                row = self.find_package_row(package_number)
                if row:
                    logging.info(f"Znaleziono wiersz {row} dla paczki {package_number}")
                    
            # Pobierz przewoźnika
            carrier_name = order_data.get("carrier", "InPost")
            carrier = self.carriers.get(carrier_name, self.carriers["InPost"])
            
            # Aktualizuj lub utwórz wiersz
            if row:
                return carrier.update_pickup(row, order_data)
            else:
                return carrier.create_pickup_row(order_data)
                
        except Exception as e:
            logging.error(f"Błąd podczas aktualizacji informacji o odbiorze: {e}")
            return False

    def update_package_transit(self, package_number, order_data):
        """Aktualizuje informacje o paczce w transporcie"""
        logging.debug(f"Wejście do funkcji: update_package_transit(package_number={package_number}, order_data={order_data})")
        if not self.connected and not self.connect():
            return False
        
        try:
            row = None
            
            # Znajdź wiersz po numerze paczki
            if package_number:
                row = self.find_package_row(package_number)
                if row:
                    logging.info(f"Znaleziono wiersz {row} dla paczki {package_number}")
            
            # Jeśli nie znaleziono, szukaj po użytkowniku
            if not row and order_data.get("user_key"):
                user_rows = self.find_user_rows(order_data["user_key"])
                if user_rows:
                    row = user_rows[-1]  # Użyj najnowszego wiersza
                    logging.info(f"Znaleziono wiersz {row} dla użytkownika {order_data['user_key']}")
            
            # Pobierz przewoźnika
            carrier_name = order_data.get("carrier", "InPost")
            
            # Jeśli przewoźnik nie jest zarejestrowany, użyj domyślnego
            if carrier_name not in self.carriers:
                logging.warning(f"Nieznany przewoźnik: {carrier_name}, używam InPost")
                carrier_name = "InPost"
                
            carrier = self.carriers[carrier_name]
            
            # Aktualizuj lub utwórz wiersz
            if row:
                return carrier.update_transit(row, order_data)
            else:
                logging.info(f"Nie znaleziono wiersza dla paczki {package_number} - próbuję utworzyć nowy")
                if hasattr(carrier, 'create_transit_row') and callable(carrier.create_transit_row):
                    return carrier.create_transit_row(order_data)
                else:
                    logging.warning(f"Przewoźnik {carrier_name} nie implementuje metody create_transit_row")
                    return False
                
        except Exception as e:
            logging.error(f"Błąd podczas aktualizacji paczki w transporcie: {e}")
            return False
        
    def move_row_to_delivered(self, row_number, order_data=None):
        """
        Deleguje przeniesienie wiersza do DeliveredOrdersManager.
        Naprawia błąd: 'SheetsHandler' object has no attribute 'move_row_to_delivered'
        """
        try:
            # Import wewnątrz funkcji, aby uniknąć błędów cyklicznych (circular import)
            from carriers_sheet_handlers import DeliveredOrdersManager
            
            manager = DeliveredOrdersManager(self)
            return manager.move_delivered_order(row_number)
        except Exception as e:
            logging.error(f"❌ Błąd w move_row_to_delivered: {e}")
            return False


