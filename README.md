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