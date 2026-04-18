import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock
import telegram_listener as tl


# --- Tests du router (commandes simples) ---

def test_help_returns_help_text():
    response, state = tl.handle_message("/linkedin help", {})
    assert "help" in response.lower() or "commandes" in response.lower()
    assert state == {}

def test_unknown_subcommand_returns_error():
    response, state = tl.handle_message("/linkedin foobar", {})
    assert "inconnu" in response.lower()
    assert state == {}

def test_non_linkedin_command_ignored():
    response, state = tl.handle_message("/start", {})
    assert response is None

def test_status_calls_cmd_status():
    with patch("telegram_listener.cmd_status", return_value="État : ✓ activé\nPosts actifs : 0") as mock:
        response, state = tl.handle_message("/linkedin status", {})
        mock.assert_called_once()
        assert "activé" in response

def test_list_calls_cmd_list_posts():
    with patch("telegram_listener.cmd_list_posts", return_value="Aucun post enregistré.") as mock:
        response, state = tl.handle_message("/linkedin list", {})
        mock.assert_called_once()
        assert state == {}

def test_on_calls_cmd_enable():
    with patch("telegram_listener.cmd_enable", return_value="Bot activé.") as mock:
        response, state = tl.handle_message("/linkedin on", {})
        mock.assert_called_once()

def test_off_calls_cmd_disable():
    with patch("telegram_listener.cmd_disable", return_value="Bot désactivé.") as mock:
        response, state = tl.handle_message("/linkedin off", {})
        mock.assert_called_once()

def test_remove_without_url_returns_usage():
    response, state = tl.handle_message("/linkedin remove", {})
    assert "usage" in response.lower() or "Usage" in response

def test_remove_with_url_calls_cmd_remove():
    url = "https://linkedin.com/post/1"
    with patch("telegram_listener.cmd_remove_post", return_value=f"Post supprimé (et engagements associés) : {url}") as mock:
        response, state = tl.handle_message(f"/linkedin remove {url}", {})
        mock.assert_called_once_with(url)

def test_add_without_url_returns_usage():
    response, state = tl.handle_message("/linkedin add", {})
    assert "usage" in response.lower() or "Usage" in response
    assert state == {}

def test_setmsg_without_url_returns_usage():
    response, state = tl.handle_message("/linkedin setmsg", {})
    assert "usage" in response.lower() or "Usage" in response
    assert state == {}

def test_run_starts_thread_and_returns_message():
    with patch("telegram_listener.cmd_run") as mock_run:
        with patch("threading.Thread") as mock_thread:
            mock_thread_instance = MagicMock()
            mock_thread.return_value = mock_thread_instance
            response, state = tl.handle_message("/linkedin run", {})
            mock_thread.assert_called_once()
            mock_thread_instance.start.assert_called_once()
            assert "lancé" in response.lower()


# --- Tests du flow conversationnel /linkedin add ---

def test_add_starts_flow():
    url = "https://linkedin.com/post/1"
    response, state = tl.handle_message(f"/linkedin add {url}", {})
    assert state == {"step": "add_msg_mp", "url": url}
    assert "MP" in response or "mp" in response.lower()

def test_add_flow_step2():
    state = {"step": "add_msg_mp", "url": "https://linkedin.com/post/1"}
    response, new_state = tl.handle_message("Salut {first_name}!", state)
    assert new_state["step"] == "add_msg_reply"
    assert new_state["msg_mp"] == "Salut {first_name}!"
    assert "commentaire" in response.lower()

def test_add_flow_step3_asks_for_keyword():
    state = {
        "step": "add_msg_reply",
        "url": "https://linkedin.com/post/1",
        "msg_mp": "Salut {first_name}!",
    }
    response, new_state = tl.handle_message("Connecte-toi!", state)
    assert new_state["step"] == "add_keyword"
    assert new_state["msg_reply"] == "Connecte-toi!"
    assert "mot" in response.lower() or "clé" in response.lower() or "keyword" in response.lower()


# --- Tests du flow conversationnel /linkedin setmsg ---

def test_setmsg_starts_flow():
    url = "https://linkedin.com/post/1"
    response, state = tl.handle_message(f"/linkedin setmsg {url}", {})
    assert state == {"step": "setmsg_msg_mp", "url": url}

def test_setmsg_flow_step2():
    state = {"step": "setmsg_msg_mp", "url": "https://linkedin.com/post/1"}
    response, new_state = tl.handle_message("Nouveau MP", state)
    assert new_state["step"] == "setmsg_msg_reply"
    assert new_state["msg_mp"] == "Nouveau MP"

def test_setmsg_flow_step3_asks_for_keyword():
    state = {
        "step": "setmsg_msg_reply",
        "url": "https://linkedin.com/post/1",
        "msg_mp": "Nouveau MP",
    }
    response, new_state = tl.handle_message("Nouvelle reply", state)
    assert new_state["step"] == "setmsg_keyword"
    assert new_state["msg_reply"] == "Nouvelle reply"
    assert "mot" in response.lower() or "clé" in response.lower() or "keyword" in response.lower()


def test_add_flow_step4_saves_post():
    state = {
        "step": "add_keyword",
        "url": "https://linkedin.com/post/1",
        "msg_mp": "Salut {first_name}!",
        "msg_reply": "Connecte-toi!",
    }
    with patch("telegram_listener.cmd_add_post", return_value="Post ajouté : https://linkedin.com/post/1") as mock:
        response, new_state = tl.handle_message("bonjour", state)
        mock.assert_called_once_with(
            "https://linkedin.com/post/1",
            "Salut {first_name}!",
            "Connecte-toi!",
            "bonjour",
        )
        assert new_state == {}
        assert "ajouté" in response.lower()


def test_setmsg_flow_step4_updates_templates():
    state = {
        "step": "setmsg_keyword",
        "url": "https://linkedin.com/post/1",
        "msg_mp": "Nouveau MP",
        "msg_reply": "Nouvelle reply",
    }
    with patch("telegram_listener.db") as mock_db:
        response, new_state = tl.handle_message("bonjour", state)
        mock_db.update_post_templates.assert_called_once_with(
            "https://linkedin.com/post/1", "Nouveau MP", "Nouvelle reply", tl.DB_PATH,
            keyword="bonjour"
        )
        assert new_state == {}
        assert "mis à jour" in response.lower()


# --- Test annulation de flow ---

def test_linkedin_command_cancels_pending_flow():
    state = {"step": "add_msg_mp", "url": "https://linkedin.com/post/1"}
    with patch("telegram_listener.cmd_status", return_value="État : ✓ activé\nPosts actifs : 0"):
        response, new_state = tl.handle_message("/linkedin status", state)
        # Le flow est annulé, on traite la nouvelle commande
        assert "step" not in new_state
