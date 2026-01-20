# AliExpress Order Tracker

Automatyczny system śledzenia zamówień z AliExpress poprzez analizę emaili i aktualizację arkusza Google Sheets.

## 🚀 Funkcjonalności

- **Automatyczne sprawdzanie emaili** z różnych dostawców (Gmail, Interia, O2)
- **Analiza statusów zamówień** za pomocą AI (OpenAI GPT)
- **Aktualizacja Google Sheets** z informacjami o zamówieniach
- **Powiadomienia** o zmianach statusów
- **Mapowanie użytkowników** do numerów zamówień i paczek
- **Graceful shutdown** z zapisem stanu
- **Rate limiting** dla API
- **Automatyczne czyszczenie logów**

## 📋 Wymagania

- Python 3.7+
- Konto Google z dostępem do Google Sheets API
- Klucz API OpenAI
- Konta email do monitorowania

## 🔧 Instalacja

1. **Sklonuj repozytorium:**
```bash
git clone <repository-url>
cd aliexpress-tracker
```

2. **Zainstaluj zależności:**
```bash
pip install -r requirements.txt
```

3. **Skonfiguruj zmienne środowiskowe:**
```bash
cp .env.example .env
```
Edytuj plik `.env` i uzupełnij wszystkie wymagane dane.

4. **Skonfiguruj Google Service Account:**
```bash
cp service_account.json.example service_account.json
```
Uzupełnij plik danymi z Google Cloud Console.

## ⚙️ Konfiguracja

### Google Sheets API

1. Przejdź do [Google Cloud Console](https://console.cloud.google.com/)
2. Utwórz nowy projekt lub wybierz istniejący
3. Włącz Google Sheets API
4. Utwórz Service Account i pobierz klucz JSON
5. Skopiuj zawartość do `service_account.json`
6. Udostępnij arkusz Google dla adresu email Service Account

### OpenAI API

1. Zarejestruj się na [OpenAI Platform](https://platform.openai.com/)
2. Wygeneruj klucz API
3. Dodaj klucz do pliku `.env`

### Konta Email

Skonfiguruj hasła aplikacji dla:
- **Gmail**: Wygeneruj hasło aplikacji w ustawieniach Google
- **Interia**: Użyj standardowego hasła
- **O2**: Użyj standardowego hasła

## 🚀 Uruchomienie

### Tryb rozwojowy:
```bash
python main.py
```

### Menu diagnostyczne:
```bash
python main.py --menu
```

### Jako usługa systemowa:
```bash
chmod +x deploy.sh
./deploy.sh
```

## 📁 Struktura projektu

```
├── main.py                    # Główny plik aplikacji
├── config.py                  # Konfiguracja
├── email_handler.py           # Obsługa emaili
├── sheets_handler.py          # Obsługa Google Sheets
├── openai_handler.py          # Integracja z OpenAI
├── notification.py            # System powiadomień
├── graceful_shutdown.py       # Graceful shutdown
├── rate_limiter.py           # Rate limiting
├── requirements.txt          # Zależności Python
├── .env.example              # Przykład zmiennych środowiskowych
├── service_account.json.example # Przykład konfiguracji Google
└── deploy.sh                 # Skrypt wdrożenia
```

## 🔒 Bezpieczeństwo

⚠️ **WAŻNE**: Nigdy nie commituj następujących plików:
- `.env` - zawiera hasła i klucze API
- `service_account.json` - zawiera klucze Google
- `user_mappings.json` - zawiera dane osobowe
- `*.log` - mogą zawierać wrażliwe informacje

Wszystkie wrażliwe dane są automatycznie ignorowane przez `.gitignore`.

## 📊 Monitorowanie

### Logi
```bash
tail -f aliexpress_tracker.log
```

### Menu diagnostyczne
```bash
python main.py --menu
```

## 📝 Licencja

Ten projekt jest prywatny i przeznaczony do użytku osobistego.

---

**Uwaga**: Ten projekt obsługuje dane osobowe. Upewnij się, że przestrzegasz lokalnych przepisów o ochronie danych.

UPDATE:
AliExpress & Multi-Carrier Order Tracker
Zaawansowany, automatyczny system do śledzenia zamówień z AliExpress (i nie tylko) poprzez analizę wiadomości email i synchronizację z Arkuszem Google. System działa w trybie ciągłym (24/7), inteligentnie zarządzając statusami kont i limitami API.

🚀 Kluczowe Funkcjonalności
🧠 Tryb Hybrydowy (AI + Regex)
Podstawowa analiza: Wykorzystuje OpenAI (GPT) do precyzyjnego wyciągania danych z trudnych maili.

Awaryjny Fallback: W przypadku błędu API (np. Limit 429 Too Many Requests), system automatycznie przełącza się na zaawansowane wyrażenia regularne (Regex), zapewniając ciągłość działania bez utraty danych.

🚚 Obsługa Wielu Przewoźników
System rozpoznaje i obsługuje specyficzne formaty maili od:

AliExpress (Potwierdzenia, W transporcie)

InPost (Paczkomaty: Nadanie, Odbiór, Kod QR)

Poczta Polska (Pocztex, Listy polecone)

DHL / DPD / GLS (Obsługa standardowa)

🔄 Inteligentny Handover (Przekazywanie Paczek)
Wykrywa sytuację, w której numer śledzenia zmienia się po przekroczeniu granicy (np. AliExpress LP... -> Poczta Polska PX...).

Nie tworzy duplikatów: Aktualizuje istniejący wiersz w arkuszu, podmieniając numer paczki i zachowując historię w notatkach.

👥 Zarządzanie Kontami (Multi-Account)
Obsługa wielu skrzynek: Monitoruje nieograniczoną liczbę kont email (zdefiniowanych w Arkuszu Google).

Statusy dostępności: Automatycznie oznacza konta w arkuszu jako "Zajęty" (Czerwony) lub "Wolny" na podstawie ostatniej aktywności mailowej.

Globalne hasło: Możliwość zdefiniowania jednego hasła w config.py dla wszystkich kont (np. Interia), bez konieczności wpisywania ich w arkuszu.

🛠️ Narzędzia Administracyjne
Health Check Server: Wbudowany serwer HTTP (port 8081) zwracający status JSON (/health) dla monitoringu uptime'u.

Reprocess Mode: Komenda CLI do "naprawy" historii lub ponownego przetworzenia starych maili bez wpływu na bieżące działanie.

Graceful Shutdown: Bezpieczne zamykanie procesu z zapisem stanu (app_state.json), zapobiegające uszkodzeniu danych.

📋 Wymagania
Python 3.8+

Konto Google Cloud (Service Account) z dostępem do Google Sheets API

Klucz OpenAI API (opcjonalne, ale zalecane dla lepszej precyzji)

Skonfigurowane konta email (IMAP włączony)

🔧 Instalacja
Sklonuj repozytorium:

Bash

git clone <repository-url>
cd aliexpress-tracker
Zainstaluj zależności:

Bash

pip install -r requirements.txt
Konfiguracjaplików:

Skopiuj .env.example do .env i uzupełnij klucz OpenAI.

Umieść plik klucza Google jako service_account.json.

Edytuj config.py (ustaw ID Arkusza, nazwy zakładek, domyślne hasło email).

⚙️ Struktura Arkusza Google
System wymaga dwóch głównych zakładek w arkuszu:

Orders (Główna):

Kolumny A-O (Email, Produkt, Adres, Telefon, Tracking, Status, Data, Link, QR Code, itd.).

Accounts (Konta):

Kolumna A: Email

Kolumna B: Status (Zajęty/Wolny - aktualizowane przez bota)

Kolumna C: Hasło (Opcjonalne - jeśli puste, użyte zostanie DEFAULT_EMAIL_PASSWORD z configu).

🚀 Uruchomienie
1. Tryb Standardowy (Live)
Uruchamia główną pętlę monitorowania, health check i aktualizację statusów.

Bash

python3 main.py
2. Tryb Reprocess (Naprawa Historii)
Służy do przeszukania starych maili i uzupełnienia brakujących danych w arkuszu (nie zmienia statusów "Zajęty").

Bash

# Przetwórz 30 ostatnich maili dla konkretnego konta
python3 main.py --reprocess-email twoj.email@interia.pl --limit 30
📊 Monitoring (Health Check)
Gdy bot działa, możesz sprawdzić jego stan w przeglądarce lub przez curl:

Bash

curl http://localhost:8081/health
Przykładowa odpowiedź:

JSON

{
  "status": "healthy",
  "uptime": "2026-01-11T17:30:00",
  "processed_emails": 15,
  "service": "aliexpress_tracker"
}
📁 Struktura Projektu
Plaintext

├── main.py                    # Główny punkt wejścia, pętla główna, CLI
├── config.py                  # Konfiguracja stałych i haseł
├── email_handler.py           # Logika pobierania i analizy emaili
├── sheets_handler.py          # Komunikacja z Google Sheets (Singleton)
├── carriers_sheet_handlers.py # Logika dla poszczególnych przewoźników (InPost, Poczta, etc.)
├── openai_handler.py          # Obsługa zapytań do GPT-4o/3.5
├── health_check.py            # Serwer monitoringu HTTP
├── graceful_shutdown.py       # Obsługa sygnałów zamknięcia (SIGINT/SIGTERM)
├── app_state.json             # Zapis stanu aplikacji
├── user_mappings.json         # Baza powiązań Email <-> Użytkownik (cache)
└── requirements.txt           # Zależności
🔒 Bezpieczeństwo
Pliki .env, service_account.json, *.log oraz user_mappings.json są wykluczone z repozytorium (.gitignore).

Hasła w arkuszu są opcjonalne – zaleca się używanie DEFAULT_EMAIL_PASSWORD w config.py dla bezpieczeństwa.

📝 Status Projektu
✅ Wdrożony i Stabilny. System poprawnie obsługuje limity API (Rate Limiting), konflikty numerów paczek (Handover) oraz wiele kont jednocześnie.

🐧 Wdrożenie na Linux (Systemd Service)
Aby bot działał 24/7 w tle i wstawał po restarcie systemu:

Utwórz plik usługi:

Bash

sudo nano /etc/systemd/system/ali-tracker.service
Wklej konfigurację:

Ini, TOML

[Unit]
Description=AliExpress Order Tracker Bot
After=network.target

[Service]
User=twoja_nazwa_uzytkownika
WorkingDirectory=/home/twoja_nazwa/sciezka/do/bota
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
Uruchom usługę:

Bash

sudo systemctl daemon-reload
sudo systemctl enable ali-tracker
sudo systemctl start ali-tracker

Restart bota (np. po zmianie hasła w config.py):
sudo systemctl restart ali-tracker.service

stop
sudo systemctl stop ali-tracker

Monitoring:

Podgląd logów na żywo: journalctl -u ali-tracker -f

Status usługi: sudo systemctl status ali-tracker