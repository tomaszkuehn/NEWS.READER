import os
import sys
import sqlite3
from datetime import datetime, timedelta, timezone

RETENTION_DAYS = 14
# Jak długo nowo odkryty artykuł jest widoczny w (wirtualnej) kategorii 'najnowsze'.
FRESH_WINDOW = timedelta(hours=2)
# „Ukryj nieaktualne" — domyślnie ukrywa artykuły starsze niż STALE_WINDOW
# (wg daty publikacji, fallback first_seen).
STALE_WINDOW = timedelta(days=7)


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
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
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
        if "article_key" not in cols:
            conn.execute("ALTER TABLE articles ADD COLUMN article_key TEXT DEFAULT ''")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_article_key ON articles(article_key)")


def _key(link):
    """Stabilny identyfikator artykułu (delegat do onet_scraper.article_key)."""
    from onet_scraper import article_key
    return article_key(link) or link


def is_known(link):
    """Czy artykuł o danym linku istnieje już w bazie (po article_key)."""
    with _connect() as conn:
        return conn.execute(
            "SELECT 1 FROM articles WHERE article_key = ?", (_key(link),)
        ).fetchone() is not None


def count_articles():
    """Zwraca liczbę artykułów w bazie."""
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]


def get_article_by_key(link):
    """Pobiera wiersz artykułu po article_key (ignoruje filtry hide_stale/kategoria)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM articles WHERE article_key = ?", (_key(link),)
        ).fetchone()
        return dict(row) if row else None


def upsert_article(article):
    """Zapisuje artykuł, jeśli nie istnieje (klucz = article_key). Odświeża last_seen.

    Ten sam artykuł może mieć różne slugi w URL (Onet je zmienia) oraz dopisek
    '#pco' — dedup po stabilnym article_key (domena + ID), a nie po pełnym linku.
    Pierwszy widziany link jest zachowywany.
    """
    key = _key(article["link"])
    with _connect() as conn:
        row = conn.execute(
            "SELECT link, category FROM articles WHERE article_key = ?", (key,)
        ).fetchone()
        if row:
            old_cat = row["category"]
            new_cat = article.get("category", old_cat)
            # Nadpisuj kategorię tylko jeśli wiemy lepiej (konkretna zamiast 'glowna')
            if old_cat == "glowna" and new_cat != "glowna":
                conn.execute(
                    "UPDATE articles SET uuid = ?, title = ?, category = ?, image = ?, is_premium = ?, published_at = COALESCE(NULLIF(?, ''), published_at), last_seen = ? WHERE article_key = ?",
                    (article.get("uuid", ""), article["title"], new_cat, article.get("image", ""),
                     int(article.get("is_premium", 0)), article.get("published_at", ""), now_iso(), key),
                )
            else:
                conn.execute(
                    "UPDATE articles SET uuid = ?, title = ?, image = ?, is_premium = ?, published_at = COALESCE(NULLIF(?, ''), published_at), last_seen = ? WHERE article_key = ?",
                    (article.get("uuid", ""), article["title"], article.get("image", ""),
                     int(article.get("is_premium", 0)), article.get("published_at", ""), now_iso(), key),
                )
        else:
            conn.execute(
                """
                INSERT INTO articles (link, article_key, uuid, title, category, image, is_premium, published_at, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (article["link"], key, article.get("uuid", ""), article["title"],
                 article["category"], article.get("image", ""),
                 int(article.get("is_premium", 0)), article.get("published_at", ""), now_iso(), now_iso()),
            )


def mark_read_and_store(link, details):
    """Oznacza artykuł jako przeczytany i zapisuje jego treść (po article_key)."""
    with _connect() as conn:
        conn.execute(
            """
            UPDATE articles
            SET is_read = 1, content = ?, image = ?, lead = ?, published_at = COALESCE(NULLIF(?, ''), published_at)
            WHERE article_key = ?
            """,
            (details.get("content", ""), details.get("image", ""),
             details.get("lead", ""), details.get("published_at", ""), _key(link)),
        )


def get_articles(category=None, query=None, sort="newest", only_unread=False, only_favorites=False, hide_stale=True):
    """Pobiera artykuły z filtrowaniem, wyszukiwaniem i sortowaniem.

    Kategoria 'najnowsze' jest wirtualna: pokazuje artykuły z ostatnich
    FRESH_WINDOW (2h) wg daty publikacji (published_at; dla artykułów bez daty
    wg first_seen — pierwszego znalezienia). Po upływie okna artykuł pozostaje
    tylko w swojej kategorii treści.

    hide_stale=True (domyślnie) ukrywa artykuły starsze niż STALE_WINDOW (7 dni)
    wg tej samej daty efektywnej — dotyczy list, wyszukiwania i liczników.
    """
    sql = "SELECT * FROM articles WHERE 1=1"
    params = []
    eff = "COALESCE(NULLIF(published_at, ''), first_seen)"

    if category == "najnowsze":
        now = datetime.now(timezone.utc).isoformat()
        fresh_cutoff = (datetime.now(timezone.utc) - FRESH_WINDOW).isoformat()
        # okno 2h wstecz; daty z przyszłości (błędne dane Onetu) są pomijane
        sql += f" AND {eff} >= ? AND {eff} <= ?"
        params += [fresh_cutoff, now]
    elif category and category != "wszystkie":
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
    if hide_stale:
        stale_cutoff = (datetime.now(timezone.utc) - STALE_WINDOW).isoformat()
        sql += f" AND {eff} >= ?"
        params.append(stale_cutoff)

    if category == "najnowsze":
        sql += f" ORDER BY {eff} DESC"
    else:
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
    """Oznacza artykuł jako przeczytany (bez treści, po article_key)."""
    with _connect() as conn:
        conn.execute("UPDATE articles SET is_read = 1 WHERE article_key = ?", (_key(link),))


def set_favorite(link, is_favorite):
    """Ustawia oznaczenie artykułu jako ulubionego (1/0, po article_key)."""
    with _connect() as conn:
        conn.execute(
            "UPDATE articles SET is_favorite = ? WHERE article_key = ?",
            (1 if is_favorite else 0, _key(link)),
        )


def recent_published_timestamps(limit=40):
    """Zwraca listę timestampów epoch (UTC) dat publikacji artykułów,
    posortowaną malejąco (najnowsze pierwsze). Używana jako zaufana
    kotwica czasu (daty pochodzą z serwerów Onetu, nie z zegara użytkownika).
    Artykuły bez daty są pomijane."""
    import time as _time
    from datetime import datetime, timezone
    out = []
    with _connect() as conn:
        rows = conn.execute(
            "SELECT published_at FROM articles WHERE published_at <> '' "
            "ORDER BY published_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    for r in rows:
        ts = _iso_to_epoch(r["published_at"])
        if ts is not None:
            out.append(ts)
    return out


def _iso_to_epoch(iso):
    try:
        s = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def get_setting(key, default=None):
    """Odczytuje ustawienie z tabeli settings (jako tekst) lub domyślną wartość."""
    try:
        with _connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return row["value"]
    except Exception:
        return default


def set_setting(key, value):
    """Zapisuje ustawienie (wartość konwertowana na tekst)."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )


def retention_days():
    """Liczba dni retencji artykułów (konfigurowalna, domyślnie RETENTION_DAYS)."""
    try:
        v = int(get_setting("retention_days", RETENTION_DAYS))
    except (TypeError, ValueError):
        v = RETENTION_DAYS
    return max(14, min(365, v))


def cleanup_old():
    """Usuwa artykuły nieaktualizowane dłużej niż retention_days dni.

    Artykuły oznaczone jako ulubione nigdy nie są usuwane automatycznie.
    """
    days = retention_days()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM articles WHERE last_seen < ? AND is_favorite = 0", (cutoff,)
        )
        return cur.rowcount


def migrate_categories(remap):
    """Przyporządkowuje kategorię treści wpisom 'glowna'/'najnowsze'.

    remap(link) -> nowa kategoria (z URL). Idempotentna.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT link FROM articles WHERE category IN ('glowna', 'najnowsze')"
        ).fetchall()
        for r in rows:
            new_cat = remap(r["link"]) or "wiadomosci"
            if new_cat not in ("glowna", "najnowsze"):
                conn.execute(
                    "UPDATE articles SET category = ? WHERE link = ?",
                    (new_cat, r["link"]),
                )
        return len(rows)


def migrate_article_keys(key_fn):
    """Wypełnia article_key i scala istniejące duplikaty.

    1. Ustawia article_key dla wierszy z pustym kluczem.
    2. Grupuje po article_key; dla grup z >1 wierszem zostawia jeden
       (najstarszy first_seen), scalając is_read/is_favorite/content/lead/image.
    Idempotentna.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT link FROM articles WHERE article_key = '' OR article_key IS NULL"
        ).fetchall()
        for r in rows:
            k = key_fn(r["link"]) or r["link"]
            conn.execute("UPDATE articles SET article_key = ? WHERE link = ?", (k, r["link"]))

        # scal duplikaty po article_key
        groups = conn.execute(
            """
            SELECT article_key, GROUP_CONCAT(link) AS links
            FROM articles WHERE article_key != '' GROUP BY article_key
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        merged = 0
        for g in groups:
            links = g["links"].split(",")
            keep = conn.execute(
                "SELECT * FROM articles WHERE link = ? ORDER BY first_seen ASC LIMIT 1",
                (links[0],),
            ).fetchone()
            keep_link = keep["link"]
            other_links = [l for l in links if l != keep_link]
            if not other_links:
                continue
            # scal flagi/treść z duplikatów do zachowanego wiersza
            for ol in other_links:
                dup = conn.execute("SELECT * FROM articles WHERE link = ?", (ol,)).fetchone()
                if dup:
                    conn.execute(
                        """
                        UPDATE articles SET
                            is_read = MAX(is_read, ?),
                            is_favorite = MAX(is_favorite, ?),
                            content = COALESCE(NULLIF(content, ''), ?),
                            lead = COALESCE(NULLIF(lead, ''), ?),
                            image = COALESCE(NULLIF(image, ''), ?),
                            summary = COALESCE(NULLIF(summary, ''), ?),
                            published_at = COALESCE(NULLIF(published_at, ''), ?)
                        WHERE link = ?
                        """,
                        (dup["is_read"], dup["is_favorite"], dup["content"], dup["lead"],
                         dup["image"], dup["summary"], dup["published_at"], keep_link),
                    )
                conn.execute("DELETE FROM articles WHERE link = ?", (ol,))
            merged += len(other_links)
        return merged