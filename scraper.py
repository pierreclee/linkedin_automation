import time
import random
import re
from datetime import datetime, timedelta
from playwright.sync_api import Page


def _parse_relative_time(time_str: str) -> datetime:
    """Convertit '5m', '2h', '3d' en datetime absolue (UTC)."""
    now = datetime.utcnow()
    m = re.match(r"(\d+)\s*([mhdjsa])", time_str.strip().lower())
    if not m:
        return now
    value, unit = int(m.group(1)), m.group(2)
    if unit == "m":
        return now - timedelta(minutes=value)
    if unit == "h":
        return now - timedelta(hours=value)
    if unit in ("d", "j"):
        return now - timedelta(days=value)
    # semaine (s), an (a) → considéré très vieux
    return now - timedelta(days=365)


def _get_connection_status(element) -> bool:
    """True si le profil a un bouton 'Envoyer un message' (= connecté)."""
    try:
        buttons = element.query_selector_all("button, a[role='button']")
        for btn in buttons:
            text = (btn.inner_text() or "").lower()
            if "message" in text or "envoyer" in text:
                return True
        return False
    except Exception:
        return False


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


def scrape_reactions(page: Page, post_url: str) -> list[dict]:
    """Scrape la liste des personnes ayant réagi au post.
    Retourne une liste de dicts : {profile_url, first_name, is_connected}
    """
    page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(random.uniform(2, 4))

    results = []
    try:
        # Cliquer sur le compteur de réactions
        reactions_btn = page.query_selector(
            "button.social-counts-reactions__count-value, "
            "span.social-counts-reactions__count, "
            "button[aria-label*='reaction'], "
            "button[aria-label*='réaction']"
        )
        if not reactions_btn:
            return results
        reactions_btn.click()
        time.sleep(random.uniform(1, 2))

        # Attendre le modal
        page.wait_for_selector(
            ".artdeco-modal .social-proof-fallback-profile, "
            ".artdeco-modal .social-details-reactors-tab-body-list-item",
            timeout=8000
        )

        # Scroll pour charger tous les réactants
        modal = page.query_selector(".artdeco-modal__content")
        if modal:
            for _ in range(20):
                prev_count = len(page.query_selector_all(
                    ".social-proof-fallback-profile, "
                    ".social-details-reactors-tab-body-list-item"
                ))
                page.evaluate("(el) => el.scrollTop += 600", modal)
                time.sleep(0.8)
                new_count = len(page.query_selector_all(
                    ".social-proof-fallback-profile, "
                    ".social-details-reactors-tab-body-list-item"
                ))
                if new_count == prev_count:
                    break

        items = page.query_selector_all(
            ".social-proof-fallback-profile, "
            ".social-details-reactors-tab-body-list-item"
        )
        for item in items:
            link = item.query_selector("a[href*='/in/']")
            if not link:
                continue
            profile_url = link.get_attribute("href").split("?")[0]
            name_el = item.query_selector(
                ".artdeco-entity-lockup__title, "
                ".social-proof-fallback-profile__name"
            )
            first_name = name_el.inner_text().strip().split()[0] if name_el else ""
            is_connected = _get_connection_status(item)
            results.append({
                "profile_url": profile_url,
                "first_name": first_name,
                "is_connected": is_connected,
            })

        # Fermer le modal
        close = page.query_selector("button[aria-label='Fermer'], button[aria-label='Close']")
        if close:
            close.click()
        time.sleep(random.uniform(1, 2))

    except Exception as e:
        print(f"[scrape_reactions] Erreur : {e}")

    return results


def scrape_comments(page: Page, post_url: str) -> list[dict]:
    """Scrape les commentaires du post.
    Retourne une liste de dicts : {profile_url, first_name, comment_url, comment_at, is_connected}
    """
    page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(random.uniform(2, 4))

    results = []
    try:
        # Charger tous les commentaires
        for _ in range(30):
            load_more = page.query_selector(
                "button.comments-comments-list__load-more-comments-button"
            )
            if not load_more or not load_more.is_visible():
                break
            load_more.click()
            time.sleep(random.uniform(1, 2))

        items = page.query_selector_all("article.comments-comment-item")
        for item in items:
            link = item.query_selector(
                ".comments-post-meta__actor-link, "
                "a[href*='/in/']"
            )
            if not link:
                continue
            profile_url = link.get_attribute("href").split("?")[0]
            name_el = item.query_selector(
                ".comments-post-meta__name-text, "
                ".artdeco-entity-lockup__title"
            )
            first_name = name_el.inner_text().strip().split()[0] if name_el else ""

            # Timestamp du commentaire
            time_el = item.query_selector(
                "time, "
                "a.comments-comment-item__timestamp, "
                "span.comments-comment-item__timestamp"
            )
            comment_at = datetime.utcnow()
            comment_url = post_url
            if time_el:
                time_text = time_el.get_attribute("datetime") or time_el.inner_text()
                try:
                    comment_at = datetime.fromisoformat(time_text)
                except ValueError:
                    comment_at = _parse_relative_time(time_text)
                href = time_el.get_attribute("href")
                if href:
                    comment_url = href if href.startswith("http") else f"https://www.linkedin.com{href}"

            is_connected = _get_connection_status(item)
            text_el = item.query_selector(
                ".comments-comment-item__main-content, "
                ".comments-comment-item__inline-show-more-text"
            )
            comment_text = text_el.inner_text().strip() if text_el else ""
            results.append({
                "profile_url": profile_url,
                "first_name": first_name,
                "comment_url": comment_url,
                "comment_at": comment_at.isoformat(),
                "is_connected": is_connected,
                "comment_text": comment_text,
            })

    except Exception as e:
        print(f"[scrape_comments] Erreur : {e}")

    return results


def scrape_reposts(page: Page, post_url: str) -> list[dict]:
    """Scrape les personnes ayant reposté le post.
    Retourne une liste de dicts : {profile_url, first_name, is_connected}
    """
    page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(random.uniform(2, 4))

    results = []
    try:
        repost_btn = page.query_selector(
            "button[aria-label*='repost'], "
            "button[aria-label*='republication'], "
            "span.social-counts-reactions__count--repost"
        )
        if not repost_btn:
            return results
        repost_btn.click()
        time.sleep(random.uniform(1, 2))

        page.wait_for_selector(
            ".artdeco-modal .artdeco-entity-lockup",
            timeout=8000
        )

        modal = page.query_selector(".artdeco-modal__content")
        if modal:
            for _ in range(20):
                prev = len(page.query_selector_all(".artdeco-modal .artdeco-entity-lockup"))
                page.evaluate("(el) => el.scrollTop += 600", modal)
                time.sleep(0.8)
                if len(page.query_selector_all(".artdeco-modal .artdeco-entity-lockup")) == prev:
                    break

        items = page.query_selector_all(".artdeco-modal .artdeco-entity-lockup")
        for item in items:
            link = item.query_selector("a[href*='/in/']")
            if not link:
                continue
            profile_url = link.get_attribute("href").split("?")[0]
            name_el = item.query_selector(".artdeco-entity-lockup__title")
            first_name = name_el.inner_text().strip().split()[0] if name_el else ""
            is_connected = _get_connection_status(item)
            results.append({
                "profile_url": profile_url,
                "first_name": first_name,
                "is_connected": is_connected,
            })

        close = page.query_selector("button[aria-label='Fermer'], button[aria-label='Close']")
        if close:
            close.click()
        time.sleep(random.uniform(1, 2))

    except Exception as e:
        print(f"[scrape_reposts] Erreur : {e}")

    return results


def scrape_post_engagements(page: Page, post_url: str, db_path: str) -> None:
    """Scrape réactions, commentaires et reposts d'un post et met à jour la DB."""
    import db as database

    print(f"[scraper] Scraping réactions : {post_url}")
    for r in scrape_reactions(page, post_url):
        database.upsert_engagement(
            r["profile_url"], post_url,
            first_name=r["first_name"],
            liked=1,
            is_connected=1 if r["is_connected"] else 0,
            db_path=db_path,
        )
    time.sleep(random.uniform(3, 6))

    print(f"[scraper] Scraping commentaires : {post_url}")
    for c in scrape_comments(page, post_url):
        database.upsert_engagement(
            c["profile_url"], post_url,
            first_name=c["first_name"],
            commented=1,
            comment_url=c["comment_url"],
            comment_at=c["comment_at"],
            comment_text=c["comment_text"],
            is_connected=1 if c["is_connected"] else 0,
            db_path=db_path,
        )
    time.sleep(random.uniform(3, 6))

    print(f"[scraper] Scraping reposts : {post_url}")
    for rp in scrape_reposts(page, post_url):
        database.upsert_engagement(
            rp["profile_url"], post_url,
            first_name=rp["first_name"],
            reposted=1,
            is_connected=1 if rp["is_connected"] else 0,
            db_path=db_path,
        )
