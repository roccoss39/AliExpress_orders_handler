import imaplib
import socket
import ssl

# ==========================================
# 👇 KONFIGURACJA - WPISZ DANE TUTAJ 👇
# ==========================================
EMAIL = "jawna.kupa@interia.pl"
  # Wpisz dokładny adres
PASSWORD = "Qweqweqweqwe1$"   # Wpisz hasło (pamiętaj, bez spacji na końcu!)
# ==========================================

IMAP_SERVER = "poczta.interia.pl"
PORT = 993

def test_connection():
    print("-" * 50)
    print(f"🚀 ROZPOCZYNAM TEST LOGOWANIA DLA: {EMAIL}")
    print("-" * 50)

    # 1. Sprawdzenie danych wejściowych
    if PASSWORD == "twoje_haslo_tutaj":
        print("❌ BŁĄD: Nie edytowałeś pliku! Wpisz swoje hasło w sekcji KONFIGURACJA.")
        return

    try:
        # 2. Nawiązywanie połączenia SSL
        print(f"1️⃣  Łączenie z serwerem: {IMAP_SERVER}:{PORT}...")
        
        # Ustawienie bezpiecznego kontekstu SSL
        context = ssl.create_default_context()
        
        # Łączenie z timeoutem 10 sekund
        server = imaplib.IMAP4_SSL(IMAP_SERVER, PORT, ssl_context=context)
        print("   ✅ Połączenie nawiązane (Socket OK).")

        # 3. Próba logowania
        print(f"2️⃣  Próba autoryzacji...")
        print(f"   👤 Login: '{EMAIL}'")
        print(f"   🔑 Hasło: '{PASSWORD[0]}...{PASSWORD[-1]}' (długość: {len(PASSWORD)})")
        
        # Logowanie
        server.login(EMAIL, PASSWORD)
        
        print("\n✅ SUKCES! ZALOGOWANO POMYŚLNIE.")
        print("-" * 50)
        
        # 4. Test pobrania listy folderów (potwierdzenie uprawnień)
        print("3️⃣  Pobieranie listy folderów...")
        status, folders = server.list()
        if status == 'OK':
            print(f"   📂 Znaleziono {len(folders)} folderów na koncie.")
        
        # 5. Wylogowanie
        server.logout()
        print("4️⃣  Wylogowano poprawnie.")

    except imaplib.IMAP4.error as e:
        print("\n❌ BŁĄD LOGOWANIA (IMAP Error):")
        print(f"   Treść błędu: {e}")
        print("\n💡 MOŻLIWE PRZYCZYNY:")
        print("   1. Błędne hasło lub login.")
        print("   2. Wyłączony dostęp IMAP w ustawieniach Interii (Ustawienia -> Parametry).")
        print("   3. Blokada 'Podejrzanego logowania' (zaloguj się przez WWW i sprawdź komunikaty).")
        print("   4. Włączone weryfikacja dwuetapowa (2FA) - wtedy musisz użyć hasła aplikacji.")

    except socket.gaierror:
        print("\n❌ BŁĄD SIECI (DNS):")
        print("   Nie można znaleźć serwera. Sprawdź połączenie z internetem.")
    
    except ConnectionRefusedError:
        print("\n❌ BŁĄD POŁĄCZENIA:")
        print("   Serwer odrzucił połączenie. Może blokada IP (ban)?")

    except Exception as e:
        print(f"\n❌ INNY BŁĄD: {e}")

if __name__ == "__main__":
    test_connection()