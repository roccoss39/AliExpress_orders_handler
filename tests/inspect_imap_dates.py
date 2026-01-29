#!/usr/bin/env python3
"""Diagnostyka dat z IMAP.

Cel:
- sprawdzić co realnie zwraca IMAP (Date/Received/itd.)
- porównać z INTERNALDATE (z fetch)

Użycie:
  python3 tests/inspect_imap_dates.py --email ujebiecie.mnie@interia.pl --days 60 --limit 10

Wymaga poprawnie ustawionych zmiennych środowiskowych (hasła) lub fallbacku w configu.
"""

import argparse
import re
import logging

from email_handler import EmailHandler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def _parse_internaldate(fetch_response_part: bytes) -> str | None:
    """Wyciąga wartość INTERNALDATE z surowej odpowiedzi imaplib.fetch."""
    try:
        # Przykład: b'12 (INTERNALDATE "29-Jan-2026 12:04:41 +0100" RFC822 {....}'
        m = re.search(rb'INTERNALDATE\s+"([^"]+)"', fetch_response_part)
        if not m:
            return None
        return m.group(1).decode('utf-8', errors='replace')
    except Exception:
        return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--email', required=True)
    p.add_argument('--days', type=int, default=60)
    p.add_argument('--limit', type=int, default=10)
    args = p.parse_args()

    eh = EmailHandler()

    # znajdź config (albo fallback w fetch_specific_account_history)
    emails = eh.fetch_specific_account_history(args.email, days_back=args.days)
    if not emails:
        print('Brak maili')
        return

    # ręcznie pobierz INTERNALDATE (bo fetch_specific_account_history obecnie bierze tylko RFC822)
    # dlatego łączymy się ponownie i robimy fetch.
    target = args.email.strip().lower()
    found_cfg = None
    import config
    for cfg in getattr(config, 'ALL_EMAIL_CONFIGS', []):
        if (cfg.get('email') or '').strip().lower() == target:
            found_cfg = cfg
            break

    if not found_cfg:
        if getattr(config, 'DEFAULT_EMAIL_PASSWORD', None):
            found_cfg = {
                'email': target,
                'password': config.DEFAULT_EMAIL_PASSWORD,
                'source': 'interia',
            }
        else:
            raise SystemExit('Brak konfiguracji i brak DEFAULT_EMAIL_PASSWORD')

    client = eh.connect_to_email_account(found_cfg)
    client.select('INBOX')

    # Pobierz UIDy z okresu
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(days=args.days)
    date_string = cutoff.strftime('%d-%b-%Y')
    status, messages = client.search(None, f'(SINCE "{date_string}")')
    ids = messages[0].split() if status == 'OK' and messages and messages[0] else []
    ids = ids[: args.limit]

    print(f"Znaleziono {len(ids)} wiadomości (pokażę do {args.limit})")

    for num in ids:
        res, msg_data = client.fetch(num, '(RFC822 INTERNALDATE)')
        if res != 'OK' or not msg_data:
            continue

        # msg_data zwykle: [(b'..', b'raw bytes'), b')']
        internal = None
        raw_bytes = None
        for part in msg_data:
            if isinstance(part, tuple) and len(part) == 2:
                meta, payload = part
                raw_bytes = payload
                internal = _parse_internaldate(meta)

        if raw_bytes is None:
            continue

        import email
        msg = email.message_from_bytes(raw_bytes)

        date_h = msg.get('Date')
        received = msg.get_all('Received') or []

        print('\n' + '=' * 80)
        print(f"IMAP id={num.decode()} INTERNALDATE={internal}")
        print(f"Header Date: {date_h}")
        print(f"Received count: {len(received)}")
        if received:
            print(f"Received[0] (first): {str(received[0])[:200]}...")
            print(f"Received[-1] (last):  {str(received[-1])[:200]}...")

        # pokaż listę nagłówków
        header_names = [k for (k, _) in msg.items()]
        print(f"Headers: {header_names}")

    try:
        client.close()
        client.logout()
    except Exception:
        pass


if __name__ == '__main__':
    main()
