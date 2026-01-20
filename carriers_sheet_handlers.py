from datetime import datetime, timedelta
import logging
import re
from config import COLORS

# ==========================================
# 🗺️ MAPA KOLUMN (Konfiguracja Arkusza)
# ==========================================
class Col:
    """Mapowanie nazw kolumn na indeksy w arkuszu (1-based dla gspread)"""
    EMAIL = 1           # A
    PRODUCT = 2         # B
    ADDRESS = 3         # C
    PHONE = 4           # D
    PICKUP_CODE = 5     # E
    DEADLINE = 6        # F
    HOURS = 7           # G
    MSG_DATE = 8        # H (Data ostatniego maila)
    STATUS = 9          # I
    ORDER_DATE = 10     # J (Data zamówienia - stała)
    EST_DELIVERY = 11   # K (Przewidywana dostawa)
    QR = 12             # L
    ORDER_NUM = 13      # M
    INFO = 14           # N
    PKG_NUM = 15        # O
    LINK = 16           # P (Link do aukcji)

    # Helper do zakresów, np. "A:P"
    LAST_COL_LETTER = "P" 

class BaseCarrier:
    """Klasa bazowa dla obsługi przewoźników w arkuszu"""
    
    def __init__(self, sheets_handler):
        self.sheets_handler = sheets_handler
        
        self.name = "Unknown"
        # Domyślne kolory
        self.colors = {
            "shipment_sent": {"red": 0.9, "green": 0.9, "blue": 0.9},
            "pickup": {"red": 1.0, "green": 1.0, "blue": 0.8},
            "delivered": {"red": 0.8, "green": 1.0, "blue": 0.8},
            "transit": {"red": 0.9, "green": 0.9, "blue": 1.0},
            "returned": {"red": 1.0, "green": 0.8, "blue": 0.8},
            "canceled": {"red": 1.0, "green": 0.8, "blue": 0.8},
            "unknown": {"red": 1.0, "green": 1.0, "blue": 1.0}
        }

    def get_status_priority(self, status_text):
        """Zwraca priorytet statusu (im wyższa liczba, tym ważniejszy status)."""
        if not status_text: return 0
        status = status_text.lower()
        
        if "unknown" in status or "nieznan" in status: return 0
        if "confirmed" in status or "zatwierdzon" in status or "potwierdzon" in status: return 1
        if "shipment_sent" in status or "nadan" in status: return 2
        if "transit" in status or "transporcie" in status or "drodze" in status: return 2
        if "pickup" in status or "odbioru" in status or "awizo" in status or "placówce" in status: return 3
        if "delivered" in status or "dostarczon" in status or "odebran" in status: return 4
        if "closed" in status or "zamknięte" in status: return 4
        if "canceled" in status or "anulowan" in status or "zwrot" in status: return 5
        return 0

    def update_shipment_sent(self, row, order_data):
        """Aktualizuje wiersz dla statusu 'shipment_sent'."""
        try:
            # 1. Pobierz obecne dane
            existing_values = self.sheets_handler.worksheet.row_values(row)
            # Uzupełnij listę pustymi stringami, jeśli wiersz jest krótszy niż P (16)
            while len(existing_values) < Col.LINK: existing_values.append("")
            
            existing_pkg = existing_values[Col.PKG_NUM - 1] 
            new_pkg = order_data.get("package_number")
            
            clean_existing = existing_pkg.replace("'", "").strip()
            clean_new = new_pkg.replace("'", "").strip() if new_pkg else ""
            
            if clean_existing and clean_new and clean_existing != clean_new:
                logging.info(f"🔄 ZMIANA NUMERU PACZKI (Handover): {clean_existing} -> {clean_new}")
                
                # Info jest w kolumnie N (Col.INFO)
                current_info = existing_values[Col.INFO - 1]
                if clean_existing not in current_info:
                     combined_info = f"{current_info} | Prev: {clean_existing}".strip(" | ")
                     self.sheets_handler.worksheet.update_cell(row, Col.INFO, combined_info)
                
                # Nadpisz numer paczki
                self.sheets_handler.worksheet.update_cell(row, Col.PKG_NUM, f"'{clean_new}")
            
            elif not clean_existing and clean_new:
                 self.sheets_handler.worksheet.update_cell(row, Col.PKG_NUM, f"'{clean_new}")

            return self.general_update_sheet_data(row, order_data, "shipment_sent")

        except Exception as e:
            logging.error(f"Błąd update_shipment_sent: {e}")
            return False

    def general_update_sheet_data(self, row, order_data, status_key):
        """Ogólna metoda aktualizacji danych w arkuszu z użyciem Col Enum"""
        try:
            # 1. Pobierz obecny status z arkusza (Kolumna I / Col.STATUS)
            current_status = self.sheets_handler.worksheet.cell(row, Col.STATUS).value or ""
            
            # 2. Sprawdź priorytety
            priority_current = self.get_status_priority(current_status)
            priority_new = self.get_status_priority(status_key)
            
            # BLOKADY
            if priority_new == 0 and priority_current > 0: return False
            if priority_new < priority_current: return False

            # 3. Przygotuj dane do aktualizacji
            updates = []
            
            # --- AKTUALIZACJA DAT (Nowa funkcjonalność J i K) ---
            email_date_str = order_data.get("email_date", "")
            
            # H: Data ostatniego maila (zawsze aktualizuj)
            if email_date_str:
                updates.append({'range': f'H{row}', 'values': [[email_date_str]]})
            
            # J & K: Data zamówienia i Przewidywana dostawa
            # Sprawdzamy czy wiersz ma już datę zamówienia. Jeśli nie - wpisujemy.
            current_order_date = self.sheets_handler.worksheet.cell(row, Col.ORDER_DATE).value
            
            if not current_order_date and email_date_str:
                # Wpisz datę pierwszego maila do kolumny J
                updates.append({'range': f'J{row}', 'values': [[email_date_str]]})
                
                # Oblicz +10 dni dla kolumny K
                try:
                    dt_obj = None
                    if len(email_date_str) > 10:
                        dt_obj = datetime.strptime(email_date_str, '%Y-%m-%d %H:%M:%S')
                    else:
                        dt_obj = datetime.strptime(email_date_str, '%Y-%m-%d')
                    
                    if dt_obj:
                        est_date = dt_obj + timedelta(days=10)
                        est_date_str = est_date.strftime('%Y-%m-%d')
                        updates.append({'range': f'K{row}', 'values': [[est_date_str]]})
                        logging.info(f"📅 Ustawiono przewidywaną dostawę na: {est_date_str}")
                except Exception as de:
                    logging.warning(f"Nie udało się obliczyć daty dostawy: {de}")

            # --- RESZTA DANYCH ---
            
            # I: Status
            carrier_display = order_data.get("carrier", self.name)
            status_text = status_key
            if status_key == "shipment_sent": status_text = f"Przesyłka nadana ({carrier_display})"
            elif status_key == "pickup": status_text = f"Gotowa do odbioru ({carrier_display})"
            elif status_key == "delivered": status_text = f"Dostarczona ({carrier_display})"
            elif status_key == "transit": status_text = f"W transporcie ({carrier_display})"
            elif status_key == "unknown": status_text = f"Status nieznany: {order_data.get('status', 'unknown')}"
            elif status_key == "confirmed": status_text = f"Zamówienie potwierdzone ({carrier_display})"
            
            updates.append({'range': f'I{row}', 'values': [[status_text]]})
            
            # M: Numer zamówienia (Col.ORDER_NUM)
            order_num = order_data.get("order_number", "")
            if order_num and "ul." not in str(order_num).lower():
                 updates.append({'range': f'M{row}', 'values': [[f"'{order_num}"]]})

            # N: Info (Col.INFO)
            if order_data.get("info"):
                updates.append({'range': f'N{row}', 'values': [[order_data["info"]]]})
                
            # O: Numer paczki (Col.PKG_NUM)
            pkg_num = order_data.get("package_number", "")
            if pkg_num:
                updates.append({'range': f'O{row}', 'values': [[f"'{pkg_num}"]]})

            # C: Adres (Col.ADDRESS)
            if order_data.get("delivery_address"):
                updates.append({'range': f'C{row}', 'values': [[order_data["delivery_address"]]]})
            
            # P: Link (Col.LINK) - Przeniesione z K!
            if order_data.get("item_link"):
                updates.append({'range': f'P{row}', 'values': [[order_data["item_link"]]]})

            # 4. Wykonaj aktualizację batchową
            if updates:
                self.sheets_handler.worksheet.batch_update(updates)
            
            # 5. Formatowanie (kolory)
            color = self.colors.get(status_key, self.colors.get("shipment_sent"))
            if color:
                self.sheets_handler.worksheet.format(f"A{row}:{Col.LAST_COL_LETTER}{row}", {
                    "backgroundColor": color,
                    "textFormat": {"foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0}}
                })
                
            # Przenieś do Delivered jeśli zakończone
            if status_key == "delivered":
                self.sheets_handler.move_row_to_delivered(row, order_data)
                
            logging.info(f"✅ Zaktualizowano wiersz {row} ({status_text})")
            return True
            
        except Exception as e:
            logging.error(f"Błąd aktualizacji arkusza: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return False

    def create_shipment_row(self, order_data):
        """Tworzy NOWY wiersz dla przesyłki"""
        return self.sheets_handler._direct_create_row(order_data)
        
    def process_notification(self, order_data):
        """Domyślna obsługa powiadomienia (szukaj i aktualizuj)"""
        # 1. Szukaj po numerze paczki
        row = self.sheets_handler.find_package_row(order_data.get("package_number"))
        
        # 2. Szukaj po numerze zamówienia
        if not row:
            row = self.sheets_handler.find_order_row(order_data.get("order_number"))
            
        # 3. Szukaj po user_key (ostatni aktywny)
        if not row:
            user_rows = self.sheets_handler.find_user_rows(order_data.get("user_key"))
            if user_rows:
                row = user_rows[-1]

        if row:
            if order_data["status"] == "shipment_sent":
                self.update_shipment_sent(row, order_data)
            else:
                self.general_update_sheet_data(row, order_data, order_data["status"])

            # Obsługa dostarczenia i czyszczenia mapowania
            if order_data["status"] == "delivered":
                if hasattr(self, 'email_handler') and self.email_handler:
                    self.email_handler.remove_user_mapping(
                        order_data.get("user_key"),
                        order_data.get("package_number"),
                        order_data.get("order_number")
                    )
                    logging.info(f"🧹 Wyczyszczono mapowanie po doręczeniu dla: {order_data.get('user_key')}")
        else:
            # Tworzenie nowego wiersza
            self.create_shipment_row(order_data)
        
class InPostCarrier(BaseCarrier):
    """Klasa obsługująca przewoźnika InPost"""
    
    def __init__(self, sheets_handler):
        super().__init__(sheets_handler)
        self.name = "InPost"
        self.colors = {
            "shipment_sent": {"red": 0.8, "green": 0.9, "blue": 1.0},
            "pickup": {"red": 0.5, "green": 0.5, "blue": 1.0},
            "delivered": {"red": 0.5, "green": 0.9, "blue": 0.8}
        }
    
    def update_pickup(self, row, order_data):
        """Aktualizuje wiersz dla paczki InPost gotowej do odbioru"""
        try:
            # Aktualizacja specyficzna dla InPost
            if order_data.get("pickup_code"):
                self.sheets_handler.worksheet.update_cell(row, Col.PICKUP_CODE, order_data["pickup_code"])
            if order_data.get("pickup_deadline"):
                self.sheets_handler.worksheet.update_cell(row, Col.DEADLINE, order_data["pickup_deadline"])
            if order_data.get("available_hours"):
                self.sheets_handler.worksheet.update_cell(row, Col.HOURS, order_data["available_hours"])
            
            # Adres paczkomatu
            pickup_address = order_data.get("pickup_location", "") or order_data.get("pickup_address", "")
            if order_data.get("pickup_location_code"):
                pickup_address = f"Paczkomat {order_data['pickup_location_code']}"
            if pickup_address:
                self.sheets_handler.worksheet.update_cell(row, Col.ADDRESS, pickup_address)

            # Aktualizuj status i kolor używając metody bazowej
            self.general_update_sheet_data(row, order_data, "pickup")
            return True
        except Exception as e:
            logging.error(f"Błąd InPost update_pickup: {e}")
            return False
    
    def create_pickup_row(self, order_data):
        """Tworzy nowy wiersz dla paczki InPost gotowej do odbioru"""
        try:
            email = order_data.get("customer_name", "") or f"{order_data.get('user_key', '')}@gmail.com"
            
            # Obliczanie daty +10 dni (J i K)
            email_date_str = order_data.get("email_date", datetime.now().strftime('%Y-%m-%d'))
            est_delivery = ""
            try:
                dt_obj = datetime.strptime(email_date_str[:10], '%Y-%m-%d')
                est_delivery = (dt_obj + timedelta(days=10)).strftime('%Y-%m-%d')
            except: pass

            row_data = [
                email,                                          # A: Email
                "Nieznany",                                     # B: Product
                order_data.get("pickup_location", "") or order_data.get("pickup_address", ""), # C: Address
                order_data.get("phone_number", ""),             # D: Phone
                order_data.get("pickup_code", ""),              # E: Code
                order_data.get("pickup_deadline", ""),          # F: Deadline
                order_data.get("available_hours", "PN-SB 06-20"), # G: Hours
                email_date_str,                                 # H: Msg Date
                "Gotowa do odbioru (InPost)",                   # I: Status
                email_date_str,                                 # J: Order Date (NEW)
                est_delivery,                                   # K: Est Delivery (NEW)
                order_data.get("qr_code", ""),                  # L: QR
                "",                                             # M: Order Num
                "",                                             # N: Info
                order_data.get("package_number", ""),           # O: Pkg Num
                ""                                              # P: Link (NEW)
            ]
            
            self.sheets_handler.worksheet.append_row(row_data)
            
            # Formatowanie ostatniego wiersza
            last_row = len(self.sheets_handler.worksheet.get_all_values())
            self.sheets_handler.worksheet.format(f"A{last_row}:P{last_row}", {"backgroundColor": self.colors["pickup"]})
            
            logging.info(f"Utworzono nowy wiersz {last_row} dla InPost (Pickup)")
            return True
        except Exception as e:
            logging.error(f"Błąd create_pickup_row InPost: {e}")
            return False


class DPDCarrier(BaseCarrier):
    """Klasa obsługująca przewoźnika DPD"""
    
    def __init__(self, sheets_handler):
        super().__init__(sheets_handler)
        self.name = "DPD"
        self.colors = {
            "shipment_sent": {"red": 0.9, "green": 0.8, "blue": 1.0},
            "pickup": {"red": 0.5, "green": 0.3, "blue": 0.8},
            "delivered": {"red": 0.5, "green": 0.9, "blue": 0.8}
        }

    def update_transit(self, row, order_data):
        """Aktualizuje wiersz dla paczki DPD w transporcie"""
        return self.general_update_sheet_data(row, order_data, "transit")

    def update_shipment_sent(self, row, order_data):
        return self.general_update_sheet_data(row, order_data, "shipment_sent")

    def create_delivered_row(self, order_data):
        try:
            email = order_data.get("email", "") or f"{order_data.get('user_key', '')}@gmail.com"
            # Daty
            email_date_str = order_data.get("email_date", datetime.now().strftime('%Y-%m-%d'))
            est_delivery = "" # Dostarczona, więc brak estymacji

            row_data = [
                email,                                  # A
                "Dostarczona",                          # B
                order_data.get("delivery_address", ""), # C
                "",                                     # D
                "",                                     # E
                order_data.get("delivery_date", ""),    # F
                "",                                     # G
                email_date_str,                         # H
                "Dostarczona (DPD)",                    # I
                email_date_str,                         # J
                est_delivery,                           # K
                "",                                     # L
                "",                                     # M
                f"Nadawca: {order_data.get('sender', '')}", # N
                order_data.get("package_number", ""),   # O
                ""                                      # P
            ]
            
            self.sheets_handler.worksheet.append_row(row_data)
            last_row = len(self.sheets_handler.worksheet.get_all_values())
            self.sheets_handler.worksheet.format(f"A{last_row}:P{last_row}", {"backgroundColor": self.colors["delivered"]})
            return True
        except Exception as e:
            logging.error(f"Błąd create_delivered_row DPD: {e}")
            return False
            
    def create_transit_row(self, order_data):
        try:
            email = order_data.get("customer_name", "") or f"{order_data.get('user_key', '')}@gmail.com"
            email_date_str = order_data.get("email_date", datetime.now().strftime('%Y-%m-%d'))
            
            # Oblicz Est Delivery
            est_delivery = ""
            try:
                dt_obj = datetime.strptime(email_date_str[:10], '%Y-%m-%d')
                est_delivery = (dt_obj + timedelta(days=10)).strftime('%Y-%m-%d')
            except: pass

            info_text = ""
            if order_data.get("sender_info"): info_text = f"Nadawca: {order_data['sender_info']}"

            row_data = [
                email,                                  # A
                "Nieznany",                             # B
                order_data.get("delivery_address", ""), # C
                order_data.get("phone_number", ""),     # D
                "",                                     # E
                "",                                     # F
                "",                                     # G
                email_date_str,                         # H
                "W transporcie (DPD)",                  # I
                email_date_str,                         # J (Order Date)
                est_delivery,                           # K (Est Delivery)
                "",                                     # L
                order_data.get("reference_number", ""), # M
                info_text,                              # N
                order_data.get("package_number", ""),   # O
                ""                                      # P
            ]
            
            self.sheets_handler.worksheet.append_row(row_data)
            last_row = len(self.sheets_handler.worksheet.get_all_values())
            self.sheets_handler.worksheet.format(f"A{last_row}:P{last_row}", {"backgroundColor": self.colors["transit"]})
            return True
        except Exception as e:
            logging.error(f"Błąd create_transit_row DPD: {e}")
            return False
            
    def _find_row_by_tracking(self, package_number):
        # ... (bez zmian, dziedziczone lub można zostawić jak wkleiłeś)
        return self.sheets_handler.find_package_row(package_number)

class DHLCarrier(BaseCarrier):
    """Obsługa aktualizacji statusów paczek DHL"""
    
    def __init__(self, sheets_handler):
        super().__init__(sheets_handler)
        self.name = "DHL"
        self.colors = {
            "shipment_sent": {"red": 1.0, "green": 1.0, "blue": 0.8},
            "pickup": {"red": 1.0, "green": 0.9, "blue": 0.0},
            "delivered": {"red": 0.5, "green": 0.9, "blue": 0.8}
        }
    
    def update_shipment_sent(self, row, order_data):
        return self.general_update_sheet_data(row, order_data, "shipment_sent")
    
    def update_pickup(self, row, order_data):
        self.general_update_sheet_data(row, order_data, "pickup")
        # Specyficzne dla DHL (kod, deadline) - general update to obsłuży jeśli dane są w order_data
        return True
    
    def update_delivered(self, row, order_data):
        return self.general_update_sheet_data(row, order_data, "delivered")
    
    def create_shipment_row(self, order_data):
        try:
            email = order_data.get("email") or f"{order_data.get('user_key', '')}@gmail.com"
            email_date_str = order_data.get("email_date", datetime.now().strftime('%Y-%m-%d'))
            
            est_delivery = order_data.get("expected_delivery_date", "")
            if not est_delivery:
                try:
                    dt_obj = datetime.strptime(email_date_str[:10], '%Y-%m-%d')
                    est_delivery = (dt_obj + timedelta(days=10)).strftime('%Y-%m-%d')
                except: pass

            pkg_num = order_data.get("package_number", "")
            if order_data.get("secondary_package_number"):
                pkg_num += f" ({order_data['secondary_package_number']})"

            row_data = [
                email,                                  # A
                "",                                     # B
                order_data.get("pickup_location", ""),  # C
                "",                                     # D
                "",                                     # E
                est_delivery,                           # F (Deadline/Expected)
                "",                                     # G
                email_date_str,                         # H
                "Przesyłka nadana (DHL)",               # I
                email_date_str,                         # J (Order Date)
                est_delivery,                           # K (Est Delivery)
                "",                                     # L
                order_data.get("sender", ""),           # M (Sender as Order Num fallback)
                "",                                     # N
                pkg_num,                                # O
                ""                                      # P
            ]
            
            self.sheets_handler.worksheet.append_row(row_data)
            last_row = len(self.sheets_handler.worksheet.get_all_values())
            self.sheets_handler.worksheet.format(f"A{last_row}:P{last_row}", {"backgroundColor": self.colors["shipment_sent"]})
            return True
        except Exception as e:
            logging.error(f"Błąd create_shipment_row DHL: {e}")
            return False
    
    def create_pickup_row(self, order_data):
        try:
            email = order_data.get("email") or f"{order_data.get('user_key', '')}@gmail.com"
            email_date_str = order_data.get("email_date", datetime.now().strftime('%Y-%m-%d'))
            
            # Est Delivery calculation
            est_delivery = ""
            try:
                dt_obj = datetime.strptime(email_date_str[:10], '%Y-%m-%d')
                est_delivery = (dt_obj + timedelta(days=10)).strftime('%Y-%m-%d')
            except: pass

            row_data = [
                email,                                  # A
                "",                                     # B
                order_data.get("pickup_location", ""),  # C
                "",                                     # D
                order_data.get("pickup_code", ""),      # E
                order_data.get("pickup_deadline", ""),  # F
                order_data.get("available_hours", ""),  # G
                email_date_str,                         # H
                "Gotowa do odbioru (DHL)",              # I
                email_date_str,                         # J (Order Date)
                est_delivery,                           # K (Est Delivery)
                "",                                     # L
                order_data.get("sender", ""),           # M
                "",                                     # N
                order_data.get("package_number", ""),   # O
                ""                                      # P
            ]
            
            self.sheets_handler.worksheet.append_row(row_data)
            last_row = len(self.sheets_handler.worksheet.get_all_values())
            self.sheets_handler.worksheet.format(f"A{last_row}:P{last_row}", {"backgroundColor": self.colors["pickup"]})
            return True
        except Exception as e:
            logging.error(f"Błąd create_pickup_row DHL: {e}")
            return False

class AliExpressCarrier(BaseCarrier):
    """Klasa obsługująca przewoźnika AliExpress/Cainiao"""
    
    def __init__(self, sheets_handler):
        super().__init__(sheets_handler)
        self.name = "AliExpress"
        self.colors = {
            "confirmed": {"red": 1.0, "green": 0.9, "blue": 0.8},
            "transit": {"red": 1.0, "green": 0.7, "blue": 0.4},
            "shipment_sent": {"red": 1.0, "green": 0.9, "blue": 0.8},
            "pickup": {"red": 1.0, "green": 0.7, "blue": 0.4},
            "delivered": {"red": 0.5, "green": 0.9, "blue": 0.8},
            "closed": {"red": 1.0, "green": 0.2, "blue": 0.2}
        }

    def update_transit(self, row, order_data):
        return self.general_update_sheet_data(row, order_data, "transit")
    
    def create_transit_row(self, order_data):
        """Tworzy nowy wiersz dla paczki AliExpress w transporcie"""
        try:
            email = order_data.get("customer_name", "") or f"{order_data.get('user_key', '')}@gmail.com"
            email_date_str = order_data.get("email_date", datetime.now().strftime('%Y-%m-%d'))
            
            est_delivery = ""
            try:
                dt_obj = datetime.strptime(email_date_str[:10], '%Y-%m-%d')
                est_delivery = (dt_obj + timedelta(days=10)).strftime('%Y-%m-%d')
            except: pass

            row_data = [
                email,                                          # A: Email
                order_data.get("product_name", "Nieznany"),     # B: Product
                order_data.get("delivery_address", ""),         # C: Address
                order_data.get("phone_number", ""),             # D: Phone
                "",                                             # E: Pickup Code
                "",                                             # F: Deadline
                "",                                             # G: Hours
                email_date_str,                                 # H: Msg Date
                "W transporcie (AliExpress)",                   # I: Status
                email_date_str,                                 # J: Order Date (NEW)
                est_delivery,                                   # K: Est Delivery (NEW)
                "",                                             # L: QR
                order_data.get("order_number", ""),             # M: Order Num
                "",                                             # N: Info
                order_data.get("package_number", ""),           # O: Pkg Num
                order_data.get("item_link", "")                 # P: Link (NEW LOCATION!)
            ]
            
            self.sheets_handler.worksheet.append_row(row_data)
            last_row = len(self.sheets_handler.worksheet.get_all_values())
            self.sheets_handler.worksheet.format(f"A{last_row}:P{last_row}", {"backgroundColor": self.colors["transit"]})
            return True
        except Exception as e:
            logging.error(f"Błąd create_transit_row AliExpress: {e}")
            return False

class ShippingManager:
    """Klasa zarządzająca wysyłkami"""

    def __init__(self, spreadsheet):
        self.spreadsheet = spreadsheet

    def get_carrier(self, order_data):
        if not order_data: return None
        carrier_name = order_data.get("carrier", "").lower()
        if "aliexpress" in carrier_name or "cainiao" in carrier_name:
            return AliExpressCarrier(self.spreadsheet)
        elif "inpost" in carrier_name:
            return InPostCarrier(self.spreadsheet)
        elif "dhl" in carrier_name:
            return DHLCarrier(self.spreadsheet)
        elif "dpd" in carrier_name: # ✅ Dodano obsługę DPD w managerze
            return DPDCarrier(self.spreadsheet)
        else:
            logging.warning(f"Nieobsługiwany przewoźnik: {carrier_name}")
            return None

class EmailAvailabilityManager:
    """Zarządza zakładką 'Accounts'"""
    
    def __init__(self, sheets_handler):
        self.sheets_handler = sheets_handler
        self.worksheet = None
        self._init_accounts_worksheet()

    def _init_accounts_worksheet(self):
        try:
            self.worksheet = self.sheets_handler.spreadsheet.worksheet("Accounts")
        except:
            logging.warning("Nie znaleziono zakładki 'Accounts'.")
            self.worksheet = None

    def get_emails_from_accounts_sheet(self):
        if not self.worksheet:
            self._init_accounts_worksheet()
            if not self.worksheet: return []
            
        try:
            import config
            accounts_data = self.worksheet.get_all_values()
            if len(accounts_data) <= 1: return []
            
            email_configs = []
            
            for i, row in enumerate(accounts_data[1:], start=2):
                try:
                    if len(row) < 1: continue
                    account_email = row[0].strip() if row[0] else ""
                    if not account_email: continue
                    
                    status = row[1].strip().lower() if len(row) > 1 and row[1] else "active"
                    if status in ['inactive', 'delivered', 'stopped', 'paused']: continue
                    
                    password = config.DEFAULT_EMAIL_PASSWORD
                    source = "" 
                    
                    if not source:
                        if '@gmail.com' in account_email.lower(): source = 'gmail'
                        elif '@interia.pl' in account_email.lower() or '@poczta.fm' in account_email.lower(): source = 'interia'
                        elif '@o2.pl' in account_email.lower() or '@tlen.pl' in account_email.lower(): source = 'o2'
                        else: source = 'gmail'
                    
                    if hasattr(config, 'EMAIL_PASSWORDS_MAP') and account_email in config.EMAIL_PASSWORDS_MAP:
                        password = config.EMAIL_PASSWORDS_MAP[account_email]
                    
                    email_configs.append({
                        'email': account_email,
                        'password': password,
                        'source': source,
                        'status': status
                    })
                    
                except Exception as e:
                    logging.error(f"❌ Błąd przetwarzania wiersza {i}: {e}")
                    continue
            
            logging.info(f"📧 Znaleziono {len(email_configs)} aktywnych emaili w Accounts")
            return email_configs
            
        except Exception as e:
            logging.error(f"❌ Błąd pobierania emaili z Accounts: {e}")
            return []

    def check_email_availability(self):
        import json
        import os
        
        logging.info("🎨 Aktualizacja kolorów i statusów w arkuszu Accounts...")
        active_emails = []
        mappings_file = "user_mappings.json"
        
        if os.path.exists(mappings_file):
            try:
                with open(mappings_file, 'r', encoding='utf-8') as f:
                    mappings = json.load(f)
                    for key in mappings.keys(): active_emails.append(key.lower())
            except Exception as e: logging.error(f"Błąd odczytu mapowań: {e}")

        try:
            if hasattr(self.sheets_handler, 'worksheet'):
                sheet = self.sheets_handler.worksheet.spreadsheet.worksheet("Accounts")
            else:
                sheet = self.sheets_handler.workbook.worksheet("Accounts")

            all_values = sheet.get_all_values()
            red_format = {"backgroundColor": {"red": 1.0, "green": 0.8, "blue": 0.8}}
            white_format = {"backgroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}}
            
            for i, row in enumerate(all_values[1:], start=2):
                if not row: continue
                email_in_sheet = str(row[0]).strip().lower()
                login_part = email_in_sheet.split('@')[0]
                
                is_active = (email_in_sheet in active_emails) or (login_part in active_emails)
                current_status = row[1] if len(row) > 1 else ""
                
                if is_active:
                    if current_status != "-": sheet.update_cell(i, 2, "-")
                    try: sheet.format(f"A{i}:B{i}", red_format)
                    except: pass
                else:
                    if current_status != "wolny": sheet.update_cell(i, 2, "wolny")
                    try: sheet.format(f"A{i}:B{i}", white_format)
                    except: pass

            logging.info("✅ Zakończono aktualizację statusów w Accounts.")
        except Exception as e:
            logging.error(f"❌ Błąd w check_email_availability: {e}")

    def free_up_account(self, email):
        clean_email = str(email).strip().lower()
        logging.info(f"💣 [DEBUG] START free_up_account: Próba usunięcia konta: '{clean_email}'")

        try:
            accounts_sheet = None
            if hasattr(self.sheets_handler, 'worksheet'):
                accounts_sheet = self.sheets_handler.worksheet.spreadsheet.worksheet("Accounts")
            else:
                accounts_sheet = self.sheets_handler.workbook.worksheet("Accounts")
            
            col_values = accounts_sheet.col_values(1)
            found = False
            
            for idx, val in enumerate(col_values):
                current_val = str(val).strip().lower()
                if current_val == clean_email:
                    row = idx + 1
                    logging.info(f"🗑️ [DEBUG] Usuwam wiersz {row}...")
                    accounts_sheet.delete_rows(row)
                    found = True
                    break
            
            if not found: logging.warning(f"⚠️ Nie znaleziono emaila '{clean_email}' w arkuszu")

        except Exception as e:
            logging.error(f"❌ Krytyczny błąd w free_up_account: {e}")

        # Druga część - aktualizacja statusów zajętości
        try:
            self.check_email_availability()
        except Exception as e:
            logging.error(f"❌ Błąd po usuwaniu konta: {e}")

class GLSCarrier(BaseCarrier):
    """Klasa obsługująca przewoźnika GLS"""
    
    def __init__(self, sheets_handler):
        super().__init__(sheets_handler)
        self.name = "GLS"
        self.colors = {
            'shipment_sent': {'red': 0.5, 'green': 0.5, 'blue': 0.5},
            'pickup': {'red': 0.3, 'green': 0.3, 'blue': 0.3},
            'delivered': {'red': 0.5, 'green': 0.9, 'blue': 0.8},
            'unknown': {'red': 0.8, 'green': 0.9, 'blue': 1.0},
            'closed': {'red': 1.0, 'green': 0.2, 'blue': 0.2}
        }

class DeliveredOrdersManager:
    """Klasa zarządzająca przenoszeniem dostarczonych zamówień do zakładki Delivered"""
    
    def __init__(self, sheets_handler):
        self.sheets_handler = sheets_handler
        self.delivered_worksheet = None
        self._initialized = False
        self._init_delivered_worksheet()
        self._initialized = True
    
    def _ensure_initialized(self):
        if not self._initialized:
            self._init_delivered_worksheet()
            self._initialized = True
    
    def _init_delivered_worksheet(self):
        try:
            if not hasattr(self.sheets_handler, 'worksheet') or not self.sheets_handler.worksheet: return
            spreadsheet = self.sheets_handler.worksheet.spreadsheet
            try:
                self.delivered_worksheet = spreadsheet.worksheet("Delivered")
            except:
                self.delivered_worksheet = spreadsheet.add_worksheet(title="Delivered", rows=1000, cols=16)
                main_headers = self.sheets_handler.worksheet.row_values(1)
                if main_headers:
                    headers = main_headers[:15]
                    headers.append("Data emaila")
                    self.delivered_worksheet.update("A1:P1", [headers])
                    self.delivered_worksheet.format("A1:P1", {
                        "backgroundColor": {"red": 0.2, "green": 0.7, "blue": 0.2},
                        "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}}
                    })
        except Exception as e:
            logging.error(f"❌ Błąd inicjalizacji Delivered: {e}")
            self.delivered_worksheet = None

    def move_delivered_order(self, row_number):
        try:
            self._ensure_initialized()
            if not self.delivered_worksheet: return False
            
            row_data = self.sheets_handler.worksheet.row_values(row_number)
            if not row_data: return False
            
            while len(row_data) < 16: row_data.append("")
            
            delivered_date = datetime.now().strftime("%Y-%m-%d %H:%M")
            if len(row_data) >= 14:
                current_info = row_data[13] if row_data[13] else ""
                row_data[13] = f"{current_info}\nPrzeniesiono: {delivered_date}".strip()
            
            delivered_values = self.delivered_worksheet.get_all_values()
            next_delivered_row = len(delivered_values) + 1
            
            self.delivered_worksheet.update(f"A{next_delivered_row}:P{next_delivered_row}", [row_data])
            self.delivered_worksheet.format(f"A{next_delivered_row}:P{next_delivered_row}", {
                "backgroundColor": {"red": 0.5, "green": 0.9, "blue": 0.8}
            })
            
            self.sheets_handler.worksheet.delete_rows(row_number)
            return True
        except Exception as e:
            logging.error(f"❌ Błąd przenoszenia zamówienia: {e}")
            return False

    def check_and_move_delivered_orders(self):
        try:
            self._ensure_initialized()
            if not self.delivered_worksheet: return 0
            
            all_data = self.sheets_handler.worksheet.get_all_values()
            if len(all_data) <= 1: return 0
            
            moved_count = 0
            status_col = 8 
            delivered_statuses = ["dostarczona", "delivered", "dostarczono", "odebrana", "zwrócona", "closed"]
            
            for i in range(len(all_data) - 1, 0, -1):
                row = all_data[i]
                current_row_number = i + 1
                if len(row) > status_col:
                    status = row[status_col].strip().lower()
                    if any(ds in status for ds in delivered_statuses):
                        if self.move_delivered_order(current_row_number):
                            moved_count += 1
            
            if moved_count > 0:
                try:
                    email_mgr = EmailAvailabilityManager(self.sheets_handler)
                    email_mgr.check_email_availability()
                except: pass
                
            return moved_count
        except Exception as e:
            logging.error(f"❌ Błąd check_and_move_delivered_orders: {e}")
            return 0

class PocztaPolskaCarrier(BaseCarrier):
    """Klasa obsługująca przewoźnika Poczta Polska"""
    def __init__(self, sheets_handler):
        super().__init__(sheets_handler)
        self.name = "PocztaPolska"
        self.colors = {
            "shipment_sent": {"red": 1.0, "green": 0.9, "blue": 0.9},
            "pickup": {"red": 1.0, "green": 0.6, "blue": 0.6},
            "delivered": {"red": 0.8, "green": 0.95, "blue": 0.8},
            "transit": {"red": 0.95, "green": 0.9, "blue": 0.9},
            "closed": {"red": 1.0, "green": 0.2, "blue": 0.2}
        }