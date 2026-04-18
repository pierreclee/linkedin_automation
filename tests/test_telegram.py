import pytest
from unittest.mock import patch, MagicMock
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import telegram as tg


def test_send_message_calls_correct_url():
    mock_response = MagicMock()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
        tg.send_message("Hello!", bot_token="TOKEN123", chat_id="CHAT456")

    call_args = mock_urlopen.call_args
    request_obj = call_args[0][0]
    assert "TOKEN123" in request_obj.full_url
    assert b"Hello!" in request_obj.data
    assert b"CHAT456" in request_obj.data


def test_send_message_uses_env_vars(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "envtoken")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "envchat")

    mock_response = MagicMock()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
        tg.send_message("Test env")

    request_obj = mock_urlopen.call_args[0][0]
    assert "envtoken" in request_obj.full_url
