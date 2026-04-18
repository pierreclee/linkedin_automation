import time
import random
import re
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, Page


def verify_session(page: Page) -> bool:
    """Vérifie que la session LinkedIn est valide en cherchant l'avatar de profil."""
    page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
    time.sleep(random.uniform(2, 4))
    # LinkedIn affiche le bouton "Me" avec l'avatar quand on est connecté
    try:
        page.wait_for_selector(
            "button[data-control-name='nav.settings_and_privacy'], "
            "[data-test-global-nav-me-dropdown-trigger], "
            "div.global-nav__me",
            timeout=10000
        )
        return True
    except Exception:
        return False
