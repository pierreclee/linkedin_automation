import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
import messenger


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("messenger.time.sleep", lambda *a: None)


def _make_page():
    """Crée un mock minimal de playwright Page."""
    page = MagicMock()
    page.goto.return_value = None
    page.wait_for_selector.return_value = MagicMock()
    return page


def test_send_mp_raises_when_no_message_button():
    page = _make_page()
    page.query_selector.return_value = None  # aucun bouton trouvé

    with pytest.raises(ValueError, match="Bouton Message non trouvé"):
        messenger.send_mp(page, "https://linkedin.com/in/alice", "Bonjour")


def test_send_mp_raises_when_no_send_button():
    page = _make_page()
    msg_btn = MagicMock()
    input_box = MagicMock()
    # Premier query_selector → msg_btn, deuxième → None (send button absent)
    page.query_selector.side_effect = [msg_btn, None]
    page.wait_for_selector.return_value = input_box

    with pytest.raises(ValueError, match="Bouton Envoyer non trouvé"):
        messenger.send_mp(page, "https://linkedin.com/in/alice", "Hi")


def test_reply_to_comment_raises_when_no_reply_button():
    page = _make_page()
    page.query_selector_all.return_value = []
    page.query_selector.return_value = None

    with pytest.raises(ValueError, match="Bouton Répondre non trouvé"):
        messenger.reply_to_comment(
            page,
            "https://linkedin.com/posts/user?commentUrn=urn%3Ali%3Acomment%3A1",
            "Bonjour",
        )


def test_reply_to_comment_raises_when_no_submit_button():
    page = _make_page()
    reply_btn = MagicMock()
    reply_box = MagicMock()
    # query_selector_all → no articles matching URN
    page.query_selector_all.return_value = []
    # query_selector: 1st call → reply_btn, 2nd call → None (submit absent)
    page.query_selector.side_effect = [reply_btn, None]
    page.wait_for_selector.return_value = reply_box

    with pytest.raises(ValueError, match="Bouton Soumettre non trouvé"):
        messenger.reply_to_comment(
            page,
            "https://linkedin.com/posts/user?commentUrn=urn%3Ali%3Acomment%3A1",
            "Bonjour",
        )


def test_accept_pending_connections_empty_when_no_button():
    page = _make_page()
    page.query_selector.return_value = None  # aucune invitation

    result = messenger.accept_pending_connections(page, max_count=5)
    assert result == []


def test_reply_to_comment_targets_correct_article_by_urn():
    """Vérifie que reply_to_comment sélectionne l'article dont le data-id contient l'URN."""
    page = _make_page()

    # Simuler 2 articles : seul le deuxième a un data-id contenant l'URN cible
    article_wrong = MagicMock()
    article_wrong.get_attribute.return_value = "urn:li:comment:999"

    reply_btn = MagicMock()
    submit_btn = MagicMock()
    reply_box = MagicMock()

    article_correct = MagicMock()
    article_correct.get_attribute.return_value = "urn:li:comment:42"
    article_correct.query_selector.return_value = reply_btn

    page.query_selector_all.return_value = [article_wrong, article_correct]
    # query_selector au niveau page (fallback) ne doit PAS être appelé
    page.query_selector.return_value = submit_btn
    page.wait_for_selector.return_value = reply_box

    # URL dont le commentUrn décodé est "urn:li:comment:42"
    comment_url = (
        "https://linkedin.com/posts/user"
        "?commentUrn=urn%3Ali%3Acomment%3A42"
    )
    messenger.reply_to_comment(page, comment_url, "Bonjour")

    # Le bouton Répondre doit avoir été récupéré depuis article_correct
    article_correct.query_selector.assert_called_once()
    # Le fallback page.query_selector ne doit pas avoir été appelé pour Répondre
    # (il peut être appelé pour le bouton submit qui est sur la page)
    # Vérifier que article_wrong.query_selector n'a pas été appelé
    article_wrong.query_selector.assert_not_called()
