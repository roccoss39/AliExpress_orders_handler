AliExpress & Multi-Carrier Order Tracker
Zaawansowany, automatyczny system do śledzenia zamówień z AliExpress (i nie tylko) poprzez analizę wiadomości email i synchronizację z Arkuszem Google. System działa w trybie ciągłym (24/7), inteligentnie zarządzając statusami kont email i limitami API.

Moje sugestie:
1. Używać funkcji reprocess do odtwarzanie wszystkich maili z konta - sprawdzenie poprawnosci systemu.
Przykład użycia: python3 main.py --reprocess-email jan.kowalski@interia.pl --limit 10

🚀 Kluczowe Funkcjonalności
🧠 Tryb Hybrydowy (AI + Regex):

AI (OpenAI GPT): Precyzyjna analiza trudnych maili.

Regex Fallback: Automatyczne przełączenie na wyrażenia regularne w przypadku błędu API lub limitów (Rate Limiting), zapewniające ciągłość działania.

🚚 Obsługa Wielu Przewoźników: Rozpoznaje specyficzne formaty maili od:

AliExpress: Potwierdzenia, wysyłka, statusy "Closed".

InPost: Nadanie, Odbiór, Kody QR.

Poczta Polska / Pocztex / Listy polecone.

Kurierzy: DHL, DPD, GLS.

🔄 Inteligentny Handover: Wykrywa zmianę numeru śledzenia (np. z AliExpress LP... na Poczta Polska PX...) i aktualizuje istniejący wiersz w arkuszu zamiast tworzyć duplikat.

👥 Zarządzanie Kontami (Multi-Account):

Monitorowanie nieograniczonej liczby skrzynek email.

Wizualizacja statusu w arkuszu: Czerwony (Zajęty/Ma paczkę) / Biały (Wolny).

Obsługa globalnego hasła dla wszystkich kont (definiowane w config.py).

🛠️ Bezpieczeństwo i Stabilność:

Graceful Shutdown: Bezpieczne zamykanie procesu z zapisem stanu (app_state.json).

Health Check Server: Wbudowany monitoring HTTP na porcie 8081.

📋 Wymagania
Python 3.8+

Konto Google Cloud (Service Account) z dostępem do Google Sheets API

Klucz OpenAI API (opcjonalne, ale zalecane dla lepszej precyzji)

Konta email z włączonym dostępem IMAP

🔧 Instalacja
Sklonuj repozytorium:

Bash

git clone <repository-url>
cd aliexpress-tracker
Zainstaluj zależności:

Bash

pip install -r requirements.txt
Skonfiguruj zmienne środowiskowe:

Bash

cp .env.example .env
Edytuj plik .env i uzupełnij klucze (OpenAI, dane email dla trybu testowego).

Skonfiguruj Google Service Account:

Utwórz projekt w Google Cloud Console i włącz Google Sheets API.

Wygeneruj klucz JSON dla Service Account i zapisz go jako service_account.json w głównym folderze.

Ważne: Udostępnij swój Arkusz Google dla adresu email widocznego w pliku service_account.json.

⚙️ Konfiguracja Arkusza i Haseł
System wymaga dwóch zakładek w Arkuszu Google. Hasła do kont email są pobierane z pliku konfiguracyjnego, a nie z arkusza.

Orders (Główna tabela):

Przechowuje dane o paczkach (Email, Produkt, Tracking, Status, Linki, QR, itd.).

QR w arkuszu:
- Kolumna QR jest zapisywana jako formuła (dla polskiej lokalizacji Google Sheets): `=HIPERŁĄCZE("URL";"QR")`
  żeby link był zawsze klikalny (nie jako zwykły tekst).

Accounts (Baza kont):

Kolumna A: Adres Email.

Kolumna B: Status (bot wpisuje tu "wolny" lub "-"). Komórki są automatycznie kolorowane na czerwono, gdy konto jest zajęte.

Uwaga: W arkuszu wystarczą tylko te dwie kolumny. Hasło jest pobierane globalnie ze zmiennej DEFAULT_EMAIL_PASSWORD w pliku config.py.

🚀 Uruchomienie i Obsługa
1. Tryb Standardowy (Live Loop)
Uruchamia bota w trybie ciągłym. Sprawdza maile, aktualizuje arkusz i zarządza kolorami w zakładce Accounts.

Bash

python3 main.py
2. Menu Diagnostyczne
Pozwala sprawdzić statusy, wyczyścić logi, przetestować API lub sprawdzić mapowania.

Bash

python3 main.py --menu
3. Tryb Reprocess (Naprawa Historii) 🛠️
Specjalny tryb służący do przeszukania historii mailowej i uzupełnienia brakujących danych w arkuszu. Przydatny, gdy bot był wyłączony przez kilka dni lub dodałeś nowe konto z istniejącymi zamówieniami.

Cechy trybu Reprocess:

Działa jednorazowo (nie jest pętlą).

Ignoruje blokady czasowe (sprawdza głęboko wstecz, np. 60 dni).

Wymusza aktualizację mapowań w pliku user_mappings.json.

Automatycznie aktualizuje kolory w zakładce Accounts po zakończeniu pracy (oznacza zajęte konta na czerwono).

Jak używać:

Bash

# Składnia:
# python3 main.py --reprocess-email <ADRES_EMAIL> [--limit <LICZBA_MAILI>] [--subject-contains <FRAZA>]

# Przykład 1: Przetwórz 10 ostatnich maili dla konkretnego konta
python3 main.py --reprocess-email jan.kowalski@interia.pl --limit 10

# Przykład 1b: Przetwórz tylko maile, których temat zawiera daną frazę (case-insensitive)
# Np. dla tematu: "InPost - Paczka już na Ciebie czeka" zadziała fraza: "czek" lub "czeka"
python3 main.py --reprocess-email jan.kowalski@interia.pl --limit 50 --subject-contains czek

# Przykład 2: Pełny skan konta (bez limitu, domyślny zakres dni z configu)
python3 main.py --reprocess-email jan.kowalski@interia.pl
🐧 Wdrażanie na Linux (Systemd)
Aby bot działał w tle 24/7 i uruchamiał się po restarcie serwera, używamy systemd.

Instalacja usługi
Utwórz plik usługi:

Bash

sudo nano /etc/systemd/system/ali-tracker.service
Wklej konfigurację (dostosuj ścieżki!):

Ini, TOML

[Unit]
Description=AliExpress Order Tracker Bot
After=network.target

[Service]
User=twoja_nazwa_uzytkownika
WorkingDirectory=/home/twoja_nazwa/aliexpress-tracker
ExecStart=/usr/bin/python3 main.py
# WAŻNE: Restartuje bota automatycznie po 10 sek w razie błędu/zamknięcia
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
Załaduj i uruchom:

Bash

sudo systemctl daemon-reload
sudo systemctl enable ali-tracker
sudo systemctl start ali-tracker
🛑 Jak zatrzymać bota (Zarządzanie działaniem w tle)
Ponieważ w konfiguracji jest Restart=always, zwykłe "zabicie" procesu (kill) nic nie da – system wstanie po 10 sekundach. Aby go skutecznie zatrzymać:

Tymczasowe zatrzymanie (do momentu restartu serwera lub ręcznego włączenia):

Bash

sudo systemctl stop ali-tracker
Użyj tego, gdy chcesz ręcznie odpalić python3 main.py w terminalu (np. do testów), aby uniknąć konfliktów dwóch instancji.

Całkowite wyłączenie (nie wstanie nawet po restarcie serwera):

Bash

sudo systemctl disable --now ali-tracker

Aby pozniej wystartowac:
sudo systemctl enable --now ali-tracker
Po wystartowaniu zawsze warto sprawdzić status, aby upewnić się, że bot nie wywalił się na starcie (np. przez błąd w kodzie):

sudo systemctl status ali-tracker

Ponowne uruchomienie (np. po zmianie kodu lub configu):
sudo systemctl restart ali-tracker
Sprawdzenie statusu i logów:

sudo systemctl status ali-tracker
# Podgląd logów na żywo:
journalctl -u ali-tracker -f
📁 Struktura projektu
Plaintext

├── main.py                    # Główny plik, CLI, pętla główna
├── config.py                  # Ustawienia, hasła, limity
├── email_handler.py           # Logika IMAP, pobieranie maili
├── sheets_handler.py          # Komunikacja z Google Sheets API
├── carriers_sheet_handlers.py # Logika kolorowania kont i specyfika przewoźników
├── aliexpress_handler.py      # Specjalistyczny parser dla AliExpress (Regex/AI)
├── openai_handler.py          # Integracja z GPT-4o/3.5
├── graceful_shutdown.py       # Bezpieczne zamykanie procesów
├── app_state.json             # Plik stanu (nie usuwać ręcznie w trakcie pracy)
├── user_mappings.json         # Cache powiązań Email <-> Tracking
└── requirements.txt           # Zależności
📊 Monitoring Health Check
Gdy bot działa w tle, możesz sprawdzić jego kondycję bez wchodzenia w logi:

Bash

curl http://localhost:8081/health
Odpowiedź JSON zawiera czas działania (uptime) oraz liczbę przetworzonych maili.

🔒 Bezpieczeństwo
⚠️ WAŻNE: Pliki .env, service_account.json oraz *.log zawierają wrażliwe dane. Są one domyślnie dodane do .gitignore. Nigdy ich nie upubliczniaj.

## 🍓 Wdrożenie na Raspberry Pi (Serwer 24/7)

Projekt jest zoptymalizowany pod kątem pracy na **Raspberry Pi Zero 2 W** (system Debian Bookworm Lite). Dzięki niskim wymaganiom zasobowym, urządzenie to idealnie sprawdza się jako dedykowany, energooszczędny serwer pracujący w trybie ciągłym.

### 🔑 Logowanie do serwera
Dostęp do konsoli Malinki uzyskujemy poprzez protokół SSH. Z poziomu terminala na laptopie wpisz:
```bash
ssh dawid@malina
Domyślna ścieżka projektu na serwerze: /home/dawid/aliexpress_orders⚙️ Zarządzanie usługą (Systemd)Bot działa jako usługa systemowa ali-tracker.service. Oznacza to, że uruchamia się automatycznie po starcie systemu i restartuje w razie wystąpienia błędów.AkcjaKomendaSprawdzenie statususudo systemctl status ali-trackerPodgląd logów (Live)journalctl -u ali-tracker -fRestart botasudo systemctl restart ali-trackerZatrzymanie botasudo systemctl stop ali-trackerLogi z dzisiajjournalctl -u ali-tracker --since "today"🚀 Automatyzacja wdrożenia (Skrypt Deploy)Aby uniknąć ręcznego kopiowania plików i restartowania usługi za każdym razem, gdy wprowadzisz zmiany w kodzie, w projekcie znajduje się skrypt deploy.sh. Pozwala on na pełną aktualizację bota jednym poleceniem z poziomu Twojego laptopa.Użycie (wykonaj na laptopie):Bash# Uruchom wdrożenie
./deploy.sh

# Sprawdzenie logów z laptopa na malince
ssh malina "journalctl -u ali-tracker -f"
🐍 Środowisko wirtualne (venv)Na serwerze używane jest izolowane środowisko Python, aby uniknąć konfliktów z pakietami systemowymi. Jeśli dodasz nową bibliotekę do requirements.txt, środowisko zaktualizuje się automatycznie przy uruchomieniu skryptu deploy.sh.🏥 Monitoring zdrowia (Health Check)Możesz sprawdzić, czy bot "żyje" i pracuje prawidłowo, wysyłając zapytanie HTTP do wbudowanego serwera monitorującego:Bash# Wykonaj na Malince lub w przeglądarce (http://malina:8081/health)
curl http://localhost:8081/health
Odpowiedź {"status": "ok"} potwierdza, że pętla główna bota oraz połączenie z API Google/OpenAI działają bez zarzutu.
Wklej ten fragment na samym dole swojego `README.md` na laptopie, uaktualnij `deploy.sh` dodając `*.md` i po wpisaniu `./deploy.sh` wszystko na Malince zaktualizuje się do nowej wersji!

### 🔄 Tryb Reprocess (Ręczne skanowanie historii)

Tryb `--reprocess-email` pozwala na wymuszenie ponownego przeskanowania starszych wiadomości dla konkretnego konta. Przydaje się, gdy bot był wyłączony, dodałeś nowe konto z historią zamówień lub chcesz naprawić brakujące dane w arkuszu.

**⚠️ WAŻNE:** Zawsze zatrzymaj usługę działającą w tle przed uruchomieniem tego trybu, aby zapobiec konfliktom (dwa procesy nie mogą modyfikować arkusza jednocześnie).

#### Opcja 1: Z poziomu Raspberry Pi (Zalecane)
Zaloguj się na serwer (`ssh dawid@malina`), a następnie wykonaj poniższe kroki w terminalu Malinki:

```bash
# 1. Zatrzymaj automat działający w tle
sudo systemctl stop ali-tracker

# 2. Uruchom reprocess używając wirtualnego środowiska (venv)
cd ~/aliexpress_orders
./venv/bin/python3 main.py --reprocess-email rafa.afar1@interia.pl --limit 20

# Opcjonalnie z filtrem tematu (np. przyspiesza skanowanie, szukając tylko InPostu):
# ./venv/bin/python3 main.py --reprocess-email rafa.afar1@interia.pl --limit 20 --subject-contains "czeka"

# 3. Po zakończeniu skanowania, uruchom automat ponownie
sudo systemctl start ali-tracker
Opcja 2: Zdalnie z poziomu Twojego laptopa
Możesz wykonać całą procedurę bez wchodzenia w interaktywną powłokę Malinki. Wystarczy wysłać komendy bezpośrednio z terminala na swoim laptopie:

Bash
# 1. Zatrzymaj bota zdalnie
ssh dawid@malina "sudo systemctl stop ali-tracker"

# 2. Odpal reprocess (logi z analizy będą wyświetlać się na żywo u Ciebie na laptopie)
ssh dawid@malina "cd ~/aliexpress_orders && ./venv/bin/python3 main.py --reprocess-email rafa.afar1@interia.pl --limit 20"

# 3. Włącz bota w tle ponownie
ssh dawid@malina "sudo systemctl start ali-tracker"

### Jak to teraz wgrać na serwer?
Po wklejeniu tego do `README.md` na swoim laptopie i zapisaniu pliku, pamiętaj, że wystarczy wpisać:

```bash
./deploy.sh

## Sprawdzenie czy działa z laptopa XX to ip, zazwyczaj 237
curl http://192.168.0.XX:8081/health