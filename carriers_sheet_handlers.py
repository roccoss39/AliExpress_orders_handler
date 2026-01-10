from datetime import datetime
import logging
import re
from config import COLORS

class BaseCarrier:
    """Bazowa klasa dla wszystkich przewoźników"""
    
    def __init__(self, sheets_handler):
        self.sheets_handler = sheets_handler
        self.name = "Unknown"
       # DOMYŚLNE KOLORY - SZARE ODCIENIE
        self.colors = {
            "transit": {"red": 0.9, "green": 0.9, "blue": 0.9},      # Jasny szary
            "shipment_sent": {"red": 0.9, "green": 0.9, "blue": 0.9}, # Jasny szary
            "pickup": {"red": 0.7, "green": 0.7, "blue": 0.7}, # Ciemny szary
            "delivered": {"red": 0.5, "green": 0.9, "blue": 0.8} ,    # Turkusowy (dostarczenie)
            "closed": {"red": 1.0, "green": 0.2, "blue": 0.2}  # CZERWONY
        }
    
    def process_notification(self, order_data):
        """Przetwarzanie powiadomień od przewoźnika i aktualizacja statusu"""

        if not order_data or not order_data.get("status"):
            return False
   
        status = order_data.get("status")
        logging.info(f"Przetwarzanie powiadomienia {self.name} o statusie: {status}")
        # Bezpośrednie przekazanie danych do uniwersalnej funkcji aktualizującej
        return self.general_update_sheet_data(order_data)
    
#     -        status = order_data.get("status")
# -        logging.info(f"Przetwarzanie powiadomienia {self.name} o statusie: {status}")
# -        
# -        # Pobierz package_number 
# -        package_number = order_data.get("package_number")
# -        
# -        # Strategia wyszukiwania wiersza:
# -        # 1. Najpierw po numerze przewoźnika
# -        row = self._find_row_by_carrier_package(package_number) if package_number else None
# -        
# -        # 2. Następnie po numerze AliExpress jeśli dostępny
# -        if not row and package_number:
# -            row = self._find_row_by_tracking(package_number)
# -            
# -        # 3. Jeśli nie znaleziono, próbujemy po adresie email
# -        if not row and order_data.get("email"):
# -            logging.info(f"Nie znaleziono wiersza po numerze przesyłki, próbuję po email: {order_data.get('email')}")
# -            row = self._find_row_by_email(order_data.get("email"))
# -        
# -        # 4. Ostatnia próba po polu customer_name
# -        if not row and order_data.get("customer_name"):
# -            logging.info(f"Próbuję wyszukać po customer_name: {order_data.get('customer_name')}")
# -            row = self._find_row_by_email(order_data.get("customer_name"))
# -        
# -        # Jeśli znaleziono wiersz, zapisz numer paczki przewoźnika w kolumnie O
# -        if row and package_number:
# -            try:
# -                self.sheets_handler.worksheet.update_cell(row, 15, package_number)  # Kolumna O = 15
# -                logging.info(f"Zapisano numer paczki przewoźnika ({package_number}) w wierszu {row}")
# -            except Exception as e:
# -                logging.error(f"Błąd podczas zapisywania numeru paczki przewoźnika: {e}")
# -        
# -        # Obsługa różnych statusów
# -        if status == "shipment_sent":
# -            if row:
# -                return self.update_shipment_sent(row, order_data)
# -            else:
# -                return self.create_transit_row(order_data)
# -        elif status == "transit":
# -            if row:
# -                return self.update_transit(row, order_data)
# -            if row:
# -                return self.update_pickup(row, order_data)
# -            else:
# -                return self.create_pickup_row(order_data)
# -        elif status == "delivered":
# -            if row:
# -                return self.update_delivered(row, order_data)
# -            else:
# -                logging.warning(f"Nie znaleziono wiersza dla przesyłki {package_number} do oznaczenia jako dostarczona")
# -                return False
# -        else:
# -            logging.warning(f"Nieznany status {self.name}: {status}")
# -            return False        else:
# -                return self.create_transit_row(order_data)
# -        elif status == "pickup":
# -            if row:
# -                return self.update_pickup(row, order_data)
# -            else:
# -                return self.create_pickup_row(order_data)
# -        elif status == "delivered":
# -            if row:
# -                return self.update_delivered(row, order_data)
# -            else:
# -                logging.warning(f"Nie znaleziono wiersza dla przesyłki {package_number} do oznaczenia jako dostarczona")
# -                return False
# -        else:
# -            logging.warning(f"Nieznany status {self.name}: {status}")
# -            return False

    
    def update_notification(self, order_data):
        """Aktualizuje dane powiadomienia"""
        pass
    
    def update_transit(self, row, order_data):
        """Aktualizuje wiersz dla paczki w transporcie"""
        try:
            # Aktualizuj status
            status = f"W transporcie ({self.name})"
            self.sheets_handler.worksheet.update_cell(row, 9, status)
            
            # Zapisz numer paczki
            if order_data.get("package_number"):
                self.sheets_handler.worksheet.update_cell(row, 13, order_data["package_number"])
            
            # Zastosuj kolor
            self.sheets_handler.worksheet.format(f"A{row}:N{row}", {
                "backgroundColor": self.colors["transit"]
            })
            
            logging.info(f"Zaktualizowano wiersz {row} dla paczki {self.name} w transporcie")
            return True
        except Exception as e:
            logging.error(f"Błąd podczas aktualizacji paczki {self.name} w transporcie: {e}")
            return False
    
    def _find_row_by_carrier_package(self, carrier_package_number):
            """Znajduje wiersz na podstawie numeru paczki przewoźnika (kolumna O)"""
            try:
                if not carrier_package_number:
                    return None
                    
                # Pobierz wszystkie dane
                all_data = self.sheets_handler.worksheet.get_all_values()
                package_number_col = 14  # Kolumna O = indeks 14
                order_number_col = 12   # Kolumna M = indeks 12
                
                # Szukaj wiersza z numerem paczki
                for i, row in enumerate(all_data):
                    if i == 0:  # Pomijamy nagłówek
                        continue
                        
                    # Sprawdź czy numer paczki znajduje się w kolumnie O (package_number)
                    if len(row) > package_number_col and row[package_number_col] and carrier_package_number in row[package_number_col]:
                        return i + 1  # Numery wierszy w API są 1-based
                    
                    # Sprawdź również kolumnę M (order_number)
                    if len(row) > order_number_col and row[order_number_col] and carrier_package_number in row[order_number_col]:
                        return i + 1
        
                return None
            
            except Exception as e:
                logging.error(f"Błąd podczas szukania wiersza po numerze paczki: {e}")
                return None        
            
    def _find_row_by_email(self, email):
        """Znajduje wiersz z podanym adresem email w kolumnie A"""
        try:
            if not email:
                return None
                
            # Pobierz wszystkie dane
            all_data = self.sheets_handler.worksheet.get_all_values()
            email_col = 0  # Kolumna A = indeks 0
            
            # Szukaj wiersza z podanym adresem email
            for i, row in enumerate(all_data):
                if i == 0:  # Pomijamy nagłówek
                    continue
                    
                # Sprawdź czy adres email pasuje
                if row[email_col] and email.lower() in row[email_col].lower():
                    return i + 1  # Numery wierszy w API są 1-based
            
            # Jeśli nie znaleziono, sprawdź również kolumnę J (dostępne emaile)
            avail_email_col = 9  # Kolumna J = indeks 9
            for i, row in enumerate(all_data):
                if i == 0:  # Pomijamy nagłówek
                    continue
                    
                # Sprawdź czy adres email znajduje się w dostępnych emailach
                if row[avail_email_col] and email.lower() in row[avail_email_col].lower():
                    return i + 1  # Numery wierszy w API są 1-based
            
            return None
                
        except Exception as e:
            logging.error(f"Błąd podczas szukania wiersza z adresem email: {e}")
            return None
        
    def update_pickup(self, row, order_data):
        """
        Aktualizuje wiersz dla przesyłki gotowej do odbioru - wersja do dziedziczenia
        
        Aktualizuje następujące kolumny:
        - email
        - receive place
        - receive code (PIN)
        - time to receive
        - available hours
        - status
        - QR
        - info
        - carrier package nr
        """
        try:
            updates = []
            
            # Kolumna 1 - Email
            if order_data.get("email"):
                self.sheets_handler.worksheet.update_cell(row, 1, order_data["email"])
                updates.append("email")
            
            # Kolumna 3 - Miejsce odbioru
            if order_data.get("pickup_location") or order_data.get("delivery_address"):
                address = order_data.get("pickup_location") or order_data.get("delivery_address")
                self.sheets_handler.worksheet.update_cell(row, 3, address)
                updates.append("miejsce odbioru")
                
            # Kolumna 5 - Kod odbioru (PIN)
            if order_data.get("pickup_code"):
                self.sheets_handler.worksheet.update_cell(row, 5, order_data["pickup_code"])
                updates.append("kod odbioru")
                
            # Kolumna 6 - Termin odbioru
            if order_data.get("pickup_deadline") or order_data.get("expected_delivery_date"):
                deadline = order_data.get("pickup_deadline") or order_data.get("expected_delivery_date")
                self.sheets_handler.worksheet.update_cell(row, 6, deadline)
                updates.append("termin odbioru")
                                
            # Kolumna 9 - Status
            status_text = "Gotowe do odbioru"
            if self.name:
                status_text += f" ({self.name})"
            self.sheets_handler.worksheet.update_cell(row, 9, status_text)
            updates.append("status")
            
            # Kolumna 12 - QR
            if order_data.get("qr_code"):
                self.sheets_handler.worksheet.update_cell(row, 12, order_data["qr_code"])
                updates.append("QR kod")
                
            # Kolumna 13 - Numer paczki
            if order_data.get("package_number"):
                self.sheets_handler.worksheet.update_cell(row, 13, order_data["package_number"])
                updates.append("numer paczki")
                
            # Kolumna 14 - Info
            if order_data.get("info"):
                self.sheets_handler.worksheet.update_cell(row, 14, order_data["info"])
                updates.append("info")
                
            # Kolumna 15 - Numer paczki przewoźnika
            if order_data.get("carrier_package_number"):
                self.sheets_handler.worksheet.update_cell(row, 15, order_data["carrier_package_number"])
                updates.append("carrier package number")
                
            # Zastosuj kolorowanie
            self.sheets_handler.worksheet.format(f"A{row}:O{row}", {
                "backgroundColor": self.colors.get("pickup", "#FFFF00")  # Domyślnie żółty jeśli nie zdefiniowano
            })
            
            logging.info(f"Zaktualizowano wiersz {row} dla paczki gotowej do odbioru - {', '.join(updates)}")
            return True
            
        except Exception as e:
            logging.error(f"Błąd podczas aktualizacji statusu pickup: {e}")
            return False
    
    # def update_all(self, row, order_data):
    #     """Aktualizuje wszystkie niepuste komórki w wierszu"""
    #     try:

    def update_delivered(self, row, order_data):
        """Aktualizuje wiersz dla paczki dostarczonej"""
        try:
            # Aktualizuj status
            status = f"Dostarczono ({self.name})"
            self.sheets_handler.worksheet.update_cell(row, 9, status)
            
            # Zastosuj kolor
            self.sheets_handler.worksheet.format(f"A{row}:N{row}", {
                "backgroundColor": self.colors["delivered"]
            })
            
            logging.info(f"Zaktualizowano wiersz {row} dla paczki {self.name} dostarczonej")
            return True
        except Exception as e:
            logging.error(f"Błąd podczas aktualizacji dostarczonej paczki {self.name}: {e}")
            return False
    
    def create_transit_row(self, order_data):
        """Tworzy nowy wiersz dla paczki w transporcie"""
        pass
    
    def create_pickup_row(self, order_data):
        """Tworzy nowy wiersz dla paczki gotowej do odbioru"""
        pass
            
    def general_get_status_text(self, status):
        """Zwraca tekst statusu w zależności od kodu"""
        status_map = {
            "shipment_sent": f"Przesyłka nadana ({self.name})",
            "transit": f"W transporcie ({self.name})",
            "pickup": f"Gotowa do odbioru ({self.name})",
            "delivered": f"Dostarczona ({self.name})",
            "confirmed": f"Zamówienie potwierdzone ({self.name})"
        }
        return status_map.get(status, f"Status nieznany: {status}")
    
    def general_update_sheet_data(self, order_data):
        """
        Uniwersalna funkcja aktualizująca dane w arkuszu na podstawie słownika order_data.
        Aktualizuje tylko pola, które nie są puste.
        
        Args:
            order_data: Słownik z danymi wyekstrahowanymi przez OpenAI
        
        Returns:
            bool: True jeśli aktualizacja się powiodła, False w przeciwnym przypadku
        """
        try:
            # Znajdź wiersz na podstawie różnych identyfikatorów
            package_number = order_data.get("package_number")
            row = self._find_row_by_carrier_package(package_number) if package_number else None
            
            # Jeśli nie znaleziono, próbuj po emailu
            if not row and order_data.get("email"):
                row = self._find_row_by_email(order_data.get("email"))
            
            # Jeśli dalej nie znaleziono, utwórz nowy wiersz
            if not row:
                 row = self.general_create_row(order_data)
                 return self._process_row_update_and_delivery(row, order_data)
            else:
                logging.info(f"Znaleziono wiersz {row} dla przesyłki {self.name} o numerze paczki {package_number}")
                    # ✅ SPRAWDŹ OBECNY STATUS PRZED AKTUALIZACJĄ
                existing_data = self.sheets_handler.worksheet.row_values(row)
                status_col = 9  # Kolumna I (status)
                
                current_status = None
                if len(existing_data) >= status_col:
                    current_status = existing_data[status_col-1]
                    logging.info(f"📊 Obecny status w arkuszu: '{current_status}'")
                
                new_status = order_data.get("status", "unknown")
                logging.info(f"📊 Nowy status z emaila: '{new_status}'")
                
                # ✅ SPRAWDŹ PRIORYTETY STATUSÓW
                current_priority = self.get_status_priority(current_status)
                new_priority = self.get_status_priority(new_status)
                
                logging.info(f"📊 Priorytet obecny: {current_priority}, priorytet nowy: {new_priority}")
                
                # ✅ BLOKUJ COFANIE SIĘ STATUSÓW
                if current_priority > new_priority:
                    logging.warning(f"🚫 BLOKUJĘ aktualizację: obecny status '{current_status}' (priorytet {current_priority}) jest późniejszy niż nowy '{new_status}' (priorytet {new_priority})")
                    return True  # Zwróć sukces ale nie aktualizuj
                
                elif current_priority == new_priority and current_status == new_status:
                    logging.info(f"ℹ️ Status się nie zmienił: '{current_status}' → '{new_status}'")
                    # Kontynuuj aktualizację - mogą być inne dane do zaktualizowania
                
                else:
                    logging.info(f"✅ DOZWOLONA aktualizacja statusu: '{current_status}' → '{new_status}' (priorytet {current_priority} → {new_priority})")
            

            # Aktualizuj pola, które nie są puste
            updates = []
            
            # Mapowanie kluczy order_data na kolumny w arkuszu
            field_mappings = {
                "email": 1,                    # A - Email
                "product_name": 2,             # B - Nazwa produktu
                "pickup_location": 3,          # C - Miejsce odbioru/dostawy
                "delivery_address": 3,         # C - Miejsce odbioru/dostawy (alternatywnie)
                "phone_number": 4,             # D - Numer telefonu
                "pickup_code": 5,              # E - Kod odbioru
                "pickup_deadline": 6,          # F - Termin odbioru
                "delivery_date": 6,            # F - Data dostarczenia (ta sama kolumna)
                "available_hours": 7,          # G - Godziny dostępności
                "email_date": 8,  
                "item link" :11,              # H - Nr order
                "qr_code": 12,                 # L - Kod QR
                "order_number": 13,            # M - Order number (zmienione)
                "info": 14,                    # N - Informacje
                "package_number": 15,
                                      # O - Package number (zmienione)
            }
            
            # Status (kolumna I - 9)
            if order_data.get("status"):
                status_text = self.general_get_status_text(order_data["status"])
                self.sheets_handler.worksheet.update_cell(row, 9, status_text)
                updates.append("status")
            
            # Aktualizuj pozostałe pola
            for field, column in field_mappings.items():
                if field in order_data and order_data[field]:
                    # ✅ SPECJALNE FORMATOWANIE DLA ORDER_NUMBER
                    if field == "order_number":
                        # Formatuj jako tekst z apostrofem na początku
                        formatted_value = f"'{str(order_data[field])}"
                        logging.info(f"🔢 Formatuję order_number jako tekst: '{order_data[field]}' → '{formatted_value}'")
                    else:
                        # Zwykłe formatowanie dla innych pól
                        formatted_value = order_data[field]
        
                    self.sheets_handler.worksheet.update_cell(row, column, formatted_value)
                    updates.append(field)
            
            # Zastosuj odpowiednie kolorowanie w zależności od statusu
            status = order_data.get("status")
            logging.info(f"🎨 Sprawdzanie koloru dla statusu: '{status}'")
            
            if status:
                # DODAJ OBSŁUGĘ STATUSU 'transit'
                if status in ["shipment_sent"]:
                    color_key = "shipment_sent"
                elif status == "confirmed":
                    color_key = "confirmed"
                elif status == "transit":  # ✅ DODAJ TĘ LINIĘ!
                    color_key = "transit"
                elif status == "pickup":
                    color_key = "pickup"
                elif status == "delivered":
                    color_key = "delivered"
                elif status == "closed":
                    color_key = "closed"
                elif status == "unknown":
                    color_key = "unknown"      
                else:
                    color_key = "transit"  # Domyślnie
                    logging.warning(f"⚠️ Nieznany status '{status}', używam domyślnego koloru")
                    
                # Sprawdź czy kolor istnieje w definicji
                if color_key not in self.colors:
                    logging.error(f"❌ Brak koloru '{color_key}' w self.colors: {list(self.colors.keys())}")
                    # ✅ FALLBACK DO PIERWSZEGO DOSTĘPNEGO KOLORU
                    available_colors = list(self.colors.keys())
                    color_key = available_colors[0] if available_colors else None
                    logging.info(f"🔄 Używam fallback koloru: {color_key}")
                    
                if color_key and color_key in self.colors:
                    color_to_apply = self.colors[color_key]
                    logging.info(f"🎨 Stosując kolor {color_key}: {color_to_apply}")
                    
                    # Zastosuj kolorowanie
                    self.sheets_handler.worksheet.format(f"A{row}:O{row}", {
                        "backgroundColor": color_to_apply
                    })
                
                logging.info(f"✅ Zastosowano kolor {color_key} dla statusu '{status}' w wierszu {row}")
                
                # ✅ DODAJ FORMATOWANIE TEKSTU DLA STATUSÓW ODBIORU
                self._apply_text_formatting(row, status)

            else:
                logging.warning("⚠️ Brak statusu w danych - nie można zastosować kolorowania")
        
            logging.info(f"Zaktualizowano wiersz {row} dla przesyłki {self.name}: {', '.join(updates)}")

            return self._process_row_update_and_delivery(row, order_data)
            # Przeniesienie wiersza do delivery
            # try:
            #     logging.info(f"Przenoszenie wiersza {row} do sekcji dostarczonych")
            #     # logging.info(f"📋 Wartości updates przed wysłaniem: {updates}")
            #     # logging.info(f"📊 Szczegóły updates: {[f'{i}: {val}' for i, val in enumerate(updates)]}")

            #     # ✅ POBIERZ ISTNIEJĄCE DANE Z WIERSZA
            #     existing_data = self.sheets_handler.worksheet.row_values(row)
            #     logging.info(f"📋 Istniejące dane z wiersza {row}: {existing_data}")
                
            #     # ✅ SKOPIUJ DANE I ZAKTUALIZUJ TYLKO NIEPUSTE POLA
            #     updates = existing_data.copy() if existing_data else [""] * 15
                

            #     range_end = "O"  # Kolumna O
            #     range_to_update = f"A{row}:{range_end}{row}"
                
            #     # ✅ WYKORZYSTAJ DELIVERED MANAGER DO AKTUALIZACJI
            #     delivered_manager = DeliveredOrdersManager(self.sheets_handler)
                
            #     # 1. Aktualizacja danych
            #     if not delivered_manager.safe_update_with_retry(range_to_update, updates):
            #         return False
                
            #     # 2. Kolorowanie
            #     status = order_data.get("status")
            #     delivered_manager.safe_apply_formatting(row, range_end, status, self.colors)
                
            #     # 3. Obsługa dostarczonych zamówień
            #     delivered_moved = delivered_manager.handle_delivered_order_after_update(row, status)
                
            #     if delivered_moved:
            #         logging.info(f"🎉 Zaktualizowano i przeniesiono dostarczone zamówienie z wiersza {row}")
            #     else:
            #         logging.info(f"🎉 Zaktualizowano wiersz {row} dla {self.name}")
                
            #     return True
                
            # except Exception as e:
            #     logging.error(f"❌ Błąd podczas przenoszenia danych w arkuszu: {e}")
            #     return False
            
        
        except Exception as e:
            logging.error(f"Błąd podczas aktualizacji danych w arkuszu: {e}")
            return False
    
    def general_create_row(self, order_data):
        """
        Uniwersalna funkcja tworząca nowy wiersz w arkuszu na podstawie danych order_data
        
        Kolumny arkusza:
        A: email
        B: what ordered (produkt)
        C: receive place (miejsce odbioru)
        D: nr tel
        E: receive code (kod odbioru)
        F: time to receive (termin odbioru)
        G: available hours (godziny dostępności)
        H: email_date
        I: status
        J: available emails
        K: item link
        L: QR kod
        M: order number (numer zamówienia)
        N: info (informacje)
        O: package number (numer paczki)
        """
        try:
            # Pobierz dane z order_data lub ustaw wartości domyślne
            email = order_data.get("email", "")
            product_name = order_data.get("product_name", "")
            
            # Miejsce odbioru/dostawy - użyj pickup_location lub delivery_address
            receive_place = order_data.get("pickup_location") or order_data.get("delivery_address", "")
            
            phone_number = order_data.get("phone_number", "")
            pickup_code = order_data.get("pickup_code", "")
            
            # Termin odbioru/dostawy - użyj pickup_deadline lub expected_delivery_date
            time_to_receive = order_data.get("pickup_deadline") or order_data.get("delivery_date") or order_data.get("expected_delivery_date", "")
            
            available_hours = order_data.get("available_hours", "")
            nr_order = order_data.get("nr_order", "")
            
            # Status - określ na podstawie pola status
            status = order_data.get("status", "")
            status_text = self.general_get_status_text(status)
            
            # Dodatkowe dane
            item_link = order_data.get("item_link", "")
            qr_code = order_data.get("qr_code", "")
            order_number = order_data.get("order_number", "")
            info = order_data.get("info", "")
            package_number = order_data.get("package_number", "")
            email_date = order_data.get("email_date", "")

            # Przygotuj dane wiersza (USUŃ email z kolumny P)
            row_data = [
                email,              # A: email
                product_name,       # B: what ordered
                receive_place,      # C: receive place
                phone_number,       # D: nr tel
                pickup_code,        # E: receive code
                time_to_receive,    # F: time to receive
                available_hours,    # G: available hours
                email_date,         # H:  email_date
                status_text,        # I: status
                "",                 # J: res.
                item_link,          # K: item link
                qr_code,            # L: QR
                order_number,       # M: order number
                info,               # N: info
                package_number      # O: package number
            ]
            
            # Znajdź pierwszy wolny wiersz
            values = self.sheets_handler.worksheet.get_all_values()
            next_row = len(values) + 1
            cell_range = f"A{next_row}:O{next_row}"  # ✅ ZMIEŃ Z P NA O
            
            # Dodaj wiersz
            self.sheets_handler.worksheet.update(cell_range, [row_data])
            
            # Zastosuj kolor w zależności od statusu
            if status == "confirmed" or status == "shipment_sent" or status == "transit":
                color = self.colors.get("transit", {"red": 0.95, "green": 0.95, "blue": 0.95})
            elif status == "pickup":
                color = self.colors.get("pickup", {"red": 0.95, "green": 0.95, "blue": 0.95})
            elif status == "delivered":
                color = self.colors.get("delivered", {"red": 0.8, "green": 0.9, "blue": 0.8})
            else:
                color = self.colors.get("transit", {"red": 0.95, "green": 0.95, "blue": 0.95})
            
            self.sheets_handler.worksheet.format(f"A{next_row}:O{next_row}", {
                "backgroundColor": color
            })
            self._apply_text_formatting(next_row, status)
            # self._apply_text_formatting(status, next_row)
            # self.sheets_handler.worksheet.format(f"A{next_row}:O{next_row}", {
            #     "textFormat": {
            #         "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},  # np. czerwony tekst
            #         "bold": True
            #     }
#               })

            logging.info(f"Utworzono nowy wiersz {next_row} dla {self.name} o statusie {status}")
            
            # ✅ SPRAWDŹ DOSTĘPNOŚĆ MAILI PO UTWORZENIU WIERSZA
            # try:
            #     from carriers_sheet_handlers import EmailAvailabilityManager
            #     email_availability_manager = EmailAvailabilityManager(self.sheets_handler)
            #     email_availability_manager.check_email_availability()
            #     logging.info("✅ Zaktualizowano dostępność maili w zakładce Accounts")
            # except Exception as e:
            #     logging.error(f"❌ Błąd podczas sprawdzania dostępności maili: {e}")
        
            return next_row
            
        except Exception as e:
            logging.error(f"Błąd podczas tworzenia wiersza: {e}")
            return False
    
    def _apply_text_formatting(self, row, status):
        """Stosuje formatowanie tekstu w zależności od statusu"""
        try:
            # ✅ CZERWONA CZCIONKA TYLKO DLA STATUSÓW ODBIORU
            pickup_statuses = [
                "pickup", "ready_for_pickup",
                "gotowa do odbioru", "gotowe do odbioru"
            ]
            
            # Sprawdź czy status wymaga czerwonej czcionki
            needs_red_text = False
            if status:
                status_lower = status.lower()
                # Sprawdź bezpośredni status
                if status_lower in pickup_statuses:
                    needs_red_text = True
                # Sprawdź czy zawiera słowa kluczowe
                elif any(keyword in status_lower for keyword in ["gotowa do odbioru", "ready for pickup"]):
                    needs_red_text = True
            
            if needs_red_text:
                # ✅ ZASTOSUJ CZERWONĄ CZCIONKĘ DLA STATUSÓW ODBIORU
                self.sheets_handler.worksheet.format(f"A{row}:O{row}", {
                    "textFormat": {
                        "foregroundColor": {"red": 1.0, "green": 0.0, "blue": 0.0},  # 🔴 CZERWONY
                        "bold": True
                    }
                })
                logging.info(f"🔴 Zastosowano czerwoną czcionkę dla statusu odbioru w wierszu {row}")
            else:
                # ✅ ZASTOSUJ CZARNĄ CZCIONKĘ DLA WSZYSTKICH INNYCH STATUSÓW
                self.sheets_handler.worksheet.format(f"A{row}:O{row}", {
                    "textFormat": {
                        "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},  # ⚫ CZARNY
                        "bold": False
                    }
                })
                logging.info(f"⚫ Zastosowano czarną czcionkę dla statusu '{status}' w wierszu {row}")
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Błąd podczas formatowania tekstu: {e}")
            return False
        
    def get_status_priority(self, status_text):
        """
        Zwraca priorytet statusu na podstawie tekstu statusu
        
        Args:
            status_text: Tekst statusu z arkusza
            
        Returns:
            int: Priorytet statusu (wyższa liczba = późniejszy status)
        """
        if not status_text:
            return 0
            
        status_lower = status_text.strip().lower()
        
        # ✅ SPRAWDŹ SŁOWA KLUCZOWE W STATUSIE
        if any(keyword in status_lower for keyword in ['potwierdzone', 'confirmed']):
            return 0  # Najwcześniejszy status
            
        elif any(keyword in status_lower for keyword in ['w transporcie', 'transit']):
            return 1  # W drodze
            
        elif any(keyword in status_lower for keyword in ['nadana', 'sent', 'shipped']):
            return 2  # Nadano
            
        elif any(keyword in status_lower for keyword in ['gotowa do odbioru', 'ready for pickup', 'pickup']):
            return 3  # Gotowe do odbioru
            
        elif any(keyword in status_lower for keyword in ['dostarczona', 'delivered', 'dostarczono']):
            return 4  # Dostarczone
            
        elif any(keyword in status_lower for keyword in ['zamknięte', 'closed', 'anulowane']):
            return 6  # Zamknięte
            
        else:
            return 5  # Nieznany status
        
    def _check_email_availability_after_update(self):
            """
            Sprawdza dostępność maili po aktualizacji danych
            """
            try:
                logging.info("📧 Sprawdzanie dostępności maili po aktualizacji...")
                email_manager = EmailAvailabilityManager(self.sheets_handler)
                result = email_manager.check_email_availability()
                
                if result:
                    logging.info("✅ Sprawdzenie dostępności maili zakończone sukcesem")
                else:
                    logging.warning("⚠️ Problem ze sprawdzaniem dostępności maili")
                    
            except Exception as e:
                logging.error(f"❌ Błąd podczas sprawdzania dostępności maili: {e}")

    def _process_row_update_and_delivery(self, row, order_data):
        """
        Przetwarza aktualizację wiersza i obsługuje przeniesienie dostarczonych zamówień
        
        Args:
            row: Numer wiersza do aktualizacji
            order_data: Dane zamówienia
            
        Returns:
            bool: True jeśli operacja się powiodła
        """
        try:
            logging.info(f"Przenoszenie wiersza {row} do sekcji dostarczonych")
            
            # ✅ POBIERZ ISTNIEJĄCE DANE Z WIERSZA
            existing_data = self.sheets_handler.worksheet.row_values(row)
            logging.info(f"📋 Istniejące dane z wiersza {row}: {existing_data}")
            
            # ✅ SKOPIUJ DANE I ZAKTUALIZUJ TYLKO NIEPUSTE POLA
            updates = existing_data.copy() if existing_data else [""] * 15       
            range_end = "O"  # Kolumna O
            range_to_update = f"A{row}:{range_end}{row}"
            
            # ✅ LOG SZCZEGÓŁÓW PRZED WYSŁANIEM
            logging.info(f"📋 FINALNE DANE DO AKTUALIZACJI:")
            for i, value in enumerate(updates):
                column_letter = chr(65 + i)  # A=65, B=66, etc.
                logging.info(f"      {column_letter}: '{value}'")
            
            # ✅ WYKORZYSTAJ DELIVERED MANAGER DO AKTUALIZACJI
            delivered_manager = DeliveredOrdersManager(self.sheets_handler)
            
            # 1. Aktualizacja danych
            if not delivered_manager.safe_update_with_retry(range_to_update, updates):
                return False
            
            # 2. Kolorowanie
            status = order_data.get("status")
            delivered_manager.safe_apply_formatting(row, range_end, status, self.colors)
            
            # 3. Obsługa dostarczonych zamówień
            delivered_moved = delivered_manager.handle_delivered_order_after_update(row, status)
            
            if delivered_moved:
                logging.info(f"🎉 Zaktualizowano i przeniesiono dostarczone zamówienie z wiersza {row}")
            else:
                logging.info(f"🎉 Zaktualizowano wiersz {row} dla {self.name}")
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Błąd podczas przenoszenia danych w arkuszu: {e}")
            return False
        
class InPostCarrier(BaseCarrier):
    """Klasa obsługująca przewoźnika InPost"""
    
    def __init__(self, sheets_handler):
        super().__init__(sheets_handler)
        self.name = "InPost"
        # INPOST - NIEBIESKIE ODCIENIE
        self.colors = {
            "shipment_sent": {"red": 0.8, "green": 0.9, "blue": 1.0},   # Jasny niebieski - nadano
            "pickup": {"red": 0.1, "green": 0.1, "blue": 0.5},          # Ciemny niebieski - gotowe do odbioru
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
            # Aktualizuj status
            status = f"W transporcie (DPD)"
            self.sheets_handler.worksheet.update_cell(row, 9, status)
            
            # Zapisz numer paczki
            if order_data.get("package_number"):
                self.sheets_handler.worksheet.update_cell(row, 13, order_data["package_number"])
            
            # Aktualizuj adres dostawy jeśli dostępny
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
                    
                    address_text = ", ".join(address_parts)
                else:
                    address_text = order_data["delivery_address"]
                
                self.sheets_handler.worksheet.update_cell(row, 3, address_text)
            
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
                self.sheets_handler.worksheet.update_cell(row, 14, info_text.strip())
            
            # Zastosuj kolor
            self.sheets_handler.worksheet.format(f"A{row}:N{row}", {
                "backgroundColor": self.colors["transit"]
            })
            
            logging.info(f"Zaktualizowano wiersz {row} dla paczki DPD w transporcie")
            return True
        except Exception as e:
            logging.error(f"Błąd podczas aktualizacji paczki DPD w transporcie: {e}")
            return False
    
    # def update_pickup(self, row, order_data):
    #     """Aktualizuje wiersz dla przesyłki DPD gotowej do odbioru"""
    #     try:
    #         # Aktualizacja statusu w kolumnie B
    #         self.sheets_handler.worksheet.update_cell(row, 2, "Kurier doręcza")
            
    #         # Aktualizuj numer paczki w kolumnie M
    #         if order_data.get("package_number"):
    #             self.sheets_handler.worksheet.update_cell(row, 13, order_data["package_number"])
            
    #         # Dodaj informacje o kurierze do kolumny INFO (N)
    #         info_text = ""
            
    #         # Dodaj informacje o kurierze
    #         if order_data.get("courier_info"):
    #             info_text += f"{order_data['courier_info']}\n"
    #         elif order_data.get("courier_name") or order_data.get("courier_phone"):
    #             courier_info = []
    #             if order_data.get("courier_name"):
    #                 courier_info.append(f"Kurier: {order_data['courier_name']}")
    #             if order_data.get("courier_phone"):
    #                 courier_info.append(f"Tel: {order_data['courier_phone']}")
    #             info_text += " | ".join(courier_info) + "\n"
            
    #         # Dodaj informacje o płatności
    #         if order_data.get("payment_info"):
    #             info_text += f"{order_data['payment_info']}\n"
            
    #         # Zapisz informacje w kolumnie INFO
    #         if info_text:
    #             self.sheets_handler.worksheet.update_cell(row, 14, info_text.strip())
            
    #         # Zastosuj kolor
    #         self.sheets_handler.worksheet.format(f"A{row}:N{row}", {
    #             "backgroundColor": self.colors["pickup"]
    #         })
            
    #         logging.info(f"Zaktualizowano wiersz {row} dla paczki DPD gotowej do odbioru")
    #         return True
            
    #     except Exception as e:
    #         logging.error(f"Błąd podczas aktualizacji statusu DPD pickup: {e}")
    #         return False

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

    # def process_notification(self, order_data):
    #     """Przetwarzanie powiadomień od DPD i aktualizacja statusu"""
    #     if not order_data or not order_data.get("status"):
    #         return False
   
    #     status = order_data.get("status")
    #     logging.info(f"Przetwarzanie powiadomienia DPD o statusie: {status}")
        
    #     # Pobierz package_number i znajdź wiersz
    #     package_number = order_data.get("package_number")
    #     row = self._find_row_by_tracking(package_number) if package_number else None
        
    #     # Jeśli nie znaleziono po numerze przesyłki, spróbuj po adresie email
    #     if not row and order_data.get("email"):
    #         logging.info(f"Nie znaleziono wiersza po numerze przesyłki, próbuję po email: {order_data.get('email')}")
    #         row = self._find_row_by_email(order_data.get("email"))
    #     elif not row and order_data.get("customer_name"):
    #         logging.info(f"Nie znaleziono wiersza po numerze przesyłki, próbuję po polu customer_name: {order_data.get('customer_name')}")
    #         row = self._find_row_by_email(order_data.get("customer_name"))
    
    #     if status == "shipment_sent":
    #         if row:
    #             return self.update_shipment_sent(row, order_data)
    #         else:
    #             return self.create_transit_row(order_data) # Użyjmy istniejącej metody
    #     elif status == "transit":
    #         if row:
    #             return self.update_transit(row, order_data)
    #         else:
    #             return self.create_transit_row(order_data)
    #     elif status == "delivered":
    #         if row:
    #             return self.update_delivered(row, order_data)
    #         else:
    #             logging.warning(f"Nie znaleziono wiersza dla przesyłki {package_number} do oznaczenia jako dostarczona")
    #             return False
    #     else:
    #         logging.warning(f"Nieznany status DPD: {status}")
    #         return False

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

    # def update_delivered(self, row, order_data):
    #     """Aktualizuje wiersz dla paczki DPD dostarczonej"""
    #     try:
    #         # Aktualizuj status
    #         self.sheets_handler.worksheet.update_cell(row, 2, "Dostarczona")
            
    #         # Zapisz datę dostarczenia jeśli dostępna
    #         if order_data.get("delivery_date"):
    #             self.sheets_handler.worksheet.update_cell(row, 6, order_data["delivery_date"])
            
    #         # Aktualizuj numer paczki w kolumnie M
    #         if order_data.get("package_number"):
    #             self.sheets_handler.worksheet.update_cell(row, 13, order_data["package_number"])
            
    #         # Dodaj informacje do kolumny INFO (N)
    #         info_text = ""
            
    #         # Możemy dodać informacje o odbiorcy
    #         if order_data.get("recipient_info"):
    #             info_text += f"Odbiorca: {order_data['recipient_info']}\n"
            
    #         # Dodaj informacje o dostawie
    #         if order_data.get("delivery_info"):
    #             info_text += f"{order_data['delivery_info']}\n"
            
    #         # Zapisz informacje w kolumnie INFO
    #         if info_text:
    #             self.sheets_handler.worksheet.update_cell(row, 14, info_text.strip())
            
    #         # Zastosuj kolor
    #         self.sheets_handler.worksheet.format(f"A{row}:N{row}", {
    #             "backgroundColor": self.colors["delivered"]
    #         })
            
    #         logging.info(f"Zaktualizowano wiersz {row} dla paczki DPD dostarczonej")
    #         return True
    #     except Exception as e:
    #         logging.error(f"Błąd podczas aktualizacji statusu DPD delivered: {e}")
    #         return False

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
    
    # def process_notification(self, order_data):
    #     """Przetwarzanie powiadomień od DHL i aktualizacja statusu"""
    #     if not order_data or not order_data.get("status"):
    #         return False
       
    #     status = order_data.get("status")
    #     logging.info(f"Przetwarzanie powiadomienia DHL o statusie: {status}")
        
    #     # Pobierz package_number i znajdź wiersz
    #     package_number = order_data.get("package_number")
    #     row = self._find_row_by_tracking(package_number) if package_number else None
        
    #     # Jeśli nie znaleziono po numerze przesyłki, spróbuj po adresie email
    #     if not row and order_data.get("email"):
    #         logging.info(f"Nie znaleziono wiersza po numerze przesyłki, próbuję po email: {order_data.get('email')}")
    #         row = self._find_row_by_email(order_data.get("email"))
    #     elif not row and order_data.get("customer_name"):
    #         logging.info(f"Nie znaleziono wiersza po numerze przesyłki, próbuję po polu customer_name: {order_data.get('customer_name')}")
    #         row = self._find_row_by_email(order_data.get("customer_name"))
        
    #     if status == "shipment_sent":
    #         if row:
    #             return self.update_shipment_sent(row, order_data)
    #         else:
    #             return self.create_transit_row(order_data)  # Użyjmy istniejącej metody
    #     elif status == "transit":
    #         if row:
    #             return self.update_pickup(row, order_data)
    #         else:
    #             return self.create_transit_row(order_data)
    #     elif status == "delivered":
    #         if row:
    #             return self.update_delivered(row, order_data)
    #         else:
    #             logging.warning(f"Nie znaleziono wiersza dla przesyłki {package_number} do oznaczenia jako dostarczona")
    #             return False
    #     else:
    #         logging.warning(f"Nieznany status DHL: {status}")
    #         return False
    
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
            # Aktualizuj status
            status = f"W transporcie (AliExpress)"
            self.sheets_handler.worksheet.update_cell(row, 9, status)
            
            # Zapisz numer zamówienia, jeśli dostępny
            if order_data.get("order_number"):
                self.sheets_handler.worksheet.update_cell(row, 8, order_data["order_number"])
            
            # Zapisz numer paczki
            if order_data.get("package_number"):
                self.sheets_handler.worksheet.update_cell(row, 13, order_data["package_number"])
            
            # Zapisz produkt i link
            if order_data.get("product_name"):
                self.sheets_handler.worksheet.update_cell(row, 2, order_data["product_name"])
            
            if order_data.get("item_link"):
                self.sheets_handler.worksheet.update_cell(row, 11, order_data["item_link"])
            
            # Zastosuj kolor
            self.sheets_handler.worksheet.format(f"A{row}:N{row}", {
                "backgroundColor": self.colors["transit"]
            })
            
            logging.info(f"Zaktualizowano wiersz {row} dla paczki AliExpress w transporcie")
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
        Pobiera listę emaili z kolumny A w zakładce Accounts.
        Zwraca listę stringów (samych adresów).
        """
        if not self.worksheet:
            self._init_accounts_worksheet()
            if not self.worksheet:
                return []
            
        try:
            email_column = self.worksheet.col_values(1)
            # Pomiń nagłówek i puste wiersze
            emails = [email.strip().lower() for email in email_column[1:] if email.strip()]
            logging.info(f"📋 Wczytano {len(emails)} aktywnych kont z zakładki Accounts")
            return emails
        except Exception as e:
            logging.error(f"Błąd pobierania emaili z Accounts: {e}")
            return []

    def check_email_availability(self):
        """
        Sprawdza dostępność maili (czy są zajęte przez aktywne zamówienia)
        i aktualizuje statusy/kolory w zakładce Accounts.
        """
        if not self.worksheet:
            return

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
    
    # def create_order_row(self, order_data):
    #     """Tworzy nowy wiersz dla zamówienia GLS"""
    #     try:
    #         new_row = [""] * 15  # Utwórz pusty wiersz z 15 kolumnami
            
    #         # Wypełnij podstawowe dane
    #         new_row[0] = order_data.get("email", "")
    #         new_row[1] = order_data.get("product_name", "")
    #         new_row[2] = order_data.get("delivery_address", "")
    #         new_row[3] = order_data.get("package_number", "")
    #         new_row[4] = order_data.get("phone_number", "")
    #         new_row[6] = order_data.get("shipping_date", "")
    #         new_row[8] = f"Przesyłka nadana ({self.name})"
    #         new_row[9] = order_data.get("email", "")
    #         new_row[12] = order_data.get("order_id", "")
            
    #         # Dodaj wiersz do arkusza
    #         self.sheets_handler.worksheet.append_row(new_row)
    #         logging.info(f"✅ Utworzono nowy wiersz dla zamówienia GLS: {order_data.get('package_number', 'BRAK_NUMERU')}")
    #         return True
            
    #     except Exception as e:
    #         logging.error(f"❌ Błąd podczas tworzenia wiersza GLS: {e}")
    #         return False
    
    # def update_status(self, row, status, additional_info=None):
    #     """Aktualizuje status zamówienia GLS"""
    #     try:
    #         status_text = f"{status} ({self.name})"
    #         if additional_info:
    #             status_text += f" - {additional_info}"
            
    #         self.sheets_handler.worksheet.update_cell(row, self.columns['status'], status_text)
    #         logging.info(f"✅ Zaktualizowano status GLS w wierszu {row}: {status_text}")
    #         return True
            
    #     except Exception as e:
    #         logging.error(f"❌ Błąd podczas aktualizacji statusu GLS: {e}")
    #         return False
    
    # def process_notification(self, order_data):
    #     """Przetwarza powiadomienie GLS"""
    #     try:
    #         status = order_data.get("status", "")
    #         package_number = order_data.get("package_number", "")
            
    #         # Znajdź wiersz z tym numerem paczki
    #         row = self.find_row_by_package_number(package_number)
            
    #         if status == "shipment_sent":
    #             if row:
    #                 return self.update_status(row, "Przesyłka nadana")
    #             else:
    #                 return self.create_order_row(order_data)
                    
    #         elif status == "pickup":
    #             if row:
    #                 pickup_info = order_data.get("pickup_location", "")
    #                 return self.update_status(row, "Gotowa do odbioru", pickup_info)
    #             else:
    #                 order_data["status"] = "Gotowa do odbioru"
    #                 return self.create_order_row(order_data)
                    
    #         elif status == "delivered":
    #             if row:
    #                 return self.update_status(row, "Dostarczona")
    #             else:
    #                 order_data["status"] = "Dostarczona"
    #                 return self.create_order_row(order_data)
            
    #         return False
            
    #     except Exception as e:
    #         logging.error(f"❌ Błąd podczas przetwarzania powiadomienia GLS: {e}")
    #         return False
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

    # Ponieważ dziedziczymy po BaseCarrier, metody update_pickup, update_delivered itp. 
    # zadziałają automatycznie (używając metody general_update_sheet_data z BaseCarrier).
    # Nie musimy ich tu pisać, chyba że chcemy specyficznego zachowania.