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
        """Wysyła ładne powiadomienie o zmianie statusu"""
        status = order_data.get('status', 'nieznany')
        user = order_data.get('user_key', 'nieznany')
        carrier = order_data.get('carrier', 'Inny')
        pkg = order_data.get('package_number', 'brak')
        
        icon = "📦"
        if status == "delivered": icon = "✅"
        elif status == "pickup": icon = "🏃"
        elif status == "shipment_sent": icon = "🚚"
        
        msg = (
            f"{icon} <b>Aktualizacja Paczki!</b>\n"
            f"👤 <b>Dla:</b> {user}\n"
            f"🚛 <b>Przewoźnik:</b> {carrier}\n"
            f"📊 <b>Status:</b> {status}\n"
            f"🔢 <b>Nr:</b> <code>{pkg}</code>"
        )
        self.send_message(msg)