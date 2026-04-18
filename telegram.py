import json
import os
import urllib.request

from dotenv import load_dotenv

load_dotenv()


def send_message(text, bot_token=None, chat_id=None):
    """Envoie un message texte via l'API Telegram HTTP."""
    token = bot_token or os.environ["TELEGRAM_BOT_TOKEN"]
    cid = chat_id or os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": cid, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10):
        pass
