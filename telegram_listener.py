#!/usr/bin/env python3
"""Listener Telegram pour le bot LinkedIn.

Tourne en permanence (service systemd), reçoit les commandes /linkedin
et appelle les fonctions de linkedin_bot.py.
"""
import json
import os
import threading
import urllib.request

from dotenv import load_dotenv

import db
import telegram as tg
from linkedin_bot import (
    DB_PATH,
    cmd_add_post,
    cmd_disable,
    cmd_enable,
    cmd_list_posts,
    cmd_remove_post,
    cmd_run,
    cmd_status,
)

load_dotenv()

HELP_TEXT = """Commandes disponibles :
/linkedin help — Afficher cette aide
/linkedin add &lt;url&gt; — Ajouter un post à scanner
/linkedin list — Lister les posts trackés
/linkedin remove &lt;url&gt; — Supprimer un post et ses données
/linkedin setmsg &lt;url&gt; — Modifier les templates d'un post
/linkedin on — Activer le bot
/linkedin off — Désactiver le bot
/linkedin status — État et stats du dernier run
/linkedin run — Forcer un run immédiat"""


def get_updates(offset: int, token: str) -> list:
    """Long-polling sur l'API Telegram. Retourne [] en cas d'erreur réseau."""
    url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=30&offset={offset}"
    try:
        with urllib.request.urlopen(url, timeout=35) as resp:
            data = json.loads(resp.read())
            return data.get("result", [])
    except Exception:
        return []


def handle_message(text: str, pending_state: dict) -> tuple:
    """Route la commande et retourne (réponse, nouvel_état).

    Retourne (None, pending_state) si le message doit être ignoré.
    """
    text = text.strip()

    # Flow multi-étapes en cours — message non-commande
    if pending_state and not text.startswith("/linkedin"):
        step = pending_state["step"]

        if step == "add_msg_mp":
            pending_state = dict(pending_state)
            pending_state["msg_mp"] = text
            pending_state["step"] = "add_msg_reply"
            return "Réponse en commentaire (pour les non connectés) ?", pending_state

        if step == "add_msg_reply":
            pending_state = dict(pending_state)
            pending_state["msg_reply"] = text
            pending_state["step"] = "add_keyword"
            return "Mot-clé déclencheur (insensible à la casse) ?", pending_state

        if step == "add_keyword":
            result = cmd_add_post(
                pending_state["url"], pending_state["msg_mp"], pending_state["msg_reply"], text
            )
            return result, {}

        if step == "setmsg_msg_mp":
            pending_state = dict(pending_state)
            pending_state["msg_mp"] = text
            pending_state["step"] = "setmsg_msg_reply"
            return "Nouvelle réponse en commentaire ?", pending_state

        if step == "setmsg_msg_reply":
            pending_state = dict(pending_state)
            pending_state["msg_reply"] = text
            pending_state["step"] = "setmsg_keyword"
            return "Nouveau mot-clé déclencheur ?", pending_state

        if step == "setmsg_keyword":
            db.update_post_templates(
                pending_state["url"], pending_state["msg_mp"], pending_state["msg_reply"],
                DB_PATH, keyword=text
            )
            return "✅ Templates mis à jour.", {}

    # Ignorer les messages qui ne sont pas des commandes /linkedin
    if not text.startswith("/linkedin"):
        return None, pending_state

    # Router principal
    parts = text.split(maxsplit=2)
    sub = parts[1] if len(parts) > 1 else "help"
    arg = parts[2].strip() if len(parts) > 2 else ""

    if sub == "help":
        return HELP_TEXT, {}

    if sub == "status":
        return cmd_status(), {}

    if sub == "list":
        return cmd_list_posts(), {}

    if sub == "on":
        return cmd_enable(), {}

    if sub == "off":
        return cmd_disable(), {}

    if sub == "run":
        threading.Thread(target=cmd_run, daemon=True).start()
        return "⏳ Run lancé... Le rapport arrivera ici à la fin.", {}

    if sub == "add":
        if not arg:
            return "Usage : /linkedin add <url>", {}
        return "Message MP (pour les connectés qui ont liké+commenté) ?", {"step": "add_msg_mp", "url": arg}

    if sub == "remove":
        if not arg:
            return "Usage : /linkedin remove <url>", {}
        return cmd_remove_post(arg), {}

    if sub == "setmsg":
        if not arg:
            return "Usage : /linkedin setmsg <url>", {}
        return "Nouveau message MP ?", {"step": "setmsg_msg_mp", "url": arg}

    return f"Commande inconnue : {sub}. Tape /linkedin help.", {}


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = str(os.environ.get("TELEGRAM_CHAT_ID", ""))
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN non défini — vérifier .env")
    if not chat_id:
        raise ValueError("TELEGRAM_CHAT_ID non défini — vérifier .env")

    db.init_db(DB_PATH)

    offset = 0
    pending_state = {}

    print("[listener] Démarré. En attente de commandes Telegram...")

    while True:
        updates = get_updates(offset, token)
        for update in updates:
            offset = update["update_id"] + 1
            message = update.get("message", {})
            if not message:
                continue

            # Sécurité : ignorer les messages d'autres chats
            if str(message.get("chat", {}).get("id", "")) != chat_id:
                continue

            text = message.get("text", "")
            if not text:
                continue

            try:
                response, pending_state = handle_message(text, pending_state)
                if response:
                    tg.send_message(response)
            except Exception as exc:
                print(f"[listener] Erreur traitement message : {exc}")
                pending_state = {}
                tg.send_message(f"⚠️ Erreur interne : {exc}")


if __name__ == "__main__":
    main()
