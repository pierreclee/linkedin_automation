import time
import random
from playwright.sync_api import Page


def accept_pending_connections(page: Page, max_count: int) -> list[str]:
    """Accepte jusqu'à max_count demandes de connexion en attente.
    Retourne la liste des profile_url acceptés.
    """
    page.goto(
        "https://www.linkedin.com/mynetwork/invitation-manager/",
        wait_until="domcontentloaded",
        timeout=30000,
    )
    time.sleep(random.uniform(2, 4))

    accepted = []
    try:
        for _ in range(max_count):
            accept_btn = page.query_selector(
                "button[aria-label*='Accepter'], "
                "button[data-control-name='accept']"
            )
            if not accept_btn or not accept_btn.is_visible():
                break

            # Récupérer l'URL du profil avant d'accepter
            card = accept_btn.evaluate_handle(
                "(el) => el.closest('li, .invitation-card, .mn-invitation-card')"
            )
            profile_link = card.as_element().query_selector("a[href*='/in/']") if card else None
            profile_url = None
            if profile_link:
                profile_url = profile_link.get_attribute("href").split("?")[0]

            accept_btn.click()
            time.sleep(random.uniform(3, 8))

            if profile_url:
                accepted.append(profile_url)

    except Exception as e:
        print(f"[messenger] accept_pending_connections erreur : {e}")

    return accepted


def send_mp(page: Page, profile_url: str, message: str) -> None:
    """Envoie un message privé à un profil LinkedIn connecté."""
    page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(random.uniform(2, 4))

    # Cliquer sur le bouton "Message"
    msg_btn = page.query_selector(
        "button[aria-label*='Message'], "
        "a[data-control-name='message']"
    )
    if not msg_btn:
        raise ValueError(f"Bouton Message non trouvé pour {profile_url}")
    msg_btn.click()
    time.sleep(random.uniform(1, 2))

    # Saisir le message
    input_box = page.wait_for_selector(
        ".msg-form__contenteditable, "
        "div[role='textbox'][aria-label*='message' i]",
        timeout=8000,
    )
    input_box.click()
    # Simuler une frappe humaine caractère par caractère
    for char in message:
        input_box.type(char, delay=random.randint(30, 80))
    time.sleep(random.uniform(1, 3))

    # Envoyer
    send_btn = page.query_selector(
        "button.msg-form__send-button, "
        "button[type='submit'][aria-label*='Envoyer' i]"
    )
    if not send_btn:
        raise ValueError(f"Bouton Envoyer non trouvé pour {profile_url}")
    send_btn.click()
    time.sleep(random.uniform(1, 2))

    # Fermer la fenêtre de message
    close_btn = page.query_selector(
        "button.msg-overlay-bubble-header__control--close, "
        "button[aria-label*='Fermer' i]"
    )
    if close_btn:
        close_btn.click()


def reply_to_comment(page: Page, comment_url: str, message: str) -> None:
    """Répond à un commentaire LinkedIn spécifique."""
    page.goto(comment_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(random.uniform(2, 4))

    # Trouver le bouton "Répondre" du commentaire ciblé
    reply_btn = page.query_selector(
        "button.comments-comment-item__reply-action-button, "
        "button[aria-label*='Répondre' i]"
    )
    if not reply_btn:
        raise ValueError(f"Bouton Répondre non trouvé pour {comment_url}")
    reply_btn.click()
    time.sleep(random.uniform(1, 2))

    reply_box = page.wait_for_selector(
        ".comments-comment-texteditor, "
        "div.ql-editor[contenteditable='true']",
        timeout=8000,
    )
    reply_box.click()
    for char in message:
        reply_box.type(char, delay=random.randint(30, 80))
    time.sleep(random.uniform(1, 2))

    submit_btn = page.query_selector(
        "button.comments-comment-texteditor__submitButton, "
        "button[type='submit']"
    )
    if not submit_btn:
        raise ValueError(f"Bouton Soumettre non trouvé pour {comment_url}")
    submit_btn.click()
    time.sleep(random.uniform(1, 2))
