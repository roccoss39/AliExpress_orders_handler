import logging
from email_handler import EmailHandler
from sheets_handler import SheetsHandler
from carriers_sheet_handlers import EmailAvailabilityManager

#example use: python3 main.py --reprocess-email jan.kowalski@interia.pl --limit 10
def run_reprocess(target_email, limit=None, subject_contains: str = ""):
    """
    Wymusza ponowne pobranie maili dla konkretnego adresu.
    """
    logging.info(f"🛠️ URUCHAMIAM TRYB REPROCESS DLA: {target_email}")
    if limit:
        logging.info(f"🔢 Limit: {limit} zamówień")

    subject_contains_norm = (subject_contains or "").strip().lower()
    if subject_contains_norm:
        logging.info(f"🔎 Filtr tematu (subject_contains): '{subject_contains_norm}'")
    
    email_handler = EmailHandler()
    sheets_handler = SheetsHandler()
    
    sheets_handler.email_handler = email_handler
    
    if not sheets_handler.connect():
        logging.error("❌ Błąd połączenia z arkuszem.")
        return

    # 1. Pobierz maile z ostatnich 60 dni
    emails = email_handler.fetch_specific_account_history(target_email, days_back=60)
    
    if not emails:
        logging.warning("Brak maili do przetworzenia.")
        return

    logging.info(f"Pobrano {len(emails)} maili. Analiza...")
    processed_count = 0 
    
    # 2. Przetwarzaj maile
    for source, msg in emails:
        if limit and processed_count >= limit:
            logging.info(f"🛑 Osiągnięto limit {limit}.")
            break

        try:
            email_date = email_handler.extract_email_date(msg)
            raw_subject = msg.get("Subject", "")
            subject = email_handler.decode_email_subject(raw_subject)

            # Opcjonalny filtr po fragmencie tematu (case-insensitive)
            if subject_contains_norm and subject_contains_norm not in subject.lower():
                continue
            
            # Szybki filtr po słowach kluczowych
            keywords = ["paczka", "zamówienie", "order", "delivery", "dostawa", "odbierz", "nadana", "status", "inpost", "dhl", "dpd", "gls", "poczta"]
            if not any(k in subject.lower() for k in keywords):
                continue

            body = email_handler.get_email_body(msg)
            
            # Wyciągnij odbiorcę
            import re
            to_header = msg.get("To", "")
            match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', to_header)
            recipient = match.group(0) if match else target_email
            
            logging.info(f"🔍 Analiza: {email_date} | {subject[:50]}...")
            
            # Wymuś przetwarzanie (force_process=True)
            order_data = email_handler.analyze_email(
                subject, body, recipient, source, 
                recipient_name=recipient, email_message=msg, email_date=email_date,
                force_process=True 
            )
            
            if order_data:
                # Uzupełnij datę jeśli brakuje
                if not order_data.get("email_date") and email_date:
                    order_data["email_date"] = email_date
                
                # Zapisz mapowania
                status_lower = str(order_data.get('status', '') or '').lower()
                is_final = any(k in status_lower for k in ['delivered', 'dostarczon', 'odebran', 'picked up', 'zwrócon', 'zwrocon', 'zamknięt', 'zamkniet'])

                user_key = order_data.get("user_key")
                if user_key and not is_final:
                    if order_data.get("order_number"):
                        email_handler._save_user_order_mapping(user_key, order_data["order_number"])
                    if order_data.get("package_number"):
                        email_handler._save_user_package_mapping(user_key, order_data["package_number"])

                # Wybierz metodę aktualizacji arkusza
                if hasattr(sheets_handler, 'handle_order_update'):
                    sheets_handler.handle_order_update(order_data)
                else:
                    # Fallback dla starszych wersji sheets_handler
                    carrier = sheets_handler.carriers.get(order_data.get("carrier", "InPost"))
                    if carrier and hasattr(carrier, 'process_notification'):
                        carrier.process_notification(order_data)
                    else:
                        sheets_handler._direct_create_row(order_data)
                
                processed_count += 1

                # Jeśli w reprocess trafiliśmy na status końcowy, to dalsze maile historyczne
                # mogą tylko "reanimować" mappingi i robić szum. Kończymy reprocess dla tego konta.
                status_lower = str(order_data.get('status', '') or '').lower()
                is_final = any(k in status_lower for k in ['delivered', 'dostarczon', 'odebran', 'picked up', 'zwrócon', 'zwrocon', 'zamknięt', 'zamkniet'])
                if is_final:
                    logging.info(f"🛑 REPROCESS: wykryto status końcowy ({status_lower}). Kończę dalsze przetwarzanie historii dla {target_email}.")
                    break
                
        except Exception as e:
            logging.error(f"Błąd przy reprocess maila: {e}")

    # Aktualizacja kolorów na koniec
    try:
        logging.info("🎨 REPROCESS: Aktualizacja statusów w Accounts...")
        EmailAvailabilityManager(sheets_handler).check_email_availability()
    except Exception as e:
        logging.error(f"❌ Błąd aktualizacji kolorów: {e}")
            
    logging.info(f"🏁 Zakończono reprocess. Przetworzono: {processed_count} zamówień.")