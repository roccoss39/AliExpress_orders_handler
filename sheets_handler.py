import gspread
from oauth2client.service_account import ServiceAccountCredentials
import config
import logging
import re
import time
from datetime import datetime, timedelta
from carriers_sheet_handlers import Col, EmailAvailabilityManager, InPostCarrier, DHLCarrier, AliExpressCarrier, DPDCarrier, GLSCarrier, PocztaPolskaCarrier

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
        self.deleted_users_cache = {}
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
                if len(row) > 8:
                    status = str(row[8]).lower()
                    keywords = ['dostarczona', 'odebrana', 'zwrócona', 'delivered', 'picked up']
                    if any(key in status for key in keywords):
                        email = row[0]
                        rows_to_archive.append((i + 1, email))

            if rows_to_archive:
                logging.info(f"Znaleziono {len(rows_to_archive)} zamówień do archiwizacji.")
                # Odwrócona kolejność jest kluczowa przy usuwaniu!
                for row_num, email in reversed(rows_to_archive):
                    logging.info(f"📦 Przetwarzanie wiersza {row_num} (Email: {email})")
                    
                    # move_delivered_order robi KOPIUJ I USUŃ. 
                    # Nie musimy usuwać ręcznie drugi raz.
                    if self.move_row_to_delivered(row_num):
                        if email:
                            self.remove_account_from_list(email)
                            self.remove_user_mapping(email)
                        
                        logging.info(f"🗑️ Zarchiwizowano wiersz {row_num}.")
                        time.sleep(1.5)
                    else:
                        logging.error(f"❌ Nie udało się przenieść wiersza {row_num}")
            else:
                logging.info("Brak starych zamówień do archiwizacji.")
        except Exception as e:
            logging.error(f"Błąd podczas startowego czyszczenia: {e}")

    # --- GLÓWNA LOGIKA ---

    def handle_order_update(self, order_data, telegram_notifier=None):
        """
        Główna funkcja aktualizacji i archiwizacji zamówień.
        """

        new_status = order_data.get('status', 'Unknown')
        raw_email = order_data.get('email') or order_data.get('user_key')
        email_val = str(raw_email).strip().lower() if raw_email else None

        row_index = self.find_order_row(order_data)
        
        if row_index:
            # 1. Sprawdzenie priorytetów
            try:
                status_col_idx = Col.STATUS 
                current_status = self.worksheet.cell(row_index, status_col_idx).value
                if self._get_status_priority(new_status) < self._get_status_priority(current_status):
                    logging.warning(f"⛔ Blokada aktualizacji statusu! '{new_status}' < '{current_status}'.")
                    return 
            except: pass
            
            # 2. Aktualizacja komórek
            logging.info(f"📝 Aktualizuję wiersz {row_index} dla {email_val}")
            self.update_row_cells(row_index, order_data)
            
            if telegram_notifier:
                telegram_notifier.send_new_package_alert(order_data)

            # 3. Archiwizacja (jeśli status końcowy)
            final_keywords = ['delivered', 'dostarczona', 'odebrana', 'zwrócona', 'picked up', 'zamknięte']
            if any(k in str(new_status).lower() for k in final_keywords):
                logging.info(f"📦 Status końcowy. Rozpoczynam czyszczenie dla {email_val}...")
                time.sleep(1.5)
                
                if not email_val:
                    email_val = str(self.worksheet.cell(row_index, Col.EMAIL).value).strip().lower()

                if self.move_row_to_delivered(row_index):
                    # CZYSZCZENIE JSON (Nuklearne)
                    if email_val and hasattr(self, 'email_handler') and self.email_handler:
                        user_key = self.get_user_key(email_val)
                        self.email_handler.remove_user_mapping(user_key)

                    # CZYSZCZENIE ACCOUNTS
                    if email_val:
                        self.deleted_users_cache[email_val] = time.time()
                        try:
                            acct_manager = EmailAvailabilityManager(self)
                            acct_manager.free_up_account(email_val)
                        except Exception as e:
                            logging.warning(f"⚠️ Nie można usunąć z Accounts (prawdopodobnie tryb reprocess): {e}")
                else:
                    logging.error("❌ Nie udało się zarchiwizować wiersza.")

        else:
            # 4. Obsługa nowych zamówień / Duchów
            ignore_statuses = ['delivered', 'dostarczona', 'odebrana', 'doręczona']
            if any(k in str(new_status).lower() for k in ignore_statuses):
                logging.warning(f"👻 Ignoruję status końcowy dla nieistniejącego zamówienia: {email_val}")
                return

            if email_val and (time.time() - self.deleted_users_cache.get(email_val, 0) < 60):
                logging.warning(f"🛑 Blokada antyspamowa dla {email_val}.")
                return

            logging.info(f"🆕 Nie znaleziono wiersza. Tworzę nowy wpis.")
            self.append_order(order_data)
            if telegram_notifier:
                telegram_notifier.send_new_package_alert(order_data)

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
    
    def _get_status_priority(self, status_text):
        """Zwraca priorytet statusu (im wyższa liczba, tym ważniejszy status)."""
        if not status_text: return 0
        status = str(status_text).lower()
        
        if "unknown" in status or "nieznan" in status: return 0
        if "confirmed" in status or "zatwierdzon" in status or "potwierdzon" in status or "created_by_inpost" in status:  return 1
        if "transit" in status or "transporcie" in status or "drodze" in status: return 2
        if "shipment_sent" in status or "nadan" in status: return 3
        if "pickup" in status or "odbioru" in status or "awizo" in status or "placówce" in status: return 4
        if "delivered" in status or "dostarczon" in status or "odebran" in status: return 5
        # Closed i Canceled mają najwyższy priorytet, bo kończą cykl definitywnie
        if "closed" in status or "zamknięte" in status: return 6
        if "canceled" in status or "anulowan" in status or "zwrot" in status: return 6
        return 0
    
    def append_order(self, order_data):
        """
        Dodaje nowy wiersz, zapisuje WSZYSTKIE bogate dane z AI i nadaje kolor.
        """
        from datetime import datetime
        import time
        
        try:
            # 1. Definicja email_date na samym początku (Fix dla Pylance)
            email_date = order_data.get("email_date") or datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Tworzymy pustą listę o długości odpowiadającej ostatniej kolumnie (P = 16)
            row = [''] * 16  
            
            # Helper do bezpiecznego pobierania danych
            def get_val(key):
                return str(order_data.get(key, '') or '')

            # 1. Email / Użytkownik
            email_val = order_data.get('email')
            if not email_val:
                email_val = order_data.get('user_key', 'Unknown')
            row[Col.EMAIL - 1] = email_val

            # 2. Produkt
            row[Col.PRODUCT - 1] = get_val('product_name')
            
            # 3. Adres
            row[Col.ADDRESS - 1] = get_val('delivery_address') or get_val('pickup_location')
            
            # 4. Telefon
            row[Col.PHONE - 1] = get_val('courier_phone') or get_val('phone_number')
            
            # 5. Kod odbioru
            row[Col.PICKUP_CODE - 1] = get_val('pickup_code')
            
            # 6. Deadline
            row[Col.DEADLINE - 1] = get_val('pickup_deadline')
            
            # 7. Godziny
            row[Col.HOURS - 1] = get_val('available_hours')
            
            # 8. Data wiadomości
            row[Col.MSG_DATE - 1] = email_date
            
            # 9. Status
            row[Col.STATUS - 1] = get_val('status')
            
            # 10. Data zamówienia
            order_date = get_val('order_date') or get_val('shipping_date')
            if not order_date:
                order_date = datetime.now().strftime('%Y-%m-%d %H:%M')
            row[Col.ORDER_DATE - 1] = order_date
            
            # 11. ✅ Przewidywana dostawa (Z NAPRAWIONĄ LOGIKĄ)
            ai_est_delivery = get_val('estimated_delivery') or get_val('expected_delivery_date')
            
            if ai_est_delivery:
                row[Col.EST_DELIVERY - 1] = ai_est_delivery
            else:
                # Jeśli brak w mailu, obliczamy sami
                carrier_name = order_data.get('carrier', 'Unknown')
                calculated_date = self.calculate_fallback_delivery_date(carrier_name, email_date)
                row[Col.EST_DELIVERY - 1] = calculated_date
            
            # 12. QR Link
            row[Col.QR - 1] = get_val('qr_code') or get_val('qr_link')
            
            # 13. Numer Zamówienia
            row[Col.ORDER_NUM - 1] = get_val('order_number')
            
            # 14. Info / Przewoźnik
            carrier = order_data.get('carrier', 'AliExpress')
            info = order_data.get('info', '')
            courier_name = get_val('courier_name')
            if courier_name:
                info = f"{info} (Kurier: {courier_name})".strip()

            row[Col.INFO - 1] = f"{carrier} | {info}" if info and info != carrier else carrier
            
            # 15. Numer Paczki
            row[Col.PKG_NUM - 1] = get_val('package_number')
            
            # 16. Link do śledzenia
            row[Col.LINK - 1] = get_val('tracking_link') or get_val('item_link')

            # --- ZAPIS DO ARKUSZA ---
            self.worksheet.append_row(row, table_range="A1")
            logging.info(f"🆕 Dodano BOGATY wiersz dla zamówienia {get_val('order_number')}")
            
            # Kolorowanie
            try:
                time.sleep(1) 
                new_row_index = self.find_order_row(order_data)
                if new_row_index:
                    self.update_row_cells(new_row_index, order_data)
            except Exception as e:
                logging.error(f"⚠️ Nie udało się pokolorować nowego wiersza: {e}")
            
        except Exception as e:
            logging.error(f"❌ Błąd krytyczny w append_order: {e}")
            import traceback
            traceback.print_exc()

    def update_row_cells(self, row_index, order_data):
        """
        Aktualizuje wiersz o BOGATE dane (adresy, kody, telefony) i nadaje KOLOR.
        Nadpisuje komórkę tylko wtedy, gdy w nowych danych faktycznie coś jest (nie kasuje starych danych).
        """
        import time
        try:
            cells_to_update = []
            
            # --- HELPERY ---
            def get_val(key):
                """Pobiera wartość jako string, zamienia None na ''"""
                return str(order_data.get(key, '') or '')

            def update_if_exists(col_idx, value):
                """Dodaje komórkę do aktualizacji TYLKO jeśli nowa wartość nie jest pusta."""
                if value and str(value).strip(): 
                    cells_to_update.append(
                        gspread.Cell(row_index, col_idx, str(value))
                    )

            # --- 1. PRZYGOTOWANIE DANYCH (Logika priorytetów) ---
            
            # Adres: delivery_address (z zamówienia) lub pickup_location (z odbioru)
            address = get_val('delivery_address') or get_val('pickup_location')
            
            # Telefon: courier_phone (ważniejszy) lub phone_number
            phone = get_val('courier_phone') or get_val('phone_number')
            
            # Daty i godziny
            deadline = get_val('pickup_deadline')
            hours = get_val('available_hours')
            est_delivery = get_val('estimated_delivery') or get_val('expected_delivery_date')
            
            # Linki
            tracking_link = get_val('tracking_link') or get_val('item_link')
            qr_link = get_val('qr_code') or get_val('qr_link')
            
            # Info + Carrier (Budowanie ładnego stringa)
            carrier = order_data.get('carrier', 'Unknown')
            info = order_data.get('info', '')
            courier_name = get_val('courier_name')
            
            # Budujemy treść Info: "InPost | Kurier: Marek | Info z maila"
            info_parts = [carrier]
            if courier_name:
                info_parts.append(f"Kurier: {courier_name}")
            if info and info != carrier:
                info_parts.append(info)
            
            carrier_info_str = " | ".join(info_parts)

            # --- 2. MAPOWANIE KOLUMN DO ZAPISU ---
            
            # Te pola aktualizujemy prawie zawsze (Status i Data Maila)
            update_if_exists(Col.STATUS, get_val('status'))
            update_if_exists(Col.MSG_DATE, get_val('email_date'))
            
            # Kluczowe dane paczkowe
            update_if_exists(Col.PICKUP_CODE, get_val('pickup_code'))
            update_if_exists(Col.PKG_NUM, get_val('package_number'))
            
            # Bogate dane (Tylko jeśli przyszły w nowym mailu!)
            update_if_exists(Col.PRODUCT, get_val('product_name'))
            update_if_exists(Col.ADDRESS, address)
            update_if_exists(Col.PHONE, phone)
            update_if_exists(Col.DEADLINE, deadline)
            update_if_exists(Col.HOURS, hours)
            update_if_exists(Col.EST_DELIVERY, est_delivery)
            
            # Linki i Info
            update_if_exists(Col.LINK, tracking_link)
            update_if_exists(Col.QR, qr_link)
            update_if_exists(Col.INFO, carrier_info_str)

            # --- 3. FIZYCZNA AKTUALIZACJA DANYCH ---
            if cells_to_update:
                logging.info(f"🐞 [DEBUG] Czekam 1s przed zapisem wiersza {row_index}...") 
                time.sleep(1) 
                self.worksheet.update_cells(cells_to_update)
                logging.info(f"✅ Zaktualizowano {len(cells_to_update)} pól w wierszu {row_index}")

            # --- 4. 🎨 AKTUALIZACJA KOLORU (Zależna od kuriera!) ---
            new_status = order_data.get('status', '')
            
            if new_status:
                # Używamy helpera do wyboru koloru
                color = self._get_status_color(new_status, carrier)
                
                range_name = f"A{row_index}:P{row_index}"
                
                self.worksheet.format(range_name, {
                    "backgroundColor": color,
                    "textFormat": {"foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0}}
                })
                logging.info(f"🎨 Zmieniono kolor wiersza {row_index} (Status: {new_status}, Carrier: {carrier})")

        except Exception as e:
            logging.error(f"❌ Błąd w update_row_cells: {e}")

    def _get_status_color(self, status_text, carrier_name="Unknown"):
        """
        Zwraca kolor RGB zależnie od STATUSU i PRZEWOŹNIKA.
        """
        status = str(status_text).lower()
        carrier = str(carrier_name).lower()
        
        # Domyślny kolor (biały)
        default_color = {"red": 1.0, "green": 1.0, "blue": 1.0}

        # ==========================================
        # 🎨 PALETY KOLORÓW WG PRZEWOŹNIKÓW
        # ==========================================
        palettes = {
            # --- ALIEXPRESS (Odcienie pomarańczu/żółci/zieleni) ---
            "aliexpress": {
                "confirmed": {"red": 1.0, "green": 0.9, "blue": 0.8},
                "zatwierdzon": {"red": 1.0, "green": 0.9, "blue": 0.8},
                "transit": {"red": 1.0, "green": 0.7, "blue": 0.4},     # Pomarańczowy
                "shipment_sent": {"red": 1.0, "green": 0.9, "blue": 0.8},
                "pickup": {"red": 1.0, "green": 0.7, "blue": 0.4},
                "delivered": {"red": 0.5, "green": 0.9, "blue": 0.8},   # Zielony
                "closed": {"red": 1.0, "green": 0.2, "blue": 0.2}       # Czerwony
            },
            # --- INPOST (Odcienie niebieskiego) ---
            "inpost": {
                "created_by_inpost": {"red": 0.85, "green": 0.85, "blue": 0.95},
                "shipment_sent": {"red": 0.8, "green": 0.9, "blue": 1.0},
                "pickup": {"red": 0.5, "green": 0.5, "blue": 1.0},      # Mocny niebieski
                "odbioru": {"red": 0.5, "green": 0.5, "blue": 1.0},
                "delivered": {"red": 0.5, "green": 0.9, "blue": 0.8}    # Zielony/Morski
            },
            # --- DPD (Niebieski/Fioletowy) ---
            "dpd": {
                "shipment_sent": {"red": 0.9, "green": 0.8, "blue": 1.0},
                "transit": {"red": 0.9, "green": 0.8, "blue": 1.0},
                "pickup": {"red": 0.5, "green": 0.3, "blue": 0.8},
                "delivered": {"red": 0.5, "green": 0.9, "blue": 0.8}
            },
            # --- DHL (Żółty) ---
            "dhl": {
                "shipment_sent": {"red": 1.0, "green": 1.0, "blue": 0.8},
                "pickup": {"red": 1.0, "green": 0.9, "blue": 0.0},      # Żółty DHL
                "delivered": {"red": 0.5, "green": 0.9, "blue": 0.8}
            },
            # --- POCZTA POLSKA (Czerwony/Różowy) ---
            "pocztapolska": {
                "shipment_sent": {"red": 1.0, "green": 0.9, "blue": 0.9},
                "transit": {"red": 0.95, "green": 0.9, "blue": 0.9},
                "pickup": {"red": 1.0, "green": 0.6, "blue": 0.6},
                "delivered": {"red": 0.8, "green": 0.95, "blue": 0.8}
            }
        }

        # 1. Wybierz paletę dla danego kuriera (lub domyślną 'universal')
        selected_palette = None
        for key in palettes:
            if key in carrier: # np. jeśli "inpost" jest w "InPost Sp. z o.o."
                selected_palette = palettes[key]
                break
        
        # Jeśli nie znaleziono kuriera, użyj uniwersalnej palety (z poprzedniego kroku)
        if not selected_palette:
            selected_palette = {
                "delivered": {"red": 0.5, "green": 0.9, "blue": 0.8},
                "pickup": {"red": 1.0, "green": 1.0, "blue": 0.8},
                "transit": {"red": 0.9, "green": 0.9, "blue": 1.0},
                "shipment_sent": {"red": 0.9, "green": 0.9, "blue": 0.9},
                "closed": {"red": 1.0, "green": 0.8, "blue": 0.8}
            }

        # 2. Znajdź kolor dla statusu w wybranej palecie
        # Sprawdzamy czy klucz statusu (np. "pickup") znajduje się w tekście statusu (np. "ready for pickup")
        for key, color in selected_palette.items():
            if key in status:
                return color
                
        return default_color
    
    def calculate_fallback_delivery_date(self, carrier_name, start_date_str):
        """
        Oblicza szacowaną datę dostawy, jeśli nie ma jej w mailu.
        Zależy od przewoźnika.
        """
        if not start_date_str:
            return ""
            
        try:
            # Parsowanie daty (bierzemy tylko YYYY-MM-DD)
            start_date = datetime.strptime(start_date_str[:10], '%Y-%m-%d')
            carrier = str(carrier_name).lower()
            days_to_add = 7 # Domyślnie
            
            if "aliexpress" in carrier:
                days_to_add = 10 # Chiny - długo
            elif "inpost" in carrier or "paczkomat" in carrier:
                days_to_add = 2   # Szybko
            elif "dhl" in carrier or "dpd" in carrier or "gls" in carrier:
                days_to_add = 2   # Kurierzy
            elif "poczta" in carrier or "pocztex" in carrier:
                days_to_add = 4   # Poczta
                
            return (start_date + timedelta(days=days_to_add)).strftime('%Y-%m-%d')
        except Exception as e:
            logging.warning(f"Błąd obliczania daty dostawy: {e}")
            return ""