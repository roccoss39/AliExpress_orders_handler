from datetime import datetime, timedelta # ✅ Pamiętaj o dodaniu timedelta
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
    LINK = 16           # P (Nowa kolumna na linki, bo K zajęte)

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
            
            # Używamy nowej klasy Col zamiast '14'
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
                updates.append({'range': f'H{row}', 'values': [[email_date_str]]}) # Col.MSG_DATE (H) is hardcoded letter here for ranges logic, keeping generic is cleaner but A1 notation needs letter.
                # Lepiej użyć konwertera numer->litera, ale dla prostoty zostawmy litery w kluczach 'range', a numery w logice 'update_cell'
                # Ale batch_update wymaga A1 notation. 
                # H = Col.MSG_DATE
            
            # J & K: Data zamówienia i Przewidywana dostawa
            # Sprawdzamy czy wiersz ma już datę zamówienia. Jeśli nie - wpisujemy.
            current_order_date = self.sheets_handler.worksheet.cell(row, Col.ORDER_DATE).value
            
            if not current_order_date and email_date_str:
                # Wpisz datę pierwszego maila do kolumny J
                updates.append({'range': f'J{row}', 'values': [[email_date_str]]})
                
                # Oblicz +10 dni dla kolumny K
                try:
                    # Zakładamy format YYYY-MM-DD HH:MM:SS lub YYYY-MM-DD
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
            
            # 5. Formatowanie (kolory) - Zakres A do P
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
        # Najpierw szukaj po numerze paczki (najpewniejsze)
        row = self.sheets_handler.find_package_row(order_data.get("package_number"))
        
        # Jeśli nie, szukaj po numerze zamówienia
        if not row:
            row = self.sheets_handler.find_order_row(order_data.get("order_number"))
            
        # Jeśli nie, szukaj po user_key (ale ostrożnie - weź ostatni aktywny)
        if not row:
            user_rows = self.sheets_handler.find_user_rows(order_data.get("user_key"))
            if user_rows:
                # Tu jest ryzyko, bierzemy ostatni wiersz usera
                # Ale update_shipment_sent ma teraz zabezpieczenie przed nadpisaniem innej paczki!
                row = user_rows[-1]

        if row:
            if order_data["status"] == "shipment_sent":
                self.update_shipment_sent(row, order_data)
            else:
                self.general_update_sheet_data(row, order_data, order_data["status"])

                if order_data["status"] == "delivered":
                    if hasattr(self, 'email_handler') and self.email_handler:
                        self.email_handler.remove_user_mapping(
                            order_data.get("user_key"),
                            order_data.get("package_number"),
                            order_data.get("order_number")
                        )
                        logging.info(f"🧹 Wyczyszczono mapowanie po doręczeniu dla: {order_data.get('user_key')}")
                    else:
                        logging.warning("⚠️ Nie można wyczyścić mapowania: brak 'email_handler' w obiekcie Carrier")

        else:
            # Nie znaleziono wiersza - utwórz nowy
            if order_data["status"] in ["shipment_sent", "transit", "confirmed"]:
                self.create_shipment_row(order_data)
            else:
                logging.warning(f"Otrzymano status {order_data['status']} dla nieistniejącego zamówienia. Tworzę nowy wiersz.")
                self.create_shipment_row(order_data)
        
class InPostCarrier(BaseCarrier):
    """Klasa obsługująca przewoźnika InPost"""
    
    def __init__(self, sheets_handler):
        super().__init__(sheets_handler)
        self.name = "InPost"
        # INPOST - NIEBIESKIE ODCIENIE
        self.colors = {
            "shipment_sent": {"red": 0.8, "green": 0.9, "blue": 1.0},   # Jasny niebieski - nadano
            "pickup": {"red": 0.5, "green": 0.5, "blue": 1.0},          # Ciemny niebieski - gotowe do odbioru
            "delivered": {"red": 0.5, "green": 0.9, "blue": 0.8}        # Turkusowy - dostarczone
        }
    
    def update_pickup(self, row, order_data):
        """Aktualizuje wiersz dla paczki InPost gotowej do odbioru"""
        try:
            # Przygotuj dane z walidacją
            pickup_code = order_data.get("pickup_code", "")
            
            pickup_deadline = order_data.get("pickup_deadline", "")
            if pickup_deadline == "None" or pickup_deadline is None:
                pickup_deadline = ""
                
            available_hours = order_data.get("available_hours", "")
            if available_hours == "None" or available_hours is None:
                available_hours = "PN-SB 06-20"
                
            pickup_address = order_data.get("pickup_address", "")
            if pickup_address == "None" or pickup_address is None or pickup_address.startswith("InPost <"):
                if order_data.get("pickup_location_code"):
                    pickup_address = f"Paczkomat {order_data['pickup_location_code']}"
                else:
                    pickup_address = ""
            
            # Aktualizuj dane odbioru
            logging.info(f"Aktualizuję komórkę E{row} na kod odbioru: {pickup_code}")
            self.sheets_handler.worksheet.update_cell(row, 5, pickup_code)
            
            logging.info(f"Aktualizuję komórkę F{row} na termin odbioru: {pickup_deadline}")
            self.sheets_handler.worksheet.update_cell(row, 6, pickup_deadline)
            
            logging.info(f"Aktualizuję komórkę G{row} na godziny dostępności: {available_hours}")
            self.sheets_handler.worksheet.update_cell(row, 7, available_hours)
            
            logging.info(f"Aktualizuję komórkę C{row} na adres odbioru: {pickup_address}")
            self.sheets_handler.worksheet.update_cell(row, 3, pickup_address)
            
            # Aktualizuj status
            status = f"Gotowa do odbioru (InPost)"
            logging.info(f"Aktualizuję komórkę I{row} na status: {status}")
            self.sheets_handler.worksheet.update_cell(row, 9, status)
            
            # Zastosuj kolor
            logging.info(f"Zastosowano kolor dla wiersza {row} (status: gotowy do odbioru, przewoźnik: InPost)")
            self.sheets_handler.worksheet.format(f"A{row}:N{row}", {
                "backgroundColor": self.colors["pickup"]
            })
            
            return True
        except Exception as e:
            logging.error(f"Błąd podczas aktualizacji paczki InPost gotowej do odbioru: {e}")
            return False
    
    def create_pickup_row(self, order_data):
        """Tworzy nowy wiersz dla paczki InPost gotowej do odbioru"""
        try:
            # Pobierz dane
            email = order_data.get("customer_name", "")
            if not email and order_data.get("user_key"):
                email = f"{order_data['user_key']}@gmail.com"
            
            # Przygotuj dane wiersza z walidacją
            pickup_code = order_data.get("pickup_code", "")
            
            pickup_deadline = order_data.get("pickup_deadline", "")
            if pickup_deadline == "None" or pickup_deadline is None:
                pickup_deadline = ""
                
            available_hours = order_data.get("available_hours", "")
            if available_hours == "None" or available_hours is None:
                available_hours = "PN-SB 06-20"
                
            # Najpierw sprawdź, czy jest dostępne pole pickup_location
            pickup_address = order_data.get("pickup_location", "")

            # Jeśli nie, spróbuj użyć pickup_address
            if not pickup_address:
                pickup_address = order_data.get("pickup_address", "")
                
            # Sprawdź, czy wartość jest poprawna
            if pickup_address == "None" or pickup_address is None or pickup_address.startswith("InPost <"):
                # Jeśli nie, utwórz adres z kodu paczkomatu
                if order_data.get("pickup_location_code"):
                    pickup_address = f"Paczkomat {order_data['pickup_location_code']}: {order_data.get('pickup_address', '')}"
                else:
                    pickup_address = ""
            
            # Przygotuj dane wiersza
            row_data = [
                email,  # A: email
                "Nieznany",  # B: product name
                pickup_address,  # C: pickup location
                order_data.get("phone_number", ""),  # D: phone number
                pickup_code,  # E: pickup code
                pickup_deadline,  # F: time to pickup
                available_hours,  # G: available hours
                "",  # H: order number
                f"Gotowa do odbioru (InPost)",  # I: status
                email,  # J: available emails
                "",  # K: aliexpress link
                order_data.get("qr_code", ""),  # L: QR code
                order_data.get("package_number", "")  # M: package number
            ]
            
            # Dodaj wiersz
            values = self.sheets_handler.worksheet.get_all_values()
            next_row = len(values) + 1
            cell_range = f"A{next_row}:M{next_row}"
            self.sheets_handler.worksheet.update(cell_range, [row_data])
            
            # Zastosuj kolor
            self.sheets_handler.worksheet.format(f"A{next_row}:M{next_row}", {
                "backgroundColor": self.colors["pickup"]
            })
            
            logging.info(f"Utworzono nowy wiersz {next_row} dla paczki InPost gotowej do odbioru")
            return True
        except Exception as e:
            logging.error(f"Błąd podczas tworzenia wiersza dla paczki InPost: {e}")
            return False


class DPDCarrier(BaseCarrier):
    """Klasa obsługująca przewoźnika DPD"""
    
    def __init__(self, sheets_handler):
        super().__init__(sheets_handler)
        self.name = "DPD"
        # DPD - FIOLETOWE ODCIENIE
        self.colors = {
            "shipment_sent": {"red": 0.9, "green": 0.8, "blue": 1.0},   # Jasny fioletowy - nadano
            "pickup": {"red": 0.5, "green": 0.3, "blue": 0.8},          # Ciemny fioletowy - gotowe do odbioru
            "delivered": {"red": 0.5, "green": 0.9, "blue": 0.8}        # Turkusowy - dostarczone
        }

    def update_transit(self, row, order_data):
        """Aktualizuje wiersz dla paczki DPD w transporcie"""
        try:
            # Aktualizuj status (Kolumna I)
            status = "W transporcie (DPD)"
            self.sheets_handler.worksheet.update_cell(row, Col.STATUS, status)
            
            # Zapisz numer paczki (Kolumna O)
            if order_data.get("package_number"):
                self.sheets_handler.worksheet.update_cell(row, Col.PKG_NUM, f"'{order_data['package_number']}")
            
            # Aktualizuj adres dostawy (Kolumna C)
            if order_data.get("delivery_address"):
                # Obsługa zagnieżdżonego formatu adresu (słownik vs string)
                if isinstance(order_data["delivery_address"], dict):
                    address_obj = order_data["delivery_address"]
                    address_parts = []
                    
                    if "street" in address_obj: address_parts.append(address_obj["street"])
                    if "postal_code" in address_obj: address_parts.append(address_obj["postal_code"])
                    if "city" in address_obj: address_parts.append(address_obj["city"])
                    if "country" in address_obj: address_parts.append(address_obj["country"])
                    
                    address_text = ", ".join(address_parts)
                else:
                    address_text = order_data["delivery_address"]
                
                self.sheets_handler.worksheet.update_cell(row, Col.ADDRESS, address_text)
            
            # Przygotuj informacje do kolumny INFO (Kolumna N)
            info_text = ""
            
            # Dodaj informacje o kurierze
            if order_data.get("courier_info"):
                info_text += f"Kurier: {order_data['courier_info']}\n"
            
            # Dodaj numer referencyjny
            if order_data.get("reference_number"):
                info_text += f"Nr ref.: {order_data['reference_number']}\n"
            
            # Dodaj informacje o nadawcy
            if order_data.get("sender_info"):
                info_text += f"Nadawca: {order_data['sender_info']}\n"
            
            # Zapisz w kolumnie N
            if info_text:
                # Najpierw pobierz stare info, żeby nie nadpisać historii (opcjonalne, ale bezpieczne)
                # current_info = self.sheets_handler.worksheet.cell(row, Col.INFO).value or ""
                # new_info = f"{current_info}\n{info_text}".strip()
                self.sheets_handler.worksheet.update_cell(row, Col.INFO, info_text.strip())
            
            # Zastosuj kolorowanie (Zakres A do P)
            self.sheets_handler.worksheet.format(f"A{row}:{Col.LAST_COL_LETTER}{row}", {
                "backgroundColor": self.colors["transit"],
                "textFormat": {"foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0}}
            })
            
            logging.info(f"✅ Zaktualizowano wiersz {row} dla paczki DPD w transporcie")
            return True
        except Exception as e:
            logging.error(f"Błąd podczas aktualizacji paczki DPD w transporcie: {e}")
            return False
    
    def create_pickup_row(self, order_data):
            """Tworzy nowy wiersz dla przesyłki DPD gotowej do odbioru"""
            try:
                # Przygotuj dane wiersza
                email = order_data.get("email", "")
                if not email and order_data.get("user_key"):
                    email = f"{order_data['user_key']}@gmail.com"
                
                delivery_address = order_data.get("delivery_address", "")
                
                # Informacje o kurierze
                courier_info = ""
                if order_data.get("courier_info"):
                    courier_info = order_data["courier_info"]
                elif order_data.get("courier_name") or order_data.get("courier_phone"):
                    info_parts = []
                    if order_data.get("courier_name"):
                        info_parts.append(f"Kurier: {order_data['courier_name']}")
                    if order_data.get("courier_phone"):
                        info_parts.append(f"Tel: {order_data['courier_phone']}")
                    courier_info = " | ".join(info_parts)
                
                # Dane do wiersza arkusza
                row_data = [
                    email,                                # A - Email
                    "Kurier doręcza",                     # B - Status
                    delivery_address,                     # C - Adres dostawy
                    "",                                   # D - Nr zamówienia AliExpress
                    "",                                   # E - Data zamówienia
                    order_data.get("shipping_date", ""),  # F - Data wysłania
                    "",                                   # G - Nr śledzenia AliExpress
                    "",                                   # H - Produkt
                    "",                                   # I - Cena
                    "",                                   # J - Dostępne emaile
                    "",                                   # K - Uwagi
                    order_data.get("sender", ""),         # L - Nadawca
                    order_data.get("package_number", ""), # M - Nr paczki przewoźnika
                    courier_info,                         # N - Info
                    order_data.get("package_number", "")  # O - Carrier package number
                ]
                
                # Dodaj wiersz do arkusza
                result = self.sheets_handler.worksheet.append_row(row_data)
                
                # Znajdź dodany wiersz
                new_row = result.get("updates", {}).get("updatedRange", "").split("!")[1]
                if new_row:
                    new_row = int(re.search(r'A(\d+)', new_row).group(1))
                    
                    # Zastosuj kolorowanie
                    self.sheets_handler.worksheet.format(f"A{new_row}:N{new_row}", {
                        "backgroundColor": self.colors["pickup"]
                    })
                    
                    logging.info(f"Utworzono nowy wiersz {new_row} dla paczki DPD gotowej do odbioru")
                else:
                    logging.info("Utworzono nowy wiersz dla paczki DPD gotowej do odbioru")
                    
                return True
            except Exception as e:
                logging.error(f"Błąd podczas tworzenia wiersza dla paczki DPD: {e}")
                return False  
                  
    def create_transit_row(self, order_data):
        """Tworzy nowy wiersz dla paczki DPD w transporcie"""
        try:
            # Pobierz dane
            email = order_data.get("customer_name", "")
            if not email and order_data.get("user_key"):
                email = f"{order_data['user_key']}@gmail.com"
            
            # Przygotuj adres dostawy
            delivery_address = ""
            if order_data.get("delivery_address"):
                # Obsługa zagnieżdzonego formatu adresu
                if isinstance(order_data["delivery_address"], dict):
                    address_obj = order_data["delivery_address"]
                    address_parts = []
                    
                    if "street" in address_obj:
                        address_parts.append(address_obj["street"])
                    if "postal_code" in address_obj:
                        address_parts.append(address_obj["postal_code"])
                    if "city" in address_obj:
                        address_parts.append(address_obj["city"])
                    if "country" in address_obj:
                        address_parts.append(address_obj["country"])
                    
                    delivery_address = ", ".join(address_parts)
                else:
                    delivery_address = order_data["delivery_address"]
            
            # Przygotuj dane wiersza
            row_data = [
                email,  # A: email
                "Nieznany",  # B: product name
                delivery_address,  # C: delivery address
                order_data.get("phone_number", ""),  # D: phone number
                "",  # E: pickup code (n/a for DPD)
                "",  # F: time to pickup (n/a for DPD)
                "",  # G: available hours (n/a for DPD)
                order_data.get("reference_number", ""),  # H: order/reference number
                f"W transporcie (DPD)",  # I: status
                email,  # J: available emails
                "",  # K: aliexpress link
                "",  # L: QR code (n/a for DPD)
                order_data.get("package_number", "")  # M: package number
            ]
            
            # Dodaj wiersz
            values = self.sheets_handler.worksheet.get_all_values()
            next_row = len(values) + 1
            cell_range = f"A{next_row}:M{next_row}"
            self.sheets_handler.worksheet.update(cell_range, [row_data])
            
            # Dodaj informacje do kolumny INFO (N)
            info_text = ""
            
            # Dodaj informacje o kurierze
            if order_data.get("courier_info"):
                info_text += f"Kurier: {order_data['courier_info']}\n"
            
            # Dodaj numer referencyjny
            if order_data.get("reference_number"):
                info_text += f"Nr ref.: {order_data['reference_number']}\n"
            
            # Dodaj informacje o nadawcy
            if order_data.get("sender_info"):
                info_text += f"Nadawca: {order_data['sender_info']}\n"
            
            # Zapisz informacje w kolumnie INFO
            if info_text:
                self.sheets_handler.worksheet.update_cell(next_row, 14, info_text.strip())
            
            # Zastosuj kolor
            self.sheets_handler.worksheet.format(f"A{next_row}:N{next_row}", {
                "backgroundColor": self.colors["transit"]
            })
            
            logging.info(f"Utworzono nowy wiersz {next_row} dla paczki DPD w transporcie")
            return True
        except Exception as e:
            logging.error(f"Błąd podczas tworzenia wiersza dla paczki DPD: {e}")
            return False
        
        # Rozszerz istniejącą metodę _find_row_by_tracking w BaseCarrier lub dodaj do DPDCarrier
    def _find_row_by_tracking(self, package_number):
        """Znajduje wiersz z podanym numerem przesyłki"""
        try:
            all_data = self.sheets_handler.worksheet.get_all_values()
            tracking_col = 3  # Kolumna D = indeks 3
            package_col = 12  # Kolumna M = indeks 12
            
            # Szukaj wiersza z numerem przesyłki
            for i, row in enumerate(all_data):
                if i == 0:  # Pomijamy nagłówek
                    continue
                    
                # Sprawdź czy numer przesyłki znajduje się w kolumnie D lub M
                if (row[tracking_col] and package_number in row[tracking_col]) or \
                   (row[package_col] and package_number in row[package_col]):
                    return i + 1  # Numery wierszy w API są 1-based
            
            return None
            
        except Exception as e:
            logging.error(f"Błąd podczas szukania wiersza z numerem przesyłki: {e}")
            return None


        # Dodaj metodę update_shipment_sent do DPDCarrier
    def update_shipment_sent(self, row, order_data):
        """Aktualizuje status przesyłki na 'Przesyłka nadana'"""
        try:
            # Aktualizuj status
            self.sheets_handler.worksheet.update_cell(row, 9, "Przesyłka nadana (DPD)")
            
            # Zapisz numer paczki
            if order_data.get("package_number"):
                self.sheets_handler.worksheet.update_cell(row, 13, order_data["package_number"])
            
            # Zastosuj kolor
            self.sheets_handler.worksheet.format(f"A{row}:N{row}", {
                "backgroundColor": self.colors["transit"]  # Użyj istniejącego koloru dla transit
            })
            
            logging.info(f"Zaktualizowano wiersz {row} dla paczki DPD - przesyłka nadana")
            return True
        except Exception as e:
            logging.error(f"Błąd podczas aktualizacji paczki DPD - przesyłka nadana: {e}")
            return False


    def create_delivered_row(self, order_data):
        """Tworzy nowy wiersz dla paczki DPD dostarczonej"""
        try:
            # Przygotuj dane wiersza
            email = order_data.get("email", "")
            if not email and order_data.get("user_key"):
                email = f"{order_data['user_key']}@gmail.com"
            
            delivery_address = order_data.get("delivery_address", "")
            
            # Dane do wiersza arkusza
            row_data = [
                email,                                # A - Email
                "Dostarczona",                        # B - Status
                delivery_address,                     # C - Adres dostawy
                "",                                   # D - Nr zamówienia
                "",                                   # E - Data zamówienia
                order_data.get("delivery_date", ""),  # F - Data dostarczenia
                "",                                   # G - Nr śledzenia AliExpress
                "",                                   # H - Produkt
                "",                                   # I - Cena
                "",                                   # J - Dostępne emaile
                "",                                   # K - Uwagi
                order_data.get("sender", ""),         # L - Nadawca
                order_data.get("package_number", ""), # M - Nr paczki przewoźnika
                "",                                   # N - Info
                order_data.get("package_number", "")  # O - Carrier package number
            ]
            
            # Dodaj wiersz do arkusza
            result = self.sheets_handler.worksheet.append_row(row_data)
            
            # Znajdź dodany wiersz
            new_row = result.get("updates", {}).get("updatedRange", "").split("!")[1]
            if new_row:
                new_row = int(re.search(r'A(\d+)', new_row).group(1))
                
                # Zastosuj kolorowanie
                self.sheets_handler.worksheet.format(f"A{new_row}:N{new_row}", {
                    "backgroundColor": self.colors["delivered"]
                })
                
                logging.info(f"Utworzono nowy wiersz {new_row} dla paczki DPD dostarczonej")
            else:
                logging.info("Utworzono nowy wiersz dla paczki DPD dostarczonej")
                
            return True
        except Exception as e:
            logging.error(f"Błąd podczas tworzenia wiersza dla paczki DPD dostarczonej: {e}")
            return False
    
class DHLCarrier(BaseCarrier):
    """Obsługa aktualizacji statusów paczek DHL"""
    
    def __init__(self, sheets_handler):
        super().__init__(sheets_handler)
        self.name = "DHL"
        # DHL - ŻÓŁTE ODCIENIE
        self.colors = {
            "shipment_sent": {"red": 1.0, "green": 1.0, "blue": 0.8},   # Jasny żółty - nadano
            "pickup": {"red": 1.0, "green": 0.9, "blue": 0.0},          # Ciemny żółty - gotowe do odbioru
            "delivered": {"red": 0.5, "green": 0.9, "blue": 0.8}        # Turkusowy - dostarczone
        }
    
    def update_shipment_sent(self, row, order_data):
        """Aktualizuje status przesyłki na 'Przesyłka nadana'"""
        try:
            # Aktualizuj status
            self.sheets_handler.worksheet.update_cell(row, 9, "Przesyłka nadana (DHL)")
            
            # Możemy też zaktualizować przewidywaną datę dostawy
            if order_data.get("expected_delivery_date"):
                self.sheets_handler.worksheet.update_cell(row, 6, order_data["expected_delivery_date"])
            
            # Zastosuj formatowanie
            self._apply_row_formatting(row, "shipment_sent")
            logging.info(f"Zaktualizowano status przesyłki na 'Przesyłka nadana' w wierszu {row}")
            return True
            
        except Exception as e:
            logging.error(f"Błąd podczas aktualizacji statusu przesyłki: {e}")
            return False
    
    def update_pickup(self, row, order_data):
        """Aktualizuje status przesyłki na 'Gotowa do odbioru'"""
        try:
            # Aktualizuj status
            self.sheets_handler.worksheet.update_cell(row, 9, "Gotowa do odbioru (DHL)")
            
            # Aktualizuj kod odbioru (PIN)
            if order_data.get("pickup_code"):
                self.sheets_handler.worksheet.update_cell(row, 5, order_data["pickup_code"])
            
            # Aktualizuj termin odbioru
            if order_data.get("pickup_deadline"):
                self.sheets_handler.worksheet.update_cell(row, 6, order_data["pickup_deadline"])
            
            # Aktualizuj godziny dostępności
            if order_data.get("available_hours"):
                self.sheets_handler.worksheet.update_cell(row, 7, order_data["available_hours"])
            
            # Aktualizuj adres odbioru
            if order_data.get("pickup_location"):
                self.sheets_handler.worksheet.update_cell(row, 3, order_data["pickup_location"])
            
            # Zastosuj formatowanie
            self._apply_row_formatting(row, "pickup")
            logging.info(f"Zaktualizowano status przesyłki na 'Gotowa do odbioru' w wierszu {row}")
            return True
        
        except Exception as e:
            logging.error(f"Błąd podczas aktualizacji statusu przesyłki do odbioru: {e}")
            return False
    
    def update_delivered(self, row, order_data):
        """Aktualizuje status przesyłki na 'Dostarczona'"""
        try:
            # Aktualizuj status
            self.sheets_handler.worksheet.update_cell(row, 9, "Dostarczona (DHL)")
            
            # Aktualizuj datę dostarczenia
            if order_data.get("delivery_date"):
                self.sheets_handler.worksheet.update_cell(row, 6, order_data["delivery_date"])
                
            # Zastosuj formatowanie
            self._apply_row_formatting(row, "delivered")
            logging.info(f"Zaktualizowano status przesyłki na 'Dostarczona' w wierszu {row}")
            return True
            
        except Exception as e:
            logging.error(f"Błąd podczas aktualizacji statusu przesyłki: {e}")
            return False
    
    def create_shipment_row(self, order_data):
        """Tworzy nowy wiersz dla nadanej przesyłki"""
        try:
            # Przygotuj dane
            package_number = order_data.get("package_number", "")
            secondary_tracking = order_data.get("secondary_package_number", "")
            if secondary_tracking:
                package_number = f"{package_number} ({secondary_tracking})"
                
            expected_delivery = order_data.get("expected_delivery_date", "")
            sender = order_data.get("sender", "")
            
            # Pobierz email z user_key
            email = order_data.get("email")
            if not email and order_data.get("user_key"):
                email = f"{order_data['user_key']}@gmail.com"
            
            # Przygotuj dane wiersza
            row_data = [
                order_data.get("user_key", ""),  # A: email
                "",                             # B: product name
                order_data.get("pickup_location", ""),  # C: delivery address
                package_number,                # D: tracking number
                "",                             # E: pickup code
                expected_delivery,              # F: time to pickup/delivery
                "",                             # G: available hours
                sender,                         # H: order number / sender
                f"Przesyłka nadana (DHL)",      # I: status
                email,                          # J: available emails
                "",                             # K: link
                "",                             # L: QR code
                package_number                 # M: package number
            ]
            
            # Dodaj wiersz
            values = self.sheets_handler.worksheet.get_all_values()
            next_row = len(values) + 1
            cell_range = f"A{next_row}:M{next_row}"
            self.sheets_handler.worksheet.update(cell_range, [row_data])
            
            # Zastosuj formatowanie
            self._apply_row_formatting(next_row, "shipment_sent")
            
            logging.info(f"Utworzono nowy wiersz {next_row} dla przesyłki nadanej przez DHL")
            return True
            
        except Exception as e:
            logging.error(f"Błąd podczas tworzenia wiersza dla przesyłki: {e}")
            return False
    
    def create_pickup_row(self, order_data):
        """Tworzy nowy wiersz dla przesyłki gotowej do odbioru"""
        try:
            # Przygotuj dane
            package_number = order_data.get("package_number", "")
            secondary_tracking = order_data.get("secondary_package_number", "")
            if secondary_tracking:
                package_number = f"{package_number} ({secondary_tracking})"
                
            pickup_code = order_data.get("pickup_code", "")
            pickup_deadline = order_data.get("pickup_deadline", "")
            available_hours = order_data.get("available_hours", "")
            pickup_location = order_data.get("pickup_location", "")
            sender = order_data.get("sender", "")
            
            # Pobierz email z user_key
            email = order_data.get("email")
            if not email and order_data.get("user_key"):
                email = f"{order_data['user_key']}@gmail.com"
            
            # Przygotuj dane wiersza
            row_data = [
                order_data.get("user_key", ""),  # A: email
                "",                             # B: product name
                pickup_location,                # C: pickup location
                package_number,                # D: tracking number
                pickup_code,                    # E: pickup code
                pickup_deadline,                # F: time to pickup
                available_hours,                # G: available hours
                sender,                         # H: order number / sender
                f"Gotowa do odbioru (DHL)",     # I: status
                email,                          # J: available emails
                "",                             # K: link
                "",                             # L: QR code
                package_number                 # M: package number
            ]
            
            # Dodaj wiersz
            values = self.sheets_handler.worksheet.get_all_values()
            next_row = len(values) + 1
            cell_range = f"A{next_row}:M{next_row}"
            self.sheets_handler.worksheet.update(cell_range, [row_data])
            
            # Zastosuj formatowanie
            self._apply_row_formatting(next_row, "pickup")
            
            logging.info(f"Utworzono nowy wiersz {next_row} dla paczki DHL gotowej do odbioru")
            
            # Wyślij powiadomienie o paczce gotowej do odbioru
            try:
                self._send_pickup_notification(order_data, next_row)
                print(f"Wysłano powiadomienie o paczce {package_number}")
            except Exception as e:
                logging.error(f"Błąd podczas wysyłania powiadomienia: {e}")
            
            return True
            
        except Exception as e:
            logging.error(f"Błąd podczas tworzenia wiersza dla paczki do odbioru: {e}")
            return False
    
    def _apply_row_formatting(self, row, status_type):
        """Stosuje formatowanie do wiersza na podstawie statusu"""
        try:
            color = self.colors.get(status_type, self.colors["transit"])
            self.sheets_handler.worksheet.format(f"A{row}:N{row}", {
                "backgroundColor": color
            })
            logging.info(f"Zastosowano kolor dla wiersza {row} (status: {status_type}, przewoźnik: {self.name})")
        except Exception as e:
            logging.error(f"Błąd podczas formatowania wiersza: {e}")
    
    def _send_pickup_notification(self, order_data, row):
        """Wysyła powiadomienie o paczce gotowej do odbioru"""
        try:
            package_number = order_data.get("package_number", "")
            if package_number:
                print(f"Wysłano powiadomienie o paczce {package_number}")
            return True
        except Exception as e:
            logging.error(f"Błąd podczas wysyłania powiadomienia: {e}")
            return False
    
       
    def _find_row_by_tracking(self, package_number):
        """Znajduje wiersz z podanym numerem przesyłki"""
        try:
            all_data = self.sheets_handler.worksheet.get_all_values()
            tracking_col = 3  # Kolumna D = indeks 3
            
            # Szukaj wiersza z numerem przesyłki
            for i, row in enumerate(all_data):
                if i == 0:  # Pomijamy nagłówek
                    continue
                    
                # Sprawdź czy numer przesyłki (JJD) zawiera się w komórce (może być format JJD + numer w nawiasie)
                if row[tracking_col] and package_number in row[tracking_col]:
                    return i + 1  # Numery wierszy w API są 1-based
            
            return None
            
        except Exception as e:
            logging.error(f"Błąd podczas szukania wiersza z numerem przesyłki: {e}")
            return None

class AliExpressCarrier(BaseCarrier):
    """Klasa obsługująca przewoźnika AliExpress/Cainiao"""
    
    def __init__(self, sheets_handler):
        super().__init__(sheets_handler)
        self.name = "AliExpress"
        # ALIEXPRESS - POMARAŃCZOWE ODCIENIE
        self.colors = {
            "confirmed": {"red": 1.0, "green": 0.9, "blue": 0.8},      # Jasny pomarańczowy
            "transit": {"red": 1.0, "green": 0.7, "blue": 0.4},       # Ciemny pomarańczowy
            "shipment_sent": {"red": 1.0, "green": 0.9, "blue": 0.8}, # Jasny pomarańczowy
            "pickup": {"red": 1.0, "green": 0.7, "blue": 0.4},       # Ciemny pomarańczowy
            "pickup": {"red": 1.0, "green": 0.7, "blue": 0.4}, # Ciemny pomarańczowy
            "delivered": {"red": 0.5, "green": 0.9, "blue": 0.8},    # Turkusowy (dostarczenie)
            "closed": {"red": 1.0, "green": 0.2, "blue": 0.2}  # ⚠️ SPRAWDŹ CZY TA LINIA ISTNIEJE

        }
    def update_transit(self, row, order_data):
        """Aktualizuje wiersz dla paczki AliExpress w transporcie"""
        try:
            # Aktualizuj status (Kolumna I)
            status = "W transporcie (AliExpress)"
            self.sheets_handler.worksheet.update_cell(row, Col.STATUS, status)
            
            # Zapisz numer zamówienia (Kolumna M)
            if order_data.get("order_number"):
                self.sheets_handler.worksheet.update_cell(row, Col.ORDER_NUM, f"'{order_data['order_number']}")
            
            # Zapisz numer paczki (Kolumna O)
            if order_data.get("package_number"):
                self.sheets_handler.worksheet.update_cell(row, Col.PKG_NUM, f"'{order_data['package_number']}")
            
            # Zapisz nazwę produktu (Kolumna B)
            if order_data.get("product_name"):
                self.sheets_handler.worksheet.update_cell(row, Col.PRODUCT, order_data["product_name"])
            
            # ✅ POPRAWKA: Zapisz link w kolumnie P (zamiast K, która jest na datę dostawy)
            if order_data.get("item_link"):
                self.sheets_handler.worksheet.update_cell(row, Col.LINK, order_data["item_link"])
            
            # Zastosuj kolorowanie (Zakres A do P)
            self.sheets_handler.worksheet.format(f"A{row}:{Col.LAST_COL_LETTER}{row}", {
                "backgroundColor": self.colors["transit"],
                "textFormat": {"foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0}}
            })
            
            logging.info(f"✅ Zaktualizowano wiersz {row} dla paczki AliExpress w transporcie (Link w kolumnie P)")
            return True
        except Exception as e:
            logging.error(f"Błąd podczas aktualizacji paczki AliExpress w transporcie: {e}")
            return False
    
    def create_transit_row(self, order_data):
        """Tworzy nowy wiersz dla paczki AliExpress w transporcie"""
        try:
            # Pobierz dane
            email = order_data.get("customer_name", "")
            if not email and order_data.get("user_key"):
                email = f"{order_data['user_key']}@gmail.com"
            
            # Przygotuj dane wiersza
            row_data = [
                email,  # A: email
                order_data.get("product_name", "Nieznany"),  # B: product name
                order_data.get("delivery_address", ""),  # C: delivery address
                order_data.get("phone_number", ""),  # D: phone number
                "",  # E: pickup code (n/a for AliExpress transit)
                "",  # F: delivery date (empty for now)
                "",  # G: available hours (n/a for AliExpress transit)
                order_data.get("order_number", ""),  # H: order number
                f"W transporcie (AliExpress)",  # I: status
                email,  # J: available emails
                order_data.get("item_link", ""),  # K: aliexpress link
                "",  # L: QR code (n/a for AliExpress transit)
                order_data.get("package_number", "")  # M: package number
            ]
            
            # Dodaj wiersz
            values = self.sheets_handler.worksheet.get_all_values()
            next_row = len(values) + 1
            cell_range = f"A{next_row}:M{next_row}"
            self.sheets_handler.worksheet.update(cell_range, [row_data])
            
            # Zastosuj kolor
            self.sheets_handler.worksheet.format(f"A{next_row}:N{next_row}", {
                "backgroundColor": self.colors["transit"]
            })
            
            logging.info(f"Utworzono nowy wiersz {next_row} dla paczki AliExpress w transporcie")
            return True
        except Exception as e:
            logging.error(f"Błąd podczas tworzenia wiersza dla paczki AliExpress: {e}")
            return False

class ShippingManager:
    """Klasa zarządzająca wysyłkami"""

    def __init__(self, spreadsheet):
        self.spreadsheet = spreadsheet

    def get_carrier(self, order_data):
        """Zwraca odpowiednią instancję przewoźnika na podstawie danych zamówienia"""
        if not order_data:
            return None
            
        carrier_name = order_data.get("carrier", "").lower()
        
        if "aliexpress" in carrier_name or "cainiao" in carrier_name:
            return AliExpressCarrier(self.spreadsheet)
        elif "inpost" in carrier_name:
            return InPostCarrier(self.spreadsheet)
        elif "dhl" in carrier_name:
            return DHLCarrier(self.spreadsheet)
        else:
            logging.warning(f"Nieobsługiwany przewoźnik: {carrier_name}")
            return None

# W pliku carriers_sheet_handlers.py (na końcu)

class EmailAvailabilityManager:
    """Zarządza zakładką 'Accounts'"""
    
    def __init__(self, sheets_handler):
        self.sheets_handler = sheets_handler
        self.worksheet = None
        self._init_accounts_worksheet()

    def _init_accounts_worksheet(self):
        """Próbuje połączyć się z zakładką Accounts"""
        try:
            self.worksheet = self.sheets_handler.spreadsheet.worksheet("Accounts")
        except:
            logging.warning("Nie znaleziono zakładki 'Accounts'.")
            self.worksheet = None

    def get_emails_from_accounts_sheet(self):
        """
        Pobiera listę emaili z zakładki Accounts wraz z hasłami.
        Zwraca listę słowników z pełną konfiguracją.
        """
        if not self.worksheet:
            self._init_accounts_worksheet()
            if not self.worksheet:
                return []
            
        try:
            import config
            
            # Pobierz wszystkie dane z arkusza
            accounts_data = self.worksheet.get_all_values()
            
            if len(accounts_data) <= 1:
                logging.warning("⚠️ Zakładka Accounts jest pusta (tylko nagłówek)")
                return []
            
            email_configs = []
            
            # Struktura: A=Email, B=Status, C=Password, D=Notatki (Ignorowane)
            for i, row in enumerate(accounts_data[1:], start=2):
                try:
                    if len(row) < 1:
                        continue
                    
                    account_email = row[0].strip() if row[0] else ""
                    if not account_email:
                        continue
                    
                    # Status (kolumna B)
                    status = row[1].strip().lower() if len(row) > 1 and row[1] else "active"
                    
                    # Pomijaj nieaktywne
                    if status in ['inactive', 'delivered', 'stopped', 'paused']:
                        logging.info(f"⏭️ Email {account_email} ma status '{status}' - pomijam")
                        continue
                    
                    # Hasło (kolumna C)
                    password = config.DEFAULT_EMAIL_PASSWORD
                    
                    source = "" 
                    
                    # ✅ AUTO-DETEKCJA ŹRÓDŁA (Teraz wykona się ZAWSZE)
                    if not source:
                        if '@gmail.com' in account_email.lower():
                            source = 'gmail'
                        elif '@interia.pl' in account_email.lower() or '@poczta.fm' in account_email.lower():
                            source = 'interia'
                        elif '@o2.pl' in account_email.lower() or '@tlen.pl' in account_email.lower():
                            source = 'o2'
                        else:
                            # Domyślnie gmail (bezpieczny fallback)
                            logging.warning(f"⚠️ Nie można określić źródła dla {account_email}, używam 'gmail'")
                            source = 'gmail'
                        
                        # (Opcjonalnie: mniej logowania, żeby nie śmiecić przy każdym sprawdzeniu)
                        # logging.info(f"🔍 Auto-wykryto źródło '{source}' dla {email}")
                    
                    # ✅ HASŁO - HIERARCHIA
                    if not password:
                        # 1. Sprawdź EMAIL_PASSWORDS_MAP
                        if hasattr(config, 'EMAIL_PASSWORDS_MAP') and account_email in config.EMAIL_PASSWORDS_MAP:
                            password = config.EMAIL_PASSWORDS_MAP[account_email]
                        # 2. Użyj DEFAULT_EMAIL_PASSWORD
                        elif hasattr(config, 'DEFAULT_EMAIL_PASSWORD') and config.DEFAULT_EMAIL_PASSWORD:
                            password = config.DEFAULT_EMAIL_PASSWORD
                        else:
                            logging.warning(f"⚠️ Brak hasła dla {account_email} - pomijam")
                            continue
                    
                    # Dodaj do listy
                    email_config = {
                        'email': account_email,
                        'password': password,
                        'source': source,
                        'status': status
                    }
                    
                    email_configs.append(email_config)
                    
                except Exception as e:
                    logging.error(f"❌ Błąd przetwarzania wiersza {i}: {e}")
                    continue
            
            logging.info(f"📧 Znaleziono {len(email_configs)} aktywnych emaili w Accounts")
            return email_configs
            
        except Exception as e:
            logging.error(f"❌ Błąd pobierania emaili z Accounts: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return []

    # W pliku carriers_sheet_handlers.py wewnątrz klasy EmailAvailabilityManager
    def check_email_availability(self):
        """
        Sprawdza plik user_mappings.json i aktualizuje statusy oraz kolory w arkuszu Accounts.
        Używa CZYSTEGO gspread (bez gspread-formatting).
        """
        import json
        import os
        
        logging.info("🎨 Aktualizacja kolorów i statusów w arkuszu Accounts...")

        # 1. Wczytaj aktualne mapowania (kto jest zajęty)
        active_emails = []
        mappings_file = "user_mappings.json"
        
        if os.path.exists(mappings_file):
            try:
                with open(mappings_file, 'r', encoding='utf-8') as f:
                    mappings = json.load(f)
                    for key in mappings.keys():
                        active_emails.append(key.lower())
            except Exception as e:
                logging.error(f"Błąd odczytu mapowań: {e}")

        try:
            # 2. Pobierz arkusz
            if hasattr(self.sheets_handler, 'worksheet'):
                sheet = self.sheets_handler.worksheet.spreadsheet.worksheet("Accounts")
            else:
                sheet = self.sheets_handler.workbook.worksheet("Accounts")

            # 3. Pobierz wszystkie dane
            all_values = sheet.get_all_values()
            
            # Definicje kolorów (zwykłe słowniki)
            red_format = {
                "backgroundColor": {"red": 1.0, "green": 0.8, "blue": 0.8}
            }
            white_format = {
                "backgroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}
            }
            
            # Pomijamy nagłówek (start od indeksu 1 -> wiersz 2)
            for i, row in enumerate(all_values[1:], start=2):
                if not row: continue
                
                email_in_sheet = str(row[0]).strip().lower()
                login_part = email_in_sheet.split('@')[0]
                
                is_active = (email_in_sheet in active_emails) or (login_part in active_emails)
                
                current_status = row[1] if len(row) > 1 else ""
                
                if is_active:
                    # Jeśli zajęty, a status jest inny niż "-", zaktualizuj tekst
                    if current_status != "-":
                        sheet.update_cell(i, 2, "-")
                    
                    # ✅ Używamy natywnej metody .format() z gspread
                    # To może chwilę potrwać przy wielu kontach, ale jest bezpieczne
                    try:
                        sheet.format(f"A{i}:B{i}", red_format)
                    except Exception:
                        pass # Ignoruj błędy formatowania, to tylko kosmetyka

                else:
                    # Jeśli wolny, a status jest inny niż "wolny", zaktualizuj tekst
                    if current_status != "wolny":
                        sheet.update_cell(i, 2, "wolny")
                    
                    # ✅ Kolorowanie na biało
                    try:
                        sheet.format(f"A{i}:B{i}", white_format)
                    except Exception:
                        pass

            logging.info("✅ Zakończono aktualizację statusów w Accounts.")

        except Exception as e:
            logging.error(f"❌ Błąd w check_email_availability: {e}")

    def free_up_account(self, email):
        """
        Konto jest jednorazowe! Usuwa wiersz z arkusza Accounts.
        Wersja NIEWRAŻLIWA NA WIELKOŚĆ LITER (Pacek == pacek).
        """
        # ✅ ZMIANA 1: Zamień email wejściowy na małe litery
        clean_email = str(email).strip().lower()
        
        logging.info(f"💣 [DEBUG] START free_up_account: Próba usunięcia konta: '{clean_email}' (znormalizowane)")

        try:
            # 1. Znajdź arkusz Accounts
            accounts_sheet = None
            try:
                if hasattr(self.sheets_handler, 'worksheet'):
                    accounts_sheet = self.sheets_handler.worksheet.spreadsheet.worksheet("Accounts")
                elif hasattr(self.sheets_handler, 'spreadsheet'):
                    accounts_sheet = self.sheets_handler.spreadsheet.worksheet("Accounts")
                else:
                    accounts_sheet = self.sheets_handler.workbook.worksheet("Accounts")
                
                logging.info("✅ [DEBUG] Arkusz 'Accounts' załadowany.")
            except Exception as e:
                logging.error(f"❌ [DEBUG] Nie udało się pobrać arkusza 'Accounts': {e}")
                return

            # 2. Pobierz całą kolumnę A i szukaj ręcznie (najpewniejsza metoda przy problemach z wielkością liter)
            logging.info(f"🔍 [DEBUG] Pobieram kolumnę A i szukam '{clean_email}' ignorując wielkość liter...")
            
            try:
                col_values = accounts_sheet.col_values(1)
                found = False
                
                # Iterujemy po wierszach sprawdzając każdy
                for idx, val in enumerate(col_values):
                    # ✅ ZMIANA 2: Porównujemy wszystko jako małe litery
                    current_val = str(val).strip().lower()
                    
                    if current_val == clean_email:
                        row = idx + 1 # Gspread liczy wiersze od 1
                        logging.info(f"📍 [DEBUG] ZNALAZŁEM! '{current_val}' pasuje do '{clean_email}' w wierszu {row}")
                        
                        logging.info(f"🗑️ [DEBUG] Usuwam wiersz {row}...")
                        accounts_sheet.delete_rows(row)
                        logging.info(f"✅ [DEBUG] SUKCES: Wiersz {row} usunięty. Konto skasowane.")
                        found = True
                        break
                
                if not found:
                    logging.warning(f"⚠️ [DEBUG] Nie znaleziono emaila '{clean_email}' w arkuszu (sprawdzono {len(col_values)} wierszy).")
                    # Wypisz dla pewności co tam jest
                    if len(col_values) > 0:
                        logging.info(f"👀 Przykładowe wartości w arkuszu: {col_values[:5]}")

            except Exception as search_err:
                logging.error(f"❌ [DEBUG] Błąd podczas przeszukiwania kolumny: {search_err}")

        except Exception as e:
            logging.error(f"❌ [DEBUG] Krytyczny błąd w free_up_account: {e}")
            import traceback
            logging.error(traceback.format_exc())

        try:
            logging.info("🔍 Sprawdzanie dostępności maili w zakładce Accounts...")
            
            # 1. Pobierz aktywne zamówienia z głównego arkusza
            # Upewnij się, że pobieramy z dobrego arkusza (zconfigurowanego w SheetsHandler)
            main_sheet = self.sheets_handler.worksheet
            all_orders = main_sheet.get_all_values()
            
            # Zbiór zajętych maili (mają aktywne zamówienie)
            busy_emails = set()
            
            # Statusy, które oznaczają, że zamówienie jest ZAKOŃCZONE (email wolny)
            finished_statuses = [
                "delivered", "dostarczona", "dostarczono", 
                "odebrana", "zwrócona", "anulowana", "canceled", "closed"
            ]
            
            # Przeiteruj przez zamówienia (pomiń nagłówek)
            for row in all_orders[1:]:
                # Sprawdź czy wiersz ma wystarczająco kolumn
                # Email jest w kolumnie A (indeks 0), Status w kolumnie I (indeks 8)
                if len(row) > 0:
                    email_raw = row[0]
                    # Status może być pusty, wtedy traktujemy jako aktywne
                    status_raw = row[8] if len(row) > 8 else ""
                    
                    if email_raw:
                        email = email_raw.strip().lower()
                        status = status_raw.strip().lower()
                        
                        # Sprawdź czy status oznacza zakończenie
                        is_finished = any(s in status for s in finished_statuses)
                        
                        if not is_finished:
                            # Jeśli nie zakończone = email zajęty
                            busy_emails.add(email)

            logging.info(f"📧 Znaleziono {len(busy_emails)} zajętych emaili: {list(busy_emails)}")

            # 2. Zaktualizuj zakładkę Accounts
            accounts_data = self.worksheet.get_all_values()
            
            # Przygotuj listę update'ów (dla wydajności)
            updates = []
            
            for i, row in enumerate(accounts_data[1:], start=2): # start=2 bo wiersz 1 to nagłówek
                if not row: continue
                
                # Pobierz email z kolumny A (indeks 0)
                email_raw = row[0] if len(row) > 0 else ""
                
                if not email_raw: continue
                
                email = email_raw.strip().lower()
                is_busy = email in busy_emails
                
                status_text = "-" if is_busy else "wolny"
                
                # Aktualizuj kolumnę B (Status - indeks 2 w API gspread, bo 1-based)
                self.worksheet.update_cell(i, 2, status_text)
                
                # Kolorowanie (Czerwony=Zajęty, Zielony=Wolny)
                # Czerwony dla zajętych, Biały/Zielony dla wolnych
                if is_busy:
                     color = {"red": 1.0, "green": 0.8, "blue": 0.8} # Czerwony
                else:
                     color = {"red": 1.0, "green": 1.0, "blue": 1.0} # Biały (domyślny)
                
                self.worksheet.format(f"A{i}:B{i}", {
                    "backgroundColor": color
                })
                
            logging.info(f"✅ Zaktualizowano statusy w Accounts.")
                
        except Exception as e:
            logging.error(f"Błąd podczas sprawdzania dostępności maili: {e}")
            import traceback
            logging.error(traceback.format_exc())

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
            'closed': {'red': 1.0, 'green': 0.2, 'blue': 0.2}            # ✅ DODANO
        }
    
class DeliveredOrdersManager:
    """Klasa zarządzająca przenoszeniem dostarczonych zamówień do zakładki Delivered"""
    
    def __init__(self, sheets_handler):
        self.sheets_handler = sheets_handler
        self.delivered_worksheet = None
        self._initialized = False
        
        # ✅ INICJALIZUJ OD RAZU
        self._init_delivered_worksheet()
        self._initialized = True
    
    def _ensure_initialized(self):
        """Upewnia się, że zakładka Delivered jest zainicjalizowana"""
        if not self._initialized:
            self._init_delivered_worksheet()
            self._initialized = True
    
    def _init_delivered_worksheet(self):
        """Inicjalizuje dostęp do zakładki Delivered"""
        try:
            # ✅ SPRAWDŹ CZY WORKSHEET JEST DOSTĘPNY
            if not hasattr(self.sheets_handler, 'worksheet') or not self.sheets_handler.worksheet:
                logging.error("❌ SheetsHandler nie ma dostępu do worksheet - pomiń inicjalizację")
                return
                
            # Pobierz spreadsheet z worksheet
            spreadsheet = self.sheets_handler.worksheet.spreadsheet
            
            # Spróbuj znaleźć zakładkę "Delivered"
            try:
                self.delivered_worksheet = spreadsheet.worksheet("Delivered")
                logging.debug("✅ Znaleziono zakładkę 'Delivered'")
            except:
                # Jeśli nie istnieje, utwórz ją
                logging.info("📝 Tworzenie nowej zakładki 'Delivered'...")
                self.delivered_worksheet = spreadsheet.add_worksheet(title="Delivered", rows=1000, cols=16)
                
                # ✅ SKOPIUJ NAGŁÓWKI Z GŁÓWNEGO ARKUSZA
                main_headers = self.sheets_handler.worksheet.row_values(1)
                if main_headers:
                    # Rozszerz nagłówki o dodatkowe kolumny
                    headers = main_headers[:15]  # A-O z głównego arkusza
                    headers.append("Data emaila")  # P
                    
                    self.delivered_worksheet.update("A1:P1", [headers])
                    
                    # Sformatuj nagłówki
                    self.delivered_worksheet.format("A1:P1", {
                        "backgroundColor": {"red": 0.2, "green": 0.7, "blue": 0.2},  # Zielony nagłówek
                        "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}}
                    })
                    
                    logging.info("✅ Utworzono zakładkę 'Delivered' z nagłówkami")
                else:
                    # Domyślne nagłówki jeśli nie można skopiować
                    headers = [
                        "User Key", "Order Number", "Product Name", "Carrier", "Package Number",
                        "Delivery Address", "Phone Number", "Email", "Status", "Pickup Location",
                        "Pickup Deadline", "Pickup Code", "QR Code", "Info", "Customer Name", "Data emaila"
                    ]
                    self.delivered_worksheet.update("A1:P1", [headers])
                    
                    self.delivered_worksheet.format("A1:P1", {
                        "backgroundColor": {"red": 0.2, "green": 0.7, "blue": 0.2},
                        "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}}
                    })
                    
                    logging.info("✅ Utworzono zakładkę 'Delivered' z domyślnymi nagłówkami")
                
        except Exception as e:
            logging.error(f"❌ Błąd podczas inicjalizacji zakładki Delivered: {e}")
            self.delivered_worksheet = None

    def move_delivered_order(self, row_number):
        """
        Przenosi dostarczony wiersz z głównego arkusza do zakładki Delivered
        
        Args:
            row_number: Numer wiersza w głównym arkuszu do przeniesienia
            
        Returns:
            bool: True jeśli przeniesienie się powiodło
        """
        try:
            self._ensure_initialized()
            
            if not self.delivered_worksheet:
                logging.error("❌ Brak dostępu do zakładki Delivered")
                return False
            
            logging.info(f"📦 Przenoszenie dostarczonych zamówień z wiersza {row_number}")
            
            # ✅ POBIERZ DANE Z GŁÓWNEGO ARKUSZA
            row_data = self.sheets_handler.worksheet.row_values(row_number)
            if not row_data:
                logging.warning(f"⚠️ Brak danych w wierszu {row_number}")
                return False
            
            # ✅ ROZSZERZ DANE DO 16 KOLUMN (A-P)
            while len(row_data) < 16:
                row_data.append("")
            
            # ✅ DODAJ DATĘ PRZENIESIENIA JAKO INFO
            delivered_date = datetime.now().strftime("%Y-%m-%d %H:%M")
            if len(row_data) >= 14:  # Kolumna N (Info)
                current_info = row_data[13] if row_data[13] else ""
                row_data[13] = f"{current_info}\nPrzeniesiono: {delivered_date}".strip()
            
            # ✅ ZNAJDŹ PIERWSZY WOLNY WIERSZ W DELIVERED
            delivered_values = self.delivered_worksheet.get_all_values()
            next_delivered_row = len(delivered_values) + 1
            
            # ✅ DODAJ WIERSZ DO DELIVERED
            range_delivered = f"A{next_delivered_row}:P{next_delivered_row}"
            self.delivered_worksheet.update(range_delivered, [row_data])
            
            # ✅ ZASTOSUJ ZIELONE KOLOROWANIE (DELIVERED)
            self.delivered_worksheet.format(f"A{next_delivered_row}:P{next_delivered_row}", {
                "backgroundColor": {"red": 0.5, "green": 0.9, "blue": 0.8}  # Turkusowy jak delivered
            })
            
            logging.info(f"✅ Dodano wiersz do zakładki Delivered (wiersz {next_delivered_row})")
            
            # ✅ USUŃ WIERSZ Z GŁÓWNEGO ARKUSZA
            self.sheets_handler.worksheet.delete_rows(row_number)
            logging.info(f"🗑️ Usunięto wiersz {row_number} z głównego arkusza")
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Błąd podczas przenoszenia zamówienia: {e}")
            return False

    def check_and_move_delivered_orders(self):
        """
        Sprawdza główny arkusz i przenosi wszystkie dostarczone zamówienia
        
        Returns:
            int: Liczba przeniesionych zamówień
        """
        try:
            self._ensure_initialized()
            
            if not self.delivered_worksheet:
                logging.error("❌ Brak dostępu do zakładki Delivered")
                return 0
            
            logging.info("🔍 Sprawdzanie głównego arkusza pod kątem dostarczonych zamówień...")
            
            # ✅ POBIERZ WSZYSTKIE DANE Z GŁÓWNEGO ARKUSZA
            all_data = self.sheets_handler.worksheet.get_all_values()
            if len(all_data) <= 1:
                logging.info("📭 Brak danych w głównym arkuszu")
                return 0
            
            moved_count = 0
            status_col = 8  # Kolumna I (status) = indeks 8
            
            # ✅ STATUSY OZNACZAJĄCE DOSTARCZENIE
            delivered_statuses = [
                "dostarczona", "delivered", "dostarczono",
                "dostarczona (dpd)", "dostarczona (dhl)", 
                "dostarczona (aliexpress)", "dostarczona (inpost)",
                "dostarczono (dpd)", "dostarczono (dhl)",
                "dostarczono (aliexpress)", "dostarczono (inpost)",
                "delivered (dpd)", "delivered (dhl)",
                "delivered (aliexpress)", "delivered (inpost)",
                "paczka dostarczona", "przesyłka dostarczona", "zamówienie dostarczone"
            ]
            
            # ✅ ITERUJ OD KOŃCA ŻEBY UNIKNĄĆ PROBLEMÓW Z USUWANIEM
            for i in range(len(all_data) - 1, 0, -1):  # Od ostatniego do pierwszego (pomijamy nagłówek)
                row = all_data[i]
                current_row_number = i + 1  # +1 bo indeksy zaczynają się od 0
                
                if len(row) > status_col:
                    status = row[status_col].strip().lower()
                    
                    # ✅ SPRAWDŹ CZY STATUS OZNACZA DOSTARCZENIE
                    if any(delivered_status in status for delivered_status in delivered_statuses):
                        logging.info(f"📦 Znaleziono dostarczone zamówienie w wierszu {current_row_number}: '{status}'")
                        
                        # ✅ PRZENIEŚ DO DELIVERED
                        if self.move_delivered_order(current_row_number):
                            moved_count += 1
                            logging.info(f"✅ Przeniesiono zamówienie {moved_count}")
                        else:
                            logging.warning(f"⚠️ Nie udało się przenieść wiersza {current_row_number}")
            
            if moved_count > 0:
                logging.info(f"🎉 Przeniesiono łącznie {moved_count} dostarczonych zamówień do zakładki Delivered")
                
                # ✅ SPRAWDŹ DOSTĘPNOŚĆ MAILI PO PRZENIESIENIU
                try:
                    email_availability_manager = EmailAvailabilityManager(self.sheets_handler)
                    email_availability_manager.check_email_availability()
                    logging.info("✅ Zaktualizowano dostępność maili po przeniesieniu")
                except Exception as e:
                    logging.error(f"❌ Błąd podczas sprawdzania dostępności maili: {e}")
            else:
                logging.info("📭 Brak dostarczonych zamówień do przeniesienia")
            
            return moved_count
            
        except Exception as e:
            logging.error(f"❌ Błąd podczas sprawdzania i przenoszenia zamówień: {e}")
            return 0

    def get_delivered_orders_count(self):
        """Zwraca liczbę zamówień w zakładce Delivered"""
        try:
            self._ensure_initialized()
            
            if not self.delivered_worksheet:
                return 0
                
            values = self.delivered_worksheet.get_all_values()
            return max(0, len(values) - 1)  # -1 bo pomijamy nagłówek
            
        except Exception as e:
            logging.error(f"❌ Błąd podczas liczenia zamówień: {e}")
            return 0
        
    def safe_update_with_retry(self, range_to_update, updates, max_retries=3):
        """
        Bezpieczna aktualizacja arkusza z mechanizmem retry
        
        Args:
            range_to_update: Zakres do aktualizacji (np. "A5:P5")
            updates: Lista wartości do aktualizacji
            max_retries: Maksymalna liczba prób
            
        Returns:
            bool: True jeśli aktualizacja się powiodła
        """
        import time
        
        logging.info(f"🔧 Aktualizuję zakres {range_to_update} z {len(updates)} wartościami")
        
        for attempt in range(max_retries):
            try:
                self.sheets_handler.worksheet.update(range_to_update, [updates])
                logging.info(f"✅ Aktualizacja udana w próbie {attempt + 1}")
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    logging.warning(f"⚠️ Próba {attempt + 1} nie powiodła się: {e}. Ponawiam...")
                    time.sleep(2)
                else:
                    logging.error(f"❌ Wszystkie próby aktualizacji nie powiodły się: {e}")
                    return False
        
        return False

    def safe_apply_formatting(self, row, range_end, status, colors_dict, max_retries=3):
        """
        Bezpieczne zastosowanie kolorowania z mechanizmem retry
        """
        import time
        
        if not status or status not in colors_dict:
            logging.warning(f"⚠️ Brak koloru dla statusu '{status}' w {list(colors_dict.keys())}")
            return False
        
        color_to_apply = colors_dict[status]
        
        for attempt in range(max_retries):
            try:
                # ✅ ZASTOSUJ KOLOR TŁA
                self.sheets_handler.worksheet.format(f"A{row}:{range_end}{row}", {
                    "backgroundColor": color_to_apply
                })
                logging.info(f"✅ Zastosowano formatowanie {status} w wierszu {row}")
                return True
                
            except Exception as e:
                if attempt < max_retries - 1:
                    logging.warning(f"⚠️ Formatowanie próba {attempt + 1} nie powiodła się: {e}")
                    time.sleep(2)
                else:
                    logging.error(f"❌ Formatowanie nie powiodło się: {e}")
                    return False
        
        return False

    def handle_delivered_order_after_update(self, row, status):
        """
        Obsługuje przeniesienie dostarczonego zamówienia do zakładki Delivered po aktualizacji
        
        Args:
            row: Numer wiersza z dostarczonym zamówieniem
            status: Status zamówienia
            
        Returns:
            bool: True jeśli przeniesienie się powiodło lub nie było potrzebne
        """
        if not status or status.lower() not in ["delivered", "dostarczona", "dostarczono"]:
            return False
        
        logging.info(f"📦 Wykryto dostarczone zamówienie w wierszu {row} - przygotowanie do przeniesienia")
        
        try:
            import time
            time.sleep(1)  # Krótka przerwa żeby aktualizacja się sfinalizowała
            
            if self.move_delivered_order(row):
                logging.info(f"✅ Przeniesiono dostarczone zamówienie z wiersza {row} do zakładki Delivered")
                return True
            else:
                logging.warning(f"⚠️ Nie udało się przenieść zamówienia z wiersza {row}")
                return False
                
        except Exception as e:
            logging.error(f"❌ Błąd podczas przenoszenia dostarczonego zamówienia: {e}")
            return False

# Dodaj to na końcu pliku carriers_sheet_handlers.py

class PocztaPolskaCarrier(BaseCarrier):
    """Klasa obsługująca przewoźnika Poczta Polska"""
    
    def __init__(self, sheets_handler):
        super().__init__(sheets_handler)
        self.name = "PocztaPolska"
        # Kolory dla Poczty Polskiej (czerwony brand)
        self.colors = {
            "shipment_sent": {"red": 1.0, "green": 0.9, "blue": 0.9}, # Jasny czerwony
            "pickup": {"red": 1.0, "green": 0.6, "blue": 0.6},       # Czerwony - Awizo/Odbiór
            "delivered": {"red": 0.8, "green": 0.95, "blue": 0.8},    # Zielony
            "transit": {"red": 0.95, "green": 0.9, "blue": 0.9},      # Szarawy
            "closed": {"red": 1.0, "green": 0.2, "blue": 0.2}
        }