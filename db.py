import sqlite3
from datetime import datetime
from contextlib import contextmanager
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "linkedin.db")


@contextmanager
def _conn(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path=DB_PATH):
    with _conn(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS posts (
                id               INTEGER PRIMARY KEY,
                url              TEXT UNIQUE NOT NULL,
                added_at         DATETIME NOT NULL,
                active           INTEGER DEFAULT 1,
                msg_mp           TEXT,
                msg_comment_reply TEXT
            );
            CREATE TABLE IF NOT EXISTS engagements (
                id               INTEGER PRIMARY KEY,
                profile_url      TEXT NOT NULL,
                post_url         TEXT NOT NULL,
                first_name       TEXT,
                liked            INTEGER DEFAULT 0,
                commented        INTEGER DEFAULT 0,
                comment_url      TEXT,
                comment_at       DATETIME,
                reposted         INTEGER DEFAULT 0,
                is_connected     INTEGER DEFAULT 0,
                action_taken     TEXT,
                action_taken_at  DATETIME,
                last_scraped_at  DATETIME,
                UNIQUE(profile_url, post_url)
            );
            CREATE TABLE IF NOT EXISTS accepted_connections (
                id           INTEGER PRIMARY KEY,
                profile_url  TEXT UNIQUE NOT NULL,
                accepted_at  DATETIME NOT NULL
            );
            CREATE TABLE IF NOT EXISTS config (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS runs (
                id                       INTEGER PRIMARY KEY,
                started_at               DATETIME NOT NULL,
                finished_at              DATETIME,
                connections_accepted     INTEGER DEFAULT 0,
                mp_sent                  INTEGER DEFAULT 0,
                comment_replies_sent     INTEGER DEFAULT 0,
                max_connections_this_run INTEGER,
                max_messages_this_run    INTEGER,
                errors                   TEXT
            );
            INSERT OR IGNORE INTO config (key, value) VALUES ('enabled', '1');
        """)


def get_config(key, db_path=DB_PATH):
    with _conn(db_path) as conn:
        row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def set_config(key, value, db_path=DB_PATH):
    with _conn(db_path) as conn:
        conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))


def add_post(url, msg_mp, msg_comment_reply, db_path=DB_PATH):
    with _conn(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO posts (url, added_at, msg_mp, msg_comment_reply) VALUES (?, ?, ?, ?)",
            (url, datetime.now().isoformat(), msg_mp, msg_comment_reply),
        )


def remove_post(url, db_path=DB_PATH):
    with _conn(db_path) as conn:
        conn.execute("DELETE FROM engagements WHERE post_url = ?", (url,))
        conn.execute("DELETE FROM posts WHERE url = ?", (url,))


def list_posts(db_path=DB_PATH):
    with _conn(db_path) as conn:
        return conn.execute("SELECT * FROM posts ORDER BY added_at DESC").fetchall()


def get_active_posts(db_path=DB_PATH):
    with _conn(db_path) as conn:
        return conn.execute("SELECT * FROM posts WHERE active = 1").fetchall()


def update_post_templates(url, msg_mp, msg_comment_reply, db_path=DB_PATH):
    with _conn(db_path) as conn:
        conn.execute(
            "UPDATE posts SET msg_mp = ?, msg_comment_reply = ? WHERE url = ?",
            (msg_mp, msg_comment_reply, url),
        )


def upsert_engagement(profile_url, post_url, first_name=None, liked=None,
                      commented=None, comment_url=None, comment_at=None,
                      reposted=None, is_connected=None, db_path=DB_PATH):
    now = datetime.now().isoformat()
    with _conn(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM engagements WHERE profile_url = ? AND post_url = ?",
            (profile_url, post_url),
        ).fetchone()

        if existing:
            updates = {"last_scraped_at": now}
            if first_name is not None:   updates["first_name"]   = first_name
            if liked is not None:        updates["liked"]        = liked
            if commented is not None:    updates["commented"]    = commented
            if comment_url is not None:  updates["comment_url"]  = comment_url
            if comment_at is not None:   updates["comment_at"]   = comment_at
            if reposted is not None:     updates["reposted"]     = reposted
            if is_connected is not None: updates["is_connected"] = is_connected
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE engagements SET {set_clause} WHERE profile_url = ? AND post_url = ?",
                (*updates.values(), profile_url, post_url),
            )
        else:
            conn.execute(
                """INSERT INTO engagements
                   (profile_url, post_url, first_name, liked, commented,
                    comment_url, comment_at, reposted, is_connected, last_scraped_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (profile_url, post_url, first_name,
                 liked or 0, commented or 0, comment_url, comment_at,
                 reposted or 0, is_connected or 0, now),
            )


def get_pending_engagements(db_path=DB_PATH):
    """Retourne les engagements éligibles triés par priorité (1 > 2 > 3).
    Priorité 1 : liked + commented + reposted + connected
    Priorité 2 : liked + commented + connected (sans repost)
    Priorité 3 : liked + commented + non connecté
    Exclut les commentaires postés il y a moins de 5 minutes.
    """
    with _conn(db_path) as conn:
        return conn.execute("""
            SELECT e.*,
                   p.msg_mp,
                   p.msg_comment_reply,
                   CASE
                       WHEN e.liked=1 AND e.commented=1 AND e.reposted=1 AND e.is_connected=1 THEN 1
                       WHEN e.liked=1 AND e.commented=1 AND e.reposted=0 AND e.is_connected=1 THEN 2
                       WHEN e.liked=1 AND e.commented=1 AND e.is_connected=0              THEN 3
                       ELSE 99
                   END AS priority
            FROM engagements e
            JOIN posts p ON e.post_url = p.url
            WHERE e.action_taken IS NULL
              AND e.liked = 1
              AND e.commented = 1
              AND e.comment_at IS NOT NULL
              AND datetime(e.comment_at) <= datetime('now', 'localtime', '-5 minutes')
            ORDER BY priority ASC
        """).fetchall()


def mark_action_taken(profile_url, post_url, action, db_path=DB_PATH):
    with _conn(db_path) as conn:
        conn.execute(
            "UPDATE engagements SET action_taken=?, action_taken_at=? WHERE profile_url=? AND post_url=?",
            (action, datetime.now().isoformat(), profile_url, post_url),
        )


def add_accepted_connection(profile_url, db_path=DB_PATH):
    with _conn(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO accepted_connections (profile_url, accepted_at) VALUES (?, ?)",
            (profile_url, datetime.now().isoformat()),
        )


def start_run(max_connections, max_messages, db_path=DB_PATH):
    with _conn(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO runs (started_at, max_connections_this_run, max_messages_this_run) VALUES (?, ?, ?)",
            (datetime.now().isoformat(), max_connections, max_messages),
        )
        return cursor.lastrowid


def finish_run(run_id, connections_accepted, mp_sent, comment_replies_sent,
               errors=None, db_path=DB_PATH):
    with _conn(db_path) as conn:
        conn.execute(
            """UPDATE runs SET finished_at=?, connections_accepted=?, mp_sent=?,
               comment_replies_sent=?, errors=? WHERE id=?""",
            (datetime.now().isoformat(), connections_accepted, mp_sent,
             comment_replies_sent, errors, run_id),
        )


def get_last_run(db_path=DB_PATH):
    with _conn(db_path) as conn:
        return conn.execute(
            "SELECT * FROM runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
