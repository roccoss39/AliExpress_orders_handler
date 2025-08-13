import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from email_handler import EmailHandler
from sheets_handler import SheetsHandler
from carriers_data_handlers import DPDDataHandler, InPostDataHandler
from carriers_sheet_handlers import DPDCarrier, InPostCarrier
from test_with_real_emails import extract_email_content

class SheetsUpdateTest(unittest.TestCase):
    
    def setUp(self):
        """Przygotowanie środowiska testowego"""
        # Podstawowy mock dla SheetsHandler
        self.mock_sheets = MagicMock()
        
        # Kluczowa różnica: stwórz najpierw mock dla worksheet
        self.mock_worksheet = MagicMock()
        
        # Przypisz mock worksheet jako atrybut sheets_handler
        self.mock_sheets.worksheet = self.mock_worksheet
        
        # Inicjalizacja handlerów
        self.email_handler = EmailHandler()
        
        # Użyj mocka arkusza we wszystkich carrierach
        self.dpd_carrier = DPDCarrier(self.mock_sheets)
        self.inpost_carrier = InPostCarrier(self.mock_sheets)
        
        # Dodaj przewoźników do słownika
        self.mock_sheets.carriers = {
            "DPD": self.dpd_carrier,
            "InPost": self.inpost_carrier
        }

    def test_dpd_shipment_sent_update(self):
        """Test aktualizacji arkusza dla DPD - przesyłka nadana"""
        # Ścieżka do pliku testowego
        test_email_path = "test_emails/nadana_dpd.eml"
        
        if not os.path.exists(test_email_path):
            self.skipTest(f"Plik testowy {test_email_path} nie istnieje")
        
        # Pobierz dane z pliku .eml
        email_data = extract_email_content(test_email_path)
        
        # Inicjalizuj handler DPD
        dpd_handler = DPDDataHandler(self.email_handler)
        
        # Przetwórz email
        order_data = dpd_handler.process(
            email_data['subject'],
            email_data['body'],
            email_data['recipient_email'],
            'gmail'
        )
        
        # Sprawdź czy dane zostały prawidłowo przetworzone
        self.assertIsNotNone(order_data)
        self.assertEqual(order_data.get('carrier'), 'DPD')
        
        # Zasymuluj aktualizację arkusza
        result = self.dpd_carrier.process_notification(order_data)
        
        # Sprawdź czy jakikolwiek z oczekiwanych methods został wywołany
        methods_called = (
            self.mock_worksheet.update.called or 
            self.mock_worksheet.update_cell.called or
            self.mock_worksheet.format.called
        )
        self.assertTrue(methods_called, "Żadna z metod aktualizacji arkusza nie została wywołana")
        
        # Jeśli append_row zostało użyte, sprawdź czy zawiera numer przesyłki
        if self.mock_sheets.worksheet.append_row.called:
            for call in self.mock_sheets.worksheet.append_row.call_args_list:
                args, kwargs = call
                row_data = args[0]  # Pierwszy argument to lista danych wiersza
                # Sprawdź czy numer przesyłki jest w danych wiersza
                self.assertTrue(
                    any(order_data.get('package_number') in str(cell) for cell in row_data),
                    "Numer przesyłki nie został dodany do nowego wiersza"
                )

    # Dodaj więcej testów dla innych przewoźników i statusów...

if __name__ == "__main__":
    unittest.main()