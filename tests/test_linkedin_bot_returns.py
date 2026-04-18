import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import db
import linkedin_bot

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    path = str(tmp_path / "test.db")
    db.init_db(path)
    monkeypatch.setattr(linkedin_bot, "DB_PATH", path)
    return path

def test_cmd_enable_returns_string(tmp_db):
    result = linkedin_bot.cmd_enable()
    assert isinstance(result, str)
    assert "activé" in result

def test_cmd_disable_returns_string(tmp_db):
    result = linkedin_bot.cmd_disable()
    assert isinstance(result, str)
    assert "désactivé" in result

def test_cmd_status_returns_string(tmp_db):
    result = linkedin_bot.cmd_status()
    assert isinstance(result, str)
    assert "État" in result

def test_cmd_list_posts_empty_returns_string(tmp_db):
    result = linkedin_bot.cmd_list_posts()
    assert isinstance(result, str)
    assert "Aucun" in result

def test_cmd_list_posts_with_post_returns_string(tmp_db):
    db.add_post("https://linkedin.com/post/1", "Salut {first_name}!", "Reply!", tmp_db)
    result = linkedin_bot.cmd_list_posts()
    assert isinstance(result, str)
    assert "linkedin.com/post/1" in result

def test_cmd_add_post_returns_string(tmp_db):
    result = linkedin_bot.cmd_add_post("https://linkedin.com/post/1", "msg_mp", "msg_reply", "bonjour")
    assert isinstance(result, str)
    assert "ajouté" in result

def test_cmd_remove_post_returns_string(tmp_db):
    db.add_post("https://linkedin.com/post/1", "msg", "reply", tmp_db)
    result = linkedin_bot.cmd_remove_post("https://linkedin.com/post/1")
    assert isinstance(result, str)
    assert "supprimé" in result
