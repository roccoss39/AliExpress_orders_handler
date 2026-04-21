import requests
import logging
import config

class TelegramNotifier:
    def __init__(self):
        self.enabled = getattr(config, 'ENABLE_TELEGRAM', False)
        self.token = getattr(config, 'TELEGRAM_BOT_TOKEN', "")
        self.chat_id = getattr(config, 'TELEGRAM_CHAT_ID', "")
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_message(self, message):
        """Wysyła wiadomość tekstową na Telegram"""
        if not self.enabled or not self.token or not self.chat_id:
            return

        try:
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML"  # Pozwala na pogrubienia itp.
            }
            response = requests.post(self.base_url, data=payload, timeout=10)
            
            if response.status_code != 200:
                logging.error(f"❌ Błąd wysyłania Telegrama: {response.text}")
        except Exception as e:
            logging.error(f"❌ Błąd połączenia z Telegramem: {e}")

    def send_startup_message(self):
        self.send_message("🚀 <b>AliExpress Tracker wystartował!</b>\nMonitorowanie aktywne.")

    def send_error_message(self, error_text):
        self.send_message(f"🔴 <b>KRYTYCZNY BŁĄD BOTA!</b>\n\n<code>{error_text}</code>\n\n<i>Bot spróbuje wstać lub zakończy pracę.</i>")

    def send_new_package_alert(self, order_data):
        """Wysyła ładne powiadomienie o zmianie statusu, uwzględniając globalny status usera i dane odbioru"""
        status = order_data.get('status', 'nieznany')
        user = order_data.get('user_key', 'nieznany')
        carrier = order_data.get('carrier', 'Inny')
        pkg = order_data.get('package_number', 'brak')

        # 1. Sprawdzamy status bana
        is_banned = order_data.get('refund_detected') is True
        if hasattr(self, 'user_mappings') and user in getattr(self, 'user_mappings', {}):
            if self.user_mappings[user].get("has_refund") is True:
                is_banned = True

        ban_status = "🔴 TAK (Konto spalone/Anulowano)" if is_banned else "🟢 Brak"
        
        icon = "📦"
        if status == "delivered": icon = "✅"
        elif status == "pickup": icon = "🏃"
        elif status == "shipment_sent": icon = "🚚"
        
        if is_banned: icon = "🚨"
        
        # 2. Budujemy podstawową wiadomość
        msg = (
            f"{icon} <b>Aktualizacja Paczki!</b>\n"
            f"👤 <b>Dla:</b> {user}\n"
            f"🚛 <b>Przewoźnik:</b> {carrier}\n"
            f"📊 <b>Status:</b> {status}\n"
            f"🔢 <b>Nr:</b> <code>{pkg}</code>\n"
        )
        
        # 3. Dodatkowe dane jeśli paczka jest do odbioru
        if status == "pickup":
            location = order_data.get('pickup_location') or order_data.get('delivery_address') or "Brak danych"
            pin = order_data.get('pickup_code')
            phone = order_data.get('phone_number') # Pobieramy numer telefonu
            qr = order_data.get('qr_code') or order_data.get('qr_link') or ""
            
            msg += f"\n📍 <b>Adres odbioru:</b> {location}\n"
            
            # Dodajemy telefon (jeśli jest)
            if phone:
                msg += f"📞 <b>Tel. do odbioru:</b> <code>{phone}</code>\n"
            
            # Dodajemy PIN (jeśli jest)
            if pin:
                msg += f"🔑 <b>Kod odbioru (PIN):</b> <code>{pin}</code>\n"
                
            # Dodajemy link do QR
            if qr:
                if qr.startswith("P|"):
                    qr = f"https://quickchart.io/qr?text={qr.replace('|', '%7C')}&size=200"
                msg += f"📱 <a href='{qr}'><b>Otwórz kod QR</b></a>\n"
                
        # 4. Dodajemy info o banie na samym dole
        msg += f"\n⚠️ <b>Ban na koncie:</b> {ban_status}"
        
        self.send_message(msg)

    def send_cancellation_notice(self, order_data):
        """Wysyła powiadomienie o anulowaniu zakupu i zwrocie."""
        user = order_data.get('user_key', 'nieznany')
        email_addr = order_data.get('email', 'brak')
        subject = order_data.get('subject', 'brak')
        msg = (
            "💸 <b>Anulowano zakup (BAN)</b>\n"
            f"👤 <b>Użytkownik:</b> {user}\n"
            f"📧 <b>Email:</b> {email_addr}\n"
            f"📝 <b>Tytuł:</b> {subject}\n\n"
            "<i>Wykryto zwrot. Profil użytkownika został oznaczony jako spalony.</i>"
        )
        self.send_message(msg)