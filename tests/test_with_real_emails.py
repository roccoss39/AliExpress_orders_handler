import os
import re
import sys
import email
import base64
import logging
import quopri
from email import policy
from email.parser import BytesParser
from datetime import datetime
from email.header import decode_header

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Importuj potrzebne klasy
from carriers_data_handlers import AliexpressDataHandler, InPostDataHandler, DHLDataHandler, DPDDataHandler
from email_handler import EmailHandler

def decode_email_header(header):
    """Dekoduje nagłówek email, który może zawierać zakodowane znaki."""
    if not header:
        return ""
    
    decoded_parts = []
    for part, encoding in decode_header(header):
        if isinstance(part, bytes):
            if encoding:
                decoded_parts.append(part.decode(encoding or 'utf-8', errors='replace'))
            else:
                decoded_parts.append(part.decode('utf-8', errors='replace'))
        else:
            decoded_parts.append(part)
    
    return ''.join(decoded_parts)

def extract_email_content(email_path):
    """Ekstrahuje treść i nagłówki z pliku .eml"""
    with open(email_path, 'rb') as f:
        msg = BytesParser(policy=policy.default).parse(f)
    
    # Ekstrahuj podstawowe informacje
    subject = decode_email_header(msg.get('subject', ''))
    from_addr = decode_email_header(msg.get('from', ''))
    to_addr = decode_email_header(msg.get('to', ''))
    
    # Wyciągnij adres email bez nazwy
    recipient_email = re.search(r'[\w\.-]+@[\w\.-]+', to_addr)
    recipient_email = recipient_email.group(0) if recipient_email else ""
    
    # Wyciągnij treść
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            
            # Pobierz tylko tekstową część, nie załączniki
            if "attachment" not in content_disposition and (content_type == "text/plain" or content_type == "text/html"):
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or 'utf-8'
                try:
                    body += payload.decode(charset, errors='replace')
                except:
                    body += payload.decode('utf-8', errors='replace')
                
                # Jeśli to HTML, to dodajemy tylko raz
                if content_type == "text/html":
                    break
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or 'utf-8'
        try:
            body = payload.decode(charset, errors='replace')
        except:
            body = payload.decode('utf-8', errors='replace')
    
    return {
        'subject': subject,
        'from': from_addr,
        'to': to_addr,
        'recipient_email': recipient_email,
        'body': body
    }

def test_email_processing(email_path):
    """Przetwarza pojedynczy plik .eml i sprawdza, jak zostałby obsłużony."""
    try:
        logging.info(f"Przetwarzanie pliku: {email_path}")
        
        # Ekstrahuj treść email
        email_data = extract_email_content(email_path)
        
        # Inicjalizuj handler email
        email_handler = EmailHandler()
        
        # Inicjalizuj wszystkie handlery
        handlers = [
            AliexpressDataHandler(email_handler),
            InPostDataHandler(email_handler),
            DHLDataHandler(email_handler),
            DPDDataHandler(email_handler)
        ]
        
        logging.info(f"Temat: {email_data['subject']}")
        logging.info(f"Od: {email_data['from']}")
        logging.info(f"Do: {email_data['to']}")
        logging.info(f"Adres odbiorcy: {email_data['recipient_email']}")
        logging.info(f"Długość treści: {len(email_data['body'])} znaków")
        
        # Dodane logowanie treści emaila (pierwsze 200 znaków)
        logging.debug("Zawartość pierwszych 200 znaków treści:")
        logging.debug(email_data['body'][:200])
        
        # Próbuj przetworzyć email przez każdy handler
        handled = False
        for handler in handlers:
            handler_name = handler.__class__.__name__
            can_handle = handler.can_handle(email_data['subject'], email_data['body'])
            logging.debug(f"Handler {handler_name}.can_handle zwrócił: {can_handle}")
            if can_handle:
                logging.info(f"Email może być obsłużony przez: {handler_name}")
                
                # Symulacja przetwarzania emaila
                result = handler.process(
                    email_data['subject'],
                    email_data['body'],
                    email_data['recipient_email'],
                    'gmail'  # Zakładamy, że to Gmail
                )
                
                # Wyświetl wyniki przetwarzania
                logging.info(f"Wynik przetwarzania przez {handler_name}:")
                if result:
                    for key, value in result.items():
                        logging.info(f"  {key}: {value}")
                    handled = True
                else:
                    logging.warning(f"Handler {handler_name} zwrócił pusty wynik.")
                
                # Sprawdź, czy email został sklasyfikowany poprawnie
                if 'status' in result:
                    logging.info(f"Status przesyłki: {result['status']}")
                else:
                    logging.warning("Brak statusu w wyniku przetwarzania.")
            
        if not handled:
            logging.warning("Żaden handler nie obsłużył tego emaila.")
        
        # Dodane logowanie debug dla DPDDataHandler
        logging.debug("Testowanie DPDDataHandler.can_handle...")
        dpd_handler = DPDDataHandler(email_handler)
        can_handle_result = dpd_handler.can_handle(email_data['subject'], email_data['body'])
        logging.debug(f"DPDDataHandler.can_handle zwrócił: {can_handle_result}")
        
        return handled
    
    except Exception as e:
        logging.error(f"Błąd podczas przetwarzania emaila: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return False

def batch_test_emails(directory=None):
    """Testuje wszystkie pliki .eml w podanym katalogu."""
    if directory is None:
        directory = os.path.expanduser("~/Downloads")  # Domyślnie katalog Pobrane
    
    logging.info(f"Rozpoczynam test plików .eml w katalogu: {directory}")
    
    eml_files = [f for f in os.listdir(directory) if f.lower().endswith('.eml')]
    
    if not eml_files:
        logging.warning(f"Nie znaleziono plików .eml w katalogu {directory}")
        return
    
    results = {
        'total': len(eml_files),
        'handled': 0,
        'failed': 0
    }
    
    for file_name in eml_files:
        file_path = os.path.join(directory, file_name)
        logging.info(f"\n--- TEST: {file_name} ---")
        
        if test_email_processing(file_path):
            results['handled'] += 1
        else:
            results['failed'] += 1
    
    # Podsumowanie
    logging.info("\n--- PODSUMOWANIE ---")
    logging.info(f"Przeanalizowano {results['total']} plików .eml")
    logging.info(f"Poprawnie obsłużono: {results['handled']}")
    logging.info(f"Nieobsłużonych: {results['failed']}")
    logging.info(f"Wskaźnik sukcesu: {(results['handled'] / results['total']) * 100:.1f}%")

def test_specific_email(file_path):
    """Testuje konkretny plik .eml podany jako argument."""
    if not os.path.exists(file_path):
        logging.error(f"Plik {file_path} nie istnieje.")
        return False
    
    logging.info(f"Rozpoczynam test pliku: {file_path}")
    return test_email_processing(file_path)

if __name__ == "__main__":
    # Sprawdź, czy podano ścieżkę do pliku jako argument
    if len(sys.argv) > 1:
        test_specific_email(sys.argv[1])
    else:
        # Możesz podać konkretny katalog jako argument
        downloads_dir = os.path.expanduser("~/Downloads")
        batch_test_emails(downloads_dir)