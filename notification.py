import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import config
import logging

def send_pickup_notification(order_data):
    """Wysyła powiadomienie o paczce gotowej do odbioru"""
    try:
        msg = MIMEMultipart()
        msg['From'] = config.GMAIL_EMAIL
        msg['To'] = config.NOTIFICATION_EMAIL
        msg['Subject'] = f"Paczka gotowa do odbioru: {order_data.get('package_number', 'brak numeru')}"
        
        body = f"""
        Witaj!
        
        Twoja paczka o numerze {order_data.get('package_number', 'brak numeru')} jest gotowa do odbioru.
        
        Szczegóły odbioru:
        - Kod odbioru: {order_data.get('receive_code', 'brak kodu')}
        - Termin odbioru: {order_data.get('time_to_receive', 'brak terminu')}
        - Numer telefonu: {order_data.get('phone_number', 'brak numeru')}
        - Miejsce odbioru: {order_data.get('delivery_address', 'brak adresu')}
        
        Pozdrawiamy,
        System śledzenia zamówień z AliExpress
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Połączenie z serwerem SMTP i wysłanie maila
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(config.GMAIL_EMAIL, config.GMAIL_PASSWORD)
        text = msg.as_string()
        server.sendmail(config.GMAIL_EMAIL, config.NOTIFICATION_EMAIL, text)
        server.quit()
        
        logging.info(f"Wysłano powiadomienie o paczce {order_data.get('package_number', 'brak numeru')}")
        return True
    except Exception as e:
        logging.info(f"Błąd podczas wysyłania powiadomienia: {e}")
        return False