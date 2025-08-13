import os
import logging
from datetime import datetime, timedelta

def cleanup_old_logs(log_file="aliexpress_tracker.log", days=3):
    """
    Usuwa logi starsze niż określona liczba dni z pliku
    
    Args:
        log_file (str): Nazwa pliku z logami (domyślnie aliexpress_tracker.log)
        days (int): Liczba dni - logi starsze będą usunięte (domyślnie 3)
    
    Returns:
        dict: Statystyki czyszczenia
    """
    if not os.path.exists(log_file):
        print(f"Plik {log_file} nie istnieje")
        return {"status": "error", "message": f"Plik {log_file} nie istnieje"}
    
    try:
        cutoff_date = datetime.now() - timedelta(days=days)
        print(f"🧹 Usuwanie logów starszych niż: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Wczytaj wszystkie linie z pliku
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        original_count = len(lines)
        
        # Filtruj linie - zachowaj tylko te z ostatnich X dni
        filtered_lines = []
        removed_count = 0
        
        for line in lines:
            # Próbuj wyciągnąć datę z początku linii (format: 2025-06-01 23:04:09,487)
            try:
                # Wyciągnij pierwsze 19 znaków (YYYY-MM-DD HH:MM:SS)
                if len(line) >= 19 and line[4] == '-' and line[7] == '-':
                    date_str = line[:19]  # 2025-06-01 23:04:09
                    log_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                    
                    if log_date > cutoff_date:
                        filtered_lines.append(line)
                    else:
                        removed_count += 1
                else:
                    # Jeśli linia nie ma prawidłowej daty, zachowaj ją
                    filtered_lines.append(line)
                    
            except ValueError:
                # Jeśli nie można sparsować daty, zachowaj linię
                filtered_lines.append(line)
        
        # Zapisz przefiltrowane logi z powrotem do pliku
        with open(log_file, 'w', encoding='utf-8') as f:
            f.writelines(filtered_lines)
        
        # Statystyki
        stats = {
            "status": "success",
            "original_lines": original_count,
            "removed_lines": removed_count,
            "remaining_lines": len(filtered_lines),
            "cutoff_date": cutoff_date.strftime('%Y-%m-%d %H:%M:%S'),
            "file": log_file
        }
        
        print(f"✅ Czyszczenie logów zakończone:")
        print(f"   • Usunięto: {removed_count} linii")
        print(f"   • Pozostało: {len(filtered_lines)} linii")
        print(f"   • Plik: {log_file}")
        
        return stats
        
    except Exception as e:
        error_msg = f"Błąd podczas czyszczenia logów: {e}"
        print(f"❌ {error_msg}")
        return {"status": "error", "message": error_msg}


def cleanup_logs_by_size(log_file="aliexpress_tracker.log", max_size_mb=50):
    """
    Alternatywna funkcja - usuwa najstarsze logi gdy plik przekracza określony rozmiar
    
    Args:
        log_file (str): Nazwa pliku z logami
        max_size_mb (int): Maksymalny rozmiar pliku w MB
    
    Returns:
        dict: Statystyki czyszczenia
    """
    if not os.path.exists(log_file):
        return {"status": "error", "message": f"Plik {log_file} nie istnieje"}
    
    try:
        # Sprawdź rozmiar pliku
        file_size_mb = os.path.getsize(log_file) / (1024 * 1024)
        
        if file_size_mb <= max_size_mb:
            msg = f"Rozmiar pliku logów: {file_size_mb:.2f}MB (limit: {max_size_mb}MB) - OK"
            print(f"📁 {msg}")
            return {
                "status": "ok", 
                "message": msg,
                "current_size_mb": file_size_mb,
                "max_size_mb": max_size_mb
            }
        
        print(f"⚠️ Plik logów za duży: {file_size_mb:.2f}MB (limit: {max_size_mb}MB)")
        
        # Wczytaj linie
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        original_lines = len(lines)
        
        # Zachowaj tylko ostatnie 50% linii
        keep_lines = len(lines) // 2
        filtered_lines = lines[-keep_lines:]
        
        # Zapisz z powrotem
        with open(log_file, 'w', encoding='utf-8') as f:
            f.writelines(filtered_lines)
        
        new_size_mb = os.path.getsize(log_file) / (1024 * 1024)
        
        stats = {
            "status": "success",
            "original_size_mb": file_size_mb,
            "new_size_mb": new_size_mb,
            "original_lines": original_lines,
            "remaining_lines": len(filtered_lines),
            "file": log_file
        }
        
        print(f"✅ Zmniejszono plik z {file_size_mb:.2f}MB do {new_size_mb:.2f}MB")
        print(f"   • Usunięto: {original_lines - len(filtered_lines)} linii")
        print(f"   • Pozostało: {len(filtered_lines)} linii")
        
        return stats
        
    except Exception as e:
        error_msg = f"Błąd podczas czyszczenia po rozmiarze: {e}"
        print(f"❌ {error_msg}")
        return {"status": "error", "message": error_msg}


def get_log_info(log_file="aliexpress_tracker.log"):
    """
    Zwraca informacje o pliku logów
    
    Args:
        log_file (str): Nazwa pliku z logami
        
    Returns:
        dict: Informacje o pliku
    """
    if not os.path.exists(log_file):
        return {"status": "error", "message": f"Plik {log_file} nie istnieje"}
    
    try:
        # Rozmiar pliku
        file_size_bytes = os.path.getsize(log_file)
        file_size_mb = file_size_bytes / (1024 * 1024)
        
        # Data modyfikacji
        mod_time = os.path.getmtime(log_file)
        mod_date = datetime.fromtimestamp(mod_time)
        
        # Liczba linii
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        
        # Znajdź najstarszą i najnowszą datę w logach
        oldest_date = None
        newest_date = None
        
        for line in lines:
            try:
                if len(line) >= 19 and line[4] == '-' and line[7] == '-':
                    date_str = line[:19]
                    log_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                    
                    if oldest_date is None or log_date < oldest_date:
                        oldest_date = log_date
                    if newest_date is None or log_date > newest_date:
                        newest_date = log_date
            except ValueError:
                continue
        
        info = {
            "status": "success",
            "file": log_file,
            "size_bytes": file_size_bytes,
            "size_mb": round(file_size_mb, 2),
            "total_lines": total_lines,
            "modified": mod_date.strftime('%Y-%m-%d %H:%M:%S'),
            "oldest_log": oldest_date.strftime('%Y-%m-%d %H:%M:%S') if oldest_date else "Brak",
            "newest_log": newest_date.strftime('%Y-%m-%d %H:%M:%S') if newest_date else "Brak"
        }
        
        # Oblicz wiek najstarszego loga
        if oldest_date:
            age_days = (datetime.now() - oldest_date).days
            info["oldest_age_days"] = age_days
        
        return info
        
    except Exception as e:
        return {"status": "error", "message": f"Błąd podczas analizy pliku: {e}"}


def auto_cleanup_logs(log_file="aliexpress_tracker.log", max_days=3, max_size_mb=50):
    """
    Automatyczne czyszczenie - usuwa stare logi ALBO gdy plik jest za duży
    
    Args:
        log_file (str): Nazwa pliku z logami
        max_days (int): Maksymalny wiek logów w dniach
        max_size_mb (int): Maksymalny rozmiar pliku w MB
        
    Returns:
        dict: Wynik czyszczenia
    """
    print(f"🔍 Sprawdzanie pliku logów: {log_file}")
    
    # Sprawdź informacje o pliku
    info = get_log_info(log_file)
    
    if info["status"] == "error":
        return info
    
    print(f"📊 Plik: {info['size_mb']}MB, {info['total_lines']} linii")
    
    # Sprawdź czy potrzebne jest czyszczenie
    needs_cleanup = False
    cleanup_reason = []
    
    # Sprawdź wiek
    if "oldest_age_days" in info and info["oldest_age_days"] > max_days:
        needs_cleanup = True
        cleanup_reason.append(f"logi starsze niż {max_days} dni")
    
    # Sprawdź rozmiar
    if info["size_mb"] > max_size_mb:
        needs_cleanup = True
        cleanup_reason.append(f"rozmiar > {max_size_mb}MB")
    
    if not needs_cleanup:
        msg = f"Plik nie wymaga czyszczenia (wiek: {info.get('oldest_age_days', 0)} dni, rozmiar: {info['size_mb']}MB)"
        print(f"✅ {msg}")
        return {"status": "ok", "message": msg, "info": info}
    
    print(f"⚠️ Wymagane czyszczenie: {', '.join(cleanup_reason)}")
    
    # Wykonaj czyszczenie po dacie (preferowane)
    if any("dni" in reason for reason in cleanup_reason):
        return cleanup_old_logs(log_file, max_days)
    # Lub po rozmiarze
    else:
        return cleanup_logs_by_size(log_file, max_size_mb)


if __name__ == "__main__":
    """Uruchomienie bezpośrednie do testowania"""
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "info":
            # python3 log_cleaner.py info
            info = get_log_info()
            print("\n=== INFORMACJE O PLIKU LOGÓW ===")
            if info["status"] == "success":
                print(f"Plik: {info['file']}")
                print(f"Rozmiar: {info['size_mb']} MB ({info['size_bytes']} bajtów)")
                print(f"Liczba linii: {info['total_lines']}")
                print(f"Ostatnia modyfikacja: {info['modified']}")
                print(f"Najstarszy log: {info['oldest_log']}")
                print(f"Najnowszy log: {info['newest_log']}")
                if "oldest_age_days" in info:
                    print(f"Wiek najstarszego loga: {info['oldest_age_days']} dni")
            else:
                print(f"Błąd: {info['message']}")
                
        elif command == "clean":
            # python3 log_cleaner.py clean [dni]
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 3
            cleanup_old_logs(days=days)
            
        elif command == "auto":
            # python3 log_cleaner.py auto
            auto_cleanup_logs()
            
        else:
            print("Użycie:")
            print("  python3 log_cleaner.py info    - informacje o pliku")
            print("  python3 log_cleaner.py clean [dni] - usuń logi starsze niż X dni")
            print("  python3 log_cleaner.py auto    - automatyczne czyszczenie")
    else:
        # Domyślne czyszczenie
        auto_cleanup_logs()