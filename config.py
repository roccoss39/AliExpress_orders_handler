import os
from dotenv import load_dotenv

# Załaduj zmienne środowiskowe z pliku .env
load_dotenv(override=True)

# Tryb śledzenia emaili:
# 'CONFIG'   - sprawdza wszystkie maile zdefiniowane w ALL_EMAIL_CONFIGS (stara metoda)
# 'ACCOUNTS' - sprawdza tylko maile wpisane w zakładce "Accounts" w Google Sheets
EMAIL_TRACKING_MODE = 'ACCOUNTS'

# Normal work : True
# True  = Sprawdza tylko te z "kropką" (UNSEEN). Szybkie, oszczędne.
# False = Sprawdza WSZYSTKIE maile z zakresu dat (nawet te otwarte). Wolniejsze, ale pewniejsze.
CHECK_ONLY_UNSEEN = False

# Czy przetwarzać również przeczytane maile? Tryb dla fun reprocess
# True = Pobiera wszystko z ostatnich dni (UWAGA: zużywa więcej tokenów AI)
# False = Pobiera tylko nowe, nieprzeczytane (Domyślnie)
PROCESS_READ_EMAILS = True # Huge API calls

# Czy ignorować datę ostatniego sprawdzenia?
# False = (Domyślnie) Bot pomija maile starsze niż te zapisane w historii. BEZPIECZNE.
# True  = Bot przetwarza KAŻDY znaleziony mail, nawet stary. 
# ⚠️ UWAGA: Ustawienie True może spowodować masowe wysyłanie powiadomień na Telegram!
IGNORE_LAST_EMAIL_DATE_CHECK = True

# Or Regrex if False
USE_OPENAI_API = False 

# Ustawienia kont e-mail
GMAIL_EMAIL = os.getenv('GMAIL_EMAIL_1')
GMAIL_PASSWORD = os.getenv('GMAIL_PASSWORD_1')
INTERIA_EMAIL = os.getenv('INTERIA_EMAIL_1')
INTERIA_PASSWORD = os.getenv('INTERIA_PASSWORD_1')
DEFAULT_EMAIL_PASSWORD = INTERIA_PASSWORD 

# Ustawienia arkusza Google
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
SHEET_NAME = "Ali_orders"

# Adres do powiadomień
NOTIFICATION_EMAIL = os.getenv('NOTIFICATION_EMAIL')

# Interwał sprawdzania (w minutach)
CHECK_INTERVAL = 5

# Interwał dla testów (w sekundach)
TEST_INTERVAL = 10

# Tryb testowy - uruchamia tylko test_single_run
TEST_MODE = False  # Ustawiamy na False żeby działał main_loop

# Szybkie sprawdzanie (co 10 sekund)
QUICK_CHECK = False  # Nowa opcja dla szybkiego sprawdzania

# Kolory statusów (wartości RGB)
COLORS = {
    "delivered": {"red": 0.7, "green": 0.9, "blue": 0.7},  # zielony
    "canceled": {"red": 0.9, "green": 0.7, "blue": 0.7},   # czerwony
    "pickup": {"red": 0.7, "green": 0.7, "blue": 0.9},  # Jasny niebieski
    "available_email": {"red": 0.8, "green": 0.7, "blue": 0.9},   # fioletowy
}

# Klucz API OpenAI
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# ✅ DODAJ KONFIGURACJĘ O2
# O2_EMAILS = [
#     {
#         'email': "podziewski39@o2.pl",
#         'password': os.getenv('O2_PASSWORD_1'),
#         'source': "o2"
#     },
#     # Dodaj więcej kont O2 w razie potrzeby
# ]

# ✅ KOMPLETA LISTA WSZYSTKICH EMAILI W JEDNYM MIEJSCU
ALL_EMAIL_CONFIGS = [
    {
        'email': GMAIL_EMAIL,
        'password': GMAIL_PASSWORD,
        'source': 'gmail'
    },
    {
        'email': INTERIA_EMAIL,
        'password': INTERIA_PASSWORD,
        'source': 'interia'
    },
    {
        'email': os.getenv('O2_EMAIL_1'),
        'password': os.getenv('O2_PASSWORD_1'),
        'source': "o2"
    }
    
]

# ✅ KONFIGURACJA OKRESÓW SPRAWDZANIA
EMAIL_CHECK_SETTINGS = {
    'days_back': 30,                    # 30 dni wstecz
    'fallback_limit': 50,               # Limit emaili w trybie fallback
    'max_emails_per_account': 100,      # Maksymalna liczba emaili na konto
    'o2_email_limit': 50,               # Specjalny limit dla O2
    'o2_days_limit': 1,                 # Specjalny limit dni dla O2
    'mark_as_read': True,               # Oznaczaj emaile jako przeczytane
    'auto_expunge': True                # Automatycznie zapisuj zmiany
}

# --- TELEGRAM CONFIG ---
ENABLE_TELEGRAM = True
TELEGRAM_BOT_TOKEN = os.getenv('_TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('_TELEGRAM_CHAT_ID')

