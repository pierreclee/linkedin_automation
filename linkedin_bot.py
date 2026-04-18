#!/usr/bin/env python3
"""CLI principal du bot LinkedIn.

Usage:
    python linkedin_bot.py --login                                # Login manuel (Windows uniquement)
    python linkedin_bot.py --run                                  # Run complet (cron)
    python linkedin_bot.py --add-post <url>                       # Ajouter un post
    python linkedin_bot.py --remove-post <url>                    # Supprimer un post
    python linkedin_bot.py --list-posts                           # Lister les posts
    python linkedin_bot.py --enable                               # Activer le bot
    python linkedin_bot.py --disable                              # Désactiver le bot
    python linkedin_bot.py --status                               # Afficher l'état
"""
import argparse
import os
import random
import time

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

import db
import messenger
import scraper
import telegram as tg

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(__file__), "linkedin.db")
SESSION_PATH = os.path.join(os.path.dirname(__file__), "session", "state.json")


def cmd_login():
    """Ouvre un navigateur visible pour le login manuel LinkedIn.
    Sauvegarde la session dans session/state.json.
    À exécuter sur Windows (pas sur le Pi).
    """
    os.makedirs(os.path.dirname(SESSION_PATH), exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://www.linkedin.com/login")
        print("Connecte-toi manuellement dans le navigateur.")
        print("Appuie sur Entrée ici quand tu es sur le fil d'actualité...")
        input()
        context.storage_state(path=SESSION_PATH)
        browser.close()
    print(f"Session sauvegardée dans {SESSION_PATH}")
    print("Transfère ce fichier sur le Pi avec :")
    print(f"  scp {SESSION_PATH} pi@<ip>:~/bot-linkedin-automation/session/state.json")


def cmd_run():
    """Run principal : accepter connexions, scraper posts, envoyer messages."""
    db.init_db(DB_PATH)

    if db.get_config("enabled", DB_PATH) != "1":
        print("[run] Bot désactivé, exit.")
        return

    max_connections = random.randint(20, 30)
    max_messages = random.randint(20, 30)
    print(f"[run] Limites du run : {max_connections} connexions, {max_messages} messages")

    run_id = db.start_run(max_connections, max_messages, DB_PATH)
    connections_accepted = 0
    mp_sent = 0
    comment_replies_sent = 0
    errors = []

    # Flag pour supprimer le rapport Telegram si une alerte session-expirée a déjà été envoyée
    session_expired = False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(storage_state=SESSION_PATH)
            page = context.new_page()

            if not scraper.verify_session(page):
                tg.send_message(
                    "⚠️ Session LinkedIn expirée.\n"
                    "Lance <code>python linkedin_bot.py --login</code> sur Windows "
                    "puis retransfère <code>session/state.json</code> sur le Pi."
                )
                errors.append("Session expirée")
                session_expired = True
                return

            # 1. Accepter les connexions
            print("[run] Acceptation des connexions...")
            accepted_urls = messenger.accept_pending_connections(page, max_connections)
            for url in accepted_urls:
                db.add_accepted_connection(url, DB_PATH)
            connections_accepted = len(accepted_urls)
            print(f"[run] {connections_accepted} connexions acceptées")

            # 2. Scraper les posts actifs
            active_posts = db.get_active_posts(DB_PATH)
            for post in active_posts:
                try:
                    scraper.scrape_post_engagements(page, post["url"], DB_PATH)
                except Exception as e:
                    err = f"Scraping {post['url']}: {e}"
                    print(f"[run] ERREUR : {err}")
                    errors.append(err)
                time.sleep(random.uniform(4, 8))

            # 3. Traiter les engagements par priorité
            pending = db.get_pending_engagements(DB_PATH)
            print(f"[run] {len(pending)} engagements à traiter")

            for eng in pending:
                priority = eng["priority"]
                first_name = eng["first_name"] or ""

                if priority in (1, 2):
                    if mp_sent >= max_messages:
                        continue
                    if not eng["msg_mp"]:
                        continue
                    try:
                        message = eng["msg_mp"].format(
                            first_name=first_name,
                            post_url=eng["post_url"],
                            reposted="oui" if eng["reposted"] else "non",
                        )
                        messenger.send_mp(page, eng["profile_url"], message)
                        db.mark_action_taken(eng["profile_url"], eng["post_url"], "mp_sent", DB_PATH)
                        mp_sent += 1
                        print(f"[run] MP envoyé à {eng['profile_url']}")
                        time.sleep(random.uniform(8, 30))
                    except Exception as e:
                        err = f"MP {eng['profile_url']}: {e}"
                        print(f"[run] ERREUR : {err}")
                        errors.append(err)

                elif priority == 3:
                    if not eng["msg_comment_reply"] or not eng["comment_url"]:
                        continue
                    try:
                        message = eng["msg_comment_reply"].format(
                            first_name=first_name,
                            post_url=eng["post_url"],
                        )
                        messenger.reply_to_comment(page, eng["comment_url"], message)
                        db.mark_action_taken(
                            eng["profile_url"], eng["post_url"], "comment_replied", DB_PATH
                        )
                        comment_replies_sent += 1
                        print(f"[run] Réponse commentaire envoyée à {eng['profile_url']}")
                        time.sleep(random.uniform(8, 30))
                    except Exception as e:
                        err = f"Reply {eng['profile_url']}: {e}"
                        print(f"[run] ERREUR : {err}")
                        errors.append(err)

            browser.close()

    except Exception as e:
        err = f"Fatal: {e}"
        print(f"[run] ERREUR FATALE : {err}")
        errors.append(err)

    finally:
        db.finish_run(run_id, connections_accepted, mp_sent, comment_replies_sent,
                      "; ".join(errors) if errors else None, DB_PATH)

        report = (
            f"✅ <b>Run LinkedIn terminé</b>\n"
            f"🔗 {connections_accepted} connexions acceptées\n"
            f"💬 {mp_sent} MP envoyés\n"
            f"💭 {comment_replies_sent} réponses commentaires\n"
        )
        if errors:
            report += f"⚠️ {len(errors)} erreur(s) : {'; '.join(errors[:3])}"
        else:
            report += "✓ Aucune erreur"
        if not session_expired:
            tg.send_message(report)
        print(report)


def cmd_add_post(url: str, msg_mp: str, msg_comment_reply: str):
    db.init_db(DB_PATH)
    db.add_post(url, msg_mp, msg_comment_reply, DB_PATH)
    text = f"Post ajouté : {url}"
    print(text)
    return text


def cmd_remove_post(url: str):
    db.init_db(DB_PATH)
    db.remove_post(url, DB_PATH)
    text = f"Post supprimé (et engagements associés) : {url}"
    print(text)
    return text


def cmd_list_posts():
    db.init_db(DB_PATH)
    posts = db.list_posts(DB_PATH)
    if not posts:
        text = "Aucun post enregistré."
        print(text)
        return text
    lines = []
    for p in posts:
        status = "✓ actif" if p["active"] else "✗ inactif"
        lines.append(f"[{status}] {p['url']}")
        msg_mp = p['msg_mp'] or ''
        msg_reply = p['msg_comment_reply'] or ''
        lines.append(f"  msg_mp          : {msg_mp[:60]}{'...' if len(msg_mp) > 60 else ''}")
        lines.append(f"  msg_comment_reply: {msg_reply[:60]}{'...' if len(msg_reply) > 60 else ''}")
    text = "\n".join(lines)
    print(text)
    return text


def cmd_enable():
    db.init_db(DB_PATH)
    db.set_config("enabled", "1", DB_PATH)
    text = "Bot activé."
    print(text)
    return text


def cmd_disable():
    db.init_db(DB_PATH)
    db.set_config("enabled", "0", DB_PATH)
    text = "Bot désactivé."
    print(text)
    return text


def cmd_status():
    db.init_db(DB_PATH)
    enabled = db.get_config("enabled", DB_PATH)
    posts = db.get_active_posts(DB_PATH)
    last = db.get_last_run(DB_PATH)
    lines = [
        f"État      : {'✓ activé' if enabled == '1' else '✗ désactivé'}",
        f"Posts actifs : {len(posts)}",
    ]
    if last:
        lines.append(f"Dernier run : {last['started_at']}")
        lines.append(
            f"  connexions={last['connections_accepted']} mp={last['mp_sent']} replies={last['comment_replies_sent']}"
        )
        if last["errors"]:
            lines.append(f"  erreurs : {last['errors']}")
    else:
        lines.append("Aucun run enregistré.")
    text = "\n".join(lines)
    print(text)
    return text


def main():
    parser = argparse.ArgumentParser(description="LinkedIn Bot Automation")
    parser.add_argument("--login", action="store_true", help="Login manuel (Windows uniquement)")
    parser.add_argument("--run", action="store_true", help="Lancer le run complet")
    parser.add_argument("--add-post", metavar="URL", help="Ajouter un post à scanner")
    parser.add_argument("--msg-mp", metavar="MSG", help="Template MP (avec --add-post)")
    parser.add_argument("--msg-reply", metavar="MSG", help="Template réponse commentaire (avec --add-post)")
    parser.add_argument("--setmsg", metavar="URL", help="Modifier les templates d'un post existant")
    parser.add_argument("--remove-post", metavar="URL", help="Supprimer un post")
    parser.add_argument("--list-posts", action="store_true", help="Lister les posts trackés")
    parser.add_argument("--enable", action="store_true", help="Activer le bot")
    parser.add_argument("--disable", action="store_true", help="Désactiver le bot")
    parser.add_argument("--status", action="store_true", help="Afficher l'état du bot")

    args = parser.parse_args()

    if args.login:
        cmd_login()
    elif args.run:
        cmd_run()
    elif args.add_post:
        msg_mp = args.msg_mp or input("Message MP (liked+commented+connecté) : ")
        msg_reply = args.msg_reply or input("Réponse commentaire (non connecté) : ")
        cmd_add_post(args.add_post, msg_mp, msg_reply)
    elif args.setmsg:
        msg_mp = args.msg_mp or input("Nouveau message MP : ")
        msg_reply = args.msg_reply or input("Nouvelle réponse commentaire : ")
        db.update_post_templates(args.setmsg, msg_mp, msg_reply, DB_PATH)
        print(f"Templates mis à jour pour : {args.setmsg}")
    elif args.remove_post:
        cmd_remove_post(args.remove_post)
    elif args.list_posts:
        cmd_list_posts()
    elif args.enable:
        cmd_enable()
    elif args.disable:
        cmd_disable()
    elif args.status:
        cmd_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
