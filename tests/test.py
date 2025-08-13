import imaplib
import email
from email.header import decode_header
from pyzbar.pyzbar import decode
from PIL import Image
import io

# --- Ustawienia logowania ---
IMAP_SERVER = "imap.gmail.com"
EMAIL_ACCOUNT = "dyskonto1@gmail.com"
EMAIL_PASSWORD = "kodb smfg hnmj kumf"  # Dla Gmaila może być konieczne hasło aplikacji
CID_TO_FIND = "<a31c5d9a-568c-3279-a5be-50e0a8393a03>"

# --- Połączenie z serwerem IMAP ---
mail = imaplib.IMAP4_SSL(IMAP_SERVER)
mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
mail.select("inbox")

# --- Pobierz ostatnią wiadomość ---
result, data = mail.search(None, "ALL")
mail_ids = data[0].split()
latest_email_id = mail_ids[-1]

result, msg_data = mail.fetch(latest_email_id, "(RFC822)")
raw_email = msg_data[0][1]
message = email.message_from_bytes(raw_email)

# --- Szukaj załącznika z określonym CID ---
found_image = None
for part in message.walk():
    if part.get_content_maintype() == "image" and part.get("Content-ID") == CID_TO_FIND:
        found_image = part.get_payload(decode=True)
        break

if not found_image:
    print("Nie znaleziono obrazu z podanym CID.")
    exit()

# --- Przetwórz obraz i odczytaj QR ---
image = Image.open(io.BytesIO(found_image))
decoded = decode(image)

if decoded:
    for obj in decoded:
        print("Zawartość QR:", obj.data.decode('utf-8'))
else:
    print("Nie udało się odczytać kodu QR.")
