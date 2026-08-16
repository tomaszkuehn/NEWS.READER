import os
import sys
import sqlite3
from datetime import datetime, timedelta, timezone

RETENTION_DAYS = 7


def get_data_dir():
    """Katalog na dane aplikacji.

    W wersji skompilowanej (PyInstaller) %APPDATA%\\NewsReader (katalog temp
    onefile jest czyszczony przy zamknięciu), w trybie dev katalog projektu.
    """
    if getattr(sys, "frozen", False):
        base = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "NewsReader")
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(base, exist_ok=True)
    return base


DB_PATH = os.path.join(get_data_dir(), "articles.db")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS articles (
                link        TEXT PRIMARY KEY,
                uuid        TEXT DEFAULT '',
                title       TEXT NOT NULL,
                category    TEXT NOT NULL,
                summary     TEXT DEFAULT '',
                content     TEXT DEFAULT '',
                image       TEXT DEFAULT '',
                lead        TEXT DEFAULT '',
                is_read     INTEGER DEFAULT 0,
                is_premium  INTEGER DEFAULT 0,
                published_at TEXT DEFAULT '',
                first_seen  TEXT NOT NULL,
                last_seen   TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
            CREATE INDEX IF NOT EXISTS idx_articles_last_seen ON articles(last_seen);
            """
        )
        cols = {r[1] for r in conn.execute("PRAGMA table_info(articles)")}
        if "uuid" not in cols:
            conn.execute("ALTER TABLE articles ADD COLUMN uuid TEXT DEFAULT ''")
        if "is_premium" not in cols:
            conn.execute("ALTER TABLE articles ADD COLUMN is_premium INTEGER DEFAULT 0")
        if "published_at" not in cols:
            conn.execute("ALTER TABLE articles ADD COLUMN published_at TEXT DEFAULT ''")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at)")
        if "is_favorite" not in cols:
            conn.execute("ALTER TABLE articles ADD COLUMN is_favorite INTEGER DEFAULT 0")


def is_known(link):
    """Czy artykuł o danym linku istnieje już w bazie."""
    with _connect() as conn:
        return conn.execute(
            "SELECT 1 FROM articles WHERE link = ?", (link,)
        ).fetchone() is not None


def upsert_article(article):
    """Zapisuje artykuł, jeśli nie istnieje (klucz = link). Odświeża last_seen."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT link, category FROM articles WHERE link = ?", (article["link"],)
        ).fetchone()
        if row:
            old_cat = row["category"]
            new_cat = article.get("category", old_cat)
            # Nadpisuj kategorię tylko jeśli wiemy lepiej (konkretna zamiast 'glowna')
            if old_cat == "glowna" and new_cat != "glowna":
                conn.execute(
                    "UPDATE articles SET uuid = ?, title = ?, category = ?, image = ?, is_premium = ?, published_at = COALESCE(NULLIF(?, ''), published_at), last_seen = ? WHERE link = ?",
                    (article.get("uuid", ""), article["title"], new_cat, article.get("image", ""),
                     int(article.get("is_premium", 0)), article.get("published_at", ""), now_iso(), article["link"]),
                )
            else:
                conn.execute(
                    "UPDATE articles SET uuid = ?, title = ?, image = ?, is_premium = ?, published_at = COALESCE(NULLIF(?, ''), published_at), last_seen = ? WHERE link = ?",
                    (article.get("uuid", ""), article["title"], article.get("image", ""),
                     int(article.get("is_premium", 0)), article.get("published_at", ""), now_iso(), article["link"]),
                )
        else:
            conn.execute(
                """
                INSERT INTO articles (link, uuid, title, category, image, is_premium, published_at, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (article["link"], article.get("uuid", ""), article["title"],
                 article["category"], article.get("image", ""),
                 int(article.get("is_premium", 0)), article.get("published_at", ""), now_iso(), now_iso()),
            )


def mark_read_and_store(link, details):
    """Oznacza artykuł jako przeczytany i zapisuje jego treść."""
    with _connect() as conn:
        conn.execute(
            """
            UPDATE articles
            SET is_read = 1, content = ?, image = ?, lead = ?, published_at = COALESCE(NULLIF(?, ''), published_at)
            WHERE link = ?
            """,
            (details.get("content", ""), details.get("image", ""),
             details.get("lead", ""), details.get("published_at", ""), link),
        )


def get_articles(category=None, query=None, sort="newest", only_unread=False, only_favorites=False):
    """Pobiera artykuły z filtrowaniem, wyszukiwaniem i sortowaniem."""
    sql = "SELECT * FROM articles WHERE 1=1"
    params = []

    if category and category != "wszystkie":
        sql += " AND category = ?"
        params.append(category)
    if query:
        sql += " AND (title LIKE ? OR summary LIKE ?)"
        like = f"%{query}%"
        params += [like, like]
    if only_unread:
        sql += " AND is_read = 0"
    if only_favorites:
        sql += " AND is_favorite = 1"

    sql += {
        "newest": " ORDER BY COALESCE(NULLIF(published_at, ''), last_seen) DESC",
        "oldest": " ORDER BY COALESCE(NULLIF(published_at, ''), last_seen) ASC",
        "title": " ORDER BY title COLLATE NOCASE ASC",
        "read": " ORDER BY is_read DESC, last_seen DESC",
    }.get(sort, " ORDER BY last_seen DESC")

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def mark_read(link):
    """Oznacza artykuł jako przeczytany (bez treści)."""
    with _connect() as conn:
        conn.execute("UPDATE articles SET is_read = 1 WHERE link = ?", (link,))


def set_favorite(link, is_favorite):
    """Ustawia oznaczenie artykułu jako ulubionego (1/0)."""
    with _connect() as conn:
        conn.execute(
            "UPDATE articles SET is_favorite = ? WHERE link = ?",
            (1 if is_favorite else 0, link),
        )


def cleanup_old():
    """Usuwa artykuły nieaktualizowane dłużej niż RETENTION_DAYS dni.

    Artykuły oznaczone jako ulubione nigdy nie są usuwane automatycznie.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM articles WHERE last_seen < ? AND is_favorite = 0", (cutoff,)
        )
        return cur.rowcount