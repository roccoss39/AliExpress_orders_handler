import logging
import sys
import os
from datetime import datetime

# Konfiguracja logowania dla testów
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - TEST - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("test_system.log"),
        logging.StreamHandler()
    ]
)

def test_imports():
    """Test importów wszystkich modułów"""
    print("🧪 Testowanie importów...")
    
    try:
        import config
        print("✅ config - OK")
    except ImportError as e:
        print(f"❌ config - BŁĄD: {e}")
        return False
    
    try:
        from email_handler import EmailHandler
        print("✅ EmailHandler - OK")
    except ImportError as e:
        print(f"❌ EmailHandler - BŁĄD: {e}")
        return False
    
    try:
        from sheets_handler import SheetsHandler
        print("✅ SheetsHandler - OK")
    except ImportError as e:
        print(f"❌ SheetsHandler - BŁĄD: {e}")
        return False
    
    try:
        from carriers_data_handlers import GLSDataHandler
        print("✅ GLSDataHandler - OK")
    except ImportError as e:
        print(f"❌ GLSDataHandler - BŁĄD: {e}")
        print("⚠️  Musisz dodać klasę GLSDataHandler do carriers_data_handlers.py")
        return False
    
    try:
        from carriers_sheet_handlers import GLSCarrier
        print("✅ GLSCarrier - OK")
    except ImportError as e:
        print(f"❌ GLSCarrier - BŁĄD: {e}")
        print("⚠️  Musisz dodać klasę GLSCarrier do carriers_sheet_handlers.py")
        return False
    
    return True

def test_gls_handler():
    """Test obsługi GLS"""
    print("🧪 Testowanie handlera GLS...")
    
    try:
        from carriers_data_handlers import GLSDataHandler
        from email_handler import EmailHandler
        
        email_handler = EmailHandler()
        gls_handler = GLSDataHandler(email_handler)
        
        # Test cases dla GLS
        test_cases = [
            {
                "subject": "GLS - Twoja przesyłka została nadana",
                "body": "Szanowny Kliencie, Państwa przesyłka GL123456789 została nadana do transportu...",
                "expected": True
            },
            {
                "subject": "Powiadomienie GLS",
                "body": "Twoja paczka GLS czeka w parcelshop przy ul. Głównej 15...",
                "expected": True
            },
            {
                "subject": "Dostawa GLS Poland",
                "body": "Państwa przesyłka została dostarczona przez General Logistics Systems...",
                "expected": True
            },
            {
                "subject": "DHL Express Dostawa",
                "body": "Paczka DHL została dostarczona...",
                "expected": False
            },
            {
                "subject": "InPost Paczkomat",
                "body": "Twoja paczka czeka w paczkomacie...",
                "expected": False
            }
        ]
        
        all_passed = True
        for i, test in enumerate(test_cases, 1):
            result = gls_handler.can_handle(test["subject"], test["body"])
            status = "✅" if result == test["expected"] else "❌"
            print(f"{status} Test {i}: '{test['subject'][:30]}...' -> {result} (expected: {test['expected']})")
            if result != test["expected"]:
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        print(f"❌ Błąd podczas testowania GLS: {e}")
        return False

def test_o2_configuration():
    """Test konfiguracji poczty O2"""
    print("🧪 Testowanie konfiguracji O2...")
    
    try:
        from email_handler import EmailHandler
        
        email_handler = EmailHandler()
        
        # Test czy O2 jest w email_sources
        o2_in_sources = 'o2' in email_handler.email_sources
        print(f"{'✅' if o2_in_sources else '❌'} O2 w email_sources: {o2_in_sources}")
        
        if o2_in_sources:
            o2_config = email_handler.email_sources['o2']
            expected_server = 'poczta.o2.pl'
            expected_port = 993
            
            server_ok = o2_config.get('imap_server') == expected_server
            port_ok = o2_config.get('port') == expected_port
            
            print(f"{'✅' if server_ok else '❌'} Server O2: {o2_config.get('imap_server')} (expected: {expected_server})")
            print(f"{'✅' if port_ok else '❌'} Port O2: {o2_config.get('port')} (expected: {expected_port})")
            
            return server_ok and port_ok
        
        return False
        
    except Exception as e:
        print(f"❌ Błąd podczas testowania O2: {e}")
        return False

def test_email_configs():
    """Test konfiguracji wszystkich kont email"""
    print("🧪 Testowanie konfiguracji kont email...")
    
    try:
        import config
        
        # Test czy ALL_EMAIL_CONFIGS istnieje i jest listą
        if not hasattr(config, 'ALL_EMAIL_CONFIGS'):
            print("❌ Brak config.ALL_EMAIL_CONFIGS")
            return False
        
        if not isinstance(config.ALL_EMAIL_CONFIGS, list):
            print(f"❌ config.ALL_EMAIL_CONFIGS nie jest listą: {type(config.ALL_EMAIL_CONFIGS)}")
            return False
        
        print(f"✅ Znaleziono {len(config.ALL_EMAIL_CONFIGS)} konfiguracji email")
        
        # Test każdej konfiguracji
        valid_configs = 0
        for i, cfg in enumerate(config.ALL_EMAIL_CONFIGS, 1):
            email = cfg.get('email', 'BRAK')
            password = cfg.get('password')
            source = cfg.get('source', 'UNKNOWN')
            
            has_email = bool(email and email != 'BRAK')
            has_password = bool(password)
            has_source = bool(source and source != 'UNKNOWN')
            
            is_valid = has_email and has_password and has_source
            
            # Maskuj email dla bezpieczeństwa
            if email and '@' in email:
                masked_email = f"{email[:3]}***@{email.split('@')[1]}"
            else:
                masked_email = email
            
            status = "✅" if is_valid else "❌"
            print(f"  {status} Konto {i}: {masked_email} ({source}) - hasło: {'OK' if has_password else 'BRAK'}")
            
            if is_valid:
                valid_configs += 1
        
        print(f"✅ Prawidłowych konfiguracji: {valid_configs}/{len(config.ALL_EMAIL_CONFIGS)}")
        return valid_configs > 0
        
    except Exception as e:
        print(f"❌ Błąd podczas testowania konfiguracji email: {e}")
        return False

def test_environment_variables():
    """Test zmiennych środowiskowych"""
    print("🧪 Testowanie zmiennych środowiskowych...")
    
    try:
        from dotenv import load_dotenv
        import os
        
        load_dotenv()
        
        required_vars = [
            'O2_EMAIL_1', 'O2_PASSWORD_1',
            'GMAIL_EMAIL_1', 'GMAIL_PASSWORD_1',
            'INTERIA_EMAIL_1', 'INTERIA_PASSWORD_1'
        ]
        
        found_vars = 0
        for var in required_vars:
            value = os.getenv(var)
            has_value = bool(value)
            status = "✅" if has_value else "❌"
            
            # Maskuj hasła
            if 'PASSWORD' in var and has_value:
                display_value = f"***{value[-3:]}" if len(value) > 3 else "***"
            else:
                display_value = value if has_value else "BRAK"
            
            print(f"  {status} {var}: {display_value}")
            
            if has_value:
                found_vars += 1
        
        print(f"✅ Znalezionych zmiennych: {found_vars}/{len(required_vars)}")
        return found_vars >= len(required_vars) // 2  # Przynajmniej połowa musi być
        
    except Exception as e:
        print(f"❌ Błąd podczas testowania zmiennych środowiskowych: {e}")
        return False

def test_google_sheets_connection():
    """Test połączenia z Google Sheets"""
    print("🧪 Testowanie połączenia z Google Sheets...")
    
    try:
        from sheets_handler import SheetsHandler
        
        sheets_handler = SheetsHandler()
        
        # Test połączenia
        if sheets_handler.connect():
            print("✅ Połączenie z Google Sheets: OK")
            
            # Test czy GLS jest w carriers
            gls_in_carriers = 'GLS' in sheets_handler.carriers
            print(f"{'✅' if gls_in_carriers else '❌'} GLS w carriers: {gls_in_carriers}")
            
            # Wyświetl wszystkich dostępnych przewoźników
            print(f"✅ Dostępni przewoźnicy: {list(sheets_handler.carriers.keys())}")
            
            return True
        else:
            print("❌ Nie można połączyć się z Google Sheets")
            return False
            
    except Exception as e:
        print(f"❌ Błąd podczas testowania Google Sheets: {e}")
        return False

def test_carriers_integration():
    """Test integracji wszystkich przewoźników"""
    print("🧪 Testowanie integracji przewoźników...")
    
    try:
        from email_handler import EmailHandler
        
        email_handler = EmailHandler()
        
        # Sprawdź czy wszystkie handlery są dostępne
        expected_handlers = ['AliexpressDataHandler', 'InPostDataHandler', 'DHLDataHandler', 'DPDDataHandler', 'GLSDataHandler']
        found_handlers = []
        
        for handler in email_handler.data_handlers:
            handler_name = handler.__class__.__name__
            found_handlers.append(handler_name)
            print(f"✅ Handler: {handler_name}")
        
        missing_handlers = set(expected_handlers) - set(found_handlers)
        if missing_handlers:
            print(f"❌ Brakujące handlery: {missing_handlers}")
            return False
        
        print(f"✅ Wszystkie handlery dostępne: {len(found_handlers)}")
        return True
        
    except Exception as e:
        print(f"❌ Błąd podczas testowania przewoźników: {e}")
        return False

def run_comprehensive_test():
    """Uruchom kompletny test systemu"""
    print("🚀 Uruchamianie kompletnego testu systemu...")
    print(f"⏰ Czas testu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    tests = [
        ("Importy modułów", test_imports),
        ("Konfiguracja zmiennych środowiskowych", test_environment_variables),
        ("Konfiguracja kont email", test_email_configs),
        ("Handler GLS", test_gls_handler),
        ("Konfiguracja O2", test_o2_configuration),
        ("Połączenie Google Sheets", test_google_sheets_connection),
        ("Integracja przewoźników", test_carriers_integration)
    ]
    
    passed_tests = 0
    total_tests = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 {test_name}:")
        try:
            if test_func():
                print(f"✅ {test_name}: PASSED")
                passed_tests += 1
            else:
                print(f"❌ {test_name}: FAILED")
        except Exception as e:
            print(f"💥 {test_name}: ERROR - {e}")
    
    print("\n" + "=" * 60)
    print(f"🎯 WYNIKI TESTÓW: {passed_tests}/{total_tests} testów zakończonych sukcesem")
    
    if passed_tests == total_tests:
        print("🎉 Wszystkie testy przeszły! System jest gotowy do pracy.")
    elif passed_tests >= total_tests * 0.8:
        print("⚠️  Większość testów przeszła. System powinien działać z drobnymi problemami.")
    else:
        print("🚨 Wiele testów nie powiodło się. Sprawdź konfigurację przed uruchomieniem systemu.")
    
    return passed_tests, total_tests

def quick_test():
    """Szybki test najważniejszych funkcji"""
    print("⚡ Szybki test systemu...")
    
    # Test importów
    if not test_imports():
        print("❌ Błąd importów - przerwano test")
        return False
    
    # Test konfiguracji
    if not test_email_configs():
        print("❌ Błąd konfiguracji email - przerwano test")
        return False
    
    print("✅ Szybki test zakończony sukcesem!")
    return True

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--quick":
            quick_test()
        elif sys.argv[1] == "--gls":
            test_gls_handler()
        elif sys.argv[1] == "--o2":
            test_o2_configuration()
        elif sys.argv[1] == "--env":
            test_environment_variables()
        elif sys.argv[1] == "--sheets":
            test_google_sheets_connection()
        else:
            print("Dostępne opcje:")
            print("  --quick   : Szybki test")
            print("  --gls     : Test GLS")
            print("  --o2      : Test O2")
            print("  --env     : Test zmiennych środowiskowych")
            print("  --sheets  : Test Google Sheets")
            print("  (brak)    : Kompletny test")
    else:
        run_comprehensive_test()