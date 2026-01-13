import imaplib
import email
from email.utils import parsedate_to_datetime
import datetime
import pytz
import os
from email.header import decode_header

# Dane logowania dla każdego konta
accounts = [
    {
        'name': 'Gmail',
        'imap_server': 'imap.gmail.com',
        'email': 'dyskonto1@gmail.com',
        'password': 'kodb smfg hnmj kumf',
        'port': 993
    },
    {
        'name': 'Interia',
        'imap_server': 'poczta.interia.pl',  # POPRAWIONY SERWER
        'email': 'styczenq@interia.pl',
        'password': '....',
        'port': 993
    },
    {
        'name': 'o2',
        'imap_server': 'poczta.o2.pl',
        'email': 'podziewski39@o2.pl',
        'password': os.getenv('O2_PASSWORD_1'),
        'port': 993,
        'timeout': 60  # Dłuższy timeout dla o2
    }
]

# Definiowanie lokalnej strefy czasowej
local_tz = pytz.timezone('Europe/Warsaw')

def fetch_first_five_email_dates(account):
    print(f"\n📬 {account['name']} ({account['email']})")
    try:
        # Połączenie z serwerem IMAP z timeout
        timeout = account.get('timeout', 30)
        mail = imaplib.IMAP4_SSL(
            account['imap_server'], 
            account.get('port', 993),
            timeout=timeout
        )
        
        print(f"Łączenie z {account['imap_server']}...")
        mail.login(account['email'], account['password'])
        mail.select('INBOX')
        print("✅ Połączono pomyślnie")

        # WYSZUKUJ WSZYSTKIE EMAILE (PRZECZYTANE I NIEPRZECZYTANE)
        print("Szukam wszystkich emaili...")
        status, messages = mail.search(None, 'ALL')
        email_ids = messages[0].split()
        
        print(f"Znaleziono {len(email_ids)} emaili")
        
        # POBIERZ 5 NAJNOWSZYCH (odwróć listę aby mieć najnowsze pierwsze)
        latest_email_ids = email_ids[-5:]  # Ostatnie 5 emaili
        latest_email_ids.reverse()  # Odwróć aby najnowsze były pierwsze
        
        print(f"Przetwarzam 5 najnowszych emaili...")

        # Pobieranie 5 najnowszych wiadomości
        for i, email_id in enumerate(latest_email_ids):
            try:
                status, msg_data = mail.fetch(email_id, '(RFC822)')
                msg = email.message_from_bytes(msg_data[0][1]) 
                
                # POPRAWIONA OBSŁUGA DAT (bez deprecated funkcji)
                date_header = msg['Date']
                if date_header:
                    # Użyj parsedate_to_datetime zamiast deprecated funkcji
                    dt_with_tz = parsedate_to_datetime(date_header)
                    
                    # Konwersja do lokalnej strefy czasowej
                    dt_local = dt_with_tz.astimezone(local_tz)
                    
                    # Dodatkowe informacje
                    # ✅ DEKODUJ TEMAT
                    # Dekoduj temat
                    subject = msg['Subject'] or 'Brak tematu'
                    if subject != 'Brak tematu':
                        try:
                            decoded = decode_header(subject)
                            subject = ''.join([
                                part.decode(encoding or 'utf-8') if isinstance(part, bytes) else str(part)
                                for part, encoding in decoded
                            ])
                        except:
                            pass  # Zostaw oryginalny jeśli błąd
                    
                    from_addr = msg['From'] or 'Nieznany nadawca'
                    
                    # Sprawdź czy email był przeczytany
                    flags_result, flags_data = mail.fetch(email_id, '(FLAGS)')
                    flags_str = flags_data[0].decode() if flags_data and flags_data[0] else ''
                    is_read = '\\Seen' in flags_str
                    read_status = "📖 Przeczytany" if is_read else "📧 Nieprzeczytany"
                    
                    print(f"📧 Email {i+1} ({read_status}):")
                    print(f"   Data: {dt_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                    print(f"   Od: {from_addr}")
                    print(f"   Temat: {subject[:50]}...")
                    print(f"   ID: {email_id.decode()}")
                    print()
                else:
                    print(f"❌ Email {i+1}: Nie udało się odczytać daty")
                    
            except Exception as e:
                print(f"❌ Błąd podczas przetwarzania emaila {i+1}: {e}")
                
        mail.logout()
        print(f"✅ Zakończono przetwarzanie {account['name']}")
        
    except imaplib.IMAP4.error as e:
        print(f"❌ Błąd IMAP dla {account['name']}: {e}")
    except OSError as e:
        print(f"❌ Błąd połączenia z {account['name']}: {e}")
        print(f"   Sprawdź serwer: {account['imap_server']}")
    except Exception as e:
        print(f"❌ Nieoczekiwany błąd dla {account['name']}: {e}")

# Przetwarzanie każdego konta
for account in accounts:
    fetch_first_five_email_dates(account)

print("\n🏁 Test zakończony")