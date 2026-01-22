import gspread
from oauth2client.service_account import ServiceAccountCredentials
import config
import logging
import re
import time
from datetime import datetime, timedelta
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
        self._credentials_file = credentials_file
        self._client = None
        self._initialized = True
        
        self.spreadsheet = None
        self.worksheet = None
        self.connected = False
        self.carriers = {}
        self.last_mapping_refresh = 0
    
    def connect(self):
        """Łączy z arkuszem Google Sheets"""
        if SheetsHandler._spreadsheet is not None:
            return SheetsHandler._spreadsheet
            
        try:
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            credentials = ServiceAccountCredentials.from_json_keyfile_name('service_account.json', scope)
            client = gspread.authorize(credentials)
            
            self.spreadsheet = client.open_by_key(config.SPREADSHEET_ID)
            self.worksheet = self.spreadsheet.worksheet(config.SHEET_NAME)
            
            # Inicjalizacja przewoźników (dla specyficznych metod parsujących, jeśli potrzebne)
            self.carriers["InPost"] = InPostCarrier(self)
            self.carriers["DHL"] = DHLCarrier(self)
            self.carriers["AliExpress"] = AliExpressCarrier(self)
            self.carriers["DPD"] = DPDCarrier(self)
            self.carriers["GLS"] = GLSCarrier(self)
            self.carriers["PocztaPolska"] = PocztaPolskaCarrier(self)
            
            self.connected = True
            SheetsHandler._spreadsheet = self.spreadsheet
            return True
        except Exception as e:
            print(f"Błąd połączenia z Google Sheets: {e}")
            self.connected = False
            return False

    def check_and_archive_delivered_orders(self):
        """STARTUP: Archiwizuje zakończone zamówienia."""
        logging.info("🧹 STARTUP: Pełne czyszczenie zakończonych zamówień...")
        if not self.connected and not self.connect(): return

        try:
            all_values = self.worksheet.get_all_values()
            rows_to_archive = []

            for i, row in enumerate(all_values):
                if i == 0: continue
                # Sprawdź status w kolumnie I (indeks 8)
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
                    if self.move_row_to_delivered(row_num):
                        if email:
                            self.remove_account_from_list(email)
                            self.remove_user_mapping(email)
                        try:
                            self.worksheet.delete_rows(row_num)
                            logging.info(f"🗑️ Usunięto wiersz {row_num}.")
                            time.sleep(1.5)
                        except Exception as e:
                            logging.error(f"❌ Błąd usuwania wiersza: {e}")
            else:
                logging.info("Brak starych zamówień do archiwizacji.")
        except Exception as e:
            logging.error(f"Błąd podczas startowego czyszczenia: {e}")

    # --- GLÓWNA LOGIKA ---

    def handle_order_update(self, order_data):
        """
        Główna metoda sterująca.
        Logika: 1 Email = 1 Wiersz.
        """
        if not self.connected and not self.connect(): return False

        status = order_data.get("status")
        carrier_name = order_data.get("carrier", "InPost")
        
        logging.info(f"🔄 Przetwarzanie statusu: {status} (Przewoźnik: {carrier_name})")

        # 1. Znajdź wiersz (Priorytet: Email)
        row_idx = self.find_order_row(order_data)

        # 2. Aktualizacja (jeśli znaleziono)
        if row_idx:
            logging.info(f"📝 Znaleziono wiersz {row_idx}. Aktualizuję.")
            success = self._update_existing_row(row_idx, order_data)
            
            # Jeśli dostarczono -> Archiwizuj
            if status == "delivered" and success:
                logging.info(f"📦 Status 'delivered'. Przenoszę do archiwum...")
                self.move_row_to_delivered(row_idx, order_data)
                
                email = order_data.get("email") or self.worksheet.cell(row_idx, 1).value
                self.remove_account_from_list(email)
                self.remove_user_mapping(email)
                
                self.worksheet.delete_rows(row_idx)
            return True

        # 3. Tworzenie (jeśli nie znaleziono)
        else:
            logging.info("🆕 Nie znaleziono wiersza dla tego maila. Tworzę nowy.")
            return self._direct_create_row(order_data)

    def find_order_row(self, order_data):
        """Znajduje numer wiersza na podstawie adresu email."""
        target_email = order_data.get("email", "").lower().strip()
        
        # Fallback: zbuduj email z user_key jeśli brak
        if not target_email and order_data.get("user_key"):
            target_email = f"{order_data.get('user_key')}@gmail.com".lower()

        if target_email:
            try:
                # Pobierz tylko kolumnę A (znacznie szybsze niż cały arkusz)
                email_column = self.worksheet.col_values(1)
                
                for idx, email_val in enumerate(email_column):
                    if idx == 0: continue # Pomiń nagłówek
                    if email_val.lower().strip() == target_email:
                        logging.info(f"✅ Znaleziono wiersz {idx + 1} dla {target_email}. Nadpisuję.")
                        return idx + 1
            except Exception as e:
                logging.error(f"Błąd szukania po mailu: {e}")
        
        return None

    def _update_existing_row(self, row_idx, order_data):
        """
        Aktualizuje wiersz. Chroni przed nadpisaniem danych pustymi wartościami.
        Obsługuje kolory dla statusów specjalnych (closed, canceled).
        """
        try:
            # Pobierz aktualne wartości (aby nie nadpisać pustymi)
            current_row = self.worksheet.row_values(row_idx)
            while len(current_row) < 20: current_row.append("")

            updates = []
            
            # STATUS (Kolumna I / 9)
            status = order_data.get("status_pl") or order_data.get("status")
            carrier = order_data.get("carrier", "Nieznany")
            full_status = f"{status} ({carrier})"
            if status: 
                updates.append({'range': f"I{row_idx}", 'values': [[full_status]]})

            # PRODUKT (Kolumna B / 2) - tylko jeśli nowy nie jest pusty
            new_product = order_data.get("product_name")
            current_product = current_row[1]
            if new_product and new_product.strip():
                updates.append({'range': f"B{row_idx}", 'values': [[new_product]]})
            elif not current_product and new_product:
                 updates.append({'range': f"B{row_idx}", 'values': [[new_product]]})

            # ORDER ID (Kolumna M / 13)
            new_order = order_data.get("order_number")
            if new_order and str(new_order).strip():
                updates.append({'range': f"M{row_idx}", 'values': [[f"'{new_order}"]]})

            # PACKAGE ID (Kolumna O / 15)
            new_package = order_data.get("package_number")
            if new_package and str(new_package).strip():
                updates.append({'range': f"O{row_idx}", 'values': [[f"'{new_package}"]]})

            # LINK (Kolumna P / 16)
            new_link = order_data.get("item_link")
            if new_link and "http" in new_link:
                updates.append({'range': f"P{row_idx}", 'values': [[new_link]]})
            
            # DATA UPDATE (Kolumna H / 8)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            updates.append({'range': f"H{row_idx}", 'values': [[now]]})

            # Wykonanie aktualizacji danych
            if updates:
                self.worksheet.batch_update(updates)

            # --- FORMATOWANIE KOLORÓW (Closed/Canceled) ---
            bg_color = None
            text_color = None
            
            raw_status = str(order_data.get("status", "")).lower()
            if raw_status in ["closed", "canceled", "anulowane"]:
                bg_color = {"red": 1.0, "green": 0.2, "blue": 0.2} # Czerwony
                text_color = {"red": 1.0, "green": 1.0, "blue": 1.0} # Biały tekst
            
            if bg_color:
                self.worksheet.format(f"A{row_idx}:P{row_idx}", {
                    "backgroundColor": bg_color,
                    "textFormat": {"foregroundColor": text_color, "bold": True}
                })

            logging.info(f"✅ Zaktualizowano wiersz {row_idx} (Bezpiecznie)")
            return True
            
        except Exception as e:
            logging.error(f"❌ Błąd bezpiecznej aktualizacji wiersza: {e}")
            return False

    def _direct_create_row(self, order_data):
        """Tworzy nowy wiersz."""
        try:
            email = order_data.get("email") or f"{order_data.get('user_key', 'unknown')}@gmail.com"
            order_num = order_data.get("order_number", "")
            pkg_num = order_data.get("package_number", "")
            status = order_data.get("status", "unknown")
            carrier = order_data.get('carrier', 'Unknown')
            
            # Daty
            email_date = order_data.get("email_date", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            est_delivery = ""
            try:
                dt_obj = datetime.strptime(email_date[:10], '%Y-%m-%d')
                est_delivery = (dt_obj + timedelta(days=10)).strftime('%Y-%m-%d')
            except: pass

            row_data = [
                email,                                      # A
                order_data.get("product_name", ""),         # B
                order_data.get("delivery_address", ""),     # C
                order_data.get("phone_number", ""),         # D
                order_data.get("pickup_code", ""),          # E
                order_data.get("pickup_deadline", ""),      # F
                order_data.get("available_hours", ""),      # G
                email_date,                                 # H
                f"{status} ({carrier})",                    # I
                email_date,                                 # J
                est_delivery,                               # K
                order_data.get("qr_code", ""),              # L
                f"'{order_num}" if order_num else "",       # M
                order_data.get("info", ""),                 # N
                f"'{pkg_num}" if pkg_num else "",           # O
                order_data.get("item_link", "")             # P
            ]
            
            self.worksheet.append_row(row_data)
            new_row_idx = len(self.worksheet.col_values(1)) # Szybsze sprawdzenie długości
            
            # Kolory
            bg_color = {"red": 0.95, "green": 0.95, "blue": 0.95} # Szary
            text_color = {"red": 0.0, "green": 0.0, "blue": 0.0}
            
            if status.lower() in ["closed", "canceled", "anulowane"]:
                bg_color = {"red": 1.0, "green": 0.2, "blue": 0.2}
                text_color = {"red": 1.0, "green": 1.0, "blue": 1.0}

            try:
                self.worksheet.format(f"A{new_row_idx}:P{new_row_idx}", {
                    "backgroundColor": bg_color,
                    "textFormat": {"foregroundColor": text_color, "bold": (status.lower() == "closed")}
                })
            except: pass
            
            logging.info(f"✅ Utworzono wiersz {new_row_idx} (Direct) dla {email}. Status: {status}")

            if status == "delivered":
                logging.info(f"📦 Nowy wiersz ma status 'delivered'. Przenoszę do archiwum...")
                self.move_row_to_delivered(new_row_idx, order_data)
                self.remove_account_from_list(email)
                self.remove_user_mapping(email)
                self.worksheet.delete_rows(new_row_idx)

            return True
        except Exception as e:
            logging.error(f"❌ Błąd w _direct_create_row: {e}")
            return False

    # --- POMOCNICZE ---

    def move_row_to_delivered(self, row_number, order_data=None):
        """Deleguje do DeliveredOrdersManager."""
        try:
            from carriers_sheet_handlers import DeliveredOrdersManager
            manager = DeliveredOrdersManager(self)
            return manager.move_delivered_order(row_number)
        except Exception as e:
            logging.error(f"❌ Błąd w move_row_to_delivered: {e}")
            return False
        
    def remove_account_from_list(self, email):
        """Usuwa email z Accounts."""
        if not email: return
        logging.info(f"🗑️ Próba usunięcia konta {email} z Accounts...")
        try:
            sheet = self.spreadsheet.worksheet("Accounts")
            cell = sheet.find(email)
            if cell:
                sheet.delete_rows(cell.row)
                logging.info(f"✅ Usunięto konto {email} z Accounts.")
        except Exception as e:
            logging.error(f"❌ Błąd usuwania z Accounts: {e}")

    def remove_user_mapping(self, email):
        """Usuwa email z Użytkownicy."""
        if not email: return
        logging.info(f"🗑️ Próba usunięcia mapowania dla {email}...")
        try:
            sheet = self.spreadsheet.worksheet("Użytkownicy")
            cell = sheet.find(email)
            if cell:
                sheet.delete_rows(cell.row)
                logging.info(f"✅ Usunięto mapowanie dla {email}.")
        except: pass

    def remove_duplicates(self):
        """Usuwa duplikaty (zachowane dla higieny)."""
        logging.info("🧹 Sprawdzanie duplikatów...")
        if not self.connected and not self.connect(): return
        try:
            vals = self.worksheet.get_all_values()
            seen_emails = set()
            rows_to_del = []
            
            # Prosta logika: 1 email = 1 wiersz. Jeśli drugi raz ten sam email - usuń.
            for i, row in enumerate(vals):
                if i == 0: continue
                email = row[0].lower().strip() if len(row) > 0 else ""
                
                if email:
                    if email in seen_emails:
                        rows_to_del.append(i + 1)
                        logging.info(f"⚠️ Znaleziono duplikat dla {email} (wiersz {i+1})")
                    else:
                        seen_emails.add(email)
            
            for row_idx in reversed(rows_to_del):
                try: self.worksheet.delete_rows(row_idx); time.sleep(1.0)
                except: pass
            
            if rows_to_del: logging.info(f"✅ Usunięto {len(rows_to_del)} duplikatów.")
            else: logging.info("✅ Brak duplikatów.")
            
        except Exception as e:
            logging.error(f"❌ Błąd usuwania duplikatów: {e}")

    def load_user_mappings_from_sheets(self):
        """Helper do mapowań."""
        try:
            s = self.spreadsheet.worksheet("Użytkownicy")
            data = s.get_all_records()
            return {r['email']: r['user_key'] for r in data if r.get('email')}, {}
        except: return {}, {}

    def get_user_key(self, recipient_email=None, recipient_name=None, body=None):
        """Helper do user key."""
        if recipient_email and "@" in recipient_email:
            return recipient_email.split('@')[0].lower()
        return "unknown"
    
    def format_phone_number(self, phone):
        if not phone: return ""
        d = re.sub(r'\D', '', phone)[-9:]
        return f"{d[:3]}-{d[3:6]}-{d[6:]}" if len(d)==9 else d