import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import MagicMock, patch
import messenger


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
