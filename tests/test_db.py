import pytest
import sqlite3
from datetime import datetime, timedelta
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import db

@pytest.fixture
def tmp_db(tmp_path):
    path = str(tmp_path / "test.db")
    db.init_db(path)
    return path

def test_init_db_creates_tables(tmp_db):
    conn = sqlite3.connect(tmp_db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    assert {"posts", "engagements", "accepted_connections", "config", "runs"} <= tables

def test_config_default_enabled(tmp_db):
    assert db.get_config("enabled", tmp_db) == "1"

def test_set_and_get_config(tmp_db):
    db.set_config("enabled", "0", tmp_db)
    assert db.get_config("enabled", tmp_db) == "0"

def test_add_and_list_posts(tmp_db):
    db.add_post("https://linkedin.com/post/1", "Salut {first_name}!", "Connecte-toi!", tmp_db)
    posts = db.list_posts(tmp_db)
    assert len(posts) == 1
    assert posts[0]["url"] == "https://linkedin.com/post/1"
    assert posts[0]["msg_mp"] == "Salut {first_name}!"

def test_add_post_idempotent(tmp_db):
    db.add_post("https://linkedin.com/post/1", "msg", "reply", tmp_db)
    db.add_post("https://linkedin.com/post/1", "msg2", "reply2", tmp_db)
    assert len(db.list_posts(tmp_db)) == 1

def test_remove_post_deletes_engagements(tmp_db):
    db.add_post("https://linkedin.com/post/1", "msg", "reply", tmp_db)
    db.upsert_engagement("https://linkedin.com/in/alice", "https://linkedin.com/post/1",
                         first_name="Alice", liked=1, commented=1,
                         comment_url="https://linkedin.com/post/1?commentId=1",
                         comment_at=(datetime.utcnow() - timedelta(minutes=10)).isoformat(),
                         is_connected=1, db_path=tmp_db)
    db.remove_post("https://linkedin.com/post/1", tmp_db)
    assert len(db.list_posts(tmp_db)) == 0
    conn = sqlite3.connect(tmp_db)
    count = conn.execute("SELECT COUNT(*) FROM engagements").fetchone()[0]
    conn.close()
    assert count == 0

def test_upsert_engagement_insert(tmp_db):
    db.add_post("https://linkedin.com/post/1", "msg", "reply", tmp_db)
    db.upsert_engagement("https://linkedin.com/in/alice", "https://linkedin.com/post/1",
                         first_name="Alice", liked=1, db_path=tmp_db)
    conn = sqlite3.connect(tmp_db)
    row = conn.execute("SELECT * FROM engagements WHERE profile_url = 'https://linkedin.com/in/alice'").fetchone()
    conn.close()
    assert row is not None
    assert row[4] == 1  # liked

def test_upsert_engagement_update_adds_comment(tmp_db):
    db.add_post("https://linkedin.com/post/1", "msg", "reply", tmp_db)
    db.upsert_engagement("https://linkedin.com/in/alice", "https://linkedin.com/post/1",
                         first_name="Alice", liked=1, db_path=tmp_db)
    db.upsert_engagement("https://linkedin.com/in/alice", "https://linkedin.com/post/1",
                         commented=1,
                         comment_url="https://linkedin.com/post/1?commentId=1",
                         comment_at=(datetime.utcnow() - timedelta(minutes=10)).isoformat(),
                         db_path=tmp_db)
    conn = sqlite3.connect(tmp_db)
    row = conn.execute("SELECT liked, commented FROM engagements WHERE profile_url = 'https://linkedin.com/in/alice'").fetchone()
    conn.close()
    assert row[0] == 1  # liked preserved
    assert row[1] == 1  # commented added

def test_get_pending_engagements_priority_order(tmp_db):
    db.add_post("https://linkedin.com/post/1", "msg_mp", "msg_reply", tmp_db)
    old_comment = (datetime.utcnow() - timedelta(minutes=10)).isoformat()

    # Priority 2: liked + commented + connected, no repost
    db.upsert_engagement("https://linkedin.com/in/bob", "https://linkedin.com/post/1",
                         first_name="Bob", liked=1, commented=1, reposted=0, is_connected=1,
                         comment_url="url1", comment_at=old_comment, db_path=tmp_db)
    # Priority 1: liked + commented + reposted + connected
    db.upsert_engagement("https://linkedin.com/in/alice", "https://linkedin.com/post/1",
                         first_name="Alice", liked=1, commented=1, reposted=1, is_connected=1,
                         comment_url="url2", comment_at=old_comment, db_path=tmp_db)
    # Priority 3: liked + commented + not connected
    db.upsert_engagement("https://linkedin.com/in/charlie", "https://linkedin.com/post/1",
                         first_name="Charlie", liked=1, commented=1, reposted=0, is_connected=0,
                         comment_url="url3", comment_at=old_comment, db_path=tmp_db)

    pending = db.get_pending_engagements(tmp_db)
    assert len(pending) == 3
    assert pending[0]["profile_url"] == "https://linkedin.com/in/alice"  # priority 1
    assert pending[1]["profile_url"] == "https://linkedin.com/in/bob"    # priority 2
    assert pending[2]["profile_url"] == "https://linkedin.com/in/charlie" # priority 3

def test_get_pending_excludes_recent_comments(tmp_db):
    db.add_post("https://linkedin.com/post/1", "msg", "reply", tmp_db)
    recent = (datetime.utcnow() - timedelta(minutes=2)).isoformat()
    db.upsert_engagement("https://linkedin.com/in/alice", "https://linkedin.com/post/1",
                         first_name="Alice", liked=1, commented=1, is_connected=1,
                         comment_url="url", comment_at=recent, db_path=tmp_db)
    assert len(db.get_pending_engagements(tmp_db)) == 0

def test_get_pending_excludes_action_taken(tmp_db):
    db.add_post("https://linkedin.com/post/1", "msg", "reply", tmp_db)
    old = (datetime.utcnow() - timedelta(minutes=10)).isoformat()
    db.upsert_engagement("https://linkedin.com/in/alice", "https://linkedin.com/post/1",
                         first_name="Alice", liked=1, commented=1, is_connected=1,
                         comment_url="url", comment_at=old, db_path=tmp_db)
    db.mark_action_taken("https://linkedin.com/in/alice", "https://linkedin.com/post/1", "mp_sent", tmp_db)
    assert len(db.get_pending_engagements(tmp_db)) == 0

def test_get_pending_excludes_liked_only(tmp_db):
    db.add_post("https://linkedin.com/post/1", "msg", "reply", tmp_db)
    db.upsert_engagement("https://linkedin.com/in/alice", "https://linkedin.com/post/1",
                         first_name="Alice", liked=1, commented=0, is_connected=1,
                         db_path=tmp_db)
    assert len(db.get_pending_engagements(tmp_db)) == 0

def test_start_and_finish_run(tmp_db):
    run_id = db.start_run(25, 22, tmp_db)
    assert run_id is not None
    db.finish_run(run_id, 10, 5, 3, None, tmp_db)
    last = db.get_last_run(tmp_db)
    assert last["connections_accepted"] == 10
    assert last["mp_sent"] == 5
    assert last["comment_replies_sent"] == 3
    assert last["max_connections_this_run"] == 25
