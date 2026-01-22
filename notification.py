import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import config
import logging

def send_pickup_notification(order_data):
    """Wysyła powiadomienie o paczce gotowej do odbioru, jeśli włączone w configu."""
    
    # 1. Sprawdzenie flagi w configu
    # Używamy getattr, żeby kod nie wyrzucił błędu, jeśli zapomnisz dodać zmienną do configu
    if not getattr(config, 'SEND_EMAIL_NOTIFICATIONS', False):
        logging.info("🔕 Powiadomienia mailowe są wyłączone w configu. Pomijam wysyłkę.")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = config.GMAIL_EMAIL
        msg['To'] = config.NOTIFICATION_EMAIL
        msg['Subject'] = f"Paczka gotowa do odbioru: {order_data.get('package_number', 'brak numeru')}"
        
        # Pobieranie danych z bezpiecznymi wartościami domyślnymi
        pkg_num = order_data.get('package_number', 'brak numeru')
        code = order_data.get('pickup_code') or order_data.get('receive_code', 'brak kodu')
        deadline = order_data.get('pickup_deadline') or order_data.get('time_to_receive', 'brak terminu')
        phone = order_data.get('phone_number', 'brak numeru')
        # Próba pobrania adresu z różnych możliwych kluczy
        address = (
            order_data.get('pickup_location') or 
            order_data.get('pickup_address') or 
            order_data.get('delivery_address', 'brak adresu')
        )

        body = f"""
        Witaj!
        
        Twoja paczka o numerze {pkg_num} jest gotowa do odbioru.
        
        Szczegóły odbioru:
        --------------------------
        Kod odbioru:    {code}
        Termin odbioru: {deadline}
        Miejsce:        {address}
        Telefon:        {phone}
        --------------------------
        
        Pozdrawiamy,
        Twój Bot Śledzący
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Połączenie z serwerem SMTP i wysłanie maila
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(config.GMAIL_EMAIL, config.GMAIL_PASSWORD)
        text = msg.as_string()
        server.sendmail(config.GMAIL_EMAIL, config.NOTIFICATION_EMAIL, text)
        server.quit()
        
        logging.info(f"📧 Wysłano powiadomienie mailowe o paczce {pkg_num}")
        return True
        
    except Exception as e:
        logging.error(f"❌ Błąd podczas wysyłania powiadomienia mailowego: {e}")
        return False