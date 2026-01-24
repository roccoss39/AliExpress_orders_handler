#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script - logowanie do Interia i pobieranie emaili z tematem "zamówienie potwierdzone"
"""

import imaplib
import email
from email.header import decode_header
import sys
import os

# Dodaj katalog główny do PATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DEFAULT_EMAIL_PASSWORD


def decode_subject(subject):
    """Dekoduje temat emaila"""
    if not subject:
        return ""
    
    decoded_parts = []
    for part, encoding in decode_header(subject):
        if isinstance(part, bytes):
            try:
                if encoding:
                    decoded_parts.append(part.decode(encoding))
                else:
                    decoded_parts.append(part.decode('utf-8', errors='ignore'))
            except:
                decoded_parts.append(part.decode('utf-8', errors='ignore'))
        else:
            decoded_parts.append(str(part))
    
    return ''.join(decoded_parts)


def get_email_body(email_message):
    """Wyciąga ciało emaila i konwertuje HTML na tekst"""
    body_text = ""
    body_html = ""
    
    if email_message.is_multipart():
        for part in email_message.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            
            # Szukaj text/plain
            if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                    body_text = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                except:
                    pass
            # Szukaj text/html
            elif content_type == "text/html" and "attachment" not in content_disposition:
                try:
                    body_html = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                except:
                    pass
    else:
        # Nie jest multipart
        try:
            body_text = email_message.get_payload(decode=True).decode('utf-8', errors='ignore')
        except:
            body_text = str(email_message.get_payload())
    
    # Preferuj text/plain, jeśli nie ma to konwertuj HTML
    if body_text:
        return body_text
    elif body_html:
        return html_to_text(body_html)
    else:
        return ""


def html_to_text(html):
    """Konwertuje HTML na czysty tekst"""
    from html.parser import HTMLParser
    import re
    
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
        # Fallback - usuń tagi HTML regex
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', html)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()


def parse_email(email_message):
    """
    Parsuje email i zwraca wszystkie kluczowe dane w słowniku
    
    Args:
        email_message: Obiekt email.message
        
    Returns:
        dict: {
            'from': 'Nadawca <email@example.com>',
            'to': 'odbiorca@example.com',
            'date': 'Sat, 17 Jan 2026 18:10:04',
            'subject': 'Temat emaila',
            'body': 'Oczyszczone ciało emaila (bez HTML)'
        }
    """
    # Pobierz nagłówki
    from_addr = email_message.get('From', '')
    to_addr = email_message.get('To', '')
    date_header = email_message.get('Date', '')
    raw_subject = email_message.get('Subject', '')
    
    # Dekoduj temat
    subject = decode_subject(raw_subject)
    
    # Pobierz oczyszczone ciało (bez HTML)
    body = get_email_body(email_message)
    
    return {
        'from': from_addr,
        'to': to_addr,
        'date': date_header,
        'subject': subject,
        'body': body
    }


def print_parsed_email(parsed_email, email_number=None):
    """
    Wyświetla sparsowany email w czytelny sposób
    
    Args:
        parsed_email (dict): Wynik z parse_email()
        email_number (int): Numer emaila (opcjonalny)
    """
    if email_number:
        print()
        print("=" * 80)
        print(f"✅ ZNALEZIONO EMAIL #{email_number}")
        print("=" * 80)
    
    print(f"📧 Od: {parsed_email['from']}")
    if parsed_email['to']:
        print(f"📮 Do: {parsed_email['to']}")
    print(f"📅 Data: {parsed_email['date']}")
    print(f"📝 Temat: {parsed_email['subject']}")
    print()
    print("📄 CIAŁO EMAILA:")
    print("-" * 80)
    print(parsed_email['body'])
    print("-" * 80)
    print()

def test_interia_login(email_address, password, search_keyword="zamówienie potwierdzone"):
    """
    Loguje się do Interia, szuka emaili z danym tematem i wyciąga ich ciało
    
    Args:
        email_address (str): Adres email Interia
        password (str): Hasło
        search_keyword (str): Słowo kluczowe w temacie
    """
    print("=" * 80)
    print(f"🔍 TEST LOGOWANIA DO INTERIA")
    print("=" * 80)
    print(f"Email: {email_address}")
    print(f"Szukam emaili z tematem: '{search_keyword}'")
    print()
    
    try:
        # 1. Połącz z IMAP
        print("📡 Łączenie z poczta.interia.pl:993...")
        mail = imaplib.IMAP4_SSL('poczta.interia.pl', 993)
        
        # 2. Zaloguj
        print(f"🔐 Logowanie jako {email_address}...")
        mail.login(email_address, password)
        print("✅ Zalogowano pomyślnie!")
        print()
        
        # 3. Wybierz skrzynkę INBOX
        mail.select('INBOX')
        print("📬 Wybrano skrzynkę: INBOX")
        print()
        
        # 4. Szukaj emaili (ostatnie 30 dni)
        from datetime import datetime, timedelta
        cutoff_date = datetime.now() - timedelta(days=30)
        date_string = cutoff_date.strftime('%d-%b-%Y')
        
        print(f"🔎 Szukam emaili od {date_string}...")
        result, data = mail.search(None, f'(SINCE {date_string})')
        
        if result != 'OK':
            print("❌ Błąd wyszukiwania")
            return
        
        email_ids = data[0].split()
        print(f"📧 Znaleziono {len(email_ids)} emaili w ostatnich 30 dniach")
        print()
        
        # 5. Przetwórz emaile (od najnowszych)
        found_count = 0
        email_ids = email_ids[-50:]  # Ostatnie 50 emaili
        
        print(f"🔄 Przetwarzam ostatnie {len(email_ids)} emaili...")
        print("-" * 80)
        
        for email_id in reversed(email_ids):  # Od najnowszych
            try:
                # Pobierz email
                result, data = mail.fetch(email_id, '(RFC822)')
                if result != 'OK':
                    continue
                
                raw_email = data[0][1]
                email_message = email.message_from_bytes(raw_email)
                
                # Dekoduj temat (szybkie sprawdzenie dla filtrowania)
                subject = decode_subject(email_message.get('Subject', ''))
                
                # Sprawdź czy zawiera słowo kluczowe
                if search_keyword.lower() in subject.lower():
                    found_count += 1
                    
                    # ✅ PARSUJ EMAIL JEDNĄ FUNKCJĄ
                    parsed = parse_email(email_message)
                    
                    # Wyświetl
                    print_parsed_email(parsed, email_number=found_count)
                    
                    # Zapisz do pliku
                    filename = f"email_body_{found_count}.txt"
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(f"Od: {parsed['from']}\n")
                        f.write(f"Do: {parsed['to']}\n")
                        f.write(f"Data: {parsed['date']}\n")
                        f.write(f"Temat: {parsed['subject']}\n")
                        f.write("\n" + "=" * 80 + "\n\n")
                        f.write(parsed['body'])
                    
                    print(f"💾 Zapisano pełne ciało do: {filename}")
                    print()
                    
            except Exception as e:
                print(f"⚠️ Błąd przetwarzania emaila {email_id}: {e}")
                continue
        
        # 6. Podsumowanie
        print()
        print("=" * 80)
        print("📊 PODSUMOWANIE")
        print("=" * 80)
        print(f"Przeszukano: {len(email_ids)} emaili")
        print(f"Znaleziono: {found_count} emaili z tematem '{search_keyword}'")
        
        if found_count > 0:
            print(f"✅ Zapisano {found_count} plików: email_body_1.txt, email_body_2.txt, ...")
        else:
            print(f"❌ Nie znaleziono emaili z tematem '{search_keyword}'")
        
        print("=" * 80)
        
        # 7. Zamknij połączenie
        mail.close()
        mail.logout()
        print()
        print("👋 Rozłączono")
        
    except imaplib.IMAP4.error as e:
        print(f"❌ Błąd IMAP: {e}")
        print()
        print("💡 Możliwe przyczyny:")
        print("   1. Nieprawidłowe hasło")
        print("   2. Dostęp IMAP wyłączony w ustawieniach konta")
        print("   3. Konto zablokowane")
        
    except Exception as e:
        print(f"❌ Błąd: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print()
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "TEST LOGOWANIA DO INTERIA" + " " * 33 + "║")
    print("╚" + "=" * 78 + "╝")
    print()
    
    # Pobierz dane z argumentów lub użyj domyślnych
    if len(sys.argv) >= 3:
        email_address = sys.argv[1]
        password = sys.argv[2]
        search_keyword = sys.argv[3] if len(sys.argv) > 3 else "zamówienie potwierdzone"
    else:
        # Dane z input
        email_address = input("📧 Podaj adres email Interia: ").strip()
        
        print()
        print("🔑 Wybierz źródło hasła:")
        print("  1. Wpisz hasło ręcznie")
        print("  2. Użyj DEFAULT_EMAIL_PASSWORD z config.py")
        choice = input("Wybór (1/2): ").strip()
        
        if choice == "2":
            password = DEFAULT_EMAIL_PASSWORD
            print(f"✅ Używam hasła z config.py: {password[:4]}...{password[-4:]}")
        else:
            import getpass
            password = getpass.getpass("🔑 Podaj hasło: ")
        
        print()
        search_keyword = input("🔎 Podaj słowo kluczowe w temacie [zamówienie potwierdzone]: ").strip()
        if not search_keyword:
            search_keyword = "zamówienie potwierdzone"
    
    print()
    
    # Uruchom test
    test_interia_login(email_address, password, search_keyword)
    
    print()
    print("✅ Test zakończony!")
